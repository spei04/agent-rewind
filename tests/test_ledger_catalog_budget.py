"""Catalog equivalence and fresh drift checks for bounded SQLite reflection."""

from types import SimpleNamespace

import pytest
from ledger_reader_fixture import complete_ar6, seed_ar7, sqlite_snapshot
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

from agent_rewind.migrations.ledger_reader_catalog import (
    _sqlite_native_indexes,
    inspect_catalog,
)
from agent_rewind.migrations.ledger_transaction import LedgerOutcome, ledger_transaction
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import (
    ADMISSION,
    LEDGER,
    MigrationRefused,
    catalog,
    installed_profile,
)


def original_native_rows(connection, names):
    indexes, parts = [], []
    quote = connection.dialect.identifier_preparer.quote_identifier
    for table in names:
        for index in connection.exec_driver_sql(f"PRAGMA main.index_list({quote(table)})"):
            indexes.append((table, *index))
            for part in connection.exec_driver_sql(f"PRAGMA main.index_xinfo({quote(index[1])})"):
                parts.append((table, index[1], *part))
    return sorted(indexes), sorted(parts)


def observed(case, revision):
    engine = case.operator_engine()
    outcome = LedgerOutcome()
    work = LedgerWork()
    try:
        with ledger_transaction(engine, outcome, work=work) as connection:
            shape = inspect_catalog(connection, revision, work)
        assert outcome.commit_acknowledged and not outcome.cleanup_failed
        return shape
    finally:
        engine.dispose()


@pytest.mark.parametrize("revision", [ADMISSION, LEDGER], ids=["ar6", "ar7"])
@pytest.mark.parametrize("legacy", [False, True], ids=["fresh", "legacy"])
def test_optimized_catalog_keeps_complete_original_and_literal_profile_equality(
    tmp_path, revision, legacy
):
    case = complete_ar6(tmp_path / "catalog.sqlite", legacy=legacy)
    try:
        if revision == LEDGER:
            seed_ar7(case)
        before = sqlite_snapshot(case.path)
        with case.engine.connect() as connection:
            independent = catalog(connection)
            names = sorted(independent)
            original_indexes, original_parts = original_native_rows(connection, names)
            grouped_indexes, grouped_parts = _sqlite_native_indexes(
                connection, names, "ar7" if revision == LEDGER else "ar6", LedgerWork()
            )
        assert (
            sorted((table, *row) for table, rows in grouped_indexes.items() for row in rows)
            == original_indexes
        )
        assert (
            sorted(
                (table, index, *row)
                for (table, index), rows in grouped_parts.items()
                for row in rows
            )
            == original_parts
        )
        assert any(row[4] is None and row[3] == -1 and row[7] == 0 for row in original_parts)
        assert independent == installed_profile("sqlite", revision)
        assert observed(case, revision) == independent
        assert sqlite_snapshot(case.path) == before
    finally:
        case.dispose()


@pytest.mark.parametrize(
    ("index", "replacement"),
    [
        (
            "run_index_project_created_run",
            "CREATE INDEX run_index_project_created_run "
            "ON run_index(project_id,created_at ASC,run_id DESC)",
        ),
        (
            "membership_active_legacy_default",
            "CREATE UNIQUE INDEX membership_active_legacy_default "
            "ON project_memberships(principal_id) WHERE legacy_default=1",
        ),
        (
            "ar7_calls_job_id",
            "CREATE INDEX ar7_calls_job_id ON provider_calls(job_id COLLATE NOCASE)",
        ),
        ("ar7_calls_job_id", "CREATE UNIQUE INDEX ar7_calls_job_id ON provider_calls(job_id)"),
    ],
    ids=["direction", "partial", "collation", "unique"],
)
def test_fresh_catalog_still_rejects_index_drift_after_an_accepted_observation(
    tmp_path, index, replacement
):
    case = seed_ar7(complete_ar6(tmp_path / "drift.sqlite", legacy=False))
    try:
        assert observed(case, LEDGER) == installed_profile("sqlite", LEDGER)
        with case.engine.begin() as connection:
            connection.exec_driver_sql(f'DROP INDEX "{index}"')
            connection.exec_driver_sql(replacement)
        before = sqlite_snapshot(case.path)
        with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
            observed(case, LEDGER)
        assert sqlite_snapshot(case.path) == before
    finally:
        case.dispose()


