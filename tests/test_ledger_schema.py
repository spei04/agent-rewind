"""Actual additive ar7 DDL and bounded literal catalog, before operator acceptance."""

import json
import os
from pathlib import Path

import pytest
import test_migrations_postgres as migration_tests
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from test_admission_schema import JOB, OTHER, PROJECT, predecessor
from test_ownership import FRESH

from agent_rewind.migrations import service
from agent_rewind.migrations.admission_schema import create_admission_schema
from agent_rewind.migrations.ledger_schema import create_ledger_constraints, create_ledger_schema
from agent_rewind.migrations.schema import (
    ADMISSION,
    LEDGER,
    MigrationRefused,
    catalog,
    installed_profile,
    schema_table_names,
    verify_installed_profile,
)

pg = migration_tests.pg
START = "2026-01-01T00:00:00.000000Z"
END = "2027-01-01T00:00:00.000000Z"
NOW = "2026-10-21T00:00:00.000000Z"
ORG_ACCOUNT, PROJECT_ACCOUNT, JOB_ACCOUNT = ("a" * 32, "b" * 32, "c" * 32)
CALL = "d" * 32


@pytest.fixture(params=["sqlite", "postgresql"])
def ledger_db(request, tmp_path):
    if request.param == "postgresql":
        if not migration_tests.POSTGRES:
            pytest.skip("Opt-in synthetic PostgreSQL ledger DDL")
        engine = request.getfixturevalue("pg")["owner"]
    else:
        engine = create_engine(f"sqlite:///{tmp_path / 'ledger.sqlite'}")

        @event.listens_for(engine, "connect")
        def foreign_keys(dbapi, _record):
            dbapi.execute("PRAGMA foreign_keys=ON")

    predecessor(engine)
    with engine.begin() as connection:
        create_admission_schema(connection)
        connection.execute(
            text("UPDATE alembic_version SET version_num=:head"), {"head": ADMISSION}
        )
        before = catalog(connection)
        assert before == installed_profile(engine.dialect.name, ADMISSION)
        create_ledger_schema(connection)
        # Fixture-only backfill precedes immutable triggers. This is not operator proof.
        connection.exec_driver_sql("UPDATE jobs SET legacy_reserved_microusd=reserved")
        create_ledger_constraints(connection)
        connection.execute(text("UPDATE alembic_version SET version_num=:head"), {"head": LEDGER})
    yield engine, before
    engine.dispose()


def account(connection, scope, **updates):
    mapping = {
        "organization": (ORG_ACCOUNT, FRESH["organization_id"], None, None),
        "project": (PROJECT_ACCOUNT, PROJECT, PROJECT, None),
        "job": (JOB_ACCOUNT, JOB, PROJECT, JOB),
    }
    identifier, scope_id, project, job = mapping[scope]
    values = {
        "id": identifier,
        "organization_id": FRESH["organization_id"],
        "scope": scope,
        "scope_id": scope_id,
        "period_start": START,
        "period_end": END,
        "limit_microusd": 500000,
        "held_microusd": 245000,
        "accounted_microusd": 0,
        "project_id": project,
        "job_id": job,
        "opening_held_microusd": 245000,
    }
    values.update(updates)
    connection.execute(
        text(
            "INSERT INTO budget_accounts ("
            + ",".join(values)
            + ") VALUES ("
            + ",".join(":" + key for key in values)
            + ")"
        ),
        values,
    )


def triple(connection):
    for scope in ("organization", "project", "job"):
        account(connection, scope)


