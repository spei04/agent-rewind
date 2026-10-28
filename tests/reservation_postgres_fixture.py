"""Real PostgreSQL admission/P1 setup, with the existing synthetic setup adapter."""

import json
from dataclasses import dataclass
from types import SimpleNamespace

import ledger_eligibility_postgres_fixture as eligibility
from ledger_provisioning_fixture import initial_manifest
from ledger_provisioning_postgres_fixture import build_postgres_case, invoke, native_snapshot
from reservation_fixture import ReservationCase
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool
from test_admission_configuration import configuration
from test_admission_request import submission

from agent_rewind.migrations.compatibility import configure_runtime_engine
from agent_rewind.request_authority import RequestAuthority


@dataclass
class PostgresReservationCase(ReservationCase):
    pg: object

    def snapshot(self):
        # Existing native observer requires all application sessions drained.
        # Dispose only this fixture's idle pool; never another caller's handle.
        assert self.engine.pool.checkedout() == 0
        self.engine.dispose()
        return native_snapshot(self.case, self.pg)


def _application_acl(connection, role):
    """Exact explicit grants to the fixture app role, including column ACLs."""
    return {
        tuple(row)
        for row in connection.execute(
            text(
                "SELECT 'table',c.relname::text,''::text,a.privilege_type,a.is_grantable,"
                "pg_get_userbyid(a.grantor)::text FROM pg_class c "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "CROSS JOIN LATERAL aclexplode(c.relacl) a "
                "WHERE n.nspname='public' "
                "AND a.grantee=(SELECT oid FROM pg_roles WHERE rolname=:r) "
                "UNION ALL "
                "SELECT 'column',c.relname::text,t.attname::text,a.privilege_type,a.is_grantable,"
                "pg_get_userbyid(a.grantor)::text FROM pg_attribute t "
                "JOIN pg_class c ON c.oid=t.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
                "CROSS JOIN LATERAL aclexplode(t.attacl) a "
                "WHERE n.nspname='public' "
                "AND a.grantee=(SELECT oid FROM pg_roles WHERE rolname=:r) "
                "UNION ALL "
                "SELECT 'schema',n.nspname::text,''::text,a.privilege_type,a.is_grantable,"
                "pg_get_userbyid(a.grantor)::text FROM pg_namespace n "
                "CROSS JOIN LATERAL aclexplode(n.nspacl) a "
                "WHERE n.nspname='public' AND a.grantee=(SELECT oid FROM pg_roles WHERE rolname=:r)"
            ),
            {"r": role},
        )
    }


