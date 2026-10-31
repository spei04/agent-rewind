"""Finite native F3 reconciliation, not F4 consumers or live startup proof.

The unchanged independent oracle supplies genuine admission/ledger/ar8 setup.
SQLite expiry/cancel/ACK readback originals remain separately source-qualified;
these new cases target PostgreSQL gaps plus both-dialect legacy and key authority.
"""

import hashlib
import json
import time
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, replace
from fractions import Fraction
from threading import Event
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection
from test_failure_persistence_native_oracle import (
    EVIDENCE,
    POSTGRES,
    DependencyAdapter,
    assert_no_canary,
    assert_only_claim_changed,
    assert_only_completion_changed,
    assert_same_state,
    assert_terminal_refusal_state,
    claim_intent,
    drain_case,
    execution_owner,
    expected_failure_hashes,
    genuine_failure_case,
    genuine_terminal_event,
    native_clock,
    native_digest_inputs,
    observe_controls,
    observe_terminal_writes,
    record_terminal_refusal_work,
    whole_state,
)
from test_failure_persistence_native_oracle import pg as pg

from agent_rewind import failure_persistence, failure_terminal
from agent_rewind.admission_transaction import AdmissionError
from agent_rewind.failure_evidence import Absent, CompletionEvent, Conflict, MatchingOriginal
from agent_rewind.request_authority import RequestAuthority
from agent_rewind.request_identity import VerifiedPrincipal
from agent_rewind.scoped_actions import ScopedActions
from agent_rewind.scoped_lineage import ResourceNotFound

__all__ = ["pg"]


def _job(case, state):
    (row,) = [row for row in state["tables"]["jobs"]["rows"] if row["id"] == case.job_id]
    return row


