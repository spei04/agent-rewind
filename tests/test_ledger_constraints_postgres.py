"""Independent native PostgreSQL checks for frozen ledger identity and evidence."""

from contextlib import contextmanager

import pytest
import test_migrations_postgres as migration_tests
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from test_admission_schema import OTHER, PROJECT, predecessor
from test_artifact_metadata import object_value
from test_ledger_schema import (
    CALL,
    END,
    JOB,
    JOB_ACCOUNT,
    NOW,
    ORG_ACCOUNT,
    PROJECT_ACCOUNT,
    account,
    call,
    triple,
)

from agent_rewind.artifact_metadata import record_verified, register_ref
from agent_rewind.migrations.admission_schema import create_admission_schema
from agent_rewind.migrations.ledger_schema import create_ledger_constraints, create_ledger_schema
from agent_rewind.migrations.schema import ADMISSION, LEDGER, catalog, installed_profile

pg = migration_tests.pg
pytestmark = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL ledger constraints"
)


@pytest.fixture
def ledger_pg(pg):
    engine = pg["owner"]
    predecessor(engine)
    with engine.begin() as connection:
        create_admission_schema(connection)
        connection.execute(
            text("UPDATE alembic_version SET version_num=:head"), {"head": ADMISSION}
        )
        assert catalog(connection) == installed_profile("postgresql", ADMISSION)
        create_ledger_schema(connection)
        # Fixture backfill is intentionally separate from the unfinished operator.
        connection.exec_driver_sql("UPDATE jobs SET legacy_reserved_microusd=reserved")
        create_ledger_constraints(connection)
        connection.execute(text("UPDATE alembic_version SET version_num=:head"), {"head": LEDGER})
    return pg


@pytest.fixture
def committed_call(ledger_pg):
    with ledger_pg["owner"].begin() as connection:
        triple(connection)
        call(connection)
    return ledger_pg


@contextmanager
def commit_refused(engine):
    """Prove the entire mutation body ran before a deferred COMMIT refusal."""
    body_completed = False
    with pytest.raises(IntegrityError) as caught, engine.begin() as connection:
        yield connection
        body_completed = True
    assert body_completed, "An earlier SQL failure masked the deferred constraint"
    assert caught.value.orig.sqlstate == "23514"


def scope_project(connection, identifier=CALL):
    return connection.execute(
        text(
            "SELECT project_id FROM resource_scopes "
            "WHERE resource_kind='provider_call' AND resource_id=:id"
        ),
        {"id": identifier},
    ).scalar_one()


@pytest.mark.parametrize(
    "mutation",
    [
        "delete",
        "reassociate",
        "delete_restore",
        "reassociate_restore",
        "kind_restore",
        "id_restore",
    ],
)
def test_call_scope_mutation_cannot_be_hidden_by_restoring_final_state(committed_call, mutation):
    engine = committed_call["owner"]
    with engine.connect() as connection:
        assert scope_project(connection) == PROJECT
        assert (
            connection.exec_driver_sql(
                "SELECT count(*) FROM artifact_refs WHERE role='budget_evidence'"
            ).scalar_one()
            == 0
        )
    with commit_refused(engine) as connection:
        parameters = {"id": CALL, "project": PROJECT, "other": OTHER, "new_id": "1" * 32}
        if mutation.startswith("delete"):
            connection.execute(
                text(
                    "DELETE FROM resource_scopes WHERE resource_kind='provider_call' "
                    "AND resource_id=:id"
                ),
                parameters,
            )
            if mutation == "delete_restore":
                connection.execute(
                    text("INSERT INTO resource_scopes VALUES('provider_call',:id,:project)"),
                    parameters,
                )
        elif mutation.startswith("reassociate"):
            connection.execute(
                text(
                    "UPDATE resource_scopes SET project_id=:other "
                    "WHERE resource_kind='provider_call' AND resource_id=:id"
                ),
                parameters,
            )
            if mutation == "reassociate_restore":
                connection.execute(
                    text(
                        "UPDATE resource_scopes SET project_id=:project "
                        "WHERE resource_kind='provider_call' AND resource_id=:id"
                    ),
                    parameters,
                )
        elif mutation == "kind_restore":
            connection.execute(
                text(
                    "UPDATE resource_scopes SET resource_kind='run' "
                    "WHERE resource_kind='provider_call' AND resource_id=:id"
                ),
                parameters,
            )
            connection.execute(
                text(
                    "UPDATE resource_scopes SET resource_kind='provider_call' "
                    "WHERE resource_kind='run' AND resource_id=:id"
                ),
                parameters,
            )
        else:
            connection.execute(
                text(
                    "UPDATE resource_scopes SET resource_id=:new_id "
                    "WHERE resource_kind='provider_call' AND resource_id=:id"
                ),
                parameters,
            )
            connection.execute(
                text(
                    "UPDATE resource_scopes SET resource_id=:id "
                    "WHERE resource_kind='provider_call' AND resource_id=:new_id"
                ),
                parameters,
            )
        assert connection.exec_driver_sql("SELECT count(*) FROM provider_calls").scalar_one() == 1
    with engine.connect() as connection:
        assert scope_project(connection) == PROJECT
        assert connection.exec_driver_sql("SELECT count(*) FROM budget_entries").scalar_one() == 3


