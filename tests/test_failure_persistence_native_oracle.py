"""Independent F3 claim fixtures; synthetic admission is not live startup proof.

The real private owner supplies claim authority; returned fences are historical.
No terminal event, provider call, live startup or maximum-cohort claim is exercised.
"""

import json
import math
import time
import traceback
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from dataclasses import asdict
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest
import test_migrations_postgres as migration_tests
from ledger_eligibility_fixture import file_hashes
from ledger_provisioning_fixture import ciphertexts
from ledger_provisioning_postgres_fixture import encrypted_files
from ledger_restore_authority import typed
from reservation_fixture import build_reservation_case
from reservation_postgres_fixture import (
    _application_acl,
    build_postgres_reservation_case,
    offline_postgres_ledger,
)
from sqlalchemy import text
from sqlalchemy.engine import Connection
from test_admission_configuration import configuration, configuration_value
from test_failure_catalog_native_oracle import full_shape, native_snapshot, project_ar7
from test_failure_service_native_oracle import assert_retained_native, observe_work
from test_run_projection_postgres import drain as drain_postgres

from agent_rewind import failure_persistence, operation_work
from agent_rewind.admission_transaction import AdmissionError
from agent_rewind.migrations.failure_service import initialize_failure_evidence
from agent_rewind.migrations.schema import FAILURE, LEDGER, catalog, checksum
from agent_rewind.operation_work import OperationWork
from agent_rewind.reservation_types import ClaimIntent, JobFence

pg = migration_tests.pg
POSTGRES = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL F3 claim components"
)
EVIDENCE = "job_failure_evidence"
SECRET_CANARY = "F3-synthetic-private-canary-DO-NOT-PUBLISH"


def drain_case(case):
    """Drain only this fixture's idle app pool before independent owner reads."""
    assert case.engine.pool.checkedout() == 0
    case.engine.dispose()
    if hasattr(case, "pg"):
        drain_postgres(case.pg)


def whole_state(case, *, table_count=21):
    """Capture native metadata and every typed cell outside the product Work."""
    assert table_count in (20, 21)
    drain_case(case)
    try:
        with case.case.engine.connect() as connection:
            raw = native_snapshot(connection, table_count)
            names = (
                sorted(raw["tables"])
                if connection.dialect.name == "sqlite"
                else [row[0] for row in raw["table_names"]]
            )
            assert len(names) == table_count
            tables = {}
            remaining = 65536  # Bounded fixture capture; no product capacity claim.
            for name in names:
                quoted = connection.dialect.identifier_preparer.quote_identifier(name)
                with connection.exec_driver_sql(f"SELECT * FROM {quoted}") as result:
                    columns = tuple(result.keys())
                    values = result.mappings().fetchmany(remaining + 1)
                assert len(values) <= remaining
                remaining -= len(values)
                tables[name] = {
                    "columns": columns,
                    "rows": sorted((dict(row) for row in values), key=lambda row: repr(typed(row))),
                }
            shape = catalog(connection) if table_count == 20 else full_shape(connection, raw)
        legacy = (
            encrypted_files(case.provisioning) if hasattr(case, "pg") else ciphertexts(case.case)
        )
        return {
            "native": raw,
            "shape": shape,
            "tables": tables,
            "legacy_ciphertexts": legacy,
            "admission_ciphertexts": file_hashes(case.admission.objects),
            "admission_journal": file_hashes(case.admission.journal),
        }
    finally:
        drain_case(case)


def assert_same_state(expected, actual):
    """Preserve native types rather than treating bool, int and float as equal."""
    assert typed(actual) == typed(expected)


