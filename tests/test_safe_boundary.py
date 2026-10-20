import io
import json
import re

import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from agent_rewind import errors
from agent_rewind.api import create_app
from agent_rewind.database import Database
from agent_rewind.errors import RULES, Fault
from agent_rewind.migrations.compatibility import CompatibilityResult
from agent_rewind.readiness import Readiness

CANARY = "private-source-token-sql-provider-body-DO-NOT-EMIT"


@pytest.fixture(autouse=True)
def diagnostic_output(monkeypatch):
    output = io.StringIO()
    monkeypatch.setattr(errors._diagnostic_handler, "stream", output)
    return output


@pytest.fixture
def boundary_app(settings, monkeypatch):
    # Synthetic supported-schema behavior only. No packaged profile is replaced.
    monkeypatch.setattr(
        Database,
        "schema_compatibility",
        lambda self: CompatibilityResult("ready", "test_only", "synthetic-install"),
    )
    monkeypatch.setattr(Readiness, "start", lambda self: None)
    app = create_app(settings)
    app.state.db.migrate(installation_key="synthetic-install")
    return app


@pytest.mark.parametrize("kind", ["value", "key", "nested", "malformed", "validation", "http"])
@pytest.mark.parametrize("prefix", ["/api/v1/", "/api/"])
def test_secret_exceptions_never_echo_or_log(boundary_app, caplog, diagnostic_output, kind, prefix):
    class Malformed(Exception):
        def __str__(self):
            raise AssertionError("exception string must never be evaluated")

    @boundary_app.get(prefix + "fault")
    def fault():
        if kind == "validation":
            raise RequestValidationError(
                [{"loc": ["body", CANARY], "msg": CANARY, "type": CANARY, "input": CANARY}]
            )
        if kind == "http":
            raise HTTPException(401, {"secret": CANARY}, headers={"private": CANARY})
        if kind == "nested":
            raise ExceptionGroup(CANARY, [ValueError(CANARY)])
        if kind == "malformed":
            raise Malformed(CANARY)
        if kind == "key":
            raise KeyError(CANARY)
        raise ValueError(CANARY)

    with TestClient(boundary_app) as client:
        response = client.get(prefix + "fault", headers={"X-Request-ID": CANARY})
        assert response.status_code == (
            422 if kind == "validation" else 401 if kind == "http" else 500
        )
        request_id = response.headers["X-Request-ID"]
        assert re.fullmatch("[0-9a-f]{32}", request_id)
        assert response.headers["Cache-Control"] == "no-store"
        assert CANARY not in response.text + str(response.headers)
        if prefix == "/api/v1/":
            assert set(response.json()) == {"code", "message", "request_id", "retryable"}
            assert response.json()["request_id"] == request_id
        else:
            assert set(response.json()) == {"detail"}
        if kind == "http":
            assert response.headers["WWW-Authenticate"] == "Bearer"
        else:
            records = [json.loads(line) for line in diagnostic_output.getvalue().splitlines()]
            if response.status_code == 500:
                assert records and records[-1]["request_id"] == request_id
                assert set(records[-1]) == {"event", "request_id", "error_code"}
        assert CANARY not in caplog.text + diagnostic_output.getvalue()
        assert client.get("/livez").headers["X-Request-ID"] != request_id


@pytest.mark.parametrize("code", list(RULES))
def test_known_faults_follow_frozen_envelope(boundary_app, code):
    @boundary_app.get("/api/v1/known")
    def known():
        raise Fault(code)

    with TestClient(boundary_app) as client:
        response = client.get("/api/v1/known")
    status, message, retryable = RULES[code]
    assert response.status_code == status
    assert response.json() == {
        "code": code,
        "message": message,
        "retryable": retryable,
        "request_id": response.headers["X-Request-ID"],
    }
    if code == "quota_exceeded":
        assert 1 <= int(response.headers["Retry-After"]) <= 60


