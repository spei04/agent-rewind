"""Bounded run-operation source observations and final relational comparison.

No authorization, connections, storage or service orchestration live here.
The caller supplies a freshly authorized original project and shared budgets.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Float,
    Text,
    and_,
    case,
    cast,
    column,
    func,
    literal_column,
    select,
    table,
    text,
    union_all,
)
from sqlalchemy.engine import Connection
from sqlalchemy.sql.selectable import CTE

from .admission_records import OPERATION_LIMITS, OPERATIONS, hexadecimal
from .database import records
from .operation_reads import (
    DESCRIPTOR_FIELDS,
    JOB_LIMITS,
    JOBS,
    RawReceipt,
    ReceiptBook,
    invalid,
    validate_association,
)
from .published_reader import _objects, _refs
from .scoped_lineage import Lineage, ResourceNotFound
from .scoped_repositories import (
    ProjectContext,
    _byte_length,
    _invalid_constant,
    _object,
    scopes,
)

RECORD_FIELDS = ("id", "kind", "created", "body")
MAX_BODY_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class RunCohort:
    job_id: str
    records: tuple[RawReceipt, ...]

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(row.identity for row in self.records)


def _scope(context: ProjectContext, kind: Any, identity: Any) -> Any:
    return and_(
        scopes.c.project_id == context.project_id,
        scopes.c.resource_kind == kind,
        scopes.c.resource_id == identity,
    )


def _discovery(context: ProjectContext, job_id: str) -> Any:
    # Match existing scoped by_job semantics: foreign incoming aliases cannot
    # deny access, and malformed selected candidates are never filtered away.
    return (
        select(
            records.c.id,
            records.c.kind,
            records.c.created,
            cast(records.c.data, Text).label("body"),
        )
        .select_from(records.join(scopes, _scope(context, records.c.kind, records.c.id)))
        .where(records.c.data["job_id"].as_string() == job_id)
        .order_by(records.c.kind, records.c.id)
    )


def cohort_query(
    connection: Connection,
    context: ProjectContext,
    job_id: str,
    book: ReceiptBook,
) -> Any:
    book._check_connection(connection)
    book._check_live(context, "job", job_id)
    book._before_cohort()
    hexadecimal(job_id, 32)
    remaining = 256 - book.source_visits
    if remaining < 0:
        raise invalid()
    # Keep native type evidence before any SQLite cast. PostgreSQL JSON is
    # necessarily native JSON; its textual representation is the raw receipt.
    native = (
        and_(
            func.typeof(records.c.data) == "text",
            func.typeof(records.c.id) == "text",
            func.typeof(records.c.kind) == "text",
            func.typeof(records.c.created).in_(("integer", "real")),
        )
        if connection.dialect.name == "sqlite"
        else literal_column("true")
    )
    candidates = (
        _discovery(context, job_id)
        .add_columns(native.label("native"))
        .limit(remaining + 1)
        .cte("cohort_candidates")
        .prefix_with("MATERIALIZED")
    )
    lengths = [
        func.coalesce(_byte_length(connection, candidates.c[name]), 0) for name in RECORD_FIELDS
    ]
    stats = (
        select(
            func.count().label("count"),
            func.coalesce(func.sum(sum(lengths, literal_column("0"))), 0).label("bytes"),
            func.coalesce(
                func.min(
                    case(
                        (
                            and_(
                                candidates.c.native,
                                _byte_length(connection, candidates.c.id) == 32,
                                _byte_length(connection, candidates.c.kind) <= 20,
                                _byte_length(connection, candidates.c.created) <= 64,
                                _byte_length(connection, candidates.c.body) <= MAX_BODY_BYTES,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                1,
            ).label("valid"),
        )
        .cte("cohort_stats")
        .prefix_with("MATERIALIZED")
    )
    safe = and_(
        stats.c.count <= remaining,
        stats.c.bytes <= book.remaining,
        stats.c.valid == 1,
    )
    return (
        select(
            *(case((safe, candidates.c[name]), else_=None).label(name) for name in RECORD_FIELDS)
        )
        .select_from(candidates.join(stats, literal_column("true")))
        .order_by(candidates.c.kind, candidates.c.id)
    )


def read_run_cohort(
    connection: Connection,
    context: ProjectContext,
    job: RawReceipt,
    book: ReceiptBook,
) -> RunCohort:
    book._check_connection(connection)
    book._check_live(context, "job", job.identity)
    if job.domain != "job" or job.fields != tuple(JOB_LIMITS) or job.row()["kind"] != "run":
        raise invalid()
    rows = (
        connection.execute(cohort_query(connection, context, job.identity, book)).mappings().all()
    )
    book.charge_sources(len(rows), edges=2 * len(rows))
    cached: dict[tuple[str, str], dict[str, Any]] = {}
    original: list[RawReceipt] = []
    for row in rows:
        identifier = row["id"]
        hexadecimal(identifier, 32)
        if (
            row["kind"] != "run"
            or type(row["body"]) is not str
            or type(row["created"]) not in (int, float)
            or not math.isfinite(row["created"])
        ):
            raise invalid()
        try:
            value = json.loads(
                row["body"],
                object_pairs_hook=_object,
                parse_constant=_invalid_constant,
            )
        except (ValueError, TypeError, RecursionError, ResourceNotFound):
            raise invalid() from None
        if (
            not isinstance(value, dict)
            or value.get("job_id") != job.identity
            or "parent_id" not in value
            or value["parent_id"] is not None
        ):
            raise invalid()
        key = "run", identifier
        if key in cached:
            raise invalid()
        cached[key] = {**value, "id": identifier, "created": row["created"]}
        original.append(book.remember("run", identifier, RECORD_FIELDS, dict(row)))
    ids = tuple(row.identity for row in original)
    book.observe("cohort", job.identity, ids)

    def record(kind: str, identity: str) -> dict[str, Any]:
        try:
            return cached[kind, identity]
        except KeyError:
            raise ResourceNotFound() from None

    def owner(identity: str) -> dict[str, Any]:
        if identity != job.identity:
            raise ResourceNotFound()
        return job.row()

    def members(identity: str) -> list[tuple[str, str]]:
        if identity != job.identity:
            raise ResourceNotFound()
        return [("run", item) for item in ids]

    # Existing lineage rules, with no hidden SQL and no expansion beyond the
    # complete run-only cohort. Two edges/member and one job were charged once.
    try:
        Lineage(record, owner, members).validate("job", job.identity)
    except ResourceNotFound:
        raise invalid() from None
    return RunCohort(job.identity, tuple(original))


def validate_result_member(cohort: RunCohort, run_id: str) -> None:
    hexadecimal(run_id, 32)
    if run_id not in cohort.ids:
        raise invalid()


def _expected(connection: Connection) -> CTE:
    if connection.dialect.name == "sqlite":
        source = text("""SELECT
            CAST(json_extract(value,'$[0]') AS TEXT) AS domain,
            CAST(json_extract(value,'$[1]') AS TEXT) AS id,
            json_extract(value,'$[3]') AS values_json
            FROM json_each(:receipts,'$.rows')""")
    elif connection.dialect.name == "postgresql":
        source = text("""SELECT value->>0 AS domain,value->>1 AS id,
            value->3 AS values_json
            FROM jsonb_array_elements(CAST(:receipts AS jsonb)->'rows')""")
    else:
        raise invalid()
    return (
        source.columns(domain=Text(), id=Text(), values_json=Text())
        .cte("expected_receipts")
        .prefix_with("MATERIALIZED")
    )


def _value(connection: Connection, wanted: CTE, index: int, sql_type: Any) -> Any:
    if connection.dialect.name == "sqlite":
        return func.json_extract(wanted.c.values_json, literal_column("'$[" + str(index) + "]'"))
    return cast(wanted.c.values_json.op("->>")(literal_column(str(index))), sql_type)


def _equal(connection: Connection, source: Any, expected: Any) -> Any:
    equality = source.is_not_distinct_from(expected)
    if connection.dialect.name == "sqlite":
        return and_(equality, func.typeof(source) == func.typeof(expected))
    return equality


def _matches(
    connection: Connection,
    wanted: CTE,
    source: Any,
    fields: tuple[str, ...],
    types: dict[str, Any],
) -> list[Any]:
    result = []
    for index, name in enumerate(fields):
        value = source.c[name]
        if connection.dialect.name == "postgresql" and name in {
            "created_at",
            "retain_until",
            "body",
        }:
            value = cast(value, Text)
        result.append(
            _equal(connection, value, _value(connection, wanted, index, types.get(name, Text())))
        )
    return result


def matching_query(
    connection: Connection,
    context: ProjectContext,
    book: ReceiptBook,
    cohort: RunCohort,
) -> tuple[Any, dict[str, str]]:
    """One relational observation; caller reauthorizes after exact key equality."""
    return _matching_query(connection, context, book, cohort, cancellation=False)


def _matching_query(
    connection: Connection,
    context: ProjectContext,
    book: ReceiptBook,
    cohort: RunCohort,
    *,
    cancellation: bool,
) -> tuple[Any, dict[str, str]]:
    book._check_connection(connection)
    book._check_live(context, "job", cohort.job_id)
    rows = {(r.domain, r.identity): r for r in book.receipts}
    operations = [r for r in book.receipts if r.domain == "operation"]
    if len(operations) != 1:
        raise invalid()
    try:
        job = rows["job", cohort.job_id]
        config = rows["admission_config", cohort.job_id]
        result_count = (0,) if cancellation else book.observations["result_count", cohort.job_id]
    except KeyError:
        raise invalid() from None
    validate_association(operations[0], job, config)
    result = rows.get(("result", cohort.job_id))
    if (
        not cancellation
        and job.row()["result"] is not None
        and (result is None or result.row()["digest"] != job.row()["result"])
    ):
        raise invalid()
    if (
        result_count not in ((0,), (1,))
        or book.observations.get(("cohort", cohort.job_id)) != cohort.ids
        or set(rows)
        != {
            ("operation", operations[0].identity),
            ("job", cohort.job_id),
            ("admission_config", cohort.job_id),
            *(("run", identity) for identity in cohort.ids),
            *({("result", cohort.job_id)} if result_count == (1,) else set()),
        }
    ):
        raise invalid()
    if cancellation and set(book.observations) != {("cohort", cohort.job_id)}:
        raise invalid()
    fields = {
        "operation": tuple(OPERATION_LIMITS),
        "job": tuple(JOB_LIMITS),
        "run": RECORD_FIELDS,
        "admission_config": (*DESCRIPTOR_FIELDS, "reference_id"),
        "result": (*DESCRIPTOR_FIELDS, "reference_id"),
    }
    if any(receipt.fields != fields[receipt.domain] for receipt in book.receipts):
        raise invalid()
    encoded = book.encoded().decode()
    wanted = _expected(connection)
    job_types = {
        "created": Float(),
        "lease_until": Float(),
        "budget": BigInteger(),
        "reserved": BigInteger(),
        "cancel": Boolean(),
        "payload_version": BigInteger(),
    }
    op_query = (
        select(wanted.c.domain, wanted.c.id)
        .select_from(wanted.join(OPERATIONS, OPERATIONS.c.id == wanted.c.id))
        .where(
            wanted.c.domain == "operation",
            OPERATIONS.c.project_id == context.project_id,
            *_matches(
                connection,
                wanted,
                OPERATIONS,
                tuple(OPERATION_LIMITS),
                {"payload_version": BigInteger()},
            ),
        )
    )
    job_query = (
        select(wanted.c.domain, wanted.c.id)
        .select_from(
            wanted.join(JOBS, JOBS.c.id == wanted.c.id).join(
                scopes,
                _scope(context, literal_column("'job'"), wanted.c.id),
            )
        )
        .where(
            wanted.c.domain == "job",
            *_matches(connection, wanted, JOBS, tuple(JOB_LIMITS), job_types),
        )
    )
    # Untyped native columns avoid JSON/Boolean result processors. SQLite BLOB
    # and integer/real changes must survive final comparison, not just rereads.
    raw_records = table("records", column("id"), column("kind"), column("created"), column("data"))
    record_values = select(
        raw_records.c.id,
        raw_records.c.kind,
        raw_records.c.created,
        (
            cast(raw_records.c.data, Text)
            if connection.dialect.name == "postgresql"
            else raw_records.c.data
        ).label("body"),
    ).subquery("raw_sources")
    record_query = (
        select(wanted.c.domain, wanted.c.id)
        .select_from(
            wanted.join(
                record_values,
                and_(
                    record_values.c.id == wanted.c.id,
                    record_values.c.kind == wanted.c.domain,
                ),
            ).join(scopes, _scope(context, wanted.c.domain, wanted.c.id))
        )
        .where(
            wanted.c.domain == "run",
            *_matches(connection, wanted, record_values, RECORD_FIELDS, {"created": Float()}),
        )
    )
    refs = (
        select(
            _refs.c.project_id,
            _refs.c.owner_kind,
            _refs.c.owner_id,
            _refs.c.role,
            _refs.c.artifact_id,
        )
        .where(
            _refs.c.project_id == context.project_id,
            _refs.c.owner_kind == "job",
            _refs.c.owner_id == cohort.job_id,
            (_refs.c.role == "admission_config")
            if cancellation
            else _refs.c.role.in_(("admission_config", "result")),
        )
        .limit(2 if cancellation else 3)
        .cte("observed_refs")
        .prefix_with("MATERIALIZED")
    )
    descriptors = (
        select(
            *(_objects.c[name] for name in DESCRIPTOR_FIELDS),
            refs.c.artifact_id.label("reference_id"),
            refs.c.owner_id,
            refs.c.role,
        )
        .select_from(
            refs.outerjoin(
                _objects,
                and_(
                    _objects.c.project_id == refs.c.project_id, _objects.c.id == refs.c.artifact_id
                ),
            )
        )
        .cte("observed_descriptors")
        .prefix_with("MATERIALIZED")
    )
    descriptor_query = (
        select(wanted.c.domain, wanted.c.id)
        .select_from(
            wanted.join(
                descriptors,
                and_(
                    descriptors.c.owner_id == wanted.c.id,
                    descriptors.c.role == wanted.c.domain,
                ),
            ),
        )
        .where(
            wanted.c.domain.in_(("admission_config", "result")),
            *_matches(
                connection,
                wanted,
                descriptors,
                (*DESCRIPTOR_FIELDS, "reference_id"),
                {"format_version": BigInteger(), "byte_count": BigInteger()},
            ),
        )
    )
    current = (
        _discovery(context, cohort.job_id)
        .with_only_columns(
            records.c.id,
            records.c.kind,
        )
        .limit(256)
        .cte("current_members")
        .prefix_with("MATERIALIZED")
    )
    unknown = (
        select(current.c.id)
        .select_from(
            current.outerjoin(
                wanted,
                and_(wanted.c.domain == current.c.kind, wanted.c.id == current.c.id),
            )
        )
        .where(wanted.c.id.is_(None))
        .exists()
    )
    config_count = (
        select(func.count())
        .select_from(refs)
        .where(
            refs.c.role == "admission_config",
        )
        .scalar_subquery()
    )
    results = (
        select(func.count())
        .select_from(refs)
        .where(
            refs.c.role == "result",
        )
        .scalar_subquery()
    )
    matches = union_all(op_query, job_query, record_query, descriptor_query).cte("matches")
    query = (
        select(matches.c.domain, matches.c.id)
        .where(
            ~unknown,
            config_count == 1,
            *(() if cancellation else (results == result_count[0],)),
        )
        .limit(len(rows) + 1)
    )
    # Bound actual compiled parameter cardinality, including SQLAlchemy constants.
    if len(query.compile(dialect=connection.dialect).params) > 64:
        raise invalid()
    return query, {"receipts": encoded}


def verify_read_snapshot(
    connection: Connection,
    context: ProjectContext,
    book: ReceiptBook,
    cohort: RunCohort,
) -> None:
    query, parameters = matching_query(connection, context, book, cohort)
    rows = connection.execute(query, parameters).all()
    keys = {(row.domain, row.id) for row in rows}
    expected = {(row.domain, row.identity) for row in book.receipts}
    if len(rows) != len(keys) or keys != expected:
        raise invalid()


def _verify_cancellation_snapshot(
    connection: Connection,
    context: ProjectContext,
    book: ReceiptBook,
    cohort: RunCohort,
) -> None:
    """Phase-local equality only; no result artifacts or cancellation effect."""
    query, parameters = _matching_query(connection, context, book, cohort, cancellation=True)
    rows = connection.execute(query, parameters).all()
    keys = {(row.domain, row.id) for row in rows}
    expected = {(row.domain, row.identity) for row in book.receipts}
    if len(rows) != len(keys) or keys != expected:
        raise invalid()
