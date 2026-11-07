"""Fresh successor authority and post-commit uncertainty on native state."""

import json
import time
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict

import pytest
import test_migrations_postgres as migration_tests
from failure_postgres_fixture import pg
from operation_failure_service_oracle import (
    assert_cancel_delta,
    assert_service_released,
    observe_service,
    one,
    service_case,
)
from sqlalchemy import text
from sqlalchemy.engine import Connection
from test_failure_persistence_native_oracle import assert_same_state, whole_state

from agent_rewind import operation_failure_service
from agent_rewind.errors import Fault
from agent_rewind.scoped_lineage import ResourceNotFound

__all__ = ["pg"]


@pytest.fixture(
    params=[
        "sqlite",
        pytest.param(
            "postgresql",
            marks=(
                pytest.mark.f4_owned_postgres,
                pytest.mark.skipif(
                    not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL F4 authority"
                ),
            ),
        ),
    ]
)
def dialect(request):
    return request.param


def change_key(fixture, change):
    """An owner changes only the actual current key; no authority result is replaced."""
    key_id = fixture.principal.principal_id.removeprefix("api-key:")
    assert len(key_id) == 32
    with fixture.engine.begin() as connection:
        if change == "revoked":
            changed = connection.execute(
                text("UPDATE api_keys SET revoked=:value WHERE id=:id"),
                {"value": True, "id": key_id},
            )
        else:
            assert change == "expired"
            changed = connection.execute(
                text("UPDATE api_keys SET expires=1 WHERE id=:id"), {"id": key_id}
            )
        assert changed.rowcount == 1
    return key_id


def expected_key_change(fixture, original, key_id, change):
    expected = deepcopy(original)
    key = one(expected, "api_keys", id=key_id)
    if change == "revoked":
        key["revoked"] = True if fixture.pg is not None else 1
    else:
        key["expires"] = 1.0
    return expected


@pytest.mark.parametrize("change", ["revoked", "expired"])
@pytest.mark.parametrize(
    "boundary",
    [
        "get_after_release",
        "cancel_before_mutation",
        "cancel_after_ack",
    ],
)
def test_successor_rechecks_actual_key_after_release_without_disclosing_or_repeating_effect(
    request, tmp_path, monkeypatch, record_property, dialect, change, boundary
):
    cancelling = boundary != "get_after_release"
    with service_case(
        request, tmp_path, monkeypatch, record_property, dialect, key=True, cancel=cancelling
    ) as fixture:
        before = whole_state(fixture.case)
        changes = []
        observed_ref = []
        transaction_facts = []
        original_transaction = operation_failure_service.admission_transaction

        @contextmanager
        def transaction(engine, outcome, **kwargs):
            try:
                with original_transaction(engine, outcome, **kwargs) as connection:
                    yield connection
            finally:
                transaction_facts.append(asdict(outcome))

        def mutate_key():
            observed = observed_ref[0]
            assert all(connection.closed for connection in observed.connections)
            assert observed.works[0]._connection is None
            assert len(changes) == 0
            if boundary == "cancel_after_ack":
                assert len(transaction_facts) == 1
                assert transaction_facts[0]["commit_acknowledged"]
                assert not transaction_facts[0]["cleanup_failed"]
            original = whole_state(fixture.case)
            key_id = change_key(fixture, change)
            changes.append((original, key_id))

        monkeypatch.setattr(operation_failure_service, "admission_transaction", transaction)
        if boundary == "get_after_release":
            original_load = fixture.service._load_result

            def load(*args, **kwargs):
                value = original_load(*args, **kwargs)
                mutate_key()
                return value

            monkeypatch.setattr(fixture.service, "_load_result", load)
        else:
            method = (
                "_cancel_mutate" if boundary == "cancel_before_mutation" else "_cancel_disclose"
            )
            original_phase = getattr(operation_failure_service._SuccessorService, method)

            def phase(service, *args, **kwargs):
                assert service.engine is fixture.reader_engine
                mutate_key()
                return original_phase(service, *args, **kwargs)

            monkeypatch.setattr(operation_failure_service._SuccessorService, method, phase)
        first = time.time()
        with observe_service(fixture, monkeypatch, record_property) as observed:
            observed_ref.append(observed)
            with pytest.raises(ResourceNotFound):
                entry = (
                    fixture.service._cancel_successor
                    if cancelling
                    else fixture.service._read_successor
                )
                entry(fixture.principal, fixture.context, fixture.operation_id)
        last = time.time()
        assert len(changes) == 1
        at_change, key_id = changes[0]
        if boundary == "cancel_after_ack":
            assert_cancel_delta(fixture, before, at_change, (first, last))
            assert sum(facts["commit_acknowledged"] for facts in transaction_facts) == 1
        else:
            assert_same_state(before, at_change)
            assert not any(facts["commit_attempted"] for facts in transaction_facts)
        assert_same_state(
            expected_key_change(fixture, at_change, key_id, change), whole_state(fixture.case)
        )
        assert_service_released(observed)
        record_property(
            "f4_successor_fresh_key",
            json.dumps(
                {
                    "boundary": boundary,
                    "change": change,
                    "transaction_facts": transaction_facts,
                    "typed_denial": "ResourceNotFound",
                    "single_mutation": True,
                },
                sort_keys=True,
            ),
        )


