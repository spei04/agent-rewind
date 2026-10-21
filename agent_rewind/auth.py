"""OIDC authorization code + PKCE, short sessions, and revocable scoped API keys."""

import base64
import hashlib
import hmac
import json
import math
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
from sqlalchemy import and_, case, select
from sqlalchemy.exc import SQLAlchemyError

from .config import Settings
from .database import Database, keys
from .models import canonical
from .request_identity import (
    IdentityInvalid,
    SessionIdentity,
    VerifiedPrincipal,
    decode_v2_session,
    encode_v2_session,
)
from .scoped_repositories import RepositoryUnavailable, _byte_length


@dataclass(frozen=True)
class Principal:
    """Authenticated identity only; current project grants supply authority."""

    verified: VerifiedPrincipal
    csrf: str = ""

    @property
    def subject(self) -> str:
        return self.verified.principal_id


class Auth:
    def __init__(self, settings: Settings, db: Database):
        self.settings, self.db = settings, db
        self.cipher = Fernet(settings.encryption_key.get_secret_value().encode())
        self.secure = settings.public_url.startswith("https://")
        self.discovery: dict[str, Any] | None = None
        self.jwks: jwt.PyJWKClient | None = None

    def session(self, request: Request) -> Principal:
        """V2 cookie authentication, including CSRF/Origin on unsafe methods.

        Deliberately independent of project membership so a revoked member can
        recover their own CSRF through /api/me and clear the session via logout.
        """
        identity = decode_v2_session(
            self.cipher, request.cookies.get("rewind_session", ""), self.settings.oidc_issuer
        )
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if not hmac.compare_digest(
                request.headers.get("x-rewind-csrf", "").encode(), identity.csrf.encode()
            ):
                raise HTTPException(403, "Missing CSRF token.")
            if request.headers.get("origin") != self.settings.public_url.rstrip("/"):
                raise HTTPException(403, "Invalid request origin.")
        return Principal(identity.principal, identity.csrf)

    def principal(self, request: Request) -> Principal:
        header = request.headers.get("authorization")
        if header is None:
            return self.session(request)
        if not header.startswith("Bearer "):
            raise IdentityInvalid()
        token = header[7:]
        if not 1 <= len(token) <= 256 or not token.isascii():
            raise IdentityInvalid()
        bootstrap = self.settings.bootstrap_key
        if bootstrap is not None and hmac.compare_digest(token, bootstrap.get_secret_value()):
            raise IdentityInvalid()
        # Bootstrap is an operator credential, never a customer API identity.
        # Select only bounded credential fields; role is evaluated freshly by
        # RequestAuthority, never copied into this authenticated identity.
        try:
            with self.db.engine.connect() as connection:
                safe = and_(
                    _byte_length(connection, keys.c.id) == 32,
                    _byte_length(connection, keys.c.expires) <= 64,
                )
                rows = (
                    connection.execute(
                        select(
                            case((safe, keys.c.id), else_=None).label("id"),
                            case((safe, keys.c.expires), else_=None).label("expires"),
                        )
                        .where(
                            keys.c.hash == hashlib.sha256(token.encode("ascii")).hexdigest(),
                            keys.c.revoked.is_(False),
                        )
                        .limit(2)
                    )
                    .mappings()
                    .all()
                )
        except SQLAlchemyError:
            raise RepositoryUnavailable() from None
        if len(rows) != 1:
            raise IdentityInvalid()
        expires = rows[0]["expires"]
        if (
            type(expires) not in {int, float}
            or not math.isfinite(expires)
            or expires <= time.time()
        ):
            raise IdentityInvalid()
        return Principal(VerifiedPrincipal.service_key(rows[0]["id"]))

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
            if self.jwks is None:
                raise ValueError("Identity provider signing keys are unavailable.")
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
            identity = SessionIdentity(
                VerifiedPrincipal.oidc(self.settings.oidc_issuer, claims["sub"]),
                self.settings.oidc_issuer,
                claims["sub"],
                secrets.token_urlsafe(32),
            )
            session = encode_v2_session(self.cipher, identity)
        except (InvalidToken, ValueError, TypeError, KeyError, httpx.HTTPError, jwt.PyJWTError):
            raise HTTPException(401, "Identity login failed.") from None
        result = RedirectResponse("/")
        result.delete_cookie("rewind_login", path="/auth")
        result.set_cookie(
            "rewind_session",
            session,
            max_age=900,
            httponly=True,
            secure=self.secure,
            samesite="lax",
        )
        self.db.audit(identity.principal.principal_id, "identity.login", "session")
        return result
