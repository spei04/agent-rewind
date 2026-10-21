"""Sequential cancellation receipt phases; no effect, authority or connection owner.

A phase encloses the caller's SQL scope, including commit/cleanup. Verification
seals its snapshot before the intentional effect. Outcome/ACK classification and
fresh disclosure authority remain the service's responsibility.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy.engine import Connection

from .admission_records import hexadecimal
from .operation_reads import (
    MAX_IDENTITIES,
    MAX_RECEIPT_BYTES,
    CancellationAssociation,
    Domain,
    RawReceipt,
    ReceiptBook,
    invalid,
    receipt_bytes,
)
from .operation_sources import RunCohort, _verify_cancellation_snapshot
from .operation_work import OperationWork
from .scoped_repositories import ProjectContext

# Actual canonical object syntax, excluding its two values. Both retained job
# representations are charged even when some immutable Python objects are shared.
_WRAPPER_BYTES = len(receipt_bytes({"original": None, "phase": None}, MAX_RECEIPT_BYTES)) - 8


def _association_rows(value: CancellationAssociation) -> list[list[Any]]:
    return [
        [r.domain, r.identity, list(r.fields), list(r.values)]
        for r in (value.operation, value.job, value.configuration)
    ]


def _same(left: RawReceipt, right: RawReceipt) -> bool:
    return left == right and tuple(map(type, left.values)) == tuple(map(type, right.values))


class CancellationReceipts:
    """One original association and one live generation; budgets never reset."""

    def __init__(
        self, work: OperationWork, original_context: ProjectContext, operation_id: str
    ) -> None:
        hexadecimal(operation_id, 32)
        hexadecimal(original_context.project_id, 32)
        self.work = work
        self.context = original_context
        self.operation_id = operation_id
        self.source_visits = 0
        self.edges = 0
        self._original: CancellationAssociation | None = None
        self._original_bytes = 4  # canonical null before the initial reservation
        self._active: CancellationPhase | None = None
        self._generation = 0
        self._failed = False

    @property
    def original(self) -> CancellationAssociation:
        if self._failed or self._original is None:
            raise invalid()
        return self._original

    @contextmanager
    def phase(self) -> Iterator[CancellationPhase]:
        # Refused nested acquisition owns nothing and cannot poison the outer
        # phase, even if the caller catches this fixed error inside that phase.
        if self._active is not None or self._failed or self.work._started is not None:
            raise invalid()
        self.work.check()
        self._generation += 1
        phase = CancellationPhase(self, self._generation)
        self._active = phase
        try:
            yield phase
            if not phase._sealed or self.work._started is not None:
                raise invalid()
        except BaseException:
            self._failed = True
            raise
        finally:
            # Pure release cannot replace the caller's denial/interruption, or
            # touch a subsequent generation. No work counter is refunded.
            phase._closed = True
            phase._book._receipts.clear()
            phase._book.observations.clear()
            phase._association = None
            if self._active is phase:
                self._active = None


class CancellationPhase:
    """Generation guard/accounting hook for the existing bounded readers."""

    def __init__(self, owner: CancellationReceipts, generation: int) -> None:
        self._owner = owner
        self._generation = generation
        self._closed = False
        self._sealed = False
        self._association: CancellationAssociation | None = None
        self._association_bytes = owner._original_bytes
        self._book = ReceiptBook(_scope=self)

    @property
    def source_visits(self) -> int:
        return self._owner.source_visits

    @property
    def edges(self) -> int:
        return self._owner.edges

    @property
    def book(self) -> ReceiptBook:
        self.check()
        return self._book

    def check(
        self,
        context: ProjectContext | None = None,
        domain: Domain | None = None,
        identity: str | None = None,
    ) -> None:
        owner = self._owner
        if (
            self._closed
            or self._sealed
            or owner._failed
            or owner._active is not self
            or owner._generation != self._generation
        ):
            raise invalid()
        if context is not None and context != owner.context:
            raise invalid()
        if domain == "result" or (domain == "operation" and identity != owner.operation_id):
            raise invalid()
        if domain in ("job", "admission_config"):
            operation = self._book._receipts.get(("operation", owner.operation_id))
            if operation is None or operation.row()["job_id"] != identity:
                raise invalid()
        owner.work.check()

    def connection(self, connection: Connection) -> None:
        self.check()
        if self._owner.work._connection is not connection:
            raise invalid()

    def charge(self, count: int, edges: int) -> None:
        self.check()
        owner = self._owner
        if owner.source_visits + count > 256 or owner.edges + edges > 512:
            raise invalid()
        owner.source_visits += count
        owner.edges += edges

    def remaining(self, book: ReceiptBook) -> int:
        self.check()
        if book is not self._book:
            raise invalid()
        return MAX_RECEIPT_BYTES - _WRAPPER_BYTES - self._association_bytes - book._wire_bytes

    def reserve(self, book: ReceiptBook, size: int, key: tuple[Domain, str] | None) -> None:
        if size < 0 or size > self.remaining(book):
            raise invalid()
        keys = set(book._receipts)
        association = self._association or self._owner._original
        if association is not None:
            keys.update(
                (r.domain, r.identity)
                for r in (association.operation, association.job, association.configuration)
            )
        if key is not None:
            keys.add(key)
        if len(keys) > MAX_IDENTITIES:
            raise invalid()

    def before_cohort(self) -> None:
        self.check()
        if self._association is None:
            raise invalid()

    def associate(self, operation: RawReceipt, job: RawReceipt, configuration: RawReceipt) -> None:
        self.check()
        try:
            if self._association is not None:
                raise invalid()
            if operation.identity != self._owner.operation_id:
                raise invalid()
            if operation.row()["project_id"] != self._owner.context.project_id:
                raise invalid()
            for value in (operation, job, configuration):
                retained = self._book._receipts.get((value.domain, value.identity))
                if retained is None or not _same(value, retained):
                    raise invalid()
            original = self._owner._original
            if original is None:
                original = CancellationAssociation.capture(operation, job, configuration)
                size = len(receipt_bytes(_association_rows(original), MAX_RECEIPT_BYTES))
            else:
                original.require_matches(operation, job, configuration)
                size = self._owner._original_bytes
            if _WRAPPER_BYTES + size + self._book._wire_bytes > MAX_RECEIPT_BYTES:
                raise invalid()
            self._association = original
            self._association_bytes = size
        except BaseException:
            self._owner._failed = True
            raise

    def verify(self, connection: Connection, cohort: RunCohort) -> None:
        self.check()
        try:
            self.connection(connection)
            self.before_cohort()
            retained = tuple(r for r in self._book.receipts if r.domain == "run")
            if len(retained) != len(cohort.records) or any(
                not _same(a, b) for a, b in zip(retained, cohort.records, strict=True)
            ):
                raise invalid()
            self.reserve(self._book, 0, None)
            _verify_cancellation_snapshot(connection, self._owner.context, self._book, cohort)
            if self._owner._original is None:
                self._owner._original = self._association
                self._owner._original_bytes = self._association_bytes
            self._sealed = True
        except BaseException:
            self._owner._failed = True
            raise
