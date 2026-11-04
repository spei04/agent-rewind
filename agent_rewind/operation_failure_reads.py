"""Successor-only operation receipts and bounded failure observations.

The old ar7 receipt wire remains separate. An evidence extension is charged
inside its existing job identity; these values never confer action authority.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .admission_records import OPERATION_LIMITS, hexadecimal, operation_value
from .errors import RULES
from .failure_encoding import association_digest, source_digest
from .failure_evidence import FailureRecord, FailureRefusal
from .operation_reads import (
    DESCRIPTOR_FIELDS,
    JOB_LIMITS,
    MAX_IDENTITIES,
    MAX_RECEIPT_BYTES,
    Domain,
    RawReceipt,
    ReceiptBook,
    Scalar,
    _ReceiptScope,
    invalid,
    receipt_bytes,
    validate_association,
    validate_job_row,
)
from .scoped_lineage import ResourceNotFound
from .scoped_repositories import ProjectContext

EVIDENCE_FIELDS = (
    "schema_version",
    "kind",
    "project_id",
    "job_resource_kind",
    "job_id",
    "operation_id",
    "lease_generation",
    "job_status",
    "cause",
    "phase",
    "origin_kind",
    "correlation_id",
    "association_sha256",
    "source_sha256",
    "created_at_micros",
)
EVIDENCE_LIMITS = (1, 17, 32, 3, 32, 32, 19, 9, 18, 15, 16, 32, 64, 64, 18)
_FIELDS: dict[Domain, tuple[str, ...]] = {
    "operation": tuple(OPERATION_LIMITS),
    "job": tuple(JOB_LIMITS),
    "admission_config": (*DESCRIPTOR_FIELDS, "reference_id"),
    "result": (*DESCRIPTOR_FIELDS, "reference_id"),
    "run": ("id", "kind", "created", "body"),
}
MAX_FRAME_BYTES = 4096


def _scalar(value: object) -> bool:
    return type(value) in (str, int, bool, type(None)) or (
        type(value) is float and math.isfinite(value)
    )


def _same_values(left: tuple[Scalar, ...], right: tuple[Scalar, ...]) -> bool:
    return left == right and tuple(map(type, left)) == tuple(map(type, right))


@dataclass(frozen=True)
class JobObservation:
    generation: int
    evidence_count: int
    any_provider_call: bool
    evidence: tuple[Scalar, ...] | None

    def __post_init__(self) -> None:
        if (
            type(self.generation) is not int
            or not 0 <= self.generation < 2**63
            or type(self.evidence_count) is not int
            or self.evidence_count not in (0, 1)
            or type(self.any_provider_call) is not bool
            or (self.evidence_count == 0) != (self.evidence is None)
        ):
            raise invalid()
        if self.evidence is not None and (
            type(self.evidence) is not tuple
            or len(self.evidence) != len(EVIDENCE_FIELDS)
            or any(not _scalar(value) for value in self.evidence)
        ):
            raise invalid()

    def wire(self) -> list[Any]:
        return [
            self.generation,
            self.evidence_count,
            self.any_provider_call,
            None if self.evidence is None else list(self.evidence),
        ]

    def same(self, other: JobObservation) -> bool:
        if type(other) is not JobObservation or self != other:
            return False
        return self.evidence is None or (
            other.evidence is not None and _same_values(self.evidence, other.evidence)
        )


class SuccessorReceiptBook(ReceiptBook):
    """One measured wire, one job extension per existing job, no extra identity."""

    def __init__(
        self,
        *,
        check: Callable[[], None] | None = None,
        _scope: _ReceiptScope | None = None,
    ) -> None:
        super().__init__(_scope=_scope)
        self._check = check
        self._wire_bytes = 35
        self.byte_count = 35
        # Values are encoded in their existing job row, never as extra receipts
        # or an uncharged observation book.
        self._jobs: dict[str, JobObservation] = {}
        self._active_frame = 0

    def _check_live(
        self,
        context: ProjectContext | None = None,
        domain: Domain | None = None,
        identity: str | None = None,
    ) -> None:
        super()._check_live(context, domain, identity)
        if self._check is not None:
            self._check()

    @property
    def active_frame_bytes(self) -> int:
        self._check_live()
        return self._active_frame

    @property
    def remaining(self) -> int:
        self._check_live()
        available = (
            MAX_RECEIPT_BYTES - self._wire_bytes
            if self._scope is None
            else self._scope.remaining(self)
        )
        return available - self._active_frame

    @contextmanager
    def frame(self, measured_size: int) -> Iterator[None]:
        """Reserve a measured finite frame before its encoded buffer is made."""
        self._check_live()
        if (
            type(measured_size) is not int
            or not 1 <= measured_size <= MAX_FRAME_BYTES
            or self._active_frame
            or measured_size > self.remaining
        ):
            raise invalid()
        self._active_frame = measured_size
        try:
            yield
            self._check_live()
        finally:
            self._active_frame = 0

    def _before_cohort(self) -> None:
        self._check_live()
        if self._active_frame:
            raise invalid()
        super()._before_cohort()

    def _reserve(self, size: int, key: tuple[Domain, str] | None) -> None:
        self._check_live()
        if size < 0 or size > self.remaining:
            raise invalid()
        if key is not None and key not in self._receipts and len(self._receipts) >= MAX_IDENTITIES:
            raise invalid()
        if self._scope is not None:
            self._scope.reserve(self, size, key)

    def _remember(
        self, receipt: RawReceipt, observation: JobObservation | None
    ) -> RawReceipt:
        self._check_live(domain=receipt.domain, identity=receipt.identity)
        hexadecimal(receipt.identity, 32)
        if (
            receipt.fields != _FIELDS.get(receipt.domain)
            or len(receipt.values) != len(receipt.fields)
            or any(not _scalar(value) for value in receipt.values)
            or (receipt.domain == "job") != (observation is not None)
        ):
            raise invalid()
        key = receipt.domain, receipt.identity
        previous = self._receipts.get(key)
        if previous is not None:
            if previous != receipt or not _same_values(previous.values, receipt.values):
                raise invalid()
            if observation is not None and not self._jobs[receipt.identity].same(observation):
                raise invalid()
            return previous
        wire: list[Any] = [receipt.domain, receipt.identity, list(receipt.values)]
        if observation is not None:
            wire.append(observation.wire())
        encoded = receipt_bytes(wire, self.remaining - bool(self._receipts))
        size = len(encoded) + bool(self._receipts)
        self._reserve(size, key)
        self._receipts[key] = receipt
        if observation is not None:
            self._jobs[receipt.identity] = observation
        self._wire_bytes += size
        self.byte_count += size
        return receipt

    def remember(
        self, domain: Domain, identity: str, fields: tuple[str, ...], row: Mapping[str, Any]
    ) -> RawReceipt:
        if (
            domain == "job"
            or fields != _FIELDS.get(domain)
            or any(name not in row for name in fields)
        ):
            raise invalid()
        return self._remember(
            RawReceipt(domain, identity, fields, tuple(row[k] for k in fields)), None
        )

    def remember_job(self, receipt: RawReceipt, observation: JobObservation) -> RawReceipt:
        if type(receipt) is not RawReceipt or type(observation) is not JobObservation:
            raise invalid()
        observation.__post_init__()
        if receipt.domain != "job" or receipt.fields != tuple(JOB_LIMITS):
            raise invalid()
        validate_job_row(receipt.row(), receipt.identity)
        return self._remember(receipt, observation)

    def job_observation(self, job_id: str) -> JobObservation:
        self._check_live(domain="job", identity=job_id)
        if ("job", job_id) not in self._receipts or job_id not in self._jobs:
            raise invalid()
        return self._jobs[job_id]

    def observe(self, kind: str, identity: str, values: tuple[Scalar, ...]) -> None:
        self._check_live()
        hexadecimal(identity, 32)
        if type(values) is not tuple or any(not _scalar(value) for value in values):
            raise invalid()
        if kind == "result_count":
            if len(values) != 1 or type(values[0]) is not int or values[0] not in (0, 1):
                raise invalid()
        elif kind == "cohort":
            if len(values) > 255 or len(set(values)) != len(values):
                raise invalid()
            for value in values:
                self._check_live()
                hexadecimal(value, 32)
        else:
            raise invalid()
        key = kind, identity
        previous = self.observations.get(key)
        if previous is not None:
            if not _same_values(previous, values):
                raise invalid()
            return
        encoded = receipt_bytes(
            [kind, identity, list(values)], self.remaining - bool(self.observations)
        )
        size = len(encoded) + bool(self.observations)
        self._reserve(size, None)
        self.observations[key] = values
        self._wire_bytes += size
        self.byte_count += size

    def _payload(self) -> dict[str, Any]:
        rows = []
        for receipt in self._receipts.values():
            self._check_live()
            row: list[Any] = [receipt.domain, receipt.identity, list(receipt.values)]
            if receipt.domain == "job":
                row.append(self.job_observation(receipt.identity).wire())
            rows.append(row)
        observations = []
        for (kind, identity), values in self.observations.items():
            self._check_live()
            observations.append([kind, identity, list(values)])
        return {"v": 1, "rows": rows, "observations": observations}

    def encoded(self) -> bytes:
        self._check_live()
        if self._active_frame or self._wire_bytes != self.byte_count:
            raise invalid()
        encoded = receipt_bytes(self._payload(), MAX_RECEIPT_BYTES)
        self._check_live()
        if len(encoded) != self._wire_bytes:
            raise invalid()
        return encoded

    def clear(self) -> None:
        """Release one closed phase's buffers, without refunding work or visits."""
        self._receipts.clear()
        self._jobs.clear()
        self.observations.clear()
        self._active_frame = 0


