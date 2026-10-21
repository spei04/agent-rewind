"""Actual operation HTTP adapters over synthetic ar6 SQLite and real credentials."""

import ast
import asyncio
import hashlib
import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient
from http_app_cleanup import http_application_cache_cleanup as http_application_cache_cleanup
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from test_admission_envelope import descriptor
from test_admission_request import at_task_size, submission
from test_admission_submit import admission_engine, publication

from agent_rewind.admission_coordinator import AdmissionCoordinator
from agent_rewind.admission_request import MAX_BODY_BYTES, MAX_TASK_BYTES
from agent_rewind.admission_transaction import AdmissionError
from agent_rewind.api import create_app
from agent_rewind.artifact_metadata import record_verified, register_ref
from agent_rewind.artifact_storage import LocalArtifactStorage
from agent_rewind.database import records
from agent_rewind.errors import Fault
from agent_rewind.migrations.compatibility import CompatibilityResult
from agent_rewind.models import canonical
from agent_rewind.request_identity import SessionIdentity, VerifiedPrincipal, encode_v2_session
from agent_rewind.scoped_lineage import ResourceNotFound
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
    assert value["retryable"] is (code in {"dependency_unavailable", "quota_exceeded"})
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


def test_no_new_work_default_and_synthetic_schema_refusal_are_separate(http_operation, settings):
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


@pytest.mark.parametrize(
    "variant",
    [
        "duplicate_top",
        "escaped_duplicate",
        "duplicate_file",
        "utf16",
        "utf32",
        "invalid_utf8",
        "float",
        "exponent",
        "boolean",
        "negative_seed",
        "huge_integer",
        "unknown",
        "legacy_budget",
        "path",
        "overlap",
        "surrogate",
    ],
)
def test_raw_body_parser_refuses_without_new_work(http_operation, variant):
    f = http_operation
    body = submission()
    if variant == "duplicate_top":
        raw = canonical(body).replace(b'"seed":0', b'"seed":0,"seed":0')
    elif variant == "escaped_duplicate":
        raw = canonical(body).replace(b'"seed":0', b'"seed":0,"se\\u0065d":0')
    elif variant == "duplicate_file":
        raw = canonical(body).replace(b'"main.py":""', b'"main.py":"","main.py":"private-canary"')
    elif variant in {"utf16", "utf32"}:
        raw = canonical(body).decode().encode("utf-16" if variant == "utf16" else "utf-32")
    elif variant == "invalid_utf8":
        raw = b"\xff"
    elif variant in {"float", "exponent", "boolean", "huge_integer"}:
        number = {
            "float": b"1.0",
            "exponent": b"1e0",
            "boolean": b"true",
            "huge_integer": b"123456789012345678901",
        }[variant]
        raw = canonical(body).replace(b'"seed":0', b'"seed":' + number)
    else:
        if variant == "negative_seed":
            body["seed"] = -1
        elif variant == "unknown":
            body["private-canary"] = True
        elif variant == "legacy_budget":
            body["task"]["budget_usd"] = 1
        elif variant == "path":
            body["task"]["files"] = {"../main.py": "private-canary"}
        elif variant == "overlap":
            body["task"]["evaluator_files"] = {"main.py": ""}
        else:
            body["task"]["files"]["main.py"] = "\ud800"
        raw = canonical(body)
    response = f.client.post(f.base + "/runs", headers=f.headers, content=raw)
    failed(response, 422, "invalid_request")
    assert "private-canary" not in response.text
    assert not f.f.policy.calls and not f.f.storage.calls
    with owned_connect(f.f.engine) as connection:
        assert connection.execute(text("SELECT count(*) FROM operations")).scalar_one() == 0


@pytest.mark.parametrize("size", [MAX_TASK_BYTES, MAX_TASK_BYTES + 1])
def test_materialized_task_boundary_reaches_real_encrypted_storage(http_operation, size):
    f = http_operation
    raw = canonical(at_task_size(size))
    assert MAX_TASK_BYTES < len(raw) < MAX_BODY_BYTES
    response = f.client.post(f.base + "/runs", content=raw, headers=f.headers)
    if size > MAX_TASK_BYTES:
        error = failed(response, 413, "invalid_request")
        assert error["message"] == "Canonical materialized task exceeds 8 MiB."
        assert not f.f.storage.calls and not f.f.policy.calls
    else:
        assert response.status_code == 202, response.text
        tasks = [value for value in f.f.storage.calls if value.byte_count == MAX_TASK_BYTES]
        assert len(tasks) == 1
        plaintext = f.f.storage.local.read_verified(tasks[0])
        assert len(plaintext) == size
        assert json.loads(plaintext)["files"]["main.py"]
        assert f.f.engine.pool.checkedout() == 0