def assert_upgrade_preserved(before, after, result):
    """Only the real F2 revision change and empty new relation alter table rows."""
    assert result.status == result.outcome == "complete"
    assert result.revision == FAILURE and result.catalog_profile == "failure_evidence_v1"
    assert result.retained_ar7.status == "complete" and result.retained_ar7.revision == LEDGER
    assert result.installation_key == result.retained_ar7.installation_key
    profile_name = (
        "postgresql16_failure_evidence.json"
        if "$postgres" in after["shape"]
        else "sqlite_failure_evidence.json"
    )
    profile = json.loads(
        (Path(__file__).parents[1] / "agent_rewind/migrations/profiles" / profile_name).read_text()
    )
    assert typed(after["shape"]) == typed(profile)
    assert result.installed_profile_sha256 == checksum(profile)
    # Project only after the independent complete successor literal has matched.
    assert typed(project_ar7(after["shape"])) == typed(before["shape"])
    assert_retained_native(before["native"], after["native"])

    expected = deepcopy(before["tables"])
    assert expected["alembic_version"]["rows"] == [{"version_num": LEDGER}]
    expected["alembic_version"]["rows"] = [{"version_num": FAILURE}]
    assert set(after["tables"]) == set(expected) | {EVIDENCE}
    assert after["tables"][EVIDENCE]["rows"] == []
    assert typed({name: after["tables"][name] for name in expected}) == typed(expected)
    for name in ("legacy_ciphertexts", "admission_ciphertexts", "admission_journal"):
        assert after[name] == before[name]


def initialize_ar8(case, monkeypatch, record_property):
    """Perform the actual scoped F2 service, without compatibility/readiness patches."""
    offline = offline_postgres_ledger(case) if hasattr(case, "pg") else nullcontext()
    drain_case(case)
    with offline:
        before = whole_state(case, table_count=20)
        with monkeypatch.context() as scoped:
            observed = observe_work(scoped)
            engine = case.case.operator_engine()
            started = time.monotonic()
            try:
                result = initialize_failure_evidence(
                    engine, installation_key=case.case.adoption["installation_key"]
                )
            finally:
                engine.dispose()
                drain_case(case)
            elapsed = time.monotonic() - started
        assert len(observed) == 1
        connection, work = observed[0]
        assert connection.closed and work._detached
        assert (work.prepaid_bootstrap, work.prepaid_cleanup) == (12, 8)
        assert 0 <= work.observed_ordinary <= 2028
        assert len(work.cleanup_observations) <= 8 and elapsed < 120
        after = whole_state(case)
        assert_upgrade_preserved(before, after, result)
        record_property(
            "f3_fixture_ar8_upgrade",
            json.dumps(
                {
                    "elapsed_seconds": elapsed,
                    "ordinary": work.observed_ordinary,
                    "bootstrap": work.prepaid_bootstrap,
                    "cleanup": work.prepaid_cleanup,
                    "cleanup_observations": work.cleanup_observations,
                    "retained_manifest_count": result.retained_ar7.manifest_count,
                    "complete_old_rows_and_ciphertexts_preserved": True,
                    "synthetic_admission_setup_only": True,
                },
                sort_keys=True,
            ),
        )
    return result


def evidence_reader_grant(case, before):
    """Add only SELECT for the new table; this first slice cannot persist evidence."""
    drain_case(case)
    with case.pg["owner"].begin() as connection:
        assert _application_acl(connection, case.pg["app_role"]) == before
        assert not any(row[1] == EVIDENCE for row in before)
        role = connection.dialect.identifier_preparer.quote_identifier(case.pg["app_role"])
        connection.exec_driver_sql(f"GRANT SELECT ON job_failure_evidence TO {role}")
        after = _application_acl(connection, case.pg["app_role"])
        expected = before | {
            ("table", EVIDENCE, "", "SELECT", False, case.pg["owner_role"]),
        }
        assert after == expected
    drain_case(case)


