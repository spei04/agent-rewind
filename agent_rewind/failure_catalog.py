"""Fixed private F3 producer catalog; no grants or caller-selected policy."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .failure_evidence import FailureRefusal
from .migrations.failure_catalog import (
    FailureCatalog,
    _catalog_inputs,
    _catalog_result,
)
from .reservation_connection import ReservationBody, require_body
from .reservation_types import ReservationScope


@dataclass(frozen=True)
class _ProducerAuthority:
    body: ReservationBody
    principal: tuple[int, int, int] | None


def _postgres_producer_authority(connection: Connection) -> tuple[int, int, int]:
    # The actual restricted session is the sole nonowner INSERT principal.
    # Owner-issued ACLs alone are insufficient: the second query checks MEMBER
    # reachability, including NOINHERIT roles that can be reached with SET ROLE.
    rows = connection.execute(
        text("""
        WITH owner AS (
          SELECT c.relowner FROM pg_catalog.pg_class c
          JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
          WHERE n.nspname='public' AND c.relname='installation_adoptions' AND c.relkind='r'
        ), target AS (
          SELECT c.* FROM pg_catalog.pg_class c
          JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
          WHERE n.nspname='public' AND c.relname='job_failure_evidence' AND c.relkind='r'
        ), producer AS (
          SELECT r.* FROM pg_catalog.pg_roles r WHERE r.rolname=current_user
        ), session AS (
          SELECT r.oid FROM pg_catalog.pg_roles r WHERE r.rolname=session_user
        )
        SELECT o.relowner::bigint,p.oid::bigint,s.oid::bigint,
          p.oid=s.oid AND p.oid<>o.relowner
          AND p.rolcanlogin AND NOT p.rolsuper AND NOT p.rolcreaterole
          AND NOT p.rolcreatedb AND NOT p.rolreplication AND NOT p.rolbypassrls
          AND t.relowner=o.relowner
          AND NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relkind='r' AND c.relowner<>o.relowner)
          AND (SELECT count(*) FROM
            aclexplode(coalesce(t.relacl,acldefault('r',t.relowner))) x
            WHERE x.grantee=p.oid AND x.grantor=o.relowner
              AND NOT x.is_grantable AND x.privilege_type IN ('SELECT','INSERT'))=2
          AND NOT EXISTS (
            SELECT 1 FROM aclexplode(coalesce(t.relacl,acldefault('r',t.relowner))) x
            WHERE x.grantor<>o.relowner OR x.is_grantable OR x.grantee=0
              OR (x.grantee<>o.relowner AND
                (NOT has_table_privilege(x.grantee,'public.jobs','SELECT')
                 OR (x.grantee=p.oid AND x.privilege_type NOT IN ('SELECT','INSERT'))
                 OR (x.grantee<>p.oid AND x.privilege_type<>'SELECT'))))
          AND NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_attribute a
            WHERE a.attrelid=t.oid AND a.attacl IS NOT NULL)
          AND NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_default_acl d,
              LATERAL aclexplode(d.defaclacl) x
            WHERE d.defaclrole=o.relowner
              AND (d.defaclnamespace=0 OR d.defaclnamespace='public'::regnamespace)
              AND (x.grantee<>o.relowner OR x.grantor<>o.relowner OR x.is_grantable))
          AND has_table_privilege(p.oid,t.oid,'SELECT')
          AND has_table_privilege(p.oid,t.oid,'INSERT')
        FROM owner o,target t,producer p,session s LIMIT 2
    """)
    ).all()
    if (
        len(rows) != 1
        or len(rows[0]) != 4
        or any(type(value) is not int or not 0 < value < 2**32 for value in rows[0][:3])
        or rows[0][3] is not True
    ):
        raise FailureRefusal("unsupported_profile")
    owner, producer, session = rows[0][:3]
    valid = connection.execute(
        text("""
        SELECT current_user::regrole::oid=:producer AND session_user::regrole::oid=:session
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
                OR (actor.oid<>:producer AND
                    (effective.oid=:producer OR has_table_privilege(
                      effective.oid,'public.job_failure_evidence','INSERT')))
                OR EXISTS (
                  SELECT 1 FROM pg_catalog.pg_proc p
                  JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
                  WHERE n.nspname='public'
                    AND has_function_privilege(effective.oid,p.oid,'EXECUTE')))
            LIMIT 1)
        """),
        {"owner": owner, "producer": producer, "session": session},
    ).all()
    if len(valid) != 1 or tuple(valid[0]) != (True,) or type(valid[0][0]) is not bool:
        raise FailureRefusal("unsupported_profile")
    return owner, producer, session


def _inspect_producer_catalog(
    connection: Connection, scope: ReservationScope
) -> tuple[FailureCatalog, _ProducerAuthority]:
    body = require_body(connection, scope)
    name, selected, expected, predecessor = _catalog_inputs(connection, body.work)
    principal = _postgres_producer_authority(connection) if name == "postgresql" else None
    observed = _catalog_result(connection, body.work, name, selected, expected, predecessor)
    if require_body(connection, scope) is not body:
        raise FailureRefusal("invalid_native_state")
    return observed, _ProducerAuthority(body, principal)


def _refresh_producer_authority(
    connection: Connection, scope: ReservationScope, witness: _ProducerAuthority
) -> None:
    if (
        type(witness) is not _ProducerAuthority
        or require_body(connection, scope) is not witness.body
    ):
        raise FailureRefusal("invalid_native_state")
    current = (
        _postgres_producer_authority(connection)
        if connection.dialect.name == "postgresql"
        else None
    )
    if current != witness.principal or require_body(connection, scope) is not witness.body:
        raise FailureRefusal("invalid_native_state")