@pytest.mark.parametrize("size", [65536, 65537], ids=["exact", "one_over"])
def test_ddl_body_is_natively_gated_before_scalar_transfer(monkeypatch, size):
    from agent_rewind.migrations.schema import _sqlite_supported_clauses

    engine = create_engine("sqlite://")
    prefix, suffix = "CREATE TABLE events (run_id TEXT, step INTEGER /*", "*/)"
    ddl = prefix + "x" * (size - len(prefix) - len(suffix)) + suffix
    original = Connection.execute
    transferred = []

    def observe(connection, *args, **kwargs):
        result = original(connection, *args, **kwargs)

        def scalar_one():
            value = result.scalar_one()
            transferred.append(value)
            return value

        return SimpleNamespace(scalar_one=scalar_one)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(ddl)
            actual = connection.exec_driver_sql(
                "SELECT length(CAST(sql AS BLOB)) FROM sqlite_master WHERE name='events'"
            ).scalar_one()
            assert actual == size
            with monkeypatch.context() as patch:
                patch.setattr(Connection, "execute", observe)
                if size == 65536:
                    _sqlite_supported_clauses(connection, ["events"])
                else:
                    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
                        _sqlite_supported_clauses(connection, ["events"])
        assert transferred == ([ddl] if size == 65536 else [None])
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "value", [None, b"CREATE TABLE events(x)", 0, False], ids=["null", "blob", "integer", "bool"]
)
def test_ddl_scalar_must_remain_text(value):
    from agent_rewind.migrations.schema import _sqlite_supported_clauses

    calls = []

    def execute(statement, parameters):
        calls.append((str(statement), parameters))
        return SimpleNamespace(scalar_one=lambda: value)

    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
        _sqlite_supported_clauses(SimpleNamespace(execute=execute), ["events"])
    assert len(calls) == 1


@pytest.mark.parametrize("fault", ["missing", "duplicate", "unknown", "wr", "strict", "bool"])
def test_table_options_batch_rejects_incomplete_or_invalid_rows(fault):
    from agent_rewind.migrations.ledger_reader_catalog import _sqlite_table_options

    names = sorted(installed_profile("sqlite", LEDGER))
    rows = [(name, 0, 0) for name in names]
    if fault == "missing":
        rows.pop()
    elif fault == "duplicate":
        rows[-1] = rows[0]
    elif fault == "unknown":
        rows[-1] = ("not_a_selected_table", 0, 0)
    elif fault == "wr":
        rows[-1] = (names[-1], 1, 0)
    elif fault == "strict":
        rows[-1] = (names[-1], 0, 1)
    else:
        rows[-1] = (names[-1], False, 0)
    connection = SimpleNamespace(exec_driver_sql=lambda sql: SimpleNamespace(all=lambda: rows))
    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
        _sqlite_table_options(connection, names, LEDGER)


def test_table_options_rejects_unowned_names_before_query():
    from agent_rewind.migrations.ledger_reader_catalog import _sqlite_table_options

    def unexpected_query(sql):
        pytest.fail("Unowned table names must never reach SQL construction")

    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
        _sqlite_table_options(
            SimpleNamespace(exec_driver_sql=unexpected_query), ["unowned'"], LEDGER
        )


@pytest.fixture(scope="module")
def original_index_rows(tmp_path_factory):
    case = seed_ar7(complete_ar6(tmp_path_factory.mktemp("native-indexes") / "case.sqlite"))
    try:
        names = sorted(installed_profile("sqlite", LEDGER))
        with case.engine.connect() as connection:
            indexes, parts = original_native_rows(connection, names)
        return names, indexes, parts
    finally:
        case.dispose()


@pytest.mark.parametrize(
    "fault",
    [
        "index_missing",
        "index_overflow",
        "index_duplicate",
        "index_ordinal",
        "index_owner",
        "part_missing",
        "part_overflow",
        "part_duplicate",
        "part_empty_index",
        "part_owner",
        "part_ordinal",
        "part_invalid_null",
        "part_null_collation",
    ],
)
def test_native_index_batch_refuses_incomplete_duplicate_or_misowned_rows(
    original_index_rows, fault
):
    names, original_indexes, original_parts = original_index_rows
    indexes, parts = list(original_indexes), list(original_parts)
    if fault == "index_missing":
        indexes.pop()
    elif fault == "index_overflow":
        indexes.append(indexes[-1])
    elif fault == "index_duplicate":
        indexes[-1] = indexes[0]
    elif fault == "index_ordinal":
        indexes[0] = (indexes[0][0], 999, *indexes[0][2:])
    elif fault == "index_owner":
        indexes[0] = ("unowned_table", *indexes[0][1:])
    elif fault == "part_missing":
        parts.pop()
    elif fault == "part_overflow":
        parts.append(parts[-1])
    elif fault == "part_duplicate":
        parts[-1] = parts[0]
    elif fault == "part_empty_index":
        absent = parts[-1][:2]
        parts = [parts[0] if row[:2] == absent else row for row in parts]
    elif fault == "part_owner":
        parts[0] = ("unowned_table", *parts[0][1:])
    elif fault == "part_ordinal":
        parts[0] = (*parts[0][:2], 999, *parts[0][3:])
    elif fault == "part_invalid_null":
        target = next(i for i, row in enumerate(parts) if row[7] == 1)
        parts[target] = (*parts[target][:4], None, *parts[target][5:])
    else:
        parts[0] = (*parts[0][:6], None, parts[0][7])
    results = iter([indexes, parts])
    connection = SimpleNamespace(
        exec_driver_sql=lambda sql: SimpleNamespace(all=lambda: next(results))
    )
    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
        _sqlite_native_indexes(connection, names, "ar7", LedgerWork())
