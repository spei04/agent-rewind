"""Fixed ar8 consumer observations; no readiness or evidence-write authority.

The caller owns its connection, transaction and acquisition-inclusive work.
This module observes the complete installed shape before returning retained ar7
history. It never selects a caller-supplied privilege profile or issues a body.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .failure_catalog import FailureCatalog, _catalog_inputs, _catalog_result
from .failure_service import _actual_revision
from .ledger_check import LedgerCheck
from .ledger_compatibility import _validate_native_projection
from .ledger_reader_history import History, read_history
from .schema import FAILURE, LEDGER, MigrationRefused


@dataclass(frozen=True)
class ConsumerPrincipal:
    """Observed native identities, not a producer or cancellation capability."""

    owner: int
    current: int
    session: int
    producer: int | None


@dataclass(frozen=True)
class ConsumerInspection:
    history: History
    principal: ConsumerPrincipal | None


def _postgres_consumer_principal(connection: Connection, checks: LedgerCheck) -> ConsumerPrincipal:
    # Discover a producer from the owner-issued INSERT ACL, independently of the
    # current reader. A dormant installation has no such nonowner grantee.
    checks.check()
    with connection.execute(
        text("""
        WITH owner AS (
          SELECT c.relowner FROM pg_catalog.pg_class c
          JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
          WHERE n.nspname='public' AND c.relname='installation_adoptions' AND c.relkind='r'
        ), target AS (
          SELECT c.* FROM pg_catalog.pg_class c
          JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
          WHERE n.nspname='public' AND c.relname='job_failure_evidence' AND c.relkind='r'
        ), acl AS MATERIALIZED (
          SELECT x.* FROM target t,
            LATERAL aclexplode(coalesce(t.relacl,acldefault('r',t.relowner))) x
        ), candidates AS MATERIALIZED (
          SELECT DISTINCT x.grantee FROM acl x,owner o
          WHERE x.grantee<>o.relowner AND x.privilege_type='INSERT' LIMIT 2
        ), producer AS (
          SELECT min(grantee::bigint)::oid AS oid,count(*) AS count FROM candidates
        ), consumer AS (
          SELECT r.* FROM pg_catalog.pg_roles r WHERE r.rolname=current_user
        ), session AS (
          SELECT r.oid FROM pg_catalog.pg_roles r WHERE r.rolname=session_user
        )
        SELECT o.relowner::bigint,c.oid::bigint,s.oid::bigint,p.oid::bigint,
          p.count<=1 AND c.oid=s.oid AND c.oid<>o.relowner
          AND c.rolcanlogin AND NOT c.rolsuper AND NOT c.rolcreaterole
          AND NOT c.rolcreatedb AND NOT c.rolreplication AND NOT c.rolbypassrls
          AND t.relowner=o.relowner
          AND NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_class other
            JOIN pg_catalog.pg_namespace n ON n.oid=other.relnamespace
            WHERE n.nspname='public' AND other.relkind='r' AND other.relowner<>o.relowner)
          AND (p.count=0 OR EXISTS (
            SELECT 1 FROM pg_catalog.pg_roles r WHERE r.oid=p.oid
              AND r.rolcanlogin AND NOT r.rolsuper AND NOT r.rolcreaterole
              AND NOT r.rolcreatedb AND NOT r.rolreplication AND NOT r.rolbypassrls
              AND (SELECT count(*) FROM acl x
                   WHERE x.grantee=r.oid AND x.grantor=o.relowner
                     AND NOT x.is_grantable
                     AND x.privilege_type IN ('SELECT','INSERT'))=2
              AND has_table_privilege(r.oid,t.oid,'SELECT')
              AND has_table_privilege(r.oid,t.oid,'INSERT')))
          AND NOT EXISTS (
            SELECT 1 FROM acl x
            WHERE x.grantor<>o.relowner OR x.is_grantable OR x.grantee=0
              OR (x.grantee<>o.relowner AND
                (NOT has_table_privilege(x.grantee,'public.jobs','SELECT')
                 OR (x.grantee=p.oid AND x.privilege_type NOT IN ('SELECT','INSERT'))
                 OR ((p.oid IS NULL OR x.grantee<>p.oid) AND x.privilege_type<>'SELECT'))))
          AND NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_attribute a
            WHERE a.attrelid=t.oid AND a.attacl IS NOT NULL)
          AND NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_default_acl d,
              LATERAL aclexplode(d.defaclacl) x
            WHERE d.defaclrole=o.relowner
              AND (d.defaclnamespace=0 OR d.defaclnamespace='public'::regnamespace)
              AND (x.grantee<>o.relowner OR x.grantor<>o.relowner OR x.is_grantable))
          AND has_table_privilege(c.oid,t.oid,'SELECT')
          AND has_table_privilege(c.oid,'public.jobs','SELECT')
        FROM owner o,target t,consumer c,session s,producer p LIMIT 2
    """)
    ) as result:
        rows = result.all()
    checks.check()
    if (
        len(rows) != 1
        or len(rows[0]) != 5
        or any(type(value) is not int or not 0 < value < 2**32 for value in rows[0][:3])
        or (rows[0][3] is not None and (type(rows[0][3]) is not int or not 0 < rows[0][3] < 2**32))
        or rows[0][4] is not True
    ):
        raise MigrationRefused("schema_incompatible")
    owner, current, session, producer = rows[0][:4]
    # Membership, including NOINHERIT/SET ROLE reachability, cannot make a
    # second login an implicit producer. Owner/superuser control-plane actors
    # retain the same explicit exception as the existing F2/F3 policy.
    with connection.execute(
        text("""
        SELECT current_user::regrole::oid=:current AND session_user::regrole::oid=:session
          AND (SELECT relowner FROM pg_catalog.pg_class
               WHERE oid='public.job_failure_evidence'::regclass)=:owner
          AND NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_roles actor
            JOIN pg_catalog.pg_roles effective
              ON actor.oid=effective.oid OR pg_has_role(actor.oid,effective.oid,'MEMBER')
            WHERE actor.rolcanlogin AND NOT actor.rolsuper AND actor.oid<>:owner
              AND (effective.oid=:owner OR effective.rolsuper OR effective.rolcreaterole
                OR effective.rolcreatedb OR effective.rolreplication OR effective.rolbypassrls
                OR has_schema_privilege(effective.oid,'public','CREATE')
                OR has_table_privilege(effective.oid,'public.job_failure_evidence',
                                       'UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                OR ((CAST(:producer AS bigint) IS NULL OR actor.oid::bigint<>:producer) AND
                    (effective.oid::bigint=:producer OR has_table_privilege(
                      effective.oid,'public.job_failure_evidence','INSERT')))
                OR EXISTS (
                  SELECT 1 FROM pg_catalog.pg_proc p
                  JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
                  WHERE n.nspname='public'
                    AND has_function_privilege(effective.oid,p.oid,'EXECUTE')))
            LIMIT 1)
        """),
        {"owner": owner, "current": current, "session": session, "producer": producer},
    ) as result:
        valid = result.all()
    checks.check()
    if len(valid) != 1 or tuple(valid[0]) != (True,) or type(valid[0][0]) is not bool:
        raise MigrationRefused("schema_incompatible")
    return ConsumerPrincipal(owner, current, session, producer)


def inspect_consumer_catalog(
    connection: Connection, checks: LedgerCheck
) -> tuple[FailureCatalog, ConsumerPrincipal | None]:
    """Observe complete ar8 with the fixed consumer policy, without admission."""
    name, selected, expected, predecessor = _catalog_inputs(connection, checks)
    principal = _postgres_consumer_principal(connection, checks) if name == "postgresql" else None
    observed = _catalog_result(connection, checks, name, selected, expected, predecessor)
    checks.check()
    return observed, principal


def refresh_consumer_principal(
    connection: Connection, checks: LedgerCheck, original: ConsumerPrincipal | None
) -> None:
    """Reobserve native principal policy; equality alone grants no action rights."""
    checks.check()
    if connection.dialect.name == "postgresql":
        if type(original) is not ConsumerPrincipal:
            raise MigrationRefused("schema_incompatible")
        if _postgres_consumer_principal(connection, checks) != original:
            raise MigrationRefused("schema_incompatible")
    elif connection.dialect.name != "sqlite" or original is not None:
        raise MigrationRefused("schema_incompatible")
    checks.check()


def validated_consumer_history(connection: Connection, checks: LedgerCheck) -> ConsumerInspection:
    """Validate immutable provenance inside the caller's existing online work."""
    checks.check()
    observed, principal = inspect_consumer_catalog(connection, checks)
    if _actual_revision(connection) != FAILURE:
        raise MigrationRefused("schema_incompatible")
    checks.check()
    history = read_history(connection, LEDGER, observed.retained_ar7, checks)
    checks.check()
    _validate_native_projection(connection, history, checks)
    refresh_consumer_principal(connection, checks, principal)
    return ConsumerInspection(history, principal)