def test_body_limit_boundary_and_validation_dynamic_keys(boundary_app, settings):
    with TestClient(boundary_app) as client:
        response = client.post(
            "/api/runs",
            content=b"x" * (9 * 1024 * 1024 + 1),
            headers={"X-Request-ID": CANARY},
        )
        assert response.status_code == 413
        assert response.json() == {"detail": "Request body exceeds 9 MiB."}
        assert re.fullmatch("[0-9a-f]{32}", response.headers["X-Request-ID"])
        assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    "method,code", [("GET", "dependency_unavailable"), ("POST", "outcome_uncertain")]
)
def test_database_mutation_unknown_outcome_is_not_retryable(boundary_app, method, code):
    @boundary_app.api_route("/api/v1/database", methods=["GET", "POST"])
    def database():
        raise OperationalError(CANARY, {"secret": CANARY}, RuntimeError(CANARY))

    with TestClient(boundary_app) as client:
        response = client.request(method, "/api/v1/database")
    assert response.status_code == 503
    assert response.json()["code"] == code
    assert response.json()["retryable"] is (method == "GET")
    assert CANARY not in response.text


def test_outage_gate_auth_before_probe_and_before_upload(boundary_app, settings, monkeypatch, task):
    probes = []

    async def unavailable():
        probes.append(True)
        return "dependency_unavailable"

    monkeypatch.setattr(boundary_app.state.readiness, "check", unavailable)
    monkeypatch.setattr(
        boundary_app.state.artifacts,
        "put_json",
        lambda value: pytest.fail("Upload occurred before successful readiness"),
    )
    admin = {"Authorization": "Bearer " + settings.bootstrap_key.get_secret_value()}
    db = boundary_app.state.db
    key = db.issue_key("viewer-token", "viewer", "synthetic-viewer", 9999999999, "test")
    job = db.enqueue("run", "0" * 64, 1, "test")
    with TestClient(boundary_app) as client:
        assert client.post("/api/runs", json=task.model_dump()).status_code == 401
        assert (
            client.post(
                "/api/runs",
                json=task.model_dump(),
                headers={"Authorization": "Bearer viewer-token"},
            ).status_code
            == 403
        )
        assert not probes
        for path in ("/api/runs", "/api/branches", "/api/studies", "/api/investigations"):
            response = client.post(path, json=task.model_dump(), headers=admin)
            assert response.status_code == 503
        assert len(probes) == 4
        assert len(db.list_jobs()) == 1
        assert client.post(f"/api/jobs/{job}/cancel", headers=admin).status_code == 200
        assert client.delete(f"/api/keys/{key}", headers=admin).status_code == 200
        assert client.post("/auth/logout", headers=admin).status_code == 200
        assert len(probes) == 4
        assert client.get("/livez").json() == {"status": "live"}
        assert client.get("/healthz").json() == {"status": "ok"}
        response = client.get("/readyz")
        assert response.status_code == 503
        assert response.json()["code"] == "dependency_unavailable"


def test_ready_is_not_authorization_or_schema_bypass(boundary_app, monkeypatch):
    async def ready():
        return "ready"

    monkeypatch.setattr(boundary_app.state.readiness, "check", ready)
    with TestClient(boundary_app) as client:
        assert client.get("/readyz").json() == {"status": "ready"}
        assert client.get("/api/runs").status_code == 401
        monkeypatch.setattr(
            boundary_app.state.db,
            "schema_compatibility",
            lambda: CompatibilityResult("incompatible", "migration_only"),
        )
        assert client.post("/api/runs", json={}).status_code == 503


def test_malformed_validation_exception_does_not_call_errors(boundary_app):
    @boundary_app.get("/api/v1/malformed")
    def malformed():
        error = RequestValidationError([])
        error.errors = lambda: (_ for _ in ()).throw(ValueError(CANARY))
        raise error

    with TestClient(boundary_app) as client:
        response = client.get("/api/v1/malformed")
    assert response.status_code == 422
    assert CANARY not in json.dumps(response.json())


def test_invalid_workspace_path_is_safe_client_error_before_reads(
    boundary_app, settings, monkeypatch
):
    monkeypatch.setattr(
        "agent_rewind.api.read_events",
        lambda *args: pytest.fail("Invalid path reached customer event reads"),
    )
    with TestClient(boundary_app) as client:
        response = client.get(
            "/api/runs/synthetic/files/1",
            params={"path": "../private-source"},
            headers={"Authorization": "Bearer " + settings.bootstrap_key.get_secret_value()},
        )
    assert response.status_code == 422
    assert "private-source" not in response.text


