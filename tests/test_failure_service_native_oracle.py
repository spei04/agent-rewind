"""Independent full-state service evidence; no admitted startup or producer grant."""

import hashlib
import json
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
import test_migrations_postgres as migration_tests
from alembic import command
from alembic.config import Config
from ledger_capacity_fixture import object_hashes
from ledger_reader_fixture import complete_ar6
from ledger_service_fixture import provision_after, service_postgres_state
from legacy_fixture import FIXTURE_ROOT, canonical_bytes, read_manifest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from test_failure_catalog_native_oracle import full_shape, native_snapshot, project_ar7
from test_failure_schema import rows
from test_ledger_service import inspect as inspect_old_ledger
from test_ledger_service import intent, invoke
from test_run_projection_postgres import drain as drain_postgres

from agent_rewind.migrations import failure_service
from agent_rewind.migrations.compatibility import (
    CONNECT_TIMEOUT_SECONDS,
    POOL_TIMEOUT_SECONDS,
    runtime_schema_compatibility,
)
from agent_rewind.migrations.failure_service import (
    FailureInitialization,
    FailureState,
    initialize_failure_evidence,
    inspect_failure_evidence,
)
from agent_rewind.migrations.failure_transaction import failure_transaction
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.ledger_transaction import LedgerOutcome
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import FAILURE, LEDGER, MigrationRefused, catalog
from agent_rewind.sqlite_ownership import create_owned_sqlite_engine

pg = migration_tests.pg
POSTGRES = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL failure service"
)


@pytest.fixture(params=["sqlite", pytest.param("postgresql", marks=POSTGRES)])
def dialect_name(request):
    return request.param


def drain(state):
    if state.pg is not None:
        drain_postgres(state.pg)


@contextmanager
def authentic_state(tmp_path, request, dialect_name, *, legacy):
    """Build ar7 through the real ledger service, including a later legacy provision."""
    if dialect_name == "postgresql":
        pg = request.getfixturevalue("pg")
        original = service_postgres_state(pg, history="later" if legacy else "empty")
        case = original.case
        objects = FIXTURE_ROOT / "objects" if legacy else None
    else:
        pg = None
        case = complete_ar6(tmp_path / "failure.sqlite", legacy=legacy)
        objects = case.path.parent / "objects" if legacy else None
    state = SimpleNamespace(case=case, pg=pg, objects=objects, engines=[])
    try:
        if pg is None:
            initial = validate_ledger_manifest(intent(case, empty=not legacy))
            receipt = invoke(case, initial.model_dump(mode="json"))
            if legacy:
                later = provision_after(initial, receipt)
                invoke(case, later.model_dump(mode="json"))
        state.retained = inspect_old_ledger(case)
        drain(state)
        assert state.retained.status == "complete" and state.retained.revision == LEDGER
        assert state.retained.manifest_count == (2 if legacy else 1)
        if legacy:
            assert object_hashes(case, directory=objects) == {
                spec["address"]: spec["ciphertext_sha256"]
                for spec in read_manifest()["objects"].values()
            }
        yield state
    finally:
        case.dispose()
        drain(state)


def call(state, operation):
    # Each call owns a fresh registered engine, including inspection after uncertainty.
    engine = state.case.operator_engine()
    state.engines.append(engine)
    try:
        return operation(engine, installation_key=state.case.adoption["installation_key"])
    finally:
        engine.dispose()
        drain(state)


def witness(state, count):
    """Read physical metadata and whole rows independently; keep raw timestamps intact."""
    with state.case.engine.connect() as connection:
        raw = native_snapshot(connection, count)
        data = rows(connection)
        shape = catalog(connection) if count == 20 else full_shape(connection, raw)
    drain(state)
    return {
        "native": raw,
        "rows": data,
        "shape": shape,
        "ciphertexts": (
            object_hashes(state.case, directory=state.objects) if state.objects is not None else {}
        ),
        "sqlite_bytes_sha256": (
            hashlib.sha256(state.case.path.read_bytes()).hexdigest()
            if state.case.path is not None
            else None
        ),
    }


