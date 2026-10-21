"""Strict v2 identity/session helpers, not yet wired to HTTP authentication.

Principal construction is not credential verification. Only a trusted
authenticator may call the factories after the documented OIDC/token checks.
No cookie role, bootstrap credential or organization role grants project access.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from .bounded_bytes import ciphertext_limit
from .models import canonical
from .ownership import oidc_principal_id

MAX_SESSION_BYTES = 40 * 1024
MAX_TOKEN_BYTES = ciphertext_limit(MAX_SESSION_BYTES)
SESSION_SECONDS = 900


class IdentityInvalid(ValueError):
    """Authentication failure, mapped to a fixed 401 by the later HTTP consumer."""

    def __init__(self) -> None:
        super().__init__("Authentication required.")


@dataclass(frozen=True)
class VerifiedPrincipal:
    """A trusted authenticator's identity; this object grants no project rights."""

    principal_id: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.principal_id, str)
            or re.fullmatch(r"(oidc:[0-9a-f]{64}|api-key:[0-9a-f]{32})", self.principal_id) is None
        ):
            raise IdentityInvalid()

    @classmethod
    def oidc(cls, issuer: str, subject: str) -> VerifiedPrincipal:
        """After exact issuer/audience/signature/nonce/expiry validation only."""
        try:
            return cls(oidc_principal_id(issuer, subject))
        except (ValueError, TypeError, UnicodeError):
            raise IdentityInvalid() from None

    @classmethod
    def service_key(cls, key_id: str) -> VerifiedPrincipal:
        """After matching the supplied token to its valid persisted key only."""
        if not isinstance(key_id, str) or re.fullmatch(r"[0-9a-f]{32}", key_id) is None:
            raise IdentityInvalid()
        return cls("api-key:" + key_id)


@dataclass(frozen=True)
class SessionIdentity:
    principal: VerifiedPrincipal
    issuer: str
    subject: str
    csrf: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.principal, VerifiedPrincipal)
            or self.principal != VerifiedPrincipal.oidc(self.issuer, self.subject)
            or not isinstance(self.csrf, str)
            or re.fullmatch(r"[A-Za-z0-9_-]{32,128}", self.csrf) is None
        ):
            raise IdentityInvalid()

    def record(self) -> dict[str, Any]:
        return {
            "version": 2,
            "principal_id": self.principal.principal_id,
            "issuer": self.issuer,
            "subject": self.subject,
            "csrf": self.csrf,
        }


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in items:
        if key in value:
            raise IdentityInvalid()
        value[key] = item
    return value


def _constant(value: str) -> None:
    raise IdentityInvalid()


def encode_v2_session(cipher: Fernet, identity: SessionIdentity) -> str:
    """Encode only; setting cookies and changing Auth belong to route integration."""
    try:
        identity.__post_init__()
        encoded = canonical(identity.record())
        if len(encoded) > MAX_SESSION_BYTES:
            raise IdentityInvalid()
        return cipher.encrypt(encoded).decode("ascii")
    except (AttributeError, TypeError, ValueError, UnicodeError, RecursionError):
        raise IdentityInvalid() from None


def decode_v2_session(cipher: Fernet, token: str, expected_issuer: str) -> SessionIdentity:
    """Authenticate a bounded v2 token against the currently configured issuer."""
    try:
        if (
            not isinstance(token, str)
            or not 1 <= len(token) <= MAX_TOKEN_BYTES
            or not isinstance(expected_issuer, str)
            or not 1 <= len(expected_issuer) <= 4096
        ):
            raise IdentityInvalid()
        data = cipher.decrypt(token.encode("ascii"), ttl=SESSION_SECONDS)
        if len(data) > MAX_SESSION_BYTES:
            raise IdentityInvalid()
        value = json.loads(data, object_pairs_hook=_pairs, parse_constant=_constant)
        if (
            not isinstance(value, dict)
            or set(value) != {"version", "principal_id", "issuer", "subject", "csrf"}
            or type(value["version"]) is not int
            or value["version"] != 2
            or value["issuer"] != expected_issuer
        ):
            raise IdentityInvalid()
        return SessionIdentity(
            VerifiedPrincipal(value["principal_id"]),
            value["issuer"],
            value["subject"],
            value["csrf"],
        )
    except (InvalidToken, TypeError, ValueError, KeyError, UnicodeError, RecursionError):
        raise IdentityInvalid() from None
