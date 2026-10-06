import time

import pytest
from fastapi.testclient import TestClient

from agent_rewind.api import create_app
from agent_rewind.models import Action


def test_auth_roles_key_revocation_and_no_payload_echo(settings, task):
    app = create_app(settings)
    app.state.db.migrate()
    with TestClient(app) as client:
        assert client.get("/api/runs").status_code == 401
        admin = {"Authorization": "Bearer " + settings.bootstrap_key.get_secret_value()}
        key = client.post(
            "/api/keys", headers=admin, json={"role": "viewer", "name": "reader", "days": 1}
        ).json()
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
    app.state.db.migrate()
    with TestClient(app) as client:
        client.cookies.set("rewind_session", "forged")
        assert client.get("/api/me").status_code == 401


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", "a/../b", "a\\b", "./foo"])
def test_tool_paths_are_normalized(path):
    with pytest.raises(ValueError):
        Action(tool="read_file", path=path)


def test_scoped_key_expiry(settings):
    app = create_app(settings)
    app.state.db.migrate()
    app.state.db.issue_key("expired-token", "administrator", "expired", time.time() - 1, "test")
    with TestClient(app) as client:
        assert (
            client.get("/api/runs", headers={"Authorization": "Bearer expired-token"}).status_code
            == 401
        )


def test_oversized_body_is_rejected_before_parsing(settings):
    app = create_app(settings)
    app.state.db.migrate()
    with TestClient(app) as client:
        response = client.post("/api/runs", content=b"x" * (9 * 1024 * 1024 + 1))
        assert response.status_code == 413


def test_cookie_write_requires_csrf_and_origin(settings, task):
    from agent_rewind.models import canonical

    app = create_app(settings)
    app.state.db.migrate()
    cookie = app.state.auth.cipher.encrypt(
        canonical({"sub": "test-user", "role": "operator", "csrf": "nonce"})
    ).decode()
    with TestClient(app) as client:
        client.cookies.set("rewind_session", cookie)
        assert client.get("/api/me").status_code == 200
        assert client.post("/api/runs", json=task.model_dump()).status_code == 403
        assert (
            client.post(
                "/api/runs",
                json=task.model_dump(),
                headers={"X-Rewind-CSRF": "nonce", "Origin": "https://attacker.invalid"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/runs",
                json=task.model_dump(),
                headers={"X-Rewind-CSRF": "nonce", "Origin": settings.public_url},
            ).status_code
            == 202
        )
