"""Two HTTP reads over actual frozen projection history and real credentials."""

import base64
import json
import re
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import test_run_projection_backfill as projection_tests
from fastapi.testclient import TestClient
from http_app_cleanup import http_application_cache_cleanup as http_application_cache_cleanup
from http_failure_diagnostics import route_failure
from pydantic import SecretStr
from route_fixture import CSRF, ISSUER, PRINCIPAL, PROJECT
from sqlalchemy import text
from test_scoped_run_listing import RUN1, RUN2
from test_scoped_run_listing_bounds import add_runs

from agent_rewind import api
from agent_rewind.api import create_app
from agent_rewind.migrations.compatibility import CompatibilityResult, runtime_schema_compatibility
from agent_rewind.migrations.projection_service import backfill_run_index, initialize_projection
from agent_rewind.request_identity import SessionIdentity, VerifiedPrincipal, encode_v2_session
from agent_rewind.sqlite_ownership import owned_connect

legacy = projection_tests.legacy
OTHER = "8" * 32
BASE = "/api/v1/projects/" + PROJECT + "/runs"
FIELDS = {"id", "project_id", "created_at", "status", "branchable", "parent_id", "event_head"}


@pytest.fixture
def http_listing(legacy, settings, monkeypatch):
    path, engine, source = legacy
    initialize_projection(engine)
    backfill_run_index(engine, source)
    settings.database_url = f"sqlite:///{path}"
    settings.data_dir = path.parent
    settings.oidc_issuer = ISSUER
    settings.cursor_signing_key = SecretStr(
        base64.urlsafe_b64encode(b"k" * 32).decode().rstrip("=")
    )
    app = create_app(settings)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO projects(id,organization_id,name,created_at,run_sequence) "
                "SELECT :id,organization_id,'Other project',created_at,0 FROM projects WHERE id=:p"
            ),
            {"id": OTHER, "p": PROJECT},
        )
        for project in (PROJECT, OTHER):
            connection.execute(
                text("INSERT INTO project_memberships VALUES(:p,:id,'viewer',NULL,false)"),
                {"p": project, "id": PRINCIPAL.principal_id},
            )
    # This per-app test substitution exercises preparatory routes. The real
    # migration-only result is separately asserted below; no release flag exists.
    monkeypatch.setattr(
        app.state.db,
        "schema_compatibility",
        lambda: CompatibilityResult("ready", "synthetic_route_test"),
    )
    client = TestClient(app)  # No readiness subprocess/lifespan is needed for SQL-only routes.
    try:
        yield app, client, engine
    finally:
        client.close()
        app.state.db.engine.dispose()


def headers(app, principal=PRINCIPAL, subject="route-human"):
    token = encode_v2_session(
        app.state.auth.cipher, SessionIdentity(principal, ISSUER, subject, CSRF)
    )
    return {"Cookie": "rewind_session=" + token}


def error(response, status, code):
    assert response.status_code == status, response.text
    value = response.json()
    assert set(value) == {"code", "message", "request_id", "retryable"}
    assert value["code"] == code
    assert re.fullmatch("[0-9a-f]{32}", value["request_id"])
    assert response.headers["x-request-id"] == value["request_id"]
    assert response.headers["cache-control"] == "no-store"
    if status == 401:
        assert response.headers["www-authenticate"] == "Bearer"
    return value["request_id"]


@pytest.mark.parametrize("default", [None, OTHER])
def test_named_viewer_with_no_or_other_default_and_exact_shapes(http_listing, default):
    app, client, engine = http_listing
    if default:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE project_memberships SET legacy_default=true "
                    "WHERE project_id=:p AND principal_id=:id"
                ),
                {"p": default, "id": PRINCIPAL.principal_id},
            )
    response = client.get(BASE, headers=headers(app))
    assert response.status_code == 200
    page = response.json()
    assert set(page) == {"items", "next_cursor"} and page["next_cursor"] is None
    assert [item["id"] for item in page["items"]] == [RUN2, RUN1]
    for item in page["items"]:
        assert set(item) == FIELDS
        assert item["project_id"] == PROJECT and item["status"] == "complete"
        assert item["created_at"] == "2023-11-14T22:13:20.125000+00:00"
        assert client.get(BASE + "/" + item["id"], headers=headers(app)).json() == item
    assert page["items"][1]["parent_id"] is None
    other = client.get(f"/api/v1/projects/{OTHER}/runs", headers=headers(app))
    assert other.json() == {"items": [], "next_cursor": None}
    error(
        client.get(f"/api/v1/projects/{OTHER}/runs/{RUN1}", headers=headers(app)), 404, "not_found"
    )
    error(client.get(BASE + "/" + "0" * 32, headers=headers(app)), 404, "not_found")


