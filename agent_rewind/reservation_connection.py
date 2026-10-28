"""Private issued-connection ownership for a single P2 transaction body."""

from __future__ import annotations

import inspect
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from threading import RLock
from typing import Any
from weakref import WeakKeyDictionary

import psycopg
from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine, RootTransaction
from sqlalchemy.pool import PoolProxiedConnection, QueuePool

from .migrations.compatibility import require_bounded_runtime_engine
from .migrations.schema import MigrationRefused
from .operation_work import OperationWork
from .reservation_types import ReservationRefusal, ReservationScope
from .sqlite_ownership import ProgressLease, SQLiteOwnershipError, require_bounded_sqlite

_LOCK = RLock()


@dataclass
class ReservationBody:
    connection: Connection
    scope: ReservationScope
    work: OperationWork
    root: RootTransaction
    proxy: PoolProxiedConnection
    raw: Any
    pool: object
    lease: ProgressLease | None
    xid: str | None = None


_BODIES: WeakKeyDictionary[Connection, ReservationBody] = WeakKeyDictionary()


def require_engine(engine: Engine) -> None:
    """Require the existing bounded application plumbing, without acquiring it.

    This is a cooperative supported-engine boundary, not a Python-code sandbox.
    Custom creators and additional connect hooks are outside the P2 cohort.
    """
    if not isinstance(engine, Engine) or not isinstance(engine.pool, QueuePool):
        raise ReservationRefusal("transaction_not_owned")
    timeout = engine.pool.timeout()
    creator = engine.pool._creator
    if (
        type(timeout) not in (int, float)
        or not 0 < timeout <= 1
        or engine.pool._pre_ping
        or not inspect.isfunction(creator)
        or creator.__module__ != "sqlalchemy.engine.create"
        or creator.__name__ != "connect"
    ):
        raise ReservationRefusal("transaction_not_owned")
    closure = inspect.getclosurevars(creator).nonlocals
    if closure.get("dialect") is not engine.dialect:
        raise ReservationRefusal("transaction_not_owned")
    try:
        if engine.dialect.name == "sqlite":
            require_bounded_sqlite(engine)
        elif engine.dialect.name == "postgresql":
            require_bounded_runtime_engine(engine)
        else:
            raise ReservationRefusal("transaction_not_owned")
    except (SQLiteOwnershipError, MigrationRefused):
        raise ReservationRefusal("transaction_not_owned") from None


def _live(body: ReservationBody) -> None:
    connection, work = body.connection, body.work
    if (
        connection.closed
        or connection.invalidated
        or connection.get_transaction() is not body.root
        or not body.root.is_active
        or connection.in_nested_transaction()
        or bool(connection.get_execution_options())
        or not body.proxy.is_valid
        or body.proxy.is_detached
        or connection.connection is not body.proxy
        or body.proxy.driver_connection is not body.raw
        or connection.engine.pool is not body.pool
        or work._connection is not connection
        or work._raw is not body.raw
        or work._detached
        or not work._ready
        or connection.info.get("operation_work") is not work
        or any(not event.contains(connection, name, callback) for name, callback in work._listeners)
        or len(work._listeners) != 2
    ):
        raise ReservationRefusal("transaction_not_owned")
    raw = body.raw
    if connection.dialect.name == "sqlite":
        lease = body.lease
        if not isinstance(raw, sqlite3.Connection) or lease is None or lease._raw is not raw:
            raise ReservationRefusal("transaction_not_owned")
        receipt = lease._receipt
        physical = lease._raw._ownership
        if (
            work._lease is not lease
            or lease._released
            or lease._raw is not raw
            or lease._owner is not work
            or lease._generation != receipt.generation
            or receipt.connection is not connection
            or receipt.proxy is not body.proxy
            or receipt.raw is not raw
            or receipt.record is None
            or receipt.record.driver_connection is not raw
            or receipt.failed
            or receipt.completed
            or receipt.returned
            or physical.receipt is not receipt
            or physical.generation != receipt.generation
            or physical.lease is not lease
            or not physical.borrowed
            or physical.closed
            or physical.tainted
            or physical.unknown_callback
            or physical.native_busy
            or raw.isolation_level is None
            or not raw.in_transaction
        ):
            raise ReservationRefusal("transaction_not_owned")
    elif (
        connection.dialect.name != "postgresql"
        or raw.closed
        or raw.autocommit is not False
        or raw.info.transaction_status != psycopg.pq.TransactionStatus.INTRANS
    ):
        raise ReservationRefusal("transaction_not_owned")
    work.check()


def _xid(body: ReservationBody) -> str:
    # Check before SQL: an idle raw connection must not silently start another tx.
    _live(body)
    xid: Any = body.connection.exec_driver_sql("SELECT pg_current_xact_id()::text").scalar_one()
    _live(body)
    if type(xid) is not str or not 1 <= len(xid) <= 20 or not xid.isascii() or not xid.isdecimal():
        raise ReservationRefusal("transaction_not_owned")
    return xid


def require_body(connection: Connection, scope: ReservationScope) -> ReservationBody:
    if not isinstance(connection, Connection):
        raise ReservationRefusal("transaction_not_owned")
    with _LOCK:
        body = _BODIES.get(connection)
    if body is None or body.scope is not scope:
        raise ReservationRefusal("transaction_not_owned")
    _live(body)
    if body.xid is not None and _xid(body) != body.xid:
        raise ReservationRefusal("transaction_not_owned")
    return body


@contextmanager
def issued_connection(
    connection: Connection, scope: ReservationScope, work: OperationWork
) -> Iterator[ReservationBody]:
    require_engine(connection.engine)
    root = connection.get_transaction()
    if root is None:
        raise ReservationRefusal("transaction_not_owned")
    body = ReservationBody(
        connection,
        scope,
        work,
        root,
        connection.connection,
        connection.connection.driver_connection,
        connection.engine.pool,
        work._lease,
    )
    _live(body)
    if connection.dialect.name == "postgresql":
        body.xid = _xid(body)
    with _LOCK:
        if connection in _BODIES:
            raise ReservationRefusal("transaction_not_owned")
        _BODIES[connection] = body
    try:
        yield body
    finally:
        with _LOCK:
            if _BODIES.get(connection) is body:
                del _BODIES[connection]
