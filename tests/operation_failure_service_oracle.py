"""Independent native state and accounting observations for private F4 consumers."""

import hashlib
import json
import math
import re
import time
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from types import SimpleNamespace

from failure_consumer_oracle import select_reader
from ledger_restore_authority import typed
from reservation_postgres_fixture import _application_acl
from sqlalchemy import event, text
from test_admission_envelope import descriptor
from test_failure_persistence_native_oracle import (
    assert_only_completion_changed,
    assert_same_state,
    genuine_failure_case,
    genuine_terminal_event,
    native_clock,
    native_digest_inputs,
    observe_controls,
    whole_state,
)
from test_operation_sources import roots
from test_run_projection_postgres import drain as drain_postgres

from agent_rewind import operation_failure_cancellation, operation_failure_service
from agent_rewind.artifact_metadata import record_verified, register_ref
from agent_rewind.database import keys
from agent_rewind.failure_terminal import TerminalCoordinator
from agent_rewind.operation_service import OperationService
from agent_rewind.operation_work import OperationWork
from agent_rewind.request_authority import RequestAuthority
from agent_rewind.request_identity import VerifiedPrincipal
from agent_rewind.scoped_repositories import members, scopes


def canonical(value):
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def one(state, table, **identity):
    found = [
        row
        for row in state["tables"][table]["rows"]
        if all(row[key] == value for key, value in identity.items())
    ]
    assert len(found) == 1
    return found[0]


def complete_failure(case, monkeypatch, record_property):
    """Create real evidence through the retained registered dependency producer."""
    with monkeypatch.context() as patch:
        controls = observe_controls(patch)
        with genuine_terminal_event(case, controls, record_property) as issued:
            native_inputs = native_digest_inputs(case)
            coordinator = TerminalCoordinator(case.engine, case.authority)
            first = native_clock(case)
            created = coordinator.complete_failure(case.principal, case.context, issued.event)
            last = native_clock(case)
            assert created.kind == "created" and coordinator.outcome.commit_acknowledged
            assert not coordinator.outcome.cleanup_failed
            assert_only_completion_changed(
                case,
                issued.claimed,
                whole_state(case),
                created.original,
                native_inputs,
                (first, last),
            )
            return created.original


def service_key(case, engine):
    """One real key/membership/scope; no identity or authority-return substitution."""
    key_id = f"{120001:032x}"
    principal = VerifiedPrincipal.service_key(key_id)
    with case.case.engine.begin() as connection:
        connection.execute(
            keys.insert().values(
                id=key_id,
                hash="a" * 64,
                role="operator",
                name="synthetic-f4-key",
                expires=time.time() + 3600,
                revoked=False,
            )
        )
        connection.execute(
            scopes.insert().values(
                resource_kind="key",
                resource_id=key_id,
                project_id=case.project_id,
            )
        )
        connection.execute(
            members.insert().values(
                project_id=case.project_id,
                principal_id=principal.principal_id,
                role="operator",
                revoked_at=None,
                legacy_default=False,
            )
        )
    authority = RequestAuthority(engine)
    context = authority.named(principal, case.project_id, action="read").context
    return principal, context


@contextmanager
def cancellation_grants(case, reader):
    """Separate native action/lock grants; evidence remains SELECT-only for this reader."""
    if reader is None:
        yield
        return
    pg = case.pg
    commands = (
        ("UPDATE(id)", "projects"),
        ("UPDATE(id)", "organizations"),
        ("UPDATE(cancel,status)", "jobs"),
        ("UPDATE(revoked)", "api_keys"),
        ("UPDATE(revoked_at)", "project_memberships"),
        ("UPDATE(resource_id)", "resource_scopes"),
        ("UPDATE(kind)", "operations"),
        ("INSERT", "audit"),
    )
    with pg["owner"].connect() as connection:
        original = _application_acl(connection, reader.reader)
    primary = None
    try:
        with pg["owner"].begin() as connection:
            for privileges, table in commands:
                connection.exec_driver_sql(f"GRANT {privileges} ON {table} TO {reader.reader_sql}")
        drain_postgres(pg)
        with reader.engine.connect() as connection:
            rights = connection.exec_driver_sql(
                "SELECT has_table_privilege(current_user,'job_failure_evidence','SELECT'),"
                "has_table_privilege(current_user,'job_failure_evidence','INSERT'),"
                "has_column_privilege(current_user,'jobs','cancel','UPDATE'),"
                "has_table_privilege(current_user,'audit','INSERT')"
            ).one()
        assert tuple(rights) == (True, False, True, True)
        drain_postgres(pg)
        yield
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            reader.engine.dispose()
            drain_postgres(pg)
            with pg["owner"].begin() as connection:
                for privileges, table in reversed(commands):
                    connection.exec_driver_sql(
                        f"REVOKE {privileges} ON {table} FROM {reader.reader_sql}"
                    )
                assert _application_acl(connection, reader.reader) == original
            drain_postgres(pg)
        except BaseException:
            if primary is not None:
                primary.add_note("F4 cancellation grant restoration also failed.")
            else:
                raise


