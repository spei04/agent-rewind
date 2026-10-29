"""Catalog equivalence and fresh drift checks for bounded SQLite reflection."""

from types import SimpleNamespace

import pytest
from ledger_reader_fixture import complete_ar6, seed_ar7, sqlite_snapshot
from sqlalchemy import create_engine, event
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
            batches = []

            @event.listens_for(connection, "before_cursor_execute")
            def observe_parameters(conn, cursor, statement, parameters, context, many):
                if statement.startswith(
                    ("SELECT p.name,p.wr,p.strict,", "WITH tables(table_name)")
                ):
                    batches.append((statement, parameters))

            from agent_rewind.migrations.ledger_reader_catalog import _sqlite_table_options

            selected, declarations = _sqlite_table_options(
                connection,
                names,
                revision,
                LedgerWork(),
                admission=revision == ADMISSION,
                ledger=revision == LEDGER,
            )
            assert selected == names
            assert declarations == {
                table: tuple((check["name"], check["sqltext"]) for check in shape["checks"])
                for table, shape in independent.items()
            }
            grouped_indexes, grouped_parts = _sqlite_native_indexes(
                connection, names, "ar7" if revision == LEDGER else "ar6", LedgerWork()
            )
            assert [len(parameters) for _, parameters in batches] == [1, 1, 2]
            assert all(type(value) is int for _, parameters in batches for value in parameters)
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
    rows = [(name, 0, 0, "CREATE TABLE x(value INTEGER)") for name in names]
    if fault == "missing":
        rows.pop()
    elif fault == "duplicate":
        rows[-1] = rows[0]
    elif fault == "unknown":
        rows[-1] = ("not_a_selected_table", 0, 0, rows[-1][3])
    elif fault == "wr":
        rows[-1] = (names[-1], 1, 0, rows[-1][3])
    elif fault == "strict":
        rows[-1] = (names[-1], 0, 1, rows[-1][3])
    else:
        rows[-1] = (names[-1], False, 0, rows[-1][3])
    pending = iter(rows)
    closed = []
    connection = SimpleNamespace(
        execute=lambda sql, params: SimpleNamespace(
            fetchone=lambda: next(pending, None), close=lambda: closed.append(True)
        )
    )
    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
        _sqlite_table_options(connection, names, LEDGER, LedgerWork(), ledger=True)
    assert closed == [True]


def test_table_options_rejects_unowned_names_before_query():
    from agent_rewind.migrations.ledger_reader_catalog import _sqlite_table_options

    def unexpected_query(sql, params):
        pytest.fail("Unowned table names must never reach SQL construction")

    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
        _sqlite_table_options(
            SimpleNamespace(execute=unexpected_query), ["unowned'"], LEDGER, LedgerWork()
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
        execute=lambda sql, params: SimpleNamespace(all=lambda: next(results))
    )
    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
        _sqlite_native_indexes(connection, names, "ar7", LedgerWork())