def _job_query(name: str, *, _cancellation: bool = False) -> str:
    if name not in ("sqlite", "postgresql"):
        raise invalid()
    prefix = "public." if name == "postgresql" else "main."

    def size(value: str) -> str:
        return (
            f"octet_length(CAST({value} AS text))"
            if name == "postgresql"
            else f"length(CAST({value} AS BLOB))"
        )

    job_columns = ",".join("j." + field for field in JOB_LIMITS)
    evidence_columns = ",".join("f." + field for field in EVIDENCE_FIELDS)
    job_size = "+".join("coalesce(" + size("j." + field) + ",0)" for field in JOB_LIMITS)
    evidence_size = "+".join(
        "coalesce(" + size("f." + field) + ",0)" for field in EVIDENCE_FIELDS
    )
    job_guards = [
        f"(j.{field} IS NULL OR {size('j.' + field)}<={limit})"
        for field, limit in JOB_LIMITS.items()
    ]
    evidence_guards = [
        f"(f.{field} IS NULL OR {size('f.' + field)}<={limit})"
        for field, limit in zip(EVIDENCE_FIELDS, EVIDENCE_LIMITS, strict=True)
    ]
    if name == "sqlite":
        for field in (*JOB_LIMITS, "lease_generation"):
            kinds = (
                "('integer','real')"
                if field in ("created", "lease_until")
                else "('integer')"
                if field in ("budget", "reserved", "payload_version", "cancel", "lease_generation")
                else "('text')"
            )
            job_guards.append(f"(j.{field} IS NULL OR typeof(j.{field}) IN {kinds})")
        for field in EVIDENCE_FIELDS:
            kind = (
                "integer"
                if field in ("schema_version", "lease_generation", "created_at_micros")
                else "text"
            )
            evidence_guards.append(f"(f.{field} IS NULL OR typeof(f.{field})='{kind}')")
    job_safe = " AND ".join(job_guards)
    eligibility = "" if _cancellation else "AND j.error IS NULL"
    evidence_safe = " AND ".join(evidence_guards)
    projected = [
        f"CASE WHEN checked.safe=1 THEN j.{field} END AS j_{field}"
        for field in JOB_LIMITS
    ] + [
        f"CASE WHEN checked.safe=1 THEN f.{field} END AS f_{field}"
        for field in EVIDENCE_FIELDS
    ]
    # Only fixed source identifiers, native predicates and finite limits enter
    # this SQL. The three request values remain named parameters.
    return f"""
    WITH j AS MATERIALIZED (
      SELECT {job_columns},j.lease_generation
      FROM {prefix}jobs j JOIN {prefix}resource_scopes s
        ON s.project_id=:project AND s.resource_kind='job' AND s.resource_id=j.id
      WHERE j.id=:job LIMIT 2
    ), f AS MATERIALIZED (
      SELECT {evidence_columns} FROM {prefix}job_failure_evidence f
      WHERE f.job_id=:job LIMIT 2
    ), evidence_stats AS MATERIALIZED (
      SELECT count(*) AS count,
        coalesce(sum({evidence_size}),0) AS bytes,
        coalesce(min(CASE WHEN {evidence_safe} THEN 1 ELSE 0 END),1) AS valid
      FROM f
    ), checked AS MATERIALIZED (
      SELECT j.id,
        CASE WHEN {job_safe}
          AND (SELECT count(*) FROM j)=1
          AND j.kind='run' AND j.payload_version=2 {eligibility}
          AND j.lease_generation BETWEEN 0 AND 9223372036854775807
          AND e.count<=1 AND e.valid=1
          AND {job_size}+coalesce({size('j.lease_generation')},0)+e.bytes<=4096
          AND {job_size}+coalesce({size('j.lease_generation')},0)+e.bytes<=:remaining
        THEN 1 ELSE 0 END AS safe
      FROM j CROSS JOIN evidence_stats e
    )
    SELECT {','.join(projected)},
      CASE WHEN checked.safe=1 THEN j.lease_generation END AS generation,
      e.count AS evidence_count,
      EXISTS(SELECT 1 FROM {prefix}provider_calls c WHERE c.job_id=j.id) AS any_provider_call,
      checked.safe
    FROM j JOIN checked ON checked.id=j.id
    CROSS JOIN evidence_stats e LEFT JOIN f ON true
    """  # noqa: S608 -- All interpolations are fixed source fragments above.


