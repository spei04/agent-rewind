"""Immutable ledger provenance values; pure validation never acknowledges a commit."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import Field, ValidationError, field_validator, model_validator
from sqlalchemy.engine import Connection

from .ledger_inputs import (
    MAX_MONEY,
    Digest,
    Identifier,
    InstallationKey,
    LedgerManifest,
    LedgerValue,
    Money,
    Time,
    decode_ledger_json,
    immutable_array,
    validate_json_value,
    validate_time,
)
from .schema import MigrationRefused, canonical, checksum, dialect

LEDGER_REVISION = "ar_0007_ledger"
MAX_CURSOR_BYTES = 65536
MAX_MANIFESTS = 256
MAX_PROGRESS_BYTES = 16 * 1024 * 1024


class LedgerManifestReceipt(LedgerValue):
    installation_key: InstallationKey
    revision: Literal["ar_0007_ledger"]
    manifest_id: Identifier
    manifest_digest: Digest
    sequence: Annotated[int, Field(ge=0, le=255)]
    operation: Literal["initialize", "provision"]
    source_digest: Digest
    account_rows: Annotated[int, Field(ge=0, le=64)]
    imported_jobs: Annotated[int, Field(ge=0, le=48)]
    imported_opening_microusd: Money
    initialized_at: Time

    _time = field_validator("initialized_at")(validate_time)


class LedgerProvisioning(LedgerManifestReceipt):
    outcome: Literal["complete"]


class ManifestCursor(LedgerValue):
    schema_version: Annotated[int, Field(ge=1, le=1)]
    manifest: LedgerManifest
    manifest_digest: Digest
    sequence: Annotated[int, Field(ge=0, le=255)]
    parent_manifest_digest: Digest | None
    database_role: Annotated[str, Field(min_length=1)] | None
    os_uid: Money
    initialized_at: Time
    account_projection_digest: Digest
    account_count: Annotated[int, Field(ge=0, le=64)]
    imported_jobs: Annotated[int, Field(ge=0, le=48)]
    imported_opening_microusd: Money

    _time = field_validator("initialized_at")(validate_time)

    @model_validator(mode="after")
    def bindings(self) -> ManifestCursor:
        manifest = self.manifest
        if (
            self.manifest_digest != manifest.digest
            or self.parent_manifest_digest != manifest.parent_manifest_digest
            or self.account_count != len(manifest.accounts)
            or (self.sequence == 0) != (manifest.operation == "initialize")
        ):
            raise ValueError("manifest cursor binding")
        if manifest.operation == "provision":
            if self.imported_jobs or self.imported_opening_microusd:
                raise ValueError("provision opening")
        elif self.imported_jobs != sum(account.scope == "job" for account in manifest.accounts):
            raise ValueError("opening coverage")
        if self.database_role is not None and len(self.database_role.encode("utf-8")) > 63:
            raise ValueError("role bound")
        return self

    @property
    def receipt(self) -> LedgerManifestReceipt:
        return LedgerManifestReceipt(
            installation_key=self.manifest.installation_key,
            revision="ar_0007_ledger",
            manifest_id=self.manifest.manifest_id,
            manifest_digest=self.manifest_digest,
            sequence=self.sequence,
            operation=self.manifest.operation,
            source_digest=self.manifest.source_digest,
            account_rows=self.account_count,
            imported_jobs=self.imported_jobs,
            imported_opening_microusd=self.imported_opening_microusd,
            initialized_at=self.initialized_at,
        )


class OpeningJob(LedgerValue):
    job_id: Identifier
    project_id: Identifier
    budget_microusd: Money
    legacy_reserved_microusd: Money

    @model_validator(mode="after")
    def bounded_exposure(self) -> OpeningJob:
        if self.legacy_reserved_microusd > self.budget_microusd:
            raise ValueError("gross exposure")
        return self


class ProjectOpening(LedgerValue):
    project_id: Identifier
    account_id: Identifier
    opening_held_microusd: Money


class OpeningCursor(LedgerValue):
    schema_version: Annotated[int, Field(ge=1, le=1)]
    manifest_id: Identifier
    manifest_digest: Digest
    source_digest: Digest
    initialized_at: Time
    jobs: Annotated[tuple[OpeningJob, ...], Field(max_length=48)]
    jobs_digest: Digest
    project_totals: Annotated[tuple[ProjectOpening, ...], Field(max_length=16)]
    organization_account_id: Identifier | None
    organization_opening_microusd: Money
    job_count: Annotated[int, Field(ge=0, le=48)]

    _jobs = field_validator("jobs", mode="before")(immutable_array)
    _projects = field_validator("project_totals", mode="before")(immutable_array)
    _time = field_validator("initialized_at")(validate_time)

    @model_validator(mode="after")
    def totals(self) -> OpeningCursor:
        ids = [job.job_id for job in self.jobs]
        projects = [project.project_id for project in self.project_totals]
        if (
            ids != sorted(set(ids))
            or projects != sorted(set(projects))
            or self.job_count != len(ids)
        ):
            raise ValueError("opening order/count")
        if self.jobs_digest != checksum([job.model_dump(mode="json") for job in self.jobs]):
            raise ValueError("opening jobs digest")
        totals: dict[str, int] = {}
        for job in self.jobs:
            totals[job.project_id] = totals.get(job.project_id, 0) + job.legacy_reserved_microusd
        if totals != {
            project.project_id: project.opening_held_microusd for project in self.project_totals
        }:
            raise ValueError("opening project totals")
        total = sum(totals.values())
        if total > MAX_MONEY or total != self.organization_opening_microusd:
            raise ValueError("opening organization total")
        if self.organization_account_id is None and (self.jobs or self.project_totals or total):
            raise ValueError("null opening organization")
        return self


class LedgerState(LedgerValue):
    status: Literal["absent", "complete"]
    installation_key: InstallationKey
    revision: Literal["ar_0006_admission", "ar_0007_ledger"]
    head: LedgerManifestReceipt | None
    manifest_count: Annotated[int, Field(ge=0, le=256)]
    account_count: Annotated[int, Field(ge=0, le=4096)]
    opening: OpeningCursor | None

    @model_validator(mode="after")
    def publication(self) -> LedgerState:
        if self.status == "absent":
            if (
                self.revision != "ar_0006_admission"
                or self.head is not None
                or self.opening is not None
                or self.manifest_count
                or self.account_count
            ):
                raise ValueError("partial absence")
        elif (
            self.revision != LEDGER_REVISION
            or self.head is None
            or self.opening is None
            or self.manifest_count == 0
            or self.head.sequence + 1 != self.manifest_count
            or self.head.installation_key != self.installation_key
        ):
            raise ValueError("incomplete publication")
        return self


def validate_manifest_cursor(connection: Connection, value: object) -> ManifestCursor:
    try:
        validate_json_value(value)
        if len(canonical(value)) > MAX_CURSOR_BYTES:
            raise ValueError("cursor size")
        cursor = ManifestCursor.model_validate(value)
        if (cursor.database_role is None) != (dialect(connection) == "sqlite"):
            raise ValueError("role dialect")
        return cursor
    except (ValueError, TypeError, RecursionError, ValidationError):
        raise MigrationRefused("ledger_progress_invalid") from None


def validate_opening_cursor(value: object) -> OpeningCursor:
    try:
        validate_json_value(value)
        if len(canonical(value)) > MAX_CURSOR_BYTES:
            raise ValueError("cursor size")
        return OpeningCursor.model_validate(value)
    except (ValueError, TypeError, RecursionError, ValidationError):
        raise MigrationRefused("ledger_progress_invalid") from None


def _observed_time(connection: Connection, value: object) -> str:
    if dialect(connection) == "sqlite":
        if type(value) is not str:
            raise ValueError("native timestamp")
        return validate_time(value)
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("native timestamp")
    utc = value.astimezone(UTC)
    return (
        f"{utc.year:04d}-{utc.month:02d}-{utc.day:02d}T"
        f"{utc.hour:02d}:{utc.minute:02d}:{utc.second:02d}.{utc.microsecond:06d}Z"
    )


def validate_progress_row(
    connection: Connection, row: Mapping[str, object]
) -> ManifestCursor | OpeningCursor:
    """Validate one already SQL-bounded raw row, without reading or changing SQL."""
    try:
        if set(row) != {
            "revision",
            "phase",
            "source_digest",
            "cursor",
            "rows_verified",
            "status",
            "updated_at",
        }:
            raise ValueError("progress columns")
        if (
            row["revision"] != LEDGER_REVISION
            or row["status"] != "complete"
            or type(row["rows_verified"]) is not int
        ):
            raise ValueError("progress state")
        raw = row["cursor"]
        if type(raw) is not str:
            raise ValueError("native cursor")
        value = decode_ledger_json(raw.encode("utf-8"), maximum=MAX_CURSOR_BYTES)
        phase = row["phase"]
        if phase == "ledger_opening":
            opening = validate_opening_cursor(value)
            if (
                row["source_digest"] != opening.source_digest
                or row["rows_verified"] != opening.job_count
                or _observed_time(connection, row["updated_at"]) != opening.initialized_at
            ):
                raise ValueError("opening row binding")
            return opening
        cursor = validate_manifest_cursor(connection, value)
        if (
            phase != "ledger_manifest_" + cursor.manifest.manifest_id
            or row["source_digest"] != cursor.manifest.source_digest
            or row["rows_verified"] != cursor.account_count
            or _observed_time(connection, row["updated_at"]) != cursor.initialized_at
        ):
            raise ValueError("manifest row binding")
        return cursor
    except (ValueError, TypeError, RecursionError):
        raise MigrationRefused("ledger_progress_invalid") from None


def validate_ledger_chain(
    manifests: tuple[ManifestCursor, ...], opening: OpeningCursor
) -> LedgerManifestReceipt:
    """Validate immutable receipts only; SQL rows and native byte gates are separate."""
    try:
        if not 1 <= len(manifests) <= MAX_MANIFESTS:
            raise ValueError("manifest count")
        if (
            sum(len(canonical(cursor.model_dump(mode="json"))) for cursor in (*manifests, opening))
            > MAX_PROGRESS_BYTES
        ):
            raise ValueError("progress size")
        first = manifests[0]
        if (
            opening.manifest_id != first.manifest.manifest_id
            or opening.manifest_digest != first.manifest_digest
            or opening.source_digest != first.manifest.source_digest
            or opening.initialized_at != first.initialized_at
            or opening.job_count != first.imported_jobs
            or opening.organization_opening_microusd != first.imported_opening_microusd
        ):
            raise ValueError("opening manifest binding")
        assignment = first.manifest.opening_accounts
        if (
            assignment is None
            or assignment.organization_account_id != opening.organization_account_id
            or [(row.project_id, row.account_id) for row in assignment.projects]
            != [(row.project_id, row.account_id) for row in opening.project_totals]
        ):
            raise ValueError("opening destination")
        jobs = {job.job_id: job for job in opening.jobs}
        initial_jobs = {
            account.job_id: account for account in first.manifest.accounts if account.scope == "job"
        }
        if set(jobs) != set(initial_jobs):
            raise ValueError("opening job coverage")
        for job_id, job in jobs.items():
            account = initial_jobs[job_id]
            if account.project_id != job.project_id or account.limit_microusd > job.budget_microusd:
                raise ValueError("opening job binding")
        account_ids: set[str] = set()
        job_ids: set[str] = set()
        organizations: set[str] = set()
        periods: dict[tuple[str, str], list[tuple[str, str]]] = {}
        seen_ids: set[str] = set()
        seen_digests: set[str] = set()
        previous: str | None = None
        for sequence, cursor in enumerate(manifests):
            manifest = cursor.manifest
            if (
                cursor.sequence != sequence
                or cursor.parent_manifest_digest != previous
                or manifest.installation_key != first.manifest.installation_key
                or manifest.manifest_id in seen_ids
                or cursor.manifest_digest in seen_digests
            ):
                raise ValueError("manifest chain")
            seen_ids.add(manifest.manifest_id)
            seen_digests.add(cursor.manifest_digest)
            previous = cursor.manifest_digest
            opening_values: dict[str, int] = {}
            if sequence == 0:
                if opening.organization_account_id is not None:
                    opening_values[opening.organization_account_id] = (
                        opening.organization_opening_microusd
                    )
                opening_values.update(
                    (row.account_id, row.opening_held_microusd) for row in opening.project_totals
                )
                for job_id, job in jobs.items():
                    opening_values[initial_jobs[job_id].id] = job.legacy_reserved_microusd
                for account in manifest.accounts:
                    if (
                        account.id
                        in {
                            opening.organization_account_id,
                            *(row.account_id for row in opening.project_totals),
                        }
                        and not account.period_start <= opening.initialized_at < account.period_end
                    ):
                        raise ValueError("opening period")
            projection = []
            for account in manifest.accounts:
                if account.id in account_ids or (
                    account.job_id is not None and account.job_id in job_ids
                ):
                    raise ValueError("repeated provisioned account")
                account_ids.add(account.id)
                if len(account_ids) > 4096:
                    raise MigrationRefused("ledger_limit_exceeded")
                organizations.add(account.organization_id)
                if len(organizations) > 1:
                    raise ValueError("multiple installation organizations")
                if account.job_id is not None:
                    job_ids.add(account.job_id)
                key = (account.scope, account.scope_id)
                cohort = periods.setdefault(key, [])
                if any(
                    start < account.period_end and account.period_start < end
                    for start, end in cohort
                ):
                    raise ValueError("overlapping provisioned period")
                cohort.append((account.period_start, account.period_end))
                exposure = opening_values.get(account.id, 0)
                if exposure > account.limit_microusd:
                    raise ValueError("opening cap")
                projection.append(
                    {**account.model_dump(mode="json"), "opening_held_microusd": exposure}
                )
            if checksum(projection) != cursor.account_projection_digest:
                raise ValueError("account projection")
        return manifests[-1].receipt
    except (ValueError, TypeError, RecursionError, KeyError):
        raise MigrationRefused("ledger_progress_invalid") from None