def test_typed_catalog_names_remain_values_and_limits_remain_native_binds(monkeypatch):
    from agent_rewind.migrations import ledger_reader_catalog as reader

    # Exercise the real three statement builders with hostile compiler inputs.
    # This substitutes a private profile only for compilation; it grants no
    # catalog acceptance to the deliberately unsupported names.
    names = [f"fixture_{number}" for number in range(18)]
    names += ["quoted'); DROP TABLE sentinel; --", "表'名"]
    names.sort()
    captured = []

    def capture(statement, parameters):
        captured.append((statement, parameters))
        rows = (
            [(name, 0, 0, "CREATE TABLE x(value INTEGER)") for name in names]
            if len(captured) == 1
            else []
        )
        pending = iter(rows)
        return SimpleNamespace(
            all=lambda: rows, fetchone=lambda: next(pending, None), close=lambda: None
        )

    with monkeypatch.context() as patch:
        patch.setattr(reader, "installed_profile", lambda dialect, revision: dict.fromkeys(names))
        assert reader._sqlite_table_options(
            SimpleNamespace(execute=capture), names, LEDGER, LedgerWork()
        ) == (names, dict.fromkeys(names, ()))
    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
        reader._sqlite_native_indexes(SimpleNamespace(execute=capture), names, "ar7", LedgerWork())
    assert len(captured) == 3

    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE sentinel (value INTEGER)")
            connection.exec_driver_sql("INSERT INTO sentinel VALUES (7)")
            for (statement, parameters), bound_count in zip(captured, [1, 1, 2], strict=True):
                compiled = statement.compile(dialect=connection.dialect)
                expanded = compiled.construct_expanded_state(parameters)
                assert len(expanded.parameters) == bound_count
                assert all(type(value) is int for value in expanded.parameters.values())
                assert "DROP TABLE sentinel" in expanded.statement
                assert "表''名" in expanded.statement
                assert connection.execute(statement, parameters).all() == []
            assert connection.exec_driver_sql("SELECT value FROM sentinel").all() == [(7,)]
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "order", [("jobs", "audit"), ("audit", "jobs")], ids=["jobs_first", "audit_first"]
)
@pytest.mark.parametrize(
    ("clause", "ddl"),
    [
        ("CHECK", "CREATE TABLE audit (value INTEGER CHECK/*policy_probe*/(1))"),
        ("DEFAULT", "CREATE TABLE audit (value INTEGER DEFAULT 0)"),
        ("AS", "CREATE TABLE audit (value INTEGER, derived INTEGER AS (value+1))"),
    ],
    ids=["check", "default", "as"],
)
def test_sqlite_clause_policy_does_not_leak_jobs_exceptions(
    monkeypatch, record_property, order, clause, ddl
):
    import builtins

    from agent_rewind.migrations import schema

    tables = ["jobs", "audit", "not_a_profile_table"]
    selections, queries = [], []

    class OrderedSelection:
        def __and__(self, allowed):
            members = builtins.set(tables) & allowed
            assert members == {"jobs", "audit"}
            selections.append(sorted(members))
            return tuple(name for name in order if name in members)

    def select_tables(values=()):
        # Control only this exact input's traversal, retaining its native intersection.
        if values is tables:
            return OrderedSelection()
        return builtins.set(values)

    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE jobs (value INTEGER DEFAULT 0 CHECK(value>=0), "
                "derived INTEGER AS (value+1))"
            )
            connection.exec_driver_sql(ddl)

            @event.listens_for(connection, "before_cursor_execute")
            def observe(_connection, _cursor, statement, parameters, _context, _many):
                assert statement == (
                    "SELECT CASE WHEN length(CAST(sql AS BLOB))<=65536 THEN sql END "
                    "FROM sqlite_master WHERE type='table' AND name=?"
                )
                assert len(parameters) == 1
                queries.append(parameters[0])

            try:
                with monkeypatch.context() as patch:
                    patch.setattr(schema, "set", select_tables, raising=False)
                    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
                        schema._sqlite_supported_clauses(connection, tables, ledger=True)
            finally:
                event.remove(connection, "before_cursor_execute", observe)
                record_property("clause", clause)
                record_property("query_order", queries)
                record_property("selected_membership", selections)
                assert selections == [["audit", "jobs"]]
                assert queries == list(order[: order.index("audit") + 1])
    finally:
        engine.dispose()


