"""Existing HTTP routes over explicit synthetic grants and actual verified publication."""

import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from publication_fixture import make_capture
from route_fixture import (
    ISSUER,
    PRINCIPAL,
    PROJECT,
    cookie_headers,
    prepared_app,
    source_run,
    work_bodies,
)
from sqlalchemy import text

from agent_rewind.api import create_app
from agent_rewind.artifact_metadata import ArtifactError
from agent_rewind.scoped_actions import ScopedActionError
from agent_rewind.sqlite_ownership import owned_begin, owned_connect

pytestmark = pytest.mark.usefixtures("legacy_behavior_schema")


@pytest.fixture
def published_http(settings, task):
    settings.oidc_issuer = ISSUER
    capture = make_capture(settings)
    run = capture.run(task)
    capture.publisher.publish(capture.intent(run), capture.source)
    app = create_app(settings)
    with owned_begin(app.state.db.engine) as connection:
        connection.execute(
            text("INSERT INTO project_memberships VALUES(:p,:id,'maintainer',NULL,true)"),
            {"p": PROJECT, "id": PRINCIPAL.principal_id},
        )
    with TestClient(app) as client:
        yield app, client, run, capture
    app.state.db.engine.dispose()
    capture.db.engine.dispose()


def read_audits(app):
    with owned_connect(app.state.db.engine) as connection:
        return connection.execute(
            text("SELECT actor,target FROM audit WHERE action='run.read'")
        ).all()


def test_existing_verified_read_shapes_and_success_audit(published_http):
    app, client, run, _ = published_http
    headers = cookie_headers(app)
    response = client.get("/api/runs/" + run, headers=headers)
    assert response.status_code == 200
    value = response.json()
    assert value["status"] == "complete" and value["success"] is False
    assert value["evaluation"]["exit_code"] == 1 and len(value["events"]) == 3
    assert read_audits(app) == [(PRINCIPAL.principal_id, run)]
    files = client.get(f"/api/runs/{run}/files/2", headers=headers)
    assert files.status_code == 200 and any(item["path"] == "binary" for item in files.json())
    assert (
        client.get(f"/api/runs/{run}/files/2", params={"path": "binary"}, headers=headers).json()[
            "content"
        ]
        == "\x00�"
    )
    assert (
        client.get(
            f"/api/runs/{run}/files/2", params={"path": "../secret"}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"/api/runs/{run}/files/2", params={"path": "missing"}, headers=headers
        ).status_code
        == 404
    )
    assert client.get(f"/api/runs/{run}/files/99", headers=headers).status_code == 404
    compared = client.get("/api/compare", params={"left": run, "right": run}, headers=headers)
    assert compared.status_code == 200 and compared.json()["files"] == []
    assert len(read_audits(app)) == 1  # No invented audit events for other read routes.
    assert client.get("/api/schema", headers=headers).status_code == 200


@pytest.mark.parametrize("failure", ["corrupt", "revoked", "audit"])
def test_failed_or_revoked_detail_never_returns_success_or_audit(
    published_http, monkeypatch, failure
):
    app, client, run, _ = published_http
    original = app.state.reader.repositories.artifact_loader
    if failure == "audit":
        monkeypatch.setattr(
            app.state.actions,
            "record_run_read",
            Mock(side_effect=ScopedActionError("outcome_uncertain")),
        )
    else:

        def load(value):
            if failure == "corrupt":
                raise ArtifactError("artifact_digest_mismatch")
            result = original(value)
            with owned_begin(app.state.db.engine) as connection:
                connection.execute(
                    text(
                        "UPDATE project_memberships SET revoked_at='2026-01-01' "
                        "WHERE principal_id=:id"
                    ),
                    {"id": PRINCIPAL.principal_id},
                )
            return result

        monkeypatch.setattr(app.state.reader.repositories, "artifact_loader", load)
    response = client.get("/api/runs/" + run, headers=cookie_headers(app))
    assert response.status_code == (404 if failure == "revoked" else 503)
    assert set(response.json()) == {"detail"} and read_audits(app) == []
    assert "events" not in response.text


def test_every_existing_data_route_authenticates_before_consumers(settings, task, monkeypatch):
    app = prepared_app(settings)
    run, job = source_run(app)
    forbidden = Mock(side_effect=AssertionError("unauthenticated consumer"))
    monkeypatch.setattr(app.state.reader.repositories, "artifact_loader", forbidden)
    monkeypatch.setattr(app.state.admission, "require_available", forbidden)
    for method in ("cancel", "issue_key", "revoke_key", "record_run_read"):
        monkeypatch.setattr(app.state.actions, method, forbidden)
    with TestClient(app) as client:
        for path in [
            "/api/me",
            "/api/schema",
            "/api/runs",
            "/api/runs/" + run,
            f"/api/runs/{run}/files/1",
            "/api/studies",
            "/api/studies/" + "3" * 32,
            "/api/jobs",
            f"/api/compare?left={run}&right={run}",
        ]:
            assert client.get(path).status_code == 401, path
        for path, body in work_bodies(run, task):
            assert client.post(path, json=body).status_code == 401, path
        assert client.post(f"/api/jobs/{job}/cancel").status_code == 401
        assert client.post("/api/keys", json={"role": "viewer", "name": "x"}).status_code == 401
        assert client.delete("/api/keys/" + "4" * 32).status_code == 401
        assert client.post("/auth/logout").status_code == 401
    forbidden.assert_not_called()