@pytest.mark.parametrize("overflow", [False, True])
@pytest.mark.parametrize("declared_length", [None, "1"])
def test_actual_chunked_bytes_override_content_length_and_stop_at_limit(
    http_operation, overflow, declared_length
):
    f = http_operation
    raw = canonical(submission())
    chunks = [raw, b" " * (MAX_BODY_BYTES - len(raw))]
    if overflow:
        chunks += [b" ", b"must-not-be-consumed"]
    consumed = []

    async def content():
        for index, chunk in enumerate(chunks):
            consumed.append(index)
            yield chunk

    seen_headers = []

    async def observed_app(scope, receive, send):
        seen_headers.extend(scope["headers"])
        await f.app(scope, receive, send)

    async def request():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=observed_app), base_url="http://testserver"
        ) as client:
            return await client.post(
                f.base + "/runs",
                headers={
                    **f.headers,
                    **({"Content-Length": declared_length} if declared_length else {}),
                },
                content=content(),
            )

    response = asyncio.run(request())
    assert [value for key, value in seen_headers if key == b"content-length"] == (
        [b"1"] if declared_length else []
    )
    if overflow:
        error = failed(response, 413, "invalid_request")
        assert error["message"] == "Request body exceeds 9 MiB."
        assert consumed == [0, 1, 2]
        assert not f.f.policy.calls and not f.f.storage.calls
    else:
        assert response.status_code == 202, response.text
        assert consumed == [0, 1]


@pytest.mark.parametrize("key", ["AbCd:123", "Z" * 128])
@pytest.mark.parametrize("media", [' Application/JSON ; charset = "UTF-8" ', "application/json"])
def test_key_boundary_exact_hash_and_valid_media(http_operation, key, media):
    f = http_operation
    response = post(f, headers={**f.headers, "Idempotency-Key": key, "Content-Type": media})
    assert response.status_code == 202, response.text
    with owned_connect(f.f.engine) as connection:
        assert connection.execute(text("SELECT key_hash FROM operation_keys")).scalar_one() == (
            hashlib.sha256(key.encode("ascii")).hexdigest()
        )


def test_materialized_defaults_replay_but_source_whitespace_conflicts(http_operation):
    f = http_operation
    initial = post(f)
    assert initial.status_code == 202
    body = submission()
    body["task"].update(max_steps=30, command_timeout=30, redact_patterns=[])
    response = f.client.post(
        f.base + "/runs",
        headers=f.headers,
        content=json.dumps(body, indent=2).encode("utf-8"),
    )
    assert response.status_code == 202 and response.json() == initial.json()
    calls = len(f.f.storage.calls)
    body["task"]["files"]["main.py"] += " "
    failed(post(f, body), 409, "idempotency_conflict")
    assert len(f.f.storage.calls) == calls


@pytest.mark.parametrize("header", ["Authorization", "Origin", "X-Rewind-CSRF"])
def test_security_header_duplicates_precede_project_and_transport(http_operation, header):
    f = http_operation
    headers = list(f.headers.items())
    if header == "Authorization":
        headers += [(header, "Bearer invalid"), (header.lower(), "Bearer invalid")]
        status, code = 401, "unauthenticated"
    else:
        headers += [(header.lower(), f.headers[header])]
        status, code = 403, "forbidden"
    failed(f.client.post(f.base + "/runs", headers=headers, content=b"{"), status, code)
    assert not f.f.policy.calls and not f.f.storage.calls


@pytest.mark.parametrize("case", ["missing_csrf", "bad_csrf", "foreign_origin", "explicit_bearer"])
def test_existing_cookie_and_explicit_bearer_precedence(http_operation, case):
    f = http_operation
    headers = dict(f.headers)
    if case == "missing_csrf":
        del headers["X-Rewind-CSRF"]
    elif case == "bad_csrf":
        headers["X-Rewind-CSRF"] = "wrong"
    elif case == "foreign_origin":
        headers["Origin"] = "https://other.invalid"
    else:
        headers["Authorization"] = "Bearer invalid"
    expected = (401, "unauthenticated") if case == "explicit_bearer" else (403, "forbidden")
    failed(f.client.post(f.base + "/runs", headers=headers, content=b"{"), *expected)
    assert not f.f.policy.calls


