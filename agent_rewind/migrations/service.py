"""Atomic, explicit installation/adoption. No customer activation or automatic repair."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.engine import Connection, Dialect, Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import ConnectionPoolEntry

from ..sqlite_ownership import SQLiteOwnershipError, owned_connect
from .inputs import AdoptionMapping, source_digest, validate_legacy_rows, validate_mapping
from .schema import (
    ADMISSION,
    ARTIFACTS,
    BASELINE,
    HEAD,
    METADATA_TABLES,
    OWNERSHIP,
    PROJECTION,
    SOURCE_COMMIT,
    MigrationRefused,
    canonical,
    catalog,
    checksum,
    dialect,
    source_profile_checksum,
    verify_baseline,
    verify_installed_profile,
)

MIGRATOR_LOCK = 710381250019
_CONNECTION_HOOK_LOCK = Lock()


def _trusted_startup_path(
    dialect: Dialect, record: ConnectionPoolEntry, arguments: list[Any], parameters: dict[str, Any]
) -> None:
    options = parameters.get("options", "")
    if not isinstance(options, str):
        raise MigrationRefused("invalid_database_options")
    # libpq processes options in order; the trusted final value supersedes an
    # unsafe DSN/role default before SQLAlchemy probes current_schema().
    trusted_suffix = " -csearch_path=public,pg_temp"
    if not options.endswith(trusted_suffix):
        parameters["options"] = options + trusted_suffix


def _secure_engine(engine: Engine) -> None:
    if engine.dialect.name == "postgresql":
        with _CONNECTION_HOOK_LOCK:
            if not event.contains(engine, "do_connect", _trusted_startup_path):
                event.listen(engine, "do_connect", _trusted_startup_path)


def _postgres_exclusion(connection: Connection, tables: list[str]) -> None:
    authority = connection.execute(
        text("""
        SELECT r.oid, r.rolsuper, d.datdba, n.nspowner
        FROM pg_roles r, pg_database d, pg_namespace n
        WHERE r.rolname=current_user AND d.datname=current_database() AND n.nspname='public'
    """)
    ).one()
    if not authority[1] and authority[0] not in (authority[2], authority[3]):
        raise MigrationRefused("migration_owner_required")
    if connection.execute(
        text("""
        SELECT 1 FROM pg_namespace WHERE nspname NOT IN ('public','information_schema')
        AND nspname NOT LIKE 'pg_%' LIMIT 1
    """)
    ).first():
        raise MigrationRefused("unsupported_database_schema")
    if connection.execute(
        text("""
        SELECT 1 FROM pg_stat_activity a
        WHERE a.datname=current_database() AND a.pid<>pg_backend_pid()
        LIMIT 1
    """)
    ).first():
        raise MigrationRefused("writers_not_drained")
    # Check effective and SET ROLE authority, not just direct grants. Superusers are
    # trusted control-plane operators; they must never be application identities.
    if connection.execute(
        text("""
        SELECT 1 FROM pg_roles actor JOIN pg_roles effective
        ON actor.oid=effective.oid OR pg_has_role(actor.oid,effective.oid,'MEMBER')
        WHERE actor.rolcanlogin AND NOT actor.rolsuper AND actor.rolname<>current_user
        AND (effective.rolname=current_user
          OR has_schema_privilege(effective.oid,'public','CREATE')
          OR EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relkind='r'
            AND has_table_privilege(effective.oid,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE')))
        LIMIT 1
    """)
    ).first():
        raise MigrationRefused("writer_privileges_present")
    if tables:
        quoted = [connection.dialect.identifier_preparer.quote(t) for t in tables]
        connection.exec_driver_sql(
            "LOCK TABLE " + ",".join("public." + t for t in quoted) + " IN ACCESS EXCLUSIVE MODE"
        )


def _legacy_role_inventory(connection: Connection, mapping: AdoptionMapping) -> None:
    if dialect(connection) == "sqlite":
        if mapping.legacy_writer_roles:
            raise MigrationRefused("postgresql_role_inventory_inapplicable")
        return
    if not mapping.legacy_writer_roles:
        raise MigrationRefused("legacy_writer_inventory_required")
    for name in mapping.legacy_writer_roles:
        role = connection.execute(
            text(
                "SELECT oid,rolcanlogin,rolsuper,rolname=current_user "
                "FROM pg_roles WHERE rolname=:name"
            ),
            {"name": name},
        ).first()
        if role is None or role[1] or role[2] or role[3]:
            raise MigrationRefused("legacy_writer_role_not_disabled")
        if connection.execute(
            text(
                "SELECT 1 FROM pg_roles WHERE rolcanlogin AND NOT rolsuper "
                "AND rolname<>current_user AND pg_has_role(oid,:oid,'MEMBER') "
                "LIMIT 1"
            ),
            {"oid": role[0]},
        ).first():
            raise MigrationRefused("legacy_writer_membership_present")


@contextmanager
def migration_transaction(engine: Engine, timeout_seconds: int = 5) -> Iterator[Connection]:
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 30:
        raise MigrationRefused("invalid_lock_timeout")
    _secure_engine(engine)
    try:
        with owned_connect(engine) as connection:
            try:
                if dialect(connection) == "sqlite":
                    raw = connection.connection.driver_connection
                    if (
                        getattr(raw, "autocommit", -1) != -1
                        or getattr(raw, "isolation_level", None) is None
                    ):
                        # Explicit BEGIN and DBAPI commit/rollback require sqlite3
                        # legacy transaction control. Never return an unsupported
                        # pooled connection with an uncommitted schema snapshot.
                        connection.invalidate()
                        raise MigrationRefused("transactional_connection_required")
                    connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                    connection.exec_driver_sql(f"PRAGMA busy_timeout={timeout_seconds * 1000}")
                    connection.exec_driver_sql("BEGIN EXCLUSIVE")
                else:
                    if (
                        getattr(connection.connection.driver_connection, "autocommit", None)
                        is not False
                    ):
                        raise MigrationRefused("transactional_connection_required")
                    connection.begin()
                    # Omitting pg_catalog keeps built-ins implicitly first; explicitly
                    # placing pg_temp last prevents temporary relation shadowing.
                    connection.exec_driver_sql("SET LOCAL search_path TO public, pg_temp")
                    connection.execute(
                        text("SELECT set_config('lock_timeout',:value,true)"),
                        {"value": f"{timeout_seconds}s"},
                    )
                    connection.execute(
                        text("SELECT set_config('statement_timeout',:value,true)"),
                        {"value": f"{timeout_seconds * 4}s"},
                    )

                    acquired: bool = connection.execute(
                        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": MIGRATOR_LOCK}
                    ).scalar_one()
                    if not acquired:
                        raise MigrationRefused("migration_busy")
                    tables: list[str] = list(
                        connection.execute(
                            text("""
                        SELECT tablename FROM pg_tables WHERE schemaname='public'
                        ORDER BY tablename LIMIT 18
                    """)
                        ).scalars()
                    )
                    if len(tables) > 17:
                        raise MigrationRefused("schema_incompatible")
                    _postgres_exclusion(connection, tables)
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
    except SQLiteOwnershipError:
        raise MigrationRefused("migration_database_failure") from None
    except DBAPIError as error:
        state = getattr(error.orig, "sqlstate", None)
        locked = state in {"55P03", "57014"} or getattr(error.orig, "sqlite_errorcode", None) in {
            5,
            6,
        }
        raise MigrationRefused(
            "migration_busy" if locked else "migration_database_failure"
        ) from None


def _alembic(connection: Connection, operation: str, target: str) -> None:
    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent))
    config.attributes.update(connection=connection, validated_operator=True)
    if operation == "stamp":
        command.stamp(config, target)
    else:
        command.upgrade(config, target)


def _installed(connection: Connection, shape: dict[str, Any]) -> dict[str, Any]:
    if "alembic_version" not in shape:
        raise MigrationRefused("schema_incompatible")
    revisions: list[str] = list(
        connection.execute(text("SELECT version_num FROM alembic_version LIMIT 2")).scalars()
    )
    if len(revisions) != 1 or revisions[0] not in {
        HEAD,
        OWNERSHIP,
        ARTIFACTS,
        PROJECTION,
        ADMISSION,
    }:
        raise MigrationRefused("schema_incompatible")
    revision = revisions[0]
    verify_baseline(
        shape,
        dialect(connection),
        versioned=True,
        ownership=revision in {OWNERSHIP, ARTIFACTS, PROJECTION, ADMISSION},
        artifacts=revision in {ARTIFACTS, PROJECTION, ADMISSION},
        projection=revision in {PROJECTION, ADMISSION},
        admission=revision == ADMISSION,
    )
    verify_installed_profile(shape, dialect(connection), revision)
    rows = connection.execute(text("SELECT * FROM installation_adoptions LIMIT 2")).mappings().all()
    if len(rows) != 1 or rows[0]["installed_schema_fingerprint"] != checksum(shape):
        raise MigrationRefused("schema_incompatible")
    row = dict(rows[0])
    try:
        if isinstance(row["mapping"], str):
            row["mapping"] = json.loads(row["mapping"])
        created = row["created_at"]
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        if not isinstance(created, datetime) or created.utcoffset() is None:
            raise ValueError("invalid provenance timestamp")
        if row["mapping_digest"] != checksum(row["mapping"]):
            raise ValueError("mapping drift")
        if (
            row["singleton"] != 1
            or row["state"]
            not in ({"prepared"} if revision == HEAD else {"prepared", "ownership_complete"})
            or row["source_baseline"] != SOURCE_COMMIT
            or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", row["installation_key"])
        ):
            raise ValueError("invalid metadata")
        if row["schema_fingerprint"] != source_profile_checksum(
            dialect(connection), row["source_kind"]
        ):
            raise ValueError("source schema provenance drift")
        if row["source_kind"] == "fresh":
            null_fields = ["backup_evidence_digest", "drain_evidence_digest"]
            if row["state"] == "prepared":
                null_fields += ["organization_id", "project_id"]
            if row["mapping"] != {"schema": 1, "source_kind": "fresh"} or any(
                row[k] is not None for k in null_fields
            ):
                raise ValueError("fresh metadata drift")
        elif row["source_kind"] == "legacy":
            parsed = validate_mapping(row["mapping"])
            if bool(parsed.legacy_writer_roles) != (dialect(connection) == "postgresql"):
                raise ValueError("invalid role inventory")
            if (
                parsed.installation_key != row["installation_key"]
                or parsed.organization_id != row["organization_id"]
                or parsed.project_id != row["project_id"]
                or any(
                    not isinstance(row[k], str) or not re.fullmatch(r"[0-9a-f]{64}", row[k])
                    for k in ["backup_evidence_digest", "drain_evidence_digest"]
                )
            ):
                raise ValueError("legacy metadata drift")
        else:
            raise ValueError("invalid origin")
    except (ValueError, TypeError, RecursionError):
        raise MigrationRefused("adoption_metadata_drift") from None
    row["_revision"] = revision
    if revision in {OWNERSHIP, ARTIFACTS, PROJECTION, ADMISSION}:
        from .ownership_state import inspect_ownership_state

        inspect_ownership_state(connection, row)
    if revision in {PROJECTION, ADMISSION}:
        from .projection_state import inspect_projection_state

        inspect_projection_state(connection, row)
    return row


def _public_state(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "revision": row.get("_revision", HEAD),
        "state": row["state"],
        "source_kind": row["source_kind"],
        "installation_key": row["installation_key"],
        "customer_ready": False,
    }


def schema_status(engine: Engine, *, include_source_digest: bool = False) -> dict[str, Any]:
    """Read-only AR-005-C interface. Prepared never means service activation is safe."""
    database = engine.url.database
    if (
        engine.dialect.name == "sqlite"
        and isinstance(database, str)
        and database not in ("", ":memory:")
        and not Path(database).exists()
    ):
        return {"revision": None, "state": "empty", "customer_ready": False}
    _secure_engine(engine)
    try:
        with owned_connect(engine) as connection:
            if dialect(connection) == "postgresql":
                if (
                    getattr(connection.connection.driver_connection, "autocommit", None)
                    is not False
                ):
                    raise MigrationRefused("transactional_connection_required")
                connection.begin()
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                connection.exec_driver_sql("SET LOCAL search_path TO public, pg_temp")
            shape = catalog(connection)
            names = set(shape) - {"$postgres"}
            if not names:
                return {"revision": None, "state": "empty", "customer_ready": False}
            if names & METADATA_TABLES:
                return _public_state(_installed(connection, shape))
            verify_baseline(shape, dialect(connection))
            result: dict[str, Any] = {
                "revision": None,
                "state": "legacy_unversioned",
                "schema_fingerprint": checksum(shape),
                "customer_ready": False,
            }
            if include_source_digest:
                result["source_dataset_digest"] = source_digest(connection)
            return result
    except (DBAPIError, SQLiteOwnershipError):
        raise MigrationRefused("schema_unavailable") from None


def _record(
    connection: Connection,
    origin: str,
    installation_key: str,
    shape: dict[str, Any],
    mapping: dict[str, Any],
    backup: str | None = None,
    drain: str | None = None,
) -> dict[str, Any]:
    installed_shape = catalog(connection)
    verify_baseline(installed_shape, dialect(connection), versioned=True)
    verify_installed_profile(installed_shape, dialect(connection))
    row = {
        "installation_key": installation_key,
        "source_kind": origin,
        "source_baseline": SOURCE_COMMIT,
        "schema_fingerprint": checksum(shape),
        "installed_schema_fingerprint": checksum(installed_shape),
        "organization_id": mapping.get("organization_id"),
        "project_id": mapping.get("project_id"),
        "mapping_digest": checksum(mapping),
        "mapping": canonical(mapping).decode(),
        "backup_evidence_digest": backup,
        "drain_evidence_digest": drain,
        "created_at": datetime.now(UTC).isoformat(),
        "state": "prepared",
    }
    statement = """INSERT INTO installation_adoptions (
        singleton,installation_key,source_kind,source_baseline,schema_fingerprint,
        installed_schema_fingerprint,organization_id,project_id,mapping_digest,mapping,
        backup_evidence_digest,drain_evidence_digest,created_at,state
    ) VALUES (1,:installation_key,:source_kind,:source_baseline,:schema_fingerprint,
        :installed_schema_fingerprint,:organization_id,:project_id,:mapping_digest,:mapping,
        :backup_evidence_digest,:drain_evidence_digest,:created_at,:state)"""
    if dialect(connection) == "postgresql":
        # The JSON parameter must be explicitly typed for psycopg without changing source data.
        statement = statement.replace(":mapping,", "CAST(:mapping AS JSON),")
        statement = statement.replace(
            ":created_at,", "CAST(:created_at AS TIMESTAMP WITH TIME ZONE),"
        )
    connection.execute(text(statement), row)
    return _public_state(row)


def install(engine: Engine, installation_key: str, *, timeout_seconds: int = 5) -> dict[str, Any]:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", installation_key):
        raise MigrationRefused("invalid_installation_key")
    with migration_transaction(engine, timeout_seconds) as connection:
        shape = catalog(connection)
        names = set(shape) - {"$postgres"}
        if names:
            row = _installed(connection, shape)
            if (
                row.get("_revision") != HEAD
                or row["source_kind"] != "fresh"
                or row["state"] != "prepared"
                or row["installation_key"] != installation_key
                or row["mapping"] != {"schema": 1, "source_kind": "fresh"}
                or any(
                    row[k] is not None
                    for k in [
                        "organization_id",
                        "project_id",
                        "backup_evidence_digest",
                        "drain_evidence_digest",
                    ]
                )
            ):
                raise MigrationRefused("installation_conflict")
            return _public_state(row)
        _alembic(connection, "upgrade", HEAD)
        return _record(
            connection, "fresh", installation_key, shape, {"schema": 1, "source_kind": "fresh"}
        )


def adopt(
    engine: Engine,
    mapping: AdoptionMapping | dict[str, Any],
    backup_evidence: str,
    drain_evidence: str,
    *,
    timeout_seconds: int = 5,
) -> dict[str, Any]:
    parsed = validate_mapping(
        mapping.model_dump() if isinstance(mapping, AdoptionMapping) else mapping
    )
    if any(
        not re.fullmatch(r"[0-9a-f]{64}", evidence)
        for evidence in (backup_evidence, drain_evidence)
    ):
        raise MigrationRefused("invalid_operator_evidence")
    with migration_transaction(engine, timeout_seconds) as connection:
        _legacy_role_inventory(connection, parsed)
        shape = catalog(connection)
        if set(shape) & METADATA_TABLES:
            row = _installed(connection, shape)
            if (
                row.get("_revision") != HEAD
                or row["source_kind"] != "legacy"
                or row["state"] != "prepared"
                or row["mapping"] != parsed.model_dump()
                or row["backup_evidence_digest"] != backup_evidence
                or row["drain_evidence_digest"] != drain_evidence
            ):
                raise MigrationRefused("adoption_conflict")
            validate_legacy_rows(connection, parsed)
            return _public_state(row)
        verify_baseline(shape, dialect(connection))
        validate_legacy_rows(connection, parsed)
        _alembic(connection, "stamp", BASELINE)
        _alembic(connection, "upgrade", HEAD)
        return _record(
            connection,
            "legacy",
            parsed.installation_key,
            shape,
            parsed.model_dump(),
            backup_evidence,
            drain_evidence,
        )


def upgrade(engine: Engine, target: str = HEAD, *, timeout_seconds: int = 5) -> dict[str, Any]:
    if target == ADMISSION:
        from .admission_service import initialize_admission

        return initialize_admission(engine, timeout_seconds=timeout_seconds)
    if target == PROJECTION:
        from .projection_service import initialize_projection

        return initialize_projection(engine, timeout_seconds=timeout_seconds)
    if target == ARTIFACTS:
        from .artifact_service import initialize_artifacts

        return initialize_artifacts(engine, timeout_seconds=timeout_seconds)
    if target not in {HEAD, OWNERSHIP}:
        raise MigrationRefused("unsupported_target_revision")
    with migration_transaction(engine, timeout_seconds) as connection:
        row = _installed(connection, catalog(connection))
        if row["_revision"] != target:
            raise MigrationRefused("explicit_ownership_initialization_required")
        return _public_state(row)
