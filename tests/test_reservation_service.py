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