@contextmanager
def _sql(case, monkeypatch):
    """Forward exactly; do not change the owned engine's callback witnesses."""
    statements = []
    original_execute, original_driver = Connection.execute, Connection.exec_driver_sql

    def execute(connection, statement, *args, **kwargs):
        if connection.engine is case.engine:
            statements.append(str(statement))
        return original_execute(connection, statement, *args, **kwargs)

    def driver(connection, statement, *args, **kwargs):
        if connection.engine is case.engine:
            statements.append(statement)
        return original_driver(connection, statement, *args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(Connection, "execute", execute)
        scoped.setattr(Connection, "exec_driver_sql", driver)
        yield statements


def _work(coordinator, controls, elapsed, record_property, label):
    work = coordinator._work
    assert work is not None and work._invocation_started is not None
    cleanup = [item for item in controls if item[0] is work and item[1] not in {"begin", "commit"}]
    assert work._detached and not work._listeners and work._connection is None
    assert work.statements <= 512 and work.statements - len(cleanup) <= 504
    assert len(cleanup) <= 8 and elapsed < 10 and work.instructions < 20_000_000
    record_property(
        label,
        json.dumps(
            {
                "outcome": asdict(coordinator.outcome),
                "total_units": work.statements,
                "ordinary_units": work.statements - len(cleanup),
                "cleanup_units": len(cleanup),
                "whole_seconds": elapsed,
                "transaction_finish_seconds": work.seconds,
                "vm_instructions": work.instructions,
            },
            sort_keys=True,
        ),
    )


def _inspection(case, retained, controls, monkeypatch, record_property, label):
    before = whole_state(case)
    frozen = asdict(retained)
    coordinator = failure_terminal.TerminalCoordinator(case.engine, case.authority)
    with _sql(case, monkeypatch) as statements:
        started = time.monotonic()
        try:
            result = coordinator.inspect_original(case.principal, case.context, retained)
        finally:
            _work(coordinator, controls, time.monotonic() - started, record_property, label)
    assert coordinator.outcome.commit_acknowledged and not coordinator.outcome.cleanup_failed
    assert not any(
        statement.lstrip().split(None, 1)[0].upper() in {"UPDATE", "INSERT", "DELETE", "REPLACE"}
        for statement in statements
    )
    assert statements and (
        "clock_timestamp()" in statements[-1]
        if hasattr(case, "pg")
        else "strftime(" in statements[-1] and "'now'" in statements[-1]
    )
    assert_same_state(before, whole_state(case))
    assert asdict(retained) == frozen
    assert not failure_terminal._TERMINALS and case.engine.pool.checkedout() == 0
    record_property(label + "_last_sql", statements[-1])
    return result


def _complete(case, issued, controls, monkeypatch, record_property):
    before = whole_state(case)
    native_inputs = native_digest_inputs(case)
    coordinator = failure_terminal.TerminalCoordinator(case.engine, case.authority)
    first = native_clock(case)
    with _sql(case, monkeypatch) as statements:
        started = time.monotonic()
        try:
            result = coordinator.complete_failure(case.principal, case.context, issued.event)
        finally:
            _work(coordinator, controls, time.monotonic() - started, record_property, "completion")
    last = native_clock(case)
    assert coordinator.outcome.commit_acknowledged and not coordinator.outcome.cleanup_failed
    assert result.original is coordinator.original
    assert issued.event not in failure_persistence._EVENTS and issued.record.event is None
    assert_only_completion_changed(
        case, before, whole_state(case), result.original, native_inputs, (first, last)
    )
    assert (
        "clock_timestamp()" in statements[-1]
        if hasattr(case, "pg")
        else "strftime(" in statements[-1]
    )
    return result.original


@contextmanager
def _short_claim(case, controls, record_property, seconds):
    """Use a valid short lease; do not rewrite the persisted lease or native clock."""
    before = whole_state(case)
    intent = replace(claim_intent(case), lease_seconds=seconds)
    adapter = DependencyAdapter()
    with execution_owner(case, adapter) as (owner, record):
        first = native_clock(case)
        started = time.monotonic()
        try:
            fence = owner.claim(case.principal, case.context, intent)
        finally:
            _work(
                record.coordinator,
                controls,
                time.monotonic() - started,
                record_property,
                "short_claim",
            )
        last = native_clock(case)
        claimed = whole_state(case)
        assert_only_claim_changed(before, claimed, intent, (first, last))
        assert owner.outcome.commit_acknowledged and not owner.outcome.cleanup_failed
        lease = _job(case, claimed)["lease_until"]
        live = native_clock(case)
        assert Fraction(live) < Fraction(lease) * 1_000_000
        record_property(
            "initialized_native_live_lease",
            json.dumps({"clock_micros": live, "lease_hex": lease.hex()}),
        )
        yield SimpleNamespace(
            owner=owner, record=record, fence=fence, adapter=adapter, claimed=claimed
        )


def _event(issued):
    issued.adapter.unavailable = True
    event = issued.owner._check_installed_binding()
    assert type(event) is CompletionEvent and issued.record.event is event
    assert event in failure_persistence._EVENTS
    assert issued.adapter.phases == ["initial", "pre_mutation", "post_clean", "dependency"]
    assert issued.adapter.validate_calls == issued.adapter.send_calls == 0
    issued.event = event


def _wait_for_expiry(case, lease, record_property):
    started = time.monotonic()
    cadence = Event()
    while True:
        tick = native_clock(case)
        if Fraction(tick) >= Fraction(lease) * 1_000_000:
            break
        assert time.monotonic() - started < 4
        cadence.wait(0.01)  # Only the observed native clock, not this cadence, proves expiry.
    record_property(
        "native_expiry_observation",
        json.dumps(
            {
                "clock_micros": tick,
                "lease_hex": lease.hex(),
                "poll_seconds": time.monotonic() - started,
            }
        ),
    )
    return tick


def _set_cancel(case, value):
    """Native-valid fixture mutation only; not a successor F4 cancel-writer claim."""
    before = whole_state(case)
    engine = case.pg["owner"] if hasattr(case, "pg") else case.engine
    with engine.begin() as connection:
        result = connection.execute(
            text("UPDATE jobs SET cancel=:cancel WHERE id=:job"),
            {"cancel": value, "job": case.job_id},
        )
        assert result.rowcount == 1
    expected = deepcopy(before)
    _job(case, expected)["cancel"] = value if hasattr(case, "pg") else int(value)
    assert_same_state(expected, whole_state(case))


def _service_key(case, record_property):
    """Use actual key lifecycle SQL; this is not HTTP authentication or startup proof."""
    drain_case(case)
    engine = case.pg["owner"] if hasattr(case, "pg") else case.engine
    actions = ScopedActions(engine, RequestAuthority(engine))
    issued = actions.issue_key(case.principal, case.context, "operator", "F3 native fixture", 1)
    state = whole_state(case)
    (native,) = [row for row in state["tables"]["api_keys"]["rows"] if row["id"] == issued.id]
    assert native["hash"] == hashlib.sha256(issued.token.encode()).hexdigest()
    assert not native["revoked"] and native["expires"] > time.time()
    principal = VerifiedPrincipal.service_key(issued.id)
    assert any(
        row["resource_kind"] == "key"
        and row["resource_id"] == issued.id
        and row["project_id"] == case.project_id
        for row in state["tables"]["resource_scopes"]["rows"]
    )
    assert any(
        row["principal_id"] == principal.principal_id
        and row["project_id"] == case.project_id
        and row["role"] == "operator"
        and row["revoked_at"] is None
        for row in state["tables"]["project_memberships"]["rows"]
    )
    context = case.authority.named(principal, case.project_id, action="record").context
    record_property(
        "native_service_key",
        json.dumps(
            {
                "issued_by_actual_scoped_actions": True,
                "persisted_token_hash_scope_membership_verified": True,
                "http_authentication_claim": False,
            }
        ),
    )
    return replace(case, principal=principal, context=context), actions, issued.id


@POSTGRES
@pytest.mark.parametrize("cancel", [False, True], ids=["not_cancelled", "cancelled"])
def test_postgres_expiry_and_original_readback_keep_fixed_failed_status(
    pg, tmp_path, monkeypatch, record_property, cancel
):
    with genuine_failure_case(tmp_path, monkeypatch, record_property, pg=pg) as fixture:
        case = fixture.case
        controls = observe_controls(monkeypatch)
        with _short_claim(case, controls, record_property, 1) as issued:
            fence = issued.fence
            lease = _job(case, issued.claimed)["lease_until"]
        if cancel:
            _set_cancel(case, True)
        expired = _wait_for_expiry(case, lease, record_property)
        before = whole_state(case)
        native_inputs = native_digest_inputs(case)
        coordinator = failure_terminal.TerminalCoordinator(case.engine, case.authority)
        with _sql(case, monkeypatch) as statements:
            started = time.monotonic()
            try:
                created = coordinator.expire_generation(case.principal, case.context, fence)
            finally:
                _work(coordinator, controls, time.monotonic() - started, record_property, "expiry")
        original = created.original
        assert original is coordinator.original and original.fence == fence
        assert coordinator.outcome.commit_acknowledged and not coordinator.outcome.cleanup_failed
        assert (original.record.cause, original.record.job_status, original.record.phase) == (
            "lease_expired",
            "failed",
            "outcome_unknown",
        )
        assert expired <= original.record.created_at_micros <= native_clock(case)
        expected = deepcopy(before)
        _job(case, expected)["status"] = "failed"
        assert expected["tables"][EVIDENCE]["rows"] == []
        expected["tables"][EVIDENCE]["rows"] = [asdict(original.record)]
        after = whole_state(case)
        assert_same_state(expected, after)
        assert (
            original.record.association_sha256,
            original.record.source_sha256,
        ) == expected_failure_hashes(case, after, original.record, native_inputs)
        assert "clock_timestamp()" in statements[-1]
        matched = _inspection(
            case, original, controls, monkeypatch, record_property, "expired_original"
        )
        assert type(matched) is MatchingOriginal and matched.original is original
        record_property("native_cancel", cancel)


@POSTGRES
@pytest.mark.parametrize("mode", ["before_completion", "after_failed"])
def test_postgres_cancel_and_late_original_inspection_preserve_original_bytes(
    pg, tmp_path, monkeypatch, record_property, mode
):
    with genuine_failure_case(tmp_path, monkeypatch, record_property, pg=pg) as fixture:
        case = fixture.case
        controls = observe_controls(monkeypatch)
        with _short_claim(case, controls, record_property, 3) as issued:
            if mode == "before_completion":
                _set_cancel(case, True)
            _event(issued)
            original = _complete(case, issued, controls, monkeypatch, record_property)
            assert original.record.job_status == (
                "cancelled" if mode == "before_completion" else "failed"
            )
        if mode == "after_failed":
            _set_cancel(case, True)
        frozen = asdict(original)
        lease = _job(case, whole_state(case))["lease_until"]
        _wait_for_expiry(case, lease, record_property)
        matched = _inspection(
            case, original, controls, monkeypatch, record_property, "late_original"
        )
        assert type(matched) is MatchingOriginal and matched.original is original
        assert asdict(original) == frozen
        record_property("native_cancel_mode", mode)


@POSTGRES
@pytest.mark.parametrize("landed", [False, True], ids=["not_visible", "visible"])
def test_postgres_original_inspection_reconciles_uncertain_completion_without_retry(
    pg, tmp_path, monkeypatch, record_property, landed
):
    with genuine_failure_case(tmp_path, monkeypatch, record_property, pg=pg) as fixture:
        case = fixture.case
        controls = observe_controls(monkeypatch)
        with genuine_terminal_event(case, controls, record_property) as issued:
            native_inputs = native_digest_inputs(case)
            before = whole_state(case)
            coordinator = failure_terminal.TerminalCoordinator(case.engine, case.authority)
            original_commit = Connection.commit
            commits = []

            def lose_ack(connection):
                if connection.engine is case.engine:
                    commits.append(landed)
                    if landed:
                        original_commit(connection)
                    raise RuntimeError("F3 synthetic completion acknowledgment lost")
                return original_commit(connection)

            first = native_clock(case)
            with monkeypatch.context() as scoped:
                scoped.setattr(Connection, "commit", lose_ack)
                started = time.monotonic()
                try:
                    with pytest.raises(AdmissionError) as caught:
                        coordinator.complete_failure(case.principal, case.context, issued.event)
                finally:
                    _work(
                        coordinator,
                        controls,
                        time.monotonic() - started,
                        record_property,
                        "uncertain_completion",
                    )
            last = native_clock(case)
            assert commits == [landed] and caught.value.code == "outcome_uncertain"
            facts = coordinator.outcome
            assert facts.commit_attempted and not facts.commit_acknowledged
            assert facts.rollback_acknowledged and not facts.cleanup_failed
            original = coordinator.original
            assert original is not None and original.fence == issued.fence
            assert issued.event not in failure_persistence._EVENTS and issued.record.event is None
            if landed:
                assert_only_completion_changed(
                    case, before, whole_state(case), original, native_inputs, (first, last)
                )
            else:
                assert_same_state(before, whole_state(case))
                proposed = deepcopy(before)
                _job(case, proposed)["status"] = "failed"
                assert (
                    original.record.association_sha256,
                    original.record.source_sha256,
                ) == expected_failure_hashes(case, proposed, original.record, native_inputs)
            frozen = asdict(original)
            observed = _inspection(
                case, original, controls, monkeypatch, record_property, "uncertain_original"
            )
            assert type(observed) is (MatchingOriginal if landed else Absent)
            if landed:
                assert observed.original is original
            assert asdict(original) == frozen and coordinator.original is original
            settled = whole_state(case)
            other = failure_terminal.TerminalCoordinator(case.engine, case.authority)
            with pytest.raises(AdmissionError) as consumed:
                other.complete_failure(case.principal, case.context, issued.event)
            assert consumed.value.reason == "capability_not_issued"
            assert not any(asdict(other.outcome).values()) and other.original is None
            assert_same_state(settled, whole_state(case))
            record_property("physical_commit_landed", landed)


@pytest.mark.parametrize("dialect", ["sqlite", pytest.param("postgresql", marks=POSTGRES)])
def test_legacy_completion_original_and_conflict_preserve_native_history(
    request, tmp_path, monkeypatch, record_property, dialect
):
    native = request.getfixturevalue("pg") if dialect == "postgresql" else None
    with genuine_failure_case(
        tmp_path, monkeypatch, record_property, pg=native, legacy=True
    ) as fixture:
        case = fixture.case
        controls = observe_controls(monkeypatch)
        with genuine_terminal_event(case, controls, record_property) as issued:
            original = _complete(case, issued, controls, monkeypatch, record_property)
        matched = _inspection(
            case, original, controls, monkeypatch, record_property, "legacy_original"
        )
        assert type(matched) is MatchingOriginal and matched.original is original
        changed = replace(
            original,
            record=replace(
                original.record, created_at_micros=original.record.created_at_micros + 1
            ),
        )
        conflict = _inspection(
            case, changed, controls, monkeypatch, record_property, "legacy_conflict"
        )
        assert type(conflict) is Conflict
        assert original.record.created_at_micros != changed.record.created_at_micros
        assert whole_state(case)["legacy_ciphertexts"] == fixture.before["legacy_ciphertexts"]


@pytest.mark.parametrize("dialect", ["sqlite", pytest.param("postgresql", marks=POSTGRES)])
@pytest.mark.parametrize("revoked", [False, True], ids=["positive", "revoked_before_terminal"])
def test_service_key_completion_or_native_revocation_consumes_genuine_event(
    request, tmp_path, monkeypatch, record_property, dialect, revoked
):
    native = request.getfixturevalue("pg") if dialect == "postgresql" else None
    with genuine_failure_case(tmp_path, monkeypatch, record_property, pg=native) as fixture:
        original_case = fixture.case
        case, actions, key_id = _service_key(original_case, record_property)
        controls = observe_controls(monkeypatch)
        with genuine_terminal_event(case, controls, record_property) as issued:
            if not revoked:
                original = _complete(case, issued, controls, monkeypatch, record_property)
                matched = _inspection(
                    case, original, controls, monkeypatch, record_property, "key_original"
                )
                assert type(matched) is MatchingOriginal and matched.original is original
            else:
                drain_case(case)
                actions.revoke_key(original_case.principal, original_case.context, key_id)
                before = whole_state(case)
                (key,) = [
                    row for row in before["tables"]["api_keys"]["rows"] if row["id"] == key_id
                ]
                assert key["revoked"]
                assert all(
                    row["revoked_at"] is not None
                    for row in before["tables"]["project_memberships"]["rows"]
                    if row["principal_id"] == case.principal.principal_id
                )
                writes = observe_terminal_writes(monkeypatch, case)
                coordinator = failure_terminal.TerminalCoordinator(case.engine, case.authority)
                started = time.monotonic()
                try:
                    with pytest.raises(ResourceNotFound) as caught:
                        coordinator.complete_failure(case.principal, case.context, issued.event)
                finally:
                    elapsed = time.monotonic() - started
                    record_terminal_refusal_work(
                        coordinator,
                        controls,
                        elapsed,
                        record_property,
                        boundary="native_service_key_revoked_before_terminal",
                    )
                assert_terminal_refusal_state(
                    case, issued, coordinator, caught.value, before, writes
                )
                assert not coordinator.outcome.cleanup_failed
                assert_no_canary(caught.value, before)


@pytest.mark.parametrize("dialect", ["sqlite", pytest.param("postgresql", marks=POSTGRES)])
@pytest.mark.parametrize("scope", ["organization", "project"])
def test_terminal_wrong_scope_consumes_genuine_event_before_native_work(
    request, tmp_path, monkeypatch, record_property, dialect, scope
):
    native = request.getfixturevalue("pg") if dialect == "postgresql" else None
    with genuine_failure_case(tmp_path, monkeypatch, record_property, pg=native) as fixture:
        case = fixture.case
        controls = observe_controls(monkeypatch)
        with genuine_terminal_event(case, controls, record_property) as issued:
            before = whole_state(case)
            field = "organization_id" if scope == "organization" else "project_id"
            wrong = replace(case.context, **{field: "f" * 32})
            assert getattr(wrong, field) != getattr(case.context, field)
            writes = observe_terminal_writes(monkeypatch, case)
            coordinator = failure_terminal.TerminalCoordinator(case.engine, case.authority)
            started = time.monotonic()
            with pytest.raises(AdmissionError) as caught:
                coordinator.complete_failure(case.principal, wrong, issued.event)
            elapsed = time.monotonic() - started
            assert caught.value.code == "invalid_request"
            assert caught.value.reason == "capability_not_issued"
            assert not any(asdict(coordinator.outcome).values()) and coordinator.original is None
            assert coordinator._work.statements == 0 and elapsed < 10
            assert writes == [] and issued.event not in failure_persistence._EVENTS
            assert issued.record.event is None and not failure_terminal._TERMINALS
            assert_same_state(before, whole_state(case))
            other = failure_terminal.TerminalCoordinator(case.engine, case.authority)
            with pytest.raises(AdmissionError) as consumed:
                other.complete_failure(case.principal, case.context, issued.event)
            assert consumed.value.reason == "capability_not_issued"
            assert not any(asdict(other.outcome).values()) and other.original is None
            assert_same_state(before, whole_state(case))
            record_property(
                "wrong_scope_refusal",
                json.dumps(
                    {
                        "field": field,
                        "event_consumed": True,
                        "native_body_entered": False,
                        "charged_units": coordinator._work.statements,
                        "whole_seconds": elapsed,
                    }
                ),
            )