def test_call_scope_noop_update_is_valid(committed_call):
    engine = committed_call["owner"]
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE resource_scopes SET project_id=project_id "
                "WHERE resource_kind='provider_call' AND resource_id=:id"
            ),
            {"id": CALL},
        )
    with engine.connect() as connection:
        assert scope_project(connection) == PROJECT


@pytest.mark.parametrize("mutation", ["delete", "reassociate"])
def test_scope_without_call_remains_mutable(committed_call, mutation):
    engine = committed_call["owner"]
    identifier = "1" * 32
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO resource_scopes VALUES('provider_call',:id,:project)"),
            {"id": identifier, "project": PROJECT},
        )
    with engine.begin() as connection:
        if mutation == "delete":
            connection.execute(
                text(
                    "DELETE FROM resource_scopes WHERE resource_kind='provider_call' "
                    "AND resource_id=:id"
                ),
                {"id": identifier},
            )
        else:
            connection.execute(
                text(
                    "UPDATE resource_scopes SET project_id=:project "
                    "WHERE resource_kind='provider_call' AND resource_id=:id"
                ),
                {"id": identifier, "project": OTHER},
            )
    with engine.connect() as connection:
        assert scope_project(connection) == PROJECT
        if mutation == "delete":
            assert (
                connection.execute(
                    text("SELECT count(*) FROM resource_scopes WHERE resource_id=:id"),
                    {"id": identifier},
                ).scalar_one()
                == 0
            )
        else:
            assert scope_project(connection, identifier) == OTHER


@pytest.mark.parametrize(
    "table,column,changed,original",
    [
        ("budget_accounts", "limit_microusd", 500001, 500000),
        ("budget_accounts", "opening_held_microusd", 245001, 245000),
        ("provider_calls", "logical_call_id", "1" * 32, "e" * 32),
        ("provider_calls", "request_digest", "1" * 64, "f" * 64),
        ("provider_calls", "price_version", "synthetic-price-2", "synthetic-price-1"),
        ("provider_calls", "purpose", "discovery", "continuation"),
        ("provider_calls", "lease_generation", 2, 1),
        ("provider_calls", "reserved_microusd", 11, 10),
        ("jobs", "legacy_reserved_microusd", 245001, 245000),
    ],
)
def test_frozen_values_reject_change_then_revert(committed_call, table, column, changed, original):
    engine = committed_call["owner"]
    identifier = {"budget_accounts": JOB_ACCOUNT, "provider_calls": CALL, "jobs": JOB}[table]
    # Table and column names come exclusively from the fixed parameter list.
    statement = text(f"UPDATE {table} SET {column}=:value WHERE id=:id")
    with commit_refused(engine) as connection:
        connection.execute(statement, {"id": identifier, "value": changed})
        connection.execute(statement, {"id": identifier, "value": original})
    with engine.connect() as connection:
        assert (
            connection.execute(
                text(f"SELECT {column} FROM {table} WHERE id=:id"), {"id": identifier}
            ).scalar_one()
            == original
        )


def test_generation_advance_is_valid_but_decrease_then_restore_is_not(committed_call):
    engine = committed_call["owner"]
    with engine.begin() as connection:
        connection.execute(text("UPDATE jobs SET lease_generation=2 WHERE id=:id"), {"id": JOB})
    with commit_refused(engine) as connection:
        connection.execute(text("UPDATE jobs SET lease_generation=1 WHERE id=:id"), {"id": JOB})
        connection.execute(text("UPDATE jobs SET lease_generation=2 WHERE id=:id"), {"id": JOB})
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT lease_generation FROM jobs WHERE id=:id"), {"id": JOB}
            ).scalar_one()
            == 2
        )


@pytest.mark.parametrize("mutation", ["update_restore", "delete_restore"])
def test_entries_are_append_only_even_when_the_final_row_is_identical(committed_call, mutation):
    engine = committed_call["owner"]
    parameters = {"call": CALL, "account": JOB_ACCOUNT, "created": NOW, "project": PROJECT}
    with commit_refused(engine) as connection:
        if mutation == "update_restore":
            connection.execute(
                text(
                    "UPDATE budget_entries SET amount_microusd=11 "
                    "WHERE call_id=:call AND account_id=:account"
                ),
                parameters,
            )
            connection.execute(
                text(
                    "UPDATE budget_entries SET amount_microusd=10 "
                    "WHERE call_id=:call AND account_id=:account"
                ),
                parameters,
            )
        else:
            connection.execute(
                text("DELETE FROM budget_entries WHERE call_id=:call AND account_id=:account"),
                parameters,
            )
            connection.execute(
                text(
                    "INSERT INTO budget_entries(call_id,account_id,entry_kind,amount_microusd,"
                    "created_at,project_id) VALUES(:call,:account,'reserve',10,:created,:project)"
                ),
                parameters,
            )