def _read_successor_job(
    connection: Connection,
    context: ProjectContext,
    job_id: str,
    book: SuccessorReceiptBook,
    *,
    _cancellation: bool,
) -> RawReceipt:
    """One candidate-first native target; no filtered evidence absence."""
    with book._attempt(connection, context, "job", job_id):
        hexadecimal(job_id, 32)
        book.charge_sources(1)
        with connection.execute(
            text(_job_query(connection.dialect.name, _cancellation=_cancellation)),
            {"project": context.project_id, "job": job_id, "remaining": book.remaining},
        ) as result:
            rows = result.mappings().all()
        book._check_live()
        if not rows:
            raise ResourceNotFound()
        if len(rows) != 1 or type(rows[0]["safe"]) is not int or rows[0]["safe"] != 1:
            raise invalid()
        row = rows[0]
        call = row["any_provider_call"]
        if connection.dialect.name == "sqlite":
            if type(call) is not int or call not in (0, 1):
                raise invalid()
            call = bool(call)
        elif type(call) is not bool:
            raise invalid()
        count = row["evidence_count"]
        evidence = (
            None
            if type(count) is int and count == 0
            else tuple(row["f_" + field] for field in EVIDENCE_FIELDS)
        )
        observation = JobObservation(row["generation"], count, call, evidence)
        job = validate_job_row({field: row["j_" + field] for field in JOB_LIMITS}, job_id)
        return book.remember_job(job, observation)