def call(connection, *, own_scope=True, reserves=3, **updates):
    values = {
        "id": CALL,
        "project_id": PROJECT,
        "job_id": JOB,
        "logical_call_id": "e" * 32,
        "purpose": "continuation",
        "request_digest": "f" * 64,
        "price_version": "synthetic-price-1",
        "state": "reserved",
        "reserved_microusd": 10,
        "created_at": NOW,
        "organization_id": FRESH["organization_id"],
        "job_resource_kind": "job",
        "lease_generation": 1,
        "organization_account_id": ORG_ACCOUNT,
        "project_account_id": PROJECT_ACCOUNT,
        "job_account_id": JOB_ACCOUNT,
    }
    values.update(updates)
    connection.execute(
        text(
            "INSERT INTO provider_calls ("
            + ",".join(values)
            + ") VALUES ("
            + ",".join(":" + key for key in values)
            + ")"
        ),
        values,
    )
    if own_scope:
        connection.execute(
            text("INSERT INTO resource_scopes VALUES('provider_call',:id,:project)"),
            {"id": CALL, "project": PROJECT},
        )
    for identifier in [ORG_ACCOUNT, PROJECT_ACCOUNT, JOB_ACCOUNT][:reserves]:
        connection.execute(
            text(
                "INSERT INTO budget_entries(call_id,account_id,entry_kind,amount_microusd,"
                "created_at,project_id) VALUES(:call,:account,'reserve',10,:created,:project)"
            ),
            {"call": CALL, "account": identifier, "created": NOW, "project": PROJECT},
        )


def test_additive_literal_catalog_and_original_values(ledger_db):
    engine, before = ledger_db
    with engine.connect() as connection:
        shape = catalog(connection)
        tables, head = schema_table_names(connection)
        assert len(tables) == 20 and head == LEDGER
        assert set(shape) - set(before) == {"budget_accounts", "provider_calls", "budget_entries"}
        assert all(
            shape[name] == before[name] for name in before if name not in {"jobs", "$postgres"}
        )
        assert shape["jobs"]["columns"][:16] == before["jobs"]["columns"]
        assert len(shape["jobs"]["columns"]) == 18
        assert connection.exec_driver_sql("SELECT sum(reserved) FROM jobs").scalar_one() == 735000
        assert (
            connection.exec_driver_sql(
                "SELECT sum(legacy_reserved_microusd) FROM jobs"
            ).scalar_one()
            == 735000
        )
        assert (
            connection.exec_driver_sql("SELECT sum(lease_generation) FROM jobs").scalar_one() == 0
        )
        capture = os.getenv("REWIND_LEDGER_CATALOG_CAPTURE")
        if capture:
            path = Path(capture) / (engine.dialect.name + "-ledger-catalog.json")
            path.write_text(json.dumps(shape, sort_keys=True, indent=2) + "\n")
            path.chmod(0o600)
        assert shape == installed_profile(engine.dialect.name, LEDGER)
        if engine.dialect.name == "sqlite":
            assert not inspect(connection).get_view_names()
            assert (
                connection.exec_driver_sql(
                    "SELECT count(*) FROM sqlite_master WHERE type='trigger'"
                ).scalar_one()
                == 0
            )
        else:
            executable = shape["$postgres"]["ledger_executables"]
            assert len(executable["triggers"]) == 5
            assert executable["function"]["security_definer"] is False
            assert executable["function"]["settings"] == ["search_path=pg_catalog, pg_temp"]


@pytest.mark.parametrize(
    "changes",
    [
        {"scope_id": "1" * 32},
        {"scope_id": b"a" * 32},
        {"held_microusd": -1},
        {"held_microusd": 500001},
        {"accounted_microusd": 300000},
        {"period_end": START},
        {"organization_id": "A" * 32},
        {"project_id": PROJECT},
    ],
)
def test_account_checks_and_foreign_keys(ledger_db, changes):
    engine, _ = ledger_db
    with pytest.raises(DBAPIError), engine.begin() as connection:
        account(connection, "organization", **changes)


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-02-29T00:00:00.000000Z",
        "2026-01-01T24:00:00.000000Z",
        "2026-01-01T00:60:00.000000Z",
        "2026-01-01T00:00:60.000000Z",
        "0000-01-01T00:00:00.000000Z",
        "2026-01-01T00:00:00Z",
    ],
)
def test_sqlite_canonical_time_is_native_not_lossy_cast(ledger_db, timestamp):
    engine, _ = ledger_db
    if engine.dialect.name != "sqlite":
        pytest.skip("SQLite lexical representation; PG validates native timestamptz")
    with pytest.raises(IntegrityError), engine.begin() as connection:
        account(connection, "organization", period_start=timestamp)