def assert_restricted_reader(case):
    """Observe actual role and effective rights, not just the GRANT statement."""
    try:
        with case.engine.connect() as connection:
            role = connection.execute(
                text(
                    "SELECT current_user,session_user,rolsuper,rolcreaterole,rolcreatedb,"
                    "rolinherit,rolbypassrls,pg_has_role(current_user,:owner,'MEMBER') "
                    "FROM pg_roles WHERE rolname=current_user"
                ),
                {"owner": case.pg["owner_role"]},
            ).one()
            rights = connection.exec_driver_sql(
                "SELECT has_table_privilege(current_user,'job_failure_evidence','SELECT'),"
                "has_table_privilege(current_user,'job_failure_evidence','INSERT'),"
                "has_table_privilege(current_user,'job_failure_evidence','UPDATE'),"
                "has_table_privilege(current_user,'job_failure_evidence','DELETE'),"
                "has_table_privilege(current_user,'job_failure_evidence','TRUNCATE'),"
                "has_table_privilege(current_user,'job_failure_evidence','REFERENCES'),"
                "has_table_privilege(current_user,'job_failure_evidence','TRIGGER'),"
                "has_schema_privilege(current_user,'public','CREATE')"
            ).one()
        assert tuple(role) == (case.pg["app_role"], case.pg["app_role"]) + (False,) * 6
        assert tuple(rights) == (True,) + (False,) * 7
        return {"role": tuple(role), "evidence_rights": tuple(rights)}
    finally:
        drain_case(case)


def restore_reader_grant(case, before):
    drain_case(case)
    with case.pg["owner"].begin() as connection:
        role = connection.dialect.identifier_preparer.quote_identifier(case.pg["app_role"])
        connection.exec_driver_sql(f"REVOKE SELECT ON job_failure_evidence FROM {role}")
        assert _application_acl(connection, case.pg["app_role"]) == before
    drain_case(case)


@contextmanager
def genuine_failure_case(tmp_path, monkeypatch, record_property, *, pg=None, legacy=False):
    """Admit/provision genuinely, upgrade to ar8, then expose a restricted claim fixture.

    The existing predecessor builder confines its synthetic readiness adapter to
    admission. No override survives into F2 setup or the forthcoming F3 call.
    """
    case = (
        build_reservation_case(tmp_path, monkeypatch, legacy=legacy)
        if pg is None
        else build_postgres_reservation_case(pg, tmp_path, monkeypatch, legacy=legacy)
    )
    primary = None
    old_acl = None
    try:
        result = initialize_ar8(case, monkeypatch, record_property)
        if pg is not None:
            drain_case(case)
            with pg["owner"].connect() as connection:
                old_acl = _application_acl(connection, pg["app_role"])
            # Save the original rights before attempting GRANT, including its ACK.
            evidence_reader_grant(case, old_acl)
            role = assert_restricted_reader(case)
            record_property("f3_fixture_restricted_role", json.dumps(role, sort_keys=True))
        before = whole_state(case)
        assert before["admission_ciphertexts"] == case.admission.ciphertexts
        assert before["admission_journal"] == case.admission.journal_hashes
        assert before["legacy_ciphertexts"] == case.admission.original_legacy_ciphertexts
        yield SimpleNamespace(case=case, initialization=result, before=before)
    except BaseException as error:
        primary = error
        raise
    finally:
        cleanup_errors = []
        if old_acl is not None:
            try:
                restore_reader_grant(case, old_acl)
            except BaseException as error:
                cleanup_errors.append(error)
        try:
            case.close()
        except BaseException as error:
            cleanup_errors.append(error)
        if pg is not None:
            try:
                drain_postgres(pg)
            except BaseException as error:
                cleanup_errors.append(error)
        if cleanup_errors:
            if primary is not None:
                primary.add_note("F3 fixture cleanup also failed; retained primary exception.")
            else:
                raise cleanup_errors[0] from None


@pytest.fixture
def legacy():
    return False


@pytest.fixture(params=["sqlite", pytest.param("postgresql", marks=POSTGRES)])
def failure_case(request, tmp_path, monkeypatch, record_property, legacy):
    selected_pg = request.getfixturevalue("pg") if request.param == "postgresql" else None
    with genuine_failure_case(
        tmp_path, monkeypatch, record_property, pg=selected_pg, legacy=legacy
    ) as fixture:
        yield fixture


