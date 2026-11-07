"""Native positive inputs and explicitly bounded Q1/Q2 component negatives.

The provenance and returned-row corruption controls below run in Python after
genuine native positives. They do not disable immutable evidence constraints or
claim that a second evidence row can inhabit an accepted complete catalog.
The final-query sentinel and the single 255-root cancellation phase execute on
the real successor schema. A single phase is not the three-phase cancel service.
"""

import json
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest
import test_migrations_postgres as migration_tests
from failure_postgres_fixture import pg
from operation_failure_service_oracle import (
    add_roots,
    assert_service_released,
    canonical,
    expected_get,
    observe_service,
    publish_result,
    service_case,
)
from sqlalchemy import text
from test_failure_persistence_native_oracle import assert_same_state, whole_state

from agent_rewind import operation_failure_reads as reads
from agent_rewind import operation_failure_sources as sources
from agent_rewind.admission_records import AdmissionStorageError
from agent_rewind.operation_failure_cancellation import SuccessorCancellationReceipts
from agent_rewind.operation_reads import read_descriptor, read_operation
from agent_rewind.operation_sources import read_run_cohort
from agent_rewind.operation_work import OperationWork, operation_connection

__all__ = ["pg"]
PG = pytest.param(
    "postgresql",
    marks=(
        pytest.mark.f4_owned_postgres,
        pytest.mark.skipif(not migration_tests.POSTGRES, reason="Opt-in synthetic F4 components"),
    ),
    id="postgresql",
)
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


@pytest.fixture(params=["sqlite", PG])
def dialect(request):
    return request.param


def changed_hex(value):
    return value[:-1] + ("0" if value[-1] != "0" else "1")


def clone_book(receipts, jobs, observations):
    book = reads.SuccessorReceiptBook()
    for row in receipts:
        if row.domain == "job":
            book.remember_job(row, jobs[row.identity])
        else:
            book.remember(row.domain, row.identity, row.fields, row.row())
    for (kind, identity), values in observations.items():
        book.observe(kind, identity, values)
    return book


class ComponentResult:
    """Only a returned-row validation seam; never a native connection."""

    def __init__(self, rows):
        self.rows = rows
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.closed = True

    def mappings(self):
        return self

    def all(self):
        return list(self.rows)


class ComponentConnection:
    def __init__(self, dialect, rows):
        self.dialect = SimpleNamespace(name=dialect)
        self.result = ComponentResult(rows)
        self.calls = []

    def execute(self, query, parameters):
        self.calls.append((query, dict(parameters)))
        return self.result


