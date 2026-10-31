"""Real PG16 dispatch boundary, with synthetic admission and an offline adapter.

The existing fixture observes actual migration_only, then temporarily replaces
admission schema_compatibility during setup. This is component proof, not
unpatched worker startup. Only UPDATE(state) on provider_calls is added here.
"""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from threading import Barrier

import pytest
import test_migrations_postgres as migrations
from ledger_restore_authority import typed
from reservation_postgres_fixture import _application_acl, build_postgres_reservation_case
from reservation_qe_fixture import claim, expected_reservation, intent, one, same
from sqlalchemy import text
from sqlalchemy.engine import Connection
from test_admission_configuration import configuration, configuration_value

from agent_rewind.admission_transaction import AdmissionError
from agent_rewind.dispatch import DispatchCoordinator
from agent_rewind.reservation_service import ReservationCoordinator
from agent_rewind.reservation_types import CreatedReservation, ReservationRefusal

pg = migrations.pg
__all__ = ["pg"]
pytestmark = pytest.mark.skipif(
    not migrations.POSTGRES, reason="Opt-in synthetic PostgreSQL dispatch components"
)
REQUEST = b'{"messages":[],"model":"model-revision-1"}'


def observe(case):
    native = case.snapshot()
    return {
        **native,
        "tables": {
            name: {
                "columns": table["columns"],
                "rows": [dict(zip(table["columns"], row, strict=True)) for row in table["rows"]],
            }
            for name, table in native["tables"].items()
        },
    }


def assert_dispatch_delta(case, before, identity, state):
    after = observe(case)
    expected = expected_reservation(before, after, identity, case.organization_id)
    one(expected, "provider_calls", id=identity.call_id)["state"] = state
    same(expected, after)
    assert case.engine.pool.checkedout() == 0
    return after


@pytest.fixture
def reservation_case(pg, tmp_path, monkeypatch):
    case = build_postgres_reservation_case(pg, tmp_path, monkeypatch)
    try:
        yield case
    finally:
        case.close()


@pytest.fixture
def dispatch_case(reservation_case, record_property):
    case = reservation_case
    before = observe(case)
    with case.pg["owner"].begin() as connection:
        old_acl = _application_acl(connection, case.pg["app_role"])
        delta = {("column", "provider_calls", "state", "UPDATE", False, case.pg["owner_role"])}
        assert old_acl.isdisjoint(delta)
        role = connection.dialect.identifier_preparer.quote(case.pg["app_role"])
        connection.exec_driver_sql(f"GRANT UPDATE(state) ON provider_calls TO {role}")
        new_acl = _application_acl(connection, case.pg["app_role"])
    assert new_acl == old_acl | delta
    same(before, observe(case))
    record_property("only_added_acl", json.dumps(typed(sorted(new_acl - old_acl))))
    return case


def prepared(case):
    fence = claim(case)
    identity = replace(
        intent(case, fence, amount=12345), request_digest=hashlib.sha256(REQUEST).hexdigest()
    )
    return fence, identity


class Adapter:
    configuration = configuration()

    def __init__(self, case, *, before=None, identity=None, failure=False):
        self.case = case
        self.before = before
        self.identity = identity
        self.failure = failure
        self.calls = []
        self.owner = None

    def validate_request(self, request, amount):
        assert request == REQUEST and amount == 12345

    def send(self, request):
        assert request == REQUEST
        if self.owner is not None:
            assert self.owner.outcome.commit_acknowledged
            assert not self.owner.outcome.cleanup_failed
            assert self.case.engine.pool.checkedout() == 0
        if self.before is not None:
            assert_dispatch_delta(self.case, self.before, self.identity, "dispatching")
        self.calls.append(request)
        if self.failure:
            raise RuntimeError("private-offline-adapter-canary")
        return b"offline-response"


def invoke(case, adapter, fence, identity, *, owner=None):
    owner = owner or DispatchCoordinator(case.engine, case.authority, adapter)
    return owner.dispatch(case.principal, case.context, fence, identity, REQUEST)


