"""Native SQLite service/publication boundaries for the dormant ar8 installation."""

import importlib
import json
import sqlite3
import time
from contextlib import closing, contextmanager
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from ledger_reader_fixture import complete_ar6, seed_ar7, sqlite_snapshot
from pydantic import ValidationError
from sqlalchemy import event
from sqlalchemy.engine import Connection
from test_failure_schema import rows
from test_ledger_service import intent, invoke

from agent_rewind.migrations import failure_schema
from agent_rewind.migrations import failure_service as service
from agent_rewind.migrations.compatibility import (
    check_schema_compatibility,
    load_release_profile,
    runtime_schema_compatibility,
)
from agent_rewind.migrations.failure_catalog import inspect_failure_catalog
from agent_rewind.migrations.failure_transaction import failure_transaction
from agent_rewind.migrations.ledger_transaction import LedgerOutcome
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import FAILURE, LEDGER, MigrationRefused, checksum


@pytest.fixture
def predecessor(tmp_path):
    case = seed_ar7(complete_ar6(tmp_path / "failure-service.sqlite", legacy=False))
    try:
        yield case
    finally:
        case.dispose()


def key(case):
    return case.adoption["installation_key"]


def call(case, *, initialize=False, installation_key=None, sql=None):
    engine = case.operator_engine()
    target = service.initialize_failure_evidence if initialize else service.inspect_failure_evidence
    expected_key = key(case) if installation_key is None else installation_key
    try:
        if sql is None:
            return target(engine, installation_key=expected_key)
        # Attested engines forbid new event callbacks. Observe forwarding calls
        # without changing that callback identity or bypassing any native work.
        original_execute = Connection.execute
        original_driver = Connection.exec_driver_sql

        def execute(connection, statement, *args, **kwargs):
            if connection.engine is engine:
                sql.append(str(statement))
            return original_execute(connection, statement, *args, **kwargs)

        def driver(connection, statement, *args, **kwargs):
            if connection.engine is engine:
                sql.append(statement)
            return original_driver(connection, statement, *args, **kwargs)

        with (
            patch.object(Connection, "execute", execute),
            patch.object(Connection, "exec_driver_sql", driver),
        ):
            return target(engine, installation_key=expected_key)
    finally:
        engine.dispose()


def native_rows(case):
    with case.engine.connect() as connection:
        return rows(connection)


def native_revision(case):
    with closing(sqlite3.connect(case.path)) as raw:
        return raw.execute("SELECT version_num FROM alembic_version").fetchall()


@pytest.fixture
def observations(monkeypatch):
    captured = []
    original = service.failure_transaction

    @contextmanager
    def observe(engine, outcome, *, work):
        record = {"work": work, "outcome": outcome}
        captured.append(record)
        with original(engine, outcome, work=work) as connection:
            record["connection"] = connection
            yield connection

    monkeypatch.setattr(service, "failure_transaction", observe)
    return captured


@pytest.mark.parametrize("legacy", [False, True], ids=["fresh", "legacy"])
def test_actual_service_upgrade_preserves_history_and_reentry_is_read_only(
    tmp_path, legacy, observations, record_property
):
    # The predecessor is initialized by the real ar7 service, not a revised stamp.
    case = complete_ar6(tmp_path / "real-service.sqlite", legacy=legacy)
    try:
        invoke(case, intent(case, empty=not legacy))
        before = native_rows(case)
        absent = call(case)
        assert absent.status == "absent" and absent.revision == LEDGER
        assert absent.catalog_profile == "ledger_v1"
        assert absent.retained_ar7.status == "complete"
        assert native_rows(case) == before
        result = call(case, initialize=True)
        assert result.status == "complete" and result.outcome == "complete"
        assert result.revision == FAILURE and result.catalog_profile == "failure_evidence_v1"
        assert result.retained_ar7 == absent.retained_ar7
        assert result.installation_key == key(case)
        after = native_rows(case)
        assert after == before | {
            "alembic_version": [(FAILURE,)],
            "job_failure_evidence": [],
        }
        assert after["installation_adoptions"] == before["installation_adoptions"]
        assert after["migration_progress"] == before["migration_progress"]
        assert native_revision(case) == [(FAILURE,)]
        engine = case.operator_engine()
        try:
            work = LedgerWork()
            with failure_transaction(engine, LedgerOutcome(), work=work) as connection:
                observed = inspect_failure_catalog(connection, work)
                assert result.installed_profile_sha256 == checksum(observed.catalog)
                assert absent.installed_profile_sha256 == checksum(observed.retained_ar7)
                assert result.installed_profile_sha256 != absent.installed_profile_sha256
        finally:
            engine.dispose()
        sql = []
        # Separate public invocations use their own issued engines and outcomes.
        inspected = call(case, sql=sql)
        replay = call(case, initialize=True, sql=sql)
        assert not any(
            statement.lstrip()
            .upper()
            .startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP"))
            for statement in sql
        )
        assert inspected == service.FailureState.model_validate(
            result.model_dump(mode="json", exclude={"outcome"})
        )
        assert replay == result
        assert native_rows(case) == after
        assert not service._UPGRADES
        assert all(item["outcome"].commit_acknowledged for item in observations)
        assert all(not item["outcome"].cleanup_failed for item in observations)
        record_property(
            "whole_offline_work",
            json.dumps(
                [
                    {
                        "ordinary": item["work"].observed_ordinary,
                        "bootstrap": item["work"].prepaid_bootstrap,
                        "cleanup_reserved": item["work"].prepaid_cleanup,
                        "cleanup_observed": item["work"].cleanup_observations,
                    }
                    for item in observations
                ],
                sort_keys=True,
            ),
        )
    finally:
        case.dispose()


