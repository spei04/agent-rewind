"""Native consumer-policy refusals and real cross-project primary visibility.

Catalog setup faults are explicit owner fixtures. Production catalog, principal,
history, authority and operation readers always execute their original methods.
"""

import json
from contextlib import contextmanager
from dataclasses import replace

import pytest
import test_migrations_postgres as migration_tests
from failure_consumer_oracle import (
    assert_released,
    consumer_fixture,
    observed_read,
    reader_role_state,
    unvalidated_native_state,
)
from failure_postgres_fixture import pg
from operation_failure_service_oracle import (
    assert_service_released,
    observe_service,
    service_case,
)
from sqlalchemy import event, text
from test_failure_persistence_native_oracle import assert_same_state, drain_case, whole_state
from test_run_projection_postgres import drain as drain_postgres

from agent_rewind import operation_failure_service
from agent_rewind.migrations import failure_catalog, failure_consumer
from agent_rewind.migrations.failure_consumer import validated_consumer_history
from agent_rewind.migrations.schema import MigrationRefused
from agent_rewind.scoped_lineage import ResourceNotFound

__all__ = ["pg"]

POSTGRES = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL F4 policy oracles"
)
F4_POSTGRES = pytest.mark.f4_owned_postgres


@pytest.fixture(
    params=[
        "sqlite",
        pytest.param("postgresql", marks=(POSTGRES, F4_POSTGRES)),
    ]
)
def dialect(request):
    return request.param


@contextmanager
def policy_case(request, tmp_path, monkeypatch, record_property, dialect):
    selected_pg = request.getfixturevalue("pg") if dialect == "postgresql" else None
    template = request.getfixturevalue("fresh_sqlite_ar6_template") if selected_pg is None else None
    with consumer_fixture(
        tmp_path,
        monkeypatch,
        record_property,
        pg=selected_pg,
        producer=True,
        template=template,
    ) as fixture:
        yield fixture


def forwarding_gate(monkeypatch, module, name):
    calls = []
    original = getattr(module, name)

    def observed(*args, **kwargs):
        calls.append(name)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, name, observed)
    return calls


def temp_count(connection, dialect):
    statement = (
        "SELECT count(*) FROM sqlite_temp_master"
        if dialect == "sqlite"
        else "SELECT count(*) FROM pg_catalog.pg_class WHERE relnamespace=pg_my_temp_schema()"
    )
    return connection.exec_driver_sql(statement).scalar_one()


def test_actual_session_temporary_relation_refuses_before_catalog_projection(
    request,
    tmp_path,
    monkeypatch,
    record_property,
    dialect,
):
    with policy_case(request, tmp_path, monkeypatch, record_property, dialect) as fixture:
        before = whole_state(fixture.case)
        fixture.engine.dispose()
        created = []

        def install_temporary(dbapi_connection, _record):
            # Fixture-only setup precedes the owner's read-only transaction on
            # this same physical session. It never patches a catalog response.
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("CREATE TEMP TABLE f4_policy_temporary(value INTEGER)")
                cursor.execute(
                    "SELECT count(*) FROM sqlite_temp_master WHERE name='f4_policy_temporary'"
                    if dialect == "sqlite"
                    else "SELECT count(*) FROM pg_catalog.pg_class "
                    "WHERE relnamespace=pg_my_temp_schema() "
                    "AND relname='f4_policy_temporary'"
                )
                assert cursor.fetchone()[0] == 1
                dbapi_connection.commit()
                created.append(True)
            finally:
                cursor.close()

        gate_name = "_sqlite_gates" if dialect == "sqlite" else "_postgres_gates"
        gates = forwarding_gate(monkeypatch, failure_catalog, gate_name)
        projections = forwarding_gate(monkeypatch, failure_consumer, "_catalog_result")
        event.listen(fixture.engine, "connect", install_temporary)
        try:
            with (
                pytest.raises(MigrationRefused) as caught,
                observed_read(fixture.engine, monkeypatch, record_property) as observed,
            ):
                validated_consumer_history(observed.connection, observed.work)
            assert caught.value.code == "schema_incompatible"
            assert created == [True] and gates == [gate_name] and projections == []
            assert_released(observed)
        finally:
            event.remove(fixture.engine, "connect", install_temporary)
            # A session-local fixture has no durable DDL or cleanup by name in
            # another session. Disposing the owned pool closes its temp owner.
            fixture.engine.dispose()
        with fixture.engine.connect() as connection:
            assert temp_count(connection, dialect) == 0
        fixture.engine.dispose()
        assert_same_state(before, whole_state(fixture.case))
        record_property(
            "f4_temporary_gate",
            json.dumps(
                {
                    "dialect": dialect,
                    "native_session_fixture": True,
                    "shared_gate_forwarded": gates,
                    "observed_catalog_projection": projections,
                    "new_session_temporary_count": 0,
                },
                sort_keys=True,
            ),
        )