def read_successor_job(
    connection: Connection,
    context: ProjectContext,
    job_id: str,
    book: SuccessorReceiptBook,
) -> RawReceipt:
    """GET refuses unsupported legacy errors before transferring their cells."""
    return _read_successor_job(connection, context, job_id, book, _cancellation=False)


def read_successor_cancel_job(
    connection: Connection,
    context: ProjectContext,
    job_id: str,
    book: SuccessorReceiptBook,
) -> RawReceipt:
    """Cancellation retains bounded worker progress, including legacy errors."""
    return _read_successor_job(connection, context, job_id, book, _cancellation=True)


def observe_failure_result_absence(
    connection: Connection,
    context: ProjectContext,
    job_id: str,
    book: SuccessorReceiptBook,
) -> None:
    """Retain job-only native result absence before accepting verified failure."""
    with book._attempt(connection, context, "job", job_id):
        hexadecimal(job_id, 32)
        with connection.execute(
            text(
                "SELECT 1 FROM artifact_refs "
                "WHERE owner_kind='job' AND owner_id=:job AND role='result' LIMIT 2"
            ),
            {"job": job_id},
        ) as result:
            rows = result.all()
        book._check_live()
        if rows:
            raise invalid()
        book.observe("result_count", job_id, (0,))


class FailureError(TypedDict):
    code: Literal["outcome_uncertain"]
    message: str
    request_id: str
    retryable: Literal[False]


