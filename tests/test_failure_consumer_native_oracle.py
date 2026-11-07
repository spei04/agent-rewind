"""Independent complete native catalog/history checks for fixed ar8 readers.

These are internal consumer observations, not HTTP startup or full F4 capacity
proof. No test mints a producer body or patches schema/readiness acceptance.
"""

from contextlib import contextmanager

import pytest
import test_migrations_postgres as migration_tests
from failure_consumer_oracle import (
    assert_history,
    assert_released,
    consumer_fixture,
    observed_read,
    unvalidated_native_state,
)
from failure_postgres_fixture import pg
from sqlalchemy import text
from test_failure_persistence_native_oracle import assert_same_state, drain_case, whole_state
from test_run_projection_postgres import drain as drain_postgres

from agent_rewind.migrations import failure_catalog, failure_consumer
from agent_rewind.migrations.failure_catalog import inspect_failure_catalog
from agent_rewind.migrations.failure_consumer import (
    inspect_consumer_catalog,
    refresh_consumer_principal,
    validated_consumer_history,
)
from agent_rewind.migrations.ledger_compatibility import validated_ar7_history
from agent_rewind.migrations.schema import FAILURE, LEDGER, MigrationRefused

F4_POSTGRES = pytest.mark.f4_owned_postgres
POSTGRES = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL F4 consumer oracles"
)
__all__ = ["pg"]

CASES = [
    pytest.param("sqlite", False, False, id="sqlite-fresh"),
    pytest.param("sqlite", True, False, id="sqlite-legacy"),
    pytest.param(
        "postgresql", False, False, marks=(POSTGRES, F4_POSTGRES), id="pg-fresh-no-producer"
    ),
    pytest.param("postgresql", False, True, marks=(POSTGRES, F4_POSTGRES), id="pg-fresh-producer"),
    pytest.param(
        "postgresql", True, False, marks=(POSTGRES, F4_POSTGRES), id="pg-legacy-no-producer"
    ),
    pytest.param("postgresql", True, True, marks=(POSTGRES, F4_POSTGRES), id="pg-legacy-producer"),
]


@pytest.mark.parametrize("dialect,legacy,producer", CASES)
def test_complete_consumer_history_preserves_native_rows_and_restricted_identity(
    request, tmp_path, monkeypatch, record_property, dialect, legacy, producer
):
    selected_pg = request.getfixturevalue("pg") if dialect == "postgresql" else None
    template = (
        request.getfixturevalue("fresh_sqlite_ar6_template")
        if selected_pg is None and not legacy
        else None
    )
    with consumer_fixture(
        tmp_path,
        monkeypatch,
        record_property,
        pg=selected_pg,
        legacy=legacy,
        producer=producer,
        template=template,
    ) as fixture:
        before = whole_state(fixture.case)
        with observed_read(fixture.engine, monkeypatch, record_property) as observed:
            inspection = validated_consumer_history(observed.connection, observed.work)
        assert_released(observed)
        assert_history(inspection, fixture, before)
        assert_same_state(before, whole_state(fixture.case))


@pytest.fixture
def reader_case(pg, tmp_path, monkeypatch, record_property):
    with consumer_fixture(tmp_path, monkeypatch, record_property, pg=pg, producer=True) as fixture:
        yield fixture


