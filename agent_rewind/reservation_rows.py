"""Bounded P2 snapshots, affected monetary proof and after-image headroom.

The inherited projection establishes the global transport/type envelope. Monetary
reconciliation is limited to the complete affected closure and target job.
"""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from sqlalchemy import column, select, table
from sqlalchemy.engine import Connection

from .admission_records import OPERATION_LIMITS, AdmissionStorageError, operation_value
from .artifact_metadata import ArtifactError, _object
from .migrations.failure_catalog import inspect_failure_catalog
from .migrations.failure_service import _actual_revision
from .migrations.ledger_compatibility import _validate_native_projection, validated_ar7_history
from .migrations.ledger_reader_financial import (
    CAP,
    FinancialProjection,
    _validate_calls,
    financial_size,
    read_financial_projection,
)
from .migrations.ledger_reader_graph import read_source_bounds
from .migrations.ledger_reader_history import History, read_history
from .migrations.schema import FAILURE, LEDGER, MigrationRefused, canonical
from .operation_reads import (
    DESCRIPTOR_FIELDS,
    JOB_LIMITS,
    RawReceipt,
    validate_association,
    validate_job_row,
)
from .operation_work import OperationWork
from .reservation_checks import SourceStats, money_total, require_source_headroom, utc_microseconds
from .reservation_types import ReservationRefusal, ReservationScope


def source_headroom(
    connection: Connection, work: OperationWork, *, prospective: bool
) -> dict[str, SourceStats]:
    receipts = read_source_bounds(connection, work)
    result = {
        key: SourceStats(value.rows, value.native_bytes, value.max_native_bytes)
        for key, value in receipts.items()
    }
    require_source_headroom(result, prospective_job_growth=prospective)
    return result


