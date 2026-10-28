"""Author controls exercise the internal coordinator against real admitted/P1 state."""

import pytest
from ledger_eligibility_fixture import rows
from reservation_fixture import build_reservation_case


@pytest.fixture
def reservation_case(tmp_path, monkeypatch, request):
    case = build_reservation_case(tmp_path, monkeypatch, legacy=getattr(request, "param", False))
    try:
        yield case
    finally:
        case.close()


@pytest.mark.parametrize("reservation_case", [False, True], indirect=True, ids=["fresh", "legacy"])
def test_reservation_setup_retains_real_admission_and_provisioned_identity(reservation_case):
    case = reservation_case
    state = case.snapshot()
    (job,) = [row for row in rows(state, "jobs") if row["id"] == case.job_id]
    assert job["id"] == case.job_id
    assert (job["kind"], job["payload_version"], job["budget"], job["reserved"]) == (
        "run",
        2,
        1_000_000,
        0,
    )
    assert (job["status"], job["owner"], job["lease_until"], job["lease_generation"]) == (
        "queued",
        None,
        None,
        0,
    )
    accounts = {row["id"]: row for row in rows(state, "budget_accounts")}
    assert set(case.account_ids) <= set(accounts)
    assert all(row["held_microusd"] == row["opening_held_microusd"] for row in accounts.values())
    assert accounts[case.account_ids[2]]["held_microusd"] == 0
    assert accounts[case.account_ids[0]]["held_microusd"] == (245000 if case.case.legacy else 0)
    assert rows(state, "provider_calls") == rows(state, "budget_entries") == []
    assert len(rows(state, "operations")) == 1
    assert case.admission.ciphertexts and case.admission.journal_hashes
    assert case.authority.engine is case.engine
    assert case.engine.pool.size() == 8 and case.engine.pool.checkedout() == 0


def test_shared_reader_receipts_preserve_existing_rows_counts_and_canonical_limit(reservation_case):
    from copy import deepcopy

    from agent_rewind.admission_transaction import TransactionOutcome, admission_transaction
    from agent_rewind.migrations.ledger_reader_financial import (
        CAP,
        financial_size,
        read_financial,
        read_financial_projection,
    )
    from agent_rewind.migrations.ledger_reader_graph import read_source_bounds, source_bounds
    from agent_rewind.migrations.schema import LEDGER, MigrationRefused
    from agent_rewind.operation_work import OperationWork

    case = reservation_case
    before = case.snapshot()
    work, outcome = OperationWork(include_acquisition=True), TransactionOutcome()
    with admission_transaction(case.engine, outcome, work=work) as connection:
        projection = read_financial_projection(connection, LEDGER, work)
        assert projection.rows == read_financial(connection, LEDGER, work)
        assert projection.canonical_bytes == financial_size(projection.rows, LEDGER, work)
        assert projection.row_count == sum(len(values) for values in projection.rows.values())
        assert projection.native_bytes <= CAP
        source = read_source_bounds(connection, work)
        assert {name: value.rows for name, value in source.items()} == source_bounds(
            connection, work
        )
        assert {name: value.rows for name, value in source.items()} == {
            name: len(before["tables"][name]["rows"]) for name in source
        }
        oversized = deepcopy(projection.rows)
        oversized["job"][0]["error"] = "x" * CAP
        with pytest.raises(MigrationRefused, match="^ledger_limit_exceeded$"):
            financial_size(oversized, LEDGER, work)
    assert outcome.commit_acknowledged and not outcome.cleanup_failed
    assert case.snapshot() == before


def test_complete_sqlite_claim_has_exact_delta_and_bounded_work(
    reservation_case, monkeypatch, record_property
):
    from sqlalchemy import event

    from agent_rewind import reservation_rows
    from agent_rewind.reservation_service import ReservationCoordinator
    from agent_rewind.reservation_types import ClaimIntent, JobFence

    case = reservation_case
    before = case.snapshot()
    queries = []
    history_units = []
    original = reservation_rows.validated_ar7_history

    def history(connection, work):
        start = work.statements
        try:
            return original(connection, work)
        finally:
            history_units.append(work.statements - start)

    monkeypatch.setattr(reservation_rows, "validated_ar7_history", history)

    def listener(_c, _cur, sql, *_args):
        queries.append(sql)

    event.listen(case.engine, "before_cursor_execute", listener)
    owner = ReservationCoordinator(case.engine, case.authority)
    try:
        fence = owner.claim_generation(
            case.principal, case.context, ClaimIntent(case.job_id, "a" * 32, 0, 60)
        )
    finally:
        event.remove(case.engine, "before_cursor_execute", listener)
        work = owner._work
        assert work is not None
        record_property("work_statements", work.statements)
        record_property("work_seconds", work.seconds)
        record_property("work_vm_instructions", work.instructions)
        record_property("observed_sql", len(queries))
        record_property("history_units", str(history_units))
        record_property("transaction_outcome", str(owner.outcome))
    assert fence == JobFence(case.job_id, "a" * 32, 1)
    assert owner.outcome.commit_acknowledged and not owner.outcome.cleanup_failed
    assert work.statements <= 512 and work.seconds < 10
    after = case.snapshot()
    changed = [name for name in before["tables"] if before["tables"][name] != after["tables"][name]]
    assert changed == ["jobs"]
    old = next(row for row in rows(before, "jobs") if row["id"] == case.job_id)
    new = next(row for row in rows(after, "jobs") if row["id"] == case.job_id)
    assert {key for key in old if old[key] != new[key]} == {
        "status",
        "owner",
        "lease_until",
        "lease_generation",
    }
    assert (new["status"], new["owner"], new["lease_generation"]) == ("running", "a" * 32, 1)
    assert isinstance(new["lease_until"], float)
    assert case.engine.pool.checkedout() == 0