def test_actual_installation_fingerprint_drift_reaches_successor_history(
    request,
    tmp_path,
    monkeypatch,
    record_property,
    dialect,
):
    with policy_case(request, tmp_path, monkeypatch, record_property, dialect) as fixture:
        before = whole_state(fixture.case)
        rows = before["tables"]["installation_adoptions"]["rows"]
        assert len(rows) == 1
        original = rows[0]["installed_schema_fingerprint"]
        changed = "0" * 64
        assert changed != original
        owner = fixture.case.case.engine
        statement = text(
            "UPDATE installation_adoptions SET installed_schema_fingerprint=:value "
            "WHERE installation_key=:key"
        )
        key = rows[0]["installation_key"]
        applied = False
        try:
            with owner.begin() as connection:
                assert connection.execute(statement, {"value": changed, "key": key}).rowcount == 1
            applied = True
            drain_case(fixture.case)
            injected = unvalidated_native_state(fixture.case, table_count=21)
            histories = forwarding_gate(monkeypatch, failure_consumer, "read_history")
            with (
                pytest.raises(MigrationRefused) as caught,
                observed_read(fixture.engine, monkeypatch, record_property) as observed,
            ):
                validated_consumer_history(observed.connection, observed.work)
            assert caught.value.code == "schema_incompatible"
            assert histories == ["read_history"]
            assert_released(observed)
            assert_same_state(injected, unvalidated_native_state(fixture.case, table_count=21))
        finally:
            if applied:
                with owner.begin() as connection:
                    assert (
                        connection.execute(statement, {"value": original, "key": key}).rowcount == 1
                    )
            drain_case(fixture.case)
        assert_same_state(before, whole_state(fixture.case))


def producer_native_state(fixture):
    producer = fixture.case.pg["app_role"]
    role = reader_role_state(fixture.case.pg, producer)
    with fixture.case.pg["owner"].connect() as connection:
        acl = tuple(
            connection.execute(
                text(
                    "SELECT privilege_type,is_grantable,grantor::bigint "
                    "FROM pg_catalog.pg_class c,"
                    "LATERAL aclexplode(c.relacl) x "
                    "WHERE c.oid='public.job_failure_evidence'::regclass "
                    "AND x.grantee=CAST(:producer AS regrole) "
                    "ORDER BY privilege_type,is_grantable,grantor"
                ),
                {"producer": producer},
            ).all()
        )
        privileges = tuple(
            connection.execute(
                text(
                    "SELECT has_schema_privilege(CAST(:producer AS regrole),'public','CREATE'),"
                    "has_table_privilege(CAST(:producer AS regrole),'public.jobs','SELECT'),"
                    "has_table_privilege(CAST(:producer AS regrole),"
                    "'public.job_failure_evidence','SELECT'),"
                    "has_table_privilege(CAST(:producer AS regrole),"
                    "'public.job_failure_evidence','INSERT')"
                ),
                {"producer": producer},
            ).one()
        )
    drain_postgres(fixture.case.pg)
    return role, acl, privileges