@pytest.mark.parametrize("started", [False, True])
@pytest.mark.parametrize("failure", ["logger", "stream"])
def test_logging_sink_failure_cannot_escape_before_or_after_headers(
    monkeypatch, capsys, started, failure
):
    import asyncio
    import logging

    from agent_rewind.errors import SafeBoundary

    def broken_sink(*args, **kwargs):
        raise RuntimeError(CANARY)

    monkeypatch.setattr(logging, "raiseExceptions", True)
    if failure == "logger":
        monkeypatch.setattr(errors._diagnostic_logger, "error", broken_sink)
    else:

        class BrokenStream:
            def write(self, value):
                raise RuntimeError(CANARY)

            def flush(self):
                raise RuntimeError(CANARY)

        monkeypatch.setattr(errors._diagnostic_handler, "stream", BrokenStream())

    async def exercise():
        messages = []

        async def app(scope, receive, send):
            if started:
                await send({"type": "http.response.start", "status": 200, "headers": []})
            raise ValueError(CANARY)

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(message):
            messages.append(message)

        await SafeBoundary(app)(
            {"type": "http", "path": "/api/v1/fault", "method": "GET"}, receive, send
        )
        assert messages[0]["status"] == (200 if started else 500)
        headers = dict(messages[0]["headers"])
        assert re.fullmatch(b"[0-9a-f]{32}", headers[b"x-request-id"])
        if not started:
            assert json.loads(messages[-1]["body"])["code"] == "internal_error"
        assert CANARY not in repr(messages)

    asyncio.run(exercise())
    captured = capsys.readouterr()
    assert CANARY not in captured.out + captured.err
    assert "--- Logging error ---" not in captured.err


def test_default_log_message_contains_safe_correlation(boundary_app, caplog, diagnostic_output):
    @boundary_app.get("/api/v1/log-fault")
    def fault():
        raise ValueError(CANARY)

    with TestClient(boundary_app) as client:
        response = client.get("/api/v1/log-fault")
    emitted = diagnostic_output.getvalue().strip()
    assert not any(record.name == "agent_rewind.safe" for record in caplog.records)
    assert json.loads(emitted) == {
        "event": "request_failed",
        "error_code": "internal_error",
        "request_id": response.headers["X-Request-ID"],
    }
    assert len(emitted) < 160 and CANARY not in emitted


@pytest.mark.parametrize(
    "path", ["/api/runs/missing/files/1", "/api/compare?left=missing&right=missing"]
)
def test_requested_missing_run_is_404(boundary_app, settings, path):
    with TestClient(boundary_app) as client:
        response = client.get(
            path, headers={"Authorization": "Bearer " + settings.bootstrap_key.get_secret_value()}
        )
    assert response.status_code == 404
    assert response.json() == {"detail": "Resource not found."}


@pytest.mark.parametrize(
    "path", ["/api/runs/present/files/1", "/api/compare?left=present&right=present"]
)
def test_internal_missing_evidence_field_remains_500(boundary_app, settings, monkeypatch, path):
    # Requested records exist; a malformed nested event is an internal data error.
    monkeypatch.setattr(boundary_app.state.db, "get", lambda *args: {})
    monkeypatch.setattr("agent_rewind.api.read_events", lambda *args: [{}])
    monkeypatch.setattr("agent_rewind.compare.read_events", lambda *args: [{}])
    with TestClient(boundary_app) as client:
        response = client.get(
            path, headers={"Authorization": "Bearer " + settings.bootstrap_key.get_secret_value()}
        )
    assert response.status_code == 500
    assert response.json() == {"detail": "The request could not be completed."}


def test_global_logger_handlers_cannot_receive_or_reformat_diagnostic(
    boundary_app, monkeypatch, diagnostic_output
):
    import logging

    class ForbiddenHandler(logging.Handler):
        def emit(self, record):
            pytest.fail("Safe diagnostic reached global handlers")

    handler = ForbiddenHandler()
    monkeypatch.setattr(logging.getLogger(), "handlers", [handler])
    monkeypatch.setattr(logging.getLogger("agent_rewind.safe"), "handlers", [handler])

    @boundary_app.get("/api/v1/isolated-log")
    def fault():
        raise ValueError(CANARY)

    with TestClient(boundary_app) as client:
        response = client.get("/api/v1/isolated-log")
    assert response.status_code == 500
    assert (
        json.loads(diagnostic_output.getvalue())["request_id"] == response.headers["X-Request-ID"]
    )
