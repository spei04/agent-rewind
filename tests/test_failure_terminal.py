"""D3 byte grammar and genuine-event completion; no live worker activation."""

import hashlib
import json
import sqlite3
import sys
from contextlib import closing
from copy import deepcopy
from dataclasses import asdict
from datetime import UTC, datetime
from time import perf_counter

import pytest
from ledger_eligibility_fixture import rows
from sqlalchemy.engine import Connection
from test_failure_claim import (
    InstalledAdapter,
    different_configuration,
    intent,
)
from test_failure_claim import (
    failure_case as failure_case,
)

from agent_rewind import admission_request, failure_encoding
from agent_rewind import failure_persistence as persistence
from agent_rewind import failure_terminal as terminal
from agent_rewind.failure_evidence import CompletionEvent, FailureRefusal
from agent_rewind.failure_terminal import _TERMINALS, TerminalCoordinator
from agent_rewind.operation_reads import MAX_RECEIPT_BYTES
from agent_rewind.operation_work import OperationWork


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, '["n"]'),
        (False, '["b",0]'),
        (True, '["b",1]'),
        (1, '["i","1"]'),
        (1.0, '["f","0x1.0000000000000p+0"]'),
        (-0.0, '["f","0x0.0p+0"]'),
        (0.0, '["f","0x0.0p+0"]'),
        ("2026-10-06 00:00:00+00:00", '["s","2026-10-06 00:00:00+00:00"]'),
        ("é\n", '["s","\\u00e9\\n"]'),
    ],
)
def test_adopted_scalar_encoding_preserves_native_type_and_timestamp(value, expected):
    tagged = failure_encoding._tag(value)
    encoded = json.dumps(tagged, separators=(",", ":"), allow_nan=False).encode()
    assert encoded == expected.encode()


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), -float("inf"), 2**63, -(2**63) - 1, [], {}, object(), "\ud800"],
)
def test_frame_scalar_rejects_nonfinite_unbounded_or_foreign_values(value):
    with pytest.raises(FailureRefusal) as caught:
        failure_encoding._tag(value)
    assert caught.value.reason == "invalid_intent"


@pytest.mark.parametrize("ceiling", [37, 4096])
def test_active_frame_checks_shared_and_frame_caps_before_output_allocation(monkeypatch, ceiling):
    frame = ["x", "a" * (ceiling - 8)]
    expected = json.dumps(frame, separators=(",", ":")).encode()
    assert len(expected) == ceiling
    digest, measured = failure_encoding._digest(frame, remaining=ceiling)
    assert (digest, measured) == (hashlib.sha256(expected).hexdigest(), ceiling)
    original = admission_request.canonical
    allocations = []

    def observe(value):
        allocations.append(value)
        return original(value)

    monkeypatch.setattr(admission_request, "canonical", observe)
    with pytest.raises(FailureRefusal) as caught:
        failure_encoding._digest(frame, remaining=ceiling - 1)
    assert caught.value.reason == "capacity_exceeded" and allocations == []
    if ceiling == 4096:
        with pytest.raises(FailureRefusal) as caught:
            failure_encoding._digest(["x", "a" * (ceiling - 7)], remaining=MAX_RECEIPT_BYTES)
        assert caught.value.reason == "capacity_exceeded" and allocations == []


def _native_now(path):
    with closing(sqlite3.connect(path)) as connection:
        value = connection.execute("SELECT strftime('%Y-%m-%dT%H:%M:%fZ','now')").fetchone()[0]
    instant = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    return int(instant.timestamp() * 1_000_000)


def _terminal_delta(case, before, after, original):
    expected = deepcopy(before)
    jobs = expected["tables"]["jobs"]
    columns = jobs["columns"]
    job = next(row for row in rows(before, "jobs") if row["id"] == case.job_id)
    replacement = {**job, "status": original.record.job_status}
    jobs["rows"] = tuple(
        sorted(
            (
                tuple(replacement[name] for name in columns)
                if row[columns.index("id")] == case.job_id
                else row
                for row in jobs["rows"]
            ),
            key=repr,
        )
    )
    evidence = expected["tables"]["job_failure_evidence"]
    assert evidence["rows"] == ()
    evidence["rows"] = (tuple(asdict(original.record)[name] for name in evidence["columns"]),)
    assert after == expected


