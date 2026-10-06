import time
from types import SimpleNamespace
from urllib.parse import urlencode

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from starlette.requests import Request

from agent_rewind.auth import Auth
from agent_rewind.models import canonical


@pytest.mark.parametrize(
    "change,accepted",
    [
        ({}, True),
        ({"iss": "https://wrong.invalid"}, False),
        ({"aud": "wrong-client"}, False),
        ({"nonce": "wrong-nonce"}, False),
        ({"exp": 1}, False),
        ({"rewind_role": "unknown"}, False),
    ],
)
def test_signed_identity_token_validation(settings, storage, monkeypatch, change, accepted):
    db, _ = storage
    settings.oidc_issuer = "https://identity.example.test"
    settings.oidc_client_id = "test-client"
    auth = Auth(settings, db)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = {
        "iss": settings.oidc_issuer,
        "aud": "test-client",
        "sub": "test-person",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "nonce": "nonce",
        "rewind_role": "operator",
    }
    claims.update(change)
    token = jwt.encode(claims, key, algorithm="RS256")
    auth.discovery = {"token_endpoint": "https://identity.example.test/token"}
    auth.jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=key.public_key())
    )

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, data):
            assert data["code_verifier"] == "verifier"
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"id_token": token})

    monkeypatch.setattr("agent_rewind.auth.httpx.Client", FakeClient)
    cookie = auth.cipher.encrypt(
        canonical({"state": "state", "nonce": "nonce", "verifier": "verifier"})
    ).decode()
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/auth/callback",
            "query_string": urlencode({"code": "code", "state": "state"}).encode(),
            "headers": [(b"cookie", f"rewind_login={cookie}".encode())],
        }
    )
    if accepted:
        response = auth.callback(request)
        assert response.status_code == 307
        session_cookie = next(
            value
            for value in response.headers.getlist("set-cookie")
            if value.startswith("rewind_session=")
        )
        assert "httponly" in session_cookie.lower()
        assert "max-age=900" in session_cookie.lower()
    else:
        with pytest.raises(HTTPException) as caught:
            auth.callback(request)
        assert caught.value.status_code == 401


def test_production_cannot_enable_standard_container_fallback(settings):
    from agent_rewind.config import Settings

    config = settings.model_dump()
    config.update(
        mode="production",
        database_url="postgresql+psycopg://unused",
        public_url="https://rewind.example.test",
        oidc_issuer="https://identity.example.test",
        oidc_client_id="client",
        sandbox_runtime="runc",
        allow_insecure_runtime=True,
    )
    with pytest.raises(ValueError, match="runsc"):
        Settings(_env_file=None, **config)