def profile_digest(shape):
    return hashlib.sha256(canonical_bytes(shape)).hexdigest()


def assert_absent(value, state, before):
    assert type(value) is FailureState
    assert (value.status, value.revision, value.catalog_profile) == ("absent", LEDGER, "ledger_v1")
    assert value.installation_key == state.case.adoption["installation_key"]
    assert value.retained_ar7 == state.retained
    assert value.installed_profile_sha256 == profile_digest(before["shape"])


def assert_retained_native(before, after):
    """Compare old physical objects after the complete successor literal has matched."""
    table, support = "job_failure_evidence", "job_failure_operation_binding_uq"
    if "tables" in before:
        assert [row for row in after["objects"] if row[2] != table and row[1] != support] == (
            before["objects"]
        )
        assert sorted(row for row in after["table_list"] if row[1] != table) == sorted(
            before["table_list"]
        )
        assert after["foreign_keys_enabled"] == before["foreign_keys_enabled"]
        assert set(after["tables"]) == set(before["tables"]) | {table}
        for name, old in before["tables"].items():
            new = after["tables"][name]
            assert new["columns"] == old["columns"]
            assert new["foreign_keys"] == old["foreign_keys"]
            # index_list's ordinal changes when the one approved support index is added.
            assert sorted(row[1:] for row in new["indexes"] if row[1] != support) == sorted(
                row[1:] for row in old["indexes"]
            )
            assert {key: value for key, value in new["index_parts"].items() if key != support} == (
                old["index_parts"]
            )
    else:
        for key in [
            "table_names",
            "pg_columns",
            "pg_constraints",
            "column_native",
            "table_owners_acl",
        ]:
            assert [row for row in after[key] if row[0] != table] == before[key]
        assert [
            row
            for row in after["pg_indexes"]
            if row[0] != table and not row[1].startswith("CREATE UNIQUE INDEX " + support + " ")
        ] == before["pg_indexes"]
        old_functions = {row["name"] for row in before["functions"]}
        assert [row for row in after["functions"] if row["name"] in old_functions] == (
            before["functions"]
        )
        assert [row for row in after["triggers"] if row["relation"] != table] == before["triggers"]
        assert [row for row in after["function_acl"] if row[0] in old_functions] == (
            before["function_acl"]
        )
        assert after["default_acl"] == before["default_acl"]


def assert_complete(value, state, before, after):
    assert (value.status, value.revision, value.catalog_profile) == (
        "complete",
        FAILURE,
        "failure_evidence_v1",
    )
    assert value.installation_key == state.case.adoption["installation_key"]
    assert value.retained_ar7 == state.retained
    profile_name = (
        "sqlite_failure_evidence.json"
        if state.case.engine.dialect.name == "sqlite"
        else "postgresql16_failure_evidence.json"
    )
    profile = json.loads(
        (Path(__file__).parents[1] / "agent_rewind/migrations/profiles" / profile_name).read_text()
    )
    assert after["shape"] == profile
    # Project only after the independent complete successor literal has matched.
    assert project_ar7(after["shape"]) == before["shape"]
    assert_retained_native(before["native"], after["native"])
    assert value.installed_profile_sha256 == profile_digest(profile)
    assert value.installed_profile_sha256 != profile_digest(before["shape"])
    assert set(after["rows"]) == set(before["rows"]) | {"job_failure_evidence"}
    assert after["rows"]["job_failure_evidence"] == []
    for table, old_rows in before["rows"].items():
        assert after["rows"][table] == ([(FAILURE,)] if table == "alembic_version" else old_rows)
    assert after["ciphertexts"] == before["ciphertexts"]