def test_persisted_inspector_rejects_comment_separated_check_without_restamping(
    tmp_path, record_property, monkeypatch
):
    import sqlite3
    from contextlib import closing

    from agent_rewind.migrations.ledger_inspection import inspect_ledger_state

    case = seed_ar7(complete_ar6(tmp_path / "clause-policy.sqlite", legacy=False))
    profile = installed_profile("sqlite", LEDGER)
    from agent_rewind.migrations import ledger_reader_catalog as reader

    prefix = "SELECT p.name,p.wr,p.strict,"
    original_policy = reader._sqlite_check_supported_ddl

    def inspect_with_trace(outcome, trace):
        engine = case.operator_engine()

        def passive(sql):
            if sql.startswith(prefix):
                if len(trace["queries"]) >= 1 or len(sql) > 2048:
                    trace["overflow"] = True
                else:
                    trace["queries"].append(sql)

        try:
            with ledger_transaction(engine, outcome, work=LedgerWork()) as connection:
                raw = connection.connection.driver_connection
                raw.set_trace_callback(passive)
                try:

                    def observe_policy(table, sql, **flags):
                        trace.setdefault("consumed", []).append(table)
                        return original_policy(table, sql, **flags)

                    with monkeypatch.context() as patch:
                        patch.setattr(reader, "_sqlite_check_supported_ddl", observe_policy)
                        return inspect_ledger_state(connection).model_dump(mode="json")
                finally:
                    raw.set_trace_callback(None)
        finally:
            engine.dispose()

    def observed_order(trace):
        assert not trace["overflow"]
        assert len(trace["queries"]) == 1
        assert "ORDER BY p.name LIMIT 21" in trace["queries"][0]
        # A SQL trace alone cannot prove fetched-row order: observe the original
        # policy call on each consumed row without changing its result/error.
        result = trace["consumed"]
        assert len(result) == len(set(result))
        assert result == sorted(result)
        return result

    try:
        original = sqlite_snapshot(case.path)
        positive = LedgerOutcome()
        positive_trace = {"queries": [], "overflow": False}
        assert inspect_with_trace(positive, positive_trace) == case.expected
        assert positive.commit_acknowledged and not positive.cleanup_failed
        assert not positive.rollback_attempted
        positive_order = observed_order(positive_trace)
        assert set(positive_order) == set(profile)
        assert sqlite_snapshot(case.path) == original
        case.engine.dispose()
        candidate = (
            'CREATE TABLE "audit" ("id" VARCHAR(32) NOT NULL,"created" FLOAT NOT NULL,'
            '"actor" VARCHAR(256) NOT NULL,"action" VARCHAR(80) NOT NULL,'
            '"target" VARCHAR(64) NOT NULL,PRIMARY KEY (id),CHECK/*f1_alias_probe*/(1))'
        )
        # Rebuild only native DDL, retaining every row and the original ar7 provenance.
        with closing(sqlite3.connect(case.path)) as raw:
            raw.execute("PRAGMA foreign_keys=ON")
            before_sql = raw.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='audit'"
            ).fetchone()[0]
            audit_rows = raw.execute(
                "SELECT rowid,id,created,actor,action,target FROM audit ORDER BY rowid"
            ).fetchall()
            raw.execute("BEGIN IMMEDIATE")
            try:
                raw.execute("DROP TABLE audit")
                raw.execute(candidate)
                raw.executemany(
                    "INSERT INTO audit(rowid,id,created,actor,action,target) VALUES(?,?,?,?,?,?)",
                    audit_rows,
                )
                assert (
                    raw.execute(
                        "SELECT rowid,id,created,actor,action,target FROM audit ORDER BY rowid"
                    ).fetchall()
                    == audit_rows
                )
                assert raw.execute("PRAGMA foreign_key_check").fetchall() == []
                assert raw.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
                raw.commit()
            except BaseException:
                raw.rollback()
                raise
        changed = sqlite_snapshot(case.path)
        differences = [
            (left.rstrip(";"), right.rstrip(";"))
            for left, right in zip(original, changed, strict=True)
            if left != right
        ]
        assert differences == [(before_sql, candidate)]
        refused = LedgerOutcome()
        refused_trace = {"queries": [], "overflow": False}
        with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
            inspect_with_trace(refused, refused_trace)
        assert refused.rollback_attempted and refused.rollback_acknowledged
        assert not refused.commit_attempted and not refused.cleanup_failed
        refused_order = observed_order(refused_trace)
        assert refused_order == positive_order[: positive_order.index("audit") + 1]
        assert sqlite_snapshot(case.path) == changed
        record_property("positive_clause_query_order", positive_order)
        record_property("refused_clause_query_order", refused_order)
        record_property("audit_row_count", len(audit_rows))
        record_property("positive_outcome", vars(positive))
        record_property("refused_outcome", vars(refused))
        record_property("only_audit_ddl_changed", True)
        record_property("refusal_preserved_whole_state", True)
    finally:
        case.dispose()


def jobs_check_native_state(case):
    """Retain native scalar types and rowids without ORM decoding."""
    import sqlite3
    from contextlib import closing

    from sqlalchemy import literal_column, select, table

    names = sorted(installed_profile("sqlite", LEDGER))
    rows = {}
    engine = create_engine(case.engine.url)
    try:
        with engine.connect() as connection:
            for name in names:
                statement = (
                    select(literal_column("rowid"), literal_column("*"))
                    .select_from(table(name))
                    .order_by(literal_column("rowid"))
                    .limit(1025)
                )
                values = connection.execute(statement).fetchall()
                assert len(values) <= 1024
                rows[name] = [
                    [
                        (type(value).__name__, value.hex() if type(value) is float else value)
                        for value in row
                    ]
                    for row in values
                ]
    finally:
        engine.dispose()
    with closing(sqlite3.connect(case.path)) as raw:
        master = raw.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name LIMIT 1025"
        ).fetchall()
        assert len(master) <= 1024
        foreign_keys = {
            name: raw.execute('PRAGMA foreign_key_list("' + name + '")').fetchall()
            for name in names
        }
        assert raw.execute("PRAGMA foreign_key_check").fetchall() == []
    return rows, master, foreign_keys


