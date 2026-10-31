"""Independent F3 native claim/completion oracles; synthetic setup is not startup proof.

The real private owner supplies claim authority; returned fences are historical.
Completion uses a genuine registered dependency event; no provider is called.
"""

import hashlib
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

from agent_rewind import failure_persistence, failure_terminal, operation_work
from agent_rewind.admission_transaction import AdmissionError
from agent_rewind.failure_evidence import CompletionEvent, CreatedFailure
from agent_rewind.migrations.compatibility import _InspectionChecks
from agent_rewind.migrations.failure_catalog import inspect_failure_catalog
from agent_rewind.migrations.failure_service import initialize_failure_evidence
from agent_rewind.migrations.schema import FAILURE, LEDGER, MigrationRefused, catalog, checksum
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


def evidence_producer_grant(case, before):
    """Install final SELECT+INSERT before claim; later stages never widen these rights."""
    drain_case(case)
    with case.pg["owner"].begin() as connection:
        assert _application_acl(connection, case.pg["app_role"]) == before
        assert not any(row[1] == EVIDENCE for row in before)
        role = connection.dialect.identifier_preparer.quote_identifier(case.pg["app_role"])
        connection.exec_driver_sql(f"GRANT SELECT, INSERT ON job_failure_evidence TO {role}")
        after = _application_acl(connection, case.pg["app_role"])
        expected = before | {
            ("table", EVIDENCE, "", "SELECT", False, case.pg["owner_role"]),
            ("table", EVIDENCE, "", "INSERT", False, case.pg["owner_role"]),
        }
        assert after == expected
    drain_case(case)