@pytest.mark.parametrize("bad", [None, True, 1, "", "é", "x" * 65, "bad/key"])
def test_invalid_key_refuses_before_checkout(bad):
    with pytest.raises(MigrationRefused, match="^invalid_installation_key$"):
        service.initialize_failure_evidence(object(), installation_key=bad)
    with pytest.raises(MigrationRefused, match="^invalid_installation_key$"):
        service.inspect_failure_evidence(object(), installation_key=bad)


@pytest.mark.parametrize("bad", [True, 0, 31, 1.0])
def test_invalid_timeout_refuses_before_checkout(bad):
    with pytest.raises(MigrationRefused, match="^invalid_lock_timeout$"):
        service.initialize_failure_evidence(
            object(), installation_key="expected", timeout_seconds=bad
        )


@pytest.mark.parametrize("initialize", [False, True])
def test_key_mismatch_never_writes(predecessor, initialize, observations):
    before = sqlite_snapshot(predecessor.path)
    with pytest.raises(MigrationRefused, match="^installation_key_mismatch$"):
        call(predecessor, initialize=initialize, installation_key="other-installation")
    assert sqlite_snapshot(predecessor.path) == before
    outcome = observations[-1]["outcome"]
    assert outcome.confirmed_precommit_rollback and not outcome.commit_attempted
    assert not service._UPGRADES


@pytest.mark.parametrize(
    "field,value",
    [
        ("revision", FAILURE),
        ("catalog_profile", "failure_evidence_v1"),
        ("status", "complete"),
        ("installation_key", "different"),
    ],
)
def test_state_cannot_mislabel_retained_predecessor(predecessor, field, value):
    state = call(predecessor)
    assert service.FailureState.model_validate(state.model_dump(mode="json")) == state
    with pytest.raises(ValidationError):
        service.FailureState.model_validate(state.model_dump(mode="json") | {field: value})
    with pytest.raises(ValidationError):
        service.FailureInitialization.model_validate(
            state.model_dump(mode="json") | {"outcome": "complete"}
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "partial",
        "future",
        "missing_version",
        "duplicate_version",
        "fingerprint",
        "history",
        "extra",
    ],
)
def test_unsupported_installation_refuses_without_repair(predecessor, mutation):
    case = predecessor
    with case.engine.begin() as connection:
        if mutation == "partial":
            failure_schema.create_failure_schema(connection)
        elif mutation == "future":
            connection.exec_driver_sql("UPDATE alembic_version SET version_num='ar_future'")
        elif mutation == "missing_version":
            connection.exec_driver_sql("DELETE FROM alembic_version")
        elif mutation == "duplicate_version":
            connection.exec_driver_sql("INSERT INTO alembic_version VALUES('ar_future')")
        elif mutation == "fingerprint":
            connection.exec_driver_sql(
                "UPDATE installation_adoptions SET installed_schema_fingerprint=?", ("0" * 64,)
            )
        elif mutation == "history":
            connection.exec_driver_sql(
                "UPDATE migration_progress SET status='blocked' WHERE phase='ledger_opening'"
            )
        else:
            connection.exec_driver_sql("CREATE TABLE unknown_successor(value INTEGER)")
    before = sqlite_snapshot(case.path)
    with pytest.raises(MigrationRefused):
        call(case, initialize=True)
    assert sqlite_snapshot(case.path) == before
    assert not service._UPGRADES