@pytest.mark.parametrize("candidate_kind", ["extra", "compensated"])
def test_persisted_inspector_rejects_unreflected_jobs_checks(
    tmp_path, record_property, candidate_kind
):
    import hashlib
    import sqlite3
    from contextlib import closing

    from sqlalchemy import inspect

    from agent_rewind.migrations.ledger_inspection import inspect_ledger_state

    case = seed_ar7(complete_ar6(tmp_path / "jobs-check.sqlite", legacy=False))
    profile = installed_profile("sqlite", LEDGER)

    def full_inspection(outcome):
        engine = case.operator_engine()
        work = LedgerWork()
        try:
            with ledger_transaction(engine, outcome, work=work) as connection:
                return inspect_ledger_state(connection).model_dump(mode="json")
        finally:
            engine.dispose()
            assert work._detached
            record_property("inspection_ordinary_units", work.observed_ordinary)

    try:
        original_dump = sqlite_snapshot(case.path)
        original_rows, original_master, original_fks = jobs_check_native_state(case)
        with case.engine.connect() as connection:
            assert catalog(connection) == profile
        assert observed(case, LEDGER) == profile
        positive = LedgerOutcome()
        assert full_inspection(positive) == case.expected
        assert positive.commit_acknowledged and not positive.cleanup_failed
        assert not positive.rollback_attempted
        assert jobs_check_native_state(case) == (original_rows, original_master, original_fks)
        case.engine.dispose()

        with closing(sqlite3.connect(case.path)) as raw:
            raw.execute("PRAGMA foreign_keys=ON")
            assert raw.execute("PRAGMA foreign_keys").fetchone() == (1,)
            original_sql = raw.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='jobs'"
            ).fetchone()[0]
            assert hashlib.sha256(original_sql.encode()).hexdigest() == (
                "22eaf8063ff8c236d7ae2e5d900c75b843faf9b2916744e82277f8d222b44a91"
            )
            empty_queries = [
                "SELECT count(*) FROM jobs",
                "SELECT count(*) FROM operations",
                "SELECT count(*) FROM provider_calls",
                "SELECT count(*) FROM budget_entries",
                "SELECT count(*) FROM operation_keys",
                "SELECT count(*) FROM resource_scopes WHERE resource_kind='job'",
                "SELECT count(*) FROM budget_accounts WHERE job_id IS NOT NULL OR scope='job'",
                "SELECT count(*) FROM artifact_refs WHERE owner_kind='job'",
            ]
            assert all(raw.execute(query).fetchone() == (0,) for query in empty_queries)
            assert sorted(
                name for name, keys in original_fks.items() if any(key[2] == "jobs" for key in keys)
            ) == ["operations", "provider_calls"]
            objects = raw.execute(
                "SELECT type,name,sql FROM sqlite_master WHERE tbl_name='jobs' ORDER BY type,name"
            ).fetchall()
            assert objects == [
                ("index", "sqlite_autoindex_jobs_1", None),
                ("table", "jobs", original_sql),
            ]
            if candidate_kind == "extra":
                assert original_sql.endswith(")")
                candidate = (
                    original_sql[:-1] + ",\n    CHECK/*review*/(budget<9223372036854775807)\n)"
                )
                assert hashlib.sha256(candidate.encode()).hexdigest() == (
                    "6b1a844818e3d9266d56a14268508f4643798c742318454363df417297b94a45"
                )
            else:
                expression = next(
                    check["sqltext"]
                    for check in profile["jobs"]["checks"]
                    if check["name"] == "ar7_jobs_generation"
                )
                declaration = "CONSTRAINT ar7_jobs_generation CHECK(" + expression + ")"
                assert original_sql.count(declaration) == 1
                candidate = original_sql.replace(
                    declaration,
                    "CONSTRAINT ar7_jobs_generation CHECK/*review*/(1) /* " + declaration + " */",
                )
            raw.execute("BEGIN IMMEDIATE")
            try:
                raw.execute("DROP TABLE jobs")
                raw.execute(candidate)
                assert raw.execute("PRAGMA foreign_key_check").fetchall() == []
                assert raw.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
                raw.commit()
            except BaseException:
                raw.rollback()
                raise

        changed_dump = sqlite_snapshot(case.path)
        assert [
            (left, right)
            for left, right in zip(original_dump, changed_dump, strict=True)
            if left != right
        ] == [(original_sql + ";", candidate + ";")]
        changed_rows, changed_master, changed_fks = jobs_check_native_state(case)
        assert changed_rows == original_rows and changed_fks == original_fks
        assert [
            (left, right)
            for left, right in zip(original_master, changed_master, strict=True)
            if left != right
        ] == [(("table", "jobs", "jobs", original_sql), ("table", "jobs", "jobs", candidate))]

        # Both attacks preserve the vulnerable reflected shape; count equality
        # cannot establish which real declaration supplied a reflected expression.
        engine = create_engine(case.engine.url)
        try:
            with engine.connect() as connection:
                assert (
                    inspect(connection).get_check_constraints("jobs") == profile["jobs"]["checks"]
                )
        finally:
            engine.dispose()
        refused = LedgerOutcome()
        with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
            full_inspection(refused)
        assert refused.rollback_attempted and refused.rollback_acknowledged
        assert not refused.commit_attempted and not refused.cleanup_failed
        engine = create_engine(case.engine.url)
        try:
            with (
                engine.connect() as connection,
                pytest.raises(MigrationRefused, match="^schema_incompatible$"),
            ):
                catalog(connection)
        finally:
            engine.dispose()
        with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
            observed(case, LEDGER)
        assert sqlite_snapshot(case.path) == changed_dump
        assert jobs_check_native_state(case) == (changed_rows, changed_master, changed_fks)
        record_property("candidate_kind", candidate_kind)
        record_property("positive_outcome", vars(positive))
        record_property("refused_outcome", vars(refused))
        record_property("only_jobs_ddl_changed", True)
        record_property("typed_rows_rowids_and_provenance_preserved", True)
    finally:
        case.dispose()


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ("x INTEGER CONSTRAINT nn NOT NULL CHECK(x>0)", ((None, "x>0"),)),
        ("x INTEGER CONSTRAINT ar7_jobs_generation CHECK(x>0)", (("ar7_jobs_generation", "x>0"),)),
        (
            "x INTEGER, CONSTRAINT fk FOREIGN KEY(x) REFERENCES parent(x), CHECK(x>0)",
            ((None, "x>0"),),
        ),
        (
            "x INTEGER CONSTRAINT c CHECK(x>0) CHECK(x<9)",
            (("c", "x>0"), (None, "x<9")),
        ),
        ("x INTEGER CONSTRAINT nn UNIQUE, CHECK(x>0)", ((None, "x>0"),)),
        (
            "\"CHECK()\" INTEGER, x INTEGER CHECK((x>0) AND length(')CHECK(')>0)",
            ((None, "(x>0) AND length(')CHECK(')>0"),),
        ),
        ("x TEXT CHECK(x!='it''s)CHECK(')", ((None, "x!='it''s)CHECK('"),)),
        ("x TEXT CHECK(x!='back\\slash')", ((None, "x!='back\\slash'"),)),
        (
            "x INTEGER, CONSTRAINT/*one*/ c /*two*/CHECK/*three*/( x>0 )",
            (("c", "x>0"),),
        ),
        ("x INTEGER /* CHECK(0) */, CHECK(x>0) -- CHECK(0)\n", ((None, "x>0"),)),
        (
            'x INTEGER, CHECK(x!=3), CONSTRAINT "~" CHECK(x!=4), '
            'CONSTRAINT "" CHECK(x!=5), CONSTRAINT same CHECK(x>0), '
            "CONSTRAINT same CHECK(x<9)",
            (("same", "x>0"), ("same", "x<9"), (None, "x!=3"), ("~", "x!=4"), ("", "x!=5")),
        ),
        ('x INTEGER, CONSTRAINT "a""b" CHECK(x>0)', (('a"b', "x>0"),)),
        ("x INTEGER, CONSTRAINT `a``b` CHECK(x>0)", (("a`b", "x>0"),)),
        ("x INTEGER, CONSTRAINT [name] CHECK(x>0)", (("name", "x>0"),)),
    ],
    ids=[
        "name-not-carried-past-not-null",
        "full-ar7-identifier",
        "name-not-carried-past-foreign-key",
        "name-not-carried-past-check",
        "name-not-carried-past-comma",
        "quoted-identifier-and-nested-string",
        "doubled-string-quote",
        "backslash-is-not-an-escape",
        "interstitial-comments",
        "comment-decoys",
        "stable-duplicate-and-anonymous-order",
        "doubled-identifier-quote",
        "doubled-backtick",
        "bracket-name",
    ],
)
def test_native_check_declarations_preserve_names_bodies_and_order(fields, expected):
    from agent_rewind.migrations.schema import _sqlite_check_declarations

    assert _sqlite_check_declarations('CREATE TABLE "CHECK(table)" (' + fields + ")") == expected