@pytest.mark.parametrize(
    "query",
    [
        "unknown=x",
        "limit=1&limit=1",
        "cursor=x&cursor=y",
        "limit=",
        "limit=0",
        "limit=201",
        "limit=-1",
        "limit=%2B1",
        "limit=1.0",
        "limit=%201",
        "limit=01",
        "limit=١",
        "limit=" + "9" * 5000,
    ],
)
def test_raw_query_validation_follows_auth_and_visibility(http_listing, query):
    app, client, _ = http_listing
    first = error(client.get(BASE + "?" + query), 401, "unauthenticated")
    foreign = BASE.replace(PROJECT, "7" * 32)
    error(client.get(foreign + "?" + query, headers=headers(app)), 404, "not_found")
    current = error(client.get(BASE + "?" + query, headers=headers(app)), 422, "invalid_request")
    assert current != first


@pytest.mark.parametrize("cursor", ["", "bogus", "x" * 2049, "é"])
def test_cursor_errors_only_after_visibility(http_listing, cursor):
    app, client, _ = http_listing
    error(client.get(BASE, params={"cursor": cursor}, headers=headers(app)), 422, "invalid_cursor")
    error(
        client.get(
            BASE.replace(PROJECT, "7" * 32), params={"cursor": cursor}, headers=headers(app)
        ),
        404,
        "not_found",
    )


@pytest.mark.parametrize("query", ["limit=1", "cursor=", "other=x", "x=1&x=2"])
def test_detail_rejects_all_query_after_project_authority(http_listing, query):
    app, client, _ = http_listing
    error(client.get(BASE + "/" + RUN1 + "?" + query), 401, "unauthenticated")
    error(
        client.get(
            BASE.replace(PROJECT, "7" * 32) + "/" + RUN1 + "?" + query, headers=headers(app)
        ),
        404,
        "not_found",
    )
    error(client.get(BASE + "/" + RUN1 + "?" + query, headers=headers(app)), 422, "invalid_request")


def test_real_migration_guard_stops_before_identity_reader_or_other_sinks(
    legacy, settings, monkeypatch
):
    path, engine, source = legacy
    initialize_projection(engine)
    backfill_run_index(engine, source)
    settings.database_url = f"sqlite:///{path}"
    settings.oidc_issuer = ISSUER
    app = create_app(settings)
    actual = runtime_schema_compatibility(app.state.db.engine)
    assert (actual.status, actual.code) == ("incompatible", "migration_only")
    forbidden = Mock(side_effect=AssertionError("guard bypass"))
    for owner, names in [
        (app.state.auth, ("principal",)),
        (app.state.authority, ("named",)),
        (app.state.run_listing, ("list", "detail")),
        (app.state.actions, ("record_run_read",)),
        (app.state.admission, ("require_available", "admit")),
        (app.state.reader.repositories, ("artifact_loader",)),
        (app.state.readiness, ("check",)),
    ]:
        for name in names:
            monkeypatch.setattr(owner, name, forbidden)
    client = TestClient(app)
    try:
        for path in (BASE + "?limit=bad", BASE + "/" + RUN1):
            error(client.get(path, headers=headers(app)), 503, "schema_incompatible")
        forbidden.assert_not_called()
    finally:
        client.close()
        app.state.db.engine.dispose()