def test_generic_upgrade_without_manifest_refuses_before_ddl(ledger_db):
    engine, _ = ledger_db
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE alembic_version SET version_num=:head"), {"head": ADMISSION}
        )
        with pytest.raises(MigrationRefused, match="invalid_ledger_manifest"):
            service._alembic(connection, "upgrade", LEDGER)
        connection.execute(text("UPDATE alembic_version SET version_num=:head"), {"head": LEDGER})
        assert len(schema_table_names(connection)[0]) == 20


def test_old_head_cannot_admit_expanded_inventory(ledger_db):
    engine, _ = ledger_db
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE alembic_version SET version_num=:head"), {"head": ADMISSION}
        )
        with pytest.raises(MigrationRefused, match="schema_incompatible"):
            catalog(connection)
        connection.execute(text("UPDATE alembic_version SET version_num=:head"), {"head": LEDGER})


@pytest.mark.parametrize(
    "scenario", ["missing_scope", "two_reserves", "immutable_account", "job_cap"]
)
def test_postgres_deferred_constraints_reject_at_commit(ledger_db, scenario):
    engine, _ = ledger_db
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL deferred constraints; SQLite operator validation is separate")
    with pytest.raises(IntegrityError), engine.begin() as connection:
        triple(connection)
        if scenario == "missing_scope":
            call(connection, own_scope=False)
        elif scenario == "two_reserves":
            call(connection, reserves=2)
        elif scenario == "immutable_account":
            connection.exec_driver_sql("UPDATE budget_accounts SET limit_microusd=500001")
            connection.exec_driver_sql("UPDATE budget_accounts SET limit_microusd=500000")
        else:
            connection.execute(text("UPDATE jobs SET budget=499999 WHERE id=:job"), {"job": JOB})
        assert connection.exec_driver_sql("SELECT count(*) FROM budget_accounts").scalar_one() == 3


def test_postgres_valid_call_and_parent_scope_retention(ledger_db):
    engine, _ = ledger_db
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL deferred final state")
    with engine.begin() as connection:
        triple(connection)
        call(connection)
    with engine.begin() as connection:
        connection.execute(text("UPDATE jobs SET lease_generation=2 WHERE id=:job"), {"job": JOB})
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            text(
                "DELETE FROM resource_scopes WHERE resource_kind='provider_call' "
                "AND resource_id=:id"
            ),
            {"id": CALL},
        )
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM provider_calls").scalar_one() == 1
        assert connection.exec_driver_sql("SELECT count(*) FROM budget_entries").scalar_one() == 3