def test_genuine_dependency_completion_has_exact_atomic_delta_and_whole_work(
    request, monkeypatch, record_property
):
    case = request.getfixturevalue("failure_case")
    adapter = InstalledAdapter(different_configuration(), drift_at=4)
    owner = persistence._FailureExecutionOwner(case.engine, case.authority, adapter)
    coordinator = TerminalCoordinator(case.engine, case.authority)
    traces, sql, controls, frames = [], [], [], []
    claim_traces, claim_controls, accounting = [], [], []
    owner_state = persistence._OWNERS[owner]
    charge_before = OperationWork._charge
    control_before = OperationWork.control_attempt
    execute_before = Connection.execute
    driver_before = Connection.exec_driver_sql
    encode_before = failure_encoding.bounded_canonical
    persist_before = terminal.persist_verified_failure

    def charge(work):
        try:
            return charge_before(work)
        finally:
            if work is coordinator._work:
                traces.append((sys._getframe(1).f_code.co_name, work.statements))
            elif work is owner_state.coordinator._work:
                claim_traces.append((sys._getframe(1).f_code.co_name, work.statements))

    def control(work, kind):
        try:
            return control_before(work, kind)
        finally:
            if work is coordinator._work:
                controls.append((kind, work.statements))
            elif work is owner_state.coordinator._work:
                claim_controls.append((kind, work.statements))

    def execute(connection, statement, *args, **kwargs):
        if connection.engine is case.engine:
            sql.append(str(statement))
        return execute_before(connection, statement, *args, **kwargs)

    def driver(connection, statement, *args, **kwargs):
        if connection.engine is case.engine:
            sql.append(statement)
        return driver_before(connection, statement, *args, **kwargs)

    def encode(value, *args, **kwargs):
        encoded = encode_before(value, *args, **kwargs)
        frames.append((deepcopy(value), encoded))
        return encoded

    def persist(connection, token):
        result = persist_before(connection, token)
        state = terminal._TERMINALS[connection][1]
        state.audit()
        encoded_sizes = [len(book.encoded()) for book in state.books]
        assert len(encoded_sizes) == 2
        assert state.retained_bytes == state.detached_bytes + sum(encoded_sizes)
        assert state.source_visits == state.books[-1].source_visits
        assert state.source_visits >= state.books[0].source_visits > 0
        assert not state.frame_active and state.active_frame_bytes == 0
        assert 0 < state.detached_bytes < state.retained_bytes <= MAX_RECEIPT_BYTES
        observations = [book.observations for book in state.books]
        assert observations[0][("failure_count", case.job_id)] == (0,)
        assert observations[1][("failure_count", case.job_id)] == (1,)
        assert ("failure_cells", case.job_id) in observations[1]
        assert all(("result_count", case.job_id) in values for values in observations)
        assert all(("any_provider_call", case.job_id) in values for values in observations)
        accounting.append(
            {
                "retained_bytes": state.retained_bytes,
                "detached_bytes": state.detached_bytes,
                "book_encoded_bytes": encoded_sizes,
                "source_visits": state.source_visits,
                "edges": state.edges,
                "identities": len(state.identities),
                "active_frame_bytes": state.active_frame_bytes,
            }
        )
        return result

    elapsed = claim_elapsed = None
    monkeypatch.setattr(OperationWork, "_charge", charge)
    monkeypatch.setattr(OperationWork, "control_attempt", control)
    try:
        claim_started = perf_counter()
        try:
            fence = owner.claim(case.principal, case.context, intent(case))
        finally:
            claim_elapsed = perf_counter() - claim_started
        event = owner._check_installed_binding()
        assert type(event) is CompletionEvent
        assert adapter.reads == 4
        before = case.snapshot()
        start_tick = _native_now(case.case.path)
        monkeypatch.setattr(OperationWork, "_charge", charge)
        monkeypatch.setattr(OperationWork, "control_attempt", control)
        monkeypatch.setattr(Connection, "execute", execute)
        monkeypatch.setattr(Connection, "exec_driver_sql", driver)
        monkeypatch.setattr(failure_encoding, "bounded_canonical", encode)
        monkeypatch.setattr(terminal, "persist_verified_failure", persist)
        started = perf_counter()
        try:
            result = coordinator.complete_failure(case.principal, case.context, event)
        finally:
            elapsed = perf_counter() - started
        final_tick = _native_now(case.case.path)
        assert result.kind == "created" and result.original is coordinator.original
        original = result.original
        assert original.fence == fence and original.organization_id == case.organization_id
        assert original.record.cause == "dependency_failed"
        assert original.record.phase == "outcome_unknown" and original.record.job_status == "failed"
        assert start_tick <= original.record.created_at_micros <= final_tick
        assert coordinator.outcome.commit_acknowledged and not coordinator.outcome.cleanup_failed
        _terminal_delta(case, before, case.snapshot(), original)
        assert event not in persistence._EVENTS and not _TERMINALS
        assert case.engine.pool.checkedout() == 0
        assert coordinator._work.statements <= 512 and elapsed < 10
        assert sum(text.lstrip().startswith("UPDATE jobs") for text in sql) == 1
        assert (
            sum(text.lstrip().startswith("INSERT INTO job_failure_evidence") for text in sql) == 1
        )
        assert "strftime(" in sql[-1] and "'now'" in sql[-1]
        assert len(frames) == 3
        assert frames[0][0][:3] == ["ar-failure-association", 1, "sqlite"]
        assert frames[1][0][:3] == ["ar-failure-source", 2, "sqlite"]
        assert frames[1][1] == frames[2][1]
        assert hashlib.sha256(frames[0][1]).hexdigest() == original.record.association_sha256
        assert hashlib.sha256(frames[1][1]).hexdigest() == original.record.source_sha256
        terminal_fields = [name for name, _ in frames[1][0][4][1]]
        assert terminal_fields == [
            "id",
            "kind",
            "created",
            "payload",
            "status",
            "owner",
            "lease_until",
            "budget",
            "reserved",
            "result",
            "error",
            "actor",
            "payload_version",
            "execution_config_ref",
            "execution_config_digest",
        ]
        assert "cancel" not in terminal_fields
        assert [name for name, _ in frames[1][0][-1][1]] == [
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
            "created_at_micros",
        ]
        assert all(len(encoded) <= 4096 for _, encoded in frames)
        snapshot = case.snapshot()
        second = TerminalCoordinator(case.engine, case.authority)
        with pytest.raises(FailureRefusal) as caught:
            second.complete_failure(case.principal, case.context, event)
        assert caught.value.reason == "capability_not_issued"
        assert not second.outcome.begun and case.snapshot() == snapshot
        with pytest.raises(FailureRefusal) as caught:
            coordinator.complete_failure(case.principal, case.context, event)
        assert caught.value.reason == "invocation_reused"
    finally:
        record_property("whole_claim_seconds", claim_elapsed)
        record_property("claim_transaction_outcome", str(owner.outcome))
        if owner_state.coordinator._work is not None:
            record_property("claim_work_statements", owner_state.coordinator._work.statements)
            record_property(
                "claim_work_vm_instructions", owner_state.coordinator._work.instructions
            )
        record_property("claim_charge_trace", json.dumps(claim_traces))
        record_property("claim_control_trace", json.dumps(claim_controls))
        record_property("whole_completion_seconds", elapsed)
        record_property("transaction_outcome", str(coordinator.outcome))
        if coordinator._work is not None:
            record_property("work_statements", coordinator._work.statements)
            record_property("work_attached_seconds", coordinator._work.seconds)
            record_property("work_vm_instructions", coordinator._work.instructions)
        record_property("charge_trace", json.dumps(traces))
        record_property("control_trace", json.dumps(controls))
        record_property("sqlalchemy_statements", json.dumps(sql))
        record_property("frame_bytes", json.dumps([len(encoded) for _, encoded in frames]))
        record_property("receipt_accounting", json.dumps(accounting))
        owner.close()