def test_postgres_dispatch_commits_before_send_and_refuses_reuse(dispatch_case, record_property):
    case = dispatch_case
    fence, identity = prepared(case)
    before = observe(case)
    adapter = Adapter(case, before=before, identity=identity)
    owner = DispatchCoordinator(case.engine, case.authority, adapter)
    adapter.owner = owner
    assert invoke(case, adapter, fence, identity, owner=owner) == b"offline-response"
    assert owner.reservation_outcome.commit_acknowledged
    assert not owner.reservation_outcome.cleanup_failed
    assert adapter.calls == [REQUEST]
    after = assert_dispatch_delta(case, before, identity, "dispatching")
    with pytest.raises(ReservationRefusal) as caught:
        invoke(case, adapter, fence, identity, owner=owner)
    assert caught.value.reason == "invocation_reused"
    with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
        invoke(case, adapter, fence, identity)
    assert adapter.calls == [REQUEST]
    same(after, observe(case))
    record_property("transition_outcome", json.dumps(asdict(owner.outcome)))
    record_property("transition_work_units", owner._work.statements)
    record_property("offline_send_count", len(adapter.calls))


def test_postgres_missing_state_grant_preserves_reserved_hold(reservation_case):
    case = reservation_case
    fence, identity = prepared(case)
    before = observe(case)
    with case.pg["owner"].connect() as connection:
        acl = _application_acl(connection, case.pg["app_role"])
    assert not any(row[:4] == ("column", "provider_calls", "state", "UPDATE") for row in acl)
    adapter = Adapter(case)
    owner = DispatchCoordinator(case.engine, case.authority, adapter)
    with pytest.raises(AdmissionError, match="^dependency_unavailable$"):
        invoke(case, adapter, fence, identity, owner=owner)
    assert owner.reservation_outcome.commit_acknowledged
    assert owner.outcome.confirmed_precommit_rollback
    assert not owner.outcome.cleanup_failed and not adapter.calls
    assert_dispatch_delta(case, before, identity, "reserved")
    with case.pg["owner"].connect() as connection:
        assert _application_acl(connection, case.pg["app_role"]) == acl


@pytest.mark.parametrize("change", ["cancel", "owner", "generation", "expiry", "config"])
def test_postgres_cancel_stale_or_configuration_refuses_without_effect(dispatch_case, change):
    case = dispatch_case
    fence, identity = prepared(case)
    adapter = Adapter(case)
    if change == "owner":
        fence = replace(fence, owner_uuid="f" * 32)
    elif change == "generation":
        fence = replace(fence, generation=fence.generation + 1)
        identity = replace(identity, lease_generation=fence.generation)
    elif change == "config":
        value = configuration_value()
        value["model_revision"] = "other-model"
        adapter.configuration = configuration(value)
    else:
        with case.pg["owner"].begin() as connection:
            connection.execute(
                text(
                    "UPDATE jobs SET "
                    + ("cancel=true" if change == "cancel" else "lease_until=0")
                    + " WHERE id=:job"
                ),
                {"job": case.job_id},
            )
    before = observe(case)
    with pytest.raises(ReservationRefusal) as caught:
        invoke(case, adapter, fence, identity)
    assert caught.value.reason == ("unsupported_job" if change == "config" else "job_not_live")
    assert not adapter.calls
    same(before, observe(case))
    assert case.engine.pool.checkedout() == 0


def test_postgres_competing_dispatchers_make_one_offline_call(dispatch_case):
    case = dispatch_case
    fence, identity = prepared(case)
    before = observe(case)
    barrier = Barrier(2)
    adapters = [Adapter(case), Adapter(case)]
    owners = [DispatchCoordinator(case.engine, case.authority, adapter) for adapter in adapters]

    def run(pair):
        adapter, owner = pair
        barrier.wait(timeout=10)
        try:
            return invoke(case, adapter, fence, identity, owner=owner)
        except AdmissionError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, zip(adapters, owners, strict=True)))
    assert results.count(b"offline-response") == 1
    assert results.count("outcome_uncertain") == 1
    assert sum(len(adapter.calls) for adapter in adapters) == 1
    assert_dispatch_delta(case, before, identity, "dispatching")
    winner = owners[results.index(b"offline-response")]
    assert winner.outcome.commit_acknowledged and not winner.outcome.cleanup_failed


