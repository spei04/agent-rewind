"""OIDC authorization code + PKCE, short sessions, and revocable scoped API keys."""

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx
import jwt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from .config import Settings
from .database import Database
from .models import canonical

ROLES = {"viewer": 0, "operator": 1, "administrator": 2}


@dataclass(frozen=True)
class Principal:
    subject: str
    role: str
    csrf: str = ""


class Auth:
    def __init__(self, settings: Settings, db: Database):
        self.settings, self.db = settings, db
        self.cipher = Fernet(settings.encryption_key.get_secret_value().encode())
        self.secure = settings.public_url.startswith("https://")
        self.discovery: dict[str, Any] | None = None
        self.jwks: jwt.PyJWKClient | None = None

    def principal(self, request: Request, minimum: str = "viewer") -> Principal:
        header = request.headers.get("authorization", "")
        principal = None
        if header.startswith("Bearer "):
            token = header[7:]
            bootstrap = self.settings.bootstrap_key
            if bootstrap and hmac.compare_digest(token, bootstrap.get_secret_value()):
                principal = Principal("bootstrap", "administrator")
            else:
                key = self.db.lookup_key(token)
                if key:
                    principal = Principal(f"api-key:{key['id']}", key["role"])
        elif request.cookies.get("rewind_session"):
            try:
                session = json.loads(
                    self.cipher.decrypt(request.cookies["rewind_session"].encode(), ttl=900)
                )
                principal = Principal(session["sub"], session["role"], session["csrf"])
            except (InvalidToken, ValueError, KeyError):
                raise HTTPException(401, "Session expired.") from None
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                if not hmac.compare_digest(
                    request.headers.get("x-rewind-csrf", ""), principal.csrf
                ):
                    raise HTTPException(403, "Missing CSRF token.")
                if request.headers.get("origin") != self.settings.public_url.rstrip("/"):
                    raise HTTPException(403, "Invalid request origin.")
        if principal is None:
            raise HTTPException(401, "Authentication required.")
        if principal.role not in ROLES or ROLES[principal.role] < ROLES[minimum]:
            raise HTTPException(403, "Insufficient permissions.")
        return principal

    def _discovery(self) -> dict[str, Any]:
        if not self.settings.oidc_issuer:
            raise HTTPException(503, "Identity login is not configured. Use a scoped API key.")
        if self.discovery is None:
            with httpx.Client(timeout=10, follow_redirects=False) as client:
                response = client.get(
                    self.settings.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration"
                )
                response.raise_for_status()
                document = response.json()
            if document["issuer"] != self.settings.oidc_issuer:
                raise ValueError("Identity discovery issuer mismatch.")
            for field in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
                if urlparse(document[field]).scheme != "https":
                    raise ValueError("Identity endpoints must use HTTPS.")
            self.discovery = document
            self.jwks = jwt.PyJWKClient(
                document["jwks_uri"], cache_jwk_set=True, lifespan=300, timeout=10
            )
        return self.discovery

    def login(self) -> RedirectResponse:
        document = self._discovery()
        verifier, state, nonce = (
            secrets.token_urlsafe(48),
            secrets.token_urlsafe(32),
            secrets.token_urlsafe(32),
        )
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        url = (
            document["authorization_endpoint"]
            + "?"
            + urlencode(
                {
                    "client_id": self.settings.oidc_client_id,
                    "response_type": "code",
                    "scope": "openid profile",
                    "redirect_uri": self.settings.public_url.rstrip("/") + "/auth/callback",
                    "state": state,
                    "nonce": nonce,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                }
            )
        )
        response = RedirectResponse(url)
        response.set_cookie(
            "rewind_login",
            self.cipher.encrypt(
                canonical({"state": state, "nonce": nonce, "verifier": verifier})
            ).decode(),
            max_age=300,
            httponly=True,
            secure=self.secure,
            samesite="lax",
            path="/auth",
        )
        return response

    def callback(self, request: Request) -> RedirectResponse:
        try:
            flow = json.loads(
                self.cipher.decrypt(request.cookies.get("rewind_login", "").encode(), ttl=300)
            )
            if not hmac.compare_digest(flow["state"], request.query_params.get("state", "")):
                raise ValueError("Invalid login state.")
            document = self._discovery()
            body = {
                "grant_type": "authorization_code",
                "code": request.query_params["code"],
                "client_id": self.settings.oidc_client_id,
                "code_verifier": flow["verifier"],
                "redirect_uri": self.settings.public_url.rstrip("/") + "/auth/callback",
            }
            if self.settings.oidc_client_secret:
                body["client_secret"] = self.settings.oidc_client_secret.get_secret_value()
            with httpx.Client(timeout=10, follow_redirects=False) as client:
                response = client.post(document["token_endpoint"], data=body)
                response.raise_for_status()
                token = response.json()["id_token"]
            assert self.jwks is not None
            signing_key = self.jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                audience=self.settings.oidc_audience or self.settings.oidc_client_id,
                issuer=self.settings.oidc_issuer,
                options={"require": ["exp", "iat", "sub", "nonce"]},
            )
            if not hmac.compare_digest(claims["nonce"], flow["nonce"]):
                raise ValueError("Invalid nonce.")
            role = claims.get(self.settings.oidc_role_claim)
            if role not in ROLES:
                raise ValueError("Identity has no application role.")
        except (InvalidToken, ValueError, KeyError, httpx.HTTPError, jwt.PyJWTError):
            raise HTTPException(401, "Identity login failed.") from None
        session = {"sub": claims["sub"], "role": role, "csrf": secrets.token_urlsafe(32)}
        result = RedirectResponse("/")
        result.delete_cookie("rewind_login", path="/auth")
        result.set_cookie(
            "rewind_session",
            self.cipher.encrypt(canonical(session)).decode(),
            max_age=900,
            httponly=True,
            secure=self.secure,
            samesite="lax",
        )
        self.db.audit(claims["sub"], "identity.login", "session")
        return result

    def issue(self, role: str, name: str, days: int, actor: str) -> dict[str, str]:
        if role not in ROLES or not 1 <= days <= 90 or not 1 <= len(name) <= 120:
            raise HTTPException(422, "Invalid key role, name, or lifetime.")
        token = "rw_" + secrets.token_urlsafe(32)
        key_id = self.db.issue_key(token, role, name, time.time() + days * 86400, actor)
        return {"id": key_id, "token": token, "role": role}
