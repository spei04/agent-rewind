"""Private ar8 claim evidence; fixture admission setup is explicitly synthetic.

The existing builder temporarily patches admission readiness, then genuinely
publishes/provisions ar7. The actual failure service upgrades it before F3 calls.
No default-ready profile, worker, provider or registration shim is installed.
"""

import json
import sqlite3
import sys
from copy import deepcopy
from dataclasses import replace
from time import perf_counter

import pytest
from ledger_eligibility_fixture import rows
from reservation_fixture import build_reservation_case
from sqlalchemy.engine import Connection
from test_admission_configuration import configuration

from agent_rewind import failure_persistence as persistence
from agent_rewind.admission_transaction import AdmissionError
from agent_rewind.failure_evidence import FailureRefusal, _AcknowledgedClaim
from agent_rewind.migrations.failure_service import initialize_failure_evidence
from agent_rewind.operation_work import OperationWork
from agent_rewind.reservation_service import ReservationCoordinator
from agent_rewind.reservation_types import ClaimIntent, JobFence, ReservationRefusal


class InstalledAdapter:
    def __init__(self, changed=None, *, drift_at=3):
        self.original = configuration()
        self.changed = changed
        self.drift_at = drift_at
        self.reads = 0

    @property
    def configuration(self):
        self.reads += 1
        return (
            self.changed
            if self.reads >= self.drift_at and self.changed is not None
            else self.original
        )

    def validate_request(self, *_args):
        raise AssertionError("claim must not validate a provider request")

    def send(self, *_args):
        raise AssertionError("claim must not call a provider")


def different_configuration():
    value = json.loads(configuration().canonical_bytes)
    value["model_revision"] = "different-installed-revision"
    return configuration(value)


@pytest.fixture
def failure_case(tmp_path, monkeypatch, request):
    case = build_reservation_case(tmp_path, monkeypatch, legacy=getattr(request, "param", False))
    try:
        engine = case.case.operator_engine()
        try:
            result = initialize_failure_evidence(
                engine, installation_key=case.case.adoption["installation_key"]
            )
            assert result.status == "complete" and result.revision == "ar_0008_failure_evidence"
        finally:
            engine.dispose()
        yield case
    finally:
        case.close()


def intent(case):
    return ClaimIntent(case.job_id, "a" * 32, 0, 60)


def assert_claim_delta(case, before, after):
    assert before["schema"] == after["schema"]
    assert set(before["tables"]) == set(after["tables"])
    expected = deepcopy(before)
    old_jobs = expected["tables"]["jobs"]
    columns = old_jobs["columns"]
    before_job = next(row for row in rows(before, "jobs") if row["id"] == case.job_id)
    after_job = next(row for row in rows(after, "jobs") if row["id"] == case.job_id)
    assert {key for key in before_job if before_job[key] != after_job[key]} == {
        "status",
        "owner",
        "lease_until",
        "lease_generation",
    }
    assert (after_job["status"], after_job["owner"], after_job["lease_generation"]) == (
        "running",
        "a" * 32,
        1,
    )
    assert type(after_job["lease_until"]) is float
    old_jobs["rows"] = tuple(
        sorted(
            (
                tuple(after_job[name] for name in columns)
                if row[columns.index("id")] == case.job_id
                else row
                for row in old_jobs["rows"]
            ),
            key=repr,
        )
    )
    assert after == expected
    assert rows(after, "job_failure_evidence") == []