def test_missing_key_is_list_only_after_authority(http_listing):
    app, client, _ = http_listing
    app.state.auth.settings.cursor_signing_key = None
    error(client.get(BASE, headers=headers(app)), 503, "dependency_unavailable")
    error(client.get(BASE.replace(PROJECT, "7" * 32), headers=headers(app)), 404, "not_found")
    assert client.get(BASE + "/" + RUN1, headers=headers(app)).status_code == 200
    assert client.get("/api/me", headers=headers(app)).json()["csrf"] == CSRF
    assert client.get("/livez").json() == {"status": "live"}
    assert (
        client.post(
            "/auth/logout",
            headers={
                **headers(app),
                "X-Rewind-CSRF": CSRF,
                "Origin": app.state.auth.settings.public_url,
            },
        ).status_code
        == 200
    )


def test_real_scoped_key_and_live_revocation(http_listing):
    app, client, engine = http_listing
    token = "synthetic-list-viewer-token"
    key = app.state.db.issue_key(token, "viewer", "list", time.time() + 3600, "fixture")
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO resource_scopes VALUES('key',:id,:p)"), {"id": key, "p": PROJECT}
        )
        connection.execute(
            text("INSERT INTO project_memberships VALUES(:p,:id,'viewer',NULL,false)"),
            {"p": PROJECT, "id": "api-key:" + key},
        )
    auth = {"Authorization": "Bearer " + token}
    assert client.get(BASE, headers=auth).status_code == 200
    assert client.get(BASE + "/" + RUN1, headers=auth).status_code == 200
    error(client.get(BASE.replace(PROJECT, OTHER), headers=auth), 404, "not_found")
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE project_memberships SET revoked_at='2026-01-01' WHERE principal_id=:id"),
            {"id": "api-key:" + key},
        )
    error(client.get(BASE, headers=auth), 404, "not_found")
    with engine.begin() as connection:
        connection.execute(text("UPDATE api_keys SET revoked=true WHERE id=:id"), {"id": key})
    error(client.get(BASE, headers=auth), 401, "unauthenticated")


def test_paging_keeps_watermark_expiry_and_original_limit(http_listing, monkeypatch):
    app, client, engine = http_listing
    clock = [datetime(2026, 1, 1, tzinfo=UTC)]

    class Clock:
        @staticmethod
        def now(zone):
            assert zone is UTC
            return clock[0]

    monkeypatch.setattr(api, "datetime", Clock)
    first = client.get(BASE + "?limit=1", headers=headers(app)).json()
    assert [v["id"] for v in first["items"]] == [RUN2]
    cursor = first["next_cursor"]
    with engine.begin() as connection:
        late = add_runs(connection, 1, created=1700000000.0)[0]
    with pytest.raises(RuntimeError), engine.begin() as connection:
        rolled_back = add_runs(connection, 1, first=2000)[0]
        raise RuntimeError("synthetic rollback")
    clock[0] += timedelta(seconds=899)
    with route_failure(monkeypatch, app, phase="listing_continuation_expected_200") as evidence:
        second = client.get(BASE, params={"cursor": cursor}, headers=headers(app))
        assert second.status_code == 200 and second.json()["next_cursor"] is None, evidence()
    assert [v["id"] for v in second.json()["items"]] == [RUN1]
    assert late not in second.text and rolled_back not in second.text
    error(
        client.get(BASE, params={"cursor": cursor, "limit": 2}, headers=headers(app)),
        422,
        "invalid_cursor",
    )
    error(
        client.get(BASE.replace(PROJECT, OTHER), params={"cursor": cursor}, headers=headers(app)),
        422,
        "invalid_cursor",
    )
    subject = "another-viewer"
    other = VerifiedPrincipal.oidc(ISSUER, subject)
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO project_memberships VALUES(:p,:id,'viewer',NULL,false)"),
            {"p": PROJECT, "id": other.principal_id},
        )
    error(
        client.get(BASE, params={"cursor": cursor}, headers=headers(app, other, subject)),
        422,
        "invalid_cursor",
    )
    tampered = cursor[:-1] + ("A" if cursor[-1] != "A" else "B")
    error(
        client.get(BASE, params={"cursor": tampered}, headers=headers(app)), 422, "invalid_cursor"
    )
    clock[0] += timedelta(seconds=1)
    error(client.get(BASE, params={"cursor": cursor}, headers=headers(app)), 422, "invalid_cursor")


