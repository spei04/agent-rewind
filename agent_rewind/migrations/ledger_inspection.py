"""Complete, non-owning ledger state inspection for the drained operator."""

from __future__ import annotations

from weakref import WeakSet

from sqlalchemy.engine import Connection

from .ledger_reader_catalog import inspect_catalog
from .ledger_reader_financial import read_financial, validate_financial
from .ledger_reader_graph import read_graph, source_bounds
from .ledger_reader_history import read_history, read_revision
from .ledger_state import LedgerState, validate_ledger_chain
from .ledger_transaction import _require_ledger_body
from .schema import ADMISSION, MigrationRefused, dialect, schema_table_names

_ACTIVE: WeakSet[Connection] = WeakSet()


def inspect_ledger_state(connection: Connection) -> LedgerState:
    """Prove the whole retained state using the caller's issued exclusion and budget.

    This does not establish current request authority or initialization eligibility.
    SQLite's issued transaction retains its cooperative no-raw-transaction-control
    precondition; PostgreSQL additionally rechecks the native transaction identity.
    """
    work = _require_ledger_body(connection)
    if connection in _ACTIVE:
        raise MigrationRefused("transactional_connection_required")
    _ACTIVE.add(connection)
    try:
        if (
            dialect(connection) == "sqlite"
            and connection.exec_driver_sql("SELECT 1 FROM sqlite_temp_master LIMIT 1").first()
        ):
            raise MigrationRefused("schema_incompatible")
        schema_table_names(connection)
        revision = read_revision(connection)
        shape = inspect_catalog(connection, revision, work)
        history = read_history(connection, revision, shape, work)
        counts = source_bounds(connection, work)
        financial = read_financial(connection, revision, work)
        validate_financial(financial, history, work)
        read_graph(connection, counts, history, financial, work)
        if revision == ADMISSION:
            state = LedgerState(
                status="absent",
                installation_key=history.adoption["installation_key"],
                revision="ar_0006_admission",
                head=None,
                manifest_count=0,
                account_count=0,
                opening=None,
            )
        else:
            if history.opening is None:
                raise MigrationRefused("ledger_progress_invalid")
            state = LedgerState(
                status="complete",
                installation_key=history.adoption["installation_key"],
                revision="ar_0007_ledger",
                head=validate_ledger_chain(history.manifests, history.opening),
                manifest_count=len(history.manifests),
                account_count=len(financial["account"]),
                opening=history.opening,
            )
        if _require_ledger_body(connection) is not work:
            raise MigrationRefused("transactional_connection_required")
        work.check()
        return state
    finally:
        _ACTIVE.remove(connection)