def observe_work(monkeypatch):
    original = failure_service._inspect
    observed = []

    def inspect(connection, key, work):
        if not any(item[1] is work for item in observed):
            observed.append((connection, work))
        return original(connection, key, work)

    monkeypatch.setattr(failure_service, "_inspect", inspect)
    return observed


def record_work(record_property, observed):
    record_property(
        "service_work",
        json.dumps(
            [
                {
                    "prepaid_bootstrap": work.prepaid_bootstrap,
                    "prepaid_cleanup": work.prepaid_cleanup,
                    "observed_ordinary": work.observed_ordinary,
                    "cleanup_observations": work.cleanup_observations,
                    "connection_closed": connection.closed,
                    "upgrade_scope_revoked": connection not in failure_service._UPGRADES,
                }
                for connection, work in observed
            ],
            sort_keys=True,
        ),
    )


def observe_upgrade(monkeypatch, *, stage=None, refusal=None):
    original = command.upgrade
    visits = []

    def upgrade(config, revision, *args, **kwargs):
        assert revision == FAILURE
        connection = config.attributes["connection"]
        work = failure_service._UPGRADES[connection]
        assert type(connection) is Connection and type(work) is LedgerWork
        visit = {"connection": connection, "work": work}
        visits.append(visit)
        result = original(config, revision, *args, **kwargs)
        assert failure_service._UPGRADES.get(connection) is work
        if stage is not None:
            assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").all() == [
                (FAILURE,)
            ]
            assert (
                connection.exec_driver_sql("SELECT count(*) FROM job_failure_evidence").scalar_one()
                == 0
            )
            visit["version_and_ddl_observed"] = True
        if stage == "after_upgrade":
            raise refusal
        if stage == "source_drift":
            row = connection.exec_driver_sql(
                "SELECT id,action FROM audit ORDER BY id LIMIT 1"
            ).one()
            changed = row.action + "-f2-source-drift"
            assert len(changed.encode()) <= 80 and changed != row.action
            assert (
                connection.execute(
                    text("UPDATE audit SET action=:action WHERE id=:id"),
                    {"id": row.id, "action": changed},
                ).rowcount
                == 1
            )
            assert (
                connection.execute(
                    text("SELECT action FROM audit WHERE id=:id"), {"id": row.id}
                ).scalar_one()
                == changed
            )
            visit["native_source_mutation_observed"] = True
        return result

    monkeypatch.setattr(command, "upgrade", upgrade)
    return visits


def assert_revoked(visits):
    assert len(visits) == 1
    connection = visits[0]["connection"]
    assert connection not in failure_service._UPGRADES
    with pytest.raises(MigrationRefused, match="^transactional_connection_required$"):
        failure_service._require_failure_upgrade(connection)


@pytest.mark.parametrize("legacy", [False, True], ids=["fresh", "legacy-later"])
def test_public_upgrade_reentry_preserves_native_history_and_ciphertexts(
    tmp_path, request, dialect_name, legacy, monkeypatch, record_property
):
    with authentic_state(tmp_path, request, dialect_name, legacy=legacy) as state:
        before = witness(state, 20)
        observed = observe_work(monkeypatch)
        visits = observe_upgrade(monkeypatch)
        absent = call(state, inspect_failure_evidence)
        assert_absent(absent, state, before)
        assert witness(state, 20) == before
        initialized = call(state, initialize_failure_evidence)
        assert type(initialized) is FailureInitialization and initialized.outcome == "complete"
        after = witness(state, 21)
        assert_complete(initialized, state, before, after)
        inspected = call(state, inspect_failure_evidence)
        assert type(inspected) is FailureState
        assert_complete(inspected, state, before, witness(state, 21))
        assert call(state, initialize_failure_evidence) == initialized
        assert_revoked(visits)
        assert len(observed) == 4 and all(connection.closed for connection, _ in observed)
        assert witness(state, 21) == after
        # Public acquisition and connection return share the unchanged two-second guard.
        url = state.case.engine.url.render_as_string(hide_password=False)
        runtime_engine = (
            create_owned_sqlite_engine(
                url,
                connect_timeout=CONNECT_TIMEOUT_SECONDS,
                pool_timeout=POOL_TIMEOUT_SECONDS,
            )
            if dialect_name == "sqlite"
            else create_engine(url, pool_pre_ping=True, pool_timeout=POOL_TIMEOUT_SECONDS)
        )
        try:
            started = time.monotonic()
            compatibility = runtime_schema_compatibility(runtime_engine)
            elapsed = time.monotonic() - started
            assert (compatibility.status, compatibility.code) == ("incompatible", "migration_only")
            assert compatibility.installation_key is None
            assert runtime_engine.pool.checkedout() == 0
        finally:
            runtime_engine.dispose()
            drain(state)
        assert witness(state, 21) == after
        record_property("compatibility_seconds", elapsed)
        # The unchanged old20 ledger boundary still refuses the successor.
        with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
            inspect_old_ledger(state.case)
        drain(state)
        assert witness(state, 21) == after
        record_work(record_property, observed)


