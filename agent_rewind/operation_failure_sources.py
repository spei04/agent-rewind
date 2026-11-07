"""One-snapshot successor matching, preserving the original operation predicates."""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Float,
    Text,
    and_,
    cast,
    column,
    func,
    literal_column,
    or_,
    select,
    table,
    text,
    union_all,
)
from sqlalchemy.engine import Connection
from sqlalchemy.sql.selectable import CTE

from .admission_records import OPERATION_LIMITS, OPERATIONS
from .database import records
from .operation_failure_reads import EVIDENCE_FIELDS, SuccessorReceiptBook
from .operation_reads import DESCRIPTOR_FIELDS, JOB_LIMITS, invalid, validate_association
from .operation_sources import RECORD_FIELDS, RunCohort, _discovery, _equal, _matches, _scope
from .published_reader import _objects, _refs
from .scoped_repositories import ProjectContext, scopes

JOBS = table("jobs", *(column(name) for name in JOB_LIMITS), column("lease_generation"))
_EVIDENCE = table("job_failure_evidence", *(column(name) for name in EVIDENCE_FIELDS))
_CALLS = table("provider_calls", column("job_id"))


def _expected_successor(connection: Connection) -> CTE:
    if connection.dialect.name == "sqlite":
        source = text("""SELECT
            CAST(json_extract(value,'$[0]') AS TEXT) AS domain,
            CAST(json_extract(value,'$[1]') AS TEXT) AS id,
            json_extract(value,'$[2]') AS values_json,
            json_extract(value,'$[3]') AS extension_json
            FROM json_each(:receipts,'$.rows')""")
    elif connection.dialect.name == "postgresql":
        source = text("""SELECT value->>0 AS domain,value->>1 AS id,
            value->2 AS values_json,value->3 AS extension_json
            FROM jsonb_array_elements(CAST(:receipts AS jsonb)->'rows')""")
    else:
        raise invalid()
    return (
        source.columns(domain=Text(), id=Text(), values_json=Text(), extension_json=Text())
        .cte("expected_receipts")
        .prefix_with("MATERIALIZED")
    )


def _extension(connection: Connection, wanted: CTE, path: tuple[int, ...], sql_type: Any) -> Any:
    # The only callers below supply fixed source indices, never request strings.
    if connection.dialect.name == "sqlite":
        pointer = "'$" + "".join("[" + str(index) + "]" for index in path) + "'"
        return func.json_extract(wanted.c.extension_json, literal_column(pointer))
    pointer = "'{" + ",".join(str(index) for index in path) + "}'"
    return cast(wanted.c.extension_json.op("#>>")(literal_column(pointer)), sql_type)


def _failure_matches(connection: Connection, wanted: CTE, job_id: str) -> list[Any]:
    candidates = (
        select(*(_EVIDENCE.c[name] for name in EVIDENCE_FIELDS))
        .where(_EVIDENCE.c.job_id == job_id)
        .limit(2)
        .cte("failure_candidates")
        .prefix_with("MATERIALIZED")
    )
    count = select(func.count()).select_from(candidates).scalar_subquery()
    any_call = select(_CALLS.c.job_id).where(_CALLS.c.job_id == job_id).exists()
    types = {
        "schema_version": BigInteger(),
        "lease_generation": BigInteger(),
        "created_at_micros": BigInteger(),
    }
    exact = []
    for index, name in enumerate(EVIDENCE_FIELDS):
        expected = _extension(connection, wanted, (3, index), types.get(name, Text()))
        exact.append(_equal(connection, candidates.c[name], expected))
    evidence_matches = (
        select(literal_column("1")).select_from(candidates).where(*exact).correlate(wanted).exists()
    )
    verified = (
        select(literal_column("1"))
        .select_from(candidates)
        .where(candidates.c.kind == literal_column("'verified_failure'"))
        .exists()
    )
    result_exists = (
        select(literal_column("1"))
        .select_from(_refs)
        .where(
            _refs.c.owner_kind == literal_column("'job'"),
            _refs.c.owner_id == job_id,
            _refs.c.role == literal_column("'result'"),
        )
        .exists()
    )
    return [
        or_(~verified, ~result_exists),
        _equal(
            connection,
            JOBS.c.lease_generation,
            _extension(connection, wanted, (0,), BigInteger()),
        ),
        _equal(connection, count, _extension(connection, wanted, (1,), BigInteger())),
        _equal(connection, any_call, _extension(connection, wanted, (2,), Boolean())),
        or_(
            and_(
                count == literal_column("0"),
                _extension(connection, wanted, (3,), Text()).is_(None),
            ),
            and_(count == literal_column("1"), evidence_matches),
        ),
    ]


