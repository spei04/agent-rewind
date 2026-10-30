"""Native dispatch-component tests; setup adapters do not establish live readiness."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest
from ledger_eligibility_fixture import rows
from sqlalchemy import text
from sqlalchemy.engine import Connection
from test_admission_configuration import configuration, configuration_value
from test_reservation_service import _claimed, _intent, reservation_case

from agent_rewind.admission_transaction import AdmissionError
from agent_rewind.dispatch import DispatchCoordinator
from agent_rewind.reservation_service import ReservationCoordinator
from agent_rewind.reservation_types import CreatedReservation, ReservationRefusal
from agent_rewind.sqlite_ownership import owned_begin

__all__ = ["reservation_case"]
REQUEST = b'{"messages":[],"model":"model-revision-1"}'


@pytest.fixture(autouse=True)
def observe_acknowledged_reservation(reservation_case, monkeypatch):
    case = reservation_case
    original = ReservationCoordinator.reserve

    def reserve(owner, *args, **kwargs):
        result = original(owner, *args, **kwargs)
        if isinstance(result, CreatedReservation):
            case.reserved_snapshot = case.snapshot()
        return result

    monkeypatch.setattr(ReservationCoordinator, "reserve", reserve)


class Adapter:
    configuration = configuration()

    def __init__(self, case, *, failure=False):
        self.case = case
        self.calls = []
        self.failure = failure

    def validate_request(self, request, reserved_microusd):
        assert request == REQUEST
        assert reserved_microusd == 12345
        assert self.case.engine.pool.checkedout() == 0

    def send(self, request):
        assert self.case.engine.pool.checkedout() == 0
        self.calls.append(request)
        if self.failure:
            raise RuntimeError("private-provider-canary")
        return b"response"


def reserved(case):
    fence = _claimed(case)
    identity = replace(_intent(case), request_digest=hashlib.sha256(REQUEST).hexdigest())
    return fence, identity


def invoke(case, adapter, fence, identity, *, owner=None, request=REQUEST):
    owner = owner or DispatchCoordinator(case.engine, case.authority, adapter)
    return owner.dispatch(case.principal, case.context, fence, identity, request)


def state_only(before, after, identity):
    # Whole-state oracle: the sole changed cell is this call's state.
    expected = rows(before, "provider_calls")
    actual = rows(after, "provider_calls")
    assert actual == [
        {**row, "state": "dispatching"} if row["id"] == identity.call_id else row
        for row in expected
    ]
    for name in before["tables"]:
        if name != "provider_calls":
            assert after["tables"][name] == before["tables"][name], name


def test_transition_commits_before_one_call_and_restart_cannot_dispatch(
    reservation_case, record_property
):
    case = reservation_case
    fence, identity = reserved(case)
    adapter = Adapter(case)
    owner = DispatchCoordinator(case.engine, case.authority, adapter)
    assert invoke(case, adapter, fence, identity, owner=owner) == b"response"
    assert owner.outcome.commit_acknowledged and not owner.outcome.cleanup_failed
    assert owner._work.statements <= 512 and owner._work.seconds < 10
    # Read only the invocation's retained Work counters after both cleanups.
    record_property(
        "dispatch_work",
        json.dumps(
            {
                phase: {
                    "statements": work.statements,
                    "seconds": work.seconds,
                    "vm_instructions": work.instructions,
                    "commit_acknowledged": outcome.commit_acknowledged,
                    "cleanup_failed": outcome.cleanup_failed,
                }
                for phase, work, outcome in (
                    ("reservation", owner._reservation._work, owner.reservation_outcome),
                    ("transition", owner._work, owner.outcome),
                )
            },
            sort_keys=True,
        ),
    )
    assert adapter.calls == [REQUEST]
    after = case.snapshot()
    state_only(case.reserved_snapshot, after, identity)
    with pytest.raises(ReservationRefusal, match="invalid_request"):
        invoke(case, adapter, fence, identity, owner=owner)
    with pytest.raises(AdmissionError, match="outcome_uncertain"):
        invoke(case, adapter, fence, identity)
    assert adapter.calls == [REQUEST] and case.snapshot() == after


@pytest.mark.parametrize(
    "change", ["request", "config", "price", "owner", "generation", "cancel", "expiry"]
)
def test_mismatch_or_lost_authority_prevents_call_and_effect(reservation_case, change):
    case = reservation_case
    fence, identity = reserved(case)
    adapter = Adapter(case)
    request = REQUEST
    if change == "request":
        request += b" "
    elif change == "config":
        value = configuration_value()
        value["model_revision"] = "other"
        adapter.configuration = configuration(value)
    elif change == "price":
        identity = replace(identity, price_version="other")
    elif change == "owner":
        fence = replace(fence, owner_uuid="f" * 32)
    elif change == "generation":
        fence = replace(fence, generation=2)
        identity = replace(identity, lease_generation=2)
    else:
        with owned_begin(case.engine) as connection:
            connection.execute(
                text(
                    "UPDATE jobs SET "
                    + ("cancel=1" if change == "cancel" else "lease_until=0")
                    + " WHERE id=:job"
                ),
                {"job": case.job_id},
            )
    before = case.snapshot()
    with pytest.raises(AdmissionError):
        invoke(case, adapter, fence, identity, request=request)
    assert adapter.calls == [] and case.snapshot() == before
    assert case.engine.pool.checkedout() == 0


@pytest.mark.parametrize("persisted", [False, True], ids=["before_commit", "after_commit"])
def test_commit_ack_loss_never_calls_adapter(reservation_case, monkeypatch, persisted):
    case = reservation_case
    fence, identity = reserved(case)
    adapter = Adapter(case)
    owner = DispatchCoordinator(case.engine, case.authority, adapter)
    original = Connection.commit
    commits = []

    def lose_ack(connection):
        if connection.engine is case.engine:
            commits.append(True)
        if connection.engine is case.engine and len(commits) == 2:
            if persisted:
                original(connection)
            raise RuntimeError("private-commit-canary")
        return original(connection)

    with monkeypatch.context() as patch:
        patch.setattr(Connection, "commit", lose_ack)
        with pytest.raises(AdmissionError, match="outcome_uncertain"):
            invoke(case, adapter, fence, identity, owner=owner)
    assert owner.outcome.commit_attempted and not owner.outcome.commit_acknowledged
    assert adapter.calls == []
    after = case.snapshot()
    if persisted:
        state_only(case.reserved_snapshot, after, identity)
        with pytest.raises(AdmissionError, match="outcome_uncertain"):
            invoke(case, adapter, fence, identity)
    else:
        assert after == case.reserved_snapshot
    assert case.engine.pool.checkedout() == 0


def test_cleanup_failure_keeps_hold_without_call(reservation_case, monkeypatch):
    case = reservation_case
    fence, identity = reserved(case)
    adapter = Adapter(case)
    owner = DispatchCoordinator(case.engine, case.authority, adapter)
    original = Connection.close
    failures = []

    def fail_close(connection):
        if connection.engine is case.engine and hasattr(case, "reserved_snapshot") and not failures:
            failures.append(True)
            raise RuntimeError("private-cleanup-canary")
        return original(connection)

    with monkeypatch.context() as patch:
        patch.setattr(Connection, "close", fail_close)
        with pytest.raises(AdmissionError, match="outcome_uncertain"):
            invoke(case, adapter, fence, identity, owner=owner)
    assert owner.outcome.commit_acknowledged and owner.outcome.cleanup_failed
    assert not adapter.calls
    state_only(case.reserved_snapshot, case.snapshot(), identity)
    assert case.engine.pool.checkedout() == 0


def test_provider_failure_keeps_dispatching_and_never_retries(reservation_case):
    case = reservation_case
    fence, identity = reserved(case)
    adapter = Adapter(case, failure=True)
    with pytest.raises(AdmissionError, match="^outcome_uncertain$") as caught:
        invoke(case, adapter, fence, identity)
    assert caught.value.__cause__ is None
    state_only(case.reserved_snapshot, case.snapshot(), identity)
    with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
        invoke(case, adapter, fence, identity)
    assert adapter.calls == [REQUEST]


def test_competing_transitions_only_one_invokes_provider(reservation_case):
    case = reservation_case
    fence, identity = reserved(case)
    barrier = Barrier(2)

    class Contender(Adapter):
        def validate_request(self, request, amount):
            assert request == REQUEST and amount == 12345

        def send(self, request):
            self.calls.append(request)
            return b"response"

    adapters = [Contender(case), Contender(case)]

    def run(adapter):
        barrier.wait(timeout=10)
        try:
            return invoke(case, adapter, fence, identity)
        except AdmissionError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, adapters))
    assert sorted(results, key=str) == sorted([b"response", "outcome_uncertain"], key=str)
    assert sum(len(adapter.calls) for adapter in adapters) == 1
    state_only(case.reserved_snapshot, case.snapshot(), identity)
    assert case.engine.pool.checkedout() == 0


def test_existing_reserved_row_is_not_fresh_dispatch_authority(reservation_case):
    case = reservation_case
    fence, identity = reserved(case)
    ReservationCoordinator(case.engine, case.authority).reserve(
        case.principal, case.context, fence, identity
    )
    before = case.snapshot()
    adapter = Adapter(case)
    with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
        invoke(case, adapter, fence, identity)
    assert adapter.calls == [] and case.snapshot() == before


@pytest.mark.parametrize("persisted", [False, True])
def test_reservation_ack_loss_never_reaches_dispatch(reservation_case, monkeypatch, persisted):
    case = reservation_case
    fence, identity = reserved(case)
    before = case.snapshot()
    adapter = Adapter(case)
    owner = DispatchCoordinator(case.engine, case.authority, adapter)
    original = Connection.commit

    def lose_ack(connection):
        if connection.engine is case.engine:
            if persisted:
                original(connection)
            raise RuntimeError("private-reservation-canary")
        return original(connection)

    with monkeypatch.context() as patch:
        patch.setattr(Connection, "commit", lose_ack)
        with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
            invoke(case, adapter, fence, identity, owner=owner)
    assert owner.reservation_outcome.commit_attempted
    assert not owner.reservation_outcome.commit_acknowledged
    assert not owner.outcome.begun and adapter.calls == []
    if persisted:
        assert rows(case.snapshot(), "provider_calls")[0]["state"] == "reserved"
        with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
            invoke(case, adapter, fence, identity)
    else:
        assert case.snapshot() == before


@pytest.mark.parametrize("where", ["property", "validation"])
def test_adapter_preflight_exceptions_are_safe_and_effect_free(reservation_case, where):
    case = reservation_case
    fence, identity = reserved(case)
    before = case.snapshot()

    class Broken(Adapter):
        @property
        def configuration(self):
            if where == "property":
                raise RuntimeError("private-adapter-canary")
            return configuration()

        def validate_request(self, *args):
            raise RuntimeError("private-adapter-canary")

    adapter = Broken(case)
    with pytest.raises(AdmissionError, match="^dependency_unavailable$") as caught:
        invoke(case, adapter, fence, identity)
    assert caught.value.__cause__ is None
    assert not adapter.calls and case.snapshot() == before