class InstalledAdapter:
    """Synthetic installed mapping only; any request validation/send is a test failure."""

    def __init__(self, initial=None, *, after=None, drift_at="post_clean"):
        self.initial = configuration() if initial is None else initial
        self.after, self.drift_at = after, drift_at
        self.record = None
        self.reads = 0
        self.phases = []
        self.validate_calls = self.send_calls = 0

    @property
    def configuration(self):
        assert self.record is not None
        transaction = self.record.coordinator._transaction
        work = self.record.coordinator._work
        assert work is not None and work._invocation_started is not None
        if not transaction.begun:
            assert not transaction.commit_attempted
            phase = "initial"
        elif transaction.commit_acknowledged:
            assert not transaction.cleanup_failed
            assert work._detached and not work._listeners and work._lease is None
            assert work._connection is None
            phase = "post_clean"
        else:
            assert not transaction.commit_attempted and not work._detached
            phase = "pre_mutation"
        self.phases.append(phase)
        self.reads += 1
        value = self.after if phase == self.drift_at and self.after is not None else self.initial
        if isinstance(value, BaseException):
            raise value
        return value

    def validate_request(self, _request, _reserved_microusd):
        self.validate_calls += 1
        raise AssertionError(SECRET_CANARY)

    def send(self, _request):
        self.send_calls += 1
        raise AssertionError(SECRET_CANARY)


class DeadlineAdapter(InstalledAdapter):
    """Advance one test clock; never alter Work fields or the native DB clock."""

    def __init__(self, phase, clock):
        super().__init__()
        self.expire_at, self.clock = phase, clock
        self.original_start = None

    @property
    def configuration(self):
        value = super().configuration
        work = self.record.coordinator._work
        if self.original_start is None:
            self.original_start = work._invocation_started
        assert work._invocation_started == self.original_start == 1000.0
        if self.phases[-1] == self.expire_at:
            assert self.clock[0] == self.original_start
            self.clock[0] = self.original_start + 10.0
        return value


def observe_claim_updates(monkeypatch, case):
    """Forward actual protected UPDATEs unchanged, recording attempts and row counts."""
    original = Connection.execute
    observed = []

    def execute(connection, statement, *args, **kwargs):
        selected = connection.engine is case.engine and str(statement).startswith(
            "UPDATE jobs SET status='running', owner=:owner, lease_until=:lease,"
        )
        entry = {"rowcount": None}
        if selected:
            observed.append(entry)
        result = original(connection, statement, *args, **kwargs)
        if selected:
            entry["rowcount"] = result.rowcount
        return result

    monkeypatch.setattr(Connection, "execute", execute)
    return observed


def changed_configuration():
    value = configuration_value()
    value["endpoint_revision"] = "different-installed-revision"
    return configuration(value)


def claim_intent(case):
    return ClaimIntent(case.job_id, "a" * 32, 0, 60)


@contextmanager
def execution_owner(case, adapter):
    owner = failure_persistence._FailureExecutionOwner(case.engine, case.authority, adapter)
    record = failure_persistence._OWNERS[owner]
    assert record.source is None and adapter.reads == 0
    adapter.record = record
    primary = None
    try:
        yield owner, record
    except BaseException as error:
        primary = error
        raise
    finally:
        facts = owner.outcome
        try:
            owner.close()
            assert owner not in failure_persistence._OWNERS
            assert record.coordinator not in failure_persistence._CLAIMS
            assert owner.outcome == facts
            assert case.engine.pool.checkedout() == 0
        except BaseException:
            if primary is not None:
                primary.add_note("F3 owner cleanup also failed; retained primary exception.")
            else:
                raise


def observe_controls(monkeypatch):
    """Forward existing controls exactly; add no SQL, waits or progress handler."""
    original = OperationWork.control_attempt
    controls = []

    def observe(work, kind):
        before = work.statements
        try:
            return original(work, kind)
        finally:
            controls.append((work, kind, before, work.statements))

    monkeypatch.setattr(OperationWork, "control_attempt", observe)
    return controls


