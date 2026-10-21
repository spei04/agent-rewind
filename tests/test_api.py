import json
import time
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from route_fixture import CSRF, PRINCIPAL, PROJECT, cookie, cookie_headers, prepared_app
from sqlalchemy import text

from agent_rewind.api import create_app
from agent_rewind.models import Action
from agent_rewind.scoped_repositories import RepositoryUnavailable

pytestmark = pytest.mark.usefixtures("legacy_behavior_schema")


def test_auth_roles_key_revocation_and_no_payload_echo(settings, task):
    app = prepared_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/runs").status_code == 401
        admin = cookie_headers(app)
        assert (
            client.get(
                "/api/runs",
                headers={"Authorization": "Bearer " + settings.bootstrap_key.get_secret_value()},
            ).status_code
            == 401
        )
        created = client.post(
            "/api/keys", headers=admin, json={"role": "viewer", "name": "reader", "days": 1}
        )
        assert created.status_code == 201
        key = created.json()
        viewer = {"Authorization": "Bearer " + key["token"]}
        assert client.get("/api/runs", headers=viewer).status_code == 200
        assert client.post("/api/runs", headers=viewer, json=task.model_dump()).status_code == 403
        assert client.delete("/api/keys/" + key["id"], headers=admin).status_code == 200
        assert client.get("/api/runs", headers=viewer).status_code == 401
        payload = task.model_dump()
        payload["max_steps"] = "private-secret-value"
        response = client.post("/api/runs", headers=admin, json=payload)
        assert response.status_code == 422
        assert "private-secret-value" not in response.text
        assert "frame-ancestors" in client.get("/").headers["content-security-policy"]


def test_tampered_cookie_rejected(settings):
    app = create_app(settings)
    app.state.db.migrate(installation_key="synthetic-test")
    with TestClient(app) as client:
        client.cookies.set("rewind_session", "forged")
        assert client.get("/api/me").status_code == 401


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", "a/../b", "a\\b", "./foo"])
def test_tool_paths_are_normalized(path):
    with pytest.raises(ValueError):
        Action(tool="read_file", path=path)


def test_scoped_key_expiry(settings):
    app = create_app(settings)
    app.state.db.migrate(installation_key="synthetic-test")
    app.state.db.issue_key("expired-token", "administrator", "expired", time.time() - 1, "test")
    with TestClient(app) as client:
        assert (
            client.get("/api/runs", headers={"Authorization": "Bearer expired-token"}).status_code
            == 401
        )


def test_oversized_body_is_rejected_before_parsing(settings):
    app = create_app(settings)
    app.state.db.migrate(installation_key="synthetic-test")
    with TestClient(app) as client:
        response = client.post("/api/runs", content=b"x" * (9 * 1024 * 1024 + 1))
        assert response.status_code == 413


def test_cookie_write_requires_csrf_and_origin(settings, task):
    app = prepared_app(settings)
    with TestClient(app) as client:
        client.cookies.set("rewind_session", cookie(app))
        assert client.get("/api/me").status_code == 200
        assert client.post("/api/runs", json=task.model_dump()).status_code == 403
        assert (
            client.post(
                "/api/runs",
                json=task.model_dump(),
                headers={"X-Rewind-CSRF": CSRF, "Origin": "https://attacker.invalid"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/runs",
                json=task.model_dump(),
                headers={"X-Rewind-CSRF": CSRF, "Origin": settings.public_url},
            ).status_code
            == 503
        )


def test_revoked_member_recovers_csrf_and_logs_out_without_data(settings):
    app = prepared_app(settings)
    with TestClient(app) as client:
        client.cookies.set("rewind_session", cookie(app))
        assert client.get("/api/me").json()["role"] == "maintainer"
        with app.state.db.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE project_memberships SET revoked_at='2026-01-01' WHERE principal_id=:id"
                ),
                {"id": PRINCIPAL.principal_id},
            )
        me = client.get("/api/me")
        assert me.status_code == 200
        assert me.json() == {"subject": PRINCIPAL.principal_id, "role": None, "csrf": CSRF}
        for path in ("/api/runs", "/api/studies", "/api/jobs", "/api/schema"):
            assert client.get(path).status_code == 404
        logout = client.post(
            "/auth/logout",
            headers={"X-Rewind-CSRF": me.json()["csrf"], "Origin": settings.public_url},
        )
        assert logout.status_code == 200 and "Max-Age=0" in logout.headers["set-cookie"]