@contextmanager
def service_case(
    request,
    tmp_path,
    monkeypatch,
    record_property,
    dialect,
    *,
    failed=False,
    key=False,
    cancel=False,
):
    pg = request.getfixturevalue("pg") if dialect == "postgresql" else None
    template = request.getfixturevalue("fresh_sqlite_ar6_template") if pg is None else None
    with genuine_failure_case(
        tmp_path, monkeypatch, record_property, pg=pg, fresh_ar6_template=template
    ) as original:
        case = original.case
        failure = complete_failure(case, monkeypatch, record_property) if failed else None
        selected = (
            select_reader(case, producer=True, record_property=record_property)
            if pg is not None
            else nullcontext(None)
        )
        with selected as reader:
            engine = case.engine if reader is None else reader.engine
            principal, context = (
                service_key(case, engine) if key else (case.principal, case.context)
            )
            authority = RequestAuthority(engine)
            service = OperationService(engine, authority)
            fixture = SimpleNamespace(
                case=case,
                engine=case.case.engine,
                reader_engine=engine,
                pg=pg,
                reader=reader,
                principal=principal,
                context=context,
                service=service,
                failure=failure,
                operation_id=case.admission.accepted["operation_id"],
            )
            with cancellation_grants(case, reader) if cancel else nullcontext():
                yield fixture


def add_roots(fixture, count, *, start=10000, job=None, project=None, update=None):
    if count == 0:
        return []
    return roots(
        fixture,
        count,
        start=start,
        job=job or fixture.case.job_id,
        project=project or fixture.context.project_id,
        update=update,
    )


def publish_result(fixture, run_id, *, publish=True):
    body = canonical({"run_id": run_id})
    value = descriptor(body, object_id=f"{950000:032x}", project=fixture.context.project_id)
    with fixture.engine.begin() as connection:
        record_verified(connection, value)
        register_ref(
            connection,
            project_id=fixture.context.project_id,
            owner_kind="job",
            owner_id=fixture.case.job_id,
            role="result",
            artifact_id=value.id,
        )
        if publish:
            connection.execute(
                text("UPDATE jobs SET status='succeeded',result=:digest WHERE id=:job"),
                {"digest": value.digest, "job": fixture.case.job_id},
            )

    def load(observed):
        assert observed == value
        assert hashlib.sha256(body).hexdigest() == observed.digest
        return body

    fixture.service.artifact_loader = load
    return value


@contextmanager
def observe_service(fixture, monkeypatch, record_property):
    """Forward production methods; observe actual work without issuing extra SQL."""
    observed = SimpleNamespace(
        works=[],
        controls=[],
        connections=[],
        books=[],
        owners=[],
        wires=[],
        frames=[],
        sql=[],
        compiled_binds=[],
        history_calls=0,
        elapsed=None,
    )
    original_control = OperationWork.control_attempt
    original_work = operation_failure_service.OperationWork
    original_book = operation_failure_service.SuccessorReceiptBook
    original_owner = operation_failure_service.SuccessorCancellationReceipts
    original_history = operation_failure_service.validated_consumer_history

    def control(work, kind):
        before = work.statements
        try:
            return original_control(work, kind)
        finally:
            observed.controls.append((work, kind, before, work.statements))

    def work(*args, **kwargs):
        value = original_work(*args, **kwargs)
        observed.works.append(value)
        return value

    def book(*args, **kwargs):
        value = original_book(*args, **kwargs)
        observed.books.append(value)
        return value

    def owner(*args, **kwargs):
        value = original_owner(*args, **kwargs)
        observed.owners.append(value)
        return value

    def history(*args, **kwargs):
        observed.history_calls += 1
        return original_history(*args, **kwargs)

    def statement(_connection, _cursor, sql, _parameters, context, _many):
        observed.sql.append(sql)
        if context.compiled is not None:
            observed.compiled_binds.append(len(context.compiled.params or {}))

    def connected(connection):
        observed.connections.append(connection)

    def retained_bytes(value):
        if value._scope is None:
            return 0
        scope = value._scope
        association = scope._association or scope._owner._original
        original = (
            None
            if association is None
            else [
                [row.domain, row.identity, list(row.values)]
                for row in (association.operation, association.job, association.configuration)
            ]
        )
        independent = len(canonical(original))
        assert scope._association_bytes == independent
        return len(canonical({"original": None, "phase": None})) - 8 + independent

    original_encoded = original_book.encoded
    original_frame = original_book.frame

    def encoded(value):
        wire = original_encoded(value)
        observed.wires.append(
            {
                "bytes": len(wire),
                "counter": value.byte_count,
                "identities": len(value._receipts),
                "active_frame": value._active_frame,
                "combined_bytes": len(wire) + retained_bytes(value),
                "sha256": hashlib.sha256(wire).hexdigest(),
            }
        )
        return wire

    @contextmanager
    def frame(value, size):
        with original_frame(value, size):
            observed.frames.append(
                (size, value._wire_bytes + retained_bytes(value), value._active_frame)
            )
            yield

    with monkeypatch.context() as patch:
        patch.setattr(OperationWork, "control_attempt", control)
        patch.setattr(operation_failure_service, "OperationWork", work)
        patch.setattr(operation_failure_service, "SuccessorReceiptBook", book)
        patch.setattr(operation_failure_cancellation, "SuccessorReceiptBook", book)
        patch.setattr(operation_failure_service, "SuccessorCancellationReceipts", owner)
        patch.setattr(operation_failure_service, "validated_consumer_history", history)
        patch.setattr(original_book, "encoded", encoded)
        patch.setattr(original_book, "frame", frame)
        event.listen(fixture.reader_engine, "engine_connect", connected)
        event.listen(fixture.reader_engine, "before_cursor_execute", statement)
        started = time.monotonic()
        try:
            yield observed
        finally:
            observed.elapsed = time.monotonic() - started
            event.remove(fixture.reader_engine, "engine_connect", connected)
            event.remove(fixture.reader_engine, "before_cursor_execute", statement)
            record_property(
                "f4_complete_service_work",
                json.dumps(
                    {
                        "elapsed_seconds": observed.elapsed,
                        "works": [
                            {
                                "total": item.statements,
                                "vm": item.instructions,
                                "acquisition_clock": item._invocation_started is not None,
                                "cleanup": sum(
                                    after - before
                                    for work_, kind, before, after in observed.controls
                                    if work_ is item and kind not in {"begin", "commit"}
                                ),
                            }
                            for item in observed.works
                        ],
                        "history_calls": observed.history_calls,
                        "maximum_compiled_binds": max(observed.compiled_binds, default=0),
                        "wires": observed.wires,
                        "frames": observed.frames,
                    },
                    sort_keys=True,
                ),
            )


