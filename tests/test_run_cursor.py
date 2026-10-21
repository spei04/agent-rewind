"""Real signatures plus independently signed malformed payloads exercise the codec."""

import base64
import hashlib
import hmac
import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta

import pytest

from agent_rewind.config import Settings
from agent_rewind.cursor_config import cursor_codec
from agent_rewind.errors import Fault
from agent_rewind.models import canonical
from agent_rewind.run_cursor import (
    DOMAIN,
    CursorCodec,
    CursorPosition,
    initial_expiry,
    page_limit,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
PROJECT = "a" * 32
PRINCIPAL = "oidc:" + "b" * 64
KEY = b"k" * 32
CODEC = CursorCodec(KEY)
POSITION = CursorPosition(50, 20, NOW - timedelta(days=2), "c" * 32, initial_expiry(NOW))


def encoded(data):
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def signed(payload, *, domain=DOMAIN):
    return encoded(payload) + "." + encoded(hmac.digest(KEY, domain + payload, hashlib.sha256))


def payload():
    token = CODEC.encode(PROJECT, PRINCIPAL, POSITION, now=NOW)
    return json.loads(base64.urlsafe_b64decode(token.split(".")[0] + "=="))


def decode(token, **kwargs):
    return CODEC.decode(token, PROJECT, PRINCIPAL, now=NOW, **kwargs)


def invalid(token, **kwargs):
    with pytest.raises(Fault) as failure:
        decode(token, **kwargs)
    assert failure.value.code == "invalid_cursor"


def test_round_trip_omitted_limit_explicit_clock_and_no_renewal():
    token = CODEC.encode(PROJECT, PRINCIPAL, POSITION, now=NOW)
    assert decode(token) == POSITION
    assert decode(token, limit=50) == POSITION
    later = NOW + timedelta(seconds=899)
    position = CODEC.decode(token, PROJECT, PRINCIPAL, now=later)
    next_token = CODEC.encode(PROJECT, PRINCIPAL, replace(position, last_id="d" * 32), now=later)
    assert CODEC.decode(next_token, PROJECT, PRINCIPAL, now=later).expires_at == POSITION.expires_at
    with pytest.raises(Fault, match="invalid_cursor"):
        CODEC.decode(next_token, PROJECT, PRINCIPAL, now=NOW + timedelta(seconds=900))
    with pytest.raises(FrozenInstanceError):
        position.limit = 10
    assert KEY.decode() not in repr(CODEC)


@pytest.mark.parametrize("principal", [PRINCIPAL, "api-key:" + "b" * 32])
@pytest.mark.parametrize("limit", [1, 200])
@pytest.mark.parametrize("watermark", [0, 2**63 - 1])
def test_supported_scope_limit_and_sequence_bounds(principal, limit, watermark):
    position = replace(POSITION, limit=limit, watermark=watermark)
    token = CODEC.encode(PROJECT, principal, position, now=NOW)
    assert CODEC.decode(token, PROJECT, principal, now=NOW) == position


@pytest.mark.parametrize(
    "field,value",
    [
        ("v", True),
        ("v", 2),
        ("project", "d" * 32),
        ("principal", "oidc:" + "d" * 64),
        ("principal", "b" * 64),
        ("filters", []),
        ("filters", {"status": "complete"}),
        ("limit", True),
        ("limit", 0),
        ("limit", 201),
        ("limit", 50.0),
        ("watermark", True),
        ("watermark", -1),
        ("watermark", 2**63),
        ("expires_at", True),
        ("expires_at", int(NOW.timestamp())),
        ("expires_at", int(NOW.timestamp()) + 901),
        ("last_id", "C" * 32),
        ("last_id", "c" * 32 + "\0"),
        ("last_created_at", "2025-12-30T00:00:00Z"),
        ("last_created_at", "2025-12-30T00:00:00+00:00"),
        ("last_created_at", "2025-12-30T01:00:00.000000+01:00"),
        ("last_created_at", "2025-12-30T00:00:00.000000"),
        ("last_created_at", None),
        ("last_created_at", "not-a-date"),
    ],
)
def test_authenticated_but_unsupported_payload_refuses(field, value):
    value_dict = payload()
    value_dict[field] = value
    invalid(signed(canonical(value_dict)))


@pytest.mark.parametrize("field", sorted(payload()))
def test_every_frozen_member_required(field):
    value = payload()
    del value[field]
    invalid(signed(canonical(value)))


def test_unknown_member_and_noncanonical_json():
    value = payload()
    invalid(signed(canonical({**value, "extra": 1})))
    invalid(signed(json.dumps(value, indent=1).encode()))
    raw = canonical(value)
    invalid(signed(raw[:-1] + b',"limit":50}'))
    invalid(signed(raw[:-1] + b',"\\u006cimit":50}'))
    invalid(signed(b"[]"))
    invalid(signed(b"\xff"))
    invalid(signed(b'{"v":NaN}'))
    invalid(signed(b'{"v":12345678901234567890}'))


@pytest.mark.parametrize("token", ["", ".", "x", "a.b.c", "é", "a" * 2049, "a=.b", "a.b="])
def test_token_shape_bounded_before_decode(token):
    invalid(token)


def test_noncanonical_base64_alias_and_wrong_mac_domain():
    value = canonical(payload())
    good = CODEC.encode(PROJECT, PRINCIPAL, POSITION, now=NOW)
    a, b = good.split(".")
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    # SHA256's unpadded final sextet has two zero padding bits.
    alias = b[:-1] + alphabet[alphabet.index(b[-1]) + 1]
    invalid(a + "." + alias)
    invalid(signed(value, domain=b"other-domain"))
    invalid(encoded(value) + "." + encoded(b"x" * 31))
    invalid(encoded(value + b" ") + "." + b)


@pytest.mark.parametrize("limit", [0, 49, 200, True, "50"])
def test_explicit_continuation_limit_must_equal_signed_value(limit):
    invalid(CODEC.encode(PROJECT, PRINCIPAL, POSITION, now=NOW), limit=limit)


def test_rotation_and_foreign_scope_refuse():
    token = CODEC.encode(PROJECT, PRINCIPAL, POSITION, now=NOW)
    for codec, project, principal in [
        (CursorCodec(b"r" * 32), PROJECT, PRINCIPAL),
        (CODEC, "d" * 32, PRINCIPAL),
        (CODEC, PROJECT, "oidc:" + "d" * 64),
    ]:
        with pytest.raises(Fault, match="invalid_cursor"):
            codec.decode(token, project, principal, now=NOW)


@pytest.mark.parametrize("value", [True, 0, 201, 50.0, "50"])
def test_initial_limit_strict(value):
    with pytest.raises(Fault, match="invalid_request"):
        page_limit(value)


def test_initial_default_and_invalid_clock():
    assert page_limit(None) == 50
    assert page_limit(200) == 200
    with pytest.raises(Fault, match="dependency_unavailable"):
        initial_expiry(datetime(2026, 1, 1))


def settings(secret):
    return Settings(
        encryption_key=encoded(b"e" * 32) + "=",
        cursor_signing_key=secret,
        _env_file=None,
    )


@pytest.mark.parametrize(
    "secret", [None, "", "x", "é" * 43, "a" * 44, "a" * 42, encoded(b"e" * 32)]
)
def test_bad_key_is_lazy_and_list_only(secret):
    configured = settings(secret)
    # Settings creation is valid, preserving unrelated surfaces.
    assert configured.mode == "development"
    with pytest.raises(Fault) as failure:
        cursor_codec(configured)
    assert failure.value.code == "dependency_unavailable"
    assert str(secret) not in str(failure.value) or secret == ""


def test_key_canonical_bits_and_no_secret_repr():
    value = encoded(KEY)
    assert cursor_codec(settings(value)) == CODEC
    assert value not in repr(settings(value))
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    alias = value[:-1] + alphabet[alphabet.index(value[-1]) + 1]
    with pytest.raises(Fault, match="dependency_unavailable"):
        cursor_codec(settings(alias))


def test_signature_is_verified_before_json(monkeypatch):
    token = CODEC.encode(PROJECT, PRINCIPAL, POSITION, now=NOW)

    def forbidden(*args, **kwargs):
        raise AssertionError("unauthenticated JSON must not parse")

    monkeypatch.setattr("agent_rewind.run_cursor.json.loads", forbidden)
    invalid(token[:-43] + encoded(b"z" * 32))