@pytest.mark.parametrize(
    "tail",
    [
        "CHECK",
        "CHECK x>0",
        "CHECK(",
        "CHECK()",
        "CHECK((x>0)",
        "CHECK(x='unterminated)",
        "CHECK(x>0 /* unterminated)",
        'CONSTRAINT "unterminated CHECK(x>0)',
        "CONSTRAINT [unterminated CHECK(x>0)",
        "CONSTRAINT `unterminated CHECK(x>0)",
        "CONSTRAINT",
        "CONSTRAINT named",
        "CONSTRAINT named, CHECK(x>0)",
        "CHECK(x>0))",
    ],
    ids=[
        "missing-opening-at-end",
        "missing-opening",
        "missing-body",
        "empty-body",
        "unbalanced-body",
        "unterminated-string",
        "unterminated-comment",
        "unterminated-double-name",
        "unterminated-bracket-name",
        "unterminated-backtick-name",
        "missing-name",
        "missing-named-constraint",
        "detached-name",
        "unbalanced-table",
    ],
)
def test_native_check_declarations_refuse_malformed_tail_without_returning_prefix(tail):
    from agent_rewind.migrations.schema import _sqlite_check_declarations

    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
        _sqlite_check_declarations("CREATE TABLE t (x INTEGER CHECK(x<9), " + tail + ")")


