"""Read-only release compatibility. This release cannot admit customer workloads."""

from __future__ import annotations

import ipaddress
import math
import os
import sqlite3
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from threading import Lock
from typing import Any, Literal
from weakref import WeakKeyDictionary

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import event, text
from sqlalchemy.engine import Connection, Dialect, Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import ConnectionPoolEntry

from ..sqlite_ownership import optional_progress, owned_connect, owned_receipt, quarantine_owned
from .schema import (
    ADMISSION,
    ARTIFACTS,
    HEAD,
    OWNERSHIP,
    PROJECTION,
    MigrationRefused,
    catalog,
    dialect,
)
from .service import _installed

POOL_TIMEOUT_SECONDS = 1
CONNECT_TIMEOUT_SECONDS = 3
INSPECTION_TIMEOUT_SECONDS = 2
_CONNECT_HOOK_LOCK = Lock()


@dataclass
class _RuntimePolicy:
    production: bool


_RUNTIME_POLICIES: WeakKeyDictionary[Engine, _RuntimePolicy] = WeakKeyDictionary()


class BackfillRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    revision: str = Field(pattern=r"^[a-z0-9_]{1,32}$")
    phase: str = Field(pattern=r"^[a-z0-9_]{1,64}$")


class RevisionProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    revision: Literal[
        "ar_0002_adoption",
        "ar_0003_ownership",
        "ar_0004_artifacts",
        "ar_0005_run_index",
        "ar_0006_admission",
    ]
    catalog_profile: Literal[
        "adoption_v1", "ownership_v1", "artifacts_v1", "projection_v1", "admission_v1"
    ]
    mode: Literal["migration_only"]
    required_completed_backfills: tuple[BackfillRequirement, ...] = Field(max_length=16)

    @model_validator(mode="after")
    def unique_backfills(self) -> RevisionProfile:
        expected = {
            HEAD: "adoption_v1",
            OWNERSHIP: "ownership_v1",
            ARTIFACTS: "artifacts_v1",
            PROJECTION: "projection_v1",
            ADMISSION: "admission_v1",
        }[self.revision]
        if self.catalog_profile != expected:
            raise ValueError("Revision catalog profile mismatch")
        requirements: tuple[BackfillRequirement, ...] = (
            (BackfillRequirement(revision=OWNERSHIP, phase="ownership"),)
            if self.revision != HEAD
            else ()
        )
        if self.revision in {PROJECTION, ADMISSION}:
            requirements += (BackfillRequirement(revision=PROJECTION, phase="run_index"),)
        if self.revision != HEAD and self.required_completed_backfills != requirements:
            raise ValueError("Required backfill differs")
        if len(set(self.required_completed_backfills)) != len(self.required_completed_backfills):
            raise ValueError("Duplicate backfill requirements")
        return self


class ReleaseProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    manifest_version: Literal[1]
    release: Literal["0.1.0"]
    revisions: tuple[RevisionProfile, ...] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def unique_revisions(self) -> ReleaseProfile:
        if len({profile.revision for profile in self.revisions}) != len(self.revisions):
            raise ValueError("Duplicate revision")
        return self


def load_release_profile() -> ReleaseProfile:
    # Package-owned immutable data, never a database reflection or environment override.
    resource = files("agent_rewind.migrations").joinpath("release_compatibility.json")
    with resource.open("rb") as handle:
        content = handle.read(16385)
    if len(content) > 16384:
        raise ValueError("Release profile exceeds its bound")
    return ReleaseProfile.model_validate_json(content)


@dataclass(frozen=True)
class CompatibilityResult:
    status: Literal["ready", "incompatible", "unavailable"]
    code: str
    # A future ready handler must derive this from its validated adoption row in
    # the same inspection transaction. Missing identity cannot authorize a sentinel.
    installation_key: str | None = None


class SchemaNotReady(RuntimeError):
    def __init__(self, result: CompatibilityResult):
        self.result = result
        super().__init__(result.code)


def _bounded_connect(
    dialect: Dialect,
    record: ConnectionPoolEntry,
    arguments: list[Any],
    parameters: dict[str, Any],
    *,
    production: bool = False,
) -> None:
    if arguments:
        raise MigrationRefused("unsupported_runtime_endpoint")
    _validate_runtime_endpoint(parameters, production=production)
    options = parameters.get("options", "")
    if not isinstance(options, str):
        raise MigrationRefused("invalid_database_options")
    suffix = " -cstatement_timeout=2000 -clock_timeout=250 -csearch_path=public,pg_temp"
    if not options.endswith(suffix):
        parameters["options"] = options + suffix
    parameters["connect_timeout"] = CONNECT_TIMEOUT_SECONDS


