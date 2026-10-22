"""Pure new-intent and immutable cursor construction for ledger provisioning."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.engine import Connection

from .ledger_inputs import MAX_MONEY, LedgerManifest
from .ledger_inspection import _LedgerContext
from .ledger_state import (
    MAX_CURSOR_BYTES,
    MAX_MANIFESTS,
    MAX_PROGRESS_BYTES,
    LedgerManifestReceipt,
    ManifestCursor,
    OpeningCursor,
    OpeningJob,
    ProjectOpening,
    validate_ledger_chain,
    validate_manifest_cursor,
    validate_opening_cursor,
)
from .ledger_work import LedgerWork
from .schema import ADMISSION, MigrationRefused, canonical, checksum


@dataclass(frozen=True)
class _PreparedLedger:
    manifests: tuple[ManifestCursor, ...]
    opening: OpeningCursor | None
    jobs: tuple[OpeningJob, ...]
    project_totals: tuple[ProjectOpening, ...]
    exposure: dict[str, int]
    organization_opening: int
    terminal_leases: tuple[int | float, ...]
    previous_fingerprint: str


def _classify_manifest(
    context: _LedgerContext, manifest: LedgerManifest, work: LedgerWork
) -> LedgerManifestReceipt | None:
    """Classify only a fully proved context; None is established intent absence."""
    work.check()
    if manifest.installation_key != context.state.installation_key:
        raise MigrationRefused("ledger_manifest_conflict")
    for cursor in context.history.manifests:
        work.check()
        if cursor.manifest.manifest_id == manifest.manifest_id:
            if cursor.manifest.canonical_bytes != manifest.canonical_bytes:
                raise MigrationRefused("ledger_manifest_conflict")
            work.check()
            return cursor.receipt
    if context.state.revision == ADMISSION:
        if manifest.operation != "initialize":
            raise MigrationRefused("ledger_history_unsupported")
        return None
    head = context.state.head
    if (
        manifest.operation == "initialize"
        or head is None
        or manifest.parent_manifest_digest != head.manifest_digest
    ):
        raise MigrationRefused("ledger_manifest_conflict")
    requested_ids = {row.id for row in manifest.accounts}
    requested_starts = {
        (row.organization_id, row.scope, row.scope_id, row.period_start)
        for row in manifest.accounts
    }
    for row in context.financial["account"]:
        work.check()
        if (
            row["id"] in requested_ids
            or (row["organization_id"], row["scope"], row["scope_id"], row["period_start"])
            in requested_starts
        ):
            raise MigrationRefused("ledger_manifest_conflict")
    return None


def _sum_money(values: list[int], work: LedgerWork) -> int:
    total = 0
    for value in values:
        work.check()
        if type(value) is not int or not 0 <= value <= MAX_MONEY - total:
            raise MigrationRefused("ledger_exposure_refused")
        total += value
    return total


def _prepare_ledger(
    context: _LedgerContext, manifest: LedgerManifest, work: LedgerWork
) -> _PreparedLedger:
    """Reduce the complete current cohort to the bounded new transition values."""
    if (
        context.state.manifest_count >= MAX_MANIFESTS
        or context.state.account_count + len(manifest.accounts) > 4096
    ):
        raise MigrationRefused("ledger_limit_exceeded")
    organization = context.history.ownership.organization_id
    jobs = {row["id"]: row for row in context.financial["job"]}
    scopes = {
        row["resource_id"]: row["project_id"]
        for row in context.financial["scope"]
        if row["resource_kind"] == "job"
    }
    current = context.financial["account"]
    for account in manifest.accounts:
        work.check()
        if account.organization_id != organization:
            raise MigrationRefused("ledger_history_unsupported")
        if account.scope == "job":
            job = jobs.get(account.job_id)
            if job is None or scopes.get(account.job_id) != account.project_id:
                raise MigrationRefused("ledger_history_unsupported")
            if account.limit_microusd > job["budget"]:
                raise MigrationRefused("ledger_exposure_refused")
        older_held = []
        for row in current:
            work.check()
            if account.job_id is not None and row["job_id"] == account.job_id:
                raise MigrationRefused("ledger_manifest_conflict")
            if (row["scope"], row["scope_id"]) != (account.scope, account.scope_id):
                continue
            if (
                row["period_start"] < account.period_end
                and account.period_start < row["period_end"]
            ):
                raise MigrationRefused("ledger_manifest_conflict")
            if row["period_start"] < account.period_start:
                older_held.append(row["held_microusd"])
            elif row["held_microusd"]:
                raise MigrationRefused("ledger_exposure_refused")
        if _sum_money(older_held, work) > account.limit_microusd:
            raise MigrationRefused("ledger_exposure_refused")

    imported: list[OpeningJob] = []
    projects: list[ProjectOpening] = []
    exposure: dict[str, int] = {}
    organization_opening = 0
    terminal_leases: list[int | float] = []
    if manifest.operation == "initialize":
        if len(jobs) > 48:
            raise MigrationRefused("ledger_limit_exceeded")
        assignments = {row.job_id: row for row in manifest.accounts if row.scope == "job"}
        if set(assignments) != set(jobs):
            raise MigrationRefused("ledger_history_unsupported")
        for identity, job in sorted(jobs.items()):
            work.check()
            if job["status"] not in {"succeeded", "failed", "cancelled", "queued"} or (
                job["status"] == "queued"
                and (
                    job["payload_version"] != 2
                    or job["reserved"] != 0
                    or job["owner"] is not None
                    or job["lease_until"] is not None
                )
            ):
                raise MigrationRefused("ledger_history_unsupported")
            if job["status"] != "queued":
                deadline = job["lease_until"]
                if deadline is None:
                    if job["owner"] is not None:
                        raise MigrationRefused("ledger_history_unsupported")
                elif type(deadline) not in (int, float) or not math.isfinite(deadline):
                    raise MigrationRefused("ledger_history_unsupported")
                else:
                    terminal_leases.append(deadline)
            amount = job["reserved"]
            if (
                type(amount) is not int
                or not 0 <= amount <= job["budget"]
                or amount > assignments[identity].limit_microusd
            ):
                raise MigrationRefused("ledger_exposure_refused")
            imported.append(
                OpeningJob(
                    job_id=identity,
                    project_id=scopes[identity],
                    budget_microusd=job["budget"],
                    legacy_reserved_microusd=amount,
                )
            )
            exposure[assignments[identity].id] = amount
        assignment = manifest.opening_accounts
        if assignment is None:
            raise MigrationRefused("invalid_ledger_manifest")
        by_id = {row.id: row for row in manifest.accounts}
        for destination in assignment.projects:
            work.check()
            total = _sum_money(
                [
                    row.legacy_reserved_microusd
                    for row in imported
                    if row.project_id == destination.project_id
                ],
                work,
            )
            if total > by_id[destination.account_id].limit_microusd:
                raise MigrationRefused("ledger_exposure_refused")
            projects.append(
                ProjectOpening(
                    project_id=destination.project_id,
                    account_id=destination.account_id,
                    opening_held_microusd=total,
                )
            )
            exposure[destination.account_id] = total
        organization_opening = _sum_money([row.legacy_reserved_microusd for row in imported], work)
        if assignment.organization_account_id is not None:
            if organization_opening > by_id[assignment.organization_account_id].limit_microusd:
                raise MigrationRefused("ledger_exposure_refused")
            exposure[assignment.organization_account_id] = organization_opening
    work.check()
    return _PreparedLedger(
        context.history.manifests,
        context.history.opening,
        tuple(imported),
        tuple(projects),
        exposure,
        organization_opening,
        tuple(terminal_leases),
        context.history.adoption["installed_schema_fingerprint"],
    )


def _ledger_cursors(
    connection: Connection,
    manifest: LedgerManifest,
    prepared: _PreparedLedger,
    initialized_at: str,
    database_role: str | None,
    os_uid: int,
    work: LedgerWork,
) -> tuple[ManifestCursor, OpeningCursor | None]:
    """Serialize only after observing real provenance; bound before progress INSERT."""
    work.check()
    if manifest.operation == "provision":
        for account in manifest.accounts:
            work.check()
            if account.scope == "job" and account.period_end <= initialized_at:
                raise MigrationRefused("invalid_ledger_manifest")
    opening = None
    if manifest.operation == "initialize":
        # Legacy finish retains owner/deadline markers. The one real database
        # observation resolves their expiry without changing original fields.
        observed_epoch = datetime.fromisoformat(initialized_at[:-1] + "+00:00").timestamp()
        for deadline in prepared.terminal_leases:
            work.check()
            if deadline > observed_epoch:
                raise MigrationRefused("ledger_history_unsupported")
        assignment = manifest.opening_accounts
        if assignment is None:
            raise MigrationRefused("invalid_ledger_manifest")
        selected = {
            assignment.organization_account_id,
            *(row.account_id for row in assignment.projects),
        }
        for account in manifest.accounts:
            work.check()
            if account.id in selected and not (
                account.period_start <= initialized_at < account.period_end
            ):
                raise MigrationRefused("invalid_ledger_manifest")
        jobs = [row.model_dump(mode="json") for row in prepared.jobs]
        value = {
            "schema_version": 1,
            "manifest_id": manifest.manifest_id,
            "manifest_digest": manifest.digest,
            "source_digest": manifest.source_digest,
            "initialized_at": initialized_at,
            "jobs": jobs,
            "jobs_digest": checksum(jobs),
            "project_totals": [row.model_dump(mode="json") for row in prepared.project_totals],
            "organization_account_id": assignment.organization_account_id,
            "organization_opening_microusd": prepared.organization_opening,
            "job_count": len(jobs),
        }
        if len(canonical(value)) > MAX_CURSOR_BYTES:
            raise MigrationRefused("ledger_limit_exceeded")
        opening = validate_opening_cursor(value)
    projection = []
    for account in manifest.accounts:
        work.check()
        projection.append(
            {
                **account.model_dump(mode="json"),
                "opening_held_microusd": prepared.exposure.get(account.id, 0),
            }
        )
    value = {
        "schema_version": 1,
        "manifest": manifest.model_dump(mode="json"),
        "manifest_digest": manifest.digest,
        "sequence": len(prepared.manifests),
        "parent_manifest_digest": manifest.parent_manifest_digest,
        "database_role": database_role,
        "os_uid": os_uid,
        "initialized_at": initialized_at,
        "account_projection_digest": checksum(projection),
        "account_count": len(manifest.accounts),
        "imported_jobs": len(prepared.jobs),
        "imported_opening_microusd": prepared.organization_opening,
    }
    if len(canonical(value)) > MAX_CURSOR_BYTES:
        raise MigrationRefused("ledger_limit_exceeded")
    cursor = validate_manifest_cursor(connection, value)
    chain_opening = opening if opening is not None else prepared.opening
    if chain_opening is None:
        raise MigrationRefused("ledger_progress_invalid")
    chain = (*prepared.manifests, cursor)
    size = 0
    for item in (*chain, chain_opening):
        work.check()
        size += len(canonical(item.model_dump(mode="json")))
        if size > MAX_PROGRESS_BYTES:
            raise MigrationRefused("ledger_limit_exceeded")
    validate_ledger_chain(chain, chain_opening, check=work.check)
    work.check()
    return cursor, opening
