"""Bounded eight-contender checks against real P2 SQL transactions."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from reservation_fixture import build_reservation_case
from reservation_qe_fixture import (
    assert_claim,
    assert_released,
    assert_reservation,
    claim,
    coordinator,
    expected_reservation,
    identity,
    intent,
    remaining_capacity,
    same,
    snapshot,
)

from agent_rewind.reservation_types import ClaimIntent, ReservationRefusal


@pytest.fixture
def case(tmp_path, monkeypatch, fresh_sqlite_ar6_template):
    value = build_reservation_case(
        tmp_path, monkeypatch, fresh_ar6_template=fresh_sqlite_ar6_template
    )
    yield value
    value.close()


def compete(action):
    barrier = Barrier(8)

    def contender(index):
        barrier.wait(timeout=10)
        return action(index)

    with ThreadPoolExecutor(max_workers=8) as pool:
        pending = [pool.submit(contender, index) for index in range(8)]
        return [future.result(timeout=30) for future in pending]


def test_eight_named_claims_advance_generation_exactly_once(case):
    before = snapshot(case.engine)

    def attempt(index):
        operation = coordinator(case)
        try:
            fence = operation.claim_generation(
                case.principal,
                case.context,
                ClaimIntent(case.job_id, identity(95000 + index), 0, 60),
            )
        except ReservationRefusal as error:
            assert error.reason == "job_not_live"
            assert operation.outcome.confirmed_precommit_rollback
            return None
        assert operation.outcome.commit_acknowledged and not operation.outcome.cleanup_failed
        return fence

    results = compete(attempt)
    (winner,) = [value for value in results if value is not None]
    assert_claim(before, snapshot(case.engine), winner)
    assert_released(case.engine)


def test_eight_exact_repeats_publish_only_one_financial_triple(case):
    fence = claim(case)
    value = intent(case, fence)
    before = snapshot(case.engine)

    def attempt(_index):
        operation = coordinator(case)
        result = operation.reserve(case.principal, case.context, fence, value)
        assert operation.outcome.commit_acknowledged and not operation.outcome.cleanup_failed
        return result

    results = compete(attempt)
    assert [result.kind for result in results].count("created") == 1
    assert [result.kind for result in results].count("original") == 7
    assert all(result.record == results[0].record for result in results)
    assert_reservation(before, snapshot(case.engine), value, case.organization_id)
    assert_released(case.engine)


def test_eight_distinct_calls_admit_only_the_exact_remaining_capacity(case):
    fence = claim(case)
    before = snapshot(case.engine)
    remaining = remaining_capacity(before, case)
    amount = remaining // 3
    assert 0 < 3 * amount <= remaining < 4 * amount
    values = [intent(case, fence, amount=amount, number=96000 + index * 2) for index in range(8)]

    def attempt(index):
        operation = coordinator(case)
        try:
            result = operation.reserve(case.principal, case.context, fence, values[index])
        except ReservationRefusal as error:
            assert error.reason == "budget_exceeded"
            assert operation.outcome.confirmed_precommit_rollback
            return None
        assert result.kind == "created" and operation.outcome.commit_acknowledged
        return values[index]

    accepted = [value for value in compete(attempt) if value is not None]
    assert len(accepted) == 3
    after = snapshot(case.engine)
    expected = before
    for value in accepted:
        expected = expected_reservation(expected, after, value, case.organization_id)
    same(expected, after)
    assert_released(case.engine)


def test_eight_contenders_across_two_real_projects_share_one_organization_cap(
    tmp_path, monkeypatch
):
    from reservation_qe_fixture import build_two_project_case, one

    first, second = build_two_project_case(tmp_path, monkeypatch, account_limit=1_000_000)
    try:
        cases = (first, second)
        fences = (claim(first, owner=99100), claim(second, owner=99101))
        before = snapshot(first.engine)
        assert first.project_id != second.project_id and first.job_id != second.job_id
        assert first.account_ids[0] == second.account_ids[0]
        values = [
            intent(cases[i % 2], fences[i % 2], amount=333_333, number=99200 + i * 2)
            for i in range(8)
        ]

        def attempt(index):
            target = cases[index % 2]
            operation = coordinator(target)
            try:
                result = operation.reserve(
                    target.principal, target.context, fences[index % 2], values[index]
                )
            except ReservationRefusal as error:
                assert error.reason == "budget_exceeded"
                assert operation.outcome.confirmed_precommit_rollback
                return None
            assert result.kind == "created" and operation.outcome.commit_acknowledged
            return values[index]

        accepted = [value for value in compete(attempt) if value is not None]
        assert len(accepted) == 3
        after = snapshot(first.engine)
        expected = before
        for value in accepted:
            expected = expected_reservation(expected, after, value, first.organization_id)
        same(expected, after)
        organization = one(after, "budget_accounts", id=first.account_ids[0])
        assert organization["held_microusd"] == 999_999
        for target in cases:
            count = sum(value.project_id == target.project_id for value in accepted)
            assert one(after, "jobs", id=target.job_id)["reserved"] == count * 333_333
            assert (
                one(after, "budget_accounts", id=target.account_ids[1])["held_microusd"]
                == count * 333_333
            )
        assert_released(first.engine)
    finally:
        first.close()


@pytest.mark.parametrize("change", ["cancel", "generation", "owner", "lease", "record_role"])
def test_waiting_reservation_rechecks_state_committed_during_acquisition(case, change):
    from copy import deepcopy
    from threading import Event, get_ident

    from reservation_qe_fixture import one
    from sqlalchemy import event, text

    from agent_rewind.request_authority import ActionForbidden
    from agent_rewind.sqlite_ownership import owned_connect

    fence = claim(case)
    value = intent(case, fence)
    before = snapshot(case.engine)
    expected = deepcopy(before)
    attempted = Event()
    observed = []
    operation = coordinator(case)
    parent = get_ident()

    def attempting(connection, _cursor, statement, _parameters, _context, _many):
        if get_ident() != parent and statement == "BEGIN IMMEDIATE":
            observed.append(connection)
            attempted.set()

    # Hold a genuine writer transaction before the P2 owner attempts its own
    # BEGIN. The event orders the adversary after invocation; no sleep or
    # substituted production wait/timeout is used or credited as elapsed proof.
    with ThreadPoolExecutor(max_workers=1) as pool:
        event.listen(case.engine, "before_cursor_execute", attempting)
        try:
            with owned_connect(case.engine) as blocker:
                blocker.exec_driver_sql("BEGIN IMMEDIATE")
                pending = pool.submit(operation.reserve, case.principal, case.context, fence, value)
                assert attempted.wait(timeout=2) and len(observed) == 1
                assert (
                    observed[0].connection.driver_connection
                    is not blocker.connection.driver_connection
                )
                assert not pending.done()
                if change == "record_role":
                    blocker.execute(
                        text(
                            "UPDATE project_memberships SET role='viewer' "
                            "WHERE project_id=:p AND principal_id=:u"
                        ),
                        {"p": case.project_id, "u": case.principal.principal_id},
                    )
                    one(
                        expected,
                        "project_memberships",
                        project_id=case.project_id,
                        principal_id=case.principal.principal_id,
                    )["role"] = "viewer"
                else:
                    changes = {
                        "cancel": ("cancel", 1),
                        "generation": ("lease_generation", fence.generation + 1),
                        "owner": ("owner", identity(99990)),
                        "lease": ("lease_until", 1.0),
                    }
                    field, changed = changes[change]
                    blocker.execute(
                        text(f"UPDATE jobs SET {field}=:value WHERE id=:id"),
                        {"value": changed, "id": case.job_id},
                    )
                    one(expected, "jobs", id=case.job_id)[field] = changed
                blocker.commit()
            refused = ActionForbidden if change == "record_role" else ReservationRefusal
            with pytest.raises(refused) as caught:
                pending.result(timeout=15)
            if change != "record_role":
                assert caught.value.reason == "job_not_live"
        finally:
            event.remove(case.engine, "before_cursor_execute", attempting)
    assert operation.outcome.confirmed_precommit_rollback
    assert not operation.outcome.commit_attempted
    same(expected, snapshot(case.engine))
    assert_released(case.engine)