@POSTGRES
@F4_POSTGRES
@pytest.mark.parametrize("mutation", ["nologin", "createdb", "schema_create"])
def test_native_discovered_producer_refuses_forbidden_role_or_effective_authority(
    request,
    tmp_path,
    monkeypatch,
    record_property,
    mutation,
):
    with policy_case(request, tmp_path, monkeypatch, record_property, "postgresql") as fixture:
        before = whole_state(fixture.case)
        native_before = producer_native_state(fixture)
        assert native_before[0][0][0] is True
        assert native_before[0][0][4] is False
        assert native_before[2] == (False, True, True, True)
        role = fixture.reader.app_sql
        if mutation == "schema_create":
            engine = fixture.case.pg["owner"]
            apply_sql = f"GRANT CREATE ON SCHEMA public TO {role}"
            restore_sql = f"REVOKE CREATE ON SCHEMA public FROM {role}"
        else:
            engine = fixture.case.pg["control"]
            apply_sql = f"ALTER ROLE {role} " + ("NOLOGIN" if mutation == "nologin" else "CREATEDB")
            restore_sql = f"ALTER ROLE {role} " + (
                "LOGIN" if mutation == "nologin" else "NOCREATEDB"
            )
        applied = False
        try:
            with engine.begin() as connection:
                connection.exec_driver_sql(apply_sql)
            applied = True
            injected = producer_native_state(fixture)
            assert injected != native_before
            assert injected[1] == native_before[1]
            if mutation == "nologin":
                assert injected[0][0][0] is False
            elif mutation == "createdb":
                assert injected[0][0][4] is True
            else:
                assert injected[2] == (True, True, True, True)
            principals = forwarding_gate(
                monkeypatch, failure_consumer, "_postgres_consumer_principal"
            )
            histories = forwarding_gate(monkeypatch, failure_consumer, "read_history")
            with (
                pytest.raises(MigrationRefused) as caught,
                observed_read(fixture.engine, monkeypatch, record_property) as observed,
            ):
                validated_consumer_history(observed.connection, observed.work)
            assert caught.value.code == "schema_incompatible"
            assert principals == ["_postgres_consumer_principal"] and histories == []
            assert_released(observed)
            assert producer_native_state(fixture) == injected
            # No application connection is attempted while its LOGIN flag is
            # deliberately false; only the separate reader executes the policy.
        finally:
            if applied:
                with engine.begin() as connection:
                    connection.exec_driver_sql(restore_sql)
            drain_postgres(fixture.case.pg)
        assert producer_native_state(fixture) == native_before
        assert_same_state(before, whole_state(fixture.case))


@pytest.mark.parametrize("entry", ["get", "cancel"])
def test_actual_successor_hides_an_existing_operation_in_another_authorized_project(
    request,
    tmp_path,
    monkeypatch,
    record_property,
    dialect,
    entry,
):
    with service_case(
        request,
        tmp_path,
        monkeypatch,
        record_property,
        dialect,
        cancel=entry == "cancel",
    ) as fixture:
        other = f"{971001:032x}"
        with fixture.engine.begin() as connection:
            assert (
                connection.execute(
                    text(
                        "INSERT INTO projects(id,organization_id,name,created_at) "
                        "SELECT :other,organization_id,'Other F4 project',created_at "
                        "FROM projects WHERE id=:source"
                    ),
                    {"other": other, "source": fixture.context.project_id},
                ).rowcount
                == 1
            )
            assert (
                connection.execute(
                    text(
                        "INSERT INTO project_memberships"
                        "(project_id,principal_id,role,revoked_at,legacy_default) "
                        "VALUES(:project,:principal,'operator',NULL,false)"
                    ),
                    {"project": other, "principal": fixture.principal.principal_id},
                ).rowcount
                == 1
            )
        context = replace(fixture.context, project_id=other)
        before = whole_state(fixture.case)
        actual = next(
            row
            for row in before["tables"]["operations"]["rows"]
            if row["id"] == fixture.operation_id
        )
        assert actual["project_id"] == fixture.context.project_id != other
        reads, checks = [], []
        original_read = operation_failure_service.read_operation
        original_check = fixture.service.authority.check

        def read_operation(*args, **kwargs):
            reads.append(True)
            return original_read(*args, **kwargs)

        def authority(connection, principal, selected, action, **kwargs):
            result = original_check(connection, principal, selected, action, **kwargs)
            checks.append(action)
            return result

        monkeypatch.setattr(operation_failure_service, "read_operation", read_operation)
        monkeypatch.setattr(fixture.service.authority, "check", authority)
        fixture.service.artifact_loader = lambda _value: pytest.fail("Foreign target loaded")
        method = (
            fixture.service._read_successor if entry == "get" else fixture.service._cancel_successor
        )
        with (
            observe_service(fixture, monkeypatch, record_property) as observed,
            pytest.raises(ResourceNotFound),
        ):
            method(fixture.principal, context, fixture.operation_id)
        assert reads == [True] and checks == ["read"]
        assert_service_released(observed)
        assert_same_state(before, whole_state(fixture.case))