@pytest.mark.parametrize(
    "failure",
    [
        "before_native_commit",
        "after_native_commit_before_ack",
        "after_ack_close",
    ],
)
def test_successor_cancel_commit_uncertainty_preserves_actual_effect_and_never_retries(
    request, tmp_path, monkeypatch, record_property, dialect, failure
):
    with service_case(
        request, tmp_path, monkeypatch, record_property, dialect, cancel=True
    ) as fixture:
        before = whole_state(fixture.case)
        original_commit, original_close = Connection.commit, Connection.close
        original_transaction = operation_failure_service.admission_transaction
        attempts, native_commits, close_failures, transaction_facts = [], [], [], []
        canary = "synthetic private F4 commit fault"

        def commit(connection):
            if connection.engine is not fixture.reader_engine:
                return original_commit(connection)
            attempts.append(connection)
            assert len(attempts) == 1
            if failure == "before_native_commit":
                raise RuntimeError(canary)
            result = original_commit(connection)
            native_commits.append(connection)
            if failure == "after_native_commit_before_ack":
                raise RuntimeError(canary)
            return result

        def close(connection):
            if failure == "after_ack_close" and connection in native_commits and not close_failures:
                close_failures.append(connection)
                raise RuntimeError(canary)
            return original_close(connection)

        @contextmanager
        def transaction(engine, outcome, **kwargs):
            try:
                with original_transaction(engine, outcome, **kwargs) as connection:
                    yield connection
            finally:
                transaction_facts.append(asdict(outcome))

        monkeypatch.setattr(Connection, "commit", commit)
        monkeypatch.setattr(Connection, "close", close)
        monkeypatch.setattr(operation_failure_service, "admission_transaction", transaction)
        first = time.time()
        with (
            observe_service(fixture, monkeypatch, record_property) as observed,
            pytest.raises(Fault) as caught,
        ):
            fixture.service._cancel_successor(
                fixture.principal, fixture.context, fixture.operation_id
            )
        last = time.time()
        assert caught.value.code == "outcome_uncertain"
        assert canary not in str(caught.value)
        assert caught.value.__cause__ is None and caught.value.__suppress_context__
        assert len(attempts) == len(transaction_facts) == 1
        facts = transaction_facts[0]
        assert facts["begun"] and facts["commit_attempted"]
        assert facts["commit_acknowledged"] is (failure == "after_ack_close")
        assert len(native_commits) == int(failure != "before_native_commit")
        assert len(close_failures) == int(failure == "after_ack_close")
        if failure == "before_native_commit":
            assert facts["rollback_acknowledged"]
            assert_same_state(before, whole_state(fixture.case))
        else:
            assert_cancel_delta(fixture, before, whole_state(fixture.case), (first, last))
        if failure == "after_ack_close":
            assert facts["cleanup_failed"]
        assert_service_released(observed)
        record_property(
            "f4_successor_commit_uncertainty",
            json.dumps(
                {
                    "failure": failure,
                    "transaction_facts": facts,
                    "native_commits": len(native_commits),
                    "commit_attempts": len(attempts),
                    "returned_error": caught.value.code,
                },
                sort_keys=True,
            ),
        )