@pytest.mark.parametrize("overlap", [False, True])
def test_organization_period_boundary_is_half_open(committed_call, overlap):
    engine = committed_call["owner"]
    values = {
        "id": "1" * 32,
        "period_start": "2026-12-31T23:59:59.999999Z" if overlap else END,
        "period_end": "2028-01-01T00:00:00.000000Z",
        "held_microusd": 0,
        "opening_held_microusd": 0,
    }
    if overlap:
        with commit_refused(engine) as connection:
            account(connection, "organization", **values)
    else:
        with engine.begin() as connection:
            account(connection, "organization", **values)
        with engine.connect() as connection:
            assert (
                connection.exec_driver_sql(
                    "SELECT count(*) FROM budget_accounts WHERE scope='organization'"
                ).scalar_one()
                == 2
            )


def evidence(connection, *, owner_id=CALL):
    value = object_value()
    record_verified(connection, value)
    register_ref(
        connection,
        project_id=PROJECT,
        owner_kind="provider_call",
        owner_id=owner_id,
        role="budget_evidence",
        artifact_id=value.id,
    )
    return value.id


def entries(connection, kind, amounts, artifact_id):
    assert len(amounts) <= 3
    for identifier, amount in zip(
        [ORG_ACCOUNT, PROJECT_ACCOUNT, JOB_ACCOUNT], amounts, strict=False
    ):
        connection.execute(
            text(
                "INSERT INTO budget_entries(call_id,account_id,entry_kind,amount_microusd,"
                "evidence_ref,created_at,project_id) "
                "VALUES(:call,:account,:kind,:amount,:evidence,:created,:project)"
            ),
            {
                "call": CALL,
                "account": identifier,
                "kind": kind,
                "amount": amount,
                "evidence": artifact_id,
                "created": NOW,
                "project": PROJECT,
            },
        )


@pytest.mark.parametrize(
    "settlement,release",
    [([7, 7, 7], [4, 4, 4]), ([3, 3], []), ([3, 4, 3], []), ([], [11, 11, 11])],
)
def test_evidence_backed_cohorts_reject_partial_unequal_or_excess_total(
    committed_call, settlement, release
):
    engine = committed_call["owner"]
    with commit_refused(engine) as connection:
        artifact_id = evidence(connection)
        entries(connection, "settle", settlement, artifact_id)
        entries(connection, "release", release, artifact_id)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM budget_entries").scalar_one() == 3


def test_settlement_and_release_equal_to_reservation_commit(committed_call):
    engine = committed_call["owner"]
    with engine.begin() as connection:
        artifact_id = evidence(connection)
        entries(connection, "settle", [6, 6, 6], artifact_id)
        entries(connection, "release", [4, 4, 4], artifact_id)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM budget_entries").scalar_one() == 9


def test_existing_evidence_for_other_call_cannot_back_this_call(committed_call):
    engine = committed_call["owner"]
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO resource_scopes VALUES('provider_call',:id,:project)"),
            {"id": "1" * 32, "project": PROJECT},
        )
        artifact_id = evidence(connection, owner_id="1" * 32)
    with pytest.raises(IntegrityError) as caught, engine.begin() as connection:
        entries(connection, "settle", [1, 1, 1], artifact_id)
    assert caught.value.orig.sqlstate == "23503"


@pytest.mark.parametrize("parent", ["artifact_refs", "artifact_objects"])
def test_evidence_parent_deletion_cannot_orphan_committed_entries(committed_call, parent):
    engine = committed_call["owner"]
    with engine.begin() as connection:
        artifact_id = evidence(connection)
        entries(connection, "settle", [1, 1, 1], artifact_id)
    with pytest.raises(IntegrityError) as caught, engine.begin() as connection:
        column = "artifact_id" if parent == "artifact_refs" else "id"
        connection.execute(text(f"DELETE FROM {parent} WHERE {column}=:id"), {"id": artifact_id})
    assert caught.value.orig.sqlstate == "23503"
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM budget_entries").scalar_one() == 6


@pytest.mark.parametrize("parent", ["job", "job_scope"])
def test_opening_account_retains_its_actual_job_and_scope_without_any_call(ledger_pg, parent):
    engine = ledger_pg["owner"]
    with engine.begin() as connection:
        triple(connection)
    with commit_refused(engine) as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM provider_calls").scalar_one() == 0
        if parent == "job":
            connection.execute(text("DELETE FROM jobs WHERE id=:id"), {"id": JOB})
        else:
            connection.execute(
                text("DELETE FROM resource_scopes WHERE resource_kind='job' AND resource_id=:id"),
                {"id": JOB},
            )
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM jobs WHERE id=:id"), {"id": JOB}
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM resource_scopes WHERE resource_kind='job' "
                    "AND resource_id=:id"
                ),
                {"id": JOB},
            ).scalar_one()
            == 1
        )
