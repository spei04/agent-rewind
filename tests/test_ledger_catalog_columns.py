"""Column observation within the complete reader's fixed parameter budget."""

import json
from types import SimpleNamespace

import psycopg
import pytest
import test_migrations_postgres as migration_tests
from ledger_reader_fixture import complete_postgres_ar6
from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg
from test_run_projection_postgres import drain

from agent_rewind.migrations import ledger_reader_catalog
from agent_rewind.migrations.ledger_inspection import inspect_ledger_state
from agent_rewind.migrations.ledger_transaction import LedgerOutcome, ledger_transaction
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import ADMISSION, MigrationRefused

pg = migration_tests.pg


def column(**changes):
    return {
        "name": "observed_name",
        "format_type": "character varying(120)",
        "not_null": True,
        "default_expression": None,
        "generated": "",
        "identity_kind": "",
        "dropped": False,
        **changes,
    }


@pytest.mark.parametrize(
    "native,normalized",
    [
        ("bigint", "BIGINT"),
        ("boolean", "BOOLEAN"),
        ("double precision", "DOUBLE PRECISION"),
        ("integer", "INTEGER"),
        ("json", "JSON"),
        ("text", "TEXT"),
        ("timestamp with time zone", "TIMESTAMP WITH TIME ZONE"),
        ("character varying(120)", "VARCHAR(120)"),
        ("character(64)", "CHAR(64)"),
    ],
)
def test_observed_column_type_and_default_are_preserved(native, normalized):
    default = "'a quoted '' value'::text"
    row = column(format_type=native, not_null=False, default_expression=default)
    assert ledger_reader_catalog._postgres_column(row) == [
        "observed_name",
        normalized,
        True,
        default,
        None,
        None,
    ]


@pytest.mark.parametrize(
    "change",
    [
        {"format_type": '"quoted_type"'},
        {"format_type": "public.domain"},
        {"format_type": "integer[]"},
        {"format_type": "character varying(0)"},
        {"format_type": "character varying(0120)"},
        {"format_type": "character varying(120) trailing"},
        {"format_type": b"text"},
        {"name": b"observed_name"},
        {"not_null": 1},
        {"dropped": 0},
        {"dropped": True},
        {"generated": "s"},
        {"identity_kind": "a"},
        {"default_expression": b"0"},
        {"extra": "unobserved"},
    ],
)
def test_unsupported_column_observation_refuses(change):
    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
        ledger_reader_catalog._postgres_column(column(**change))


def test_missing_column_field_refuses():
    row = column()
    del row["generated"]
    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
        ledger_reader_catalog._postgres_column(row)


@pytest.mark.parametrize("count", [0, 33])
def test_column_transport_refuses_missing_or_overfull_rows(count):
    rows = [column() for _ in range(count)]
    connection = SimpleNamespace(
        execute=lambda *args: SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))
    )
    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
        ledger_reader_catalog._postgres_columns(connection, "jobs", LedgerWork())


def test_column_query_keeps_observed_names_and_one_bound_table_parameter():
    rows = [column(name="second"), column(name="first")]
    calls = []

    def execute(statement, parameters):
        calls.append((statement, parameters))
        return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))

    table = "quoted'; SELECT 1; --"
    observed = ledger_reader_catalog._postgres_columns(
        SimpleNamespace(execute=execute), table, LedgerWork()
    )
    assert [row[0] for row in observed] == ["second", "first"]
    assert len(calls) == 1 and calls[0][1] == {"table_name": table}
    compiled = (
        calls[0][0]
        .bindparams(**calls[0][1])
        .compile(dialect=PGDialect_psycopg())
        .construct_expanded_state()
    )
    assert compiled.parameters == {"table_name": table}
    assert table not in compiled.statement
    assert compiled.statement.rstrip().endswith("LIMIT 33")


def test_column_preflight_failure_prevents_body(monkeypatch):
    gates = []

    def gate(connection, revision, name):
        gates.append(name)
        if name == "catalog_column_gate":
            raise MigrationRefused("schema_incompatible")

    def forbidden(*args):
        pytest.fail("Column body must not follow a failed scalar preflight")

    monkeypatch.setattr(ledger_reader_catalog, "_gate", gate)
    monkeypatch.setattr(ledger_reader_catalog, "_postgres_columns", forbidden)
    connection = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql", server_version_info=(16, 15))
    )
    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
        ledger_reader_catalog.inspect_catalog(connection, ADMISSION, LedgerWork())
    assert gates == ["catalog_relation_gate", "catalog_column_count", "catalog_column_gate"]


@pytest.mark.skipif(not migration_tests.POSTGRES, reason="Opt-in PostgreSQL column observation")
@pytest.mark.parametrize(
    "changes",
    [
        ("ALTER TABLE api_keys ALTER COLUMN expires SET DEFAULT 7.5",),
        ("ALTER TABLE api_keys ALTER COLUMN name TYPE VARCHAR(121)",),
        ("COMMENT ON COLUMN api_keys.name IS 'unsupported annotation'",),
        (
            "ALTER TABLE api_keys ADD COLUMN removed_column INTEGER",
            "ALTER TABLE api_keys DROP COLUMN removed_column",
        ),
    ],
    ids=["default", "type", "comment", "dropped"],
)
def test_postgres_column_drift_refuses_before_body(pg, monkeypatch, changes, record_property):
    case = complete_postgres_ar6(pg, legacy=False)
    native_execute = psycopg.Cursor.execute
    calls = []
    phase = ["positive"]

    def execute(cursor, query, *args, **kwargs):
        statement = query.decode() if isinstance(query, bytes) else str(query)
        parameters = args[0] if args else kwargs.get("params")
        calls.append((phase[0], statement, len(parameters) if parameters is not None else 0))
        return native_execute(cursor, query, *args, **kwargs)

    monkeypatch.setattr(psycopg.Cursor, "execute", execute)
    engine = case.operator_engine()
    try:
        positive = LedgerOutcome()
        with ledger_transaction(engine, positive, work=LedgerWork()) as connection:
            state = inspect_ledger_state(connection)
        assert state.model_dump(mode="json") == case.expected
        assert positive.commit_acknowledged and not positive.cleanup_failed
        body = "SELECT a.attname::text AS name,"
        positive_bodies = [row for row in calls if row[0] == "positive" and row[1].startswith(body)]
        assert positive_bodies and all(row[2] == 1 for row in positive_bodies)
        engine.dispose()
        phase[0] = "fixture-drift"
        with case.engine.begin() as connection:
            for statement in changes:
                connection.exec_driver_sql(statement)
        drain(pg)
        engine = case.operator_engine()
        phase[0] = "negative"
        outcome = LedgerOutcome()
        published = []
        with (
            pytest.raises(MigrationRefused, match="^schema_incompatible$"),
            ledger_transaction(engine, outcome, work=LedgerWork()) as connection,
        ):
            published.append(inspect_ledger_state(connection))
        assert not published
        assert outcome.rollback_acknowledged and not outcome.commit_attempted
        assert not outcome.cleanup_failed
        assert not [row for row in calls if row[0] == "negative" and row[1].startswith(body)]
        expected_gate = (
            "SELECT count(*) AS candidate_rows FROM (SELECT c.oid AS relation_oid"
            if len(changes) == 2
            else "WITH expected(table_name,ordinal,column_name"
        )
        assert any(row[0] == "negative" and expected_gate in row[1] for row in calls)
        record_property("column_observation_native", json.dumps(calls))
    finally:
        engine.dispose()
        case.dispose()