@contextmanager
def forbidden_grant(fixture, kind):
    """Introduce one native privilege violation and restore that exact privilege."""
    case, reader = fixture.case, fixture.reader
    assert reader is not None
    table = "job_failure_evidence"
    if kind == "second_producer":
        grant = f"GRANT INSERT ON {table} TO {reader.reader_sql}"
        revoke = f"REVOKE INSERT ON {table} FROM {reader.reader_sql}"
    elif kind == "update":
        grant = f"GRANT UPDATE ON {table} TO {reader.reader_sql}"
        revoke = f"REVOKE UPDATE ON {table} FROM {reader.reader_sql}"
    elif kind == "public_select":
        grant, revoke = (
            f"GRANT SELECT ON {table} TO PUBLIC",
            f"REVOKE SELECT ON {table} FROM PUBLIC",
        )
    elif kind == "column_select":
        grant = f"GRANT SELECT(job_id) ON {table} TO {reader.reader_sql}"
        revoke = f"REVOKE SELECT(job_id) ON {table} FROM {reader.reader_sql}"
    elif kind == "producer_membership":
        grant = f"GRANT {reader.app_sql} TO {reader.reader_sql}"
        revoke = f"REVOKE {reader.app_sql} FROM {reader.reader_sql}"
    else:
        raise AssertionError("Unknown privilege fixture")
    owner = case.pg["control"] if kind == "producer_membership" else case.pg["owner"]
    try:
        with owner.begin() as connection:
            connection.exec_driver_sql(grant)
        drain_postgres(case.pg)
        yield
    finally:
        with owner.begin() as connection:
            connection.exec_driver_sql(revoke)
        drain_postgres(case.pg)


@POSTGRES
@F4_POSTGRES
@pytest.mark.parametrize(
    "kind", ["second_producer", "update", "public_select", "column_select", "producer_membership"]
)
def test_reader_refuses_real_native_privilege_expansion_without_source_mutation(
    reader_case, monkeypatch, record_property, kind
):
    fixture = reader_case
    original = whole_state(fixture.case)
    with forbidden_grant(fixture, kind):
        injected = whole_state(fixture.case)
        if kind == "producer_membership":
            with fixture.case.pg["control"].connect() as connection:
                assert (
                    connection.execute(
                        text("SELECT pg_has_role(:reader,:producer,'MEMBER')"),
                        {"reader": fixture.reader.reader, "producer": fixture.case.pg["app_role"]},
                    ).scalar_one()
                    is True
                )
            drain_postgres(fixture.case.pg)
        with (
            pytest.raises(MigrationRefused) as error,
            observed_read(fixture.engine, monkeypatch, record_property) as observed,
        ):
            validated_consumer_history(observed.connection, observed.work)
        assert error.value.code == "schema_incompatible"
        assert_released(observed)
        assert_same_state(injected, whole_state(fixture.case))
    assert_same_state(original, whole_state(fixture.case))


@POSTGRES
@F4_POSTGRES
def test_consumer_policy_does_not_widen_the_public_f2_catalog_policy(
    reader_case, monkeypatch, record_property
):
    fixture = reader_case
    before = whole_state(fixture.case)
    with (
        pytest.raises(MigrationRefused) as error,
        observed_read(fixture.engine, monkeypatch, record_property) as observed,
    ):
        inspect_failure_catalog(observed.connection, observed.work)
    assert error.value.code == "schema_incompatible"
    assert_released(observed)
    assert_same_state(before, whole_state(fixture.case))


@POSTGRES
@F4_POSTGRES
def test_refresh_refuses_a_real_producer_change_during_the_read(
    reader_case, monkeypatch, record_property
):
    fixture = reader_case
    case, reader = fixture.case, fixture.reader
    before = whole_state(case)
    changed = False
    try:
        with (
            pytest.raises(MigrationRefused) as error,
            observed_read(fixture.engine, monkeypatch, record_property) as observed,
        ):
            _, principal = inspect_consumer_catalog(observed.connection, observed.work)
            assert principal is not None
            assert principal.producer == fixture.expected_principal["producer"]
            with case.pg["owner"].begin() as connection:
                connection.exec_driver_sql(
                    f"REVOKE INSERT ON job_failure_evidence FROM {reader.app_sql}"
                )
            changed = True
            refresh_consumer_principal(observed.connection, observed.work, principal)
        assert changed and error.value.code == "schema_incompatible"
        assert_released(observed)
    finally:
        with case.pg["owner"].begin() as connection:
            connection.exec_driver_sql(f"GRANT INSERT ON job_failure_evidence TO {reader.app_sql}")
        drain_postgres(case.pg)
    assert_same_state(before, whole_state(case))