def scoped_key(f, role="operator"):
    token = "http-synthetic-" + role
    key_id = f.app.state.db.issue_key(token, role, "HTTP fixture", time.time() + 3600, "fixture")
    with owned_begin(f.f.engine) as connection:
        connection.execute(
            text("INSERT INTO resource_scopes VALUES('key',:id,:p)"),
            {"id": key_id, "p": f.f.context.project_id},
        )
        connection.execute(
            text("INSERT INTO project_memberships VALUES(:p,:id,:role,NULL,false)"),
            {"p": f.f.context.project_id, "id": "api-key:" + key_id, "role": role},
        )
    return key_id, {
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "Idempotency-Key": KEY,
    }


def test_actual_key_submit_replay_and_current_membership_key_revocation(http_operation):
    f = http_operation
    key_id, headers = scoped_key(f)
    f.f.principal = VerifiedPrincipal.service_key(key_id)
    f.f.context = f.f.authority.named(f.f.principal, f.f.context.project_id).context
    response = post(f, headers=headers)
    assert response.status_code == 202, response.text
    path = f.base + "/operations/" + response.json()["operation_id"]
    assert f.client.get(path, headers=headers).status_code == 200
    assert post(f, headers=headers).json() == response.json()
    with owned_begin(f.f.engine) as connection:
        connection.execute(
            text("UPDATE project_memberships SET revoked_at='2026-01-01' WHERE principal_id=:p"),
            {"p": f.f.principal.principal_id},
        )
    failed(f.client.get(path, headers=headers), 404, "not_found")
    failed(post(f, headers=headers), 404, "not_found")
    with owned_begin(f.f.engine) as connection:
        connection.execute(text("UPDATE api_keys SET revoked=true WHERE id=:id"), {"id": key_id})
    failed(f.client.get(path, headers=headers), 401, "unauthenticated")


def test_actual_viewer_is_not_creator_or_canceller_and_target_precedes_action(http_operation):
    f = http_operation
    accepted = post(f).json()
    _key, headers = scoped_key(f, "viewer")
    path = f.base + "/operations/" + accepted["operation_id"]
    assert f.client.get(path, headers=headers).status_code == 200
    failed(f.client.post(path + "/cancel", headers=headers), 403, "forbidden")
    missing = f.base + "/operations/" + "0" * 32
    failed(f.client.post(missing + "/cancel", headers=headers), 404, "not_found")
    failed(post(f, headers=headers), 403, "forbidden")
    with owned_connect(f.f.engine) as connection:
        assert (
            connection.execute(
                text("SELECT cancel FROM jobs WHERE id=:id"), {"id": accepted["job_id"]}
            ).scalar_one()
            == 0
        )


@pytest.mark.parametrize(
    "code,status",
    [
        ("invalid_request", 422),
        ("idempotency_conflict", 409),
        ("dependency_unavailable", 503),
        ("schema_incompatible", 503),
        ("outcome_uncertain", 503),
    ],
)
def test_finite_coordinator_error_has_safe_shape_no_retry(
    http_operation, monkeypatch, code, status
):
    f = http_operation
    call = Mock(side_effect=AdmissionError(code))
    monkeypatch.setattr(f.app.state.operation_coordinator, "submit", call)
    response = post(f)
    failed(response, status, code)
    assert call.call_count == 1
    assert not f.f.policy.calls and not f.f.storage.calls


@pytest.mark.parametrize(
    "error,method,code,status",
    [
        (ValueError("private-canary"), "POST", "internal_error", 500),
        (RuntimeError("private-canary"), "GET", "internal_error", 500),
        (SQLAlchemyError("private-canary"), "POST", "outcome_uncertain", 503),
        (SQLAlchemyError("private-canary"), "GET", "dependency_unavailable", 503),
        (Fault("quota_exceeded"), "POST", "quota_exceeded", 429),
    ],
)
def test_unexpected_or_database_faults_keep_existing_boundary(
    http_operation, monkeypatch, capsys, error, method, code, status
):
    f = http_operation
    if method == "POST":
        monkeypatch.setattr(f.app.state.operation_coordinator, "submit", Mock(side_effect=error))
        response = post(f)
    else:
        monkeypatch.setattr(
            f.app.state.operation_service, "read_operation", Mock(side_effect=error)
        )
        response = f.client.get(f.base + "/operations/" + "a" * 32, headers=f.headers)
    failed(response, status, code)
    if status == 429:
        assert response.headers["retry-after"] == "5"
    assert "private-canary" not in response.text
    assert "private-canary" not in capsys.readouterr().err