@pytest.mark.parametrize("stage", ["reserve", "transition"])
@pytest.mark.parametrize("persisted", [False, True], ids=["before_commit", "after_commit"])
def test_postgres_commit_ack_loss_never_sends(dispatch_case, monkeypatch, stage, persisted):
    case = dispatch_case
    fence, identity = prepared(case)
    before = observe(case)
    adapter = Adapter(case)
    owner = DispatchCoordinator(case.engine, case.authority, adapter)
    original = Connection.commit
    commits = []
    selected = 1 if stage == "reserve" else 2

    def lose_ack(connection):
        if connection.engine is case.engine:
            commits.append(True)
            if len(commits) == selected:
                if persisted:
                    original(connection)
                raise RuntimeError("private-native-commit-canary")
        return original(connection)

    with monkeypatch.context() as patch:
        patch.setattr(Connection, "commit", lose_ack)
        with pytest.raises(AdmissionError, match="^outcome_uncertain$") as caught:
            invoke(case, adapter, fence, identity, owner=owner)
    assert caught.value.__cause__ is None and len(commits) == selected
    outcome = owner.reservation_outcome if stage == "reserve" else owner.outcome
    assert outcome.commit_attempted and not outcome.commit_acknowledged
    assert not adapter.calls
    if stage == "reserve":
        assert not owner.outcome.begun
    if stage == "reserve" and not persisted:
        same(before, observe(case))
    else:
        state = "dispatching" if stage == "transition" and persisted else "reserved"
        after = assert_dispatch_delta(case, before, identity, state)
        with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
            invoke(case, adapter, fence, identity)
        same(after, observe(case))
    assert not adapter.calls and case.engine.pool.checkedout() == 0


def test_postgres_cleanup_failure_retains_dispatching_without_send(dispatch_case, monkeypatch):
    case = dispatch_case
    fence, identity = prepared(case)
    before = observe(case)
    adapter = Adapter(case)
    owner = DispatchCoordinator(case.engine, case.authority, adapter)
    original = Connection.close
    failures = []

    def fail_close(connection):
        if (
            connection.engine is case.engine
            and owner._transaction.commit_acknowledged
            and not failures
        ):
            failures.append(True)
            raise RuntimeError("private-native-close-canary")
        return original(connection)

    with monkeypatch.context() as patch:
        patch.setattr(Connection, "close", fail_close)
        with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
            invoke(case, adapter, fence, identity, owner=owner)
    assert len(failures) == 1 and owner.outcome.commit_acknowledged
    assert owner.outcome.cleanup_failed and not adapter.calls
    after = assert_dispatch_delta(case, before, identity, "dispatching")
    with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
        invoke(case, adapter, fence, identity)
    same(after, observe(case))
    assert not adapter.calls


def test_postgres_adapter_failure_is_not_retry_or_release_evidence(dispatch_case):
    case = dispatch_case
    fence, identity = prepared(case)
    before = observe(case)
    adapter = Adapter(case, before=before, identity=identity, failure=True)
    owner = DispatchCoordinator(case.engine, case.authority, adapter)
    adapter.owner = owner
    with pytest.raises(AdmissionError, match="^outcome_uncertain$") as caught:
        invoke(case, adapter, fence, identity, owner=owner)
    assert caught.value.__cause__ is None
    after = assert_dispatch_delta(case, before, identity, "dispatching")
    with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
        invoke(case, adapter, fence, identity)
    assert adapter.calls == [REQUEST]
    same(after, observe(case))


def test_postgres_prior_reservation_is_not_new_dispatch_authority(dispatch_case):
    case = dispatch_case
    fence, identity = prepared(case)
    before = observe(case)
    result = ReservationCoordinator(case.engine, case.authority).reserve(
        case.principal, case.context, fence, identity, configuration=configuration()
    )
    assert isinstance(result, CreatedReservation)
    reserved = assert_dispatch_delta(case, before, identity, "reserved")
    adapter = Adapter(case)
    with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
        invoke(case, adapter, fence, identity)
    assert not adapter.calls
    same(reserved, observe(case))