@pytest.mark.parametrize(
    "dialect", ["sqlite", pytest.param("postgresql", marks=(POSTGRES, F4_POSTGRES))]
)
@pytest.mark.parametrize("mutation", ["revision", "projection", "extra_table"])
def test_native_catalog_history_and_projection_fail_closed_on_actual_source_changes(
    request, tmp_path, monkeypatch, record_property, dialect, mutation
):
    selected_pg = request.getfixturevalue("pg") if dialect == "postgresql" else None
    template = request.getfixturevalue("fresh_sqlite_ar6_template") if selected_pg is None else None
    with consumer_fixture(
        tmp_path,
        monkeypatch,
        record_property,
        pg=selected_pg,
        producer=False,
        template=template,
    ) as fixture:
        case = fixture.case
        before = whole_state(case)
        account = next(
            row for row in before["tables"]["budget_accounts"]["rows"] if row["scope"] == "job"
        )
        owner = case.case.engine
        if mutation == "revision":
            apply_sql = "UPDATE alembic_version SET version_num=:value"
            apply_values, restore_values = {"value": LEDGER}, {"value": FAILURE}
            restore_sql = apply_sql
        elif mutation == "projection":
            apply_sql = "UPDATE budget_accounts SET limit_microusd=:value WHERE id=:id"
            apply_values = {"id": account["id"], "value": account["limit_microusd"] + 1}
            restore_values = {"id": account["id"], "value": account["limit_microusd"]}
            restore_sql = apply_sql
        else:
            apply_sql = "CREATE TABLE f4_unexpected_source(id INTEGER PRIMARY KEY)"
            restore_sql = "DROP TABLE f4_unexpected_source"
            apply_values = restore_values = {}
        applied = False
        try:
            with owner.begin() as connection:
                connection.execute(text(apply_sql), apply_values)
            applied = True
            drain_case(case)
            table_count = 22 if mutation == "extra_table" else 21
            injected = unvalidated_native_state(case, table_count=table_count)
            target_module, target_name = {
                "revision": (failure_consumer, "_actual_revision"),
                "projection": (failure_consumer, "_validate_native_projection"),
                "extra_table": (failure_catalog, "_tables"),
            }[mutation]
            original_gate = getattr(target_module, target_name)
            reached = []

            def actual_gate(*args, **kwargs):
                reached.append(target_name)
                return original_gate(*args, **kwargs)

            with monkeypatch.context() as scoped:
                scoped.setattr(target_module, target_name, actual_gate)
                with (
                    pytest.raises(MigrationRefused) as error,
                    observed_read(fixture.engine, monkeypatch, record_property) as observed,
                ):
                    validated_consumer_history(observed.connection, observed.work)
            assert reached == [target_name]
            assert error.value.code == (
                "ledger_progress_invalid" if mutation == "projection" else "schema_incompatible"
            )
            assert_released(observed)
            assert_same_state(injected, unvalidated_native_state(case, table_count=table_count))
        finally:
            if applied:
                with owner.begin() as connection:
                    connection.execute(text(restore_sql), restore_values)
            drain_case(case)
        assert_same_state(before, whole_state(case))


@pytest.mark.parametrize(
    "dialect", ["sqlite", pytest.param("postgresql", marks=(POSTGRES, F4_POSTGRES))]
)
def test_original_ar7_history_entry_still_refuses_the_successor(
    request, tmp_path, monkeypatch, record_property, dialect
):
    selected_pg = request.getfixturevalue("pg") if dialect == "postgresql" else None
    template = request.getfixturevalue("fresh_sqlite_ar6_template") if selected_pg is None else None
    with consumer_fixture(
        tmp_path,
        monkeypatch,
        record_property,
        pg=selected_pg,
        producer=False,
        template=template,
    ) as fixture:
        before = whole_state(fixture.case)
        with (
            pytest.raises(MigrationRefused) as error,
            observed_read(fixture.engine, monkeypatch, record_property) as observed,
        ):
            validated_ar7_history(observed.connection, observed.work)
        assert error.value.code == "schema_incompatible"
        assert_released(observed)
        assert_same_state(before, whole_state(fixture.case))