def test_genuine_failure_inputs_reach_provenance_and_transfer_rejection_gates(
    request, tmp_path, monkeypatch, record_property, dialect
):
    with service_case(
        request, tmp_path, monkeypatch, record_property, dialect, failed=True
    ) as fixture:
        before = whole_state(fixture.case)
        captured = []
        original_verified = reads._verified_error

        def capture(*args):
            result = original_verified(*args)
            captured.append(args[:5] + (args[6],))
            return result

        with monkeypatch.context() as patch:
            patch.setattr(reads, "_verified_error", capture)
            with observe_service(fixture, patch, record_property) as observed:
                result = fixture.service._read_successor(
                    fixture.principal, fixture.context, fixture.operation_id
                )
        assert result == expected_get(fixture, before)
        assert_service_released(observed)
        assert captured
        name, context, operation, job, configuration, observation = captured[0]
        assert name == dialect and observation.evidence_count == 1
        assert job.row()["status"] == "failed"
        assert tuple(reads.EVIDENCE_FIELDS) == EVIDENCE_FIELDS
        wanted_error = expected_get(fixture, before)["error"]

        def retained(value):
            return clone_book(
                (operation, job, configuration),
                {job.identity: value},
                {("result_count", job.identity): (0,)},
            )

        # Genuine retained inputs must pass before any deliberately malformed
        # Python component input is considered.
        positive = retained(observation)
        assert (
            reads.successor_error(dialect, context, operation, job, configuration, positive)
            == wanted_error
        )
        assert positive.active_frame_bytes == 0

        cells = dict(zip(EVIDENCE_FIELDS, observation.evidence, strict=True))
        vectors = [
            ("version", "schema_version", 2, 0, 0),
            ("kind", "kind", "invented", 0, 0),
            ("version-type", "schema_version", True, 0, 0),
            ("project", "project_id", changed_hex(cells["project_id"]), 0, 0),
            ("resource", "job_resource_kind", "run", 0, 0),
            ("job", "job_id", changed_hex(cells["job_id"]), 0, 0),
            ("operation", "operation_id", changed_hex(cells["operation_id"]), 0, 0),
            ("generation", "lease_generation", cells["lease_generation"] + 1, 0, 0),
            ("generation-type", "lease_generation", True, 0, 0),
            ("status", "job_status", "cancelled", 0, 0),
            ("origin", "origin_kind", "migration_marker", 0, 0),
            ("correlation", "correlation_id", changed_hex(cells["correlation_id"]), 0, 0),
            ("cause", "cause", "invented", 0, 0),
            ("phase", "phase", "invented", 0, 0),
            ("created-type", "created_at_micros", False, 0, 0),
            ("association", "association_sha256", changed_hex(cells["association_sha256"]), 1, 0),
            ("source", "source_sha256", changed_hex(cells["source_sha256"]), 1, 1),
        ]
        witnessed = []
        for label, field, value, association_calls, source_calls in vectors:
            altered = dict(cells)
            altered[field] = value
            component = replace(
                observation, evidence=tuple(altered[name] for name in EVIDENCE_FIELDS)
            )
            book = retained(component)
            initial_wire = book.encoded()
            visits = {"verified": 0, "record": 0, "association": 0, "source": 0}
            real_record = reads.FailureRecord
            real_association = reads.association_digest
            real_source = reads.source_digest

            def verified(*args, _visits=visits):
                _visits["verified"] += 1
                return original_verified(*args)

            def record(*, _visits=visits, _real_record=real_record, **kwargs):
                _visits["record"] += 1
                return _real_record(**kwargs)

            def association(*args, _visits=visits, _real_association=real_association, **kwargs):
                _visits["association"] += 1
                return _real_association(*args, **kwargs)

            def source_digest(*args, _visits=visits, _real_source=real_source, **kwargs):
                _visits["source"] += 1
                return _real_source(*args, **kwargs)

            with monkeypatch.context() as patch:
                patch.setattr(reads, "_verified_error", verified)
                patch.setattr(reads, "FailureRecord", record)
                patch.setattr(reads, "association_digest", association)
                patch.setattr(reads, "source_digest", source_digest)
                with pytest.raises(AdmissionStorageError):
                    reads.successor_error(dialect, context, operation, job, configuration, book)
            assert visits == {
                "verified": 1,
                "record": 1,
                "association": association_calls,
                "source": source_calls,
            }, label
            assert book.active_frame_bytes == 0 and book.encoded() == initial_wire
            witnessed.append({"component": label, "visits": visits})

        # Native guarded transfer is executed once to establish an authentic
        # positive row. Subsequent corrupt rows are parser-only controls; no DDL,
        # trigger removal, evidence UPDATE or manufactured native absence occurs.
        query = reads._job_query(dialect)
        parameters = {"project": context.project_id, "job": job.identity, "remaining": 4 * 1024**2}
        with fixture.reader_engine.connect() as connection:
            native_rows = connection.execute(text(query), parameters).mappings().all()
        assert len(native_rows) == 1 and native_rows[0]["safe"] == 1
        native = dict(native_rows[0])
        candidate = ComponentConnection(dialect, [native])
        parsed = reads.read_successor_job(
            candidate, context, job.identity, reads.SuccessorReceiptBook()
        )
        assert parsed == job and candidate.result.closed and len(candidate.calls) == 1
        transfer_vectors = [
            ("two-returned-rows", [native, dict(native)], 0),
            ("unsafe", [{**native, "safe": 0}], 0),
            ("safe-bool", [{**native, "safe": True}], 0),
            ("second-evidence-candidate", [{**native, "evidence_count": 2}], 1),
            ("count-bool", [{**native, "evidence_count": True}], 1),
            ("generation-float", [{**native, "generation": float(native["generation"])}], 1),
            (
                "call-type",
                [{**native, "any_provider_call": True if dialect == "sqlite" else 1}],
                0,
            ),
        ]
        original_post_init = reads.JobObservation.__post_init__
        for label, rows, post_init_calls in transfer_vectors:
            visits = []
            candidate = ComponentConnection(dialect, rows)
            book = reads.SuccessorReceiptBook()

            def post_init(value, *, _visits=visits):
                _visits.append("observation")
                return original_post_init(value)

            with monkeypatch.context() as patch:
                patch.setattr(reads.JobObservation, "__post_init__", post_init)
                with pytest.raises(AdmissionStorageError):
                    reads.read_successor_job(candidate, context, job.identity, book)
            assert len(visits) == post_init_calls, label
            assert len(candidate.calls) == 1 and candidate.result.closed
            assert book.receipts == () and not book.observations and book.source_visits == 1
            witnessed.append({"component": label, "observation_visits": len(visits)})
        record_property("f4_parser_component_gates", json.dumps(witnessed, sort_keys=True))
        assert_same_state(before, whole_state(fixture.case))


