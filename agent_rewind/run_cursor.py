"""Deterministic scoped cursor codec; a signed position is never authorization."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .errors import Fault
from .models import canonical

MAX_CURSOR_BYTES = 2048
MAX_SEQUENCE = 2**63 - 1
CURSOR_TTL_SECONDS = 900
DOMAIN = b"agent-rewind:run-list:v1\0"
FIELDS = frozenset(
    {
        "v",
        "project",
        "principal",
        "filters",
        "limit",
        "watermark",
        "last_created_at",
        "last_id",
        "expires_at",
    }
)


def _fail() -> None:
    raise Fault("invalid_cursor")


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    if not value or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None:
        _fail()
    try:
        decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except ValueError:
        raise Fault("invalid_cursor") from None
    if _encode(decoded) != value:
        _fail()
    return decoded


def _members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            _fail()
        value[key] = item
    return value


def _integer(value: str) -> int:
    if len(value) > 19:
        _fail()
    return int(value)


def _unsupported(value: str) -> None:
    _fail()


def _clock(now: datetime) -> int:
    # Clock failure is a dependency issue, never a caller cursor diagnostic.
    if type(now) is not datetime or now.utcoffset() is None:
        raise Fault("dependency_unavailable")
    seconds = int(now.timestamp())
    if not 0 <= seconds <= MAX_SEQUENCE - CURSOR_TTL_SECONDS:
        raise Fault("dependency_unavailable")
    return seconds


def initial_expiry(now: datetime) -> int:
    """Trusted initial clock; carry this expiry unchanged through continuation."""
    return _clock(now) + CURSOR_TTL_SECONDS


def page_limit(value: int | None) -> int:
    if value is None:
        return 50
    if type(value) is not int or not 1 <= value <= 200:
        raise Fault("invalid_request")
    return value


def utc_text(value: datetime) -> str:
    if type(value) is not datetime or value.utcoffset() is None:
        _fail()
    return value.astimezone(UTC).isoformat(timespec="microseconds")


@dataclass(frozen=True)
class CursorPosition:
    limit: int
    watermark: int
    last_created_at: datetime
    last_id: str
    expires_at: int


def _position(value: Any, project: str, principal: str, now: datetime) -> CursorPosition:
    seconds = _clock(now)
    if (
        type(value) is not dict
        or set(value) != FIELDS
        or type(value["v"]) is not int
        or value["v"] != 1
        or type(project) is not str
        or re.fullmatch(r"[0-9a-f]{32}", project) is None
        or type(principal) is not str
        or re.fullmatch(r"(?:oidc:[0-9a-f]{64}|api-key:[0-9a-f]{32})", principal) is None
        or value["project"] != project
        or value["principal"] != principal
        or type(value["filters"]) is not dict
        or value["filters"] != {}
        or type(value["limit"]) is not int
        or not 1 <= value["limit"] <= 200
        or type(value["watermark"]) is not int
        or not 0 <= value["watermark"] <= MAX_SEQUENCE
        or type(value["expires_at"]) is not int
        or not seconds < value["expires_at"] <= seconds + CURSOR_TTL_SECONDS
        or type(value["last_id"]) is not str
        or re.fullmatch(r"[0-9a-f]{32}", value["last_id"]) is None
        or type(value["last_created_at"]) is not str
    ):
        _fail()
    try:
        created = datetime.fromisoformat(value["last_created_at"])
        if utc_text(created) != value["last_created_at"]:
            _fail()
    except (ValueError, OverflowError):
        raise Fault("invalid_cursor") from None
    return CursorPosition(
        value["limit"], value["watermark"], created, value["last_id"], value["expires_at"]
    )


@dataclass(frozen=True)
class CursorCodec:
    """Key supplied by trusted configuration; no environment or clock reads."""

    key: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.key) is not bytes or len(self.key) != 32:
            raise Fault("dependency_unavailable")

    def encode(
        self, project: str, principal: str, position: CursorPosition, *, now: datetime
    ) -> str:
        value = {
            "v": 1,
            "project": project,
            "principal": principal,
            "filters": {},
            "limit": position.limit,
            "watermark": position.watermark,
            "last_created_at": utc_text(position.last_created_at),
            "last_id": position.last_id,
            "expires_at": position.expires_at,
        }
        _position(value, project, principal, now)
        payload = canonical(value)
        token = (
            _encode(payload)
            + "."
            + _encode(hmac.digest(self.key, DOMAIN + payload, hashlib.sha256))
        )
        if len(token) > MAX_CURSOR_BYTES:
            _fail()
        return token

    def decode(
        self, token: str, project: str, principal: str, *, now: datetime, limit: int | None = None
    ) -> CursorPosition:
        # Bound characters before encoding/decoding, including hostile Unicode.
        if type(token) is not str or len(token) > MAX_CURSOR_BYTES or not token.isascii():
            _fail()
        parts = token.split(".")
        if len(parts) != 2:
            _fail()
        payload, signature = _decode(parts[0]), _decode(parts[1])
        if len(signature) != 32 or not hmac.compare_digest(
            signature, hmac.digest(self.key, DOMAIN + payload, hashlib.sha256)
        ):
            _fail()
        try:
            value = json.loads(
                payload.decode("utf-8"),
                object_pairs_hook=_members,
                parse_int=_integer,
                parse_float=_unsupported,
                parse_constant=_unsupported,
            )
            if canonical(value) != payload:
                _fail()
        except (ValueError, TypeError, RecursionError, OverflowError):
            raise Fault("invalid_cursor") from None
        position = _position(value, project, principal, now)
        if limit is not None and (type(limit) is not int or limit != position.limit):
            _fail()
        return position