def _validate_runtime_endpoint(parameters: Mapping[str, Any], *, production: bool) -> None:
    # libpq may fill absent routing fields from the environment. Refuse hidden
    # routing rather than validate a URL and then connect to a different endpoint.
    if any(
        parameters.get(key) or os.environ.get(env)
        for key, env in (
            ("service", "PGSERVICE"),
            ("servicefile", "PGSERVICEFILE"),
        )
    ):
        raise MigrationRefused("explicit_runtime_endpoint_required")
    for key, env in (("host", "PGHOST"), ("hostaddr", "PGHOSTADDR"), ("port", "PGPORT")):
        if os.environ.get(env) and not parameters.get(key):
            raise MigrationRefused("explicit_runtime_endpoint_required")
    host, address = parameters.get("host", ""), parameters.get("hostaddr", "")
    if not isinstance(host, str) or not isinstance(address, str):
        raise MigrationRefused("unsupported_runtime_endpoint")
    if "," in host or "," in address or not (host or address):
        raise MigrationRefused("unsupported_runtime_endpoint")
    port = parameters.get("port", 5432)
    if not isinstance(port, str | int) or not str(port).isdigit() or not 1 <= int(port) <= 65535:
        raise MigrationRefused("unsupported_runtime_endpoint")
    if production:
        endpoint = address or host
        if not endpoint.startswith("/"):
            try:
                ipaddress.ip_address(endpoint)
            except ValueError:
                raise MigrationRefused("numeric_runtime_endpoint_required") from None


def configure_runtime_engine(engine: Engine, *, production: bool = False) -> None:
    """Configure before first checkout; validate final DBAPI parameters again.

    Production uses one numeric address/socket so DNS is outside the connection
    path. A logical host may accompany hostaddr for TLS hostname verification.
    Development DNS resolution remains subject to the operating system resolver.
    An already production-configured engine cannot be downgraded by its wrapper.
    """
    if engine.dialect.name == "sqlite":
        return
    if engine.dialect.name != "postgresql" or engine.dialect.driver != "psycopg":
        raise MigrationRefused("unsupported_runtime_database")
    arguments, parameters = engine.dialect.create_connect_args(engine.url)
    if arguments:
        raise MigrationRefused("unsupported_runtime_endpoint")
    _validate_runtime_endpoint(parameters, production=production)
    with _CONNECT_HOOK_LOCK:
        policy = _RUNTIME_POLICIES.get(engine)
        if policy is None:
            policy = _RuntimePolicy(production)
            _RUNTIME_POLICIES[engine] = policy

            def connect(
                dialect: Dialect,
                record: ConnectionPoolEntry,
                arguments: list[Any],
                parameters: dict[str, Any],
            ) -> None:
                _bounded_connect(
                    dialect, record, arguments, parameters, production=policy.production
                )

            event.listen(engine, "do_connect", connect)
        else:
            policy.production = policy.production or production


@dataclass(frozen=True)
class _InspectionChecks:
    """One caller-owned deadline; this view grants no ledger transaction rights."""

    deadline: float

    def remaining(self) -> int:
        milliseconds = math.floor((self.deadline - time.monotonic()) * 1000)
        if milliseconds <= 0:
            raise TimeoutError("inspection deadline")
        return milliseconds

    def check(self) -> None:
        self.remaining()