@pytest.mark.parametrize("stage", ["after_ddl", "after_version", "fingerprint"])
def test_staged_upgrade_failure_rolls_back_ddl_version_and_history(
    predecessor, monkeypatch, stage, observations
):
    case = predecessor
    before = sqlite_snapshot(case.path)
    seen = []
    error = MigrationRefused("schema_incompatible")
    if stage == "after_ddl":
        original = failure_schema.create_failure_schema

        def create(connection):
            original(connection)
            seen.append(
                connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
            )
            raise error

        monkeypatch.setattr(failure_schema, "create_failure_schema", create)
    else:
        original = service._upgrade

        def upgrade(connection, work):
            original(connection, work)
            seen.append(
                connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
            )
            if stage == "fingerprint":
                connection.exec_driver_sql(
                    "UPDATE installation_adoptions SET installed_schema_fingerprint=?", ("0" * 64,)
                )
            else:
                raise error

        monkeypatch.setattr(service, "_upgrade", upgrade)
    with pytest.raises(MigrationRefused, match="^schema_incompatible$") as caught:
        call(case, initialize=True)
    if stage != "fingerprint":
        assert caught.value is error
    assert seen == [LEDGER if stage == "after_ddl" else FAILURE]
    assert sqlite_snapshot(case.path) == before
    assert observations[-1]["outcome"].confirmed_precommit_rollback
    assert not service._UPGRADES


@pytest.mark.parametrize("fault", ["before_commit", "after_commit", "close", "rollback"])
def test_publication_retains_uncertainty_and_fresh_inspection_is_not_retry(
    predecessor, monkeypatch, fault, observations
):
    case = predecessor
    before = sqlite_snapshot(case.path)
    engine = case.operator_engine()
    calls = []
    method = "close" if fault == "close" else "rollback" if fault == "rollback" else "commit"
    original = getattr(Connection, method)

    def fail(connection):
        if connection.engine is engine and not calls:
            calls.append(method)
            if fault == "after_commit":
                original(connection)
            raise RuntimeError("private-ack-canary")
        return original(connection)

    monkeypatch.setattr(Connection, method, fail)
    if fault == "rollback":
        original_upgrade = service._upgrade

        def force_rollback(connection, work):
            original_upgrade(connection, work)
            raise MigrationRefused("schema_incompatible")

        monkeypatch.setattr(service, "_upgrade", force_rollback)
    try:
        with pytest.raises(MigrationRefused, match="^ledger_outcome_uncertain$"):
            service.initialize_failure_evidence(engine, installation_key=key(case))
        outcome = observations[-1]["outcome"]
        assert calls == [method]
        assert not service._UPGRADES
        if fault == "close":
            assert outcome.commit_acknowledged and outcome.cleanup_failed
        else:
            assert not outcome.commit_acknowledged
        assert not outcome.confirmed_precommit_rollback
    finally:
        monkeypatch.setattr(Connection, method, original)
        engine.dispose()
    committed = fault in {"after_commit", "close"}
    visible = native_rows(case)
    state = call(case)
    assert state.status == ("complete" if committed else "absent")
    assert state.revision == (FAILURE if committed else LEDGER)
    assert native_rows(case) == visible  # inspection performs no repair/retry
    if not committed:
        assert sqlite_snapshot(case.path) == before


def test_thin_revision_requires_exact_live_upgrade_scope(predecessor):
    revision = importlib.import_module("agent_rewind.migrations.versions.0008_failure_evidence")
    assert revision.revision == FAILURE and revision.down_revision == LEDGER
    assert revision.branch_labels is None and revision.depends_on is None
    before = sqlite_snapshot(predecessor.path)
    engine = predecessor.operator_engine()
    try:
        with failure_transaction(engine, LedgerOutcome(), work=LedgerWork()) as connection:
            with pytest.raises(MigrationRefused, match="^transactional_connection_required$"):
                service._require_failure_upgrade(connection)
            config = Config()
            config.set_main_option("script_location", str(service.Path(service.__file__).parent))
            config.attributes.update(connection=connection, validated_operator=True)
            with pytest.raises(MigrationRefused, match="^transactional_connection_required$"):
                command.upgrade(config, FAILURE)
        with pytest.raises(MigrationRefused, match="^transactional_connection_required$"):
            service._require_failure_upgrade(connection)
        with pytest.raises(RuntimeError, match="verified restore"):
            revision.downgrade()
        assert sqlite_snapshot(predecessor.path) == before
        assert not service._UPGRADES
    finally:
        engine.dispose()