def test_incomplete_null_and_current_job_suppression_use_reader(http_listing):
    app, client, engine = http_listing
    with engine.begin() as connection:
        body = json.loads(
            connection.execute(
                text("SELECT data FROM records WHERE id=:id"), {"id": RUN1}
            ).scalar_one()
        )
        connection.execute(text("UPDATE jobs SET cancel=true WHERE id=:id"), {"id": body["job_id"]})
    item = client.get(BASE + "/" + RUN1, headers=headers(app)).json()
    assert item["status"] == "complete" and item["branchable"] is False
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE run_index SET status='incomplete',branchable=false,event_head=NULL,"
                "projection_reason='unfenced_execution' WHERE run_id=:id"
            ),
            {"id": RUN1},
        )
    item = client.get(BASE + "/" + RUN1, headers=headers(app)).json()
    assert set(item) == FIELDS
    assert item["event_head"] is None and item["parent_id"] is None
    assert item["status"] == "incomplete" and item["branchable"] is False


def test_registered_operation_ids_and_required_nullable_response_fields(http_listing):
    app, _, _ = http_listing
    schema = app.openapi()
    path = "/api/v1/projects/{project_id}/runs"
    operation = schema["paths"][path]["get"]
    assert operation["operationId"] == "listProjectRuns"
    queries = {p["name"]: p["schema"] for p in operation["parameters"] if p["in"] == "query"}
    assert queries == {
        "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
        "cursor": {"type": "string", "maxLength": 2048},
    }
    assert schema["paths"][path + "/{run_id}"]["get"]["operationId"] == "getProjectRun"
    summary = schema["components"]["schemas"]["RunSummary"]
    assert set(summary["required"]) == FIELDS and summary["additionalProperties"] is False
    page = schema["components"]["schemas"]["RunPage"]
    assert set(page["required"]) == {"items", "next_cursor"}
    assert page["additionalProperties"] is False


@pytest.mark.parametrize("suffix", ["", "/" + RUN1])
def test_success_is_sql_only_without_legacy_audit_or_work(http_listing, monkeypatch, suffix):
    from sqlalchemy import event

    from agent_rewind import engine as run_engine

    app, client, engine = http_listing
    forbidden = Mock(side_effect=AssertionError("unexpected customer side effect"))
    monkeypatch.setattr(run_engine, "read_events", forbidden)
    for owner, names in [
        (app.state.db, ("enqueue", "audit", "get", "list_records")),
        (app.state.views, ("run", "runs", "files", "compare", "jobs")),
        (app.state.actions, ("record_run_read",)),
        (app.state.reader.repositories, ("artifact_loader",)),
        (app.state.admission, ("require_available", "admit")),
        (app.state.readiness, ("check",)),
    ]:
        for name in names:
            monkeypatch.setattr(owner, name, forbidden)
    with engine.connect() as connection:
        before = (
            connection.execute(text("SELECT count(*) FROM audit")).scalar_one(),
            connection.execute(text("SELECT run_sequence FROM projects ORDER BY id")).all(),
        )
    statements = []

    def observe(connection, cursor, statement, parameters, context, many):
        statements.append(statement)

    event.listen(app.state.db.engine, "before_cursor_execute", observe)
    try:
        response = client.get(BASE + suffix, headers=headers(app))
        assert response.status_code == 200, response.text
    finally:
        event.remove(app.state.db.engine, "before_cursor_execute", observe)
    assert statements and all(s.lstrip().upper().startswith(("SELECT", "WITH")) for s in statements)
    forbidden.assert_not_called()
    with engine.connect() as connection:
        after = (
            connection.execute(text("SELECT count(*) FROM audit")).scalar_one(),
            connection.execute(text("SELECT run_sequence FROM projects ORDER BY id")).all(),
        )
    assert before == after