def bounded_claim(owner, record, case, controls, record_property):
    started = time.monotonic()
    fence = owner.claim(case.principal, case.context, claim_intent(case))
    elapsed = time.monotonic() - started
    work = record.coordinator._work
    assert work is record.work and work._invocation_started is not None
    assert work._detached and not work._listeners and work._lease is None
    observed = [item for item in controls if item[0] is work]
    cleanup = [item for item in observed if item[1] not in {"begin", "commit"}]
    assert observed and any(item[1] == "commit" for item in observed)
    assert 0 < len(cleanup) <= 8
    assert work.statements - len(cleanup) <= 504 and work.statements <= 512
    assert elapsed < 10 and work.instructions < 20_000_000
    assert owner.outcome.commit_acknowledged and not owner.outcome.cleanup_failed
    record_property(
        "f3_complete_claim_work",
        json.dumps(
            {
                "elapsed_seconds": elapsed,
                "owned_seconds": work.seconds,
                "ordinary_units": work.statements - len(cleanup),
                "cleanup_units": len(cleanup),
                "total_units": work.statements,
                "vm_instructions": work.instructions,
                "acquisition_clock": True,
                "outcome": asdict(owner.outcome),
            },
            sort_keys=True,
        ),
    )
    return fence


def utc_micros(value):
    """Decode the independent native clock/account witness with integer arithmetic."""
    observed = (
        datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    )
    assert isinstance(observed, datetime) and observed.utcoffset() is not None
    delta = observed.astimezone(UTC) - datetime(1970, 1, 1, tzinfo=UTC)
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def native_clock(case):
    """Observe outside the product transaction; never substitute its time source."""
    drain_case(case)
    try:
        with case.case.engine.connect() as connection:
            sql = (
                "SELECT clock_timestamp()"
                if connection.dialect.name == "postgresql"
                else "SELECT strftime('%Y-%m-%dT%H:%M:%fZ','now')"
            )
            return utc_micros(connection.exec_driver_sql(sql).scalar_one())
    finally:
        drain_case(case)