def assert_restricted_producer(case):
    """Observe actual role and effective rights, not just the GRANT statement."""
    try:
        with case.engine.connect() as connection:
            role = connection.execute(
                text(
                    "SELECT current_user,session_user,rolsuper,rolcreaterole,rolcreatedb,"
                    "rolinherit,rolreplication,rolbypassrls,"
                    "pg_has_role(current_user,:owner,'MEMBER') "
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
            functions = connection.execute(
                text(
                    "SELECT p.proname,pg_get_userbyid(p.proowner),"
                    "has_function_privilege(current_user,p.oid,'EXECUTE'),"
                    "has_function_privilege(:owner,p.oid,'EXECUTE') "
                    "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                    "WHERE n.nspname='public' ORDER BY p.proname LIMIT 3"
                ),
                {"owner": case.pg["owner_role"]},
            ).all()
        assert tuple(role) == (case.pg["app_role"], case.pg["app_role"]) + (False,) * 7
        assert tuple(rights) == (True, True) + (False,) * 6
        assert [tuple(row) for row in functions] == [
            (name, case.pg["owner_role"], False, True)
            for name in ("ar7_ledger_constraint", "job_failure_evidence_guard")
        ]
        return {
            "role": tuple(role),
            "evidence_rights": tuple(rights),
            "function_execution": [tuple(row) for row in functions],
        }
    finally:
        drain_case(case)


def restore_producer_grant(case, before):
    drain_case(case)
    with case.pg["owner"].begin() as connection:
        role = connection.dialect.identifier_preparer.quote_identifier(case.pg["app_role"])
        connection.exec_driver_sql(f"REVOKE SELECT, INSERT ON job_failure_evidence FROM {role}")
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
            evidence_producer_grant(case, old_acl)
            role = assert_restricted_producer(case)
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
                restore_producer_grant(case, old_acl)
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


# Exact ordered fields from the adopted D3 tag2 contract, not production constants.
D3_SCOPE = ("organization_id", "project_id", "resource_kind", "resource_id")
D3_OPERATION = (
    "id",
    "project_id",
    "principal_id",
    "kind",
    "client_operation_id",
    "request_digest",
    "job_id",
    "accepted_response",
    "created_at",
    "retain_until",
    "job_resource_kind",
    "execution_config_digest",
    "payload_version",
    "failure_correlation_id",
)
D3_JOB_IMMUTABLE = (
    "id",
    "kind",
    "created",
    "payload",
    "actor",
    "payload_version",
    "execution_config_ref",
    "execution_config_digest",
    "budget",
)
D3_CONFIGURATION = (
    "id",
    "project_id",
    "digest",
    "locator",
    "format_version",
    "byte_count",
    "created_at",
    "reference_id",
)
D3_EVIDENCE = (
    "schema_version",
    "kind",
    "project_id",
    "job_resource_kind",
    "job_id",
    "operation_id",
    "lease_generation",
    "job_status",
    "cause",
    "phase",
    "origin_kind",
    "correlation_id",
    "created_at_micros",
)
D3_JOB_TERMINAL = (
    "id",
    "kind",
    "created",
    "payload",
    "status",
    "owner",
    "lease_until",
    "budget",
    "reserved",
    "result",
    "error",
    "actor",
    "payload_version",
    "execution_config_ref",
    "execution_config_digest",
)


class DependencyAdapter(InstalledAdapter):
    """An installed property genuinely becomes unavailable after acknowledged claim."""

    def __init__(self):
        super().__init__()
        self.unavailable = False

    @property
    def configuration(self):
        if not self.unavailable:
            return super().configuration
        assert self.record.source is not None
        assert self.record.coordinator.outcome.commit_acknowledged
        self.reads += 1
        self.phases.append("dependency")
        raise RuntimeError(SECRET_CANARY)


def native_digest_inputs(case):
    """Independent native SELECTs; preserve database timestamp Text exactly."""
    drain_case(case)
    try:
        with case.case.engine.connect() as connection:
            op_columns = ",".join(
                f"CAST({name} AS TEXT) AS {name}"
                if name in {"created_at", "retain_until"}
                else name
                for name in D3_OPERATION
            )
            operation_rows = (
                connection.execute(
                    text(f"SELECT {op_columns} FROM operations WHERE job_id=:job LIMIT 2"),
                    {"job": case.job_id},
                )
                .mappings()
                .all()
            )
            assert len(operation_rows) == 1
            operation = dict(operation_rows[0])
            config_columns = ",".join(
                "r.artifact_id AS reference_id"
                if name == "reference_id"
                else "CAST(o.created_at AS TEXT) AS created_at"
                if name == "created_at"
                else f"o.{name}"
                for name in D3_CONFIGURATION
            )
            config_rows = (
                connection.execute(
                    text(
                        f"SELECT {config_columns} FROM artifact_refs r "
                        "LEFT JOIN artifact_objects o ON o.id=r.artifact_id "
                        "AND o.project_id=r.project_id WHERE r.owner_kind='job' "
                        "AND r.owner_id=:job AND r.role='admission_config' LIMIT 2"
                    ),
                    {"job": case.job_id},
                )
                .mappings()
                .all()
            )
            assert len(config_rows) == 1
            configuration_row = dict(config_rows[0])
        return operation, configuration_row
    finally:
        drain_case(case)


def expected_failure_hashes(case, state, record, native_inputs):
    """Encode adopted typed arrays directly, without the runtime encoder/readers."""

    def tag(value):
        if value is None:
            return ["n"]
        if type(value) is bool:
            return ["b", int(value)]
        if type(value) is int:
            assert -(2**63) <= value < 2**63
            return ["i", str(value)]
        if type(value) is float:
            assert math.isfinite(value)
            return ["f", (0.0 if value == 0 else value).hex()]
        assert type(value) is str
        assert len(value.encode("utf-8")) <= 4096
        return ["s", value]

    def row(label, fields, values):
        return [label, [[name, tag(values[name])] for name in fields]]

    def digest(frame):
        encoded = json.dumps(
            frame, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        assert len(encoded) <= 4096
        return hashlib.sha256(encoded).hexdigest()

    operation, descriptor = native_inputs
    (job,) = [r for r in state["tables"]["jobs"]["rows"] if r["id"] == case.job_id]
    assert operation["project_id"] == descriptor["project_id"] == case.context.project_id
    assert operation["job_id"] == job["id"]
    assert descriptor["id"] == descriptor["reference_id"]
    assert descriptor["digest"] == operation["execution_config_digest"]
    scope = {
        "organization_id": case.organization_id,
        "project_id": case.context.project_id,
        "resource_kind": "job",
        "resource_id": case.job_id,
    }
    dialect = "postgresql" if hasattr(case, "pg") else "sqlite"
    association = digest(
        [
            "ar-failure-association",
            1,
            dialect,
            row("scope", D3_SCOPE, scope),
            row("operation", D3_OPERATION, operation),
            row("job_immutable", D3_JOB_IMMUTABLE, job),
            row("admission_config", D3_CONFIGURATION, descriptor),
        ]
    )
    any_call = any(r["job_id"] == case.job_id for r in state["tables"]["provider_calls"]["rows"])
    source = digest(
        [
            "ar-failure-source",
            2,
            dialect,
            association,
            row("job_terminal", D3_JOB_TERMINAL, job),
            ["generation", tag(record.lease_generation)],
            ["any_provider_call_for_job", tag(any_call)],
            row("evidence_core", D3_EVIDENCE, asdict(record)),
        ]
    )
    return association, source


def assert_only_completion_changed(case, before, after, original, native_inputs, clock_bounds):
    expected = deepcopy(before)
    (job,) = [r for r in expected["tables"]["jobs"]["rows"] if r["id"] == case.job_id]
    assert job["status"] == "running"
    status = "cancelled" if job["cancel"] else "failed"
    job["status"] = status
    record = original.record
    assert original.organization_id == case.organization_id
    assert original.fence == JobFence(case.job_id, job["owner"], job["lease_generation"])
    assert (record.job_status, record.cause, record.phase) == (
        status,
        "dependency_failed",
        "outcome_unknown",
    )
    assert (
        record.schema_version,
        record.kind,
        record.job_resource_kind,
        record.origin_kind,
        record.job_id,
        record.lease_generation,
    ) == (1, "verified_failure", "job", "admission", case.job_id, original.fence.generation)
    assert record.project_id == case.context.project_id
    assert record.operation_id == native_inputs[0]["id"]
    assert record.correlation_id == native_inputs[0]["failure_correlation_id"]
    assert clock_bounds[0] <= record.created_at_micros <= clock_bounds[1]
    assert expected["tables"][EVIDENCE]["rows"] == []
    expected["tables"][EVIDENCE]["rows"] = [asdict(record)]
    assert_same_state(expected, after)
    assert (record.association_sha256, record.source_sha256) == expected_failure_hashes(
        case, after, record, native_inputs
    )


def assert_public_dormant_policy_refuses_producer(case):
    """Public F2 stays SELECT-only even when the private producer is installed."""
    if not hasattr(case, "pg"):
        return
    before = whole_state(case)
    try:
        with case.engine.connect() as connection:
            with pytest.raises(MigrationRefused) as caught:
                inspect_failure_catalog(connection, _InspectionChecks(time.monotonic() + 2))
            assert caught.value.code == "schema_incompatible"
    finally:
        drain_case(case)
    assert_same_state(before, whole_state(case))


@pytest.mark.parametrize("legacy", [False, True], ids=["fresh", "legacy"])
def test_genuine_completion_keeps_final_grants_and_exact_native_delta(
    failure_case, monkeypatch, record_property
):
    case = failure_case.case
    assert_public_dormant_policy_refuses_producer(case)
    before = whole_state(case)
    adapter = DependencyAdapter()
    controls = observe_controls(monkeypatch)
    with execution_owner(case, adapter) as (owner, record):
        start = native_clock(case)
        fence = bounded_claim(owner, record, case, controls, record_property)
        end = native_clock(case)
        claimed = whole_state(case)
        assert_only_claim_changed(before, claimed, claim_intent(case), (start, end))
        if hasattr(case, "pg"):
            assert_restricted_producer(case)
        adapter.unavailable = True
        event = owner._check_installed_binding()
        assert type(event) is CompletionEvent and record.event is event
        assert event in failure_persistence._EVENTS
        assert adapter.phases == ["initial", "pre_mutation", "post_clean", "dependency"]
        assert adapter.validate_calls == adapter.send_calls == 0
        assert_same_state(claimed, whole_state(case))
        native_inputs = native_digest_inputs(case)
        coordinator = failure_terminal.TerminalCoordinator(case.engine, case.authority)
        assert coordinator.original is None
        first = native_clock(case)
        started = time.monotonic()
        created = coordinator.complete_failure(case.principal, case.context, event)
        elapsed = time.monotonic() - started
        last = native_clock(case)
        assert type(created) is CreatedFailure and created.kind == "created"
        assert created.original is coordinator.original and created.original.fence == fence
        facts = coordinator.outcome
        assert facts.commit_acknowledged and not facts.cleanup_failed
        assert not facts.rollback_attempted
        assert event not in failure_persistence._EVENTS and record.event is None
        assert not failure_terminal._TERMINALS
        work = coordinator._work
        assert work._detached and not work._listeners and work._connection is None
        cleanup = [
            item for item in controls if item[0] is work and item[1] not in {"begin", "commit"}
        ]
        assert 0 < len(cleanup) <= 8
        assert work.statements <= 512 and work.statements - len(cleanup) <= 504
        assert elapsed < 10 and work.instructions < 20_000_000
        after = whole_state(case)
        assert SECRET_CANARY not in repr(created) and SECRET_CANARY not in repr(after)
        assert_only_completion_changed(
            case, claimed, after, created.original, native_inputs, (first, last)
        )
        if hasattr(case, "pg"):
            assert_restricted_producer(case)
        with pytest.raises(AdmissionError) as reused:
            failure_terminal.TerminalCoordinator(case.engine, case.authority).complete_failure(
                case.principal, case.context, event
            )
        assert reused.value.reason == "capability_not_issued"
        assert reused.value.code == "invalid_request"
        assert_same_state(after, whole_state(case))
        record_property(
            "f3_native_completion",
            json.dumps(
                {
                    "total_units": work.statements,
                    "cleanup_units": len(cleanup),
                    "ordinary_units": work.statements - len(cleanup),
                    "vm_instructions": work.instructions,
                    "elapsed_seconds": elapsed,
                    "outcome": asdict(facts),
                    "native_clock_bounds": [first, last],
                    "created_at_micros": created.original.record.created_at_micros,
                    "independent_hashes_equal": True,
                    "stable_producer_grants": True,
                    "full_state_and_ciphertexts_exact": True,
                    "provider_calls": 0,
                },
                sort_keys=True,
            ),
        )


@pytest.mark.parametrize("boundary", ["commit_before", "commit_after", "cleanup"])
def test_completion_uncertainty_retains_original_and_never_reissues_event(
    failure_case, monkeypatch, record_property, boundary
):
    case = failure_case.case
    before = whole_state(case)
    adapter = DependencyAdapter()
    controls = observe_controls(monkeypatch)
    original_commit, original_close = Connection.commit, Connection.close
    attempts = []

    def commit(connection):
        if connection.engine is case.engine and boundary != "cleanup":
            attempts.append("commit")
            if boundary == "commit_after":
                original_commit(connection)
            raise RuntimeError(SECRET_CANARY)
        return original_commit(connection)

    def close(connection):
        if connection.engine is case.engine and boundary == "cleanup" and not attempts:
            attempts.append("close")
            raise RuntimeError(SECRET_CANARY)
        return original_close(connection)

    with execution_owner(case, adapter) as (owner, record):
        claim_start = native_clock(case)
        fence = bounded_claim(owner, record, case, controls, record_property)
        claim_end = native_clock(case)
        claimed = whole_state(case)
        assert_only_claim_changed(before, claimed, claim_intent(case), (claim_start, claim_end))
        adapter.unavailable = True
        event = owner._check_installed_binding()
        assert type(event) is CompletionEvent and record.event is event
        assert adapter.phases == ["initial", "pre_mutation", "post_clean", "dependency"]
        assert_same_state(claimed, whole_state(case))
        native_inputs = native_digest_inputs(case)
        coordinator = failure_terminal.TerminalCoordinator(case.engine, case.authority)
        first = native_clock(case)
        started = time.monotonic()
        with monkeypatch.context() as scoped:
            scoped.setattr(Connection, "commit", commit)
            scoped.setattr(Connection, "close", close)
            with pytest.raises(AdmissionError) as caught:
                coordinator.complete_failure(case.principal, case.context, event)
        elapsed = time.monotonic() - started
        last = native_clock(case)
        assert attempts == (["close"] if boundary == "cleanup" else ["commit"])
        assert caught.value.code == "outcome_uncertain"
        facts = coordinator.outcome
        assert facts.commit_attempted and not facts.confirmed_precommit_rollback
        assert facts.commit_acknowledged is (boundary == "cleanup")
        assert facts.cleanup_failed is (boundary == "cleanup")
        retained = coordinator.original
        assert retained is not None and retained.fence == fence
        assert retained.record.cause == "dependency_failed"
        assert retained.record.job_status == "failed"
        assert first <= retained.record.created_at_micros <= last
        assert event not in failure_persistence._EVENTS and record.event is None
        assert not failure_terminal._TERMINALS
        assert adapter.validate_calls == adapter.send_calls == 0
        after = whole_state(case)
        visible = boundary != "commit_before"
        if visible:
            assert_only_completion_changed(
                case, claimed, after, retained, native_inputs, (first, last)
            )
        else:
            assert_same_state(claimed, after)
            proposed = deepcopy(claimed)
            (job,) = [row for row in proposed["tables"]["jobs"]["rows"] if row["id"] == case.job_id]
            job["status"] = "failed"
            assert (
                retained.record.association_sha256,
                retained.record.source_sha256,
            ) == expected_failure_hashes(case, proposed, retained.record, native_inputs)
        assert_no_canary(caught.value, after)
        assert SECRET_CANARY not in repr(retained)
        with pytest.raises(AdmissionError) as reused:
            coordinator.complete_failure(case.principal, case.context, event)
        assert reused.value.reason == "invocation_reused"
        assert reused.value.code == "invalid_request"
        assert coordinator.outcome == facts and coordinator.original is retained
        other = failure_terminal.TerminalCoordinator(case.engine, case.authority)
        with pytest.raises(AdmissionError) as consumed:
            other.complete_failure(case.principal, case.context, event)
        assert consumed.value.reason == "capability_not_issued"
        assert consumed.value.code == "invalid_request"
        assert other.original is None and not any(asdict(other.outcome).values())
        assert_same_state(after, whole_state(case))
        work = coordinator._work
        cleanup = [
            item for item in controls if item[0] is work and item[1] not in {"begin", "commit"}
        ]
        assert work._detached and not work._listeners and work._connection is None
        assert work.statements <= 512 and work.statements - len(cleanup) <= 504
        assert len(cleanup) <= 8 and elapsed < 10 and work.instructions < 20_000_000
        record_property(
            "f3_terminal_uncertainty",
            json.dumps(
                {
                    "boundary": boundary,
                    "visible_native_completion": visible,
                    "outcome": asdict(facts),
                    "original_identity_retained": True,
                    "created_at_micros": retained.record.created_at_micros,
                    "event_consumed_without_reissue": True,
                    "readback": "independent native observation; no product inspect or retry",
                    "total_units": work.statements,
                    "ordinary_units": work.statements - len(cleanup),
                    "cleanup_units": len(cleanup),
                    "elapsed_seconds": elapsed,
                    "vm_instructions": work.instructions,
                },
                sort_keys=True,
            ),
        )


@contextmanager
def genuine_terminal_event(case, controls, record_property):
    """Issue through the actual claim owner and fixed dependency observation."""
    before = whole_state(case)
    adapter = DependencyAdapter()
    with execution_owner(case, adapter) as (owner, record):
        first = native_clock(case)
        fence = bounded_claim(owner, record, case, controls, record_property)
        last = native_clock(case)
        claimed = whole_state(case)
        assert_only_claim_changed(before, claimed, claim_intent(case), (first, last))
        adapter.unavailable = True
        event = owner._check_installed_binding()
        assert type(event) is CompletionEvent and record.event is event
        assert event in failure_persistence._EVENTS
        assert adapter.phases == ["initial", "pre_mutation", "post_clean", "dependency"]
        assert adapter.validate_calls == adapter.send_calls == 0
        assert_same_state(claimed, whole_state(case))
        yield SimpleNamespace(owner=owner, record=record, fence=fence, event=event, claimed=claimed)


def observe_terminal_writes(monkeypatch, case):
    """Forward real terminal DML without substituting its result."""
    execute = Connection.execute
    observed = []

    def forward(connection, statement, *args, **kwargs):
        table = getattr(getattr(statement, "table", None), "name", None)
        selected = connection.engine is case.engine and (
            getattr(statement, "is_update", False)
            and table == "jobs"
            or getattr(statement, "is_insert", False)
            and table == EVIDENCE
        )
        attempt = {"table": table, "returned": False, "rowcount": None}
        if selected:
            observed.append(attempt)
        result = execute(connection, statement, *args, **kwargs)
        if selected:
            attempt.update(returned=True, rowcount=result.rowcount)
        return result

    monkeypatch.setattr(Connection, "execute", forward)
    return observed


def assert_terminal_refusal_state(case, issued, coordinator, error, before, writes):
    """A refused completion consumes its event and preserves the observed state."""
    facts = coordinator.outcome
    assert facts.begun and not facts.commit_attempted and not facts.commit_acknowledged
    assert facts.rollback_attempted and facts.rollback_acknowledged
    assert coordinator.original is None and writes == []
    assert issued.event not in failure_persistence._EVENTS and issued.record.event is None
    assert not failure_terminal._TERMINALS
    after = whole_state(case)
    assert_same_state(before, after)
    assert_no_canary(error, after)
    observer = failure_terminal.TerminalCoordinator(case.engine, case.authority)
    with pytest.raises(AdmissionError) as consumed:
        observer.complete_failure(case.principal, case.context, issued.event)
    assert consumed.value.reason == "capability_not_issued"
    assert consumed.value.code == "invalid_request"
    assert observer.original is None and not any(asdict(observer.outcome).values())
    assert_same_state(after, whole_state(case))
    assert case.engine.pool.checkedout() == 0


def record_terminal_refusal_work(coordinator, controls, elapsed, record_property, **observed):
    work = coordinator._work
    cleanup = [item for item in controls if item[0] is work and item[1] not in {"begin", "commit"}]
    assert work._detached and not work._listeners and work._connection is None
    assert work.statements <= 512 and work.statements - len(cleanup) <= 504
    assert len(cleanup) <= 8 and elapsed < 10 and work.instructions < 20_000_000
    record_property(
        "f3_terminal_refusal",
        json.dumps(
            {
                "outcome": asdict(coordinator.outcome),
                "total_units": work.statements,
                "ordinary_units": work.statements - len(cleanup),
                "cleanup_units": len(cleanup),
                "elapsed_seconds": elapsed,
                "vm_instructions": work.instructions,
                **observed,
            },
            sort_keys=True,
        ),
    )


@pytest.mark.parametrize("changed", ["owner", "generation", "origin"])
def test_terminal_refuses_changed_native_identity_before_protected_writes(
    failure_case, monkeypatch, record_property, changed
):
    case = failure_case.case
    controls = observe_controls(monkeypatch)
    with genuine_terminal_event(case, controls, record_property) as issued:
        expected = deepcopy(issued.claimed)
        if changed == "origin":
            (row,) = [
                row
                for row in expected["tables"]["operations"]["rows"]
                if row["job_id"] == case.job_id
            ]
            field, table, key = "failure_correlation_id", "operations", "job_id"
            value = "d" * 32 if row[field] != "d" * 32 else "e" * 32
            sql = "UPDATE operations SET failure_correlation_id=:value WHERE job_id=:job"
            reason = "stale_source"
        else:
            (row,) = [row for row in expected["tables"]["jobs"]["rows"] if row["id"] == case.job_id]
            field, table, key = (
                "lease_generation" if changed == "generation" else "owner",
                "jobs",
                "id",
            )
            value = issued.fence.generation + 1 if changed == "generation" else "e" * 32
            assert value != row[field]
            sql = (
                "UPDATE jobs SET lease_generation=:value WHERE id=:job"
                if changed == "generation"
                else "UPDATE jobs SET owner=:value WHERE id=:job"
            )
            reason = "not_eligible"
        row[field] = value
        # These setup-owner writes retain every trigger and grant. An early schema
        # refusal fails this case; it cannot impersonate a terminal-path refusal.
        drain_case(case)
        with case.case.engine.begin() as connection:
            result = connection.execute(text(sql), {"value": value, "job": case.job_id})
            assert result.rowcount == 1
            observed = connection.execute(
                text(f"SELECT {field} FROM {table} WHERE {key}=:job"), {"job": case.job_id}
            ).scalar_one()
            assert typed(observed) == typed(value)
        fault_before = whole_state(case)
        assert_same_state(expected, fault_before)
        coordinator = failure_terminal.TerminalCoordinator(case.engine, case.authority)
        with monkeypatch.context() as patch:
            writes = observe_terminal_writes(patch, case)
            started = time.monotonic()
            with pytest.raises(AdmissionError) as caught:
                coordinator.complete_failure(case.principal, case.context, issued.event)
            elapsed = time.monotonic() - started
        assert caught.value.reason == reason and caught.value.code == "dependency_unavailable"
        record_terminal_refusal_work(
            coordinator,
            controls,
            elapsed,
            record_property,
            fault=changed,
            native_mutation_committed=True,
            protected_writes=writes,
        )
        assert_terminal_refusal_state(case, issued, coordinator, caught.value, fault_before, writes)


def terminal_body_refusal(case, monkeypatch, record_property, mode):
    controls = observe_controls(monkeypatch)
    persist = failure_terminal.persist_verified_failure
    injected = []

    def replace_body(connection, token):
        assert connection.engine is case.engine and injected == []
        logical = connection.get_transaction()
        assert logical is not None and logical.is_active
        raw = connection.connection.driver_connection
        postgres = connection.dialect.name == "postgresql"
        before_xid = (
            raw.execute("SELECT pg_current_xact_id()::text").fetchone()[0] if postgres else None
        )
        if mode == "logical_restarted":
            if postgres:
                connection.rollback()
                injected_control = "ROLLBACK"
                assert raw.info.transaction_status.name == "IDLE"
            else:
                # The supported SQLite lease permits this read-only COMMIT.
                # It is injected physical control, not coordinator commit ACK.
                connection.commit()
                injected_control = "COMMIT"
                assert not raw.in_transaction
            assert not logical.is_active and connection.get_transaction() is None
            connection.exec_driver_sql(
                "BEGIN ISOLATION LEVEL READ COMMITTED" if postgres else "BEGIN IMMEDIATE"
            )
            assert connection.get_transaction() is not logical
        else:
            raw.execute("ROLLBACK")
            injected_control = "ROLLBACK"
            assert connection.get_transaction() is logical and logical.is_active
            if mode == "raw_restarted":
                assert postgres
                raw.execute("BEGIN ISOLATION LEVEL READ COMMITTED")
        after_xid = (
            raw.execute("SELECT pg_current_xact_id()::text").fetchone()[0]
            if postgres and mode != "raw_idle"
            else None
        )
        if postgres:
            assert type(before_xid) is str
            if mode == "raw_idle":
                assert raw.info.transaction_status.name == "IDLE"
            else:
                assert raw.info.transaction_status.name == "INTRANS"
                assert type(after_xid) is str and before_xid != after_xid
        else:
            assert raw.in_transaction is (mode == "logical_restarted")
        injected.append(
            {
                "mode": mode,
                "before_xid": before_xid,
                "after_xid": after_xid,
                "same_logical_root": connection.get_transaction() is logical,
                "injected_physical_control": injected_control,
                "qualification": (
                    "Read-only test injection before protected writes; "
                    "its physical COMMIT is separate from coordinator outcome facts."
                ),
            }
        )
        return persist(connection, token)

    with genuine_terminal_event(case, controls, record_property) as issued:
        coordinator = failure_terminal.TerminalCoordinator(case.engine, case.authority)
        with monkeypatch.context() as patch:
            writes = observe_terminal_writes(patch, case)
            patch.setattr(failure_terminal, "persist_verified_failure", replace_body)
            started = time.monotonic()
            with pytest.raises(AdmissionError) as caught:
                coordinator.complete_failure(case.principal, case.context, issued.event)
            elapsed = time.monotonic() - started
        assert len(injected) == 1
        assert caught.value.reason == "invalid_native_state"
        assert caught.value.code == "dependency_unavailable"
        record_terminal_refusal_work(
            coordinator,
            controls,
            elapsed,
            record_property,
            fault="native_body",
            injected=injected,
            protected_writes=writes,
        )
        assert_terminal_refusal_state(
            case, issued, coordinator, caught.value, issued.claimed, writes
        )


@pytest.mark.parametrize("mode", ["logical_restarted", "raw_idle"])
def test_terminal_refuses_replaced_native_body(failure_case, monkeypatch, record_property, mode):
    terminal_body_refusal(failure_case.case, monkeypatch, record_property, mode)


@POSTGRES
def test_postgres_terminal_refuses_restarted_raw_xid(pg, tmp_path, monkeypatch, record_property):
    with genuine_failure_case(tmp_path, monkeypatch, record_property, pg=pg) as fixture:
        terminal_body_refusal(fixture.case, monkeypatch, record_property, "raw_restarted")


@POSTGRES
def test_postgres_terminal_refuses_revoked_insert_without_reissuing_event(
    pg, tmp_path, monkeypatch, record_property
):
    with genuine_failure_case(tmp_path, monkeypatch, record_property, pg=pg) as fixture:
        case = fixture.case
        controls = observe_controls(monkeypatch)
        with genuine_terminal_event(case, controls, record_property) as issued:
            drain_case(case)
            with pg["owner"].connect() as connection:
                old_acl = _application_acl(connection, pg["app_role"])
                role = connection.dialect.identifier_preparer.quote_identifier(pg["app_role"])
            removed = ("table", EVIDENCE, "", "INSERT", False, pg["owner_role"])
            assert removed in old_acl
            try:
                with pg["owner"].begin() as connection:
                    connection.exec_driver_sql(f"REVOKE INSERT ON job_failure_evidence FROM {role}")
                    assert _application_acl(connection, pg["app_role"]) == old_acl - {removed}
                with case.engine.connect() as connection:
                    rights = connection.exec_driver_sql(
                        "SELECT current_user,session_user,"
                        "has_table_privilege(current_user,'job_failure_evidence','SELECT'),"
                        "has_table_privilege(current_user,'job_failure_evidence','INSERT')"
                    ).one()
                assert tuple(rights) == (pg["app_role"], pg["app_role"], True, False)
                fault_before = whole_state(case)
                expected = deepcopy(issued.claimed)
                original_acls = expected["native"]["table_owners_acl"]
                changed_acls = fault_before["native"]["table_owners_acl"]
                assert [r for r in original_acls if r[0] != EVIDENCE] == [
                    r for r in changed_acls if r[0] != EVIDENCE
                ]
                (old,) = [r for r in original_acls if r[0] == EVIDENCE]
                (new,) = [r for r in changed_acls if r[0] == EVIDENCE]
                assert old[:2] == new[:2] and old[2] != new[2]
                expected["native"]["table_owners_acl"] = changed_acls
                assert_same_state(expected, fault_before)
                coordinator = failure_terminal.TerminalCoordinator(case.engine, case.authority)
                with monkeypatch.context() as patch:
                    writes = observe_terminal_writes(patch, case)
                    started = time.monotonic()
                    with pytest.raises(AdmissionError) as caught:
                        coordinator.complete_failure(case.principal, case.context, issued.event)
                    elapsed = time.monotonic() - started
                assert caught.value.reason == "unsupported_profile"
                assert caught.value.code == "schema_incompatible"
                record_terminal_refusal_work(
                    coordinator,
                    controls,
                    elapsed,
                    record_property,
                    fault="revoked_insert",
                    intentional_grant_fault=True,
                    native_rights=list(rights),
                    protected_writes=writes,
                )
                assert_terminal_refusal_state(
                    case, issued, coordinator, caught.value, fault_before, writes
                )
            finally:
                drain_case(case)
                with pg["owner"].begin() as connection:
                    connection.exec_driver_sql(f"GRANT INSERT ON job_failure_evidence TO {role}")
                    assert _application_acl(connection, pg["app_role"]) == old_acl
            assert_restricted_producer(case)
            assert_same_state(issued.claimed, whole_state(case))


@POSTGRES
def test_postgres_terminal_real_deferred_generation_failure_rolls_back(
    pg, tmp_path, monkeypatch, record_property
):
    from sqlalchemy.exc import DBAPIError

    with genuine_failure_case(tmp_path, monkeypatch, record_property, pg=pg) as fixture:
        case = fixture.case
        controls = observe_controls(monkeypatch)
        with genuine_terminal_event(case, controls, record_property) as issued:
            coordinator = failure_terminal.TerminalCoordinator(case.engine, case.authority)
            flush = failure_terminal.reservation.flush_constraints
            execute_sql = Connection.exec_driver_sql
            transient, flush_errors, flush_statements = [], [], []

            def observe_flush(connection, statement, *args, **kwargs):
                selected = connection.engine is case.engine and statement.startswith(
                    "SET CONSTRAINTS "
                )
                if selected:
                    flush_statements.append(statement)
                try:
                    return execute_sql(connection, statement, *args, **kwargs)
                except DBAPIError as error:
                    if selected:
                        flush_errors.append(error.orig.sqlstate)
                    raise

            def change_and_restore(connection, scope):
                assert connection.engine is case.engine and transient == []
                original = coordinator.original
                assert original is not None and original.fence == issued.fence
                assert issued.fence.generation == 1
                assert (
                    connection.execute(
                        text("SELECT status FROM jobs WHERE id=:id"), {"id": case.job_id}
                    ).scalar_one()
                    == "failed"
                )
                assert (
                    connection.execute(
                        text("SELECT count(*) FROM job_failure_evidence WHERE job_id=:id"),
                        {"id": case.job_id},
                    ).scalar_one()
                    == 1
                )
                # Both writes must really succeed under the unchanged app grants.
                # The queued OLD/NEW generation violation survives the restoration.
                for generation in (0, issued.fence.generation):
                    observed = connection.execute(
                        text(
                            "UPDATE jobs SET lease_generation=:generation WHERE id=:id "
                            "RETURNING lease_generation"
                        ),
                        {"generation": generation, "id": case.job_id},
                    ).scalar_one()
                    assert type(observed) is int and observed == generation
                    transient.append(observed)
                return flush(connection, scope)

            with monkeypatch.context() as patch:
                writes = observe_terminal_writes(patch, case)
                patch.setattr(Connection, "exec_driver_sql", observe_flush)
                patch.setattr(failure_terminal.reservation, "flush_constraints", change_and_restore)
                started = time.monotonic()
                with pytest.raises(AdmissionError) as caught:
                    coordinator.complete_failure(case.principal, case.context, issued.event)
                elapsed = time.monotonic() - started
            assert transient == [0, 1]
            assert len(flush_statements) == 1 and flush_errors == ["23514"]
            assert caught.value.code == "dependency_unavailable"
            assert writes == [
                {"table": "jobs", "returned": True, "rowcount": 1},
                {"table": EVIDENCE, "returned": True, "rowcount": 1},
            ]
            facts = coordinator.outcome
            assert facts.begun and not facts.commit_attempted and not facts.commit_acknowledged
            assert facts.rollback_attempted and facts.rollback_acknowledged
            assert not facts.cleanup_failed
            retained = coordinator.original
            assert retained is not None and retained.fence == issued.fence
            assert retained.record.lease_generation == 1
            assert issued.event not in failure_persistence._EVENTS and issued.record.event is None
            assert not failure_terminal._TERMINALS
            after = whole_state(case)
            assert_same_state(issued.claimed, after)
            assert_no_canary(caught.value, after)
            observer = failure_terminal.TerminalCoordinator(case.engine, case.authority)
            with pytest.raises(AdmissionError) as consumed:
                observer.complete_failure(case.principal, case.context, issued.event)
            assert (consumed.value.reason, consumed.value.code) == (
                "capability_not_issued",
                "invalid_request",
            )
            assert not any(asdict(observer.outcome).values()) and observer.original is None
            assert coordinator.original is retained
            assert_same_state(after, whole_state(case))
            record_terminal_refusal_work(
                coordinator,
                controls,
                elapsed,
                record_property,
                fault="actual_deferred_generation",
                transient_native_generations=transient,
                actual_flush_statements=flush_statements,
                actual_sqlstates=flush_errors,
                protected_writes=writes,
                original_retained=True,
                exact_rollback=True,
            )


def test_terminal_conditional_update_refuses_same_body_generation_drift(
    failure_case, monkeypatch, record_property
):
    case = failure_case.case
    controls = observe_controls(monkeypatch)
    with genuine_terminal_event(case, controls, record_property) as issued:
        coordinator = failure_terminal.TerminalCoordinator(case.engine, case.authority)
        execute = Connection.execute
        injected, conditional, inserts = [], [], []

        def drift_before_update(connection, statement, *args, **kwargs):
            table_name = getattr(getattr(statement, "table", None), "name", None)
            selected = connection.engine is case.engine
            if selected and getattr(statement, "is_insert", False) and table_name == EVIDENCE:
                inserts.append("evidence")
            if selected and getattr(statement, "is_update", False) and table_name == "jobs":
                assert injected == [] and coordinator.original is not None
                generation = issued.fence.generation + 1
                result = execute(
                    connection,
                    text(
                        "UPDATE jobs SET lease_generation=:generation WHERE id=:id "
                        "RETURNING lease_generation"
                    ),
                    {"generation": generation, "id": case.job_id},
                )
                observed = result.scalar_one()
                assert type(observed) is int and observed == generation
                injected.append(observed)
                # Forward the actual conditional statement and its actual result.
                changed = execute(connection, statement, *args, **kwargs)
                conditional.append(changed.rowcount)
                native = execute(
                    connection,
                    text("SELECT status,lease_generation FROM jobs WHERE id=:id"),
                    {"id": case.job_id},
                ).one()
                assert tuple(native) == ("running", generation)
                assert (
                    execute(
                        connection,
                        text("SELECT count(*) FROM job_failure_evidence WHERE job_id=:id"),
                        {"id": case.job_id},
                    ).scalar_one()
                    == 0
                )
                return changed
            return execute(connection, statement, *args, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(Connection, "execute", drift_before_update)
            started = time.monotonic()
            with pytest.raises(AdmissionError) as caught:
                coordinator.complete_failure(case.principal, case.context, issued.event)
            elapsed = time.monotonic() - started
        assert injected == [issued.fence.generation + 1]
        assert conditional == [0] and inserts == []
        assert (caught.value.reason, caught.value.code) == (
            "stale_source",
            "dependency_unavailable",
        )
        facts = coordinator.outcome
        assert facts.begun and not facts.commit_attempted and not facts.commit_acknowledged
        assert facts.rollback_attempted and facts.rollback_acknowledged and not facts.cleanup_failed
        retained = coordinator.original
        assert retained is not None and retained.fence == issued.fence
        assert retained.record.lease_generation == issued.fence.generation
        assert issued.event not in failure_persistence._EVENTS and issued.record.event is None
        assert not failure_terminal._TERMINALS
        after = whole_state(case)
        assert_same_state(issued.claimed, after)
        assert_no_canary(caught.value, after)
        observer = failure_terminal.TerminalCoordinator(case.engine, case.authority)
        with pytest.raises(AdmissionError) as consumed:
            observer.complete_failure(case.principal, case.context, issued.event)
        assert (consumed.value.reason, consumed.value.code) == (
            "capability_not_issued",
            "invalid_request",
        )
        assert not any(asdict(observer.outcome).values()) and observer.original is None
        assert coordinator.original is retained
        assert_same_state(after, whole_state(case))
        record_terminal_refusal_work(
            coordinator,
            controls,
            elapsed,
            record_property,
            fault="same_body_conditional_generation",
            actual_injected_generation=injected,
            actual_conditional_rowcounts=conditional,
            evidence_insert_attempts=inserts,
            original_retained=True,
            exact_rollback=True,
        )


def test_terminal_expiry_writers_exclude_one_native_outcome(
    failure_case, monkeypatch, record_property
):
    import sqlite3
    from concurrent.futures import ThreadPoolExecutor
    from dataclasses import replace
    from threading import Event, get_ident

    case = failure_case.case
    postgres = case.engine.dialect.name == "postgresql"
    controls = observe_controls(monkeypatch)
    before_claim = whole_state(case)
    short_intent = replace(claim_intent(case), lease_seconds=1)
    adapter = InstalledAdapter()
    with execution_owner(case, adapter) as (owner, record):
        before_tick = native_clock(case)
        started = time.monotonic()
        fence = owner.claim(case.principal, case.context, short_intent)
        claim_elapsed = time.monotonic() - started
        after_tick = native_clock(case)
        claimed = whole_state(case)
        assert_only_claim_changed(before_claim, claimed, short_intent, (before_tick, after_tick))
        assert owner.outcome.commit_acknowledged and not owner.outcome.cleanup_failed
        claim_work = record.work
        assert claim_work is record.coordinator._work and claim_work._detached
        claim_cleanup = [
            item
            for item in controls
            if item[0] is claim_work and item[1] not in {"begin", "commit"}
        ]
        assert claim_work.statements <= 512 and claim_work.statements - len(claim_cleanup) <= 504
        assert len(claim_cleanup) <= 8 and claim_elapsed < 10
    job = next(row for row in claimed["tables"]["jobs"]["rows"] if row["id"] == case.job_id)
    numerator, denominator = job["lease_until"].as_integer_ratio()
    cadence = Event()
    poll_started = time.monotonic()
    while True:
        expired_tick = native_clock(case)
        if expired_tick * denominator >= numerator * 1_000_000:
            break
        assert time.monotonic() - poll_started < 4
        cadence.wait(0.01)
    assert_same_state(claimed, whole_state(case))
    native_inputs = native_digest_inputs(case)
    first = failure_terminal.TerminalCoordinator(case.engine, case.authority)
    second = failure_terminal.TerminalCoordinator(case.engine, case.authority)
    coordinators = {"winner": first, "loser": second}
    actors, pids, results, elapsed = {}, {}, {}, {}
    writes = {"winner": [], "loser": []}
    first_locked, second_started, release = Event(), Event(), Event()
    busy_codes, blockers_observed = [], []
    persist = failure_terminal.persist_verified_failure
    lock_authority = failure_terminal.lock_authority
    execute, execute_sql = Connection.execute, Connection.exec_driver_sql

    def actor_lock(connection_authority, connection, *args, **kwargs):
        actor = actors[get_ident()]
        if postgres:
            pids[actor] = connection.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
            if actor == "loser":
                second_started.set()
        return lock_authority(connection_authority, connection, *args, **kwargs)

    def held_persist(connection, token):
        actor = actors[get_ident()]
        if actor == "winner":
            first_locked.set()
            assert release.wait(5), "bounded terminal winner rendezvous expired"
        return persist(connection, token)

    def observed_execute(connection, statement, *args, **kwargs):
        actor = actors.get(get_ident())
        table_name = getattr(getattr(statement, "table", None), "name", None)
        selected = (
            connection.engine is case.engine
            and actor is not None
            and (
                getattr(statement, "is_update", False)
                and table_name == "jobs"
                or getattr(statement, "is_insert", False)
                and table_name == EVIDENCE
            )
        )
        result = execute(connection, statement, *args, **kwargs)
        if selected:
            writes[actor].append({"table": table_name, "rowcount": result.rowcount})
        return result

    def observed_sql(connection, statement, *args, **kwargs):
        actor = actors.get(get_ident())
        if not postgres and actor == "loser" and statement == "BEGIN IMMEDIATE":
            second_started.set()
        try:
            return execute_sql(connection, statement, *args, **kwargs)
        except Exception as error:
            if not postgres and actor == "loser" and statement == "BEGIN IMMEDIATE":
                busy_codes.append(getattr(getattr(error, "orig", None), "sqlite_errorcode", None))
            raise

    def attempt(actor):
        actors[get_ident()] = actor
        started = time.monotonic()
        try:
            try:
                result = coordinators[actor].expire_generation(case.principal, case.context, fence)
                results[actor] = {"value": result, "error": None}
            except AdmissionError as error:
                results[actor] = {"value": None, "error": error}
        finally:
            elapsed[actor] = time.monotonic() - started
            actors.pop(get_ident())

    with monkeypatch.context() as patch:
        patch.setattr(failure_terminal, "lock_authority", actor_lock)
        patch.setattr(failure_terminal, "persist_verified_failure", held_persist)
        patch.setattr(Connection, "execute", observed_execute)
        patch.setattr(Connection, "exec_driver_sql", observed_sql)
        with ThreadPoolExecutor(max_workers=2) as executor:
            winner_future = executor.submit(attempt, "winner")
            try:
                assert first_locked.wait(3)
                loser_future = executor.submit(attempt, "loser")
                assert second_started.wait(2)
                if postgres:
                    assert pids["winner"] != pids["loser"]
                    deadline = time.monotonic() + 2
                    with case.pg["owner"].connect() as observer:
                        while time.monotonic() < deadline and not loser_future.done():
                            blocked = observer.execute(
                                text("SELECT pg_blocking_pids(:pid)"), {"pid": pids["loser"]}
                            ).scalar_one()
                            if pids["winner"] in blocked:
                                blockers_observed.append(list(blocked))
                                break
                            cadence.wait(0.01)
                    assert blockers_observed, "second terminal writer was never natively blocked"
                    assert not loser_future.done()
                else:
                    loser_future.result(timeout=5)
                    assert busy_codes == [sqlite3.SQLITE_BUSY]
                release.set()
                winner_future.result(timeout=6)
                loser_future.result(timeout=6)
            finally:
                release.set()
        assert winner_future.done() and loser_future.done()
    assert set(results) == {"winner", "loser"}
    assert results["winner"]["error"] is None and type(results["winner"]["value"]) is CreatedFailure
    created = results["winner"]["value"]
    failure = results["loser"]["error"]
    assert results["loser"]["value"] is None and isinstance(failure, AdmissionError)
    assert failure.code == "dependency_unavailable"
    if postgres:
        assert failure.reason == "not_eligible"
        assert second.outcome.begun and second.outcome.rollback_acknowledged
    else:
        assert not second.outcome.begun
    assert not second.outcome.commit_attempted and not second.outcome.commit_acknowledged
    assert second.original is None
    assert first.outcome.commit_acknowledged and not first.outcome.cleanup_failed
    assert writes == {
        "winner": [{"table": "jobs", "rowcount": 1}, {"table": EVIDENCE, "rowcount": 1}],
        "loser": [],
    }
    original = created.original
    assert original is first.original and original.fence == fence
    assert (original.record.cause, original.record.job_status, original.record.phase) == (
        "lease_expired",
        "failed",
        "outcome_unknown",
    )
    after_tick = native_clock(case)
    assert expired_tick <= original.record.created_at_micros <= after_tick
    expected = deepcopy(claimed)
    next(row for row in expected["tables"]["jobs"]["rows"] if row["id"] == case.job_id)[
        "status"
    ] = "failed"
    assert expected["tables"][EVIDENCE]["rows"] == []
    expected["tables"][EVIDENCE]["rows"] = [asdict(original.record)]
    after = whole_state(case)
    assert_same_state(expected, after)
    assert (original.record.association_sha256, original.record.source_sha256) == (
        expected_failure_hashes(case, after, original.record, native_inputs)
    )
    assert_no_canary(failure, after)
    assert not failure_terminal._TERMINALS and case.engine.pool.checkedout() == 0
    observations = {}
    for actor, coordinator in coordinators.items():
        work = coordinator._work
        cleanup = [
            item for item in controls if item[0] is work and item[1] not in {"begin", "commit"}
        ]
        assert work._detached and not work._listeners and work._connection is None
        assert work.statements <= 512 and work.statements - len(cleanup) <= 504
        assert len(cleanup) <= 8 and elapsed[actor] < 10 and work.instructions < 20_000_000
        observations[actor] = {
            "outcome": asdict(coordinator.outcome),
            "total_units": work.statements,
            "ordinary_units": work.statements - len(cleanup),
            "cleanup_units": len(cleanup),
            "elapsed_seconds": elapsed[actor],
            "vm_instructions": work.instructions,
        }
    record_property(
        "f3_terminal_writer_race",
        json.dumps(
            {
                "native_sqlite_busy": busy_codes,
                "native_postgres_pids": pids,
                "native_postgres_blockers": blockers_observed,
                "first_observed_expired_tick": expired_tick,
                "unchanged_native_lease": repr(job["lease_until"]),
                "winner_created_at_micros": original.record.created_at_micros,
                "protected_writes": writes,
                "observations": observations,
                "single_exact_evidence_row": True,
                "no_second_terminal_write": True,
                "scope": "Internal participating terminal coordinators; not live caller wiring.",
            },
            sort_keys=True,
        ),
    )


@pytest.mark.parametrize("receiver_mode", ["idle", "active"])
def test_terminal_scope_refuses_bare_and_foreign_connection(
    failure_case, monkeypatch, record_property, receiver_mode
):
    case = failure_case.case
    controls = observe_controls(monkeypatch)
    persist = failure_terminal.persist_verified_failure
    with genuine_terminal_event(case, controls, record_property) as issued:
        coordinator = failure_terminal.TerminalCoordinator(case.engine, case.authority)
        borrowed, source_connections, receiver_controls = [], [], []
        with monkeypatch.context() as patch:
            writes = observe_terminal_writes(patch, case)
            with case.engine.connect() as receiver:
                raw = receiver.connection.driver_connection
                postgres = receiver.dialect.name == "postgresql"
                assert receiver.get_transaction() is None
                assert (
                    raw.info.transaction_status.name == "IDLE"
                    if postgres
                    else not raw.in_transaction
                )
                if receiver_mode == "active":
                    receiver.exec_driver_sql(
                        "BEGIN ISOLATION LEVEL READ COMMITTED READ ONLY" if postgres else "BEGIN"
                    )
                    assert receiver.exec_driver_sql("SELECT 1").scalar_one() == 1
                    receiver_controls.append("BEGIN")
                receiver_root = receiver.get_transaction()
                active = receiver_mode == "active"
                assert (receiver_root is not None) is active
                assert (
                    raw.info.transaction_status.name == ("INTRANS" if active else "IDLE")
                    if postgres
                    else raw.in_transaction is active
                )
                # The idle witness uses native properties only, never diagnostic SQL.
                with pytest.raises(AdmissionError) as bare:
                    persist(receiver, object())
                assert (bare.value.reason, bare.value.code) == (
                    "capability_not_issued",
                    "invalid_request",
                )
                assert receiver.get_transaction() is receiver_root
                assert receiver not in failure_terminal._TERMINALS and writes == []

                def forward_to_foreign(connection, token):
                    assert borrowed == [] and connection.engine is receiver.engine
                    assert connection is not receiver
                    assert connection.connection.driver_connection is not raw
                    source_root = connection.get_transaction()
                    assert source_root is not None and source_root.is_active
                    assert source_root is not receiver_root
                    assert failure_terminal._TERMINALS[connection][0] is token
                    assert receiver not in failure_terminal._TERMINALS
                    assert receiver.get_transaction() is receiver_root
                    assert (
                        raw.info.transaction_status.name == ("INTRANS" if active else "IDLE")
                        if postgres
                        else raw.in_transaction is active
                    )
                    borrowed.append(
                        {
                            "actual_issued_token": True,
                            "distinct_connection_and_native_driver": True,
                            "receiver_native_active": active,
                            "receiver_logical_active": receiver_root is not None,
                        }
                    )
                    source_connections.append(connection)
                    return persist(receiver, token)

                patch.setattr(failure_terminal, "persist_verified_failure", forward_to_foreign)
                started = time.monotonic()
                with pytest.raises(AdmissionError) as caught:
                    coordinator.complete_failure(case.principal, case.context, issued.event)
                elapsed = time.monotonic() - started
                assert (caught.value.reason, caught.value.code) == (
                    "capability_not_issued",
                    "invalid_request",
                )
                assert len(borrowed) == len(source_connections) == 1
                assert source_connections[0].closed
                assert receiver.get_transaction() is receiver_root
                assert (
                    raw.info.transaction_status.name == ("INTRANS" if active else "IDLE")
                    if postgres
                    else raw.in_transaction is active
                )
                if active:
                    receiver.rollback()
                    receiver_controls.append("ROLLBACK")
                assert receiver.get_transaction() is None
                assert (
                    raw.info.transaction_status.name == "IDLE"
                    if postgres
                    else not raw.in_transaction
                )
            assert receiver.closed
        assert receiver_controls == (["BEGIN", "ROLLBACK"] if active else [])
        assert not coordinator.outcome.cleanup_failed
        assert_terminal_refusal_state(
            case, issued, coordinator, caught.value, issued.claimed, writes
        )
        record_terminal_refusal_work(
            coordinator,
            controls,
            elapsed,
            record_property,
            fault="unissued_and_foreign_terminal_scope",
            receiver_mode=receiver_mode,
            bare_entry_refused=True,
            genuine_token_forwarding=borrowed,
            receiver_injected_controls=receiver_controls,
            receiver_closed=True,
            source_closed=True,
            protected_writes=writes,
        )