@pytest.mark.parametrize("method,suffix", [("GET", ""), ("POST", "/cancel")])
def test_foreign_project_precedes_duplicate_encoding_and_malformed_target(
    http_operation, method, suffix
):
    f = http_operation
    path = f.base + "/operations/not-an-id" + suffix
    bad = [*f.headers.items(), ("Content-Encoding", "identity"), ("content-encoding", "gzip")]
    failed(f.client.request(method, path, headers=bad), 422, "invalid_request")
    foreign = path.replace(f.f.context.project_id, "0" * 32)
    failed(f.client.request(method, foreign, headers=bad), 404, "not_found")
    failed(f.client.request(method, path, headers=f.headers), 404, "not_found")
    missing_auth = [(key, value) for key, value in bad if key != "Cookie"]
    failed(f.client.request(method, foreign, headers=missing_auth), 401, "unauthenticated")


def test_populated_named_projects_are_disjoint_and_original_context_replay_is_stable(
    http_operation,
):
    f = http_operation
    first_context = f.f.context
    first = post(f).json()
    other = "8" * 32
    with owned_begin(f.f.engine) as connection:
        connection.execute(
            text(
                "INSERT INTO projects(id,organization_id,name,created_at,run_sequence) "
                "SELECT :id,organization_id,name,created_at,0 FROM projects WHERE id=:p"
            ),
            {"id": other, "p": first_context.project_id},
        )
        connection.execute(
            text("INSERT INTO project_memberships VALUES(:p,:id,'operator',NULL,true)"),
            {"p": other, "id": f.f.principal.principal_id},
        )
    f.f.context = f.f.authority.named(f.f.principal, other).context
    second_path = f.base.replace(first_context.project_id, other)
    second_response = f.client.post(
        second_path + "/runs", headers=f.headers, content=canonical(submission())
    )
    assert second_response.status_code == 202, second_response.text
    second = second_response.json()
    assert second != first
    for base, accepted, foreign in ((f.base, first, second), (second_path, second, first)):
        path = base + "/operations/"
        response = f.client.get(path + accepted["operation_id"], headers=f.headers)
        assert response.status_code == 200 and response.json()["job_id"] == accepted["job_id"]
        assert response.json()["project_id"] == base.rsplit("/", 1)[1]
        failed(f.client.get(path + foreign["operation_id"], headers=f.headers), 404, "not_found")
    f.f.context = first_context
    assert post(f).json() == first
    with owned_connect(f.f.engine) as connection:
        assert connection.execute(text("SELECT count(*) FROM operations")).scalar_one() == 2
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def publish_http_result(f, accepted):
    run_id = "d" * 32
    body = canonical({"run_id": run_id})
    value = descriptor(body, object_id="e" * 32, project=f.f.context.project_id)
    f.f.storage.local.put_verified(value, body)
    with owned_begin(f.f.engine) as connection:
        connection.execute(
            records.insert(),
            {
                "id": run_id,
                "kind": "run",
                "created": 1700000000.125,
                "data": {"job_id": accepted["job_id"], "parent_id": None, "success": True},
            },
        )
        connection.execute(
            text("INSERT INTO resource_scopes VALUES('run',:id,:project)"),
            {"id": run_id, "project": f.f.context.project_id},
        )
        record_verified(connection, value)
        register_ref(
            connection,
            project_id=f.f.context.project_id,
            owner_kind="job",
            owner_id=accepted["job_id"],
            role="result",
            artifact_id=value.id,
        )
        connection.execute(
            text(
                "UPDATE jobs SET status='succeeded',result=:digest,reserved=:reserved WHERE id=:id"
            ),
            {"digest": value.digest, "reserved": 2**53 + 1, "id": accepted["job_id"]},
        )
    return run_id, value


