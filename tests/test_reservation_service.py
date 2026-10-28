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
