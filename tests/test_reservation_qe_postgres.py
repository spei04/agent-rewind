"""Native adversarial P2 qualification. Runs only under an explicit bounded PG grant."""

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
import test_migrations_postgres as migrations
from reservation_postgres_fixture import (
    build_postgres_reservation_case,
    with_postgres_service_key,
)
from reservation_postgres_qe_helpers import (
    assert_competitor_delta,
    bounded,
    build_expiring_period_case,
    claim,
    micros,
    record,
    report,
    state,
)
from reservation_qe_fixture import expected_reservation, intent, one, same
from sqlalchemy import event, text
from test_scoped_actions_postgres import observe_actor, wait_blocked

from agent_rewind import reservation, reservation_rows
from agent_rewind.reservation_connection import require_body
from agent_rewind.reservation_service import ReservationCoordinator
from agent_rewind.reservation_types import ReservationRefusal
from agent_rewind.scoped_lineage import ResourceNotFound

pg = migrations.pg
__all__ = ["pg"]
pytestmark = pytest.mark.skipif(
    not migrations.POSTGRES, reason="Opt-in synthetic PostgreSQL reservation adversaries"
)


def test_postgres_same_handle_transaction_replacement_refuses_before_writes(
    pg, tmp_path, monkeypatch, record_property
):
    case = build_postgres_reservation_case(pg, tmp_path, monkeypatch)
    try:
        fence = claim(case, record_property)
        before = state(case)
        original = reservation_rows.ReservationRows.require_headroom
        original_body = reservation.require_body
        witnesses, denials, writes = [], [], []

        def capture_body(connection, scope):
            try:
                return original_body(connection, scope)
            except ReservationRefusal as error:
                denials.append(error)
                raise

        def replace_transaction(self, after):
            original(self, after)
            connection = self.work._connection
            assert connection is not None
            body = require_body(connection, self.scope)
            root, raw = connection.get_transaction(), connection.connection.driver_connection
            first = connection.exec_driver_sql("SELECT pg_current_xact_id()::text").scalar_one()
            assert first == body.xid and raw.info.transaction_status.name == "INTRANS"
            # Explicit out-of-band fault, charged to the retained Work. The
            # coordinator does not acknowledge this COMMIT as its own operation.
            self.work.control_attempt("commit")
            with raw.cursor() as cursor:
                cursor.execute("COMMIT")
                assert raw.info.transaction_status.name == "IDLE"
                self.work.control_attempt("begin")
                cursor.execute("BEGIN")
            second = connection.exec_driver_sql("SELECT pg_current_xact_id()::text").scalar_one()
            assert first != second
            assert root is connection.get_transaction() and root.is_active
            assert raw is connection.connection.driver_connection
            assert raw.info.transaction_status.name == "INTRANS"
            witnesses.append(
                {
                    "original_xid": first,
                    "replacement_xid": second,
                    "same_root": root is body.root,
                    "same_raw": raw is body.raw,
                    "same_work": connection.info["operation_work"] is self.work,
                    "raw_commit_occurred": True,
                    "rollback_scope": "Replacement only; original COMMIT had no writes.",
                }
            )

        def observe(_connection, _cursor, statement, *_args):
            if statement.lstrip().split(None, 1)[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
                writes.append(statement)

        monkeypatch.setattr(
            reservation_rows.ReservationRows, "require_headroom", replace_transaction
        )
        monkeypatch.setattr(reservation, "require_body", capture_body)
        event.listen(case.engine, "before_cursor_execute", observe)
        owner = ReservationCoordinator(case.engine, case.authority)
        try:
            with pytest.raises(ReservationRefusal) as caught:
                owner.reserve(case.principal, case.context, fence, intent(case, fence))
        finally:
            event.remove(case.engine, "before_cursor_execute", observe)
            report(record_property, "replacement_owner", owner)
            record(record_property, "replacement_witness", witnesses)
        assert caught.value.reason == "transaction_not_owned"
        assert len(denials) == 1 and caught.value is denials[0]
        assert len(witnesses) == 1 and all(
            witnesses[0][name] for name in ("same_root", "same_raw", "same_work")
        )
        assert writes == []
        assert owner.outcome.rollback_acknowledged and not owner.outcome.commit_attempted
        bounded(owner)
        assert case.engine.pool.checkedout() == 0
        same(before, state(case))
    finally:
        case.close()


def test_postgres_eight_two_project_reservations_share_organization_cap(
    pg, tmp_path, monkeypatch, record_property
):
    # This shared seam must be committed/reviewed before any native invocation.
    from reservation_postgres_fixture import with_postgres_second_project

    first = build_postgres_reservation_case(pg, tmp_path, monkeypatch, account_limit=10)
    try:
        second = with_postgres_second_project(first, tmp_path, monkeypatch)
        cases = (first, second)
        fences = (claim(first, record_property, 141000), claim(second, record_property, 141001))
        before = state(first)
        assert first.project_id != second.project_id and first.job_id != second.job_id
        assert first.account_ids[0] == second.account_ids[0]
        assert one(before, "budget_accounts", id=first.account_ids[0])["limit_microusd"] == 10
        values = [
            intent(cases[index % 2], fences[index % 2], amount=3, number=141100 + index * 2)
            for index in range(8)
        ]
        barrier, pids = Barrier(8), []
        owners = [ReservationCoordinator(first.engine, first.authority) for _ in range(8)]

        def simultaneous_checkout(raw, _record, _proxy):
            pids.append(raw.info.backend_pid)
            barrier.wait(timeout=3)

        def attempt(index):
            target, owner = cases[index % 2], owners[index]
            try:
                result = owner.reserve(
                    target.principal, target.context, fences[index % 2], values[index]
                )
            except ReservationRefusal as error:
                assert error.reason == "budget_exceeded"
                assert owner.outcome.confirmed_precommit_rollback
                bounded(owner)
                return None
            assert result.kind == "created" and result.record.identity == values[index]
            assert owner.outcome.commit_acknowledged
            bounded(owner)
            return values[index]

        event.listen(first.engine, "checkout", simultaneous_checkout)
        try:
            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = [pool.submit(attempt, index) for index in range(8)]
                results = [future.result(timeout=20) for future in futures]
        finally:
            event.remove(first.engine, "checkout", simultaneous_checkout)
            for index, owner in enumerate(owners):
                report(record_property, "contender_" + str(index), owner)
            record(record_property, "contender_backend_pids", pids)
        assert len(pids) == len(set(pids)) == 8
        accepted = [value for value in results if value is not None]
        assert len(accepted) == 3
        after, expected = state(first), before
        for value in accepted:
            expected = expected_reservation(expected, after, value, first.organization_id)
        same(expected, after)
        assert one(after, "budget_accounts", id=first.account_ids[0])["held_microusd"] == 9
        for target in cases:
            count = sum(value.project_id == target.project_id for value in accepted)
            assert one(after, "jobs", id=target.job_id)["reserved"] == 3 * count
            for account_id in target.account_ids[1:]:
                assert one(after, "budget_accounts", id=account_id)["held_microusd"] == 3 * count
        assert first.engine.pool.checkedout() == 0
    finally:
        # The second case shares this engine/fixture; close exactly once.
        first.close()


def competitor_change(writer, case, change):
    if change == "member_revoked":
        observed = writer.execute(
            text(
                "UPDATE project_memberships SET revoked_at=clock_timestamp() "
                "WHERE project_id=:project AND principal_id=:principal RETURNING revoked_at"
            ),
            {"project": case.project_id, "principal": case.principal.principal_id},
        ).scalar_one()
        return (
            "project_memberships",
            {"project_id": case.project_id, "principal_id": case.principal.principal_id},
            {"revoked_at": observed},
        )
    if change.startswith("key_"):
        key_id = case.principal.principal_id.removeprefix("api-key:")
        if change == "key_revoked":
            writer.execute(text("UPDATE api_keys SET revoked=true WHERE id=:id"), {"id": key_id})
            return "api_keys", {"id": key_id}, {"revoked": True}
        expires = writer.execute(
            text(
                "UPDATE api_keys SET expires=extract(epoch from clock_timestamp())+0.05 "
                "WHERE id=:id RETURNING expires"
            ),
            {"id": key_id},
        ).scalar_one()
        deadline = time.monotonic() + 1
        while time.time() <= expires:
            assert time.monotonic() < deadline, "actual key expiry not observed"
            Event().wait(0.01)
        return "api_keys", {"id": key_id}, {"expires": expires}
    expressions = {
        "cancel": ("cancel", "true"),
        "generation": ("lease_generation", "lease_generation+1"),
        "lease": ("lease_until", "extract(epoch from clock_timestamp())-0.001"),
    }
    field, expression = expressions[change]
    value = writer.execute(
        text(f"UPDATE jobs SET {field}={expression} WHERE id=:id RETURNING {field}"),
        {"id": case.job_id},
    ).scalar_one()
    return "jobs", {"id": case.job_id}, {field: value}


@pytest.mark.parametrize(
    "change", ["member_revoked", "key_revoked", "key_expired", "cancel", "generation", "lease"]
)
def test_postgres_acquisition_wait_revalidates_authority_and_job(
    pg, tmp_path, monkeypatch, record_property, change
):
    case = build_postgres_reservation_case(pg, tmp_path, monkeypatch)
    if change.startswith("key_"):
        case = with_postgres_service_key(case)
    try:
        fence = claim(case, record_property)
        before = state(case)
        ready, pids, listener = observe_actor(case.engine)
        owner = ReservationCoordinator(case.engine, case.authority)
        original_authority, original_live = case.authority.check, reservation._live
        denials, wait_observation = [], {}

        def checked(*args, **kwargs):
            try:
                return original_authority(*args, **kwargs)
            except ResourceNotFound as error:
                denials.append(error)
                raise

        def live(*args):
            try:
                return original_live(*args)
            except ReservationRefusal as error:
                denials.append(error)
                raise

        monkeypatch.setattr(case.authority, "check", checked)
        monkeypatch.setattr(reservation, "_live", live)
        expected_error = (
            ResourceNotFound if change.endswith(("revoked", "expired")) else ReservationRefusal
        )
        try:
            with pg["owner"].connect() as writer, ThreadPoolExecutor(max_workers=1) as pool:
                writer.exec_driver_sql("SET LOCAL statement_timeout='3s'")
                writer.exec_driver_sql("SET LOCAL lock_timeout='3s'")
                writer.execute(
                    text("SELECT id FROM organizations WHERE id=:id FOR UPDATE"),
                    {"id": case.organization_id},
                ).scalar_one()
                blocker = writer.connection.driver_connection.info.backend_pid
                future = pool.submit(
                    owner.reserve, case.principal, case.context, fence, intent(case, fence)
                )
                try:
                    assert ready.wait(3)
                    assert len(pids) == 1 and pids[0] != blocker and not future.done()
                    wait_blocked(pg, pids[0], blocker)
                    wait_observation.update(
                        actor_pid=pids[0], blocker_pid=blocker, native_dependency_observed=True
                    )
                    table, selectors, changes = competitor_change(writer, case, change)
                    assert not future.done()
                    writer.commit()
                    wait_observation["competitor_commit_acknowledged"] = True
                    with pytest.raises(expected_error) as caught:
                        future.result(timeout=10)
                finally:
                    writer.rollback()
        finally:
            event.remove(case.engine, "checkout", listener)
            report(record_property, "waiter", owner)
            record(
                record_property,
                "observed_wait",
                {"actor_pids": pids, "change": change, **wait_observation},
            )
        assert len(denials) == 1 and caught.value is denials[0]
        if isinstance(caught.value, ReservationRefusal):
            assert caught.value.reason == "job_not_live"
        assert owner.outcome.confirmed_precommit_rollback
        assert not owner.outcome.commit_attempted
        bounded(owner)
        assert case.engine.pool.checkedout() == 0
        after = state(case)
        assert_competitor_delta(before, after, table, selectors, changes)
        record(record_property, "exact_competitor_delta", (table, selectors, changes))
    finally:
        case.close()


@pytest.mark.parametrize("selected", ["organization", "project"])
def test_postgres_final_period_fence_observes_injected_constraint_latency(
    pg, tmp_path, monkeypatch, record_property, selected
):
    case, fence, selected_end, before = build_expiring_period_case(
        pg, tmp_path, monkeypatch, selected, record_property
    )
    try:
        # Reuse the complete immediately post-provision snapshot; no intervening
        # mutation or redundant catalog scan consumes the short period.
        selected_rows = [one(before, "budget_accounts", id=key) for key in case.account_ids]
        owner = ReservationCoordinator(case.engine, case.authority)
        original_clock, original_final = reservation._clock, reservation.final_fence
        clocks, constraints, writes, waits, denials = [], [], [], [], []

        def native_clock(connection):
            value = original_clock(connection)
            clocks.append(value)
            return value

        def final_fence(*args):
            try:
                return original_final(*args)
            except ReservationRefusal as error:
                denials.append(error)
                raise

        def inject(connection, _cursor, statement, *_args):
            command = statement.lstrip().split(None, 1)[0].upper()
            if command in {"INSERT", "UPDATE"}:
                writes.append(statement)
            if not statement.startswith("SET CONSTRAINTS "):
                return
            assert constraints == [] and len(writes) == 9
            work = owner._work
            assert connection.info["operation_work"] is work
            before_units = work.statements
            now = connection.exec_driver_sql("SELECT clock_timestamp()").scalar_one()
            assert len(clocks) == 1
            assert all(
                micros(row["period_start"]) <= clocks[0] < micros(row["period_end"])
                for row in selected_rows
            )
            delay = (selected_end - now).total_seconds() + 0.02
            statement_ms, _lock_ms = work.remaining_timeouts_ms()
            assert 0 < delay < 4.1 and delay * 1000 + 100 < statement_ms
            raw = connection.connection.driver_connection
            connection.execute(text("SELECT pg_sleep(:delay)"), {"delay": delay}).scalar_one()
            assert connection.info["operation_work"] is work
            assert connection.connection.driver_connection is raw
            waits.append(
                {
                    "before_native_time": now,
                    "selected_end": selected_end,
                    "requested_sleep_seconds": delay,
                    "same_work": True,
                    "same_raw": True,
                    "before_units": before_units,
                    "after_units": work.statements,
                    "qualification": "Injected native latency before SET; no natural FK wait.",
                }
            )

        def completed(_connection, _cursor, statement, *_args):
            if statement.startswith("SET CONSTRAINTS "):
                constraints.append(statement)

        monkeypatch.setattr(reservation, "_clock", native_clock)
        monkeypatch.setattr(reservation, "final_fence", final_fence)
        event.listen(case.engine, "before_cursor_execute", inject)
        event.listen(case.engine, "after_cursor_execute", completed)
        try:
            with pytest.raises(ReservationRefusal) as caught:
                owner.reserve(case.principal, case.context, fence, intent(case, fence))
        finally:
            event.remove(case.engine, "before_cursor_execute", inject)
            event.remove(case.engine, "after_cursor_execute", completed)
            report(record_property, "final_period_owner", owner)
            record(
                record_property,
                "constraint_latency",
                {
                    "waits": waits,
                    "clock_samples": clocks,
                    "constraints": constraints,
                    "writes": writes,
                },
            )
        assert caught.value.reason == "job_not_live"
        assert len(denials) == 1 and caught.value is denials[0]
        assert len(waits) == len(constraints) == 1 and len(clocks) == 2
        final = clocks[-1]
        expired = [row["scope"] for row in selected_rows if micros(row["period_end"]) <= final]
        assert expired == [selected] and micros(selected_end) <= final
        assert one(before, "jobs", id=case.job_id)["lease_until"] * 1_000_000 > final
        assert owner.outcome.confirmed_precommit_rollback
        assert not owner.outcome.commit_attempted
        bounded(owner)
        assert case.engine.pool.checkedout() == 0
        same(before, state(case))
    finally:
        case.close()