def test_verified_result_loader_outside_sql_exact_integers_and_final_receipt(
    http_operation, monkeypatch
):
    f = http_operation
    accepted = post(f).json()
    run_id, descriptor = publish_http_result(f, accepted)
    loader = f.app.state.operation_service.artifact_loader
    calls = []

    def load(value):
        assert f.f.engine.pool.checkedout() == 0
        assert value == descriptor
        calls.append(value)
        return loader(value)

    monkeypatch.setattr(f.app.state.operation_service, "artifact_loader", load)
    path = f.base + "/operations/" + accepted["operation_id"]
    response = f.client.get(path, headers=f.headers)
    assert response.status_code == 200, response.text
    assert response.json()["result_run_id"] == run_id and calls == [descriptor]
    assert response.json()["reserved_microusd"] == 2**53 + 1
    assert response.json()["error"] is None
    assert len(response.json()) == 10
    assert type(response.json()["reserved_microusd"]) is int

    def changed(value):
        data = load(value)
        with owned_begin(f.f.engine) as connection:
            connection.execute(
                text("DELETE FROM artifact_refs WHERE artifact_id=:id"), {"id": descriptor.id}
            )
        return data

    monkeypatch.setattr(f.app.state.operation_service, "artifact_loader", changed)
    failed(f.client.get(path, headers=f.headers), 503, "dependency_unavailable")
    assert len(calls) == 2


@pytest.mark.parametrize("revoke", [False, True])
def test_loader_secondary_not_found_rechecks_current_visibility(
    http_operation, monkeypatch, revoke
):
    f = http_operation
    accepted = post(f).json()
    publish_http_result(f, accepted)

    def missing(_value):
        assert f.f.engine.pool.checkedout() == 0
        if revoke:
            with owned_begin(f.f.engine) as connection:
                connection.execute(
                    text(
                        "UPDATE project_memberships SET revoked_at='2026-01-01' "
                        "WHERE principal_id=:id AND project_id=:p"
                    ),
                    {"id": f.f.principal.principal_id, "p": f.f.context.project_id},
                )
        raise ResourceNotFound()

    monkeypatch.setattr(f.app.state.operation_service, "artifact_loader", missing)
    response = f.client.get(f.base + "/operations/" + accepted["operation_id"], headers=f.headers)
    failed(response, 404 if revoke else 503, "not_found" if revoke else "dependency_unavailable")


@pytest.mark.parametrize(
    "status,error",
    [("failed", None), ("failed", "private-canary"), ("succeeded", "private-canary")],
)
def test_legacy_failure_refusal_does_not_block_terminal_cancellation(http_operation, status, error):
    f = http_operation
    accepted = post(f).json()
    with owned_begin(f.f.engine) as connection:
        connection.execute(
            text("UPDATE jobs SET status=:status,error=:error,reserved=9 WHERE id=:id"),
            {"status": status, "error": error, "id": accepted["job_id"]},
        )
    path = f.base + "/operations/" + accepted["operation_id"]
    response = f.client.get(path, headers=f.headers)
    failed(response, 503, "dependency_unavailable")
    assert "private-canary" not in response.text
    for _ in range(2):
        cancelled = f.client.post(path + "/cancel", headers=f.headers)
        assert cancelled.status_code == 202, cancelled.text
        assert cancelled.json() == {
            "operation_id": accepted["operation_id"],
            "cancel_requested": True,
            "status": status,
        }
    with owned_connect(f.f.engine) as connection:
        row = connection.execute(
            text("SELECT status,error,reserved,result FROM jobs WHERE id=:id"),
            {"id": accepted["job_id"]},
        ).one()
        assert tuple(row) == (status, error, 9, None)
        assert (
            connection.execute(
                text("SELECT count(*) FROM audit WHERE target=:id AND action='job.cancel'"),
                {"id": accepted["job_id"]},
            ).scalar_one()
            == 2
        )


def test_installed_http_smoke_helper_body(tmp_path, capsys):
    source = Path(__file__).parents[1] / "scripts/ci_smoke.py"
    module = ast.parse(source.read_text())
    helper = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "operation_http_smoke"
    )
    namespace = {"Path": Path}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), "ci_smoke.py", "exec"), namespace)
    namespace["operation_http_smoke"](tmp_path)
    assert "operation_http_installed_smoke_verified" in capsys.readouterr().out