@pytest.mark.parametrize("failure_case", [False, True], indirect=True, ids=["fresh", "legacy"])
def test_genuine_private_claim_has_exact_delta_and_whole_path_work(
    failure_case, monkeypatch, record_property
):
    case = failure_case
    before = case.snapshot()
    adapter = InstalledAdapter()
    owner = persistence._FailureExecutionOwner(case.engine, case.authority, adapter)
    state = persistence._OWNERS[owner]
    charges, sql, controls = [], [], []
    original_charge = OperationWork._charge
    original_control = OperationWork.control_attempt
    original_execute = Connection.execute
    original_driver = Connection.exec_driver_sql

    def charge(work):
        caller = sys._getframe(1).f_code.co_name
        try:
            return original_charge(work)
        finally:
            if work is state.coordinator._work:
                charges.append((caller, work.statements))

    def control(work, kind):
        try:
            return original_control(work, kind)
        finally:
            if work is state.coordinator._work:
                controls.append((kind, work.statements))

    def execute(connection, statement, *args, **kwargs):
        if connection.engine is case.engine:
            sql.append(str(statement))
        return original_execute(connection, statement, *args, **kwargs)

    def driver(connection, statement, *args, **kwargs):
        if connection.engine is case.engine:
            sql.append(statement)
        return original_driver(connection, statement, *args, **kwargs)

    monkeypatch.setattr(OperationWork, "_charge", charge)
    monkeypatch.setattr(OperationWork, "control_attempt", control)
    monkeypatch.setattr(Connection, "execute", execute)
    monkeypatch.setattr(Connection, "exec_driver_sql", driver)
    started = perf_counter()
    elapsed = None
    try:
        try:
            fence = owner.claim(case.principal, case.context, intent(case))
        finally:
            elapsed = perf_counter() - started
        assert fence == JobFence(case.job_id, "a" * 32, 1)
        assert owner.outcome.commit_acknowledged and not owner.outcome.cleanup_failed
        assert state.source is not None and state.source.fence == fence
        assert state.source.configuration_digest == configuration().digest
        assert state.source.configuration_size == len(configuration().canonical_bytes)
        assert state.source.operation.row()["failure_correlation_id"] is not None
        assert adapter.reads == 3
        assert state.coordinator not in persistence._CLAIMS
        assert_claim_delta(case, before, case.snapshot())
        preserved = owner.outcome
        with pytest.raises(FailureRefusal, match="^invalid_request$") as caught:
            owner.claim(case.principal, case.context, intent(case))
        assert caught.value.reason == "invocation_reused" and owner.outcome == preserved
        assert case.engine.pool.checkedout() == 0
        assert state.coordinator._work.statements <= 512 and elapsed < 10
    finally:
        work = state.coordinator._work
        record_property("whole_claim_seconds", elapsed)
        record_property("transaction_outcome", str(owner.outcome))
        if work is not None:
            record_property("work_statements", work.statements)
            record_property("work_attached_seconds", work.seconds)
            record_property("work_vm_instructions", work.instructions)
        record_property("charge_trace", json.dumps(charges))
        record_property("control_trace", json.dumps(controls))
        record_property("sqlalchemy_statements", json.dumps(sql))
        facts = owner.outcome
        owner.close()
        assert owner not in persistence._OWNERS and state.coordinator not in persistence._CLAIMS
        assert owner.outcome == facts


def test_initial_whole_configuration_mismatch_cannot_claim(failure_case):
    case = failure_case
    adapter = InstalledAdapter()
    adapter.original = different_configuration()
    owner = persistence._FailureExecutionOwner(case.engine, case.authority, adapter)
    state = persistence._OWNERS[owner]
    before = case.snapshot()
    try:
        with pytest.raises(FailureRefusal) as caught:
            owner.claim(case.principal, case.context, intent(case))
        assert caught.value.reason == "origin_unproved"
        assert owner.outcome.confirmed_precommit_rollback
        assert not owner.outcome.commit_attempted and state.source is None
        assert state.coordinator not in persistence._CLAIMS
        assert case.snapshot() == before
    finally:
        owner.close()


def test_pre_mutation_binding_drift_refuses_without_protected_update(failure_case, monkeypatch):
    case = failure_case
    adapter = InstalledAdapter(different_configuration(), drift_at=2)
    owner = persistence._FailureExecutionOwner(case.engine, case.authority, adapter)
    state = persistence._OWNERS[owner]
    before = case.snapshot()
    writes = []
    original = Connection.execute

    def observe(connection, statement, *args, **kwargs):
        if connection.engine is case.engine and str(statement).startswith("UPDATE jobs"):
            writes.append(str(statement))
        return original(connection, statement, *args, **kwargs)

    monkeypatch.setattr(Connection, "execute", observe)
    try:
        with pytest.raises(FailureRefusal) as caught:
            owner.claim(case.principal, case.context, intent(case))
        assert caught.value.reason == "stale_source"
        assert adapter.reads == 2 and writes == []
        assert owner.outcome.confirmed_precommit_rollback
        assert not owner.outcome.commit_attempted and state.source is None
        assert state.coordinator not in persistence._CLAIMS
        assert case.snapshot() == before
    finally:
        owner.close()


def test_post_clean_binding_drift_retains_commit_but_issues_nothing(failure_case):
    case = failure_case
    adapter = InstalledAdapter(different_configuration())
    owner = persistence._FailureExecutionOwner(case.engine, case.authority, adapter)
    state = persistence._OWNERS[owner]
    before = case.snapshot()
    try:
        with pytest.raises(FailureRefusal) as caught:
            owner.claim(case.principal, case.context, intent(case))
        assert caught.value.reason == "stale_source"
        assert owner.outcome.commit_acknowledged and not owner.outcome.cleanup_failed
        assert adapter.reads == 3 and state.source is None
        assert state.coordinator not in persistence._CLAIMS
        assert_claim_delta(case, before, case.snapshot())
    finally:
        owner.close()