@pytest.mark.parametrize("suffix", ["", "/" + RUN1])
@pytest.mark.parametrize("change", ["membership", "source"])
def test_final_original_receipts_and_authority_are_not_bypassed_at_http(
    http_listing, monkeypatch, suffix, change
):
    app, client, engine = http_listing
    original = app.state.run_listing._finish

    def altered(principal, context, entries, sources, work):
        with engine.begin() as connection:
            if change == "membership":
                connection.execute(
                    text(
                        "UPDATE project_memberships SET revoked_at='2026-01-01' "
                        "WHERE project_id=:p AND principal_id=:id"
                    ),
                    {"p": PROJECT, "id": PRINCIPAL.principal_id},
                )
            else:
                connection.execute(
                    text("UPDATE records SET created=created+1 WHERE id=:id"), {"id": RUN1}
                )
        return original(principal, context, entries, sources, work)

    monkeypatch.setattr(app.state.run_listing, "_finish", altered)
    response = client.get(BASE + suffix, headers=headers(app))
    error(
        response,
        404 if change == "membership" else 503,
        "not_found" if change == "membership" else "dependency_unavailable",
    )
    assert "items" not in response.json() and "event_head" not in response.json()


def test_old_bootstrap_and_mixed_credentials_do_not_bypass_new_routes(http_listing):
    app, client, _ = http_listing
    old = app.state.auth.cipher.encrypt(
        json.dumps({"sub": "route-human", "role": "administrator", "csrf": CSRF}).encode()
    ).decode()
    credentials = [
        {"Cookie": "rewind_session=" + old},
        {"Authorization": "Bearer " + app.state.auth.settings.bootstrap_key.get_secret_value()},
        {**headers(app), "Authorization": "Bearer invalid-service-key"},
    ]
    for auth in credentials:
        for path in (BASE + "?cursor=", BASE + "/" + RUN1):
            error(client.get(path, headers=auth), 401, "unauthenticated")


def _contract_shape(value, document):
    if isinstance(value, list):
        return [_contract_shape(item, document) for item in value]
    if not isinstance(value, dict):
        return value
    if "$ref" in value:
        target = document
        for part in value["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        return _contract_shape(target, document)
    result = {
        key: _contract_shape(item, document)
        for key, item in value.items()
        if key not in {"title", "description", "summary"}
    }
    for key in ("required", "enum"):
        if isinstance(result.get(key), list):
            result[key] = sorted(result[key])
    return result


def test_two_operations_preserve_frozen_response_headers_and_parameter_schemas(http_listing):
    from pathlib import Path

    app, _, _ = http_listing
    actual = app.openapi()
    frozen = json.loads(
        (Path(__file__).parents[1] / "contracts/proposals/m1.openapi.json").read_text()
    )
    path = "/api/v1/projects/{project_id}/runs"
    for target in (path, path + "/{run_id}"):
        operation = actual["paths"][target]["get"]
        expected = frozen["paths"][target]["get"]
        assert operation["operationId"] == expected["operationId"]
        assert _contract_shape(operation["responses"], actual) == _contract_shape(
            expected["responses"], frozen
        )
        expected_parameters = [
            *frozen["paths"][target].get("parameters", []),
            *expected.get("parameters", []),
        ]
        actual_parameters = operation["parameters"]
        identities = [(item["in"], item["name"]) for item in actual_parameters]
        assert len(identities) == len(set(identities))

        # OpenAPI defaults omitted optional query required flags to false.
        def parameters(items, document):
            return {
                (item["in"], item["name"]): {
                    "required": item.get("required", False),
                    "schema": _contract_shape(item["schema"], document),
                }
                for item in items
            }

        assert parameters(actual_parameters, actual) == parameters(expected_parameters, frozen)


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/projects/not-a-project/runs",
        "/api/v1/projects/not-a-project/runs/not-a-run",
        BASE + "/not-a-run",
    ],
)
def test_path_schema_patterns_do_not_validate_before_auth_and_visibility(http_listing, path):
    app, client, _ = http_listing
    error(client.get(path), 401, "unauthenticated")
    error(client.get(path, headers=headers(app)), 404, "not_found")