def test_foreign_resource_visibility_precedes_viewer_action_and_storage(
    settings, task, monkeypatch
):
    app = prepared_app(settings)
    run, job = source_run(app)
    foreign_project, foreign_run, foreign_job = "b" * 32, "c" * 32, "d" * 32
    with owned_begin(app.state.db.engine) as connection:
        connection.execute(
            text("UPDATE project_memberships SET role='viewer' WHERE principal_id=:id"),
            {"id": PRINCIPAL.principal_id},
        )
        connection.execute(
            text(
                "INSERT INTO projects SELECT :id,organization_id,'Foreign',created_at "
                "FROM projects WHERE id=:p"
            ),
            {"id": foreign_project, "p": PROJECT},
        )
        connection.execute(
            text(
                "INSERT INTO jobs(id,kind,created,payload,status,cancel,budget,reserved) "
                "VALUES(:id,'run',1,:d,'queued',false,1,0)"
            ),
            {"id": foreign_job, "d": "0" * 64},
        )
        connection.execute(
            text("INSERT INTO records VALUES(:id,'run',1,:d)"),
            {
                "id": foreign_run,
                "d": json.dumps(
                    {"job_id": foreign_job, "parent_id": None, "name": "foreign-secret"}
                ),
            },
        )
        for kind, ident in [("job", foreign_job), ("run", foreign_run)]:
            connection.execute(
                text("INSERT INTO resource_scopes VALUES(:kind,:id,:p)"),
                {"kind": kind, "id": ident, "p": foreign_project},
            )
    forbidden = Mock(side_effect=AssertionError("foreign storage or unavailable adapter"))
    monkeypatch.setattr(app.state.reader.repositories, "artifact_loader", forbidden)
    monkeypatch.setattr(app.state.admission, "require_available", forbidden)
    with TestClient(app) as client:
        headers = cookie_headers(app)
        listed = client.get("/api/runs", headers=headers)
        assert listed.status_code == 200 and [v["id"] for v in listed.json()] == [run]
        assert "foreign-secret" not in listed.text
        for target in (foreign_run, "0" * 32):
            assert client.get("/api/runs/" + target, headers=headers).status_code == 404
            for path, body in work_bodies(target, task)[1:]:
                assert client.post(path, json=body, headers=headers).status_code == 404
        for path, body in work_bodies(run, task):
            assert client.post(path, json=body, headers=headers).status_code == 403
        assert client.post(f"/api/jobs/{job}/cancel", headers=headers).status_code == 403
        assert client.post(f"/api/jobs/{foreign_job}/cancel", headers=headers).status_code == 404
    forbidden.assert_not_called()


def test_s3_configuration_has_no_constructor_or_unauthorized_backend_io(settings, monkeypatch):
    import boto3

    from agent_rewind.artifact_storage import LocalArtifactStorage

    forbidden = Mock(side_effect=AssertionError("raw or fallback storage"))
    monkeypatch.setattr(boto3, "client", forbidden)
    monkeypatch.setattr(LocalArtifactStorage, "read_verified", forbidden)
    settings.storage = "s3"
    settings.s3_bucket = "synthetic-bucket"
    app = prepared_app(settings)
    run, _ = source_run(app)
    with TestClient(app) as client:
        assert client.get("/livez").status_code == 200
        assert client.get("/api/runs/" + run).status_code == 401
        assert client.get("/api/me", headers=cookie_headers(app)).status_code == 200
        # This unpublished record refuses before any backend, too.
        assert client.get("/api/runs/" + run, headers=cookie_headers(app)).status_code == 404
    forbidden.assert_not_called()


def test_registered_graph_on_configured_s3_refuses_without_local_fallback(
    published_http, monkeypatch
):
    import boto3

    from agent_rewind.artifact_storage import LocalArtifactStorage

    app, _, run, _ = published_http
    settings = app.state.auth.settings
    settings.storage = "s3"
    settings.s3_bucket = "synthetic-bucket"
    forbidden = Mock(side_effect=AssertionError("backend setup/fallback"))
    monkeypatch.setattr(boto3, "client", forbidden)
    monkeypatch.setattr(LocalArtifactStorage, "read_verified", forbidden)
    remote = create_app(settings)
    try:
        with TestClient(remote) as client:
            assert client.get("/api/runs/" + run, headers=cookie_headers(remote)).status_code == 503
        assert read_audits(remote) == []
        forbidden.assert_not_called()
    finally:
        remote.state.db.engine.dispose()


@pytest.mark.parametrize("role", ["viewer", "operator"])
def test_service_key_me_intersects_current_membership_and_cannot_manage_keys(settings, role):
    app = prepared_app(settings)
    with TestClient(app) as client:
        created = client.post(
            "/api/keys", headers=cookie_headers(app), json={"role": role, "name": "synthetic"}
        )
        assert created.status_code == 201
        key = created.json()
        headers = {"Authorization": "Bearer " + key["token"]}
        assert client.get("/api/me", headers=headers).json()["role"] == role
        assert (
            client.post(
                "/api/keys", headers=headers, json={"role": "viewer", "name": "no"}
            ).status_code
            == 403
        )
        assert client.delete("/api/keys/" + key["id"], headers=headers).status_code == 403
        assert client.delete("/api/keys/" + "0" * 32, headers=headers).status_code == 404
        with owned_begin(app.state.db.engine) as connection:
            connection.execute(
                text("UPDATE project_memberships SET role='maintainer' WHERE principal_id=:id"),
                {"id": "api-key:" + key["id"]},
            )
        assert client.get("/api/me", headers=headers).json()["role"] == role
        with owned_begin(app.state.db.engine) as connection:
            connection.execute(
                text(
                    "UPDATE project_memberships SET revoked_at='2026-01-01' WHERE principal_id=:id"
                ),
                {"id": "api-key:" + key["id"]},
            )
        assert client.get("/api/me", headers=headers).json()["role"] is None
        assert client.get("/api/runs", headers=headers).status_code == 404