@pytest.mark.parametrize(
    ("fields", "matches"),
    [
        ('x INTEGER, CONSTRAINT "named" CHECK(x>0)', True),
        ("x INTEGER, CONSTRAINT [named] CHECK(x>0)", True),
        ("x INTEGER, CONSTRAINT `named` CHECK(x>0)", True),
        ("x INTEGER, CONSTRAINT 'named' CHECK(x>0)", True),
        ("x INTEGER, CHECK/*hidden*/(x>0)", False),
        ("x INTEGER, CHECK(x>0 /* ) */)", False),
        ('x INTEGER, CONSTRAINT "a""b" CHECK(x>0)', False),
        ("x INTEGER, CONSTRAINT same CHECK/*hidden*/(1) /* CONSTRAINT same CHECK(x>0) */", False),
    ],
    ids=[
        "double-name",
        "bracket-name",
        "backtick-name",
        "single-name",
        "hidden-check",
        "comment-parenthesis",
        "escaped-name-representation",
        "equal-count-spoof",
    ],
)
def test_native_check_correspondence_uses_actual_sqlite_and_pinned_reflection(fields, matches):
    from sqlalchemy import inspect

    from agent_rewind.migrations.schema import (
        _sqlite_check_declarations,
        _sqlite_require_reflected_checks,
    )

    ddl = "CREATE TABLE t (" + fields + ")"
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(ddl)
            native = _sqlite_check_declarations(ddl)
            reflected = inspect(connection).get_check_constraints("t")
            if matches:
                _sqlite_require_reflected_checks(native, reflected)
            else:
                with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
                    _sqlite_require_reflected_checks(native, reflected)
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "reflected",
    [
        None,
        ({"name": None, "sqltext": "x>0"},),
        [],
        [{"name": None}],
        [{"name": None, "sqltext": "x>0", "extra": None}],
        [{"name": False, "sqltext": "x>0"}],
        [{"name": None, "sqltext": 1}],
        [{"name": "", "sqltext": "x>0"}],
        [{"name": None, "sqltext": " x>0 "}],
    ],
    ids=[
        "null",
        "tuple",
        "missing",
        "missing-key",
        "extra-key",
        "nontext-name",
        "nontext-body",
        "empty-is-not-anonymous",
        "no-body-normalization",
    ],
)
def test_native_check_correspondence_refuses_malformed_or_changed_reflection(reflected):
    from agent_rewind.migrations.schema import _sqlite_require_reflected_checks

    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
        _sqlite_require_reflected_checks(((None, "x>0"),), reflected)


def test_native_check_correspondence_retains_duplicate_multiplicity_and_tie_order():
    from agent_rewind.migrations.schema import _sqlite_require_reflected_checks

    native = (("same", "x>0"), ("same", "x<9"), (None, "x!=3"), ("~", "x!=4"))
    original = [{"name": name, "sqltext": body} for name, body in native]
    _sqlite_require_reflected_checks(native, original)
    for changed in (
        [original[1], original[0], *original[2:]],
        [*original[:2], original[3], original[2]],
        original[:-1],
        [*original, original[-1]],
    ):
        with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
            _sqlite_require_reflected_checks(native, changed)