@pytest.mark.parametrize(
    "variant",
    [
        "missing_key",
        "high_bit_key",
        "missing_media",
        "empty_charset",
        "extra_parameter",
        "query",
        "encoding_list",
    ],
)
def test_remaining_raw_transport_refusals_do_not_prepare_work(http_operation, variant):
    f = http_operation
    headers = [(name.lower().encode(), value.encode()) for name, value in f.headers.items()]
    path = f.base + "/runs"
    if variant == "missing_key":
        headers = [(name, value) for name, value in headers if name != b"idempotency-key"]
    elif variant == "high_bit_key":
        headers = [
            (name, b"\xff" * 8 if name == b"idempotency-key" else value) for name, value in headers
        ]
    elif variant == "missing_media":
        headers = [(name, value) for name, value in headers if name != b"content-type"]
    elif variant in {"empty_charset", "extra_parameter"}:
        media = (
            b"application/json;charset="
            if variant == "empty_charset"
            else b"application/json;boundary=unused"
        )
        headers = [(name, media if name == b"content-type" else value) for name, value in headers]
    elif variant == "query":
        path += "?client_operation_id=other"
    else:
        headers += [(b"content-encoding", b"identity,identity")]
    failed(
        f.client.post(path, headers=headers, content=canonical(submission())),
        422,
        "invalid_request",
    )
    assert not f.f.policy.calls and not f.f.storage.calls


def test_single_identity_encoding_accepts_case_and_optional_whitespace(http_operation):
    f = http_operation
    response = post(f, headers={**f.headers, "Content-Encoding": " \tIdEnTiTy\t "})
    assert response.status_code == 202, response.text


def test_completed_ar6_real_migration_only_guard_blocks_all_routes_and_sinks(
    settings, tmp_path, monkeypatch
):
    from agent_rewind.migrations.admission_service import initialize_admission
    from agent_rewind.migrations.artifact_service import initialize_artifacts
    from agent_rewind.migrations.compatibility import load_release_profile
    from agent_rewind.migrations.ownership_service import initialize_ownership
    from agent_rewind.migrations.projection_service import initialize_projection
    from agent_rewind.migrations.service import install

    settings.database_url = f"sqlite:///{tmp_path / 'real-guard.sqlite'}"
    settings.data_dir = tmp_path / "real-guard-data"
    settings.oidc_issuer = ISSUER
    app = create_app(settings)
    engine = app.state.db.engine
    project = "9" * 32
    principal = VerifiedPrincipal.oidc(ISSUER, SUBJECT)
    install(engine, "operation-http-guard")
    initialize_ownership(
        engine,
        {
            "schema_version": 1,
            "installation_key": "operation-http-guard",
            "organization_id": "8" * 32,
            "project_id": project,
            "project_name": "Guard",
            "principal_grants": [
                {
                    "principal_id": principal.principal_id,
                    "role": "maintainer",
                    "legacy_default": False,
                }
            ],
        },
    )
    initialize_artifacts(engine)
    initialize_projection(engine)
    initialize_admission(engine)
    profile = load_release_profile()

    def state():
        with owned_connect(engine) as connection:
            tables = (
                connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
                .scalars()
                .all()
            )
            return {
                name: connection.exec_driver_sql(f'SELECT * FROM "{name}"').all() for name in tables
            }

    original = state()
    guard = app.state.db.schema_compatibility()
    assert (guard.status, guard.code) == ("incompatible", "migration_only")
    forbidden = Mock(side_effect=AssertionError("real migration-only guard reached a sink"))
    for owner, names in [
        (app.state.auth, ("principal",)),
        (app.state.authority, ("named",)),
        (app.state.operation_coordinator, ("submit",)),
        (app.state.operation_service, ("read_operation", "cancel_operation", "artifact_loader")),
        (app.state.operation_service._actions, ("_cancel_effect",)),
        (app.state.readiness, ("check",)),
        (app.state.admission, ("require_available", "admit")),
    ]:
        for name in names:
            monkeypatch.setattr(owner, name, forbidden)
    token = encode_v2_session(
        app.state.auth.cipher, SessionIdentity(principal, ISSUER, SUBJECT, CSRF)
    )
    headers = {
        "Cookie": "rewind_session=" + token,
        "X-Rewind-CSRF": CSRF,
        "Origin": settings.public_url.rstrip("/"),
        "Content-Type": "application/json",
        "Idempotency-Key": KEY,
    }
    base = f"/api/v1/projects/{project}"
    paths = [
        ("POST", base + "/runs"),
        ("GET", base + "/operations/" + "0" * 32),
        ("POST", base + "/operations/" + "0" * 32 + "/cancel"),
    ]
    client = TestClient(app)
    try:
        for method, path in paths:
            failed(
                client.request(method, path, headers=headers, content=b"{"),
                503,
                "schema_incompatible",
            )
        forbidden.assert_not_called()
        after = app.state.db.schema_compatibility()
        assert (after.status, after.code) == ("incompatible", "migration_only")
        assert state() == original
        assert load_release_profile() == profile
        assert engine.pool.checkedout() == 0
    finally:
        client.close()
        engine.dispose()