def test_native_259_matcher_260_sentinel_and_separate_key_validation_components(
    request, tmp_path, monkeypatch, record_property, dialect
):
    with service_case(request, tmp_path, monkeypatch, record_property, dialect) as fixture:
        ids = add_roots(fixture, 255)
        publish_result(fixture, ids[-1])
        before = whole_state(fixture.case)
        captured = []
        original_query = sources.matching_successor_query

        def capture(connection, context, book, cohort):
            query, parameters = original_query(connection, context, book, cohort)
            compiled = query.compile(dialect=connection.dialect)
            assert len(compiled.params) <= 64
            assert query._limit_clause.value == 260
            receipts = tuple(book.receipts)
            assert len(receipts) == 259
            captured.append(
                (
                    context,
                    receipts,
                    {fixture.case.job_id: book.job_observation(fixture.case.job_id)},
                    dict(book.observations),
                    cohort,
                    query,
                    dict(parameters),
                    len(compiled.params),
                )
            )
            return query, parameters

        with monkeypatch.context() as patch:
            patch.setattr(sources, "matching_successor_query", capture)
            with observe_service(fixture, patch, record_property) as observed:
                result = fixture.service._read_successor(
                    fixture.principal, fixture.context, fixture.operation_id
                )
        assert result == expected_get(fixture, before, result_run_id=ids[-1])
        assert_service_released(observed)
        assert len(captured) == 1
        context, receipts, jobs, observations, cohort, query, parameters, binds = captured[0]
        rows = [SimpleNamespace(domain=row.domain, id=row.identity) for row in receipts]
        # Test only returned-key acceptance. Query construction/execution above
        # was native; these altered result lists are not claimed native rows.
        cases = [
            ("exact", rows, False),
            ("duplicate", rows + [rows[0]], True),
            ("missing", rows[1:], True),
            ("foreign", [SimpleNamespace(domain="run", id="f" * 32), *rows[1:]], True),
        ]
        visits = []
        for label, result_rows, refuses in cases:
            book = clone_book(receipts, jobs, observations)
            connection = ComponentConnection(dialect, result_rows)
            initial = book.encoded()

            def fixed_query(
                actual_connection,
                actual_context,
                actual_book,
                actual_cohort,
                *,
                _connection=connection,
                _book=book,
                _label=label,
            ):
                assert actual_connection is _connection and actual_context == context
                assert actual_book is _book and actual_cohort is cohort
                visits.append(_label)
                return query, parameters

            with monkeypatch.context() as patch:
                patch.setattr(sources, "matching_successor_query", fixed_query)
                if refuses:
                    with pytest.raises(AdmissionStorageError):
                        sources.verify_successor_snapshot(connection, context, book, cohort)
                else:
                    sources.verify_successor_snapshot(connection, context, book, cohort)
            assert len(connection.calls) == 1 and connection.result.closed
            assert book.encoded() == initial
        assert visits == ["exact", "duplicate", "missing", "foreign"]
        record_property(
            "f4_final_matcher_components",
            json.dumps(
                {
                    "native_identities": 259,
                    "compiled_sentinel": 260,
                    "compiled_binds": binds,
                    "python_result_controls": visits,
                },
                sort_keys=True,
            ),
        )
        assert_same_state(before, whole_state(fixture.case))


