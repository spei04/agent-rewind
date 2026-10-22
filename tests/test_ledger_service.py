"""Authored service controls using real predecessor history and persisted results."""

import pytest
from ledger_fixture import identifier
from ledger_reader_fixture import complete_ar6, original_rows, sqlite_snapshot
from sqlalchemy import text

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.ledger_inspection import inspect_ledger_state
from agent_rewind.migrations.ledger_transaction import LedgerOutcome, ledger_transaction
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import LEDGER, MigrationRefused, catalog, checksum


def intent(case, *, empty=False):
    with case.engine.connect() as connection:
        organization = connection.exec_driver_sql("SELECT id FROM organizations").scalar_one()
        jobs = list(
            connection.exec_driver_sql(
                "SELECT j.id,j.budget,j.reserved,s.project_id FROM jobs j "
                "JOIN resource_scopes s ON s.resource_kind='job' AND s.resource_id=j.id "
                "ORDER BY j.id"
            ).mappings()
        )

    def account(number, scope, scope_id, project=None, job=None, limit=1_000_000):
        return {
            "id": identifier(number),
            "organization_id": organization,
            "scope": scope,
            "scope_id": scope_id,
            "project_id": project,
            "job_id": job,
            "period_start": "2000-01-01T00:00:00.000000Z",
            "period_end": "2100-01-01T00:00:00.000000Z",
            "limit_microusd": limit,
        }

    projects = sorted({row["project_id"] for row in jobs})
    accounts = [] if empty else [account(10_000, "organization", organization)]
    accounts += [
        account(20_000 + index, "project", value, project=value)
        for index, value in enumerate(projects)
    ]
    accounts += [
        account(
            30_000 + index,
            "job",
            row["id"],
            project=row["project_id"],
            job=row["id"],
            limit=row["budget"],
        )
        for index, row in enumerate(jobs)
    ]
    return {
        "schema_version": 1,
        "installation_key": case.adoption["installation_key"],
        "manifest_id": identifier(1_000_000),
        "operation": "initialize",
        "source_digest": case.original_digest,
        "parent_manifest_digest": None,
        "backup_evidence_digest": "2" * 64,
        "drain_evidence_digest": "3" * 64,
        "accounts": accounts,
        "opening_accounts": {
            "organization_account_id": None if empty else identifier(10_000),
            "projects": [
                {"project_id": value, "account_id": identifier(20_000 + index)}
                for index, value in enumerate(projects)
            ],
        },
    }


def inspect(case):
    engine = case.operator_engine()
    try:
        with ledger_transaction(engine, LedgerOutcome(), work=LedgerWork()) as connection:
            return inspect_ledger_state(connection)
    finally:
        engine.dispose()


def invoke(case, raw):
    engine = case.operator_engine()
    try:
        return ledger_service.initialize_ledger(engine, validate_ledger_manifest(raw))
    finally:
        engine.dispose()


@pytest.mark.parametrize("legacy,empty", [(False, True), (False, False), (True, False)])
def test_actual_initialize_preserves_original_history(tmp_path, legacy, empty):
    case = complete_ar6(tmp_path / "service.sqlite", legacy=legacy)
    try:
        raw = intent(case, empty=empty)
        receipt = invoke(case, raw)
        state = inspect(case)
        assert receipt.outcome == "complete"
        assert receipt.manifest_id == raw["manifest_id"]
        assert receipt.manifest_digest == validate_ledger_manifest(raw).digest
        assert state.head.manifest_digest == receipt.manifest_digest
        assert state.status == "complete" and state.manifest_count == 1
        assert state.account_count == len(raw["accounts"])
        assert state.opening.organization_opening_microusd == (245000 if legacy else 0)
        assert receipt.imported_opening_microusd == (245000 if legacy else 0)
        assert original_rows(case.engine) == case.original_rows
        with case.engine.connect() as connection:
            adoption = dict(
                connection.exec_driver_sql("SELECT * FROM installation_adoptions").mappings().one()
            )
            assert adoption["installed_schema_fingerprint"] == checksum(catalog(connection))
            assert {
                key: value
                for key, value in adoption.items()
                if key != "installed_schema_fingerprint"
            } == {
                key: value
                for key, value in case.adoption.items()
                if key != "installed_schema_fingerprint"
            }
            prior = [
                tuple(row)
                for row in connection.execute(
                    text(
                        "SELECT * FROM migration_progress WHERE revision<>:revision "
                        "ORDER BY revision,phase"
                    ),
                    {"revision": LEDGER},
                )
            ]
            assert prior == case.previous_progress
            accounts = list(
                connection.exec_driver_sql(
                    "SELECT opening_held_microusd,held_microusd,accounted_microusd "
                    "FROM budget_accounts"
                )
            )
            assert all(opening == held and accounted == 0 for opening, held, accounted in accounts)
            if legacy:
                assert sum(value[0] for value in accounts) == 3 * 245000
    finally:
        case.dispose()