def assert_only_claim_changed(before, after, intent, clock_bounds):
    expected = deepcopy(before)
    (old,) = [row for row in expected["tables"]["jobs"]["rows"] if row["id"] == intent.job_id]
    (actual,) = [row for row in after["tables"]["jobs"]["rows"] if row["id"] == intent.job_id]
    assert (old["status"], old["owner"], old["lease_until"], old["lease_generation"]) == (
        "queued",
        None,
        None,
        intent.expected_generation,
    )
    lease = actual["lease_until"]
    assert type(lease) in (int, float) and math.isfinite(lease)
    first, last = clock_bounds
    assert type(first) is type(last) is int and first <= last
    (account,) = [
        row
        for row in before["tables"]["budget_accounts"]["rows"]
        if row["scope"] == "job" and row["job_id"] == intent.job_id
    ]
    quantum = 1 if "$postgres" in before["shape"] else 1000
    period_start = -(-utc_micros(account["period_start"]) // quantum) * quantum
    period_end = (utc_micros(account["period_end"]) // quantum) * quantum
    assert period_start <= first < period_end
    lower = min(first + intent.lease_seconds * 1_000_000, period_end)
    upper = min(last + intent.lease_seconds * 1_000_000, period_end)
    exact_lease = Fraction(lease) * 1_000_000
    # Permit only the downward float representation at the lower native bound.
    assert Fraction(math.nextafter(float(lease), math.inf)) * 1_000_000 >= lower
    assert first < exact_lease <= upper
    old.update(
        status="running",
        owner=intent.owner_uuid,
        lease_until=actual["lease_until"],
        lease_generation=intent.expected_generation + 1,
    )
    assert_same_state(expected, after)


def assert_no_canary(error, state):
    assert SECRET_CANARY not in str(error)
    assert SECRET_CANARY not in repr(error)
    assert SECRET_CANARY not in "".join(traceback.format_exception(error))
    assert SECRET_CANARY not in repr(state)


@pytest.mark.parametrize("legacy", [False, True], ids=["fresh", "legacy"])
def test_genuine_claim_has_exact_state_delta_and_complete_work(
    failure_case, monkeypatch, record_property
):
    case = failure_case.case
    before = whole_state(case)
    adapter = InstalledAdapter()
    controls = observe_controls(monkeypatch)
    with execution_owner(case, adapter) as (owner, record):
        first = native_clock(case)
        fence = bounded_claim(owner, record, case, controls, record_property)
        last = native_clock(case)
        assert type(fence) is JobFence
        assert fence == JobFence(case.job_id, "a" * 32, 1)
        assert record.source is not None and record.source.fence == fence
        assert record.source.configuration_digest == adapter.initial.digest
        assert record.source.configuration_size == len(adapter.initial.canonical_bytes)
        assert adapter.phases == ["initial", "pre_mutation", "post_clean"]
        assert adapter.validate_calls == adapter.send_calls == 0
        after = whole_state(case)
        assert_only_claim_changed(before, after, claim_intent(case), (first, last))
        facts = owner.outcome
        with pytest.raises(AdmissionError) as reused:
            owner.claim(case.principal, case.context, claim_intent(case))
        assert reused.value.reason == "invocation_reused"
        assert reused.value.code == "invalid_request"
        assert owner.outcome == facts
        assert_same_state(after, whole_state(case))


def test_installed_configuration_mismatch_never_claims_or_registers(failure_case):
    case = failure_case.case
    before = whole_state(case)
    adapter = InstalledAdapter(changed_configuration())
    with execution_owner(case, adapter) as (owner, record):
        with pytest.raises(AdmissionError) as caught:
            owner.claim(case.principal, case.context, claim_intent(case))
        assert caught.value.reason == "origin_unproved"
        assert caught.value.code == "dependency_unavailable"
        assert owner.outcome.confirmed_precommit_rollback
        assert not owner.outcome.commit_attempted
        assert record.source is None and adapter.validate_calls == adapter.send_calls == 0
        after = whole_state(case)
        assert_same_state(before, after)
        assert_no_canary(caught.value, after)


@pytest.mark.parametrize("drift", ["configuration", "unavailable"])
def test_postclean_installed_drift_retains_claim_but_never_registers(
    failure_case, monkeypatch, record_property, drift
):
    case = failure_case.case
    before = whole_state(case)
    after_mapping = (
        changed_configuration() if drift == "configuration" else RuntimeError(SECRET_CANARY)
    )
    adapter = InstalledAdapter(after=after_mapping)
    with execution_owner(case, adapter) as (owner, record):
        first = native_clock(case)
        with monkeypatch.context() as scoped:
            writes = observe_claim_updates(scoped, case)
            with pytest.raises(AdmissionError) as caught:
                owner.claim(case.principal, case.context, claim_intent(case))
        last = native_clock(case)
        assert writes == [{"rowcount": 1}]
        assert caught.value.reason == "stale_source"
        assert caught.value.code == "dependency_unavailable"
        assert owner.outcome.commit_acknowledged and not owner.outcome.cleanup_failed
        assert not owner.outcome.confirmed_precommit_rollback
        assert record.source is None
        assert adapter.phases == ["initial", "pre_mutation", "post_clean"]
        assert adapter.validate_calls == adapter.send_calls == 0
        after = whole_state(case)
        assert_only_claim_changed(before, after, claim_intent(case), (first, last))
        assert_no_canary(caught.value, after)
        record_property(
            "f3_post_clean_binding",
            json.dumps(
                {
                    "phases": adapter.phases,
                    "protected_update_attempts": writes,
                    "outcome": asdict(owner.outcome),
                    "capability_registered": False,
                },
                sort_keys=True,
            ),
        )


@pytest.mark.parametrize("persisted", [False, True], ids=["not-visible", "visible"])
def test_lost_claim_ack_never_registers_and_fresh_state_is_not_retry_authority(
    failure_case, monkeypatch, record_property, persisted
):
    case = failure_case.case
    before = whole_state(case)
    adapter = InstalledAdapter()
    original = Connection.commit
    attempted = []

    def lose_ack(connection):
        if connection.engine is case.engine:
            attempted.append(connection)
            if persisted:
                original(connection)
            raise RuntimeError(SECRET_CANARY)
        return original(connection)

    with execution_owner(case, adapter) as (owner, record):
        first = native_clock(case)
        with monkeypatch.context() as scoped:
            scoped.setattr(Connection, "commit", lose_ack)
            with pytest.raises(AdmissionError) as caught:
                owner.claim(case.principal, case.context, claim_intent(case))
        last = native_clock(case)
        assert len(attempted) == 1 and caught.value.code == "outcome_uncertain"
        assert owner.outcome.commit_attempted and not owner.outcome.commit_acknowledged
        assert not owner.outcome.confirmed_precommit_rollback
        assert record.source is None and adapter.phases == ["initial", "pre_mutation"]
        after = whole_state(case)
        if persisted:
            assert_only_claim_changed(before, after, claim_intent(case), (first, last))
        else:
            assert_same_state(before, after)
        assert_no_canary(caught.value, after)
        facts = owner.outcome
        with pytest.raises(AdmissionError) as reused:
            owner.claim(case.principal, case.context, claim_intent(case))
        assert reused.value.reason == "invocation_reused"
        assert reused.value.code == "invalid_request"
        assert owner.outcome == facts
        assert_same_state(after, whole_state(case))
        record_property(
            "f3_unknown_claim_ack",
            json.dumps({"visible": persisted, "outcome": asdict(facts)}, sort_keys=True),
        )


def test_committed_claim_cleanup_failure_withholds_registration(
    failure_case, monkeypatch, record_property
):
    case = failure_case.case
    before = whole_state(case)
    adapter = InstalledAdapter()
    original = Connection.close
    attempted = []

    def lose_cleanup(connection):
        if connection.engine is case.engine and not attempted:
            attempted.append(connection)
            raise RuntimeError(SECRET_CANARY)
        return original(connection)

    with execution_owner(case, adapter) as (owner, record):
        first = native_clock(case)
        with monkeypatch.context() as scoped:
            scoped.setattr(Connection, "close", lose_cleanup)
            with pytest.raises(AdmissionError) as caught:
                owner.claim(case.principal, case.context, claim_intent(case))
        last = native_clock(case)
        assert len(attempted) == 1 and caught.value.code == "outcome_uncertain"
        assert owner.outcome.commit_acknowledged and owner.outcome.cleanup_failed
        assert not owner.outcome.confirmed_precommit_rollback and record.source is None
        assert adapter.phases == ["initial", "pre_mutation"]
        assert adapter.validate_calls == adapter.send_calls == 0
        after = whole_state(case)
        assert_only_claim_changed(before, after, claim_intent(case), (first, last))
        assert_no_canary(caught.value, after)
        record_property(
            "f3_claim_cleanup_failure", json.dumps(asdict(owner.outcome), sort_keys=True)
        )


@pytest.mark.parametrize("drift", ["configuration", "unavailable"])
def test_pre_mutation_installed_drift_never_updates_or_registers(
    failure_case, monkeypatch, record_property, drift
):
    case = failure_case.case
    before = whole_state(case)
    changed = changed_configuration() if drift == "configuration" else RuntimeError(SECRET_CANARY)
    adapter = InstalledAdapter(after=changed, drift_at="pre_mutation")
    with execution_owner(case, adapter) as (owner, record):
        with monkeypatch.context() as scoped:
            writes = observe_claim_updates(scoped, case)
            with pytest.raises(AdmissionError) as caught:
                owner.claim(case.principal, case.context, claim_intent(case))
        assert caught.value.reason == "stale_source"
        assert caught.value.code == "dependency_unavailable"
        assert adapter.phases == ["initial", "pre_mutation"]
        assert writes == [] and adapter.validate_calls == adapter.send_calls == 0
        assert owner.outcome.confirmed_precommit_rollback
        assert not owner.outcome.commit_attempted and not owner.outcome.cleanup_failed
        assert record.source is None and record.coordinator not in failure_persistence._CLAIMS
        after = whole_state(case)
        assert_same_state(before, after)
        assert_no_canary(caught.value, after)
        record_property(
            "f3_pre_mutation_binding",
            json.dumps(
                {
                    "phases": adapter.phases,
                    "protected_update_attempts": writes,
                    "outcome": asdict(owner.outcome),
                    "whole_state_preserved": True,
                },
                sort_keys=True,
            ),
        )


@pytest.mark.parametrize("phase", ["initial", "pre_mutation", "post_clean"])
def test_installed_observation_deadline_withholds_authority_with_truthful_state(
    failure_case, monkeypatch, record_property, phase
):
    """Deterministic +10s boundary; actual wall time is a separately labeled observation."""
    case = failure_case.case
    before = whole_state(case)
    first = native_clock(case)
    clock = [1000.0]
    adapter = DeadlineAdapter(phase, clock)
    with execution_owner(case, adapter) as (owner, record):
        started = time.monotonic()
        with monkeypatch.context() as scoped:
            scoped.setattr(operation_work, "perf_counter", lambda: clock[0])
            writes = observe_claim_updates(scoped, case)
            controls = observe_controls(scoped)
            with pytest.raises(AdmissionError) as caught:
                owner.claim(case.principal, case.context, claim_intent(case))
        actual_seconds = time.monotonic() - started
        last = native_clock(case)
        work = record.coordinator._work
        assert work is record.work and work._invocation_started == adapter.original_start == 1000.0
        assert clock == [1010.0] and work._detached
        assert not work._listeners and work._lease is None and work._connection is None
        assert record.source is None and record.coordinator not in failure_persistence._CLAIMS
        assert adapter.validate_calls == adapter.send_calls == 0
        phases = ["initial", "pre_mutation", "post_clean"]
        assert adapter.phases == phases[: phases.index(phase) + 1]
        facts = owner.outcome
        after = whole_state(case)
        if phase == "initial":
            assert caught.value.code == "dependency_unavailable"
            assert not any(asdict(facts).values()) and writes == [] and work.statements == 0
            assert_same_state(before, after)
        elif phase == "pre_mutation":
            assert caught.value.code == "dependency_unavailable"
            assert facts.confirmed_precommit_rollback and facts.cleanup_failed
            assert not facts.commit_attempted and writes == []
            assert_same_state(before, after)
        else:
            assert caught.value.code == "dependency_unavailable"
            assert facts.commit_acknowledged and not facts.cleanup_failed
            assert not facts.rollback_attempted and writes == [{"rowcount": 1}]
            assert_only_claim_changed(before, after, claim_intent(case), (first, last))
        assert_no_canary(caught.value, after)
        cleanup = [
            item for item in controls if item[0] is work and item[1] not in {"begin", "commit"}
        ]
        assert work.statements <= 512 and work.statements - len(cleanup) <= 504
        assert len(cleanup) <= 8
        record_property(
            "f3_installed_deadline",
            json.dumps(
                {
                    "target_phase": phase,
                    "observed_phases": adapter.phases,
                    "clock_kind": "deterministic monotonic boundary; not wall-time duration",
                    "unchanged_work_start": adapter.original_start,
                    "observed_clock": clock[0],
                    "actual_wall_seconds": actual_seconds,
                    "protected_update_attempts": writes,
                    "ordinary_units": work.statements - len(cleanup),
                    "cleanup_units": len(cleanup),
                    "total_units": work.statements,
                    "outcome": asdict(facts),
                    "capability_registered": False,
                },
                sort_keys=True,
            ),
        )
