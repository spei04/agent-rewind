"""Independent native fixtures and observations for dormant successor readers.

Synthetic admission setup is inherited from the accepted fixture. Consumer work
runs through the real read-only owner after that setup has ended.
"""

import json
from contextlib import contextmanager
from dataclasses import asdict
from types import SimpleNamespace

from ledger_restore_authority import typed
from reservation_postgres_fixture import _application_acl
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from test_failure_catalog_native_oracle import native_snapshot
from test_failure_persistence_native_oracle import drain_case, genuine_failure_case
from test_run_projection_postgres import drain as drain_postgres

from agent_rewind.migrations.compatibility import configure_runtime_engine
from agent_rewind.operation_work import OperationWork, operation_connection


def reader_role_state(pg, reader):
    with pg["control"].connect() as connection:
        flags = tuple(
            connection.execute(
                text(
                    "SELECT rolcanlogin,rolinherit,rolsuper,rolcreaterole,rolcreatedb,"
                    "rolreplication,rolbypassrls FROM pg_roles WHERE rolname=:role"
                ),
                {"role": reader},
            ).one()
        )
        memberships = connection.execute(
            text(
                "SELECT count(*) FROM pg_auth_members "
                "WHERE roleid=CAST(:role AS regrole) OR member=CAST(:role AS regrole)"
            ),
            {"role": reader},
        ).scalar_one()
    return flags, memberships


@contextmanager
def select_reader(case, *, producer, record_property):
    """Use the fixture's existing group role as a separate, SELECT-only login."""
    pg = case.pg
    reader = pg["group_role"]
    app = pg["app_role"]
    drain_case(case)
    original_role = reader_role_state(pg, reader)
    assert original_role == ((False, True) + (False,) * 5, 0)
    with pg["owner"].connect() as connection:
        original_app = _application_acl(connection, app)
        assert _application_acl(connection, reader) == set()
        quote = connection.dialect.identifier_preparer.quote_identifier
        reader_sql, app_sql = quote(reader), quote(app)
    engine = None
    primary = None
    try:
        with pg["control"].begin() as connection:
            connection.exec_driver_sql(
                f"ALTER ROLE {reader_sql} LOGIN NOINHERIT PASSWORD 'synthetic-test-only'"
            )
        with pg["owner"].begin() as connection:
            connection.exec_driver_sql(
                f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {reader_sql}"
            )
            if not producer:
                connection.exec_driver_sql(f"REVOKE INSERT ON job_failure_evidence FROM {app_sql}")
        engine = create_engine(
            pg["app"].url.set(username=reader, password="synthetic-test-only"),
            poolclass=NullPool,
        )
        configure_runtime_engine(engine, production=True)
        drain_postgres(pg)
        with engine.connect() as connection:
            actual = connection.exec_driver_sql(
                "SELECT current_user,session_user,"
                "has_table_privilege(current_user,'job_failure_evidence','SELECT'),"
                "has_table_privilege(current_user,'job_failure_evidence','INSERT'),"
                "has_table_privilege(current_user,'job_failure_evidence','UPDATE'),"
                "has_table_privilege(current_user,'job_failure_evidence','DELETE'),"
                "has_table_privilege(current_user,'job_failure_evidence','TRUNCATE'),"
                "has_schema_privilege(current_user,'public','CREATE')"
            ).one()
        assert tuple(actual) == (reader, reader, True) + (False,) * 5
        with pg["control"].connect() as connection:
            identities = {
                name: connection.execute(
                    text("SELECT oid::bigint FROM pg_roles WHERE rolname=:name"), {"name": name}
                ).scalar_one()
                for name in (pg["owner_role"], reader, app)
            }
        drain_postgres(pg)
        yield SimpleNamespace(
            engine=engine,
            reader=reader,
            reader_sql=reader_sql,
            app_sql=app_sql,
            expected_principal={
                "owner": identities[pg["owner_role"]],
                "current": identities[reader],
                "session": identities[reader],
                "producer": identities[app] if producer else None,
            },
        )
    except BaseException as error:
        primary = error
        raise
    finally:
        errors = []
        if engine is not None:
            try:
                engine.dispose()
                drain_postgres(pg)
            except BaseException as error:
                errors.append(error)
        for engine_key, statements in (
            (
                "owner",
                [
                    f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {reader_sql}",
                    f"GRANT SELECT, INSERT ON job_failure_evidence TO {app_sql}",
                ],
            ),
            ("control", [f"ALTER ROLE {reader_sql} NOLOGIN INHERIT PASSWORD NULL"]),
        ):
            try:
                with pg[engine_key].begin() as connection:
                    for statement in statements:
                        connection.exec_driver_sql(statement)
            except BaseException as error:
                errors.append(error)
        try:
            with pg["owner"].connect() as connection:
                assert _application_acl(connection, app) == original_app
                assert _application_acl(connection, reader) == set()
            restored_role = reader_role_state(pg, reader)
            assert restored_role == original_role
            record_property(
                "f4_reader_role_restoration",
                json.dumps(
                    {
                        "original": original_role,
                        "observed": restored_role,
                        "app_acl_restored": True,
                        "reader_acl_empty": True,
                    },
                    sort_keys=True,
                ),
            )
            drain_postgres(pg)
        except BaseException as error:
            errors.append(error)
        if errors:
            if primary is not None:
                primary.add_note("Reader fixture cleanup failed; original failure retained.")
            else:
                raise errors[0] from None