@contextmanager
def _inspection(
    connection: Connection,
    *,
    coherent_snapshot: bool = False,
    checks: _InspectionChecks | None = None,
) -> Iterator[_InspectionChecks]:
    """Own one idle connection transaction; restore session state before pool return."""
    if connection.in_transaction():
        raise MigrationRefused("idle_inspection_connection_required")
    kind = dialect(connection)
    raw = connection.connection.driver_connection
    if raw is None:
        raise MigrationRefused("unsupported_runtime_database")
    if checks is None:
        checks = _InspectionChecks(time.monotonic() + INSPECTION_TIMEOUT_SECONDS)
    deadline = checks.deadline
    if coherent_snapshot:
        checks.check()
        if kind == "sqlite" and getattr(raw, "in_transaction", False):
            raise MigrationRefused("idle_inspection_connection_required")
        if kind == "postgresql" and raw.info.transaction_status != 0:
            raise MigrationRefused("idle_inspection_connection_required")
    previous: tuple[int, int] | None = None

    def remaining() -> int:
        return checks.remaining()

    def setup_check() -> None:
        if coherent_snapshot:
            checks.check()

    def before_query(
        connection: Connection,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        milliseconds = remaining()
        if kind == "postgresql":
            cursor.execute(f"SET LOCAL statement_timeout = '{milliseconds}ms'")
            if coherent_snapshot:
                milliseconds = remaining()
            cursor.execute(f"SET LOCAL lock_timeout = '{min(milliseconds, 250)}ms'")
            setup_check()

    # Capture before effects; failed nested acquisition owns no cleanup rights.
    receipt = owned_receipt(connection)
    lease = optional_progress(connection, owner=object())
    progress = False
    listener = False
    native_begin_attempted = False
    primary: BaseException | None = None
    cleanup_error: BaseException | None = None
    interruption: BaseException | None = None

    def failed(error: BaseException) -> None:
        nonlocal cleanup_error, interruption
        if cleanup_error is None:
            cleanup_error = error
        if interruption is None and not isinstance(error, Exception):
            interruption = error

    try:
        if kind == "sqlite":
            if not isinstance(raw, sqlite3.Connection):
                raise MigrationRefused("unsupported_runtime_database")
            setup_check()
            query_only = raw.execute("PRAGMA query_only").fetchone()[0]
            setup_check()
            busy_timeout = raw.execute("PRAGMA busy_timeout").fetchone()[0]
            previous = (query_only, busy_timeout)
            setup_check()
            raw.execute("PRAGMA query_only=ON")
            setup_check()
            raw.execute("PRAGMA busy_timeout=250")
            setup_check()
            progress = True

            def callback() -> int:
                return int(time.monotonic() >= deadline)

            if lease is None:
                raw.set_progress_handler(callback, 1000)
            else:
                lease.install(callback, 1000)
        elif getattr(raw, "autocommit", None) is not False:
            raise MigrationRefused("transactional_connection_required")
        setup_check()
        connection.begin()
        setup_check()
        # Install before coherent setup so its PostgreSQL targets get fresh caps too.
        if coherent_snapshot:
            listener = True
            event.listen(connection, "before_cursor_execute", before_query)
        if kind == "postgresql":
            transaction_mode = (
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                if coherent_snapshot
                else "SET TRANSACTION READ ONLY"
            )
            connection.exec_driver_sql(transaction_mode)
            setup_check()
            connection.exec_driver_sql("SET LOCAL search_path TO public, pg_temp")
            setup_check()
        elif coherent_snapshot:
            # sqlite3 legacy transaction control does not BEGIN for SELECT.
            native_begin_attempted = True
            connection.exec_driver_sql("BEGIN")
            setup_check()
        if not coherent_snapshot:
            listener = True
            event.listen(connection, "before_cursor_execute", before_query)
        yield checks
        remaining()
    except BaseException as error:
        primary = error
    finally:
        if listener:
            try:
                if event.contains(connection, "before_cursor_execute", before_query):
                    event.remove(connection, "before_cursor_execute", before_query)
            except BaseException as error:
                failed(error)
        try:
            if lease is not None:
                lease.release()
            elif progress:
                raw.set_progress_handler(None, 0)
        except BaseException as error:
            failed(error)
        try:
            connection.rollback()
            if native_begin_attempted and raw.in_transaction:
                # Python 3.12 autocommit=True makes DBAPI rollback a no-op,
                # even after our explicit BEGIN. Discharge only our own attempt.
                raw.execute("ROLLBACK")
                if raw.in_transaction:
                    raise RuntimeError("inspection native rollback not acknowledged")
            if previous is not None and cleanup_error is None:
                raw.execute(f"PRAGMA query_only={previous[0]}")
                raw.execute(f"PRAGMA busy_timeout={previous[1]}")
        except BaseException as error:
            failed(error)
        if cleanup_error is not None:
            quarantine_owned(receipt)
            try:
                connection.invalidate()
            except BaseException as error:
                failed(error)
    if primary is not None:
        raise primary from None
    if interruption is not None:
        raise interruption from None
    if cleanup_error is not None:
        raise cleanup_error from None
    setup_check()


def check_schema_compatibility(
    connection: Connection, release_profile: ReleaseProfile
) -> CompatibilityResult:
    """Inspect an idle connection without schema/data writes or cached success.

    The caller must establish the trusted startup namespace before any PostgreSQL
    dialect probes; configure_runtime_engine does so for production wrappers.
    The first release deliberately has no customer-ready revision. A later scoped
    release must extend both the manifest and validated revision/state handlers.
    """
    checks = _InspectionChecks(time.monotonic() + INSPECTION_TIMEOUT_SECONDS)
    return _check_schema_compatibility(connection, release_profile, checks)


def _check_schema_compatibility(
    connection: Connection,
    release_profile: ReleaseProfile,
    checks: _InspectionChecks,
) -> CompatibilityResult:
    try:
        checks.check()
        # Revalidate even constructed/copy-modified models; no arbitrary caller profile
        # can turn the adoption revision into a customer-ready revision.
        profile = ReleaseProfile.model_validate_json(release_profile.model_dump_json())
        with _inspection(connection, coherent_snapshot=True, checks=checks):
            shape = catalog(connection)
            checks.check()
            if "alembic_version" not in shape:
                return CompatibilityResult("incompatible", "schema_incompatible")
            revisions: list[str] = list(
                connection.execute(
                    text("SELECT version_num FROM alembic_version LIMIT 2")
                ).scalars()
            )
            checks.check()
            selected = [p for p in profile.revisions if revisions == [p.revision]]
            if len(selected) != 1:
                return CompatibilityResult("incompatible", "schema_incompatible")
            _installed(connection, shape)
            checks.check()
            for requirement in selected[0].required_completed_backfills:
                rows: Sequence[str] = (
                    connection.execute(
                        text(
                            "SELECT status FROM migration_progress "
                            "WHERE revision=:revision AND phase=:phase LIMIT 2"
                        ),
                        requirement.model_dump(),
                    )
                    .scalars()
                    .all()
                )
                checks.check()
                if rows != ["complete"]:
                    return CompatibilityResult("incompatible", "backfill_incomplete")
            return CompatibilityResult("incompatible", "migration_only")
    except ValidationError:
        return CompatibilityResult("incompatible", "release_profile_invalid")
    except MigrationRefused:
        return CompatibilityResult("incompatible", "schema_incompatible")
    except (SQLAlchemyError, sqlite3.Error, OSError, TimeoutError):
        return CompatibilityResult("unavailable", "schema_unavailable")


def runtime_schema_compatibility(engine: Engine) -> CompatibilityResult:
    """Production entry point: only the packaged release profile is consumed."""
    checks = _InspectionChecks(time.monotonic() + INSPECTION_TIMEOUT_SECONDS)
    try:
        profile = load_release_profile()
        configure_runtime_engine(engine)
        database = engine.url.database
        if (
            engine.dialect.name == "sqlite"
            and isinstance(database, str)
            and database not in ("", ":memory:")
            and not Path(database).is_file()
        ):
            return CompatibilityResult("incompatible", "schema_incompatible")
        checks.check()
        with owned_connect(engine) as connection:
            result = _check_schema_compatibility(connection, profile, checks)
        # Connection return is part of this invocation, unlike the direct API's
        # already-connected caller. Never reset the deadline after acquisition.
        checks.check()
        return result
    except (ValueError, ValidationError, MigrationRefused):
        return CompatibilityResult("incompatible", "release_profile_or_connection_invalid")
    except (SQLAlchemyError, sqlite3.Error, OSError, TimeoutError):
        return CompatibilityResult("unavailable", "schema_unavailable")


def runtime_database_connectivity(engine: Engine) -> bool:
    """Legacy health check: bounded read-only SELECT1, never schema readiness."""
    try:
        configure_runtime_engine(engine)
        database = engine.url.database
        if (
            engine.dialect.name == "sqlite"
            and isinstance(database, str)
            and database not in ("", ":memory:")
            and not Path(database).is_file()
        ):
            return False
        with owned_connect(engine) as connection, _inspection(connection):
            return bool(connection.exec_driver_sql("SELECT 1").scalar_one() == 1)
    except (SQLAlchemyError, sqlite3.Error, OSError, TimeoutError, MigrationRefused):
        return False