def test_older_exact_replay_never_rehashes_or_writes(tmp_path, monkeypatch):
    case = complete_ar6(tmp_path / "service.sqlite")
    try:
        raw = intent(case)
        original = invoke(case, raw)
        provision = {
            **raw,
            "manifest_id": identifier(1_000_001),
            "operation": "provision",
            "parent_manifest_digest": original.manifest_digest,
            "opening_accounts": None,
            "accounts": [
                {
                    **raw["accounts"][0],
                    "id": identifier(40_000),
                    "period_start": "2100-01-01T00:00:00.000000Z",
                    "period_end": "2200-01-01T00:00:00.000000Z",
                }
            ],
        }
        second = invoke(case, provision)
        assert second.sequence == 1 and second.imported_jobs == 0
        before = sqlite_snapshot(case.path)
        monkeypatch.setattr(
            ledger_service,
            "source_digest",
            lambda *args: pytest.fail("exact replay must not hash current source"),
        )
        replay = invoke(case, raw)
        assert replay == original
        assert sqlite_snapshot(case.path) == before
        assert inspect(case).head.manifest_digest == second.manifest_digest
    finally:
        case.dispose()


@pytest.mark.parametrize("marker", ["future", "missing", "nonfinite"])
def test_actual_legacy_lease_refusal_preserves_entire_predecessor(tmp_path, monkeypatch, marker):
    from agent_rewind.migrations.inputs import source_digest

    case = complete_ar6(tmp_path / "service.sqlite", legacy=True)
    try:
        with case.engine.begin() as connection:
            value = {"future": 253402300799.0, "missing": None, "nonfinite": float("inf")}[marker]
            connection.execute(
                text("UPDATE jobs SET lease_until=:value WHERE id=:id"),
                {"value": value, "id": case.original_rows["jobs"][0][0]},
            )
        if marker != "nonfinite":
            with case.engine.connect() as connection:
                case.original_digest = source_digest(connection)
        before = sqlite_snapshot(case.path)
        phases = []
        original = ledger_service._execute

        def execute(connection, name, values=None):
            phases.append(name)
            return original(connection, name, values)

        monkeypatch.setattr(ledger_service, "_execute", execute)
        with pytest.raises(MigrationRefused, match="^ledger_history_unsupported$"):
            invoke(case, intent(case))
        assert sqlite_snapshot(case.path) == before
        assert "progress.insert" not in phases
        if marker == "future":
            assert phases.count("provenance.observe") == 1
            assert "accounts.insert" in phases
        else:
            assert "accounts.insert" not in phases
    finally:
        case.dispose()


def test_actual_terminal_null_owner_and_expired_deadline_is_preserved(tmp_path):
    from agent_rewind.migrations.inputs import source_digest

    case = complete_ar6(tmp_path / "service.sqlite", legacy=True)
    try:
        with case.engine.begin() as connection:
            connection.exec_driver_sql("UPDATE jobs SET owner=NULL")
        before = original_rows(case.engine)
        with case.engine.connect() as connection:
            case.original_digest = source_digest(connection)
        receipt = invoke(case, intent(case))
        assert receipt.imported_opening_microusd == 245000
        assert original_rows(case.engine) == before
    finally:
        case.dispose()


@pytest.mark.parametrize(
    "stage", ["accounts.insert", "progress.insert", "adoption.publish_fingerprint"]
)
def test_actual_staged_write_failure_rolls_back_before_publication(tmp_path, monkeypatch, stage):
    case = complete_ar6(tmp_path / "service.sqlite")
    try:
        raw, before = intent(case), sqlite_snapshot(case.path)
        original = ledger_service._write
        visits = []

        def write(connection, name, values):
            original(connection, name, values)
            visits.append(name)
            if name == stage:
                raise MigrationRefused("migration_busy")

        monkeypatch.setattr(ledger_service, "_write", write)
        with pytest.raises(MigrationRefused, match="^migration_busy$"):
            invoke(case, raw)
        assert visits.count(stage) == 1
        assert sqlite_snapshot(case.path) == before
        monkeypatch.setattr(ledger_service, "_write", original)
        assert inspect(case).status == "absent"
    finally:
        case.dispose()


