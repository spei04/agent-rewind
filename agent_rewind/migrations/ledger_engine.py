"""Private, single-attempt engines for the offline ledger operator."""

from __future__ import annotations

import os
import sqlite3
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from threading import RLock
from typing import Any, cast
from weakref import ReferenceType, WeakKeyDictionary, ref

import psycopg
import sqlalchemy
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg
from sqlalchemy.engine import Connection, Dialect, Engine, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.pool import NullPool, Pool, reset_none

from ..sqlite_ownership import (
    SQLiteOwnershipError,
    create_owned_sqlite_engine,
    require_owned_sqlite,
)
from .compatibility import CONNECT_TIMEOUT_SECONDS, _validate_runtime_endpoint
from .ledger_work import LedgerWork
from .schema import MigrationRefused
from .service import _trusted_startup_path

_LOCK = RLock()
_REGISTRY: WeakKeyDictionary[Engine, _EngineState] = WeakKeyDictionary()
_PG_PARAMETERS = {
    "dbname",
    "host",
    "hostaddr",
    "port",
    "user",
    "password",
    "sslmode",
    "sslrootcert",
    "sslcert",
    "sslkey",
    "application_name",
    "options",
    "connect_timeout",
    "target_session_attrs",
}


def _supported_versions(kind: str) -> None:
    try:
        supported = (
            version("sqlalchemy") == sqlalchemy.__version__ == "2.1.3"
            and sys.implementation.name == "cpython"
            and sys.version_info[:2] in {(3, 11), (3, 12)}
        )
        if kind == "postgresql":
            supported = supported and (
                version("psycopg") == psycopg.__version__ == "3.3.6"
                and version("psycopg-binary") == "3.3.6"
                and psycopg.pq.__impl__ == "binary"
            )
        else:
            supported = supported and sqlite3.sqlite_version_info >= (3, 35)
    except PackageNotFoundError:
        supported = False
    if not supported:
        raise MigrationRefused("schema_incompatible")


def _no_class_handlers(*classes: Any) -> None:
    # This finite check is deliberately tied to the pinned SQLAlchemy version.
    for cls in classes:
        dispatch = cls.dispatch
        for name in dispatch._event_names:
            levels = getattr(getattr(dispatch, name), "_clslevel", {})
            if any(levels.values()):
                raise MigrationRefused("schema_incompatible")


def _handlers(engine: Engine) -> dict[str, tuple[Any, ...]]:
    result: dict[str, tuple[Any, ...]] = {}
    for label, obj in (("engine", engine), ("pool", engine.pool), ("dialect", engine.dialect)):
        dispatch: Any = obj.dispatch
        for name in dispatch._event_names:
            callbacks = tuple(getattr(dispatch, name))
            if callbacks:
                result[f"{label}.{name}"] = callbacks
    return result


def _pg_parameters(arguments: Any, parameters: Mapping[str, Any], *, context: Any) -> None:
    if (
        arguments
        or set(parameters) - (_PG_PARAMETERS | {"context"})
        or context is None
        or parameters.get("context") is not context
    ):
        raise MigrationRefused("unsupported_runtime_endpoint")
    _validate_runtime_endpoint(parameters, production=True)
    for value in (
        parameters.get("target_session_attrs"),
        os.environ.get("PGTARGETSESSIONATTRS"),
    ):
        if value not in (None, "", "any"):
            raise MigrationRefused("unsupported_runtime_endpoint")


@dataclass
class LedgerEngineClaim:
    engine: Engine
    work: LedgerWork
    raw: Any = None
    connect_requested: bool = False
    physical_attempted: bool = False
    checked_out: bool = False
    released: bool = False

    def _begin_connect(self) -> None:
        if self.connect_requested or self.released:
            raise MigrationRefused("migration_database_failure")
        self.connect_requested = True


@dataclass
class _EngineState:
    # Identity witnesses must not root the Engine through pool/event closures.
    pool: ReferenceType[Pool]
    dialect: ReferenceType[Dialect]
    url: Any
    context: ReferenceType[Any] | None = None
    handlers: dict[str, tuple[ReferenceType[Any], ...]] = field(default_factory=dict)
    claim: LedgerEngineClaim | None = None
    poisoned: bool = False

    def resolved_handlers(self) -> dict[str, tuple[Any, ...]] | None:
        result: dict[str, tuple[Any, ...]] = {}
        for name, references in self.handlers.items():
            callbacks = tuple(reference() for reference in references)
            if any(callback is None for callback in callbacks):
                return None
            result[name] = callbacks
        return result