def matching_successor_query(
    connection: Connection,
    context: ProjectContext,
    book: SuccessorReceiptBook,
    cohort: RunCohort,
) -> tuple[Any, dict[str, str]]:
    return _matching_successor_query(connection, context, book, cohort, cancellation=False)


def _matching_successor_query(
    connection: Connection,
    context: ProjectContext,
    book: SuccessorReceiptBook,
    cohort: RunCohort,
    *,
    cancellation: bool,
) -> tuple[Any, dict[str, str]]:
    with book._attempt(connection, context, "job", cohort.job_id):
        rows = {(r.domain, r.identity): r for r in book.receipts}
        operations = [r for r in book.receipts if r.domain == "operation"]
        if len(operations) != 1:
            raise invalid()
        try:
            job = rows["job", cohort.job_id]
            config = rows["admission_config", cohort.job_id]
            result_count = (
                (0,) if cancellation else book.observations["result_count", cohort.job_id]
            )
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
        if cancellation:
            expected_observations = {("cohort", cohort.job_id)}
            observed = book.job_observation(cohort.job_id)
            if observed.evidence is not None and observed.evidence[1] == "verified_failure":
                zero = book.observations.get(("result_count", cohort.job_id))
                if zero != (0,) or type(zero[0]) is not int:
                    raise invalid()
                expected_observations.add(("result_count", cohort.job_id))
            if set(book.observations) != expected_observations:
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
        wanted = _expected_successor(connection)
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
                *_failure_matches(connection, wanted, cohort.job_id),
            )
        )
        # Untyped native columns avoid JSON/Boolean result processors. SQLite BLOB
        # and integer/real changes must survive final comparison, not just rereads.
        raw_records = table(
            "records", column("id"), column("kind"), column("created"), column("data")
        )
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
                        _objects.c.project_id == refs.c.project_id,
                        _objects.c.id == refs.c.artifact_id,
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


def verify_successor_snapshot(
    connection: Connection,
    context: ProjectContext,
    book: SuccessorReceiptBook,
    cohort: RunCohort,
) -> None:
    with book._attempt(connection, context, "job", cohort.job_id):
        query, parameters = matching_successor_query(connection, context, book, cohort)
        with connection.execute(query, parameters) as result:
            rows = result.all()
        book._check_live()
        keys = {(row.domain, row.id) for row in rows}
        expected = {(row.domain, row.identity) for row in book.receipts}
        if len(rows) != len(keys) or keys != expected:
            raise invalid()


def verify_successor_cancellation_snapshot(
    connection: Connection,
    context: ProjectContext,
    book: SuccessorReceiptBook,
    cohort: RunCohort,
) -> None:
    """Phase-local raw equality; neither disclosure nor an effect capability."""
    with book._attempt(connection, context, "job", cohort.job_id):
        query, parameters = _matching_successor_query(
            connection, context, book, cohort, cancellation=True
        )
        with connection.execute(query, parameters) as result:
            rows = result.all()
        book._check_live()
        keys = {(row.domain, row.id) for row in rows}
        expected = {(row.domain, row.identity) for row in book.receipts}
        if len(rows) != len(keys) or keys != expected:
            raise invalid()
