"""Direct ar8 paid-wrapper faults; no dispatch, provider requests, or retry.

Native publication/ACK/period tests use supported genuine fixtures. The named
SQLite corrupt-evidence cases are query/refusal components, not valid producer
states; their setup must finish before any consumer-refusal credit is possible.
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from threading import Event

import pytest
import reservation_postgres_fixture as pg_cases
import test_failure_persistence_native_oracle as genuine
import test_migrations_postgres as migration_tests
from failure_postgres_fixture import pg
from ledger_eligibility_postgres_fixture import refreshed
from ledger_provisioning_fixture import digest
from ledger_provisioning_postgres_fixture import invoke
from ledger_restore_authority import typed
from operation_failure_paid_oracle import (
    assert_reservation_delta,
    claim_intent,
    observe_paid,
    reservation_intent,
)
from operation_failure_service_oracle import one, service_key
from reservation_postgres_qe_helpers import micros, native_time, stamp, state
from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError
from test_failure_persistence_native_oracle import (
    assert_only_claim_changed,
    assert_same_state,
    genuine_failure_case,
    native_clock,
    whole_state,
)
from test_operation_failure_paid_oracle import case
from test_scoped_actions_postgres import observe_actor, wait_blocked

from agent_rewind import reservation_successor
from agent_rewind.admission_transaction import AdmissionError
from agent_rewind.failure_evidence import FailureRefusal
from agent_rewind.reservation_service import ReservationCoordinator
from agent_rewind.reservation_types import ReservationRefusal
from agent_rewind.scoped_lineage import ResourceNotFound

__all__ = ["case", "pg"]


def _record(record_property, name, value):
    record_property(name, json.dumps(typed(value), allow_nan=False))


def _claim(case, monkeypatch, record_property, principal=None, context=None):
    principal = case.principal if principal is None else principal
    context = case.context if context is None else context
    before = whole_state(case)
    coordinator = ReservationCoordinator(case.engine, case.authority)
    first = native_clock(case)
    with observe_paid(case, monkeypatch, record_property, coordinator):
        fence = coordinator._claim_successor(principal, context, claim_intent(case))
    last = native_clock(case)
    assert coordinator.outcome.commit_acknowledged
    assert not coordinator.outcome.cleanup_failed
    assert_only_claim_changed(before, whole_state(case), claim_intent(case), (first, last))
    return fence


def _call(coordinator, case, entry, fence, principal=None, context=None):
    principal = case.principal if principal is None else principal
    context = case.context if context is None else context
    if entry == "claim":
        assert fence is None
        return coordinator._claim_successor(principal, context, claim_intent(case))
    assert entry == "reserve" and fence is not None
    return coordinator._reserve_successor(
        principal, context, fence, reservation_intent(case, fence)
    )


def _rollback(coordinator):
    facts = coordinator.outcome
    assert facts.begun and facts.rollback_attempted and facts.rollback_acknowledged
    assert not facts.commit_attempted and not facts.commit_acknowledged
    assert not facts.cleanup_failed


def _publication(statement, parameters, case):
    """Classify actual native statements; never replace their result or rowcount."""
    sql = " ".join(statement.split()).lower()
    if sql.startswith("update jobs set status="):
        return "claim"
    if sql.startswith("insert into provider_calls"):
        return "call"
    if sql.startswith("insert into resource_scopes"):
        return "scope"
    if sql.startswith("insert into budget_entries"):
        index = case.account_ids.index(parameters["account_id"])
        return ("entry-organization", "entry-project", "entry-job")[index]
    if sql.startswith("update budget_accounts set held_microusd="):
        index = case.account_ids.index(parameters["id"])
        return ("held-organization", "held-project", "held-job")[index]
    if sql.startswith("update jobs set reserved="):
        return "gross"
    return None


def _order(case, entry):
    if entry == "claim":
        return ["claim"]
    held = {
        key: name
        for key, name in zip(
            case.account_ids, ("held-organization", "held-project", "held-job"), strict=True
        )
    }
    return [
        "call",
        "scope",
        "entry-organization",
        "entry-project",
        "entry-job",
        *(held[key] for key in sorted(held)),
        "gross",
    ]


@pytest.mark.parametrize(
    "target",
    [
        "claim",
        "call",
        "scope",
        "entry-organization",
        "entry-project",
        "entry-job",
        "held-organization",
        "held-project",
        "held-job",
        "gross",
    ],
)
def test_successor_each_native_publication_write_failure_rolls_back(
    case, monkeypatch, record_property, target
):
    entry = "claim" if target == "claim" else "reserve"
    fence = None if entry == "claim" else _claim(case, monkeypatch, record_property)
    before = whole_state(case)
    coordinator = ReservationCoordinator(case.engine, case.authority)
    observed = []
    canary = "synthetic F4 post-write fault"

    def completed(connection, cursor, statement, _parameters, context, _many):
        assert connection.engine is case.engine
        parameters = context.compiled_parameters[0] if context.compiled is not None else {}
        tag = _publication(statement, parameters, case)
        if tag is not None:
            assert cursor.rowcount == 1
            observed.append(tag)
            if tag == target:
                raise RuntimeError(canary)

    event.listen(case.engine, "after_cursor_execute", completed)
    try:
        with (
            observe_paid(case, monkeypatch, record_property, coordinator),
            pytest.raises(AdmissionError) as caught,
        ):
            _call(coordinator, case, entry, fence)
    finally:
        event.remove(case.engine, "after_cursor_execute", completed)
    assert caught.value.code == "dependency_unavailable"
    assert canary not in str(caught.value) and caught.value.__cause__ is None
    expected = _order(case, entry)
    assert observed == expected[: expected.index(target) + 1]
    _rollback(coordinator)
    assert_same_state(before, whole_state(case))
    _record(
        record_property,
        "f4_paid_publication_rollback",
        {
            "target": target,
            "actual_native_writes_before_failure": observed,
            "qualification": (
                "Controlled exception after a successful native write; no driver error invented."
            ),
            "transaction": asdict(coordinator.outcome),
        },
    )


@pytest.mark.parametrize("entry", ["claim", "reserve"])
@pytest.mark.parametrize(
    "failure",
    [
        "before_native_commit",
        "after_native_commit_before_ack",
        "after_ack_close",
    ],
)
def test_successor_paid_commit_uncertainty_retains_exact_native_effect_and_holds(
    case, monkeypatch, record_property, entry, failure
):
    fence = None if entry == "claim" else _claim(case, monkeypatch, record_property)
    before = whole_state(case)
    coordinator = ReservationCoordinator(case.engine, case.authority)
    original_commit, original_close = Connection.commit, Connection.close
    attempts, committed, close_failures = [], [], []
    canary = "synthetic F4 paid acknowledgement fault"

    def commit(connection):
        if connection.engine is not case.engine:
            return original_commit(connection)
        attempts.append(connection)
        assert len(attempts) == 1
        if failure == "before_native_commit":
            raise RuntimeError(canary)
        result = original_commit(connection)
        committed.append(connection)
        if failure == "after_native_commit_before_ack":
            raise RuntimeError(canary)
        return result

    def close(connection):
        if failure == "after_ack_close" and connection in committed and not close_failures:
            close_failures.append(connection)
            raise RuntimeError(canary)
        return original_close(connection)

    first = native_clock(case)
    with monkeypatch.context() as patch:
        patch.setattr(Connection, "commit", commit)
        patch.setattr(Connection, "close", close)
        with (
            observe_paid(case, patch, record_property, coordinator),
            pytest.raises(AdmissionError) as caught,
        ):
            _call(coordinator, case, entry, fence)
    last = native_clock(case)
    assert caught.value.code == "outcome_uncertain"
    assert canary not in str(caught.value)
    assert caught.value.__cause__ is None and caught.value.__suppress_context__
    assert len(attempts) == 1
    assert len(committed) == int(failure != "before_native_commit")
    assert len(close_failures) == int(failure == "after_ack_close")
    facts = coordinator.outcome
    assert facts.begun and facts.commit_attempted
    assert facts.commit_acknowledged is (failure == "after_ack_close")
    assert facts.cleanup_failed is (failure == "after_ack_close")
    after = whole_state(case)
    if failure == "before_native_commit":
        assert facts.rollback_acknowledged
        assert_same_state(before, after)
    elif entry == "claim":
        assert_only_claim_changed(before, after, claim_intent(case), (first, last))
    else:
        assert_reservation_delta(
            case, before, after, reservation_intent(case, fence), (first, last)
        )
    _record(
        record_property,
        "f4_paid_commit_uncertainty",
        {
            "entry": entry,
            "fault": failure,
            "transaction": asdict(facts),
            "commit_attempts": len(attempts),
            "actual_commits": len(committed),
            "retry_attempts": 0,
        },
    )


@pytest.mark.parametrize("target", ["claim", "held-organization", "gross"])
def test_successor_actual_zero_row_conditional_effect_rolls_back(
    case, monkeypatch, record_property, target
):
    entry = "claim" if target == "claim" else "reserve"
    fence = None if entry == "claim" else _claim(case, monkeypatch, record_property)
    before = whole_state(case)
    coordinator = ReservationCoordinator(case.engine, case.authority)
    original = Connection.execute
    injected, rowcounts = [], []

    def execute(connection, statement, *args, **kwargs):
        parameters = args[0] if args and isinstance(args[0], dict) else {}
        sql = " ".join(str(statement).split()).lower()
        tag = (
            _publication(str(statement), parameters, case)
            if sql.startswith(("update jobs set ", "update budget_accounts set "))
            else None
        )
        if connection.engine is case.engine and tag == target:
            assert not injected
            if target == "held-organization":
                changed = original(
                    connection,
                    text(
                        "UPDATE budget_accounts SET held_microusd=held_microusd+1 "
                        "WHERE id=:id RETURNING held_microusd"
                    ),
                    {"id": case.account_ids[0]},
                ).scalar_one()
            elif target == "claim":
                changed = original(
                    connection,
                    text(
                        "UPDATE jobs SET lease_generation=lease_generation+1 "
                        "WHERE id=:id RETURNING lease_generation"
                    ),
                    {"id": case.job_id},
                ).scalar_one()
            else:
                changed = original(
                    connection,
                    text("UPDATE jobs SET reserved=reserved+1 WHERE id=:id RETURNING reserved"),
                    {"id": case.job_id},
                ).scalar_one()
            assert type(changed) is int
            injected.append(changed)
            actual = original(connection, statement, *args, **kwargs)
            rowcounts.append(actual.rowcount)
            return actual
        return original(connection, statement, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Connection, "execute", execute)
        with (
            observe_paid(case, patch, record_property, coordinator),
            pytest.raises(ReservationRefusal) as caught,
        ):
            _call(coordinator, case, entry, fence)
    assert len(injected) == 1 and rowcounts == [0]
    assert caught.value.reason == (
        "ledger_state_invalid" if target == "held-organization" else "job_not_live"
    )
    _rollback(coordinator)
    assert_same_state(before, whole_state(case))
    _record(
        record_property,
        "f4_paid_native_zero_row",
        {
            "target": target,
            "actual_rowcounts": rowcounts,
            "qualification": "Same-body native predicate drift, not a competing-writer proof.",
        },
    )


@pytest.mark.parametrize("entry", ["claim", "reserve"])
@pytest.mark.f4_owned_postgres
@pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL F4 deferred fault"
)
def test_successor_real_deferred_generation_failure_rolls_back_publication(
    pg, tmp_path, monkeypatch, record_property, entry
):
    with genuine_failure_case(tmp_path, monkeypatch, record_property, pg=pg) as fixture:
        selected = fixture.case
        fence = None if entry == "claim" else _claim(selected, monkeypatch, record_property)
        before = whole_state(selected)
        coordinator = ReservationCoordinator(selected.engine, selected.authority)
        original_flush, original_sql = (
            reservation_successor.flush_constraints,
            Connection.exec_driver_sql,
        )
        generations, sqlstates, flushes = [], [], []

        def sql(connection, statement, *args, **kwargs):
            chosen = connection.engine is selected.engine and statement.startswith(
                "SET CONSTRAINTS "
            )
            if chosen:
                flushes.append(statement)
            try:
                return original_sql(connection, statement, *args, **kwargs)
            except DBAPIError as error:
                if chosen:
                    sqlstates.append(error.orig.sqlstate)
                raise

        def flush(connection, scope):
            assert connection.engine is selected.engine and not generations
            for value in (0, 1):
                actual = connection.execute(
                    text(
                        "UPDATE jobs SET lease_generation=:value WHERE id=:id "
                        "RETURNING lease_generation"
                    ),
                    {"value": value, "id": selected.job_id},
                ).scalar_one()
                assert type(actual) is int and actual == value
                generations.append(actual)
            return original_flush(connection, scope)

        with monkeypatch.context() as patch:
            patch.setattr(Connection, "exec_driver_sql", sql)
            patch.setattr(reservation_successor, "flush_constraints", flush)
            with (
                observe_paid(selected, patch, record_property, coordinator) as statements,
                pytest.raises(AdmissionError) as caught,
            ):
                _call(coordinator, selected, entry, fence)
        assert generations == [0, 1] and sqlstates == ["23514"] and len(flushes) == 1
        assert caught.value.code == "dependency_unavailable"
        _rollback(coordinator)
        assert_same_state(before, whole_state(selected))
        _record(
            record_property,
            "f4_paid_deferred_failure",
            {
                "entry": entry,
                "native_generations": generations,
                "sqlstates": sqlstates,
                "flushes": flushes,
                "statement_count": len(statements),
            },
        )


def _sorted(snapshot):
    for table in snapshot["tables"].values():
        table["rows"].sort(key=lambda row: repr(typed(row)))
    return snapshot


def _marker(case, *, corrupt=None):
    """Owner setup only; corrupt variants explicitly lack valid-producer credit."""
    before = whole_state(case)
    job = one(before, "jobs", id=case.job_id)
    operation = one(before, "operations", id=case.admission.accepted["operation_id"])
    assert job["payload_version"] == 2 and job["status"] in {"queued", "running"}
    assert operation["failure_correlation_id"] is not None
    assert before["tables"]["job_failure_evidence"]["rows"] == []
    marker = {
        "schema_version": 1,
        "kind": "historical_marker",
        "project_id": case.project_id,
        "job_resource_kind": "job",
        "job_id": case.job_id,
        "operation_id": operation["id"],
        "lease_generation": job["lease_generation"],
        "job_status": job["status"],
        "cause": None,
        "phase": None,
        "origin_kind": "migration_marker",
        "correlation_id": "e" * 32,
        "association_sha256": "c" * 64,
        "source_sha256": "d" * 64,
        "created_at_micros": 0,
    }
    if corrupt == "foreign":
        assert case.project_id != "f" * 32
        marker["project_id"] = "f" * 32
    elif corrupt == "stale":
        marker["lease_generation"] += 1
    elif corrupt == "malformed":
        marker["source_sha256"] = b"not-native-text"
    else:
        assert corrupt is None
    columns = ",".join(marker)
    placeholders = ",".join(":" + name for name in marker)
    statement = text(f"INSERT INTO job_failure_evidence ({columns}) VALUES ({placeholders})")
    engine = case.case.engine
    if corrupt is None:
        with engine.begin() as connection:
            if hasattr(case, "pg"):
                assert (
                    connection.exec_driver_sql(
                        "SELECT current_user=session_user AND NOT EXISTS("
                        "SELECT 1 FROM pg_catalog.pg_class "
                        "WHERE relnamespace='public'::regnamespace "
                        "AND relkind='r' AND relowner<>current_user::regrole)"
                    ).scalar_one()
                    is True
                )
            assert (
                connection.execute(
                    text("UPDATE operations SET failure_correlation_id=NULL WHERE id=:operation"),
                    {"operation": operation["id"]},
                ).rowcount
                == 1
            )
            assert connection.execute(statement, marker).rowcount == 1
    else:
        assert not hasattr(case, "pg") and engine.dialect.name == "sqlite"
        # This explicitly constructs out-of-band corrupt evidence. All catalog
        # definitions/settings are restored before the real wrapper is invoked.
        # It cannot count as a supported migration or producer-state control.
        with engine.connect() as connection:
            triggers = list(
                connection.exec_driver_sql(
                    "SELECT name,sql FROM sqlite_master WHERE type='trigger' "
                    "AND tbl_name='job_failure_evidence' ORDER BY name"
                )
            )
            assert triggers and len(triggers) <= 8 and all(sql for _, sql in triggers)
            connection.rollback()
            foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()
            checks = connection.exec_driver_sql("PRAGMA ignore_check_constraints").scalar_one()
            connection.rollback()
            assert foreign_keys == 1 and checks == 0
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.exec_driver_sql("PRAGMA ignore_check_constraints=ON")
            connection.rollback()
            try:
                connection.exec_driver_sql("BEGIN IMMEDIATE")
                for name, _ in triggers:
                    quoted = connection.dialect.identifier_preparer.quote(name)
                    connection.exec_driver_sql(f"DROP TRIGGER {quoted}")
                assert (
                    connection.execute(
                        text(
                            "UPDATE operations SET failure_correlation_id=NULL WHERE id=:operation"
                        ),
                        {"operation": operation["id"]},
                    ).rowcount
                    == 1
                )
                assert connection.execute(statement, marker).rowcount == 1
                for _, sql in triggers:
                    connection.exec_driver_sql(sql)
                connection.commit()
            finally:
                connection.rollback()
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                connection.exec_driver_sql("PRAGMA ignore_check_constraints=OFF")
                assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
                assert (
                    connection.exec_driver_sql("PRAGMA ignore_check_constraints").scalar_one() == 0
                )
            restored = list(
                connection.exec_driver_sql(
                    "SELECT name,sql FROM sqlite_master WHERE type='trigger' "
                    "AND tbl_name='job_failure_evidence' ORDER BY name"
                )
            )
            assert [tuple(row) for row in restored] == [tuple(row) for row in triggers]
    expected = deepcopy(before)
    one(expected, "operations", id=operation["id"])["failure_correlation_id"] = None
    expected["tables"]["job_failure_evidence"]["rows"].append(marker)
    actual = whole_state(case)
    assert_same_state(_sorted(expected), actual)
    assert typed(actual["tables"]["job_failure_evidence"]["rows"][0]) == typed(marker)
    return actual


def _assert_presence_denial(case, monkeypatch, record_property, entry, fence, before):
    coordinator = ReservationCoordinator(case.engine, case.authority)
    original = reservation_successor._absence
    visits = []

    def absence(connection, scope):
        assert connection.engine is case.engine and scope.job_id == case.job_id
        visits.append(connection)
        return original(connection, scope)

    with monkeypatch.context() as patch:
        patch.setattr(reservation_successor, "_absence", absence)
        with (
            observe_paid(case, patch, record_property, coordinator) as statements,
            pytest.raises(FailureRefusal) as caught,
        ):
            _call(coordinator, case, entry, fence)
    assert caught.value.reason == "not_eligible"
    assert len(visits) == 1 and visits[0].closed
    assert not any(sql.lstrip().startswith(("INSERT", "UPDATE", "DELETE")) for sql, _ in statements)
    _rollback(coordinator)
    assert_same_state(before, whole_state(case))


@pytest.mark.parametrize("entry", ["claim", "reserve"])
def test_successor_valid_current_marker_denies_new_paid_effect(
    case, monkeypatch, record_property, entry
):
    fence = None if entry == "claim" else _claim(case, monkeypatch, record_property)
    before = _marker(case)
    _assert_presence_denial(case, monkeypatch, record_property, entry, fence, before)
    _record(
        record_property,
        "f4_paid_marker_denial",
        {
            "entry": entry,
            "native_insert_acknowledged": True,
            "qualification": (
                "Current native generation/status marker; no Error or paid authority derived."
            ),
        },
    )


@pytest.mark.parametrize("case", ["sqlite"], indirect=True)
@pytest.mark.parametrize("entry", ["claim", "reserve"])
@pytest.mark.parametrize("variant", ["foreign", "stale", "malformed"])
def test_successor_unfiltered_job_key_corrupt_evidence_component_refuses(
    case, monkeypatch, record_property, entry, variant
):
    fence = None if entry == "claim" else _claim(case, monkeypatch, record_property)
    before = _marker(case, corrupt=variant)
    _assert_presence_denial(case, monkeypatch, record_property, entry, fence, before)
    _record(
        record_property,
        "f4_paid_corrupt_evidence_component",
        {
            "entry": entry,
            "variant": variant,
            "actual_absence_gate_reached": True,
            "qualification": (
                "Deliberately corrupt SQLite evidence component, "
                "not a valid producer/full-path positive."
            ),
        },
    )


@pytest.mark.parametrize("entry", ["claim", "reserve"])
@pytest.mark.f4_owned_postgres
@pytest.mark.skipif(not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL F4 paid wait")
def test_successor_native_acquisition_wait_rechecks_revoked_service_key(
    pg, tmp_path, monkeypatch, record_property, entry
):
    with genuine_failure_case(tmp_path, monkeypatch, record_property, pg=pg) as fixture:
        selected = fixture.case
        principal, context = service_key(selected, selected.engine)
        fence = (
            None
            if entry == "claim"
            else _claim(selected, monkeypatch, record_property, principal, context)
        )
        before = whole_state(selected)
        key_id = principal.principal_id.removeprefix("api-key:")
        assert len(key_id) == 32
        coordinator = ReservationCoordinator(selected.engine, selected.authority)
        ready, pids, listener = observe_actor(selected.engine)
        original_check = selected.authority.check
        denials, native_wait = [], {}
        pool = ThreadPoolExecutor(max_workers=1)
        future = None

        def checked(*args, **kwargs):
            try:
                return original_check(*args, **kwargs)
            except ResourceNotFound as error:
                denials.append(error)
                raise

        try:
            with monkeypatch.context() as patch:
                patch.setattr(selected.authority, "check", checked)
                with pg["owner"].connect() as writer:
                    writer.exec_driver_sql("SET LOCAL statement_timeout='3s'")
                    writer.exec_driver_sql("SET LOCAL lock_timeout='3s'")
                    writer.execute(
                        text("SELECT id FROM organizations WHERE id=:id FOR UPDATE"),
                        {"id": selected.organization_id},
                    ).scalar_one()
                    blocker = writer.connection.driver_connection.info.backend_pid
                    try:
                        with observe_paid(selected, patch, record_property, coordinator):
                            future = pool.submit(
                                _call, coordinator, selected, entry, fence, principal, context
                            )
                            assert ready.wait(3)
                            assert len(pids) == 1 and pids[0] != blocker and not future.done()
                            wait_blocked(pg, pids[0], blocker)
                            native_wait.update(actor=pids[0], blocker=blocker, witnessed=True)
                            assert (
                                writer.execute(
                                    text("UPDATE api_keys SET revoked=true WHERE id=:id"),
                                    {"id": key_id},
                                ).rowcount
                                == 1
                            )
                            assert not future.done()
                            writer.commit()
                            native_wait["revocation_commit_acknowledged"] = True
                            with pytest.raises(ResourceNotFound) as caught:
                                future.result(timeout=10)
                    finally:
                        writer.rollback()
            assert len(denials) == 1 and caught.value is denials[0]
            assert future is not None and future.done()
            _rollback(coordinator)
            expected = deepcopy(before)
            one(expected, "api_keys", id=key_id)["revoked"] = True
            assert_same_state(expected, whole_state(selected))
            _record(
                record_property,
                "f4_paid_native_authority_wait",
                {
                    "entry": entry,
                    **native_wait,
                    "transaction": asdict(coordinator.outcome),
                },
            )
        finally:
            event.remove(selected.engine, "checkout", listener)
            # The native blocker is already released; the external owned-process
            # deadline remains authoritative if a client cannot finish.
            pool.shutdown(wait=False, cancel_futures=True)


@contextmanager
def _expiring_successor_case(pg, tmp_path, monkeypatch, record_property, selected):
    """Provision actual short periods before ar8; remove setup hooks before use."""
    original_builder = genuine.build_postgres_reservation_case
    original_manifest = pg_cases.initial_manifest
    boundary, provisioned = [], []

    def initial_manifest(fixture):
        manifest = original_manifest(fixture)
        end = native_time(pg) + timedelta(seconds=10)
        boundary.append(end)
        for account in manifest["accounts"]:
            if account["scope"] in {"organization", "project"}:
                account["period_end"] = stamp(end)
        return manifest

    def builder(*args, **kwargs):
        with monkeypatch.context() as initial:
            initial.setattr(pg_cases, "initial_manifest", initial_manifest)
            built = original_builder(*args, **kwargs)
        try:
            assert len(boundary) == 1 and not provisioned
            deadline = time.monotonic() + 14
            samples = 0
            while True:
                observed = native_time(pg)
                samples += 1
                if observed >= boundary[0]:
                    break
                assert time.monotonic() < deadline and samples <= 512
                Event().wait(min(0.05, max(0, (boundary[0] - observed).total_seconds())))
            fixture = refreshed(built.provisioning, pg)
            previous = built.admission.manifest
            before = state(built)
            with pg_cases.offline_postgres_ledger(
                built, lambda name, value: _record(record_property, name, value)
            ):
                start = native_time(pg)
                end = start + timedelta(seconds=45)
                accounts = []
                for number, family in enumerate(("organization", "project"), 982010):
                    old = next(row for row in previous["accounts"] if row["scope"] == family)
                    accounts.append(
                        {
                            **old,
                            "id": f"{number:032x}",
                            "period_start": stamp(boundary[0]),
                            "period_end": stamp(
                                end if family == selected else datetime(2100, 1, 1, tzinfo=UTC)
                            ),
                        }
                    )
                manifest = {
                    **previous,
                    "manifest_id": f"{982012:032x}",
                    "operation": "provision",
                    "source_digest": fixture.source,
                    "parent_manifest_digest": digest(previous),
                    "opening_accounts": None,
                    "accounts": accounts,
                }
                receipt = invoke(fixture, pg, manifest)
            assert receipt.account_rows == 2 and receipt.sequence == 1
            after = state(built)
            for table in set(before["tables"]) - {"budget_accounts", "migration_progress"}:
                assert typed(before["tables"][table]) == typed(after["tables"][table]), table
            old = {row["id"]: row for row in before["tables"]["budget_accounts"]["rows"]}
            current = {row["id"]: row for row in after["tables"]["budget_accounts"]["rows"]}
            assert set(current) == set(old) | {row["id"] for row in accounts}
            assert all(current[key] == value for key, value in old.items())
            assert all(
                current[row["id"]]["held_microusd"] == 0
                and current[row["id"]]["accounted_microusd"] == 0
                for row in accounts
            )
            provisioned.append((end, accounts, receipt.model_dump(mode="json")))
            _record(
                record_property,
                "f4_paid_period_setup",
                {
                    "initial_end": boundary[0],
                    "initial_expiry_samples": samples,
                    "selected_end": end,
                    "accounts": accounts,
                    "receipt": receipt.model_dump(mode="json"),
                    "qualification": (
                        "Real native P1 provision before ar8; fixed deadline is never extended."
                    ),
                },
            )
            return replace(
                built,
                provisioning=fixture,
                account_ids=(accounts[0]["id"], accounts[1]["id"], built.account_ids[2]),
            )
        except BaseException:
            built.close()
            raise

    with monkeypatch.context() as setup:
        setup.setattr(genuine, "build_postgres_reservation_case", builder)
        with genuine_failure_case(tmp_path, setup, record_property, pg=pg) as fixture:
            setup.undo()
            assert genuine.build_postgres_reservation_case is original_builder
            assert pg_cases.initial_manifest is original_manifest
            assert len(provisioned) == 1
            end, _, _ = provisioned[0]
            assert native_time(pg) < end, "Period expired during setup; no product-refusal credit."
            yield fixture.case, end


@pytest.mark.parametrize("selected", ["organization", "project"])
@pytest.mark.f4_owned_postgres
@pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL F4 selected period"
)
def test_successor_selected_period_expires_after_selection_while_job_lease_is_live(
    pg, tmp_path, monkeypatch, record_property, selected
):
    with _expiring_successor_case(pg, tmp_path, monkeypatch, record_property, selected) as (
        paid_case,
        selected_end,
    ):
        fence = _claim(paid_case, monkeypatch, record_property)
        before = whole_state(paid_case)
        accounts = [one(before, "budget_accounts", id=key) for key in paid_case.account_ids]
        alignment_started = time.monotonic()
        for _samples in range(1, 1025):
            observed = native_time(pg)
            remaining = (selected_end - observed).total_seconds()
            if remaining <= 4:
                break
            assert time.monotonic() - alignment_started < 45
            Event().wait(min(0.05, max(0, remaining - 4)))
        assert 0 < remaining <= 4, (
            "No captured-selection/expiry proof if setup misses its deadline."
        )
        assert one(before, "jobs", id=paid_case.job_id)["lease_until"] * 1_000_000 > micros(
            observed
        )
        coordinator = ReservationCoordinator(paid_case.engine, paid_case.authority)
        original_clock, original_final = (
            reservation_successor._clock,
            reservation_successor.final_fence,
        )
        clocks, writes, flushes, waits, denials = [], [], [], [], []

        def clock(connection):
            value = original_clock(connection)
            clocks.append(value)
            return value

        def final(*args, **kwargs):
            try:
                return original_final(*args, **kwargs)
            except ReservationRefusal as error:
                denials.append(error)
                raise

        def completed(_connection, _cursor, statement, _parameters, context, _many):
            parameters = context.compiled_parameters[0] if context.compiled is not None else {}
            tag = _publication(statement, parameters, paid_case)
            if tag is not None:
                writes.append(tag)
            if statement.startswith("SET CONSTRAINTS "):
                flushes.append(statement)

        def inject(connection, _cursor, statement, *_args):
            if not statement.startswith("SET CONSTRAINTS "):
                return
            assert writes == _order(paid_case, "reserve") and not waits and len(clocks) == 1
            assert all(
                micros(row["period_start"]) <= clocks[0] < micros(row["period_end"])
                for row in accounts
            )
            work = coordinator._work
            assert connection.info["operation_work"] is work
            now = connection.exec_driver_sql("SELECT clock_timestamp()").scalar_one()
            delay = (selected_end - now).total_seconds() + 0.02
            statement_ms, _ = work.remaining_timeouts_ms()
            assert 0 < delay < 4.1 and delay * 1000 + 100 < statement_ms
            raw = connection.connection.driver_connection
            connection.execute(text("SELECT pg_sleep(:delay)"), {"delay": delay}).scalar_one()
            assert connection.connection.driver_connection is raw
            waits.append(
                {
                    "native_before": now,
                    "selected_end": selected_end,
                    "delay": delay,
                    "qualification": (
                        "Injected bounded native latency, "
                        "not a naturally occurring constraint wait."
                    ),
                }
            )

        event.listen(paid_case.engine, "before_cursor_execute", inject)
        event.listen(paid_case.engine, "after_cursor_execute", completed)
        try:
            with monkeypatch.context() as patch:
                patch.setattr(reservation_successor, "_clock", clock)
                patch.setattr(reservation_successor, "final_fence", final)
                with (
                    observe_paid(paid_case, patch, record_property, coordinator),
                    pytest.raises(ReservationRefusal) as caught,
                ):
                    _call(coordinator, paid_case, "reserve", fence)
        finally:
            event.remove(paid_case.engine, "before_cursor_execute", inject)
            event.remove(paid_case.engine, "after_cursor_execute", completed)
        assert caught.value.reason == "job_not_live"
        assert len(denials) == 1 and caught.value is denials[0]
        assert len(waits) == len(flushes) == 1 and len(clocks) == 2
        final_clock = clocks[-1]
        assert [row["scope"] for row in accounts if micros(row["period_end"]) <= final_clock] == [
            selected
        ]
        assert micros(selected_end) <= final_clock
        assert one(before, "jobs", id=paid_case.job_id)["lease_until"] * 1_000_000 > final_clock
        _rollback(coordinator)
        assert_same_state(before, whole_state(paid_case))
        _record(
            record_property,
            "f4_paid_final_period_expiry",
            {
                "selected": selected,
                "clocks": clocks,
                "waits": waits,
                "alignment_samples": _samples,
                "job_lease_still_live": True,
                "transaction": asdict(coordinator.outcome),
            },
        )
