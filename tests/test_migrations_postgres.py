"""PostgreSQL 16 adoption against disposable databases and genuinely separate roles.

Only the explicitly configured synthetic integration database server is used. The
administrator provisions test roles/databases; mutations execute as a nonsuperuser
owner. Catalog capture is a failing review aid, never automatic profile approval.
"""

import hashlib
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from legacy_fixture import FIXTURE_ROOT, canonical_bytes, read_manifest
from postgres_control import wait_for_database_drain
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import NullPool

from agent_rewind.migrations import service
from agent_rewind.migrations.inputs import source_digest
from agent_rewind.migrations.schema import HEAD, MigrationRefused, catalog, verify_baseline

POSTGRES = os.getenv("REWIND_TEST_POSTGRES_URL") or os.getenv("REWIND_TEST_POSTGRES")
PROFILE = Path(__file__).parents[1] / "agent_rewind/migrations/profiles/postgresql16.json"
pytestmark = pytest.mark.skipif(not POSTGRES, reason="Opt-in synthetic PostgreSQL integration")


@pytest.fixture
def pg():
    admin = create_engine(POSTGRES, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    token = "ar_migration_" + uuid4().hex
    owner, app, group = token + "_owner", token + "_app", token + "_group"
    password = "synthetic-test-only"
    with admin.connect() as connection:
        assert connection.exec_driver_sql("SHOW server_version_num").scalar_one().startswith("16")
        connection.exec_driver_sql(f"CREATE ROLE {owner} LOGIN PASSWORD '{password}'")
        connection.exec_driver_sql(f"CREATE ROLE {app} LOGIN NOINHERIT PASSWORD '{password}'")
        connection.exec_driver_sql(f"CREATE ROLE {group} NOLOGIN")
        connection.exec_driver_sql(f"CREATE DATABASE {token} OWNER {owner}")
    url = admin.url.set(database=token)
    owner_engine = create_engine(url.set(username=owner, password=password), poolclass=NullPool)
    app_engine = create_engine(url.set(username=app, password=password), poolclass=NullPool)
    privileged = create_engine(url, poolclass=NullPool)
    try:
        with owner_engine.begin() as connection:
            connection.exec_driver_sql("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            identity = connection.execute(
                text("SELECT rolsuper,rolcreaterole FROM pg_roles WHERE rolname=current_user")
            ).one()
            assert tuple(identity) == (False, False)
        # NullPool closes the client before PostgreSQL necessarily reports backend
        # exit. Observe that setup session leaving before the first migration.
        wait_for_database_drain(admin, token)
        yield {
            "owner": owner_engine,
            "app": app_engine,
            "admin": privileged,
            "control": admin,
            "owner_role": owner,
            "app_role": app,
            "group_role": group,
        }
    finally:
        owner_engine.dispose()
        app_engine.dispose()
        privileged.dispose()
        with admin.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE {token} WITH (FORCE)")
            for role in [app, group, owner]:
                connection.exec_driver_sql(f"DROP ROLE {role}")
        admin.dispose()


@pytest.fixture
def frozen_profile():
    if not PROFILE.is_file():
        pytest.skip("The first hosted catalog capture needs independent freezing before acceptance")


def load_legacy(engine):
    manifest = read_manifest()
    sql = (FIXTURE_ROOT / "baseline.sql").read_bytes()
    assert hashlib.sha256(sql).hexdigest() == manifest["baseline_sql_sha256"]
    # Frozen baseline DDL is portable. Row insertion translates only SQLite boolean
    # representation and JSON binding; literal expected values/hashes stay independent.
    ddl = sql.decode().split("INSERT INTO records", 1)[0]
    ddl = "\n".join(line for line in ddl.splitlines() if not line.lstrip().startswith("--"))
    with engine.begin() as connection:
        for statement in ddl.split(";"):
            if statement.strip():
                connection.exec_driver_sql(statement)
        for table, rows in manifest["expected_rows"].items():
            for expected in rows:
                values = dict(expected)
                if table == "records":
                    values["data"] = json.dumps(values["data"])
                for field in ["cancel", "revoked"]:
                    if field in values and values[field] is not None:
                        values[field] = bool(values[field])
                parameters = [
                    "CAST(:data AS JSON)" if field == "data" else ":" + field for field in values
                ]
                connection.execute(
                    text(
                        f"INSERT INTO {table} ({','.join(values)}) VALUES ({','.join(parameters)})"
                    ),
                    values,
                )


def mapping_for(engine):
    with engine.connect() as connection:
        digest = source_digest(connection)
    return {
        "schema_version": 1,
        "installation_key": "synthetic-postgres",
        "source_dataset_digest": digest,
        "organization_id": "8" * 32,
        "project_id": "9" * 32,
        "selector": "all-verified-legacy-resources",
        "principal_grants": [
            {"principal_id": "oidc:" + "a" * 64, "role": "maintainer", "legacy_default": True}
        ],
        "key_dispositions": [],
        "legacy_writer_roles": [engine.url.username.removesuffix("_owner") + "_group"],
    }


def assert_original_rows(engine):
    manifest = read_manifest()
    with engine.connect() as connection:
        for table, expected in manifest["expected_rows"].items():
            order = "run_id,step" if table == "events" else "id"
            rows = [
                dict(row)
                for row in connection.execute(
                    text(f"SELECT * FROM {table} ORDER BY {order}")
                ).mappings()
            ]
            for row in rows:
                for field in ["cancel", "revoked"]:
                    if field in row and row[field] is not None:
                        row[field] = int(row[field])
            assert rows == expected, f"Original {table} values changed"
            assert [hashlib.sha256(canonical_bytes(row)).hexdigest() for row in rows] == (
                manifest["row_sha256"][table]
            )
        assert connection.exec_driver_sql("SELECT sum(reserved) FROM jobs").scalar_one() == 245000


def assert_unversioned(engine):
    with engine.connect() as connection:
        assert (
            connection.exec_driver_sql("SELECT to_regclass('public.alembic_version')").scalar_one()
            is None
        )


def test_postgres_profile_is_frozen(pg):
    with service.migration_transaction(pg["owner"]) as connection:
        service._alembic(connection, "upgrade", HEAD)
        shape = catalog(connection)
        if not PROFILE.is_file():
            pytest.fail(
                "SYNTHETIC_POSTGRES16_CATALOG_REVIEW_REQUIRED="
                + json.dumps(shape, sort_keys=True, separators=(",", ":"))
            )
        verify_baseline(shape, "postgresql", versioned=True)
        assert shape == json.loads(PROFILE.read_text())


def test_postgres_fresh_reentry_and_frozen_legacy_preservation(pg, frozen_profile):
    load_legacy(pg["owner"])
    with pg["owner"].connect() as connection:
        verify_baseline(catalog(connection), "postgresql")
    mapping = mapping_for(pg["owner"])
    first = service.adopt(pg["owner"], mapping, "b" * 64, "d" * 64)
    assert first["state"] == "prepared" and first["customer_ready"] is False
    assert service.adopt(pg["owner"], mapping, "b" * 64, "d" * 64) == first
    assert service.schema_status(pg["owner"]) == first
    assert_original_rows(pg["owner"])
    with pytest.raises(MigrationRefused, match="migration_owner_required"):
        service.upgrade(pg["app"])
    # Read-only inspection works after explicit SELECT grants, without DDL authority.
    with pg["owner"].begin() as connection:
        connection.exec_driver_sql(
            f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {pg['app_role']}"
        )
    assert service.schema_status(pg["app"]) == first


def test_postgres_fresh_install_and_uncertain_response_replay(pg, frozen_profile):
    first = service.install(pg["owner"], "synthetic-postgres")
    assert service.install(pg["owner"], "synthetic-postgres") == first
    with pytest.raises(MigrationRefused, match="installation_conflict"):
        service.install(pg["owner"], "different")


@pytest.mark.parametrize(
    "sql",
    [
        "ALTER TABLE jobs ADD COLUMN unexpected INTEGER",
        "ALTER TABLE jobs ALTER COLUMN reserved SET DEFAULT 0",
        "ALTER TABLE jobs ALTER COLUMN reserved DROP NOT NULL",
        'ALTER TABLE jobs ALTER COLUMN actor TYPE VARCHAR(256) COLLATE "C"',
        "ALTER TABLE jobs DROP CONSTRAINT jobs_pkey; "
        "ALTER TABLE jobs ADD PRIMARY KEY (id) DEFERRABLE",
        "ALTER TABLE jobs ADD COLUMN dropped INTEGER; ALTER TABLE jobs DROP COLUMN dropped",
        "CREATE INDEX unexpected ON jobs(created)",
        "CREATE RULE unexpected AS ON UPDATE TO jobs DO ALSO NOTIFY synthetic_change",
    ],
)
def test_postgres_foreign_catalog_refuses_without_stamp(pg, sql):
    load_legacy(pg["owner"])
    mapping = mapping_for(pg["owner"])
    with pg["owner"].begin() as connection:
        for statement in sql.split(";"):
            connection.exec_driver_sql(statement)
    with pytest.raises(MigrationRefused, match="schema_incompatible"):
        service.adopt(pg["owner"], mapping, "b" * 64, "d" * 64)
    assert_unversioned(pg["owner"])


@pytest.mark.parametrize("authority", ["direct", "public", "set_role", "schema", "owner"])
def test_postgres_effective_writer_authority_is_refused(pg, authority):
    load_legacy(pg["owner"])
    mapping = mapping_for(pg["owner"])
    with pg["admin"].begin() as connection:
        if authority in {"direct", "public"}:
            role = pg["app_role"] if authority == "direct" else "PUBLIC"
            connection.exec_driver_sql(f"GRANT UPDATE ON jobs TO {role}")
        elif authority == "set_role":
            connection.exec_driver_sql(f"GRANT UPDATE ON jobs TO {pg['group_role']}")
            connection.exec_driver_sql(f"GRANT {pg['group_role']} TO {pg['app_role']}")
        elif authority == "schema":
            connection.exec_driver_sql(f"GRANT CREATE ON SCHEMA public TO {pg['app_role']}")
        else:
            connection.exec_driver_sql(f"ALTER TABLE jobs OWNER TO {pg['app_role']}")
    with pytest.raises(MigrationRefused, match="writer_privileges_present"):
        service.adopt(pg["owner"], mapping, "b" * 64, "d" * 64)
    assert_unversioned(pg["owner"])


def test_postgres_security_definer_is_a_writer_even_without_direct_grants(pg):
    load_legacy(pg["owner"])
    with pg["owner"].begin() as connection:
        connection.exec_driver_sql(
            "CREATE FUNCTION public.bump_hold() RETURNS void LANGUAGE sql "
            "SECURITY DEFINER AS 'UPDATE public.jobs SET reserved=reserved+1'"
        )
    with pg["app"].begin() as connection:
        connection.exec_driver_sql("SELECT public.bump_hold()")
    mapping = mapping_for(pg["owner"])
    with pytest.raises(MigrationRefused, match="schema_incompatible"):
        service.adopt(pg["owner"], mapping, "b" * 64, "d" * 64)
    assert_unversioned(pg["owner"])


def test_postgres_hidden_other_role_session_blocks_nonsuperuser_owner(pg):
    load_legacy(pg["owner"])
    mapping = mapping_for(pg["owner"])
    with pg["app"].connect() as app_connection:
        pid = app_connection.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
        with pg["owner"].connect() as connection:
            row = connection.execute(
                text("SELECT backend_type,query FROM pg_stat_activity WHERE pid=:pid"), {"pid": pid}
            ).one()
            assert row[0] is None, "Test must exercise restricted pg_stat_activity visibility"
            assert "insufficient privilege" in row[1]
        with pytest.raises(MigrationRefused, match="writers_not_drained"):
            service.adopt(pg["owner"], mapping, "b" * 64, "d" * 64)
    assert_unversioned(pg["owner"])


def test_postgres_advisory_and_actual_table_writer_locks_are_bounded(pg, monkeypatch):
    load_legacy(pg["owner"])
    mapping = mapping_for(pg["owner"])
    # A trusted administrator racing after the drain inspection still cannot
    # bypass the transactional table lock; injected timing is exact, with no sleeps.
    original = service._postgres_exclusion
    writer = None

    def delayed_writer(connection, tables):
        original(connection, [])
        nonlocal writer
        writer = pg["admin"].connect()
        writer.exec_driver_sql("UPDATE jobs SET reserved=reserved+1")
        connection.exec_driver_sql("LOCK TABLE public.jobs IN ACCESS EXCLUSIVE MODE")

    monkeypatch.setattr(service, "_postgres_exclusion", delayed_writer)
    try:
        with pytest.raises(MigrationRefused, match="migration_busy"):
            service.adopt(pg["owner"], mapping, "b" * 64, "d" * 64, timeout_seconds=1)
    finally:
        if writer is not None:
            writer.rollback()
            writer.close()
    monkeypatch.setattr(service, "_postgres_exclusion", original)
    with (
        service.migration_transaction(pg["owner"]),
        pytest.raises(MigrationRefused, match="migration_busy"),
    ):
        service.adopt(pg["owner"], mapping, "b" * 64, "d" * 64, timeout_seconds=1)
    assert_original_rows(pg["owner"])
    assert_unversioned(pg["owner"])


@pytest.mark.parametrize("when", ["before_commit", "after_commit"])
def test_postgres_process_death_and_idempotent_retry(pg, frozen_profile, when):
    load_legacy(pg["owner"])
    mapping = mapping_for(pg["owner"])
    code = """
import json, os, signal, sys
from sqlalchemy import create_engine, event
from sqlalchemy.pool import NullPool
from agent_rewind.migrations import service
spec=json.load(sys.stdin)
engine=create_engine(spec["url"], poolclass=NullPool)
def connected(connection, record):
    print(json.dumps({"backend_pid":connection.info.backend_pid}), flush=True)
event.listen(engine,"connect",connected)
if spec["when"] == "before_commit":
    original=service._record
    def interrupted(*args, **kwargs):
        original(*args, **kwargs)
        os.kill(os.getpid(), signal.SIGKILL)
    service._record=interrupted
service.adopt(engine,spec["mapping"],"b"*64,"d"*64)
os.kill(os.getpid(), signal.SIGKILL)
"""
    payload = {
        "url": pg["owner"].url.render_as_string(hide_password=False),
        "mapping": mapping,
        "when": when,
    }
    result = subprocess.run(
        [sys.executable, "-c", code],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == -signal.SIGKILL, "Child did not reach the transaction interruption"
    identity = json.loads(result.stdout)
    assert set(identity) == {"backend_pid"} and type(identity["backend_pid"]) is int
    assert identity["backend_pid"] > 0
    # Reaping the Python client does not prove PostgreSQL finished backend cleanup.
    wait_for_database_drain(pg["control"], pg["owner"].url.database)
    if when == "before_commit":
        assert_unversioned(pg["owner"])
    else:
        assert service.schema_status(pg["owner"])["state"] == "prepared"
    assert_original_rows(pg["owner"])
    # NullPool verification clients also close asynchronously on the server side.
    wait_for_database_drain(pg["control"], pg["owner"].url.database)
    assert service.adopt(pg["owner"], mapping, "b" * 64, "d" * 64)["state"] == "prepared"
    assert_original_rows(pg["owner"])


def test_postgres_drain_observes_live_backend_and_its_actual_exit(pg, frozen_profile):
    load_legacy(pg["owner"])
    mapping = mapping_for(pg["owner"])
    with pg["app"].connect() as application:
        backend = application.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
        assert backend > 0
        with pytest.raises(AssertionError, match="Synthetic database sessions did not drain"):
            wait_for_database_drain(pg["control"], pg["owner"].url.database, timeout=0.1)
        with pytest.raises(MigrationRefused, match="writers_not_drained"):
            service.adopt(pg["owner"], mapping, "b" * 64, "d" * 64)
    wait_for_database_drain(pg["control"], pg["owner"].url.database)
    assert service.adopt(pg["owner"], mapping, "b" * 64, "d" * 64)["state"] == "prepared"
    assert_original_rows(pg["owner"])


def test_postgres_legacy_superuser_session_is_not_implicitly_trusted(pg):
    load_legacy(pg["owner"])
    mapping = mapping_for(pg["owner"])
    with pg["admin"].connect() as legacy_superuser:
        legacy_superuser.exec_driver_sql("SELECT 1")
        with pytest.raises(MigrationRefused, match="writers_not_drained"):
            service.adopt(pg["owner"], mapping, "b" * 64, "d" * 64)
    assert_unversioned(pg["owner"])


@pytest.mark.parametrize(
    "inventory", [[], ["missing_synthetic_role"], ["$invalid"], ["owner"], ["app"]]
)
def test_postgres_missing_invalid_or_enabled_legacy_inventory_refuses(pg, inventory):
    load_legacy(pg["owner"])
    mapping = mapping_for(pg["owner"])
    mapping["legacy_writer_roles"] = [
        pg[r + "_role"] if r in {"owner", "app"} else r for r in inventory
    ]
    with pytest.raises(
        MigrationRefused,
        match="legacy_writer_inventory_required|legacy_writer_role_not_disabled|invalid_mapping",
    ):
        service.adopt(pg["owner"], mapping, "b" * 64, "d" * 64)
    assert_unversioned(pg["owner"])


def test_postgres_inventory_retry_binding_and_role_membership(pg, frozen_profile):
    load_legacy(pg["owner"])
    mapping = mapping_for(pg["owner"])
    with pg["admin"].begin() as connection:
        connection.exec_driver_sql(f"GRANT {pg['group_role']} TO {pg['app_role']}")
    with pytest.raises(MigrationRefused, match="legacy_writer_membership_present"):
        service.adopt(pg["owner"], mapping, "b" * 64, "d" * 64)
    with pg["admin"].begin() as connection:
        connection.exec_driver_sql(f"REVOKE {pg['group_role']} FROM {pg['app_role']}")
    first = service.adopt(pg["owner"], mapping, "b" * 64, "d" * 64)
    assert service.adopt(pg["owner"], mapping, "b" * 64, "d" * 64) == first
    with pg["admin"].begin() as connection:
        connection.exec_driver_sql(f"ALTER ROLE {pg['app_role']} NOLOGIN")
    changed = {**mapping, "legacy_writer_roles": [pg["app_role"]]}
    with pytest.raises(MigrationRefused, match="adoption_conflict"):
        service.adopt(pg["owner"], changed, "b" * 64, "d" * 64)


def test_postgres_declared_legacy_superuser_must_be_disabled_and_drained(pg, frozen_profile):
    load_legacy(pg["owner"])
    mapping = mapping_for(pg["owner"])
    mapping["legacy_writer_roles"] = [pg["app_role"]]
    with pg["admin"].begin() as connection:
        connection.exec_driver_sql(f"ALTER ROLE {pg['app_role']} SUPERUSER")
    with pg["app"].connect() as old_app:
        old_app.exec_driver_sql("SELECT 1")
        with pg["admin"].begin() as connection:
            connection.exec_driver_sql(f"ALTER ROLE {pg['app_role']} NOLOGIN NOSUPERUSER")
        with pytest.raises(MigrationRefused, match="writers_not_drained"):
            service.adopt(pg["owner"], mapping, "b" * 64, "d" * 64)
    result = service.adopt(pg["owner"], mapping, "b" * 64, "d" * 64)
    assert result["state"] == "prepared"
    assert_original_rows(pg["owner"])


def test_postgres_nologin_superuser_inventory_is_still_rejected(pg):
    load_legacy(pg["owner"])
    mapping = mapping_for(pg["owner"])
    with pg["admin"].begin() as connection:
        connection.exec_driver_sql(f"ALTER ROLE {pg['group_role']} SUPERUSER")
    with pytest.raises(MigrationRefused, match="legacy_writer_role_not_disabled"):
        service.adopt(pg["owner"], mapping, "b" * 64, "d" * 64)
    assert_unversioned(pg["owner"])


def test_postgres_catalog_refuses_session_temporary_state(pg):
    load_legacy(pg["owner"])
    with pg["owner"].begin() as connection:
        connection.exec_driver_sql("CREATE TEMP TABLE jobs (reserved INTEGER)")
        with pytest.raises(MigrationRefused, match="schema_incompatible"):
            catalog(connection)


def test_postgres_transaction_preserves_builtin_resolution_order(pg):
    with service.migration_transaction(pg["owner"]) as connection:
        schemas = connection.exec_driver_sql("SELECT current_schemas(true)").scalar_one()
        assert schemas[0] == "pg_catalog"
        assert schemas.index("public") > schemas.index("pg_catalog")


@pytest.mark.parametrize(
    "function,return_type",
    [
        ("set_config(text,text,boolean)", "text"),
        ("pg_my_temp_schema()", "oid"),
        ("current_schema()", "name"),
    ],
)
def test_postgres_hostile_initial_path_cannot_invoke_public_overload(pg, function, return_type):
    load_legacy(pg["owner"])
    mapping = mapping_for(pg["owner"])
    with pg["owner"].begin() as connection:
        connection.exec_driver_sql(
            f"CREATE FUNCTION public.{function} "
            f"RETURNS {return_type} LANGUAGE plpgsql AS $$ BEGIN "
            "RAISE EXCEPTION 'synthetic-public-overload-invoked'; END $$"
        )
    hostile = create_engine(
        pg["owner"].url,
        poolclass=NullPool,
        connect_args={"options": "-csearch_path=public,pg_catalog"},
    )
    try:
        with pytest.raises(MigrationRefused, match="schema_incompatible"):
            service.adopt(hostile, mapping, "b" * 64, "d" * 64)
        with pytest.raises(MigrationRefused, match="schema_incompatible"):
            service.schema_status(hostile)
    finally:
        hostile.dispose()
    assert_unversioned(pg["owner"])


def test_postgres_duplicate_source_json_members_refuse_before_stamp(pg):
    load_legacy(pg["owner"])
    mapping = mapping_for(pg["owner"])
    with pg["owner"].begin() as connection:
        connection.execute(
            text("UPDATE records SET data=CAST(:value AS JSON)"),
            {"value": '{"secret":"never-echo","secret":2}'},
        )
    with pytest.raises(MigrationRefused, match="invalid_source_data") as failure:
        service.adopt(pg["owner"], mapping, "b" * 64, "d" * 64)
    assert "never-echo" not in str(failure.value)
    assert_unversioned(pg["owner"])


def test_postgres_json_size_preflight_precedes_driver_decode(pg, monkeypatch):
    from agent_rewind.migrations import inputs

    load_legacy(pg["owner"])
    with pg["owner"].begin() as connection:
        connection.execute(
            text("UPDATE records SET data=CAST(:value AS JSON)"),
            {"value": json.dumps({"large": "x" * 5000})},
        )
    monkeypatch.setattr(inputs, "MAX_ROW_BYTES", 4096)

    def unexpected_decode(*args, **kwargs):
        raise AssertionError("Oversized JSON reached the decoder")

    monkeypatch.setattr(inputs.json, "loads", unexpected_decode)
    with (
        pg["owner"].connect() as connection,
        pytest.raises(MigrationRefused, match="source_limit_exceeded"),
    ):
        source_digest(connection)
    assert_unversioned(pg["owner"])


def test_postgres_connection_hook_retains_safe_options_once(pg):
    engine = create_engine(
        pg["owner"].url,
        poolclass=NullPool,
        connect_args={
            "options": "-capplication_name=synthetic-migration -csearch_path=public,pg_catalog"
        },
    )
    observed_options = []

    def observe(dialect, record, arguments, parameters):
        observed_options.append(parameters["options"])

    try:
        service._secure_engine(engine)
        service._secure_engine(engine)
        event.listen(engine, "do_connect", observe)
        for _ in range(4):
            with engine.connect() as connection:
                assert connection.exec_driver_sql("SHOW application_name").scalar_one() == (
                    "synthetic-migration"
                )
                assert connection.exec_driver_sql("SELECT current_schemas(true)").scalar_one()[
                    0
                ] == ("pg_catalog")
        assert service.schema_status(engine)["state"] == "empty"
        assert len(observed_options) == 5
        assert len(set(observed_options)) == 1
        assert observed_options[0].count(" -csearch_path=public,pg_temp") == 1
    finally:
        engine.dispose()


def test_postgres_autocommit_engine_refuses_before_any_install_ddl(pg, monkeypatch):
    engine = create_engine(pg["owner"].url, isolation_level="AUTOCOMMIT", poolclass=NullPool)

    def unexpected_record(*args, **kwargs):
        raise AssertionError("Autocommit reached metadata mutation")

    monkeypatch.setattr(service, "_record", unexpected_record)
    try:
        with pytest.raises(MigrationRefused, match="transactional_connection_required"):
            service.install(engine, "synthetic-autocommit")
    finally:
        engine.dispose()
    assert service.schema_status(pg["owner"])["state"] == "empty"


@pytest.mark.parametrize("state", ["empty", "partial", "future"])
def test_postgres_runtime_role_cannot_mutate_empty_partial_or_future_schema(
    pg, frozen_profile, state
):
    if state == "partial":
        with pg["owner"].begin() as connection:
            connection.exec_driver_sql("CREATE TABLE jobs (id VARCHAR(32) PRIMARY KEY)")
    elif state == "future":
        service.install(pg["owner"], "synthetic")
        with pg["owner"].begin() as connection:
            connection.exec_driver_sql("UPDATE alembic_version SET version_num='ar_9999_unknown'")
    with pg["owner"].connect() as connection:
        before = catalog(connection)
    for operation in [
        lambda: service.install(pg["app"], "synthetic"),
        lambda: service.upgrade(pg["app"]),
    ]:
        with pytest.raises(MigrationRefused, match="migration_owner_required"):
            operation()
    with pg["owner"].connect() as connection:
        assert catalog(connection) == before