@pytest.mark.parametrize("bearer", ["valid", "invalid"])
@pytest.mark.parametrize(
    "csrf,origin,expected",
    [
        (None, None, 403),
        ("wrong", "correct", 403),
        ("correct", "wrong", 403),
        ("correct", "correct", 200),
    ],
)
def test_logout_cookie_boundary_ignores_bearer_precedence(settings, bearer, csrf, origin, expected):
    app = prepared_app(settings)
    app.state.db.issue_key("valid", "operator", "fixture", time.time() + 1000, "test")
    headers = {"Authorization": "Bearer " + bearer}
    if csrf is not None:
        headers["X-Rewind-CSRF"] = CSRF if csrf == "correct" else csrf
    if origin is not None:
        headers["Origin"] = (
            settings.public_url if origin == "correct" else "https://attacker.invalid"
        )
    with TestClient(app) as client:
        client.cookies.set("rewind_session", cookie(app))
        assert client.post("/auth/logout", headers=headers).status_code == expected
        # Other routes consistently use an explicitly supplied bearer first.
        if bearer == "invalid":
            assert client.get("/api/me", headers=headers).status_code == 401


def test_me_database_failure_is_not_null_role(settings, monkeypatch):
    app = prepared_app(settings)

    def unavailable(*args):
        raise RepositoryUnavailable()

    monkeypatch.setattr(app.state.authority, "legacy_role", unavailable)
    with TestClient(app) as client:
        assert client.get("/api/me", headers=cookie_headers(app)).status_code == 503


def test_admission_refuses_before_readiness_storage_or_writes(settings, task, monkeypatch):
    app = prepared_app(settings)
    forbidden = Mock(side_effect=AssertionError("unavailable admission crossed boundary"))
    monkeypatch.setattr(app.state.readiness, "check", forbidden)
    monkeypatch.setattr(app.state.reader.repositories, "artifact_loader", forbidden)
    monkeypatch.setattr(app.state.db, "enqueue", forbidden)
    run = "1" * 32
    # Trusted synthetic SQL source only; no accepted work creation is claimed.
    job_id = "2" * 32
    with app.state.db.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO jobs(id,kind,created,payload,status,cancel,budget,reserved) "
                "VALUES(:id,'run',1,:digest,'queued',false,1,0)"
            ),
            {"id": job_id, "digest": "0" * 64},
        )
        connection.execute(
            text("INSERT INTO records(id,kind,created,data) VALUES(:id,'run',1,:data)"),
            {"id": run, "data": json.dumps({"parent_id": None, "job_id": job_id})},
        )
        for kind, identity in (("job", job_id), ("run", run)):
            connection.execute(
                text("INSERT INTO resource_scopes VALUES(:kind,:id,:project)"),
                {"kind": kind, "id": identity, "project": PROJECT},
            )
    bodies = [
        ("/api/runs", task.model_dump()),
        (
            "/api/branches",
            {
                "parent_id": run,
                "intervention": {"step": 1, "kind": "action", "action": {"tool": "finish"}},
            },
        ),
        (
            "/api/studies",
            {
                "run_id": run,
                "candidates": [{"step": 1, "kind": "action", "action": {"tool": "finish"}}],
            },
        ),
        ("/api/investigations", {"run_id": run}),
    ]
    with app.state.db.engine.connect() as connection:
        before = connection.exec_driver_sql("SELECT count(*) FROM audit").scalar_one()
    with TestClient(app) as client:
        for path, body in bodies:
            assert client.post(path, json=body, headers=cookie_headers(app)).status_code == 503
    with app.state.db.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM audit").scalar_one() == before
        assert connection.exec_driver_sql("SELECT count(*) FROM jobs").scalar_one() == 1
    forbidden.assert_not_called()