def test_nested_upgrade_and_interruption_revoke_scope(predecessor, monkeypatch, observations):
    error = KeyboardInterrupt("private-upgrade-interruption")
    seen = []

    def interrupt(config, target):
        connection = config.attributes["connection"]
        work = service._require_failure_upgrade(connection)
        seen.append((connection, work, target))
        with pytest.raises(MigrationRefused, match="^transactional_connection_required$"):
            service._upgrade(connection, work)
        assert service._require_failure_upgrade(connection) is work
        raise error

    monkeypatch.setattr(command, "upgrade", interrupt)
    before = sqlite_snapshot(predecessor.path)
    with pytest.raises(KeyboardInterrupt) as caught:
        call(predecessor, initialize=True)
    assert caught.value is error
    assert len(seen) == 1 and seen[0][2] == FAILURE
    assert observations[-1]["outcome"].confirmed_precommit_rollback
    assert not service._UPGRADES
    with pytest.raises(MigrationRefused, match="^transactional_connection_required$"):
        service._require_failure_upgrade(seen[0][0])
    assert sqlite_snapshot(predecessor.path) == before


def test_actual_successor_compatibility_is_migration_only_and_read_only(
    predecessor, record_property
):
    state = call(predecessor, initialize=True)
    before = sqlite_snapshot(predecessor.path)
    profile = load_release_profile()
    selected = [entry for entry in profile.revisions if entry.revision == FAILURE]
    assert len(selected) == 1 and selected[0].mode == "migration_only"
    assert selected[0].catalog_profile == "failure_evidence_v1"
    assert [(r.revision, r.phase) for r in selected[0].required_completed_backfills] == [
        ("ar_0003_ownership", "ownership"),
        ("ar_0005_run_index", "run_index"),
        (LEDGER, "ledger_opening"),
    ]
    start = time.monotonic()
    result = runtime_schema_compatibility(predecessor.engine)
    elapsed = time.monotonic() - start
    assert (result.status, result.code) == ("incompatible", "migration_only")
    assert result.installation_key is None
    assert state.revision == FAILURE
    assert sqlite_snapshot(predecessor.path) == before
    record_property("compatibility_seconds", elapsed)


@pytest.mark.parametrize("mutation", ["missing", "empty", "future", "multiple", "null", "oversize"])
def test_compatibility_preserves_old_missing_and_malformed_revision_refusal(tmp_path, mutation):
    from sqlalchemy import create_engine

    engine = create_engine("sqlite:///" + str(tmp_path / "malformed.sqlite"))
    try:
        with engine.begin() as connection:
            if mutation != "missing":
                connection.exec_driver_sql("CREATE TABLE alembic_version(version_num TEXT)")
                values = {
                    "empty": [],
                    "future": ["ar_future"],
                    "multiple": [LEDGER, FAILURE],
                    "null": [None],
                    "oversize": ["x" * 33],
                }[mutation]
                for value in values:
                    connection.exec_driver_sql("INSERT INTO alembic_version VALUES(?)", (value,))
        with engine.connect() as connection:
            result = check_schema_compatibility(connection, load_release_profile())
        assert (result.status, result.code) == ("incompatible", "schema_incompatible")
    finally:
        engine.dispose()


@pytest.mark.parametrize("shape", ["missing_column", "wrong_type", "old_revision"])
def test_additive_malformed_version_shape_is_incompatible_before_version_query(predecessor, shape):
    case = predecessor
    with case.engine.begin() as connection:
        failure_schema.create_failure_schema(connection)
        if shape != "old_revision":
            connection.exec_driver_sql("DROP TABLE alembic_version")
            connection.exec_driver_sql(
                "CREATE TABLE alembic_version(unknown_column VARCHAR(32) NOT NULL PRIMARY KEY)"
                if shape == "missing_column"
                else "CREATE TABLE alembic_version(version_num INTEGER NOT NULL PRIMARY KEY)"
            )
    before = sqlite_snapshot(case.path)
    statements = []
    event.listen(
        case.engine, "before_cursor_execute", lambda _c, _u, s, _p, _x, _m: statements.append(s)
    )
    with case.engine.connect() as connection:
        result = check_schema_compatibility(connection, load_release_profile())
    assert (result.status, result.code) == ("incompatible", "schema_incompatible")
    revision_reads = [
        statement for statement in statements if "SELECT CASE WHEN typeof(version_num)" in statement
    ]
    assert len(revision_reads) == (1 if shape == "old_revision" else 0)
    assert all(statement.endswith("LIMIT 2") for statement in revision_reads)
    assert sqlite_snapshot(case.path) == before