def test_single_successor_cancellation_phase_accepts_255_roots_without_effect(
    request, tmp_path, monkeypatch, record_property, dialect
):
    with service_case(request, tmp_path, monkeypatch, record_property, dialect) as fixture:
        ids = add_roots(fixture, 255)
        before = whole_state(fixture.case)
        work = OperationWork(include_acquisition=True)
        owner = SuccessorCancellationReceipts(work, fixture.context, fixture.operation_id)
        controls = []
        original_control = OperationWork.control_attempt

        def control(target, kind):
            count = target.statements
            try:
                return original_control(target, kind)
            finally:
                if target is work:
                    controls.append((kind, count, target.statements))

        started = time.monotonic()
        with monkeypatch.context() as patch:
            patch.setattr(OperationWork, "control_attempt", control)
            with owner.phase() as phase:
                with operation_connection(fixture.reader_engine, work) as connection:
                    if dialect == "postgresql":
                        assert connection.exec_driver_sql(
                            "SELECT "
                            "has_table_privilege(current_user,'job_failure_evidence','INSERT'),"
                            "has_column_privilege(current_user,'jobs','cancel','UPDATE'),"
                            "has_table_privilege(current_user,'audit','INSERT')"
                        ).one() == (False, False, False)
                    book = phase.book
                    _, operation = read_operation(
                        connection, fixture.context, fixture.operation_id, book
                    )
                    job = reads.read_successor_cancel_job(
                        connection, fixture.context, fixture.case.job_id, book
                    )
                    _, configuration = read_descriptor(
                        connection, fixture.context, fixture.case.job_id, "admission_config", book
                    )
                    phase.associate(connection, operation, job, configuration)
                    cohort = read_run_cohort(connection, fixture.context, job, book)
                    assert len(cohort.records) == 255 and set(cohort.ids) == set(ids)
                    assert len(book.receipts) == 258
                    association = phase._association
                    original_rows = [
                        [row.domain, row.identity, list(row.values)]
                        for row in (
                            association.operation,
                            association.job,
                            association.configuration,
                        )
                    ]
                    combined = canonical(
                        {
                            "original": original_rows,
                            "phase": json.loads(book.encoded()),
                        }
                    )
                    assert book.remaining == 4 * 1024**2 - len(combined)
                    query, parameters = sources._matching_successor_query(
                        connection, fixture.context, book, cohort, cancellation=True
                    )
                    assert len(query.compile(dialect=connection.dialect).params) <= 64
                    assert query._limit_clause.value == 259 and len(parameters) == 1
                    phase.verify(connection, cohort)
                assert connection.closed and work._started is None
            assert owner._active is None and not owner._failed
        elapsed = time.monotonic() - started
        cleanup = sum(
            after - before for kind, before, after in controls if kind not in {"begin", "commit"}
        )
        assert owner.source_visits == 256 and owner.edges == 510
        assert book._receipts == {} and book.observations == {} and book._active_frame == 0
        assert work._connection is None and work._raw is None and work._lease is None
        assert work._detached and not work._listeners and work._invocation_started is not None
        assert 0 < cleanup <= 8 and work.statements - cleanup <= 504
        assert work.statements <= 512 and work.instructions < 20_000_000 and elapsed < 10
        record_property(
            "f4_single_cancellation_phase",
            json.dumps(
                {
                    "scope": "one phase only; not a three-phase service",
                    "roots": 255,
                    "identities": 258,
                    "source_visits": owner.source_visits,
                    "edges": owner.edges,
                    "total_statements": work.statements,
                    "cleanup_statements": cleanup,
                    "elapsed_seconds": elapsed,
                    "combined_retained_bytes": len(combined),
                },
                sort_keys=True,
            ),
        )
        assert_same_state(before, whole_state(fixture.case))