@pytest.mark.parametrize("stage", ["after_upgrade", "source_drift"])
def test_real_version_and_source_mutation_roll_back_without_publication(
    tmp_path, request, dialect_name, stage, monkeypatch, record_property
):
    with authentic_state(tmp_path, request, dialect_name, legacy=True) as state:
        before = witness(state, 20)
        refusal = MigrationRefused("migration_busy")
        observed = observe_work(monkeypatch)
        visits = observe_upgrade(monkeypatch, stage=stage, refusal=refusal)
        original_digest = failure_service.source_digest
        digests = []

        def digest(connection, work):
            value = original_digest(connection, work)
            digests.append(value)
            return value

        monkeypatch.setattr(failure_service, "source_digest", digest)
        returned = []
        with pytest.raises(MigrationRefused) as caught:
            returned.append(call(state, initialize_failure_evidence))
        assert returned == [] and visits[0]["version_and_ddl_observed"]
        if stage == "after_upgrade":
            assert caught.value is refusal and len(digests) == 1
        else:
            assert caught.value.code == "schema_incompatible"
            assert visits[0]["native_source_mutation_observed"]
            assert len(digests) == 2 and digests[0] != digests[1]
        assert_revoked(visits)
        assert witness(state, 20) == before
        assert_absent(call(state, inspect_failure_evidence), state, before)
        assert witness(state, 20) == before
        record_property(
            "rollback_boundary",
            json.dumps(
                {
                    "stage": stage,
                    "version_and_ddl_observed": True,
                    "native_source_mutation_observed": stage == "source_drift",
                    "real_digest_calls": len(digests),
                    "whole_state_restored": True,
                    "public_result_returned": False,
                }
            ),
        )
        record_work(record_property, observed)


def test_thin_revision_requires_scoped_owned_connection(
    tmp_path, request, dialect_name, monkeypatch, record_property
):
    with authentic_state(tmp_path, request, dialect_name, legacy=False) as state:
        before = witness(state, 20)
        with (
            state.case.engine.connect() as bare,
            pytest.raises(MigrationRefused, match="^transactional_connection_required$"),
        ):
            failure_service._require_failure_upgrade(bare)
        drain(state)
        engine = state.case.operator_engine()
        outcome, work = LedgerOutcome(), LedgerWork()
        original_guard, guard_calls = failure_service._require_failure_upgrade, []

        def guard(connection):
            guard_calls.append(connection)
            return original_guard(connection)

        monkeypatch.setattr(failure_service, "_require_failure_upgrade", guard)
        try:
            with (
                pytest.raises(MigrationRefused, match="^transactional_connection_required$"),
                failure_transaction(engine, outcome, work=work) as connection,
            ):
                assert connection not in failure_service._UPGRADES
                config = Config()
                config.set_main_option(
                    "script_location", str(Path(failure_service.__file__).parent)
                )
                config.attributes.update(connection=connection, validated_operator=True)
                command.upgrade(config, FAILURE)
            assert guard_calls == [connection]
            assert connection not in failure_service._UPGRADES
            assert outcome.confirmed_precommit_rollback and not outcome.commit_attempted
            assert not outcome.cleanup_failed
        finally:
            engine.dispose()
            drain(state)
        assert witness(state, 20) == before
        record_work(record_property, [(connection, work)])


