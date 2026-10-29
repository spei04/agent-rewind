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
from agent_rewind.migrations.schema import ADMISSION, MigrationRefused, installed_profile

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


def column_rows():
    profile = installed_profile("postgresql", ADMISSION)
    names = sorted(name for name in profile if not name.startswith("$"))
    rows = [
        column(
            table_name=name,
            ordinal=index,
            name=field[0],
            default_expression=None if index % 2 else "'quoted default'::text",
        )
        for name in names
        for index, field in enumerate(profile[name]["columns"], 1)
    ]
    assert len(rows) == 115
    return names, rows


@pytest.mark.parametrize("fault", ["missing", "overfull"])
def test_column_transport_refuses_missing_or_overfull_rows(fault):
    names, rows = column_rows()
    if fault == "missing":
        rows.pop()
    else:
        rows.append(rows[-1])
    connection = SimpleNamespace(
        execute=lambda *args: SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))
    )
    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
        ledger_reader_catalog._postgres_columns(connection, names, "ar6", LedgerWork())


def test_column_query_keeps_observed_names_and_one_bound_row_limit():
    names, rows = column_rows()
    calls = []

    def execute(statement, parameters):
        calls.append((statement, parameters))
        return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))

    observed = ledger_reader_catalog._postgres_columns(
        SimpleNamespace(execute=execute), names, "ar6", LedgerWork()
    )
    assert set(observed) == set(names)
    for name in names:
        native = [row for row in rows if row["table_name"] == name]
        assert [row[0] for row in observed[name]] == [row["name"] for row in native]
        assert [row[3] for row in observed[name]] == [row["default_expression"] for row in native]
    assert len(calls) == 1 and calls[0][1] == {"row_limit": 116}
    compiled = (
        calls[0][0]
        .bindparams(**calls[0][1])
        .compile(dialect=PGDialect_psycopg())
        .construct_expanded_state()
    )
    assert compiled.parameters == {"row_limit": 116}
    assert "ORDER BY c.relname,a.attnum" in compiled.statement
    assert compiled.statement.rstrip().endswith("LIMIT %(row_limit)s::INTEGER")


def test_column_query_rejects_unowned_selected_names_before_sql():
    names, _ = column_rows()
    names[-1] = "quoted'; SELECT 1; --"

    def unexpected(*args):
        pytest.fail("Unowned table selection reached SQL")

    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
        ledger_reader_catalog._postgres_columns(
            SimpleNamespace(execute=unexpected), names, "ar6", LedgerWork()
        )


@pytest.mark.parametrize(
    "fault",
    [
        "unknown-table",
        "table-type",
        "ordinal-bool",
        "ordinal-zero",
        "ordinal-gap",
        "ordinal-duplicate",
        "global-order",
        "duplicate-name",
        "missing-field",
        "extra-field",
        "identity",
        "dropped",
    ],
)
def test_column_batch_rejects_misowned_disordered_or_unsupported_rows(fault):
    names, rows = column_rows()
    index = next(i for i, row in enumerate(rows) if row["ordinal"] == 2)
    if fault == "unknown-table":
        rows[index]["table_name"] = "unowned"
    elif fault == "table-type":
        rows[index]["table_name"] = b"unowned"
    elif fault == "ordinal-bool":
        rows[index]["ordinal"] = True
    elif fault == "ordinal-zero":
        rows[index]["ordinal"] = 0
    elif fault == "ordinal-gap":
        rows[index]["ordinal"] += 1
    elif fault == "ordinal-duplicate":
        rows[index]["ordinal"] -= 1
    elif fault == "global-order":
        first, second = names[:2]
        rows = (
            [row for row in rows if row["table_name"] == second]
            + [row for row in rows if row["table_name"] == first]
            + [row for row in rows if row["table_name"] not in {first, second}]
        )
    elif fault == "duplicate-name":
        rows[index]["name"] = rows[index - 1]["name"]
    elif fault == "missing-field":
        del rows[index]["generated"]
    elif fault == "extra-field":
        rows[index]["unobserved"] = None
    elif fault == "identity":
        rows[index]["identity_kind"] = "a"
    else:
        rows[index]["dropped"] = True
    connection = SimpleNamespace(
        execute=lambda *args: SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))
    )
    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
        ledger_reader_catalog._postgres_columns(connection, names, "ar6", LedgerWork())


@pytest.mark.parametrize("first_count", [32, 33], ids=["exact", "one-over"])
def test_column_batch_preserves_per_table_transport_ceiling(first_count):
    names, _ = column_rows()
    counts = [first_count] + [1] * (len(names) - 1)
    remaining = 115 - sum(counts)
    for index in range(1, len(counts)):
        amount = min(remaining, 31)
        counts[index] += amount
        remaining -= amount
    assert remaining == 0
    rows = [
        column(table_name=name, ordinal=index, name=f"column_{index}")
        for name, count in zip(names, counts, strict=True)
        for index in range(1, count + 1)
    ]
    connection = SimpleNamespace(
        execute=lambda *args: SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))
    )
    if first_count == 32:
        observed = ledger_reader_catalog._postgres_columns(connection, names, "ar6", LedgerWork())
        assert len(observed[names[0]]) == 32 and sum(map(len, observed.values())) == 115
    else:
        with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
            ledger_reader_catalog._postgres_columns(connection, names, "ar6", LedgerWork())


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
        body = "SELECT c.relname::text AS table_name, a.attnum AS ordinal,"
        positive_bodies = [row for row in calls if row[0] == "positive" and row[1].startswith(body)]
        assert len(positive_bodies) == 1 and positive_bodies[0][2] == 1
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