@pytest.mark.parametrize("size", [65536, 65537], ids=["exact", "one_over"])
@pytest.mark.parametrize("padding", ["x", "表"], ids=["ascii", "utf8"])
def test_fused_ddl_body_is_gated_before_native_transfer(monkeypatch, size, padding):
    from agent_rewind.migrations import ledger_reader_catalog as reader

    prefix, suffix = "CREATE TABLE events (value INTEGER /*", "*/)"
    available = size - len((prefix + suffix).encode())
    ddl = prefix + padding * (available // len(padding.encode()))
    ddl += "x" * (available % len(padding.encode())) + suffix
    assert len(ddl.encode()) == size
    engine = create_engine("sqlite://")
    original = Connection.execute
    transfers, closed, native_binds = [], [], []

    def observe(connection, statement, parameters):
        result = original(connection, statement, parameters)

        def fetchone():
            row = result.fetchone()
            transfers.append(None if row is None else tuple(row))
            return row

        def close():
            closed.append(True)
            result.close()

        return SimpleNamespace(fetchone=fetchone, close=close)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(ddl)

            @event.listens_for(connection, "before_cursor_execute")
            def binds(_conn, _cursor, _statement, parameters, _context, _many):
                native_binds.append(parameters)

            with monkeypatch.context() as patch:
                # A private one-table profile isolates transport, not catalog acceptance.
                patch.setattr(reader, "installed_profile", lambda *_: {"events": {}})
                patch.setattr(Connection, "execute", observe)
                if size == 65536:
                    assert reader._sqlite_table_options(
                        connection, ["events"], LEDGER, LedgerWork()
                    ) == (["events"], {"events": ()})
                else:
                    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
                        reader._sqlite_table_options(connection, ["events"], LEDGER, LedgerWork())
            event.remove(connection, "before_cursor_execute", binds)
        assert transfers == (
            [("events", 0, 0, ddl), None] if size == 65536 else [("events", 0, 0, None)]
        )
        assert native_binds == [(2,)]
        assert closed == [True]
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "fault",
    [
        "empty",
        "overflow",
        "reordered",
        "name_blob",
        "short",
        "long",
        "strict_bool",
        "ddl_null",
        "ddl_blob",
        "ddl_integer",
        "ddl_bool",
        "ddl_overflow",
    ],
)
def test_fused_table_rows_refuse_visible_shape_and_sentinel_faults(fault):
    from agent_rewind.migrations.ledger_reader_catalog import _sqlite_table_options

    names = sorted(installed_profile("sqlite", LEDGER))
    ddl = "CREATE TABLE x(value INTEGER)"
    rows = [(name, 0, 0, ddl) for name in names]
    if fault == "empty":
        rows = []
    elif fault == "overflow":
        rows.append(rows[-1])
    elif fault == "reordered":
        rows[:2] = reversed(rows[:2])
    elif fault == "name_blob":
        rows[0] = (names[0].encode(), 0, 0, ddl)
    elif fault == "short":
        rows[0] = rows[0][:-1]
    elif fault == "long":
        rows[0] = (*rows[0], None)
    elif fault == "strict_bool":
        rows[0] = (names[0], 0, False, ddl)
    else:
        body = {
            "ddl_null": None,
            "ddl_blob": ddl.encode(),
            "ddl_integer": 0,
            "ddl_bool": False,
            "ddl_overflow": ddl + " " * 65536,
        }[fault]
        rows[0] = (*rows[0][:3], body)
    pending = iter(rows)
    fetched, closed = [], []

    def fetchone():
        row = next(pending, None)
        fetched.append(row)
        return row

    connection = SimpleNamespace(
        execute=lambda *_: SimpleNamespace(fetchone=fetchone, close=lambda: closed.append(True))
    )
    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
        _sqlite_table_options(connection, names, LEDGER, LedgerWork(), ledger=True)
    assert closed == [True]
    assert len(fetched) <= len(names) + 1
    assert len(fetched) == (len(names) + 1 if fault == "overflow" else 1)


@pytest.mark.parametrize("primary_stage", ["none", "fetch", "parser", "work"])
def test_fused_cursor_close_preserves_primary_and_prevents_reflection(monkeypatch, primary_stage):
    from agent_rewind.migrations import ledger_reader_catalog as reader

    primary = KeyboardInterrupt("original") if primary_stage == "fetch" else RuntimeError("primary")
    close_error = RuntimeError("close")
    closed, called = [], []
    pending = iter([("jobs", 0, 0, "CREATE TABLE jobs(value INTEGER)")])

    def fetchone():
        if primary_stage == "fetch":
            raise primary
        return next(pending, None)

    def close():
        closed.append(True)
        raise close_error

    def policy(*args, **kwargs):
        if primary_stage == "parser":
            raise primary
        return ()

    def check():
        if primary_stage == "work":
            raise primary

    def later(*args):
        pytest.fail("Reflection/native indexes must not execute after failed cursor closure")

    with monkeypatch.context() as patch:
        patch.setattr(reader, "dialect", lambda _: "sqlite")
        patch.setattr(reader, "inspect", lambda _: SimpleNamespace(get_columns=later))
        patch.setattr(reader, "schema_table_names", lambda _: (["jobs"], LEDGER))
        patch.setattr(reader, "installed_profile", lambda *_: {"jobs": {}})
        patch.setattr(reader, "_sqlite_check_supported_ddl", policy)
        patch.setattr(reader, "_sqlite_native_indexes", later)
        connection = SimpleNamespace(
            execute=lambda *_: SimpleNamespace(fetchone=fetchone, close=close),
            exec_driver_sql=lambda sql: (called.append(sql) or SimpleNamespace(first=lambda: None)),
        )
        expected = close_error if primary_stage == "none" else primary
        with pytest.raises(BaseException) as caught:
            reader._observe_catalog(connection, {}, "ar7", SimpleNamespace(check=check))
        assert caught.value is expected
    assert closed == [True]
    assert called == [
        "SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view') LIMIT 1",
        "SELECT 1 FROM sqlite_temp_master LIMIT 1",
    ]