@POSTGRES
@pytest.mark.parametrize(
    "boundary",
    ["before_commit", "after_commit", "after_rollback", "after_close", "inspect_close"],
)
def test_public_postgres_results_wait_for_ack_and_cleanup(
    tmp_path, request, monkeypatch, boundary, record_property
):
    with authentic_state(tmp_path, request, "postgresql", legacy=True) as state:
        before = witness(state, 20)
        observed = observe_work(monkeypatch)
        refusal = MigrationRefused("migration_busy")
        visits = observe_upgrade(
            monkeypatch,
            stage="after_upgrade" if boundary == "after_rollback" else None,
            refusal=refusal,
        )
        commit, rollback, close = (
            psycopg.Connection.commit,
            psycopg.Connection.rollback,
            Connection.close,
        )
        failures = []
        raw_targets = []

        def target(raw):
            return bool(observed) and raw is raw_targets[0]

        original_inspect = failure_service._inspect

        def inspect(connection, key, work):
            if not raw_targets:
                raw_targets.append(connection.connection.driver_connection)
            return original_inspect(connection, key, work)

        def commit_ack(raw):
            if boundary in {"before_commit", "after_commit"} and target(raw):
                assert failures == []
                failures.append(boundary)
                if boundary == "after_commit":
                    commit(raw)
                raise RuntimeError("synthetic-private-service-commit")
            return commit(raw)

        def rollback_ack(raw):
            if boundary == "after_rollback" and target(raw) and not failures:
                rollback(raw)
                failures.append(boundary)
                raise RuntimeError("synthetic-private-service-rollback")
            return rollback(raw)

        def close_ack(connection):
            result = close(connection)
            if (
                boundary in {"after_close", "inspect_close"}
                and observed
                and connection is observed[0][0]
                and not failures
            ):
                failures.append(boundary)
                raise RuntimeError("synthetic-private-service-close")
            return result

        operation = (
            inspect_failure_evidence if boundary == "inspect_close" else initialize_failure_evidence
        )
        returned = []
        with monkeypatch.context() as patch:
            patch.setattr(failure_service, "_inspect", inspect)
            patch.setattr(psycopg.Connection, "commit", commit_ack)
            patch.setattr(psycopg.Connection, "rollback", rollback_ack)
            patch.setattr(Connection, "close", close_ack)
            with pytest.raises(MigrationRefused, match="^ledger_outcome_uncertain$") as caught:
                returned.append(call(state, operation))
        assert returned == [] and failures == [boundary]
        assert raw_targets[0].closed and caught.value.__suppress_context__
        assert caught.value.__cause__ is None and "synthetic-private" not in str(caught.value)
        if boundary == "inspect_close":
            assert visits == []
        else:
            assert_revoked(visits)
        # Fresh observation is a distinct new engine, never automatic retry/initialization.
        seen = call(state, inspect_failure_evidence)
        assert state.engines[-1] is not state.engines[0]
        visible_commit = boundary in {"after_commit", "after_close"}
        if visible_commit:
            after = witness(state, 21)
            assert_complete(seen, state, before, after)
        else:
            assert_absent(seen, state, before)
            assert witness(state, 20) == before
        record_property(
            "public_ack_boundary",
            json.dumps(
                {
                    "boundary": boundary,
                    "public_result_returned": False,
                    "native_commit_visible": visible_commit,
                    "fresh_inspection_engine": True,
                    "initialization_retried": False,
                }
            ),
        )
        record_work(record_property, observed)