def test_unregistered_token_does_not_replace_the_genuine_acknowledged_claim(
    failure_case, monkeypatch
):
    case = failure_case
    original = ReservationCoordinator._claim_for_failure_execution

    def substitute(coordinator, *args, **kwargs):
        original(coordinator, *args, **kwargs)
        return object.__new__(_AcknowledgedClaim)

    monkeypatch.setattr(ReservationCoordinator, "_claim_for_failure_execution", substitute)
    owner = persistence._FailureExecutionOwner(case.engine, case.authority, InstalledAdapter())
    state = persistence._OWNERS[owner]
    before = case.snapshot()
    try:
        with pytest.raises(FailureRefusal) as caught:
            owner.claim(case.principal, case.context, intent(case))
        assert caught.value.reason == "capability_not_issued"
        assert owner.outcome.commit_acknowledged and state.source is None
        assert state.coordinator not in persistence._CLAIMS
        assert_claim_delta(case, before, case.snapshot())
    finally:
        owner.close()


@pytest.mark.parametrize("fault", ["commit_after", "close_after"])
def test_ack_or_cleanup_failure_never_registers_a_committed_claim(
    failure_case, monkeypatch, fault, record_property
):
    case = failure_case
    name = "commit" if fault == "commit_after" else "close"
    original = getattr(Connection, name)
    injected = []

    def fail(connection, *args, **kwargs):
        result = original(connection, *args, **kwargs)
        if connection.engine is case.engine and not injected:
            injected.append(True)
            raise OSError("private native fault canary")
        return result

    monkeypatch.setattr(Connection, name, fail)
    owner = persistence._FailureExecutionOwner(case.engine, case.authority, InstalledAdapter())
    state = persistence._OWNERS[owner]
    before = case.snapshot()
    try:
        with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
            owner.claim(case.principal, case.context, intent(case))
        assert injected == [True]
        assert owner.outcome.commit_attempted
        assert owner.outcome.commit_acknowledged == (fault == "close_after")
        assert state.source is None and state.coordinator not in persistence._CLAIMS
        assert_claim_delta(case, before, case.snapshot())
        assert case.engine.pool.checkedout() == 0
        record_property("transaction_outcome", str(owner.outcome))
    finally:
        owner.close()


def test_public_ar7_claim_guard_still_refuses_ar8_without_mutation(failure_case):
    case = failure_case
    before = case.snapshot()
    owner = ReservationCoordinator(case.engine, case.authority)
    with pytest.raises(ReservationRefusal) as caught:
        owner.claim_generation(case.principal, case.context, intent(case))
    assert caught.value.reason == "schema_or_provenance_invalid"
    assert case.snapshot() == before


def test_selected_schema_valid_historical_marker_prevents_claim(failure_case):
    case = failure_case
    # This is a native schema-valid marker fixture, not F5 operator evidence.
    with sqlite3.connect(case.case.path) as raw:
        raw.execute("PRAGMA foreign_keys=ON")
        operation = raw.execute(
            "SELECT id FROM operations WHERE job_id=?", (case.job_id,)
        ).fetchone()[0]
        raw.execute("UPDATE operations SET failure_correlation_id=NULL WHERE id=?", (operation,))
        raw.execute(
            "INSERT INTO job_failure_evidence VALUES "
            "(1,'historical_marker',?,'job',?,?,0,'queued',NULL,NULL,"
            "'migration_marker',?,?,?,0)",
            (case.project_id, case.job_id, operation, "b" * 32, "c" * 64, "d" * 64),
        )
    before = case.snapshot()
    owner = persistence._FailureExecutionOwner(case.engine, case.authority, InstalledAdapter())
    state = persistence._OWNERS[owner]
    try:
        with pytest.raises(FailureRefusal) as caught:
            owner.claim(case.principal, case.context, intent(case))
        assert caught.value.reason == "not_eligible"
        assert owner.outcome.confirmed_precommit_rollback and state.source is None
        assert case.snapshot() == before
    finally:
        owner.close()


def test_claim_source_is_revalidated_data_not_authority(failure_case):
    case = failure_case
    owner = persistence._FailureExecutionOwner(case.engine, case.authority, InstalledAdapter())
    try:
        owner.claim(case.principal, case.context, intent(case))
        source = persistence._OWNERS[owner].source
        assert source is not None
        with pytest.raises(FailureRefusal, match="^invalid_request$"):
            replace(source, configuration_digest="f" * 64)
        with pytest.raises(FailureRefusal, match="^invalid_request$"):
            replace(source, configuration_size=True)

        class PrivateCanary:
            @property
            def fields(self):
                raise AssertionError("wrong-object property must not be accessed")

        with pytest.raises(FailureRefusal, match="^invalid_request$"):
            replace(source, operation=PrivateCanary())
        copied = replace(source)
        assert copied == source and copied is not source
        assert not isinstance(copied, _AcknowledgedClaim)
    finally:
        owner.close()