@pytest.mark.parametrize(
    ("expected", "observed_revision", "flags", "accepted"),
    [
        ("ar7", ADMISSION, {"admission": True, "ledger": False}, True),
        ("ar6", LEDGER, {"admission": False, "ledger": True}, True),
        ("ar7", None, {"admission": False, "ledger": False}, False),
    ],
    ids=["observed_ar6", "observed_ar7", "unverified"],
)
def test_fused_policy_uses_observed_revision_flags(
    monkeypatch, expected, observed_revision, flags, accepted
):
    from agent_rewind.migrations import ledger_reader_catalog as reader

    original = reader._sqlite_check_supported_ddl
    witnessed, closed = [], []
    stop = RuntimeError("observation reached native indexes")

    def policy(table, ddl, **actual):
        witnessed.append(actual)
        return original(table, ddl, **actual)

    def later(*_):
        raise stop

    pending = iter([("jobs", 0, 0, "CREATE TABLE jobs(value INTEGER CHECK(value>0))")])
    with monkeypatch.context() as patch:
        patch.setattr(reader, "dialect", lambda _: "sqlite")
        patch.setattr(reader, "inspect", lambda _: None)
        patch.setattr(reader, "schema_table_names", lambda _: (["jobs"], observed_revision))
        patch.setattr(reader, "installed_profile", lambda *_: {"jobs": {}})
        patch.setattr(reader, "_sqlite_check_supported_ddl", policy)
        patch.setattr(reader, "_sqlite_native_indexes", later)
        connection = SimpleNamespace(
            execute=lambda *_: SimpleNamespace(
                fetchone=lambda: next(pending, None), close=lambda: closed.append(True)
            ),
            exec_driver_sql=lambda _: SimpleNamespace(first=lambda: None),
        )
        with pytest.raises(RuntimeError) as caught:
            reader._observe_catalog(connection, {}, expected, LedgerWork())
        if accepted:
            assert caught.value is stop
        else:
            assert isinstance(caught.value, MigrationRefused)
            assert caught.value.code == "schema_incompatible"
    assert witnessed == [flags]
    assert closed == [True]


@pytest.mark.parametrize(
    ("table", "clause", "flags", "allowed"),
    [
        ("audit", "CHECK(value>0)", {}, False),
        ("jobs", "DEFAULT 0 CHECK(value>=0)", {"admission": True}, True),
        ("jobs", "DEFAULT 0 CHECK(value>=0)", {"ledger": True}, True),
        ("jobs", "DEFAULT 0 CHECK(value>=0)", {}, False),
        ("alembic_version", "CHECK(value>0)", {}, True),
        ("alembic_version", "DEFAULT 0", {}, False),
        ("project_memberships", "DEFAULT 0 REFERENCES parent(value)", {}, True),
        ("artifact_refs", "DEFAULT 0 REFERENCES parent(value)", {}, True),
        ("run_index", "DEFAULT 0 REFERENCES parent(value)", {}, True),
        ("operations", "DEFAULT 0 REFERENCES parent(value)", {}, True),
        ("budget_accounts", "DEFAULT 0 REFERENCES parent(value)", {"ledger": True}, True),
        ("budget_accounts", "DEFAULT 0 REFERENCES parent(value)", {}, False),
        ("budget_accounts", "COLLATE NOCASE", {"ledger": True}, False),
    ],
)
def test_fused_policy_retains_table_specific_native_restrictions(
    monkeypatch, table, clause, flags, allowed
):
    from agent_rewind.migrations import ledger_reader_catalog as reader

    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(f'CREATE TABLE "{table}"(value INTEGER {clause})')
            with monkeypatch.context() as patch:
                patch.setattr(reader, "installed_profile", lambda *_: {table: {}})
                if allowed:
                    selected, checks = reader._sqlite_table_options(
                        connection, [table], LEDGER, LedgerWork(), **flags
                    )
                    assert selected == [table]
                    assert checks == {
                        table: ((None, "value>=0"),)
                        if table == "jobs"
                        else ((None, "value>0"),)
                        if table == "alembic_version"
                        else ()
                    }
                else:
                    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
                        reader._sqlite_table_options(
                            connection, [table], LEDGER, LedgerWork(), **flags
                        )
    finally:
        engine.dispose()