def _marker(
    values: tuple[Scalar, ...],
    operation: RawReceipt,
    job: RawReceipt,
    observation: JobObservation,
) -> None:
    row: dict[str, Any] = dict(zip(EVIDENCE_FIELDS, values, strict=True))
    original = operation_value(operation.row())
    state = job.row()
    if (
        type(row["schema_version"]) is not int
        or row["schema_version"] != 1
        or row["kind"] != "historical_marker"
        or row["project_id"] != original.project_id
        or row["job_resource_kind"] != "job"
        or row["job_id"] != job.identity
        or row["operation_id"] != original.id
        or type(row["lease_generation"]) is not int
        or row["lease_generation"] != observation.generation
        or row["job_status"] != state["status"]
        or row["cause"] is not None
        or row["phase"] is not None
        or row["origin_kind"] != "migration_marker"
        or original.failure_correlation_id is not None
        or type(row["created_at_micros"]) is not int
        or not 0 <= row["created_at_micros"] <= 253402300799999999
    ):
        raise invalid()
    hexadecimal(row["correlation_id"], 32)
    hexadecimal(row["association_sha256"], 64)
    hexadecimal(row["source_sha256"], 64)
    # GET admits only the existing v2 operation association. A v1/null-operation
    # marker cannot manufacture that association, and W is never recomputed.


def _retained_inputs(
    context: ProjectContext,
    operation: RawReceipt,
    job: RawReceipt,
    configuration: RawReceipt,
    book: SuccessorReceiptBook,
) -> JobObservation:
    book._check_live(context, "job", job.identity)
    validate_association(operation, job, configuration)
    for receipt in (operation, job, configuration):
        previous = book._receipts.get((receipt.domain, receipt.identity))
        if (
            previous is None
            or previous != receipt
            or not _same_values(previous.values, receipt.values)
        ):
            raise invalid()
    if operation_value(operation.row()).project_id != context.project_id:
        raise invalid()
    return book.job_observation(job.identity)


def _verified_error(
    dialect: str,
    context: ProjectContext,
    operation: RawReceipt,
    job: RawReceipt,
    configuration: RawReceipt,
    book: SuccessorReceiptBook,
    observation: JobObservation,
) -> FailureError:
    cells = observation.evidence
    result_count = book.observations.get(("result_count", job.identity))
    if (
        cells is None
        or result_count != (0,)
        or type(result_count[0]) is not int
        or ("result", job.identity) in book._receipts
    ):
        raise invalid()
    original, state = operation_value(operation.row()), job.row()
    try:
        native: dict[str, Any] = dict(zip(EVIDENCE_FIELDS, cells, strict=True))
        record = FailureRecord(**native)
        if (
            record.project_id != context.project_id
            or record.job_id != job.identity
            or record.operation_id != original.id
            or record.lease_generation != observation.generation
            or record.job_status != state["status"]
            or record.correlation_id != original.failure_correlation_id
        ):
            raise invalid()
        association, _ = association_digest(
            dialect,
            context.organization_id,
            context.project_id,
            operation,
            job,
            configuration,
            remaining=book.remaining,
            _reserve=book.frame,
        )
        if association != record.association_sha256:
            raise invalid()
        source, _ = source_digest(
            dialect,
            association,
            job,
            observation.generation,
            observation.any_provider_call,
            record,
            remaining=book.remaining,
            _reserve=book.frame,
        )
        if source != record.source_sha256:
            raise invalid()
    except (FailureRefusal, TypeError, ValueError):
        raise invalid() from None
    book._check_live()
    return {
        "code": "outcome_uncertain",
        "message": RULES["outcome_uncertain"][1],
        "request_id": record.correlation_id,
        "retryable": False,
    }


def successor_error(
    dialect: str,
    context: ProjectContext,
    operation: RawReceipt,
    job: RawReceipt,
    configuration: RawReceipt,
    book: SuccessorReceiptBook,
) -> FailureError | None:
    """Validate retained GET provenance; the caller owns fresh disclosure."""
    observation = _retained_inputs(context, operation, job, configuration, book)
    state = job.row()
    if state["error"] is not None:
        raise invalid()
    cells = observation.evidence
    if cells is None:
        if state["status"] == "failed":
            raise invalid()
        return None
    if cells[1] == "historical_marker":
        _marker(cells, operation, job, observation)
        if state["status"] == "failed":
            raise invalid()
        return None
    return _verified_error(dialect, context, operation, job, configuration, book, observation)


def validate_cancellation_evidence(
    dialect: str,
    context: ProjectContext,
    operation: RawReceipt,
    job: RawReceipt,
    configuration: RawReceipt,
    book: SuccessorReceiptBook,
) -> None:
    """Keep cancellation progress semantics; no Error or failure is invented."""
    observation = _retained_inputs(context, operation, job, configuration, book)
    cells = observation.evidence
    if cells is None:
        return
    if cells[1] == "historical_marker":
        _marker(cells, operation, job, observation)
        return
    _verified_error(dialect, context, operation, job, configuration, book, observation)
