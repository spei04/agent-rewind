"""Explicit atomic ledger initialization/provisioning; no automatic recovery retry."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from sqlalchemy import BigInteger, Integer, String, bindparam, text
from sqlalchemy.engine import Connection, CursorResult, Engine

from .inputs import validate_mapping
from .ledger_inputs import LedgerManifest, validate_ledger_manifest, validate_time
from .ledger_inspection import _inspect_ledger_context, _LedgerContext
from .ledger_provisioning import _classify_manifest, _ledger_cursors, _prepare_ledger
from .ledger_reader_catalog import inspect_catalog
from .ledger_reader_financial import read_financial, validate_financial
from .ledger_reader_graph import read_graph, source_bounds
from .ledger_reader_history import read_history
from .ledger_schema import create_ledger_constraints
from .ledger_source import source_digest
from .ledger_state import (
    LedgerManifestReceipt,
    LedgerProvisioning,
    LedgerState,
    ManifestCursor,
    OpeningCursor,
    validate_ledger_chain,
)
from .ledger_transaction import LedgerOutcome, _require_ledger_body, ledger_transaction
from .ledger_work import LedgerWork
from .ledger_writer_sql import PARAMETER_TYPES, SQL
from .schema import LEDGER, MigrationRefused, canonical, checksum, dialect
from .service import _legacy_role_inventory

_TYPES = {"String": String, "BigInteger": BigInteger, "Integer": Integer}


def _execute(
    connection: Connection, name: str, values: dict[str, Any] | None = None
) -> CursorResult[Any]:
    key = (dialect(connection), name)
    statement = text(SQL[key]).bindparams(
        *(bindparam(field, type_=_TYPES[kind]) for field, kind in PARAMETER_TYPES[key].items())
    )
    return connection.execute(statement, {} if values is None else values)


def _write(connection: Connection, name: str, values: dict[str, Any]) -> None:
    with _execute(connection, name, values) as result:
        if result.rowcount != 1:
            raise MigrationRefused("migration_database_failure")


def _checked_manifest(manifest: LedgerManifest) -> LedgerManifest:
    if not isinstance(manifest, LedgerManifest):
        raise MigrationRefused("invalid_ledger_manifest")
    try:
        return validate_ledger_manifest(manifest.model_dump(mode="json"))
    except (ValueError, TypeError, RecursionError):
        raise MigrationRefused("invalid_ledger_manifest") from None


def _legacy_inventory(connection: Connection, context: _LedgerContext) -> None:
    adoption = context.history.adoption
    if adoption["source_kind"] == "legacy":
        _legacy_role_inventory(connection, validate_mapping(adoption["mapping"]))


def _writer_owner(connection: Connection) -> None:
    if dialect(connection) != "postgresql":
        return
    with _execute(connection, "owner.compatibility") as result:
        rows = result.mappings().all()
    if (
        len(rows) != 1
        or set(rows[0]) != {"owner_compatible"}
        or rows[0]["owner_compatible"] is not True
    ):
        raise MigrationRefused("schema_incompatible")


def _projects(
    connection: Connection, manifest: LedgerManifest, organization: str, work: LedgerWork
) -> None:
    ids = sorted({row.project_id for row in manifest.accounts if row.project_id is not None})
    if not ids:
        return
    parameters = {
        f"project_{index:02d}": ids[index] if index < len(ids) else None for index in range(16)
    }
    with _execute(connection, "projects.gate", parameters) as result:
        receipts = result.mappings().all()
    if (
        len(receipts) != 1
        or set(receipts[0]) != {"candidate_rows", "invalid_rows", "native_bytes", "max_row_bytes"}
        or any(type(value) is not int for value in receipts[0].values())
        or receipts[0]["candidate_rows"] != len(ids)
        or receipts[0]["invalid_rows"] != 0
        or receipts[0]["native_bytes"] != 64 * len(ids)
        or receipts[0]["max_row_bytes"] != 64
    ):
        raise MigrationRefused("ledger_history_unsupported")
    with _execute(connection, "projects.body", parameters) as result:
        rows = result.mappings().all()
    if len(rows) != len(ids):
        raise MigrationRefused("ledger_history_unsupported")
    found = set()
    for row in rows:
        work.check()
        if (
            set(row) != {"id", "organization_id"}
            or type(row["id"]) is not str
            or type(row["organization_id"]) is not str
            or row["id"] not in ids
            or row["id"] in found
            or row["organization_id"] != organization
        ):
            raise MigrationRefused("ledger_history_unsupported")
        found.add(row["id"])
    if found != set(ids):
        raise MigrationRefused("ledger_history_unsupported")


def _upgrade(connection: Connection, manifest: LedgerManifest) -> None:
    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent))
    config.attributes.update(
        connection=connection, validated_operator=True, ledger_manifest=manifest
    )
    command.upgrade(config, LEDGER)


def _provenance(connection: Connection) -> tuple[str, str | None, int]:
    with _execute(connection, "provenance.observe") as result:
        rows = result.mappings().all()
    try:
        if len(rows) != 1 or set(rows[0]) != {"initialized_at", "database_role"}:
            raise ValueError("provenance receipt")
        observed, role = rows[0]["initialized_at"], rows[0]["database_role"]
        if type(observed) is not str or len(observed.encode("utf-8")) != 27:
            raise ValueError("provenance timestamp")
        validate_time(observed)
        if dialect(connection) == "sqlite":
            if role is not None:
                raise ValueError("SQLite role")
        elif type(role) is not str or not 1 <= len(role.encode("utf-8")) <= 63:
            raise ValueError("PostgreSQL role")
        uid = os.getuid()
        if type(uid) is not int or not 0 <= uid <= 2**63 - 1:
            raise ValueError("OS identity")
        return observed, role, uid
    except (ValueError, TypeError, UnicodeError):
        raise MigrationRefused("ledger_progress_invalid") from None


def _insert_progress(
    connection: Connection, cursor: ManifestCursor | OpeningCursor, work: LedgerWork
) -> None:
    work.check()
    if isinstance(cursor, OpeningCursor):
        phase, source, count = "ledger_opening", cursor.source_digest, cursor.job_count
    else:
        phase = "ledger_manifest_" + cursor.manifest.manifest_id
        source, count = cursor.manifest.source_digest, cursor.account_count
    _write(
        connection,
        "progress.insert",
        {
            "revision": LEDGER,
            "phase": phase,
            "source_digest": source,
            "cursor": canonical(cursor.model_dump(mode="json")).decode("utf-8"),
            "rows_verified": count,
            "status": "complete",
            "updated_at": cursor.initialized_at,
        },
    )


def _finalize(
    connection: Connection,
    manifest: LedgerManifest,
    previous_fingerprint: str,
    work: LedgerWork,
) -> _LedgerContext:
    if _require_ledger_body(connection) is not work:
        raise MigrationRefused("transactional_connection_required")
    # These observations remain private across read-only fingerprinting and the
    # sole adoption fingerprint UPDATE. No cached domain is changed in between.
    shape = inspect_catalog(connection, LEDGER, work)
    counts = source_bounds(connection, work)
    financial = read_financial(connection, LEDGER, work)
    if source_digest(connection, work) != manifest.source_digest:
        raise MigrationRefused("source_digest_mismatch")
    if manifest.operation == "initialize":
        _write(
            connection,
            "adoption.publish_fingerprint",
            {
                "fingerprint": checksum(shape),
                "installation_key": manifest.installation_key,
                "previous_fingerprint": previous_fingerprint,
            },
        )
    # Observe the persisted fingerprint, never patch an earlier History value.
    history = read_history(connection, LEDGER, shape, work)
    validate_financial(financial, history, work)
    read_graph(connection, counts, history, financial, work)
    if history.opening is None:
        raise MigrationRefused("ledger_progress_invalid")
    head = validate_ledger_chain(history.manifests, history.opening, check=work.check)
    state = LedgerState(
        status="complete",
        installation_key=history.adoption["installation_key"],
        revision="ar_0007_ledger",
        head=head,
        manifest_count=len(history.manifests),
        account_count=len(financial["account"]),
        opening=history.opening,
    )
    if _require_ledger_body(connection) is not work:
        raise MigrationRefused("transactional_connection_required")
    work.check()
    return _LedgerContext(state, history, financial)


def initialize_ledger(
    engine: Engine, manifest: LedgerManifest, *, timeout_seconds: int = 5
) -> LedgerProvisioning:
    """Initialize or provision once; publish only after COMMIT ACK and cleanup."""
    manifest = _checked_manifest(manifest)
    work, outcome = LedgerWork(timeout_seconds), LedgerOutcome()
    with ledger_transaction(engine, outcome, work=work) as connection:
        context = _inspect_ledger_context(connection)
        _legacy_inventory(connection, context)
        receipt = _classify_manifest(context, manifest, work)
        if receipt is None:
            _writer_owner(connection)
            _projects(connection, manifest, context.history.ownership.organization_id, work)
            prepared = _prepare_ledger(context, manifest, work)
            if source_digest(connection, work) != manifest.source_digest:
                raise MigrationRefused("source_digest_mismatch")
            # All remaining transition values are bounded reductions. Do not keep
            # the original financial cohort while materializing the final one.
            del context
            if manifest.operation == "initialize":
                _upgrade(connection, manifest)
                for job in prepared.jobs:
                    work.check()
                    _write(
                        connection,
                        "jobs.backfill",
                        {"id": job.job_id, "opening": job.legacy_reserved_microusd},
                    )
            for account in manifest.accounts:
                work.check()
                opening = prepared.exposure.get(account.id, 0)
                _write(
                    connection,
                    "accounts.insert",
                    {
                        **account.model_dump(mode="json"),
                        "opening_held_microusd": opening,
                        "held_microusd": opening,
                        "accounted_microusd": 0,
                    },
                )
            observed, role, uid = _provenance(connection)
            cursor, opening_cursor = _ledger_cursors(
                connection, manifest, prepared, observed, role, uid, work
            )
            _insert_progress(connection, cursor, work)
            if opening_cursor is not None:
                _insert_progress(connection, opening_cursor, work)
            if manifest.operation == "initialize":
                create_ledger_constraints(connection)
            context = _finalize(connection, manifest, prepared.previous_fingerprint, work)
            receipt = _classify_manifest(context, manifest, work)
            if receipt is None or receipt != cursor.receipt:
                raise MigrationRefused("ledger_progress_invalid")
            if dialect(connection) == "postgresql":
                _execute(connection, "constraints.immediate").close()
                if _require_ledger_body(connection) is not work:
                    raise MigrationRefused("transactional_connection_required")
            work.check()
    return LedgerProvisioning(**receipt.model_dump(mode="json"), outcome="complete")


def _inspect_ledger_reentry(
    engine: Engine, manifest: LedgerManifest, *, timeout_seconds: int = 5
) -> LedgerManifestReceipt | None:
    """Explicit fresh inspection after uncertainty; absence never authorizes a retry."""
    manifest = _checked_manifest(manifest)
    work, outcome = LedgerWork(timeout_seconds), LedgerOutcome()
    with ledger_transaction(engine, outcome, work=work) as connection:
        context = _inspect_ledger_context(connection)
        _legacy_inventory(connection, context)
        receipt = _classify_manifest(context, manifest, work)
        work.check()
    return receipt