def create_ledger_engine(url: str) -> Engine:
    """Construct without connecting; only this factory grants ledger ownership."""
    try:
        if type(url) is not str:
            raise MigrationRefused("schema_incompatible")
        parsed = make_url(url)
    except ArgumentError:
        raise MigrationRefused("schema_incompatible") from None
    if parsed.drivername not in {"sqlite", "sqlite+pysqlite", "postgresql+psycopg"}:
        raise MigrationRefused("schema_incompatible")
    kind = "sqlite" if parsed.drivername.startswith("sqlite") else "postgresql"
    if kind == "postgresql" and (
        set(parsed.query) - _PG_PARAMETERS
        or any(type(value) is not str for value in parsed.query.values())
    ):
        # Plugins are consumed by create_engine before dialect validation.
        raise MigrationRefused("unsupported_runtime_endpoint")
    _supported_versions(kind)
    _no_class_handlers(Engine, Connection, Pool)
    if kind == "sqlite":
        try:
            engine = create_owned_sqlite_engine(url, pool_size=1, max_overflow=0)
        except SQLiteOwnershipError:
            raise MigrationRefused("schema_incompatible") from None
    else:
        engine = create_engine(
            parsed,
            poolclass=NullPool,
            pool_pre_ping=False,
            pool_reset_on_return=None,
            use_native_hstore=False,
            connect_args={"autocommit": False, "prepare_threshold": None},
        )
    try:
        _no_class_handlers(type(engine.dialect))
        arguments, parameters = engine.dialect.create_connect_args(engine.url)
        context = getattr(engine.dialect, "_psycopg_adapters_map", None)
        if kind == "postgresql":
            _pg_parameters(arguments, parameters, context=context)
        try:
            state = _EngineState(
                ref(engine.pool),
                ref(engine.dialect),
                engine.url,
                context=ref(context) if context is not None else None,
            )
        except TypeError:
            raise MigrationRefused("schema_incompatible") from None

        def connect(dialect: Dialect, record: Any, args: Any, params: Any) -> Any:
            with _LOCK:
                claim = state.claim
                if claim is None or not claim.connect_requested or claim.physical_attempted:
                    raise MigrationRefused("migration_database_failure")
                claim.physical_attempted = True
            claim.work.check()
            if kind == "sqlite":
                return None  # the existing owned factory retains the native receipt
            # create_engine merges these reviewed non-libpq driver parameters.
            supplied = dict(params)
            if supplied.pop("autocommit", None) is not False:
                raise MigrationRefused("schema_incompatible")
            if supplied.pop("prepare_threshold", object()) is not None:
                raise MigrationRefused("schema_incompatible")
            _pg_parameters(
                args, supplied, context=state.context() if state.context is not None else None
            )
            supplied["target_session_attrs"] = "any"
            _trusted_startup_path(dialect, record, [], supplied)
            statement_ms, lock_ms = claim.work.remaining_timeouts_ms()
            supplied["options"] += f" -cstatement_timeout={statement_ms} -clock_timeout={lock_ms}"
            supplied["connect_timeout"] = CONNECT_TIMEOUT_SECONDS
            # Retain before SQLAlchemy runs its eventless initialization.
            raw = psycopg.connect(**supplied, autocommit=False, prepare_threshold=None)
            claim.raw = raw
            return raw

        def checkout(_raw: Any, _record: Any, _proxy: Any) -> None:
            with _LOCK:
                claim = state.claim
                if claim is None or not claim.connect_requested or claim.checked_out:
                    raise MigrationRefused("migration_database_failure")
                claim.checked_out = True

        event.listen(engine, "do_connect", connect, insert=True)
        event.listen(engine, "checkout", checkout, insert=True)
        handlers = _handlers(engine)
        expected = {"pool.connect": 2, "pool.checkout": 1, "dialect.do_connect": 1}
        if kind == "sqlite":
            expected.update(
                {"pool.checkout": 2, "pool.reset": 1, "pool.checkin": 1, "dialect.do_connect": 2}
            )
        if {key: len(value) for key, value in handlers.items()} != expected:
            raise MigrationRefused("schema_incompatible")
        try:
            state.handlers = {
                name: tuple(ref(callback) for callback in callbacks)
                for name, callbacks in handlers.items()
            }
        except TypeError:
            raise MigrationRefused("schema_incompatible") from None
        with _LOCK:
            _REGISTRY[engine] = state
        return engine
    except BaseException:
        engine.dispose()
        raise


def claim_ledger_engine(engine: Engine, work: LedgerWork) -> LedgerEngineClaim:
    if type(engine) is not Engine or type(work) is not LedgerWork:
        raise MigrationRefused("schema_incompatible")
    _supported_versions(engine.dialect.name)
    _no_class_handlers(Engine, Connection, Pool, type(engine.dialect))
    with _LOCK:
        state = _REGISTRY.get(engine)
        pool = state.pool() if state is not None else None
        dialect = state.dialect() if state is not None else None
        handlers = state.resolved_handlers() if state is not None else None
        if (
            state is None
            or pool is None
            or dialect is None
            or handlers is None
            or state.poisoned
            or state.claim is not None
            or engine.pool is not pool
            or engine.dialect is not dialect
            or engine.url != state.url
            or _handlers(engine) != handlers
            or engine.pool._pre_ping
            or engine.pool._reset_on_return is not reset_none
            or bool(engine._execution_options)
        ):
            raise MigrationRefused("schema_incompatible")
        if engine.dialect.name == "sqlite":
            require_owned_sqlite(engine)
        else:
            context = state.context() if state.context is not None else None
            if (
                context is None
                or not isinstance(engine.dialect, PGDialect_psycopg)
                or engine.dialect.use_native_hstore
                or engine.dialect.client_encoding is not None
                or engine.dialect.isolation_level is not None
                or engine.dialect._psycopg_adapters_map is not context
            ):
                raise MigrationRefused("schema_incompatible")
            args, params = cast(Dialect, engine.dialect).create_connect_args(engine.url)
            _pg_parameters(args, params, context=context)
        work._prepay()
        claim = LedgerEngineClaim(engine, work)
        state.claim = claim
        return claim


def release_ledger_engine(claim: LedgerEngineClaim, *, clean: bool) -> None:
    if type(claim) is not LedgerEngineClaim or type(clean) is not bool:
        raise MigrationRefused("migration_database_failure")
    with _LOCK:
        state = _REGISTRY.get(claim.engine)
        if (
            type(claim) is not LedgerEngineClaim
            or type(clean) is not bool
            or claim.released
            or state is None
            or state.claim is not claim
        ):
            raise MigrationRefused("migration_database_failure")
        claim.released = True
        state.claim = None
        if not clean:
            state.poisoned = True