def _unique(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    result = {row[key]: row for row in rows}
    if len(result) != len(rows):
        raise ReservationRefusal("ledger_state_invalid")
    return result


@dataclass
class ReservationRows:
    scope: ReservationScope
    work: OperationWork
    history: History
    projection: FinancialProjection
    source: dict[str, SourceStats]

    @classmethod
    def capture(
        cls, connection: Connection, scope: ReservationScope, work: OperationWork
    ) -> ReservationRows:
        try:
            history = validated_ar7_history(connection, work)
        except MigrationRefused:
            raise ReservationRefusal("schema_or_provenance_invalid") from None
        if history.ownership.organization_id != scope.context.organization_id:
            raise ReservationRefusal("schema_or_provenance_invalid")
        observed = read_financial_projection(connection, LEDGER, work)
        source = source_headroom(connection, work, prospective=False)
        value = cls(scope, work, history, observed, source)
        value.require_job()
        return value

    @classmethod
    def _capture_failure(
        cls, connection: Connection, scope: ReservationScope, work: OperationWork
    ) -> ReservationRows:
        # This fixed private producer entry never broadens the public ar7 guard.
        # The complete successor must pass before its retained ar7 view is used.
        observed = inspect_failure_catalog(connection, work)
        if _actual_revision(connection) != FAILURE:
            raise MigrationRefused("schema_incompatible")
        history = read_history(connection, LEDGER, observed.retained_ar7, work)
        _validate_native_projection(connection, history, work)
        if history.ownership.organization_id != scope.context.organization_id:
            raise ReservationRefusal("schema_or_provenance_invalid")
        projection = read_financial_projection(connection, LEDGER, work)
        source = source_headroom(connection, work, prospective=False)
        value = cls(scope, work, history, projection, source)
        value.require_job()
        return value

    @property
    def data(self) -> dict[str, list[dict[str, Any]]]:
        return self.projection.rows

    @property
    def job(self) -> dict[str, Any]:
        found = [row for row in self.data["job"] if row["id"] == self.scope.job_id]
        if len(found) != 1:
            raise ReservationRefusal("ledger_state_invalid")
        return found[0]

    def require_job(self) -> None:
        scope, data, job = self.scope, self.data, self.job
        if data["organization"] != [
            {
                "id": scope.context.organization_id,
                "installation_key": self.history.adoption["installation_key"],
            }
        ]:
            raise ReservationRefusal("schema_or_provenance_invalid")
        if job["kind"] != "run" or job["payload_version"] != 2:
            raise ReservationRefusal("unsupported_job")
        if [
            row
            for row in data["scope"]
            if row["resource_kind"] == "job" and row["resource_id"] == scope.job_id
        ] != [
            {
                "resource_kind": "job",
                "resource_id": scope.job_id,
                "project_id": scope.context.project_id,
            }
        ]:
            raise ReservationRefusal("ledger_state_invalid")
        operations = [row for row in data["operation"] if row["job_id"] == scope.job_id]
        references = [
            row
            for row in data["ref"]
            if row["owner_kind"] == "job"
            and row["owner_id"] == scope.job_id
            and row["role"] == "admission_config"
        ]
        if len(operations) != 1 or len(references) != 1:
            raise ReservationRefusal("unsupported_job")
        op, ref = operations[0], references[0]
        objects = [row for row in data["object"] if row["id"] == ref["artifact_id"]]
        if (
            len(objects) != 1
            or ref["project_id"] != scope.context.project_id
            or op["project_id"] != scope.context.project_id
        ):
            raise ReservationRefusal("unsupported_job")
        config = {**objects[0], "reference_id": ref["artifact_id"]}
        try:
            operation_value(op)
            validate_association(
                RawReceipt(
                    "operation",
                    op["id"],
                    tuple(OPERATION_LIMITS),
                    tuple(op[name] for name in OPERATION_LIMITS),
                ),
                validate_job_row({name: job[name] for name in JOB_LIMITS}, scope.job_id),
                RawReceipt(
                    "admission_config",
                    scope.job_id,
                    (*DESCRIPTOR_FIELDS, "reference_id"),
                    tuple(config[name] for name in (*DESCRIPTOR_FIELDS, "reference_id")),
                ),
            )
        except (AdmissionStorageError, ArtifactError, ValueError, TypeError, KeyError):
            raise ReservationRefusal("unsupported_job") from None

    def affected(self) -> dict[str, dict[str, Any]]:
        context, job_id = self.scope.context, self.scope.job_id
        return {
            row["id"]: row
            for row in self.data["account"]
            if row["organization_id"] == context.organization_id
            and (
                row["scope"] == "organization"
                or row["scope"] == "project"
                and row["project_id"] == context.project_id
                or row["scope"] == "job"
                and row["job_id"] == job_id
            )
        }

    def lock_accounts(self, connection: Connection) -> None:
        # One complete sorted observation, not one query per account. The
        # strongest organization exclusion was acquired before this lock.
        accounts = table(
            "budget_accounts",
            column("id"),
            column("organization_id"),
            column("scope"),
            column("project_id"),
            column("job_id"),
        )
        statement = (
            select(accounts.c.id)
            .where(
                accounts.c.organization_id == self.scope.context.organization_id,
                (accounts.c.scope == "organization")
                | (
                    (accounts.c.scope == "project")
                    & (accounts.c.project_id == self.scope.context.project_id)
                )
                | ((accounts.c.scope == "job") & (accounts.c.job_id == self.scope.job_id)),
            )
            .order_by(accounts.c.id)
            .limit(4097)
            .with_for_update()
        )
        rows: Sequence[Any] = connection.execute(statement).scalars().all()
        if len(rows) > 4096:
            raise ReservationRefusal("capacity_exceeded")
        if rows != sorted(self.affected()):
            raise ReservationRefusal("ledger_state_invalid")

    def reconcile(self, now: int) -> None:
        data, work, context = self.data, self.work, self.scope.context
        accounts = _unique(data["account"], "id")
        affected = self.affected()
        entry_calls = {row["call_id"] for row in data["entry"] if row["account_id"] in affected}
        calls = {
            row["id"]: row
            for row in data["call"]
            if row["job_id"] == self.scope.job_id
            or row["id"] in entry_calls
            or any(
                row[name + "_account_id"] in affected for name in ("organization", "project", "job")
            )
        }
        if not entry_calls <= set(calls):
            raise ReservationRefusal("ledger_state_invalid")
        if len(calls) > 4096:
            raise ReservationRefusal("capacity_exceeded")
        jobs = _unique(data["job"], "id")
        opening = self.history.opening
        if opening is None:
            raise ReservationRefusal("schema_or_provenance_invalid")
        original_jobs = {row.job_id: row for row in opening.jobs}
        relevant_jobs = {self.scope.job_id, *(row["job_id"] for row in calls.values())}
        for job_id in relevant_jobs:
            work.check()
            job = jobs.get(job_id)
            original = original_jobs.get(job_id)
            expected = 0 if original is None else original.legacy_reserved_microusd
            if job is None or job["legacy_reserved_microusd"] != expected:
                raise ReservationRefusal("ledger_state_invalid")
        for account in accounts.values():
            work.check()
            if (
                account["scope"] == "job"
                and account["job_id"] in relevant_jobs
                and account["limit_microusd"] > jobs[account["job_id"]]["budget"]
            ):
                raise ReservationRefusal("ledger_state_invalid")
        entries = [row for row in data["entry"] if row["call_id"] in calls]
        if len(entries) > 9 * len(calls):
            raise ReservationRefusal("capacity_exceeded")
        # Every relevant call includes its three counterpart account/entry
        # identities and evidence references, even outside the monetary closure.
        scopes = {
            (row["resource_kind"], row["resource_id"]): row["project_id"] for row in data["scope"]
        }
        ref_keys = {
            (row["project_id"], row["owner_kind"], row["owner_id"], row["artifact_id"], row["role"])
            for row in data["ref"]
        }
        objects = _unique(data["object"], "id")
        relevant_refs = [
            row
            for row in data["ref"]
            if row["owner_kind"] == "provider_call"
            and row["owner_id"] in calls
            and row["role"] == "budget_evidence"
        ]
        ref_identities = set()
        for ref in relevant_refs:
            work.check()
            key = (ref["project_id"], ref["owner_id"], ref["artifact_id"], ref["role"])
            descriptor = objects.get(ref["artifact_id"])
            if (
                key in ref_identities
                or descriptor is None
                or ref["project_id"] != calls[ref["owner_id"]]["project_id"]
                or descriptor["project_id"] != ref["project_id"]
            ):
                raise ReservationRefusal("ledger_state_invalid")
            ref_identities.add(key)
            try:
                _object(descriptor)
            except (ArtifactError, ValueError, TypeError, KeyError):
                raise ReservationRefusal("ledger_state_invalid") from None
        _validate_calls(
            calls,
            accounts,
            _unique(data["job"], "id"),
            scopes,
            _unique(data["project"], "id"),
            entries,
            ref_keys,
            context.organization_id,
            work,
        )
        for family in ("organization", "project", "job"):
            rows = sorted(
                (row for row in affected.values() if row["scope"] == family),
                key=lambda row: row["period_start"],
            )
            if family == "job" and len(rows) != 1:
                raise ReservationRefusal("ledger_state_invalid")
            previous_end: int | None = None
            for account in rows:
                work.check()
                start, end = (
                    utc_microseconds(account["period_start"]),
                    utc_microseconds(account["period_end"]),
                )
                if start >= end or previous_end is not None and start < previous_end:
                    raise ReservationRefusal("ledger_state_invalid")
                previous_end = end
                if start > now and any(
                    account[key]
                    for key in ("held_microusd", "accounted_microusd", "opening_held_microusd")
                ):
                    raise ReservationRefusal("ledger_state_invalid")
                relevant = [row for row in entries if row["account_id"] == account["id"]]
                per_call: dict[str, dict[str, int]] = {}
                for entry in relevant:
                    per_call.setdefault(entry["call_id"], {})[entry["entry_kind"]] = entry[
                        "amount_microusd"
                    ]
                remaining = []
                settled = []
                for amounts in per_call.values():
                    work.check()
                    # Cohort validation already proves reductions <= reserve.
                    # Lifetime account gross is not a stored signed64 field.
                    settled.append(amounts.get("settle", 0))
                    remaining.append(
                        amounts["reserve"] - amounts.get("settle", 0) - amounts.get("release", 0)
                    )
                held = money_total([account["opening_held_microusd"], *remaining])
                accounted = money_total(settled)
                if account["held_microusd"] != held or account["accounted_microusd"] != accounted:
                    raise ReservationRefusal("ledger_state_invalid")
        gross = money_total(
            [
                self.job["legacy_reserved_microusd"],
                *[
                    row["reserved_microusd"]
                    for row in calls.values()
                    if row["job_id"] == self.scope.job_id
                ],
            ]
        )
        if gross != self.job["reserved"]:
            raise ReservationRefusal("ledger_state_invalid")

    def after_image(self) -> dict[str, list[dict[str, Any]]]:
        self.work.check()
        result = deepcopy(self.data)
        self.work.check()
        return result

    def require_headroom(self, after: dict[str, list[dict[str, Any]]]) -> None:
        require_source_headroom(self.source, prospective_job_growth=True)
        financial_size(after, LEDGER, self.work)
        # A conservative native bound for changed/new rows. Retaining all old
        # bytes avoids subtracting a guessed backend rendering. Numeric native
        # representations are bounded by the inherited 64-byte scalar gates.
        additional = 0
        for domain, rows in after.items():
            original = {canonical(row) for row in self.data[domain]}
            for row in rows:
                self.work.check()
                if canonical(row) not in original:
                    additional += sum(
                        0
                        if value is None
                        else len(value.encode("utf-8"))
                        if type(value) is str
                        else 64
                        for value in row.values()
                    )
        if self.projection.native_bytes + additional > CAP:
            raise ReservationRefusal("capacity_exceeded")

    def confirm(self, connection: Connection, after: dict[str, list[dict[str, Any]]]) -> None:
        actual = read_financial_projection(connection, LEDGER, self.work)
        for domain in after:
            self.work.check()
            if sorted(map(canonical, actual.rows[domain])) != sorted(map(canonical, after[domain])):
                raise ReservationRefusal("ledger_state_invalid")
        source_headroom(connection, self.work, prospective=False)
