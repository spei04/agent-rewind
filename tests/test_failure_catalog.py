"""Failure-catalog refusal boundaries; profiles come from independent native capture."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
import test_ledger_constraints_postgres as ledger_pg_tests
import test_migrations_postgres as migration_tests
from ledger_reader_fixture import complete_ar6, seed_ar7, sqlite_snapshot
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection
from sqlalchemy.engine.reflection import Inspector
from test_failure_schema import rows

from agent_rewind.migrations import failure_catalog as reader
from agent_rewind.migrations.compatibility import check_schema_compatibility, load_release_profile
from agent_rewind.migrations.failure_schema import create_failure_schema
from agent_rewind.migrations.schema import LEDGER, MigrationRefused, catalog, installed_profile

ledger_pg = ledger_pg_tests.ledger_pg
pg = migration_tests.pg


class Checks:
    def __init__(self):
        self.calls = 0

    def check(self):
        self.calls += 1


@pytest.fixture
def successor(tmp_path, fresh_sqlite_ar6_template):
    case = seed_ar7(fresh_sqlite_ar6_template.copy_to(tmp_path / "failure.sqlite"))
    with case.engine.begin() as connection:
        create_failure_schema(connection)
    try:
        yield case
    finally:
        case.dispose()


@pytest.mark.parametrize("legacy", [False, True], ids=["fresh", "legacy"])
def test_complete_successor_precedes_retained_projection(tmp_path, legacy, record_property):
    case = seed_ar7(complete_ar6(tmp_path / "complete.sqlite", legacy=legacy))
    try:
        with case.engine.begin() as connection:
            predecessor_rows = rows(connection)
            create_failure_schema(connection)
        before = sqlite_snapshot(case.path)
        statements = []
        checks = Checks()
        with case.engine.connect() as connection:

            def observed(_conn, _cursor, statement, parameters, _context, _many):
                statements.append((statement, len(parameters)))

            event.listen(connection, "before_cursor_execute", observed)
            try:
                value = reader.inspect_failure_catalog(connection, checks)
            finally:
                event.remove(connection, "before_cursor_execute", observed)
            assert value.catalog == reader._profile("sqlite")
            assert value.retained_ar7 == installed_profile("sqlite", LEDGER)
            assert len([key for key in value.catalog if not key.startswith("$")]) == 21
            assert len(value.catalog["$executables"]["triggers"]) == 3
            assert value.catalog["job_failure_evidence"]["pk"] == ["job_id"]
            assert rows(connection) == predecessor_rows | {"job_failure_evidence": []}
            with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
                catalog(connection)
            assert (
                check_schema_compatibility(connection, load_release_profile()).code
                == "schema_incompatible"
            )
            value.retained_ar7["jobs"]["columns"].clear()
            assert value.catalog["jobs"]["columns"]
        assert sqlite_snapshot(case.path) == before
        assert checks.calls > 21
        assert max(size for _sql, size in statements) <= 16
        record_property(
            "catalog_component_observation",
            json.dumps(
                {
                    "sql_statements": len(statements),
                    "check_calls": checks.calls,
                    "maximum_native_binds": max(size for _sql, size in statements),
                    "whole_transaction_work_fit": False,
                },
                sort_keys=True,
            ),
        )
    finally:
        case.dispose()


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_table",
        "extra_table",
        "missing_support",
        "changed_support",
        "missing_trigger",
        "extra_trigger",
        "changed_trigger",
        "changed_check",
        "extra_view",
        "temporary",
        "index_sort",
        "index_collation",
    ],
)
def test_native_catalog_drift_refuses_without_projecting_or_writing(
    successor, mutation, monkeypatch
):
    with successor.engine.begin() as connection:
        if mutation == "missing_table":
            connection.exec_driver_sql("DROP TABLE job_failure_evidence")
        elif mutation == "extra_table":
            connection.exec_driver_sql("CREATE TABLE extra_catalog_relation (value INTEGER)")
        elif mutation == "missing_support":
            connection.exec_driver_sql("DROP INDEX job_failure_operation_binding_uq")
        elif mutation == "changed_support":
            connection.exec_driver_sql("DROP INDEX job_failure_operation_binding_uq")
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX job_failure_operation_binding_uq ON "
                "operations(id,project_id,job_id)"
            )
        elif mutation in {"missing_trigger", "changed_trigger"}:
            connection.exec_driver_sql("DROP TRIGGER job_failure_evidence_update_guard")
            if mutation == "changed_trigger":
                connection.exec_driver_sql(
                    "CREATE TRIGGER job_failure_evidence_update_guard BEFORE UPDATE "
                    "ON job_failure_evidence BEGIN SELECT 1; END"
                )
        elif mutation == "extra_trigger":
            connection.exec_driver_sql(
                "CREATE TRIGGER extra_guard BEFORE INSERT ON job_failure_evidence "
                "BEGIN SELECT 1; END"
            )
        elif mutation == "extra_view":
            connection.exec_driver_sql("CREATE VIEW extra_view AS SELECT 1")
        elif mutation == "temporary":
            connection.exec_driver_sql("CREATE TEMP TABLE extra_temporary(value INTEGER)")
        elif mutation == "changed_check":
            ddl = connection.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE name='job_failure_evidence'"
            ).scalar_one()
            assert "schema_version BETWEEN 1 AND 1" in ddl
            triggers = (
                connection.exec_driver_sql(
                    "SELECT sql FROM sqlite_master WHERE type='trigger' AND "
                    "tbl_name='job_failure_evidence'"
                )
                .scalars()
                .all()
            )
            connection.exec_driver_sql("DROP TABLE job_failure_evidence")
            connection.exec_driver_sql(
                ddl.replace("schema_version BETWEEN 1 AND 1", "schema_version BETWEEN 1 AND 2", 1)
            )
            for trigger in triggers:
                connection.exec_driver_sql(trigger)
        else:
            connection.exec_driver_sql("DROP INDEX run_index_project_created_run")
            suffix = (
                "project_id,created_at ASC,run_id DESC"
                if mutation == "index_sort"
                else "project_id COLLATE NOCASE,created_at DESC,run_id DESC"
            )
            connection.exec_driver_sql(
                "CREATE INDEX run_index_project_created_run ON run_index(" + suffix + ")"
            )
        state = rows(connection)
        projected = []
        original = reader._project_ar7

        def project(shape, name):
            projected.append(shape)
            return original(shape, name)

        with monkeypatch.context() as patch:
            patch.setattr(reader, "_project_ar7", project)
            with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
                reader.inspect_failure_catalog(connection, Checks())
        assert len(projected) == 1  # source profile only; never a refused observation
        assert rows(connection) == state


@pytest.mark.parametrize("fault", ["missing", "body", "name", "extra"])
def test_native_check_and_reflected_check_must_correspond(successor, monkeypatch, fault):
    original = Inspector.get_check_constraints

    def changed(self, table, *args, **kwargs):
        value = original(self, table, *args, **kwargs)
        if table == "job_failure_evidence":
            value = deepcopy(value)
            if fault == "missing":
                value.pop()
            elif fault == "extra":
                value.append(deepcopy(value[-1]))
            else:
                value[0]["sqltext" if fault == "body" else "name"] += "_changed"
        return value

    before = sqlite_snapshot(successor.path)
    with monkeypatch.context() as patch:
        patch.setattr(Inspector, "get_check_constraints", changed)
        with (
            successor.engine.connect() as connection,
            pytest.raises(MigrationRefused, match="^schema_incompatible$"),
        ):
            reader.inspect_failure_catalog(connection, Checks())
    assert sqlite_snapshot(successor.path) == before


@pytest.mark.parametrize("size", [65536, 65537], ids=["exact", "one_over"])
@pytest.mark.parametrize("padding", ["x", "表"], ids=["ascii", "utf8"])
def test_ddl_per_table_gate_precedes_body_transfer(monkeypatch, size, padding):
    prefix, suffix = "CREATE TABLE events (value INTEGER /*", "*/)"
    available = size - len((prefix + suffix).encode())
    ddl = prefix + padding * (available // len(padding.encode()))
    ddl += "x" * (available % len(padding.encode())) + suffix
    assert len(ddl.encode()) == size
    engine = create_engine("sqlite://")
    original = Connection.execute
    transfers, closed = [], []

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
            with monkeypatch.context() as patch:
                patch.setattr(Connection, "execute", observe)
                if size == 65536:
                    assert reader._sqlite_table_options(connection, ["events"], Checks()) == (
                        ["events"],
                        {"events": ()},
                    )
                else:
                    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
                        reader._sqlite_table_options(connection, ["events"], Checks())
        assert transfers == (
            [("events", 0, 0, ddl), None] if size == 65536 else [("events", 0, 0, None)]
        )
        assert closed == [True]
    finally:
        engine.dispose()


@pytest.mark.parametrize("total", [1310720, 1310721], ids=["exact", "one_over"])
def test_native_aggregate_ddl_gate_precedes_reflection(successor, total, monkeypatch):
    with successor.engine.begin() as connection:
        original = connection.exec_driver_sql(
            "SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name"
        ).all()
        lengths = [total // 21 + (index < total % 21) for index in range(21)]
        assert max(lengths) <= 65536
        connection.exec_driver_sql("PRAGMA writable_schema=ON")
        try:
            for (name, ddl), size in zip(original, lengths, strict=True):
                assert len(ddl.encode()) < size
                connection.execute(
                    text("UPDATE sqlite_master SET sql=:ddl WHERE type='table' AND name=:name"),
                    {"ddl": ddl + " " * (size - len(ddl.encode())), "name": name},
                )
        finally:
            connection.exec_driver_sql("PRAGMA writable_schema=OFF")
        observed = connection.exec_driver_sql(
            "SELECT max(length(CAST(sql AS BLOB))),sum(length(CAST(sql AS BLOB))) "
            "FROM sqlite_master WHERE type='table'"
        ).one()
        assert observed == (max(lengths), total)

        def forbidden(*_args, **_kwargs):
            pytest.fail("aggregate refusal must precede reflection/body observation")

        if total == 1310720:
            reader._sqlite_gates(connection, Checks())
        else:
            with monkeypatch.context() as patch:
                patch.setattr(reader, "_observe", forbidden)
                with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
                    reader.inspect_failure_catalog(connection, Checks())


@pytest.mark.parametrize("fault", ["missing", "overflow", "reordered", "blob", "null"])
def test_21_table_identity_requires_complete_ordered_native_rows(fault):
    expected = [f"table_{index:02d}" for index in range(21)]
    values = [(name,) for name in expected]
    if fault == "missing":
        values.pop()
    elif fault == "overflow":
        values.append(("table_22",))
    elif fault == "reordered":
        values.reverse()
    else:
        values[0] = (b"table_00" if fault == "blob" else None,)
    connection = SimpleNamespace(exec_driver_sql=lambda _sql: SimpleNamespace(all=lambda: values))
    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
        reader._tables(connection, "sqlite", expected)


@pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL failure catalog"
)
@pytest.mark.parametrize(
    "mutation",
    [
        "public_execute",
        "null_function_acl",
        "table_write",
        "column_grant",
        "default_public",
        "security_definer",
        "missing_trigger",
        "disabled_trigger",
        "extra_function",
        "changed_support",
        "changed_check",
        "constraint_comment",
        "extra_table",
    ],
)
def test_postgres_native_authority_and_structure_refuse(ledger_pg, mutation, record_property):
    engine, role = ledger_pg["owner"], ledger_pg["app_role"]
    with engine.begin() as connection:
        create_failure_schema(connection)
        accepted = reader.inspect_failure_catalog(connection, Checks())
        assert accepted.retained_ar7 == installed_profile("postgresql", LEDGER)
        quoted = connection.dialect.identifier_preparer.quote_identifier(role)
        if mutation == "public_execute":
            sql = "GRANT EXECUTE ON FUNCTION job_failure_evidence_guard() TO PUBLIC"
        elif mutation == "null_function_acl":
            # REVOKE all explicit grants yields an empty ACL, not NULL. Native
            # ALTER OWNER round-trip resets owner identity, so this case proves
            # the implicit PUBLIC default through a replacement same-body function.
            definition = connection.exec_driver_sql(
                "SELECT pg_get_functiondef('job_failure_evidence_guard()'::regprocedure)"
            ).scalar_one()
            triggers = (
                connection.exec_driver_sql(
                    "SELECT pg_get_triggerdef(oid) FROM pg_trigger WHERE "
                    "tgrelid='public.job_failure_evidence'::regclass AND NOT "
                    "tgisinternal ORDER BY tgname"
                )
                .scalars()
                .all()
            )
            connection.exec_driver_sql(
                "DROP TRIGGER job_failure_evidence_row_guard ON job_failure_evidence"
            )
            connection.exec_driver_sql(
                "DROP TRIGGER job_failure_evidence_truncate_guard ON job_failure_evidence"
            )
            connection.exec_driver_sql("DROP FUNCTION job_failure_evidence_guard()")
            connection.exec_driver_sql(definition)
            for trigger in triggers:
                connection.exec_driver_sql(trigger)
            assert connection.exec_driver_sql(
                "SELECT proacl IS NULL FROM pg_proc WHERE "
                "oid='job_failure_evidence_guard()'::regprocedure"
            ).scalar_one()
            sql = None
        elif mutation == "table_write":
            sql = "GRANT INSERT ON job_failure_evidence TO " + quoted
        elif mutation == "column_grant":
            sql = "GRANT SELECT(job_id) ON job_failure_evidence TO " + quoted
        elif mutation == "default_public":
            sql = "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT INSERT ON TABLES TO PUBLIC"
        elif mutation == "security_definer":
            sql = "ALTER FUNCTION job_failure_evidence_guard() SECURITY DEFINER"
        elif mutation == "missing_trigger":
            sql = "DROP TRIGGER job_failure_evidence_row_guard ON job_failure_evidence"
        elif mutation == "disabled_trigger":
            sql = "ALTER TABLE job_failure_evidence DISABLE TRIGGER job_failure_evidence_row_guard"
        elif mutation == "extra_function":
            sql = (
                "CREATE FUNCTION unexpected_catalog_function() RETURNS integer "
                "LANGUAGE sql AS 'SELECT 1'"
            )
        elif mutation == "changed_support":
            definition = connection.exec_driver_sql(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE "
                "conrelid='public.job_failure_evidence'::regclass "
                "AND conname='failure_operation_fk'"
            ).scalar_one()
            connection.exec_driver_sql(
                "ALTER TABLE job_failure_evidence DROP CONSTRAINT failure_operation_fk"
            )
            connection.exec_driver_sql("DROP INDEX job_failure_operation_binding_uq")
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX job_failure_operation_binding_uq "
                "ON operations(id,project_id,job_id)"
            )
            sql = (
                "ALTER TABLE job_failure_evidence ADD CONSTRAINT failure_operation_fk " + definition
            )
        elif mutation == "changed_check":
            connection.exec_driver_sql(
                "ALTER TABLE job_failure_evidence DROP CONSTRAINT failure_schema_version"
            )
            sql = (
                "ALTER TABLE job_failure_evidence ADD CONSTRAINT failure_schema_version "
                "CHECK (schema_version BETWEEN 1 AND 2)"
            )
        elif mutation == "constraint_comment":
            sql = (
                "COMMENT ON CONSTRAINT failure_pk ON job_failure_evidence IS 'not reflected safely'"
            )
        else:
            sql = "CREATE TABLE extra_catalog_relation(value integer)"
        if sql is not None:
            connection.exec_driver_sql(sql)
        state = rows(connection)
        with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
            reader.inspect_failure_catalog(connection, Checks())
        assert rows(connection) == state
        record_property("native_refusal", mutation)


@pytest.mark.parametrize("actual", [True, None, "21", 21.0])
def test_native_aggregate_cells_keep_exact_types(actual):
    connection = SimpleNamespace(execute=lambda _sql: SimpleNamespace(all=lambda: [(actual,)]))
    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
        reader._scalar_gate(connection, "SELECT native_count", (21,))


@pytest.mark.parametrize("stage", ["native_row", "work", "close"])
def test_fused_cursor_has_one_close_and_preserves_primary(stage):
    selected = ["events"]
    closed = []
    values = iter([("events", 0, 0, "CREATE TABLE events (id INTEGER)"), None])

    def fetchone():
        if stage == "native_row":
            raise RuntimeError("native row failed")
        return next(values)

    def close():
        closed.append(True)
        raise RuntimeError("close failed")

    def check():
        if stage == "work":
            raise RuntimeError("work failed")

    connection = SimpleNamespace(execute=lambda *_: SimpleNamespace(fetchone=fetchone, close=close))
    expected = {"native_row": "native row failed", "work": "work failed", "close": "close failed"}
    with pytest.raises(RuntimeError, match="^" + expected[stage] + "$"):
        reader._sqlite_table_options(connection, selected, SimpleNamespace(check=check))
    assert closed == [True]


@pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL failure catalog"
)
def test_postgres_select_only_reader_preserves_complete_observation(ledger_pg):
    owner, app = ledger_pg["owner"], ledger_pg["app"]
    with owner.begin() as connection:
        create_failure_schema(connection)
        role = connection.dialect.identifier_preparer.quote_identifier(ledger_pg["app_role"])
        connection.exec_driver_sql("GRANT SELECT ON jobs,job_failure_evidence TO " + role)
        expected = reader.inspect_failure_catalog(connection, Checks())
        before = rows(connection)
    with app.connect() as connection:
        actual = reader.inspect_failure_catalog(connection, Checks())
        assert actual == expected
        assert (
            connection.exec_driver_sql("SELECT count(*) FROM job_failure_evidence").scalar_one()
            == 0
        )
        assert (
            connection.exec_driver_sql(
                "SELECT has_table_privilege(current_user,'job_failure_evidence','INSERT')"
            ).scalar_one()
            is False
        )
    with owner.connect() as connection:
        assert rows(connection) == before


@pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL failure catalog"
)
@pytest.mark.parametrize("inherit", [True, False], ids=["inherited", "set_role_only"])
def test_postgres_owner_membership_refuses_with_unchanged_direct_acl(
    ledger_pg, inherit, record_property
):
    owner, app, control = ledger_pg["owner"], ledger_pg["app"], ledger_pg["control"]
    quote = owner.dialect.identifier_preparer.quote_identifier
    owner_role, app_role, group_role = (
        quote(ledger_pg[field]) for field in ("owner_role", "app_role", "group_role")
    )
    with owner.begin() as connection:
        create_failure_schema(connection)
        accepted = reader.inspect_failure_catalog(connection, Checks())
        before = rows(connection)
        acl = connection.exec_driver_sql(
            "SELECT relacl::text FROM pg_class WHERE oid='job_failure_evidence'::regclass"
        ).scalar_one()
    granted = False
    try:
        with control.connect() as connection:
            connection.exec_driver_sql(
                "ALTER ROLE " + app_role + (" INHERIT" if inherit else " NOINHERIT")
            )
            connection.exec_driver_sql("GRANT " + owner_role + " TO " + group_role)
            connection.exec_driver_sql("GRANT " + group_role + " TO " + app_role)
            granted = True
        with owner.connect() as connection:
            assert (
                connection.exec_driver_sql(
                    "SELECT relacl::text FROM pg_class WHERE oid='job_failure_evidence'::regclass"
                ).scalar_one()
                == acl
            )
            with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
                reader.inspect_failure_catalog(connection, Checks())
            assert rows(connection) == before
        with app.begin() as connection:
            usage = connection.execute(
                text("SELECT pg_has_role(current_user,:owner,'USAGE')"),
                {"owner": ledger_pg["owner_role"]},
            ).scalar_one()
            assert usage is inherit
            assert (
                connection.exec_driver_sql(
                    "SELECT has_table_privilege(current_user,'job_failure_evidence','INSERT')"
                ).scalar_one()
                is inherit
            )
            with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
                reader.inspect_failure_catalog(connection, Checks())
            connection.exec_driver_sql("SET LOCAL ROLE " + owner_role)
            assert (
                connection.exec_driver_sql("SELECT current_user").scalar_one()
                == (ledger_pg["owner_role"])
            )
            assert (
                connection.exec_driver_sql(
                    "SELECT has_table_privilege(current_user,'job_failure_evidence','INSERT')"
                ).scalar_one()
                is True
            )
            with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
                reader.inspect_failure_catalog(connection, Checks())
        record_property(
            "effective_owner_path",
            json.dumps(
                {
                    "inherited": inherit,
                    "set_role_observed": True,
                    "target_direct_acl_unchanged": True,
                    "rows_unchanged": True,
                },
                sort_keys=True,
            ),
        )
    finally:
        if granted:
            with control.connect() as connection:
                connection.exec_driver_sql("REVOKE " + group_role + " FROM " + app_role)
                connection.exec_driver_sql("REVOKE " + owner_role + " FROM " + group_role)
    with owner.connect() as connection:
        assert reader.inspect_failure_catalog(connection, Checks()) == accepted
        assert rows(connection) == before


@pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL failure catalog"
)
@pytest.mark.parametrize("overflow", [False, True], ids=["adopted", "check_one_over"])
def test_postgres_constraint_kinds_and_native_key_widths(
    ledger_pg, overflow, monkeypatch, record_property
):
    with ledger_pg["owner"].begin() as connection:
        create_failure_schema(connection)
        native = connection.exec_driver_sql(
            "SELECT k.contype,count(*),max(coalesce(cardinality(k.conkey),0)),"
            "max(coalesce(cardinality(k.confkey),0)),"
            "bool_and(k.conkey IS NULL),bool_and(k.confkey IS NULL) "
            "FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid "
            "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' "
            "GROUP BY k.contype ORDER BY k.contype LIMIT 6"
        ).all()
        assert [tuple(row) for row in native] == [
            ("c", 129, 7, 0, False, True),
            ("f", 34, 5, 5, False, False),
            ("p", 21, 5, 0, False, True),
            ("t", 5, 0, 0, True, True),
            ("u", 16, 4, 0, False, True),
        ]
        trigger_constraints = connection.exec_driver_sql(
            "SELECT c.relname,k.conname,k.condeferrable,k.condeferred,k.convalidated,"
            "t.tgname,t.tgrelid=k.conrelid,t.tgdeferrable=k.condeferrable,"
            "t.tginitdeferred=k.condeferred,NOT t.tgisinternal "
            "FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "LEFT JOIN pg_trigger t ON t.tgconstraint=k.oid "
            "WHERE n.nspname='public' AND k.contype='t' ORDER BY c.relname,k.conname LIMIT 6"
        ).all()
        assert len(trigger_constraints) == 5
        assert all(
            tuple(row[2:5]) == (True, True, True)
            and row[5] == row[1]
            and tuple(row[6:]) == (True, True, True, True)
            for row in trigger_constraints
        )
        if overflow:
            definition = connection.exec_driver_sql(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid='job_failure_evidence'::regclass AND conname='failure_variant'"
            ).scalar_one()
            assert definition.startswith("CHECK (") and definition.endswith(")")
            connection.exec_driver_sql(
                "ALTER TABLE job_failure_evidence DROP CONSTRAINT failure_variant"
            )
            connection.exec_driver_sql(
                "ALTER TABLE job_failure_evidence ADD CONSTRAINT failure_variant "
                "CHECK (schema_version=1 AND (" + definition[7:-1] + "))"
            )
            assert (
                connection.exec_driver_sql(
                    "SELECT cardinality(conkey) FROM pg_constraint WHERE "
                    "conrelid='job_failure_evidence'::regclass AND conname='failure_variant'"
                ).scalar_one()
                == 8
            )

            def forbidden(*_args, **_kwargs):
                pytest.fail("native CHECK overflow must refuse before body reflection/projection")

            state = rows(connection)
            with monkeypatch.context() as patch:
                patch.setattr(reader, "_observe", forbidden)
                with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
                    reader.inspect_failure_catalog(connection, Checks())
            assert rows(connection) == state
        else:
            actual = reader.inspect_failure_catalog(connection, Checks())
            assert actual.catalog == reader._profile("postgresql")
            assert actual.retained_ar7 == installed_profile("postgresql", LEDGER)
        record_property(
            "native_constraint_widths",
            json.dumps(
                {
                    "rows": [list(row) for row in native],
                    "trigger_constraints": [list(row) for row in trigger_constraints],
                    "one_over_check": overflow,
                },
                sort_keys=True,
            ),
        )
