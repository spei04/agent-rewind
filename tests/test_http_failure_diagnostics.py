"""Original-call, safe-output and retained-primary controls for the HTTP witness."""

import json
import sqlite3
from types import FunctionType

import http_failure_diagnostics
import pytest
from http_app_cleanup import http_application_cache_cleanup as http_application_cache_cleanup
from http_failure_diagnostics import MAX_BYTES, MAX_EXCEPTIONS, first_get_failure
from sqlalchemy.exc import OperationalError
from test_admission_transaction import engine
from test_operation_http import admission_engine, http_operation, publication

from agent_rewind import errors
from agent_rewind.admission_transaction import AdmissionError
from agent_rewind.operation_work import OperationWork, operation_connection
from agent_rewind.scoped_repositories import RepositoryUnavailable

__all__ = ["engine", "admission_engine", "http_operation", "publication"]


def test_witness_preserves_original_classifier_calls_and_restores_on_exit(monkeypatch, capsys):
    original = errors.classified
    error = RuntimeError("private-canary")
    scope = {"method": "GET"}
    calls = []

    def classify(actual_scope, actual_error):
        calls.append((actual_scope, actual_error))
        return original(actual_scope, actual_error)

    monkeypatch.setattr(errors, "classified", classify)
    interruption = KeyboardInterrupt()
    with (
        pytest.raises(KeyboardInterrupt) as caught,
        first_get_failure(monkeypatch) as report,
    ):
        assert errors.classified(scope, error) == "internal_error"
        assert json.loads(report())["classified"][0]["exceptions"][0]["type"] == "RuntimeError"
        raise interruption
    assert caught.value is interruption
    assert errors.classified is classify
    assert calls == [(scope, error)]
    assert capsys.readouterr() == ("", "")
    errors.classified(scope, error)
    assert len(calls) == 2  # Later requests no longer enter the witness.

    def observer_failure(_error):
        raise ValueError("private-observer-canary")

    monkeypatch.setattr(http_failure_diagnostics, "exception_evidence", observer_failure)
    with first_get_failure(monkeypatch) as report:
        assert errors.classified(scope, error) == "internal_error"
        assert json.loads(report())["classified"][0]["diagnostic_unavailable"]
    assert calls == [(scope, error)] * 3

    def classifier_failure(_scope, _error):
        raise interruption

    monkeypatch.setattr(errors, "classified", classifier_failure)
    with (
        pytest.raises(KeyboardInterrupt) as caught,
        first_get_failure(monkeypatch) as report,
    ):
        errors.classified(scope, error)
    assert caught.value is interruption and errors.classified is classifier_failure
    assert json.loads(report())["classified"] == []


def test_witness_bounds_and_redacts_sql_exception_payloads_and_cycles(monkeypatch):
    secret = "private-canary"
    database = OperationalError(secret, {"secret": secret}, RuntimeError(secret))
    unknown_type = type(secret, (RuntimeError,), {})
    root = unknown_type(secret)
    root.code = secret
    root.__cause__ = database
    previous = database
    for _ in range(30):
        following = RuntimeError(secret)
        previous.__context__ = following
        previous = following
    previous.__context__ = root

    def raise_root():
        raise root

    spoofed = FunctionType(
        raise_root.__code__.replace(co_filename=secret, co_name=secret),
        globals(),
        closure=raise_root.__closure__,
    )
    with pytest.raises(unknown_type) as caught:
        spoofed()
    assert caught.value is root
    with first_get_failure(monkeypatch) as report:
        assert errors.classified({"method": "GET", "path": secret}, root) == "internal_error"
        encoded = report()
    assert secret not in encoded and len(encoded.encode()) <= MAX_BYTES
    evidence = json.loads(encoded)["classified"][0]
    assert len(evidence["exceptions"]) == MAX_EXCEPTIONS and evidence["truncated"]
    assert evidence["exceptions"][0]["type"] == "OtherException"
    assert any(item["type"] == "OperationalError" for item in evidence["exceptions"])


def test_witness_observes_pre_service_named_authority_failure(http_operation, monkeypatch):
    original_error = RepositoryUnavailable()
    original_error.args = ("private-canary",)
    calls = []

    def unavailable(*args, **kwargs):
        calls.append((args, kwargs))
        raise original_error

    monkeypatch.setattr(http_operation.f.authority, "named", unavailable)
    with first_get_failure(monkeypatch) as report:
        response = http_operation.client.get(
            http_operation.base + "/operations/" + "a" * 32, headers=http_operation.headers
        )
        encoded = report()
    assert response.status_code == 503 and response.json()["code"] == "dependency_unavailable"
    assert len(calls) == 1 and "private-canary" not in encoded
    evidence = json.loads(encoded)["classified"][0]
    assert evidence["exceptions"][0]["type"] == "RepositoryUnavailable"
    assert any(
        frame["file"] == "operation_http.py" and frame["function"] == "named"
        for item in evidence["exceptions"]
        for frame in item["frames"]
    )


def test_witness_retains_real_connection_primary_and_cleanup_without_payloads(engine, monkeypatch):
    original_error = sqlite3.OperationalError("private-sql-and-parameters")
    work = OperationWork()
    with first_get_failure(monkeypatch) as report:
        try:
            with operation_connection(engine, work):
                raise original_error
        except AdmissionError as outward:
            assert outward is not original_error
            assert errors.classified({"method": "GET"}, outward) == "internal_error"
        else:
            pytest.fail("Expected the original connection refusal")
        encoded = report()
    evidence = json.loads(encoded)["classified"][0]
    phases = [
        frame
        for item in evidence["exceptions"]
        for frame in item["frames"]
        if frame["file"] == "operation_work.py" and frame["function"] == "operation_connection"
    ]
    assert phases and phases[0]["primary"]["type"] == "SQLiteOperationalError"
    assert phases[0]["phase"]["setup_ok"] and not phases[0]["phase"]["cleanup_failed"]
    assert phases[0]["work"]["statements"] == work.statements
    assert any(item["relation"] == "retained_primary" for item in evidence["exceptions"])
    assert "private-sql-and-parameters" not in encoded
    assert engine.pool.checkedout() == 0