def test_second_real_fingerprint_mismatch_rolls_back_all_staging(tmp_path, monkeypatch):
    case = complete_ar6(tmp_path / "service.sqlite")
    try:
        raw, before = intent(case), sqlite_snapshot(case.path)
        original = ledger_service.source_digest
        observed = []

        def changed(connection, work):
            digest = original(connection, work)
            observed.append(digest)
            return "f" * 64 if len(observed) == 2 else digest

        monkeypatch.setattr(ledger_service, "source_digest", changed)
        with pytest.raises(MigrationRefused, match="^source_digest_mismatch$"):
            invoke(case, raw)
        assert observed == [case.original_digest, case.original_digest]
        assert sqlite_snapshot(case.path) == before
    finally:
        case.dispose()


@pytest.mark.parametrize("commit_happened", [False, True])
def test_explicit_fresh_reentry_classifies_after_commit_uncertainty(
    tmp_path, monkeypatch, commit_happened
):
    from sqlalchemy.engine import Connection

    case = complete_ar6(tmp_path / "service.sqlite")
    engine = case.operator_engine()
    try:
        checked = validate_ledger_manifest(intent(case))
        original = Connection.commit
        attempts = []

        def commit(connection):
            if connection.engine is engine:
                attempts.append("attempt")
                if commit_happened:
                    original(connection)
                raise RuntimeError("controlled lost acknowledgement")
            return original(connection)

        monkeypatch.setattr(Connection, "commit", commit)
        with pytest.raises(MigrationRefused, match="^ledger_outcome_uncertain$"):
            ledger_service.initialize_ledger(engine, checked)
        assert attempts == ["attempt"]
        monkeypatch.setattr(Connection, "commit", original)
        engine.dispose()
        fresh = case.operator_engine()
        try:
            receipt = ledger_service._inspect_ledger_reentry(fresh, checked)
        finally:
            fresh.dispose()
        if commit_happened:
            assert receipt.manifest_digest == checked.digest
            assert inspect(case).status == "complete"
        else:
            assert receipt is None and inspect(case).status == "absent"
    finally:
        engine.dispose()
        case.dispose()


@pytest.mark.parametrize("timeout", [True, 0, 31, 1.0])
def test_native_timeout_refuses_before_checkout(timeout):
    from ledger_fixture import manifest

    with pytest.raises(MigrationRefused, match="^invalid_lock_timeout$"):
        ledger_service.initialize_ledger(
            object(), validate_ledger_manifest(manifest(empty=True)), timeout_seconds=timeout
        )


def test_constructed_manifest_is_revalidated_before_checkout():
    from ledger_fixture import manifest

    forged = validate_ledger_manifest(manifest(empty=True)).model_copy(
        update={"source_digest": "invalid"}
    )
    with pytest.raises(MigrationRefused, match="^invalid_ledger_manifest$"):
        ledger_service.initialize_ledger(object(), forged)


def test_one_work_pays_both_proofs_hashes_writes_commit_and_cleanup(tmp_path, monkeypatch, request):
    import json
    import sqlite3

    from ledger_operator_fixture import SQLiteTrace

    case = complete_ar6(tmp_path / "service.sqlite", legacy=True)
    try:
        raw = intent(case)
        observed = []
        trace = SQLiteTrace()
        monkeypatch.setattr(sqlite3, "connect", trace.connect)
        original = ledger_service.LedgerWork

        def work(timeout_seconds):
            value = original(timeout_seconds)
            observed.append(value)
            return value

        monkeypatch.setattr(ledger_service, "LedgerWork", work)
        receipt = invoke(case, raw)
        assert receipt.imported_opening_microusd == 245000
        assert len(observed) == 1
        work = observed[0]
        assert (work.prepaid_bootstrap, work.prepaid_cleanup) == (12, 8)
        assert 0 < work.observed_ordinary <= 2028 and work._detached
        sql = trace.sql()
        assert sum(value == "COMMIT" for value in sql) == 1
        assert not any(value.startswith(("SAVEPOINT", "ROLLBACK TO")) for value in sql)
        request.node.user_properties.append(
            (
                "writer_work",
                json.dumps(
                    {
                        "ordinary": work.observed_ordinary,
                        "cleanup": work.cleanup_observations,
                        "native_sql": len(sql),
                        "timeout_seconds": work.timeout_seconds,
                    }
                ),
            )
        )
    finally:
        case.dispose()
