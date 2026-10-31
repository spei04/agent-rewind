"""Owned F3 failure completion; no worker activation or public issuer."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from threading import Lock, RLock
from typing import Any, Literal
from weakref import WeakKeyDictionary

from sqlalchemy import Text, and_, cast, column, func, literal, select, table, update
from sqlalchemy.engine import Connection, Engine

from . import reservation
from .admission_transaction import TransactionOutcome, admission_transaction
from .failure_catalog import _refresh_producer_authority
from .failure_encoding import association_digest, source_digest
from .failure_evidence import (
    CompletionEvent,
    CreatedFailure,
    FailureRecord,
    FailureRefusal,
    IssuedTerminalScope,
    OriginalFailureIntent,
    TentativeCreated,
)
from .failure_persistence import (
    _absence,
    _association,
    _consume_dependency_event,
    _DependencyRecord,
    _same_association,
)
from .migrations.schema import MigrationRefused
from .operation_reads import (
    JOB_LIMITS,
    MAX_IDENTITIES,
    MAX_RECEIPT_BYTES,
    Domain,
    RawReceipt,
    ReceiptBook,
    receipt_bytes,
)
from .operation_work import OperationWork
from .request_authority import RequestAuthority
from .request_identity import VerifiedPrincipal
from .reservation_checks import lease_live
from .reservation_connection import (
    ReservationBody,
    issued_connection,
    require_body,
    require_engine,
)
from .reservation_connection import (
    _live as _body_live,
)
from .reservation_rows import ReservationRows
from .reservation_types import JobFence, ReservationRefusal, ReservationScope, TransactionFacts
from .scoped_locks import lock_authority
from .scoped_repositories import ProjectContext, _byte_length

_FIELDS = tuple(FailureRecord.__dataclass_fields__)
_LIMITS = (1, 17, 32, 3, 32, 32, 19, 9, 18, 15, 16, 32, 64, 64, 18)
_EVIDENCE = table("job_failure_evidence", *(column(name) for name in _FIELDS))
_LOCK = RLock()


@dataclass
class _TerminalState:
    coordinator: TerminalCoordinator
    body: ReservationBody
    event: _DependencyRecord
    used: bool = False
    original: OriginalFailureIntent | None = None
    initial_job: RawReceipt | None = None
    after: dict[str, list[dict[str, Any]]] | None = None
    rows: ReservationRows | None = None
    retained_bytes: int = 0
    detached_bytes: int = 0
    active_frame_bytes: int = 0
    frame_active: bool = False
    source_visits: int = 0
    edges: int = 0
    failed: bool = False
    books: list[ReceiptBook] = field(default_factory=list)
    identities: set[tuple[Domain, str]] = field(default_factory=set)
    association_frame_bytes: int = 0
    source_frame_bytes: int = 0

    def check(
        self,
        context: ProjectContext | None = None,
        domain: Domain | None = None,
        identity: str | None = None,
    ) -> None:
        with _LOCK:
            issued = _TERMINALS.get(self.body.connection)
            if (
                issued is None
                or issued[1] is not self
                or self.failed
                or not self.used
                or self.frame_active
                or self.coordinator._work is not self.body.work
                or context is not None
                and context is not self.body.scope.context
            ):
                raise FailureRefusal("invalid_native_state")
        if domain is not None:
            expected = (
                self.event.source.operation.identity
                if domain == "operation"
                else self.body.scope.job_id
            )
            if (
                domain not in ("operation", "job", "admission_config", "result")
                or identity != expected
            ):
                raise FailureRefusal("invalid_native_state")
        # Pure issued-body validation: this accounting check must not add a
        # native xid query after the final clock or reset the invocation Work.
        _body_live(self.body)

    def connection(self, connection: Connection) -> None:
        self.check()
        if connection is not self.body.connection:
            raise FailureRefusal("invalid_native_state")

    def fail(self) -> None:
        self.failed = True

    def charge(self, count: int, edges: int) -> None:
        self.check()
        if (
            type(count) is not int
            or type(edges) is not int
            or count < 0
            or edges < 0
            or self.source_visits + count > 256
            or self.edges + edges > 512
        ):
            raise FailureRefusal("capacity_exceeded")
        self.source_visits += count
        self.edges += edges

    def remaining(self, book: ReceiptBook) -> int:
        self.check()
        if not any(book is known for known in self.books):
            raise FailureRefusal("invalid_native_state")
        return MAX_RECEIPT_BYTES - self.retained_bytes - self.active_frame_bytes

    def reserve(self, book: ReceiptBook, size: int, key: tuple[Domain, str] | None) -> None:
        if type(size) is not int or not 0 <= size <= self.remaining(book):
            raise FailureRefusal("capacity_exceeded")
        if key is not None:
            if key not in self.identities and len(self.identities) >= MAX_IDENTITIES:
                raise FailureRefusal("capacity_exceeded")
            self.identities.add(key)
        self.retained_bytes += size

    def before_cohort(self) -> None:
        # This fixed terminal path does not discover or load a run cohort.
        raise FailureRefusal("invalid_native_state")

    def new_book(self) -> ReceiptBook:
        self.check()
        if len(self.books) >= 2:
            raise FailureRefusal("invalid_native_state")
        book = ReceiptBook(_scope=self)
        if book._wire_bytes > MAX_RECEIPT_BYTES - self.retained_bytes:
            raise FailureRefusal("capacity_exceeded")
        self.retained_bytes += book._wire_bytes
        self.books.append(book)
        return book

    def retain(self, value: Any) -> None:
        self.check()
        size = len(receipt_bytes(value, MAX_RECEIPT_BYTES - self.retained_bytes))
        self.retained_bytes += size
        self.detached_bytes += size

    def retain_configuration(self, value: bytes) -> None:
        self.check()
        if type(value) is not bytes or len(value) > MAX_RECEIPT_BYTES - self.retained_bytes:
            raise FailureRefusal("capacity_exceeded")
        self.retained_bytes += len(value)
        self.detached_bytes += len(value)

    def audit(self) -> None:
        self.check()
        if self.retained_bytes != self.detached_bytes + sum(
            book._wire_bytes for book in self.books
        ):
            raise FailureRefusal("invalid_native_state")
        if self.retained_bytes > MAX_RECEIPT_BYTES:
            raise FailureRefusal("capacity_exceeded")

    @contextmanager
    def frame_allowance(self) -> Iterator[int]:
        self.audit()
        # Reserve the entire permitted active frame before the encoder measures
        # and allocates it. No helper book/retention may run inside this scope.
        # The codec reports the actual measured bytes; the conservative reserve
        # is released in finally before further observations or another frame.
        limit = min(4096, MAX_RECEIPT_BYTES - self.retained_bytes)
        self.active_frame_bytes = limit
        self.frame_active = True
        try:
            yield limit
        finally:
            self.active_frame_bytes = 0
            self.frame_active = False
        self.audit()


_TERMINALS: WeakKeyDictionary[Connection, tuple[IssuedTerminalScope, _TerminalState]] = (
    WeakKeyDictionary()
)


def _issued(connection: Connection, token: IssuedTerminalScope) -> _TerminalState:
    if type(token) is not IssuedTerminalScope or not isinstance(connection, Connection):
        raise FailureRefusal("capability_not_issued")
    with _LOCK:
        issued = _TERMINALS.get(connection)
        if issued is None or issued[0] is not token:
            raise FailureRefusal("capability_not_issued")
        state = issued[1]
        if (
            type(state.coordinator) is not TerminalCoordinator
            or not state.coordinator._consumed
            or state.coordinator._work is not state.body.work
            or state.coordinator.engine is not connection.engine
            or require_body(connection, state.body.scope) is not state.body
        ):
            raise FailureRefusal("invalid_native_state")
        return state


def _receipt_payload(values: tuple[RawReceipt, ...]) -> list[Any]:
    return [[r.domain, r.identity, list(r.fields), list(r.values)] for r in values]


def _eligible(job: dict[str, Any], fence: JobFence, generation: int, now: int) -> None:
    if (
        job["status"] != "running"
        or job["owner"] != fence.owner_uuid
        or type(generation) is not int
        or generation != fence.generation
        or type(job["cancel"]) not in (bool, int)
        or job["cancel"] not in (False, True, 0, 1)
        or not lease_live(job["lease_until"], now)
        or job["error"] is not None
        or job["result"] is not None
    ):
        raise FailureRefusal("not_eligible")


def _any_call(connection: Connection, job_id: str) -> bool:
    calls = table("provider_calls", column("job_id"))
    value = connection.execute(
        select(select(1).where(calls.c.job_id == job_id).exists())
    ).scalar_one()
    if type(value) not in (bool, int) or value not in (False, True, 0, 1):
        raise FailureRefusal("invalid_native_state")
    return bool(value)


def _same_scalar(connection: Connection, expression: Any, value: Any) -> Any:
    equal = expression.is_not_distinct_from(value)
    if connection.dialect.name != "sqlite":
        return equal
    native_type = (
        "null"
        if value is None
        else "text"
        if type(value) is str
        else "real"
        if type(value) is float
        else "integer"
    )
    return and_(equal, func.typeof(expression) == native_type)


def _association_predicate(
    connection: Connection, operation: RawReceipt, configuration: RawReceipt
) -> Any:
    operations = table("operations", *(column(name) for name in operation.fields))
    objects = table("artifact_objects", *(column(name) for name in configuration.fields[:-1]))
    refs = table(
        "artifact_refs",
        column("project_id"),
        column("owner_kind"),
        column("owner_id"),
        column("artifact_id"),
        column("role"),
    )

    def matching(source: Any, receipt: RawReceipt) -> list[Any]:
        result = []
        for name, value in zip(receipt.fields, receipt.values, strict=True):
            if name == "reference_id":
                continue
            expression = source.c[name]
            if connection.dialect.name == "postgresql" and name in ("created_at", "retain_until"):
                expression = cast(expression, Text)
            result.append(_same_scalar(connection, expression, value))
        return result

    op = operation.row()
    return and_(
        select(1).select_from(operations).where(*matching(operations, operation)).exists(),
        select(func.count())
        .select_from(operations)
        .where(operations.c.job_id == op["job_id"])
        .scalar_subquery()
        == 1,
        select(1)
        .select_from(
            objects.join(
                refs,
                and_(refs.c.artifact_id == objects.c.id, refs.c.project_id == objects.c.project_id),
            )
        )
        .where(
            *matching(objects, configuration),
            refs.c.owner_kind == "job",
            refs.c.owner_id == op["job_id"],
            refs.c.role == "admission_config",
            refs.c.artifact_id == configuration.row()["reference_id"],
        )
        .exists(),
    )


def _read_created(connection: Connection, job_id: str, book: ReceiptBook) -> FailureRecord:
    # Candidate selection is job-only. Bound every cell before transfer; no
    # malformed/project/tag predicate can turn an existing row into absence.
    book._check_connection(connection)
    book.charge_sources(1)
    native_size = sum(
        (func.coalesce(_byte_length(connection, _EVIDENCE.c[name]), 0) for name in _FIELDS),
        literal(0),
    )
    safe = and_(
        native_size <= book.remaining,
        *(
            _EVIDENCE.c[name].is_(None) | (_byte_length(connection, _EVIDENCE.c[name]) <= limit)
            for name, limit in zip(_FIELDS, _LIMITS, strict=True)
        ),
    )
    from sqlalchemy import case

    values = (
        connection.execute(
            select(*(case((safe, _EVIDENCE.c[name]), else_=None).label(name) for name in _FIELDS))
            .where(_EVIDENCE.c.job_id == job_id)
            .limit(2)
        )
        .mappings()
        .all()
    )
    if len(values) != 1:
        raise FailureRefusal("invalid_native_state")
    book.observe("failure_count", job_id, (len(values),))
    book.observe("failure_cells", job_id, tuple(values[0][name] for name in _FIELDS))
    try:
        return FailureRecord(**dict(values[0]))
    except (TypeError, FailureRefusal):
        raise FailureRefusal("invalid_native_state") from None


def persist_verified_failure(
    connection: Connection, scope: IssuedTerminalScope
) -> TentativeCreated:
    """One exact issued completion scope; no caller-selected cause or values."""
    state = _issued(connection, scope)
    with _LOCK:
        if state.used:
            raise FailureRefusal("invocation_reused")
        state.used = True
    body, event = state.body, state.event
    reservation_scope = body.scope
    source, configuration = event.source, event.configuration
    source.__post_init__()
    state.retain(_receipt_payload((source.operation, source.job, source.configuration)))
    state.retain_configuration(configuration.canonical_bytes)
    state.retain(
        [
            source.organization_id,
            source.project_id,
            source.fence.job_id,
            source.fence.owner_uuid,
            source.fence.generation,
        ]
    )
    state.identities.update(
        (r.domain, r.identity) for r in (source.operation, source.job, source.configuration)
    )
    initial_book = state.new_book()
    rows = ReservationRows._capture_failure(connection, reservation_scope, body.work)
    state.rows = rows
    _absence(connection, reservation_scope)
    initial_book.charge_sources(1)
    initial_book.observe("failure_count", source.fence.job_id, (0,))
    current = _association(
        connection, reservation_scope, source.operation.identity, configuration, _book=initial_book
    )
    _same_association((source.operation, source.job, source.configuration), current)
    job = current[1].row()
    if job["lease_until"] != source.job.row()["lease_until"] or (
        type(job["lease_until"]) is not type(source.job.row()["lease_until"])
    ):
        raise FailureRefusal("stale_source")
    now = reservation._clock(connection)
    _eligible(job, source.fence, rows.job["lease_generation"], now)
    rows.reconcile(now)
    any_call = _any_call(connection, source.fence.job_id)
    initial_book.observe("any_provider_call", source.fence.job_id, (any_call,))
    with state.frame_allowance() as remaining:
        association, state.association_frame_bytes = association_digest(
            connection.dialect.name,
            source.organization_id,
            source.project_id,
            *current,
            remaining=remaining,
        )
    status: Literal["failed", "cancelled"] = "cancelled" if job["cancel"] else "failed"
    correlation = current[0].row()["failure_correlation_id"]
    if type(correlation) is not str:
        raise FailureRefusal("origin_unproved")
    after_job = replace(
        current[1], values=tuple(status if name == "status" else job[name] for name in JOB_LIMITS)
    )
    record = FailureRecord(
        1,
        "verified_failure",
        source.project_id,
        "job",
        source.fence.job_id,
        source.operation.identity,
        source.fence.generation,
        status,
        "dependency_failed",
        "outcome_unknown",
        "admission",
        correlation,
        association,
        "0" * 64,
        now,
    )
    state.retain(_receipt_payload((after_job,)))
    state.retain(asdict(record))
    with state.frame_allowance() as remaining:
        digest, state.source_frame_bytes = source_digest(
            connection.dialect.name,
            association,
            after_job,
            source.fence.generation,
            any_call,
            record,
            remaining=remaining,
        )
    record = replace(record, source_sha256=digest)
    original = OriginalFailureIntent(source.organization_id, source.fence, record)
    state.retain(asdict(original))
    state.original = original
    state.coordinator._original = original
    state.initial_job = current[1]
    after = rows.after_image()
    next(row for row in after["job"] if row["id"] == source.fence.job_id)["status"] = status
    rows.require_headroom(after)
    state.after = after
    _issued(connection, scope)
    jobs = table("jobs", *(column(name) for name in JOB_LIMITS), column("lease_generation"))
    result_refs = table("artifact_refs", column("owner_kind"), column("owner_id"), column("role"))
    changed = connection.execute(
        update(jobs)
        .values(status=status)
        .where(
            *(_same_scalar(connection, jobs.c[name], value) for name, value in job.items()),
            jobs.c.lease_generation == source.fence.generation,
            _association_predicate(connection, current[0], current[2]),
            ~select(1).where(_EVIDENCE.c.job_id == source.fence.job_id).exists(),
            ~select(1)
            .where(
                result_refs.c.owner_kind == "job",
                result_refs.c.owner_id == source.fence.job_id,
                result_refs.c.role == "result",
            )
            .exists(),
        )
    )
    if type(changed.rowcount) is not int or changed.rowcount != 1:
        raise FailureRefusal("stale_source")
    inserted = connection.execute(_EVIDENCE.insert().values(**asdict(record)))
    if type(inserted.rowcount) is not int or inserted.rowcount != 1:
        raise FailureRefusal("invalid_native_state")
    reservation.flush_constraints(connection, reservation_scope)
    state.coordinator.authority.check(
        connection,
        reservation_scope.principal,
        reservation_scope.context,
        "record",
        resource_kind="job",
        resource_id=source.fence.job_id,
    )
    rows.confirm(connection, after)
    final_book = state.new_book()
    final = _association(
        connection, reservation_scope, source.operation.identity, configuration, _book=final_book
    )
    _same_association(current, final)
    if final[1] != after_job or tuple(map(type, final[1].values)) != tuple(
        map(type, after_job.values)
    ):
        raise FailureRefusal("stale_source")
    actual = _read_created(connection, source.fence.job_id, final_book)
    final_call = _any_call(connection, source.fence.job_id)
    final_book.observe("any_provider_call", source.fence.job_id, (final_call,))
    if actual != record or final_call != any_call:
        raise FailureRefusal("stale_source")
    state.retain(asdict(actual))
    with state.frame_allowance() as remaining:
        final_digest, _ = source_digest(
            connection.dialect.name,
            association,
            final[1],
            source.fence.generation,
            any_call,
            actual,
            remaining=remaining,
        )
    if final_digest != record.source_sha256:
        raise FailureRefusal("stale_source")
    if rows.failure_authority is None:
        raise FailureRefusal("invalid_native_state")
    _refresh_producer_authority(connection, reservation_scope, rows.failure_authority)
    _issued(connection, scope)
    final_now = reservation._clock(connection)
    # Only pure checks and inherited COMMIT controls follow the final native tick.
    _eligible(job, source.fence, rows.job["lease_generation"], final_now)
    state.audit()
    body.work.check()
    return TentativeCreated(original)


class TerminalCoordinator:
    """One terminal attempt; retained intent is inspection data, never a retry."""

    def __init__(self, engine: Engine, authority: RequestAuthority):
        self.engine, self.authority = engine, authority
        self._lock = Lock()
        self._consumed = False
        self._transaction = TransactionOutcome()
        self._outcome = TransactionFacts.observe(self._transaction)
        self._work: OperationWork | None = None
        self._original: OriginalFailureIntent | None = None

    @property
    def outcome(self) -> TransactionFacts:
        with self._lock:
            return self._outcome

    @property
    def original(self) -> OriginalFailureIntent | None:
        return self._original

    def complete_failure(
        self, principal: VerifiedPrincipal, context: ProjectContext, event: CompletionEvent
    ) -> CreatedFailure:
        work = OperationWork(include_acquisition=True)
        with self._lock:
            if self._consumed:
                raise FailureRefusal("invocation_reused")
            self._consumed = True
            self._work = work
        try:
            # Pop once before any terminal storage work; refusal never restores it.
            record = _consume_dependency_event(
                event, self.engine, self.authority, principal, context
            )
            if (
                type(self) is not TerminalCoordinator
                or type(self.authority) is not RequestAuthority
            ):
                raise FailureRefusal("invalid_intent")
            if self.authority.engine is not self.engine:
                raise FailureRefusal("invalid_intent")
            self.authority._principal(principal)
            require_engine(self.engine)
            scope = ReservationScope(principal, context, record.source.fence.job_id)
            with (
                admission_transaction(self.engine, self._transaction, work=work) as connection,
                issued_connection(connection, scope, work) as body,
            ):
                lock_authority(
                    self.authority,
                    connection,
                    principal,
                    context,
                    "job",
                    scope.job_id,
                    exclusive_organization=True,
                )
                self.authority.check(
                    connection,
                    principal,
                    context,
                    "record",
                    resource_kind="job",
                    resource_id=scope.job_id,
                )
                token = object.__new__(IssuedTerminalScope)
                state = _TerminalState(self, body, record)
                with _LOCK:
                    if connection in _TERMINALS:
                        raise FailureRefusal("invalid_native_state")
                    _TERMINALS[connection] = token, state
                try:
                    tentative = persist_verified_failure(connection, token)
                finally:
                    with _LOCK:
                        _TERMINALS.pop(connection, None)
            facts = TransactionFacts.observe(self._transaction)
            if not facts.commit_acknowledged or facts.cleanup_failed:
                raise FailureRefusal("invalid_native_state")
            work._limits(cleanup=True)
            work.remaining_timeouts_ms()
            return CreatedFailure(tentative.original)
        except MigrationRefused as error:
            raise FailureRefusal(
                "capacity_exceeded"
                if error.code in {"ledger_limit_exceeded", "source_limit_exceeded"}
                else "unsupported_profile"
            ) from None
        except ReservationRefusal as error:
            raise FailureRefusal(
                "not_eligible"
                if error.reason == "job_not_live"
                else "capacity_exceeded"
                if error.reason == "capacity_exceeded"
                else "unsupported_profile"
                if error.reason == "schema_or_provenance_invalid"
                else "invalid_native_state"
            ) from None
        finally:
            with self._lock:
                self._outcome = TransactionFacts.observe(self._transaction)