def _claimed(case):
    from agent_rewind.reservation_service import ReservationCoordinator
    from agent_rewind.reservation_types import ClaimIntent

    owner = ReservationCoordinator(case.engine, case.authority)
    return owner.claim_generation(
        case.principal, case.context, ClaimIntent(case.job_id, "a" * 32, 0, 60)
    )


def _intent(case, amount=12345):
    from agent_rewind.reservation_types import ReservationIntent

    return ReservationIntent(
        call_id="b" * 32,
        project_id=case.project_id,
        job_id=case.job_id,
        logical_call_id="c" * 32,
        request_digest="d" * 64,
        purpose="continuation",
        price_version=case.price_version,
        reserved_microusd=amount,
        lease_generation=1,
        organization_account_id=case.account_ids[0],
        project_account_id=case.account_ids[1],
        job_account_id=case.account_ids[2],
    )


def test_atomic_reservation_and_exact_original_repeat(reservation_case, record_property):
    from dataclasses import replace

    from agent_rewind.reservation_service import ReservationCoordinator
    from agent_rewind.reservation_types import (
        CallMatching,
        CreatedReservation,
        OriginalReservation,
        ReservationRefusal,
    )

    case = reservation_case
    fence = _claimed(case)
    intent = _intent(case)
    before = case.snapshot()
    owner = ReservationCoordinator(case.engine, case.authority)
    try:
        result = owner.reserve(case.principal, case.context, fence, intent)
    finally:
        assert owner._work is not None
        record_property("reserve_work_statements", owner._work.statements)
        record_property("reserve_work_seconds", owner._work.seconds)
        record_property("reserve_work_vm", owner._work.instructions)
        record_property("reserve_outcome", str(owner.outcome))
    assert isinstance(result, CreatedReservation) and result.record.identity == intent
    assert owner.outcome.commit_acknowledged and not owner.outcome.cleanup_failed
    assert owner._work.statements <= 512 and owner._work.seconds < 10
    after = case.snapshot()
    changed = {name for name in before["tables"] if before["tables"][name] != after["tables"][name]}
    assert changed == {
        "jobs",
        "budget_accounts",
        "provider_calls",
        "budget_entries",
        "resource_scopes",
    }
    assert len(rows(after, "provider_calls")) == 1
    entries = rows(after, "budget_entries")
    assert len(entries) == 3
    assert {entry["account_id"] for entry in entries} == set(case.account_ids)
    assert all(
        entry["entry_kind"] == "reserve" and entry["amount_microusd"] == 12345 for entry in entries
    )
    old_accounts = {row["id"]: row for row in rows(before, "budget_accounts")}
    for account in rows(after, "budget_accounts"):
        assert account == {
            **old_accounts[account["id"]],
            "held_microusd": old_accounts[account["id"]]["held_microusd"]
            + (12345 if account["id"] in case.account_ids else 0),
        }
    job = next(row for row in rows(after, "jobs") if row["id"] == case.job_id)
    assert job["reserved"] == 12345
    repeat = ReservationCoordinator(case.engine, case.authority).reserve(
        case.principal, case.context, fence, intent
    )
    assert isinstance(repeat, OriginalReservation) and repeat.record == result.record
    assert case.snapshot() == after
    inspected = ReservationCoordinator(case.engine, case.authority).inspect_original(
        case.principal, case.context, case.job_id, intent
    )
    assert isinstance(inspected.call, CallMatching) and inspected.call.record == result.record
    assert case.snapshot() == after
    conflict = ReservationCoordinator(case.engine, case.authority)
    with pytest.raises(ReservationRefusal) as caught:
        conflict.reserve(
            case.principal, case.context, fence, replace(intent, request_digest="e" * 64)
        )
    assert caught.value.reason == "identity_conflict"
    assert conflict.outcome.confirmed_precommit_rollback and case.snapshot() == after


def test_reservation_mid_write_failure_rolls_back_all_tables(reservation_case):
    from sqlalchemy import event

    from agent_rewind.admission_transaction import AdmissionError
    from agent_rewind.reservation_service import ReservationCoordinator

    case = reservation_case
    fence = _claimed(case)
    before = case.snapshot()
    completed_entries = []

    def fail(_c, _cur, sql, *_args):
        if sql.startswith("INSERT INTO budget_entries"):
            completed_entries.append(sql)
            if len(completed_entries) == 2:
                raise RuntimeError("injected-after-native-entry-write")

    owner = ReservationCoordinator(case.engine, case.authority)
    event.listen(case.engine, "after_cursor_execute", fail)
    try:
        with pytest.raises(AdmissionError, match="^dependency_unavailable$"):
            owner.reserve(case.principal, case.context, fence, _intent(case))
    finally:
        event.remove(case.engine, "after_cursor_execute", fail)
    assert len(completed_entries) == 2
    assert owner.outcome.confirmed_precommit_rollback and not owner.outcome.commit_attempted
    assert case.snapshot() == before
    assert case.engine.pool.checkedout() == 0