def assert_service_released(observed):
    assert len(observed.works) == 1 and observed.history_calls == 1
    work = observed.works[0]
    cleanup = sum(
        after - before
        for target, kind, before, after in observed.controls
        if target is work and kind not in {"begin", "commit"}
    )
    assert work._invocation_started is not None
    assert 0 < cleanup <= 8 and 0 < work.statements - cleanup <= 504
    assert work.statements <= 512 and work.instructions < 20_000_000
    assert observed.elapsed is not None and observed.elapsed < 10
    assert work._started is None and work._connection is None and work._raw is None
    assert work._detached and not work._listeners and work._lease is None
    assert all(connection.closed for connection in observed.connections)
    assert max(observed.compiled_binds, default=0) <= 64
    assert all(
        0 < row["bytes"] <= 4 * 1024 * 1024
        and row["combined_bytes"] <= 4 * 1024 * 1024
        and row["counter"] == row["bytes"]
        and row["active_frame"] == 0
        for row in observed.wires
    )
    assert all(
        0 < size <= 4096 and active == size and retained + active <= 4 * 1024 * 1024
        for size, retained, active in observed.frames
    )
    assert all(owner._active is None for owner in observed.owners)


def expected_get(fixture, before, *, result_run_id=None):
    job = one(before, "jobs", id=fixture.case.job_id)
    operation = one(before, "operations", id=fixture.operation_id)
    error = None
    if fixture.failure is not None:
        error = {
            "code": "outcome_uncertain",
            "message": "The operation outcome is not yet known; reconcile the original request.",
            "request_id": fixture.failure.record.correlation_id,
            "retryable": False,
        }
    return {
        "id": operation["id"],
        "project_id": operation["project_id"],
        "job_id": operation["job_id"],
        "client_operation_id": operation["client_operation_id"],
        "status": job["status"],
        "cancel_requested": bool(job["cancel"]),
        "result_run_id": result_run_id,
        "budget_microusd": job["budget"],
        "reserved_microusd": job["reserved"],
        "error": error,
    }


def assert_cancel_delta(fixture, before, after, clock_bounds):
    expected = deepcopy(before)
    job = one(expected, "jobs", id=fixture.case.job_id)
    job["cancel"] = True if fixture.pg is not None else 1
    if job["status"] == "queued":
        job["status"] = "cancelled"
    old_ids = {row["id"] for row in before["tables"]["audit"]["rows"]}
    additions = [row for row in after["tables"]["audit"]["rows"] if row["id"] not in old_ids]
    assert len(additions) == 1
    actual = additions[0]
    assert set(actual) == {"id", "created", "actor", "action", "target"}
    assert re.fullmatch(r"[0-9a-f]{32}", actual["id"])
    assert type(actual["created"]) is float and math.isfinite(actual["created"])
    assert clock_bounds[0] <= actual["created"] <= clock_bounds[1]
    assert (actual["actor"], actual["action"], actual["target"]) == (
        fixture.principal.principal_id,
        "job.cancel",
        fixture.case.job_id,
    )
    expected["tables"]["audit"]["rows"].append(actual)
    expected["tables"]["audit"]["rows"].sort(key=lambda row: repr(typed(row)))
    assert_same_state(expected, after)
