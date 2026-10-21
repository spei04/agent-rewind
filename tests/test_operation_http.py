"""Actual operation HTTP adapters over synthetic ar6 SQLite and real credentials."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from test_admission_request import submission
from test_admission_submit import admission_engine, publication

from agent_rewind.admission_coordinator import AdmissionCoordinator
from agent_rewind.api import create_app
from agent_rewind.artifact_storage import LocalArtifactStorage
from agent_rewind.migrations.compatibility import CompatibilityResult
from agent_rewind.models import canonical
from agent_rewind.request_identity import SessionIdentity, VerifiedPrincipal, encode_v2_session
from agent_rewind.sqlite_ownership import owned_begin, owned_connect

__all__ = ["admission_engine", "publication"]
ISSUER = "https://operation-http.invalid"
SUBJECT = "operation-http"
CSRF = "c" * 32
KEY = "http-Key:123"


@pytest.fixture
def http_operation(publication, settings, monkeypatch):
    f = publication
    settings.database_url = str(f.engine.url)
    settings.oidc_issuer = ISSUER
    app = create_app(settings)
    f.engine = app.state.db.engine
    f.principal = VerifiedPrincipal.oidc(ISSUER, SUBJECT)
    with owned_begin(f.engine) as connection:
        connection.execute(
            text("INSERT INTO project_memberships VALUES(:p,:id,'operator',NULL,false)"),
            {"p": f.context.project_id, "id": f.principal.principal_id},
        )
    f.authority = app.state.authority
    f.context = f.authority.named(f.principal, f.context.project_id).context
    f.storage.local = LocalArtifactStorage(
        settings.data_dir, app.state.auth.cipher, plaintext_limit=8 * 1024 * 1024
    )
    app.state.operation_coordinator = AdmissionCoordinator(
        f.engine,
        f.authority,
        policy=f.policy,
        registry=f.registry,
        readiness=f.ready,
        journal=f.journal,
        storage=f.storage,
    )
    for owner in (app.state.db, app.state.operation_coordinator, app.state.operation_service):
        monkeypatch.setattr(
            owner,
            "schema_compatibility",
            lambda: CompatibilityResult("ready", "synthetic_http_only"),
        )
    token = encode_v2_session(
        app.state.auth.cipher, SessionIdentity(f.principal, ISSUER, SUBJECT, CSRF)
    )
    headers = {
        "Cookie": "rewind_session=" + token,
        "X-Rewind-CSRF": CSRF,
        "Origin": settings.public_url.rstrip("/"),
        "Content-Type": "application/json",
        "Idempotency-Key": KEY,
    }
    client = TestClient(app)
    value = SimpleNamespace(
        f=f,
        app=app,
        client=client,
        headers=headers,
        base=f"/api/v1/projects/{f.context.project_id}",
    )
    try:
        yield value
    finally:
        client.close()
        assert f.engine.pool.checkedout() == 0
        f.engine.dispose()


def failed(response, status, code):
    assert response.status_code == status, response.text
    value = response.json()
    assert set(value) == {"code", "message", "request_id", "retryable"}
    assert value["code"] == code
    assert response.headers["x-request-id"] == value["request_id"]
    assert response.headers["cache-control"] == "no-store"
    assert len(value["request_id"]) == 32
    if status == 401:
        assert response.headers["www-authenticate"] == "Bearer"
    return value


def post(f, body=None, headers=None):
    return f.client.post(
        f.base + "/runs",
        content=canonical(submission() if body is None else body),
        headers=f.headers if headers is None else headers,
    )


def test_real_submit_get_cancel_and_replay_with_unavailable_dependencies(http_operation):
    f = http_operation
    response = post(f)
    assert response.status_code == 202, response.text
    accepted = response.json()
    assert set(accepted) == {"operation_id", "job_id"}
    origin = response.headers["x-request-id"]
    operation = f.base + "/operations/" + accepted["operation_id"]
    view = f.client.get(operation, headers=f.headers)
    assert view.status_code == 200, view.text
    assert view.json() == {
        "id": accepted["operation_id"],
        "project_id": f.f.context.project_id,
        "job_id": accepted["job_id"],
        "client_operation_id": submission()["client_operation_id"],
        "status": "queued",
        "cancel_requested": False,
        "result_run_id": None,
        "budget_microusd": 1,
        "reserved_microusd": 0,
        "error": None,
    }
    cancel = f.client.post(operation + "/cancel", headers=f.headers)
    assert cancel.status_code == 202, cancel.text
    assert cancel.json() == {
        "operation_id": accepted["operation_id"],
        "cancel_requested": True,
        "status": "cancelled",
    }
    # Default-unavailable coordinator still returns the original SQL winner.
    service = AdmissionCoordinator(f.f.engine, f.f.authority)
    service.schema_compatibility = lambda: CompatibilityResult("ready", "synthetic_http_only")
    f.app.state.operation_coordinator = service
    replay = post(f, headers={**f.headers, "X-Request-ID": "attacker"})
    assert replay.status_code == 202 and replay.json() == accepted
    assert replay.headers["x-request-id"] not in {origin, "attacker"}
    with owned_connect(f.f.engine) as connection:
        assert connection.execute(text("SELECT count(*) FROM operations")).scalar_one() == 1
        assert (
            connection.execute(text("SELECT failure_correlation_id FROM operations")).scalar_one()
            == origin
        )
        assert (
            connection.execute(text("SELECT key_hash FROM operation_keys")).scalar_one()
            == hashlib.sha256(KEY.encode("ascii")).hexdigest()
        )


@pytest.mark.parametrize(
    "header,value",
    [
        ("Idempotency-Key", ""),
        ("Idempotency-Key", " short"),
        ("Idempotency-Key", "x" * 129),
        ("Idempotency-Key", "key,another"),
        ("Content-Type", "text/plain"),
        ("Content-Type", "application/json; charset=utf-16"),
        ("Content-Encoding", "gzip"),
    ],
)
def test_submit_transport_after_auth_and_project_visibility(http_operation, header, value):
    f = http_operation
    bad = {**f.headers, header: value}
    failed(post(f, headers=bad), 422, "invalid_request")
    anonymous = {name: val for name, val in bad.items() if name != "Cookie"}
    failed(post(f, headers=anonymous), 401, "unauthenticated")
    path = f.base.replace(f.f.context.project_id, "0" * 32) + "/runs"
    failed(f.client.post(path, headers=bad, content=b"{"), 404, "not_found")
    assert not f.f.policy.calls and not f.f.storage.calls


@pytest.mark.parametrize("header", ["Idempotency-Key", "Content-Type", "Content-Encoding"])
def test_duplicate_headers_are_not_collapsed(http_operation, header):
    f = http_operation
    values = list(f.headers.items())
    if header == "Content-Encoding":
        values += [(header, "identity"), (header.lower(), "identity")]
    else:
        values += [(header.lower(), f.headers[header])]
    failed(post(f, headers=values), 422, "invalid_request")
    assert not f.f.policy.calls


@pytest.mark.parametrize("method,suffix", [("GET", ""), ("POST", "/cancel")])
def test_unused_inputs_cannot_change_service_arguments_and_encoding_precedes_effect(
    http_operation, method, suffix
):
    f = http_operation
    accepted = post(f).json()
    path = f.base + "/operations/" + accepted["operation_id"] + suffix
    failed(
        f.client.request(
            method, path, headers={**f.headers, "Content-Encoding": "gzip"}, content=b"ignored"
        ),
        422,
        "invalid_request",
    )
    with owned_connect(f.f.engine) as connection:
        assert (
            connection.execute(
                text("SELECT cancel FROM jobs WHERE id=:id"), {"id": accepted["job_id"]}
            ).scalar_one()
            == 0
        )
    response = f.client.request(
        method,
        path + "?job_id=other&status=failed&job_id=again",
        headers=f.headers,
        content=b'{"operation_id":"other","status":"failed"}',
    )
    assert response.status_code == (200 if method == "GET" else 202), response.text
    value = response.json()
    assert value.get("id", value.get("operation_id")) == accepted["operation_id"]
    assert value["status"] == ("queued" if method == "GET" else "cancelled")


def test_no_new_work_default_and_real_schema_guard_are_separate(http_operation, settings):
    f = http_operation
    default = AdmissionCoordinator(f.f.engine, f.f.authority)
    default.schema_compatibility = lambda: CompatibilityResult("ready", "synthetic_http_only")
    f.app.state.operation_coordinator = default
    failed(post(f), 503, "dependency_unavailable")
    assert not f.f.policy.calls and not f.f.storage.calls
    guarded = create_app(settings)
    denied = Mock(side_effect=AssertionError("real guard reached a route"))
    guarded.state.auth.principal = denied
    guarded.state.operation_coordinator.submit = denied
    guarded.state.operation_service.cancel_operation = denied
    try:
        client = TestClient(guarded)
        response = client.post(f.base + "/runs", content=b"{}", headers=f.headers)
        failed(response, 503, "schema_incompatible")
        denied.assert_not_called()
    finally:
        client.close()
        guarded.state.db.engine.dispose()


def test_frozen_metadata_for_only_three_operations(http_operation):
    f = http_operation
    generated = f.app.openapi()
    frozen = json.loads(
        (Path(__file__).parents[1] / "contracts/proposals/m1.openapi.json").read_text()
    )

    def resolved(value, document):
        if isinstance(value, list):
            return [resolved(item, document) for item in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            current = document
            for part in value["$ref"].split("/")[1:]:
                current = current[part]
            return resolved(current, document)
        return {
            key: sorted(item)
            if key in {"enum", "required"} and isinstance(item, list)
            else resolved(item, document)
            for key, item in value.items()
            if key not in {"title", "description", "summary"}
        }

    paths = [
        ("/api/v1/projects/{project_id}/runs", "post"),
        ("/api/v1/projects/{project_id}/operations/{operation_id}", "get"),
        ("/api/v1/projects/{project_id}/operations/{operation_id}/cancel", "post"),
    ]
    for path, method in paths:
        actual = generated["paths"][path][method]
        expected = frozen["paths"][path][method]
        assert actual["operationId"] == expected["operationId"]
        assert actual["security"] == frozen["security"]
        assert set(actual["responses"]) == set(expected["responses"])
        for status in actual["responses"]:
            assert resolved(actual["responses"][status], generated) == resolved(
                expected["responses"][status], frozen
            )
        assert resolved(actual.get("requestBody"), generated) == resolved(
            expected.get("requestBody"), frozen
        )
        parameters = expected.get("parameters", []) + frozen["paths"][path]["parameters"]

        def by_name(values):
            return {
                (item["name"], item["in"]): resolved({"required": False, **item}, generated)
                for item in values
            }

        assert by_name(actual["parameters"]) == by_name(parameters)
