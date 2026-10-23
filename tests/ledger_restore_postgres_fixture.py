"""Same-cluster restore fixtures; expectations always originate in the source."""

import hashlib
import json
import os
import sys
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from cryptography.fernet import Fernet
from ledger_provisioning_postgres_fixture import native_snapshot
from ledger_restore_authority import observe_authority, typed
from ledger_restore_tools import run_tool, tool_environment
from legacy_fixture import FIXTURE_ROOT, read_manifest
from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool
from test_run_projection_postgres import drain

TOOLS_ENV = "REWIND_TEST_POSTGRES_TOOL_DIRECTORY"


def save(directory, name, value, record_property):
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / (name + ".json")
    with path.open("x") as handle:
        os.chmod(path, 0o600)
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
    record_property(
        "restore_" + name,
        json.dumps(
            {
                "file": str(path),
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        ),
    )
    return value


def tool_configuration(pg, directory, record_property):
    selected = os.environ.get(TOOLS_ENV)
    assert selected, "reviewed existing PostgreSQL tools must be explicitly configured"
    binary = Path(selected)
    assert binary.is_absolute() and binary.is_dir()
    socket = pg["control"].url.query["host"]
    port = int(pg["control"].url.query["port"])
    assert port == 55432 and Path(socket).is_absolute()
    token = pg["owner"].url.database.removeprefix("ar_migration_")
    env = tool_environment(socket, "ar_restore_" + token + "_version")
    tools = {}
    for name in ("pg_dump", "pg_restore"):
        executable = binary / name
        assert executable.is_file()
        version = (
            run_tool(
                [str(executable), "--version"],
                directory,
                label=name.replace("_", "-") + "-version",
                env=env,
                timeout=5,
            )
            .read_text()
            .strip()
        )
        assert version == name + " (PostgreSQL) 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1)", (
            "unreviewed PostgreSQL tool version"
        )
        tools[name] = {
            "path": str(executable),
            "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
            "version": version,
        }
    save(directory, "tools", tools, record_property)
    return binary, socket, port, token


def capture(fixture, pg, directory, name, record_property):
    snapshot = native_snapshot(fixture.case, pg)
    try:
        with fixture.case.engine.begin() as connection:
            connection.exec_driver_sql("SET LOCAL statement_timeout='2000ms'")
            connection.exec_driver_sql("SET LOCAL lock_timeout='1000ms'")
            authority = observe_authority(connection, pg)
            progress = [
                dict(row)
                for row in connection.exec_driver_sql(
                    "SELECT revision,phase,source_digest,cursor::text AS cursor,rows_verified,"
                    "status,updated_at FROM migration_progress ORDER BY revision,phase"
                ).mappings()
            ]
    finally:
        drain(pg)
    result = {"snapshot": typed(snapshot), "authority": authority, "progress": typed(progress)}
    save(directory, name, result, record_property)
    return result


def copy_ciphertexts(source, destination):
    manifest = read_manifest()
    expected = {item["address"]: item for item in manifest["objects"].values()}
    assert len(expected) == 18 and {path.name for path in source.iterdir()} == set(expected)
    destination.mkdir(mode=0o700)
    cipher = Fernet(manifest["synthetic_fernet_key"].encode())
    hashes = {}
    for address, item in sorted(expected.items()):
        data = (source / address).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        assert digest == item["ciphertext_sha256"]
        assert hashlib.sha256(cipher.decrypt(data)).hexdigest() == address
        with (destination / address).open("xb") as handle:
            os.chmod(destination / address, 0o600)
            handle.write(data)
        hashes[address] = digest
    return hashes


def target_view(fixture, pg, engines):
    target_pg = {**pg, **engines}
    target_fixture = replace(fixture, case=replace(fixture.case, engine=engines["owner"]))
    # Retain original witnesses by identity; restored data must never become expectations.
    assert target_fixture.before is fixture.before
    assert target_fixture.original is fixture.original
    assert target_fixture.case.adoption is fixture.case.adoption
    assert target_fixture.case.previous_progress is fixture.case.previous_progress
    return target_fixture, target_pg


@contextmanager
def bounded_admin(pg):
    with pg["control"].connect() as connection:
        connection.exec_driver_sql("SET statement_timeout='2000ms'")
        connection.exec_driver_sql("SET lock_timeout='1000ms'")
        yield connection


@contextmanager
def empty_target(fixture, pg, directory, record_property):
    source = pg["owner"].url.database
    assert source.startswith("ar_migration_")
    target = "ar_restore_" + source.removeprefix("ar_migration_")
    assert len(target) == 43 and all(c in "0123456789abcdef" for c in target[11:])
    owner = pg["owner_role"]
    assert owner == source + "_owner"
    engines = {}
    created = False
    absence_observed = False
    cleanup = []
    try:
        with pg["control"].connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM pg_database WHERE datname=:name"), {"name": target}
                ).scalar_one()
                == 0
            )
            # All identifiers were validated above; no user/database-derived SQL fragment.
            connection.exec_driver_sql(f'CREATE DATABASE "{target}" OWNER "{owner}"')
            created = True
        for name in ("owner", "app", "admin"):
            engines[name] = create_engine(pg[name].url.set(database=target), poolclass=NullPool)
        with engines["owner"].begin() as connection:
            connection.exec_driver_sql("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        drain(pg, engines["owner"])
        yield target_view(fixture, pg, engines)
    finally:
        first = sys.exception()
        for name, engine in engines.items():
            try:
                engine.dispose()
            except BaseException as error:
                cleanup.append({"phase": "dispose-" + name, "error": type(error).__name__})
        if created:
            if "owner" in engines:
                try:
                    drain(pg, engines["owner"])
                except BaseException as error:
                    cleanup.append({"phase": "drain-target", "error": type(error).__name__})
            try:
                with bounded_admin(pg) as connection:
                    connection.exec_driver_sql(f'DROP DATABASE "{target}" WITH (FORCE)')
                    assert (
                        connection.execute(
                            text("SELECT count(*) FROM pg_database WHERE datname=:name"),
                            {"name": target},
                        ).scalar_one()
                        == 0
                    )
                    absence_observed = True
            except BaseException as error:
                cleanup.append({"phase": "drop-target", "error": type(error).__name__})
        try:
            save(
                directory,
                "target-cleanup",
                {
                    "target": target,
                    "created": created,
                    "absence_observed": absence_observed,
                    "errors": cleanup,
                },
                record_property,
            )
        except BaseException as error:
            cleanup.append({"phase": "cleanup-record", "error": type(error).__name__})
        if cleanup:
            if first is not None:
                first.add_note(
                    "owned restore target cleanup failed; retained cleanup record if writable"
                )
            else:
                raise AssertionError("owned restore target cleanup failed")


def denied_probe(engine, sql, parameters, *, json_parameters=()):
    """Rollback before evaluating the native denial, including unexpected success."""
    assert set(json_parameters) <= parameters.keys()
    statement = text(sql).bindparams(*(bindparam(name, type_=JSONB) for name in json_parameters))
    observed = None
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(statement, parameters)
        except DBAPIError as error:
            observed = getattr(error.orig, "sqlstate", None)
        finally:
            transaction.rollback()
        assert not transaction.is_active
    assert observed == "42501", "expected native application-role permission denial"
    return {"sql": sql, "sqlstate": observed, "rollback_acknowledged": True}


def assert_application_denials(fixture, pg, directory, record_property):
    before = capture(fixture, pg, directory, "before-role-probes", record_property)
    probes = []
    try:
        with pg["app"].connect() as connection:
            identity = tuple(
                connection.exec_driver_sql("SELECT current_user,current_database()").one()
            )
            assert identity == (pg["app_role"], pg["app"].url.database)
            assert (
                connection.exec_driver_sql(
                    "SELECT nspname FROM pg_namespace WHERE nspname='public'"
                ).scalar_one()
                == "public"
            )
            permissions = [
                tuple(row)
                for row in connection.exec_driver_sql(
                    "SELECT c.relname,has_table_privilege(current_user,c.oid,'SELECT'),"
                    "has_table_privilege(current_user,c.oid,'INSERT'),"
                    "has_table_privilege(current_user,c.oid,'UPDATE'),"
                    "has_table_privilege(current_user,c.oid,'DELETE'),"
                    "has_table_privilege(current_user,c.oid,'TRUNCATE') "
                    "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='public' AND c.relname IN "
                    "('budget_accounts','migration_progress') ORDER BY c.relname"
                )
            ]
            assert len(permissions) == 2 and all(not any(row[2:]) for row in permissions)
            for table, readable, *_ in permissions:
                if readable:
                    connection.exec_driver_sql(f"SELECT count(*) FROM {table}").scalar_one()
        drain(pg, pg["app"])
        for table in ("budget_accounts", "migration_progress"):
            with pg["owner"].connect() as connection:
                row = dict(
                    connection.exec_driver_sql(f"SELECT * FROM {table} ORDER BY 1 LIMIT 1")
                    .mappings()
                    .one()
                )
            drain(pg)
            names = list(row)
            params = {"p" + str(i): row[name] for i, name in enumerate(names)}
            insert = (
                f"INSERT INTO {table} ({','.join(names)}) VALUES ("
                + ",".join(":p" + str(i) for i in range(len(names)))
                + ")"
            )
            key = "id" if table == "budget_accounts" else "phase"
            # Keep the observed native dict; bind JSONB so the driver can reach
            # the actual permission check instead of refusing an untyped dict.
            cursor_parameter = ("p" + str(names.index("cursor")),) if "cursor" in row else ()
            for sql, arguments, json_parameters in [
                (insert, params, cursor_parameter),
                (f"UPDATE {table} SET {key}={key} WHERE {key}=:key", {"key": row[key]}, ()),
                (f"DELETE FROM {table} WHERE {key}=:key", {"key": row[key]}, ()),
                (f"TRUNCATE {table}", {}, ()),
            ]:
                probes.append(
                    denied_probe(pg["app"], sql, arguments, json_parameters=json_parameters)
                )
                drain(pg, pg["app"])
        for sql in (
            "ALTER SCHEMA public RENAME TO ar_restore_denied",
            "ALTER FUNCTION public.ar7_ledger_constraint() SET search_path=public",
        ):
            probes.append(denied_probe(pg["app"], sql, {}))
            drain(pg, pg["app"])
        assert len(probes) == 10
        save(
            directory,
            "role-probes",
            {
                "identity": identity,
                "permissions": permissions,
                "probes": probes,
            },
            record_property,
        )
    finally:
        drain(pg, pg["app"])
        after = capture(fixture, pg, directory, "after-role-probes", record_property)
        assert before == after
    assert copy_hashes(FIXTURE_ROOT / "objects") == fixture.encrypted


def copy_hashes(directory):
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.iterdir())
    }