@contextmanager
def consumer_fixture(
    tmp_path, monkeypatch, record_property, *, pg=None, legacy=False, producer=False, template=None
):
    with genuine_failure_case(
        tmp_path,
        monkeypatch,
        record_property,
        pg=pg,
        legacy=legacy,
        fresh_ar6_template=template,
    ) as fixture:
        if pg is None:
            yield SimpleNamespace(
                case=fixture.case,
                initialization=fixture.initialization,
                engine=fixture.case.engine,
                expected_principal=None,
                reader=None,
            )
        else:
            with select_reader(
                fixture.case, producer=producer, record_property=record_property
            ) as reader:
                yield SimpleNamespace(
                    case=fixture.case,
                    initialization=fixture.initialization,
                    engine=reader.engine,
                    expected_principal=reader.expected_principal,
                    reader=reader,
                )


@contextmanager
def observed_read(engine, monkeypatch, record_property):
    """Forward real ownership and controls; never replace a product observation."""
    work = OperationWork(include_acquisition=True)
    observed = SimpleNamespace(work=work, connection=None, controls=[])
    original = work.control_attempt

    def control(kind):
        before = work.statements
        try:
            return original(kind)
        finally:
            observed.controls.append((kind, before, work.statements))

    with monkeypatch.context() as scoped:
        scoped.setattr(work, "control_attempt", control)
        try:
            with operation_connection(engine, work) as connection:
                observed.connection = connection
                yield observed
        finally:
            cleanup = sum(
                after - before
                for kind, before, after in observed.controls
                if kind in {"rollback", "close", "discard", "restore"}
            )
            record_property(
                "f4_consumer_work",
                json.dumps(
                    {
                        "ordinary": work.statements - cleanup,
                        "cleanup": cleanup,
                        "total": work.statements,
                        "seconds": work.seconds,
                        "vm_instructions": work.instructions,
                        "controls": observed.controls,
                        "detached": work._detached,
                        "connection_closed": (
                            observed.connection is not None and observed.connection.closed
                        ),
                    },
                    sort_keys=True,
                ),
            )


def assert_released(observed):
    work = observed.work
    cleanup = sum(
        after - before
        for kind, before, after in observed.controls
        if kind in {"rollback", "close", "discard", "restore"}
    )
    assert 0 < work.statements - cleanup <= 504
    assert 0 < cleanup <= 8 and work.statements <= 512
    assert 0 <= work.seconds < 10 and work.instructions < 20_000_000
    assert work._detached and not work._listeners and work._lease is None
    assert work._connection is None and work._started is None
    assert observed.connection is not None and observed.connection.closed
    assert all(kind != "commit" for kind, _, _ in observed.controls)


def assert_history(inspection, fixture, before):
    history = inspection.history
    assert history.adoption["installation_key"] == fixture.initialization.installation_key
    assert history.ownership.organization_id == fixture.case.organization_id
    assert history.opening is not None
    assert len(history.manifests) == fixture.initialization.retained_ar7.manifest_count
    accounts = {
        account.id: account for cursor in history.manifests for account in cursor.manifest.accounts
    }
    native = {row["id"]: row for row in before["tables"]["budget_accounts"]["rows"]}
    assert set(accounts) == set(native)
    for identity, account in accounts.items():
        assert account.organization_id == native[identity]["organization_id"]
        assert account.limit_microusd == native[identity]["limit_microusd"]
        assert account.project_id == native[identity]["project_id"]
        assert account.job_id == native[identity]["job_id"]
    principal = None if inspection.principal is None else asdict(inspection.principal)
    assert principal == fixture.expected_principal


def unvalidated_native_state(case, *, table_count):
    """Capture bounded typed cells even when the deliberately changed source is invalid."""
    assert table_count in {21, 22}
    drain_case(case)
    try:
        with case.case.engine.connect() as connection:
            native = native_snapshot(connection, table_count)
            names = (
                sorted(native["tables"])
                if connection.dialect.name == "sqlite"
                else [row[0] for row in native["table_names"]]
            )
            remaining = 65536
            tables = {}
            for name in names:
                quoted = connection.dialect.identifier_preparer.quote_identifier(name)
                with connection.exec_driver_sql(f"SELECT * FROM {quoted}") as result:
                    columns = tuple(result.keys())
                    values = result.mappings().fetchmany(remaining + 1)
                assert len(values) <= remaining
                remaining -= len(values)
                tables[name] = {
                    "columns": columns,
                    "rows": sorted((dict(row) for row in values), key=lambda row: repr(typed(row))),
                }
        return {"native": native, "tables": tables}
    finally:
        drain_case(case)