def test_populated_projects_keep_lists_and_details_disjoint(http_listing):
    from sqlalchemy import insert

    from agent_rewind.database import jobs, records

    app, client, engine = http_listing
    other_ids = ("4" * 32, "5" * 32)
    with engine.begin() as connection:
        original = json.loads(
            connection.execute(
                text("SELECT CAST(data AS TEXT) FROM records WHERE id=:id"), {"id": RUN1}
            ).scalar_one()
        )
        original_job = dict(
            connection.execute(text("SELECT * FROM jobs WHERE id=:id"), {"id": original["job_id"]})
            .mappings()
            .one()
        )
        for sequence, run_id in enumerate(other_ids, 1):
            job_id = str(sequence + 5) * 32
            connection.execute(
                insert(jobs).values(
                    **{
                        **original_job,
                        "id": job_id,
                        "kind": "run",
                        "status": "succeeded",
                        "cancel": False,
                        "owner": None,
                        "lease_until": None,
                    }
                )
            )
            connection.execute(
                insert(records).values(
                    id=run_id,
                    kind="run",
                    created=1700000000.125,
                    data={**original, "job_id": job_id, "parent_id": None, "status": "complete"},
                )
            )
            for kind, identity in (("run", run_id), ("job", job_id)):
                connection.execute(
                    text("INSERT INTO resource_scopes VALUES(:kind,:id,:project)"),
                    {"kind": kind, "id": identity, "project": OTHER},
                )
            connection.execute(
                text(
                    "INSERT INTO run_index "
                    "SELECT :id,:project,'run',created_at,status,branchable,NULL,event_head,"
                    ":seq,projection_reason FROM run_index WHERE run_id=:original"
                ),
                {"id": run_id, "project": OTHER, "seq": sequence, "original": RUN1},
            )
        connection.execute(text("UPDATE projects SET run_sequence=2 WHERE id=:id"), {"id": OTHER})
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    for project, expected in ((PROJECT, [RUN2, RUN1]), (OTHER, list(reversed(other_ids)))):
        base = f"/api/v1/projects/{project}/runs"
        response = client.get(base, headers=headers(app))
        assert response.status_code == 200, response.text
        page = response.json()
        assert [item["id"] for item in page["items"]] == expected
        assert page["next_cursor"] is None
        for item in page["items"]:
            assert set(item) == FIELDS and item["project_id"] == project
            detail = client.get(base + "/" + item["id"], headers=headers(app))
            assert detail.status_code == 200 and detail.json() == item
        foreign = other_ids[0] if project == PROJECT else RUN1
        error(client.get(base + "/" + foreign, headers=headers(app)), 404, "not_found")


@pytest.mark.parametrize("suffix", ["", "/" + RUN1])
def test_final_sql_phase_exhaustion_is_fixed_503_without_partial_response(
    http_listing, monkeypatch, suffix
):
    from agent_rewind import listing_session

    app, client, _ = http_listing
    reader = app.state.run_listing
    clock, stages = [0.0], []
    monkeypatch.setattr(listing_session, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    original_receipts, original_check = reader._receipts, reader.authority.check

    def receipts(*args, **kwargs):
        result = original_receipts(*args, **kwargs)
        stages.append("receipts")
        return result

    def checked(*args, **kwargs):
        result = original_check(*args, **kwargs)
        if stages:
            stages.append("final-authority")
            # Exhaust only after real final SQL/authority, before returning a page.
            clock[0] = listing_session.MAX_SQL_SECONDS + 0.001
        return result

    with monkeypatch.context() as patch:
        patch.setattr(reader, "_receipts", receipts)
        patch.setattr(reader.authority, "check", checked)
        response = client.get(BASE + suffix, headers=headers(app))
    assert stages == ["receipts", "final-authority"]
    error(response, 503, "dependency_unavailable")
    assert response.json()["retryable"] is True
    assert "items" not in response.json() and "event_head" not in response.json()
    assert reader.engine.pool.checkedout() == 0
    with owned_connect(reader.engine) as connection:
        assert connection.exec_driver_sql("PRAGMA query_only").scalar_one() == 0
        assert not connection.connection.driver_connection.in_transaction
    # The next independent read remains usable after the failed final phase.
    clock[0] = 0.0
    assert client.get(BASE + suffix, headers=headers(app)).status_code == 200
