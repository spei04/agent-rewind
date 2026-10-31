"""Explicit dormant failure-schema installation; no retry or runtime admission."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Literal

from pydantic import TypeAdapter, ValidationError, model_validator
from sqlalchemy.engine import Connection, Engine

from .failure_catalog import inspect_failure_catalog
from .failure_transaction import failure_transaction
from .inputs import validate_mapping
from .ledger_check import LedgerCheck
from .ledger_compatibility import _validate_native_projection
from .ledger_inputs import Digest, InstallationKey, LedgerValue
from .ledger_inspection import _inspect_ledger_context
from .ledger_reader_financial import read_financial, validate_financial
from .ledger_reader_graph import read_graph, source_bounds
from .ledger_reader_history import History, read_history
from .ledger_source import source_digest
from .ledger_state import LedgerState, validate_ledger_chain
from .ledger_transaction import LedgerOutcome, _require_ledger_body
from .ledger_work import LedgerWork
from .schema import FAILURE, LEDGER, MigrationRefused, checksum, dialect, installed_profile
from .service import _legacy_role_inventory

_KEY = TypeAdapter(InstallationKey)
_SCOPE_LOCK = RLock()
# Strong ownership is intentional only during this one synchronous upgrade;
# finally removes the exact entry, including on interruption.
_UPGRADES: dict[Connection, LedgerWork] = {}


class FailureState(LedgerValue):
    status: Literal["absent", "complete"]
    installation_key: InstallationKey
    revision: Literal["ar_0007_ledger", "ar_0008_failure_evidence"]
    catalog_profile: Literal["ledger_v1", "failure_evidence_v1"]
    installed_profile_sha256: Digest
    retained_ar7: LedgerState

    @model_validator(mode="after")
    def publication(self) -> FailureState:
        expected = (
            ("ar_0007_ledger", "ledger_v1")
            if self.status == "absent"
            else ("ar_0008_failure_evidence", "failure_evidence_v1")
        )
        if (
            (self.revision, self.catalog_profile) != expected
            or self.retained_ar7.status != "complete"
            or self.retained_ar7.revision != LEDGER
            or self.retained_ar7.installation_key != self.installation_key
        ):
            raise ValueError("inconsistent failure installation")
        return self


class FailureInitialization(FailureState):
    status: Literal["complete"]
    revision: Literal["ar_0008_failure_evidence"]
    catalog_profile: Literal["failure_evidence_v1"]
    outcome: Literal["complete"]


def _checked_key(value: str) -> str:
    try:
        return _KEY.validate_python(value, strict=True)
    except ValidationError:
        raise MigrationRefused("invalid_installation_key") from None


def _actual_revision(
    connection: Connection,
) -> Literal["ar_0007_ledger", "ar_0008_failure_evidence"]:
    query = (
        "SELECT CASE WHEN octet_length(version_num)<=32 THEN version_num END "
        "FROM alembic_version LIMIT 2"
        if dialect(connection) == "postgresql"
        else "SELECT CASE WHEN typeof(version_num)='text' "
        "AND length(CAST(version_num AS BLOB))<=32 THEN version_num END "
        "FROM alembic_version LIMIT 2"
    )
    with connection.exec_driver_sql(query) as result:
        rows = result.all()
    if len(rows) != 1 or type(rows[0][0]) is not str or rows[0][0] not in {LEDGER, FAILURE}:
        raise MigrationRefused("schema_incompatible")
    return "ar_0007_ledger" if rows[0][0] == LEDGER else "ar_0008_failure_evidence"


def _is_failure_candidate(connection: Connection, checks: LedgerCheck) -> bool:
    """Bounded candidate detection only; it does not prove any installed revision."""
    checks.check()
    query = (
        "SELECT tablename FROM pg_tables WHERE schemaname='public' "
        "AND tablename IN ('alembic_version','job_failure_evidence') ORDER BY tablename LIMIT 3"
        if dialect(connection) == "postgresql"
        else "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name IN ('alembic_version','job_failure_evidence') ORDER BY name LIMIT 3"
    )
    with connection.exec_driver_sql(query) as result:
        names = [row[0] for row in result]
    checks.check()
    if "job_failure_evidence" not in names:
        return False
    if names != ["alembic_version", "job_failure_evidence"]:
        raise MigrationRefused("schema_incompatible")
    return True


def _validate_failure_compatibility(connection: Connection, checks: LedgerCheck) -> None:
    """Immutable installation provenance only; no F4 rows, ready result or body rights."""
    # The candidate probe grants no shape or revision assumption. Validate the
    # whole native catalog before querying the proven version column.
    observed = inspect_failure_catalog(connection, checks)
    if _actual_revision(connection) != FAILURE:
        raise MigrationRefused("schema_incompatible")
    history = read_history(connection, LEDGER, observed.retained_ar7, checks)
    _validate_native_projection(connection, history, checks)
    checks.check()


def _require_failure_upgrade(connection: Connection) -> LedgerWork:
    work = _require_ledger_body(connection)
    with _SCOPE_LOCK:
        if _UPGRADES.get(connection) is not work:
            raise MigrationRefused("transactional_connection_required")
    work.check()
    return work


def _upgrade(connection: Connection, work: LedgerWork) -> None:
    from alembic import command
    from alembic.config import Config

    if _require_ledger_body(connection) is not work:
        raise MigrationRefused("transactional_connection_required")
    with _SCOPE_LOCK:
        if connection in _UPGRADES:
            raise MigrationRefused("transactional_connection_required")
        _UPGRADES[connection] = work
    try:
        config = Config()
        config.set_main_option("script_location", str(Path(__file__).parent))
        config.attributes.update(connection=connection, validated_operator=True)
        command.upgrade(config, FAILURE)
    finally:
        with _SCOPE_LOCK:
            if _UPGRADES.get(connection) is work:
                del _UPGRADES[connection]


def _history_digest(history: History) -> str:
    # PG history has already parsed this bounded wire timestamp. This digest
    # compares typed history; native raw-byte preservation is a separate oracle.
    adoption = dict(history.adoption)
    created = adoption["created_at"]
    if isinstance(created, datetime):
        adoption["created_at"] = created.isoformat(timespec="microseconds")
    return checksum(
        {
            "adoption": adoption,
            "ownership": history.ownership.cursor,
            "projection": history.projection.cursor,
            "manifests": [value.model_dump(mode="json") for value in history.manifests],
            "opening": None if history.opening is None else history.opening.model_dump(mode="json"),
        }
    )


def _inspect(
    connection: Connection, installation_key: str, work: LedgerWork
) -> tuple[FailureState, str]:
    if _require_ledger_body(connection) is not work:
        raise MigrationRefused("transactional_connection_required")
    revision = _actual_revision(connection)
    if revision == LEDGER:
        context = _inspect_ledger_context(connection)
        history, retained = context.history, context.state
        shape = installed_profile(dialect(connection), LEDGER)
    else:
        if (
            dialect(connection) == "sqlite"
            and connection.exec_driver_sql("SELECT 1 FROM sqlite_temp_master LIMIT 1").first()
        ):
            raise MigrationRefused("schema_incompatible")
        observed = inspect_failure_catalog(connection, work)
        shape = observed.catalog
        history = read_history(connection, LEDGER, observed.retained_ar7, work)
        counts = source_bounds(connection, work)
        financial = read_financial(connection, LEDGER, work)
        validate_financial(financial, history, work)
        read_graph(connection, counts, history, financial, work)
        if history.opening is None:
            raise MigrationRefused("ledger_progress_invalid")
        retained = LedgerState(
            status="complete",
            installation_key=history.adoption["installation_key"],
            revision="ar_0007_ledger",
            head=validate_ledger_chain(history.manifests, history.opening, check=work.check),
            manifest_count=len(history.manifests),
            account_count=len(financial["account"]),
            opening=history.opening,
        )
    if history.adoption["installation_key"] != installation_key:
        raise MigrationRefused("installation_key_mismatch")
    if history.adoption["source_kind"] == "legacy":
        _legacy_role_inventory(connection, validate_mapping(history.adoption["mapping"]))
    state = FailureState(
        status="absent" if revision == LEDGER else "complete",
        installation_key=installation_key,
        revision=revision,
        catalog_profile="ledger_v1" if revision == LEDGER else "failure_evidence_v1",
        installed_profile_sha256=checksum(shape),
        retained_ar7=retained,
    )
    digest = _history_digest(history)
    if _require_ledger_body(connection) is not work:
        raise MigrationRefused("transactional_connection_required")
    work.check()
    return state, digest


def initialize_failure_evidence(
    engine: Engine, *, installation_key: str, timeout_seconds: int = 5
) -> FailureInitialization:
    """Install once explicitly; never publish through uncertain ACK or cleanup."""
    key = _checked_key(installation_key)
    work, outcome = LedgerWork(timeout_seconds), LedgerOutcome()
    with failure_transaction(engine, outcome, work=work) as connection:
        before, original_history = _inspect(connection, key, work)
        if before.status == "absent":
            original_source = source_digest(connection, work)
            _upgrade(connection, work)
            state, final_history = _inspect(connection, key, work)
            if (
                state.status != "complete"
                or state.retained_ar7 != before.retained_ar7
                or final_history != original_history
                or source_digest(connection, work) != original_source
            ):
                raise MigrationRefused("schema_incompatible")
            # F2 creates a dormant empty relation, never marker or failure rows.
            if connection.exec_driver_sql("SELECT 1 FROM job_failure_evidence LIMIT 1").first():
                raise MigrationRefused("schema_incompatible")
        else:
            state = before
        if _require_ledger_body(connection) is not work:
            raise MigrationRefused("transactional_connection_required")
        work.check()
    return FailureInitialization(**state.model_dump(mode="json"), outcome="complete")


def inspect_failure_evidence(
    engine: Engine, *, installation_key: str, timeout_seconds: int = 5
) -> FailureState:
    """Fresh full inspection after uncertainty; absence grants no write or retry authority."""
    key = _checked_key(installation_key)
    work, outcome = LedgerWork(timeout_seconds), LedgerOutcome()
    with failure_transaction(engine, outcome, work=work) as connection:
        state, _ = _inspect(connection, key, work)
    return state