@pytest.mark.parametrize(
    "mutation", ["delete_reinsert", "project_revert", "kind_revert", "identity_revert"]
)
def test_postgres_call_scope_identity_change_cannot_be_reversed(ledger_db, mutation):
    engine, _ = ledger_db
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL deferred OLD/NEW identity retention")
    with engine.begin() as connection:
        triple(connection)
        call(connection)
    reached_commit = False
    with pytest.raises(IntegrityError) as failure, engine.begin() as connection:
        if mutation == "delete_reinsert":
            connection.execute(
                text(
                    "DELETE FROM resource_scopes WHERE resource_kind='provider_call' "
                    "AND resource_id=:id"
                ),
                {"id": CALL},
            )
            connection.execute(
                text("INSERT INTO resource_scopes VALUES('provider_call',:id,:project)"),
                {"id": CALL, "project": PROJECT},
            )
        else:
            column, changed, original = {
                "project_revert": ("project_id", OTHER, PROJECT),
                "kind_revert": ("resource_kind", "run", "provider_call"),
                "identity_revert": ("resource_id", "9" * 32, CALL),
            }[mutation]
            connection.execute(
                text(
                    f"UPDATE resource_scopes SET {column}=:changed "
                    "WHERE resource_kind='provider_call' AND resource_id=:id"
                ),
                {"changed": changed, "id": CALL},
            )
            connection.execute(
                text(
                    f"UPDATE resource_scopes SET {column}=:original "
                    "WHERE resource_kind=:kind AND resource_id=:id"
                ),
                {
                    "original": original,
                    "kind": changed if column == "resource_kind" else "provider_call",
                    "id": changed if column == "resource_id" else CALL,
                },
            )
        assert connection.exec_driver_sql("SELECT count(*) FROM artifact_refs").scalar_one() == 0
        assert connection.exec_driver_sql("SELECT count(*) FROM budget_entries").scalar_one() == 3
        reached_commit = True
    assert reached_commit
    assert failure.value.orig.sqlstate == "23514"
    assert failure.value.orig.diag.message_primary == "immutable ledger call scope"
    with engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT project_id FROM resource_scopes WHERE resource_kind='provider_call' "
                    "AND resource_id=:id"
                ),
                {"id": CALL},
            ).scalar_one()
            == PROJECT
        )
        assert connection.exec_driver_sql("SELECT count(*) FROM provider_calls").scalar_one() == 1
        assert connection.exec_driver_sql("SELECT count(*) FROM budget_entries").scalar_one() == 3


def test_postgres_scope_guard_preserves_noop_and_unconstrained_scopes(ledger_db):
    engine, _ = ledger_db
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL deferred scope identity controls")
    orphan, unrelated = "8" * 32, "9" * 32
    with engine.begin() as connection:
        triple(connection)
        call(connection)
        for kind, identifier in (("provider_call", orphan), ("run", unrelated)):
            connection.execute(
                text("INSERT INTO resource_scopes VALUES(:kind,:id,:project)"),
                {"kind": kind, "id": identifier, "project": PROJECT},
            )
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE resource_scopes SET project_id=project_id "
                "WHERE resource_kind='provider_call' AND resource_id=:id"
            ),
            {"id": CALL},
        )
        for identifier in (orphan, unrelated):
            connection.execute(
                text("UPDATE resource_scopes SET project_id=:project WHERE resource_id=:id"),
                {"project": OTHER, "id": identifier},
            )
    with engine.begin() as connection:
        for identifier in (orphan, unrelated):
            connection.execute(
                text("DELETE FROM resource_scopes WHERE resource_id=:id"), {"id": identifier}
            )
    with engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT project_id FROM resource_scopes WHERE resource_kind='provider_call' "
                    "AND resource_id=:id"
                ),
                {"id": CALL},
            ).scalar_one()
            == PROJECT
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM resource_scopes WHERE resource_id IN (:a,:b)"),
                {"a": orphan, "b": unrelated},
            ).scalar_one()
            == 0
        )
        assert connection.exec_driver_sql("SELECT count(*) FROM artifact_refs").scalar_one() == 0


def test_twenty_first_table_refuses_before_reflection(ledger_db):
    engine, _ = ledger_db
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE unexpected(id INTEGER)")
        with pytest.raises(MigrationRefused, match="schema_incompatible"):
            catalog(connection)


@pytest.mark.parametrize("mutation", ["public_execute", "disabled_trigger"])
def test_postgres_executable_policy_drift_refuses(ledger_db, mutation):
    engine, _ = ledger_db
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL executable inventory")
    with engine.begin() as connection:
        if mutation == "public_execute":
            connection.exec_driver_sql(
                "GRANT EXECUTE ON FUNCTION public.ar7_ledger_constraint() TO PUBLIC"
            )
        else:
            connection.exec_driver_sql(
                "ALTER TABLE budget_accounts DISABLE TRIGGER ar7_accounts_constraint"
            )
        with pytest.raises(MigrationRefused, match="schema_incompatible"):
            verify_installed_profile(catalog(connection), "postgresql", LEDGER)
