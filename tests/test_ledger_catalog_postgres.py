"""Independent PostgreSQL catalog bounds, literal identity and invoker controls."""

import pytest
import test_migrations_postgres as migration_tests
from sqlalchemy import event, text
from sqlalchemy.exc import ProgrammingError
from test_ledger_constraints_postgres import committed_call as committed_call_fixture
from test_ledger_constraints_postgres import ledger_pg as ledger_pg_fixture
from test_ledger_schema import CALL

from agent_rewind.migrations.ledger_catalog import ledger_executables
from agent_rewind.migrations.schema import (
    LEDGER,
    MigrationRefused,
    catalog,
    installed_profile,
    verify_installed_profile,
)

pg = migration_tests.pg
ledger_pg = ledger_pg_fixture
committed_call = committed_call_fixture
pytestmark = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL ledger catalog"
)


def test_literal_executable_identity_and_owner_binding(ledger_pg):
    with ledger_pg["owner"].connect() as connection:
        shape = catalog(connection)
        assert shape == installed_profile("postgresql", LEDGER)
        identity = connection.exec_driver_sql(
            "SELECT p.prosecdef, p.provolatile, p.proparallel, p.pronargs,"
            "p.proowner=a.relowner, p.proconfig "
            "FROM pg_proc p JOIN pg_class a ON a.relname='installation_adoptions' "
            "WHERE p.oid='public.ar7_ledger_constraint()'::regprocedure"
        ).one()
        assert tuple(identity) == (False, "v", "u", 0, True, ["search_path=pg_catalog, pg_temp"])
        grants = connection.exec_driver_sql(
            "SELECT x.grantee=p.proowner, x.grantor=p.proowner, "
            "x.privilege_type, x.is_grantable FROM pg_proc p "
            "CROSS JOIN LATERAL aclexplode(p.proacl) x "
            "WHERE p.oid='public.ar7_ledger_constraint()'::regprocedure"
        ).all()
        assert grants == [(True, True, "EXECUTE", False)]


@pytest.mark.parametrize(
    "mutation",
    [
        "extra_function",
        "extra_trigger",
        "oversized_body",
        "oversized_trigger",
        "oversized_settings",
        "public_execute",
    ],
)
def test_count_and_size_policy_refuses_before_transferring_definitions(ledger_pg, mutation):
    engine = ledger_pg["owner"]
    with engine.begin() as connection:
        if mutation == "extra_function":
            connection.exec_driver_sql(
                "CREATE FUNCTION public.unreviewed() RETURNS integer LANGUAGE sql AS 'SELECT 1'"
            )
        elif mutation == "extra_trigger":
            connection.exec_driver_sql(
                "CREATE TRIGGER unreviewed AFTER UPDATE ON jobs FOR EACH ROW "
                "EXECUTE FUNCTION public.ar7_ledger_constraint()"
            )
        elif mutation == "oversized_body":
            connection.exec_driver_sql(
                "CREATE OR REPLACE FUNCTION public.ar7_ledger_constraint() RETURNS trigger "
                "LANGUAGE plpgsql AS $body$ BEGIN /*" + "x" * 16385 + "*/ RETURN NULL; END $body$"
            )
        elif mutation == "oversized_trigger":
            connection.exec_driver_sql("DROP TRIGGER ar7_accounts_constraint ON budget_accounts")
            connection.exec_driver_sql(
                "CREATE CONSTRAINT TRIGGER ar7_accounts_constraint AFTER INSERT OR UPDATE "
                "OR DELETE ON budget_accounts DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
                "WHEN (length('" + "x" * 4097 + "') > 0) "
                "EXECUTE FUNCTION public.ar7_ledger_constraint()"
            )
        elif mutation == "oversized_settings":
            connection.exec_driver_sql(
                "ALTER FUNCTION public.ar7_ledger_constraint() "
                "SET search_path TO '" + ",".join(["pg_catalog"] * 500) + "'"
            )
        else:
            connection.exec_driver_sql(
                "GRANT EXECUTE ON FUNCTION public.ar7_ledger_constraint() TO PUBLIC"
            )
        statements = []

        def observe(_conn, _cursor, statement, _parameters, _context, _many):
            statements.append(statement)

        event.listen(connection, "before_cursor_execute", observe)
        try:
            with pytest.raises(MigrationRefused, match="schema_incompatible"):
                ledger_executables(connection)
        finally:
            event.remove(connection, "before_cursor_execute", observe)
        assert statements
        assert not any(" AS definition" in statement for statement in statements)