def build_postgres_reservation_case(
    pg,
    tmp_path,
    monkeypatch,
    *,
    budget=1_000_000,
    account_limit=1_000_000,
    legacy=False,
    record=None,
):
    if type(budget) is not int or not 1 <= budget <= 200_000_000:
        raise ValueError("invalid_fixture_budget")
    if type(account_limit) is not int or not 0 <= account_limit <= 2**63 - 1:
        raise ValueError("invalid_fixture_account_limit")
    fixture = build_postgres_case(pg, legacy=legacy)
    engine = None
    events = []
    try:
        body = submission()
        body["budget_microusd"] = budget
        with monkeypatch.context() as patch:
            patch.setattr(eligibility, "submission", lambda: body)
            fixture, admission = eligibility.admit_existing_fixture(
                fixture, pg, tmp_path, patch, lambda name, value: events.append((name, value))
            )
        manifest = initial_manifest(fixture)
        for account in manifest["accounts"]:
            if account["scope"] in {"organization", "project"}:
                account["limit_microusd"] = account_limit
        receipt = invoke(fixture, pg, manifest)
        # Existing runtime read/authority-lock grants, plus only the new P2
        # columns/inserts. The fixture owner provisions; this NOINHERIT app role
        # executes P2 without owner membership or any DDL permission.
        before_grants = native_snapshot(fixture.case, pg)
        with pg["owner"].begin() as connection:
            assert _application_acl(connection, pg["app_role"]) == set()
            role = connection.dialect.identifier_preparer.quote(pg["app_role"])
            connection.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {role}")
            connection.exec_driver_sql(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {role}")
            for table in ("projects", "organizations", "api_keys"):
                connection.exec_driver_sql(f"GRANT UPDATE(id) ON {table} TO {role}")
            connection.exec_driver_sql(
                f"GRANT UPDATE(principal_id) ON project_memberships TO {role}"
            )
            connection.exec_driver_sql(f"GRANT UPDATE(resource_id) ON resource_scopes TO {role}")
            connection.exec_driver_sql(
                "GRANT UPDATE(owner,status,lease_until,lease_generation,reserved) "
                f"ON jobs TO {role}"
            )
            connection.exec_driver_sql(f"GRANT UPDATE(held_microusd) ON budget_accounts TO {role}")
            connection.exec_driver_sql(
                f"GRANT INSERT ON provider_calls,resource_scopes,budget_entries TO {role}"
            )
            app_acl = _application_acl(connection, pg["app_role"])
        after_grants = native_snapshot(fixture.case, pg)
        for key in ("catalog", "tables", "role"):
            assert after_grants[key] == before_grants[key]
        assert after_grants["authority"]["functions"] == before_grants["authority"]["functions"]
        expected = {
            ("table", name, "", "SELECT", False, pg["owner_role"])
            for name in before_grants["tables"]
        }
        (schema_before,) = before_grants["authority"]["schema"]
        assert schema_before[:2] == ("public", "pg_database_owner")
        # PostgreSQL attributes an indirect owner GRANT to the owning role.
        # This witness precedes GRANT and is independent of the resulting ACL.
        expected.add(("schema", "public", "", "USAGE", False, schema_before[1]))
        expected.update(
            ("table", name, "", "INSERT", False, pg["owner_role"])
            for name in ("provider_calls", "resource_scopes", "budget_entries")
        )
        updates = {
            "projects": ("id",),
            "organizations": ("id",),
            "api_keys": ("id",),
            "project_memberships": ("principal_id",),
            "resource_scopes": ("resource_id",),
            "jobs": ("owner", "status", "lease_until", "lease_generation", "reserved"),
            "budget_accounts": ("held_microusd",),
        }
        expected.update(
            ("column", name, column, "UPDATE", False, pg["owner_role"])
            for name, columns in updates.items()
            for column in columns
        )
        acl_diagnostic = {
            "schema_before": schema_before,
            "observed": sorted(app_acl),
            "expected": sorted(expected),
            "missing": sorted(expected - app_acl),
            "extra": sorted(app_acl - expected),
        }
        events.append(("application_acl", acl_diagnostic))
        if record is not None:
            record("application_acl", acl_diagnostic)
        assert app_acl == expected
        events.append(("grant_acl", sorted(app_acl)))
        events.append(("authority_before_grants", before_grants["authority"]))
        events.append(("authority_after_grants", after_grants["authority"]))
        engine = create_engine(
            pg["app"].url,
            poolclass=QueuePool,
            pool_timeout=1,
            pool_size=8,
            max_overflow=0,
            pool_pre_ping=False,
        )
        configure_runtime_engine(engine, production=True)
        with engine.connect() as connection:
            role = connection.execute(
                text(
                    "SELECT current_user,session_user,rolsuper,rolcreaterole,rolcreatedb,"
                    "rolinherit,rolbypassrls,"
                    "pg_has_role(current_user,:owner,'MEMBER') "
                    "FROM pg_roles WHERE rolname=current_user"
                ),
                {"owner": pg["owner_role"]},
            ).one()
            forbidden = connection.exec_driver_sql(
                "SELECT has_schema_privilege(current_user,'public','CREATE'),"
                "has_table_privilege(current_user,'jobs','INSERT'),"
                "has_table_privilege(current_user,'jobs','DELETE'),"
                "has_table_privilege(current_user,'jobs','TRUNCATE'),"
                "has_table_privilege(current_user,'budget_accounts','INSERT'),"
                "has_table_privilege(current_user,'budget_accounts','DELETE'),"
                "has_table_privilege(current_user,'migration_progress','UPDATE'),"
                "has_table_privilege(current_user,'jobs','TRIGGER'),"
                "has_column_privilege(current_user,'api_keys','revoked','UPDATE')"
            ).one()
        assert tuple(role) == (
            pg["app_role"],
            pg["app_role"],
            False,
            False,
            False,
            False,
            False,
            False,
        )
        assert tuple(forbidden) == (False,) * 9
        events.append(("runtime_role", tuple(role)))
        events.append(("forbidden_privileges", tuple(forbidden)))
        principal, _binding = eligibility.native_principal(fixture)
        authority = RequestAuthority(engine)
        context = authority.named(principal, fixture.project, action="record").context
        job_id = admission.accepted["job_id"]
        org = next(row["id"] for row in manifest["accounts"] if row["scope"] == "organization")
        project = next(row["id"] for row in manifest["accounts"] if row["scope"] == "project")
        job = next(row["id"] for row in manifest["accounts"] if row["job_id"] == job_id)
        return PostgresReservationCase(
            engine=engine,
            authority=authority,
            principal=principal,
            context=context,
            job_id=job_id,
            organization_id=fixture.organization,
            project_id=fixture.project,
            account_ids=(org, project, job),
            price_version=json.loads(configuration().canonical_bytes)["price_version"],
            case=fixture.case,
            provisioning=fixture,
            admission=SimpleNamespace(
                **vars(admission), manifest=manifest, initialization_receipt=receipt
            ),
            setup_events=events,
            pg=pg,
        )
    except BaseException:
        if engine is not None:
            engine.dispose()
        fixture.close()
        raise