@pytest.mark.parametrize(
    "statement",
    [
        "ALTER FUNCTION public.ar7_ledger_constraint() SECURITY DEFINER",
        "ALTER FUNCTION public.ar7_ledger_constraint() STABLE",
        "ALTER FUNCTION public.ar7_ledger_constraint() PARALLEL SAFE",
        "ALTER FUNCTION public.ar7_ledger_constraint() SET search_path=public",
        "ALTER TABLE budget_accounts DISABLE TRIGGER ar7_accounts_constraint",
        "ALTER TABLE budget_accounts ENABLE ALWAYS TRIGGER ar7_accounts_constraint",
    ],
)
def test_in_bounds_semantic_drift_cannot_match_literal_profile(ledger_pg, statement):
    with ledger_pg["owner"].begin() as connection:
        assert catalog(connection) == installed_profile("postgresql", LEDGER)
        connection.exec_driver_sql(statement)
        with pytest.raises(MigrationRefused, match="schema_incompatible"):
            verify_installed_profile(catalog(connection), "postgresql", LEDGER)


@pytest.mark.parametrize("target", ["function", "table"])
def test_real_owner_drift_refuses_before_owner_name_normalization(ledger_pg, target):
    with ledger_pg["admin"].begin() as connection:
        role = connection.dialect.identifier_preparer.quote(ledger_pg["app_role"])
        if target == "function":
            connection.exec_driver_sql(
                f"ALTER FUNCTION public.ar7_ledger_constraint() OWNER TO {role}"
            )
        else:
            connection.exec_driver_sql(f"ALTER TABLE jobs OWNER TO {role}")
        with pytest.raises(MigrationRefused, match="schema_incompatible"):
            ledger_executables(connection)


def grant_trigger_reads_and_scope_update(ledger):
    with ledger["owner"].begin() as connection:
        role = connection.dialect.identifier_preparer.quote(ledger["app_role"])
        connection.exec_driver_sql(
            "GRANT SELECT ON budget_accounts,provider_calls,budget_entries,jobs,"
            f"resource_scopes TO {role}"
        )
        connection.exec_driver_sql(f"GRANT UPDATE ON resource_scopes TO {role}")


def test_installed_trigger_executes_without_runtime_function_execute_grant(committed_call):
    grant_trigger_reads_and_scope_update(committed_call)
    with committed_call["app"].begin() as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT has_function_privilege(current_user,"
                "'public.ar7_ledger_constraint()', 'EXECUTE')"
            ).scalar_one()
            is False
        )
        result = connection.execute(
            text(
                "UPDATE resource_scopes SET project_id=project_id "
                "WHERE resource_kind='provider_call' AND resource_id=:id"
            ),
            {"id": CALL},
        )
        assert result.rowcount == 1


def test_invoker_trigger_cannot_read_a_table_without_select_privilege(committed_call):
    grant_trigger_reads_and_scope_update(committed_call)
    with committed_call["owner"].begin() as connection:
        role = connection.dialect.identifier_preparer.quote(committed_call["app_role"])
        connection.exec_driver_sql(f"REVOKE SELECT ON budget_entries FROM {role}")
    body_completed = False
    with pytest.raises(ProgrammingError) as caught, committed_call["app"].begin() as connection:
        result = connection.execute(
            text(
                "UPDATE resource_scopes SET project_id=project_id "
                "WHERE resource_kind='provider_call' AND resource_id=:id"
            ),
            {"id": CALL},
        )
        assert result.rowcount == 1
        body_completed = True
    assert body_completed
    assert caught.value.orig.sqlstate == "42501"
    assert "budget_entries" in str(caught.value.orig)


def test_trigger_creation_requires_function_execute_privilege(ledger_pg):
    with ledger_pg["owner"].begin() as connection:
        role = connection.dialect.identifier_preparer.quote(ledger_pg["app_role"])
        connection.exec_driver_sql(f"GRANT TRIGGER ON jobs TO {role}")
    with ledger_pg["app"].connect() as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT has_table_privilege(current_user, 'public.jobs', 'TRIGGER')"
            ).scalar_one()
            is True
        )
        assert (
            connection.exec_driver_sql(
                "SELECT has_function_privilege(current_user,"
                "'public.ar7_ledger_constraint()', 'EXECUTE')"
            ).scalar_one()
            is False
        )
    with pytest.raises(ProgrammingError) as caught, ledger_pg["app"].begin() as connection:
        connection.exec_driver_sql(
            "CREATE TRIGGER forbidden AFTER UPDATE ON jobs FOR EACH ROW "
            "EXECUTE FUNCTION public.ar7_ledger_constraint()"
        )
    assert caught.value.orig.sqlstate == "42501"
    assert caught.value.orig.diag.message_primary == (
        "permission denied for function public.ar7_ledger_constraint"
    )
    with ledger_pg["owner"].connect() as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal"
            ).scalar_one()
            == 5
        )
