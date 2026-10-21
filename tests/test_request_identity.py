import json
import time
from unittest.mock import Mock

import pytest
from cryptography.fernet import Fernet

from agent_rewind.models import canonical
from agent_rewind.request_identity import (
    MAX_TOKEN_BYTES,
    SESSION_SECONDS,
    IdentityInvalid,
    SessionIdentity,
    VerifiedPrincipal,
    decode_v2_session,
    encode_v2_session,
)

ISSUER = "https://identity.synthetic.invalid"
SUBJECT = "same-subject"
CSRF = "n" * 43


def identity(issuer=ISSUER, subject=SUBJECT):
    return SessionIdentity(VerifiedPrincipal.oidc(issuer, subject), issuer, subject, CSRF)


@pytest.fixture
def cipher():
    return Fernet(Fernet.generate_key())


def test_exact_issuer_and_subject_identity_and_v2_roundtrip(cipher):
    original = identity()
    token = encode_v2_session(cipher, original)
    assert decode_v2_session(cipher, token, ISSUER) == original
    assert original.principal != identity(ISSUER + "/").principal
    assert original.principal != identity(ISSUER.upper()).principal
    assert identity(subject="é").principal != identity(subject="e\u0301").principal
    assert set(original.record()) == {"version", "principal_id", "issuer", "subject", "csrf"}


@pytest.mark.parametrize(
    "principal", ["bootstrap", "subject", "administrator", "api-key:abc", None]
)
def test_only_namespaced_identity_supported(principal):
    with pytest.raises(IdentityInvalid, match="^Authentication required.$"):
        VerifiedPrincipal(principal)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("version", 1),
        ("version", True),
        ("version", 2.0),
        ("principal_id", "api-key:" + "a" * 32),
        ("principal_id", "oidc:" + "0" * 64),
        ("issuer", ISSUER + "/"),
        ("subject", ""),
        ("subject", []),
        ("csrf", ""),
        ("csrf", "x" * 129),
        ("csrf", ["private-canary"]),
    ],
)
def test_strict_session_fields_are_rejected_with_fixed_error(cipher, field, value):
    record = {**identity().record(), field: value}
    token = cipher.encrypt(canonical(record)).decode()
    with pytest.raises(IdentityInvalid, match="^Authentication required.$"):
        decode_v2_session(cipher, token, ISSUER)


@pytest.mark.parametrize("variant", ["old", "extra", "missing", "array", "duplicate", "nonfinite"])
def test_old_extra_missing_duplicate_and_nonobject_sessions_rejected(cipher, variant):
    record = identity().record()
    if variant == "old":
        body = canonical({"sub": SUBJECT, "role": "administrator", "csrf": CSRF})
    elif variant == "extra":
        body = canonical({**record, "role": "administrator"})
    elif variant == "missing":
        del record["csrf"]
        body = canonical(record)
    elif variant == "array":
        body = b"[]"
    elif variant == "duplicate":
        body = canonical(record)[:-1] + b', "ver\\u0073ion": 2}'
    else:
        body = b'{"version": NaN}'
    with pytest.raises(IdentityInvalid, match="^Authentication required.$"):
        decode_v2_session(cipher, cipher.encrypt(body).decode(), ISSUER)


def test_current_issuer_expiry_and_signature_are_required(cipher):
    token = encode_v2_session(cipher, identity())
    other_cipher = Fernet(Fernet.generate_key())
    with pytest.raises(IdentityInvalid):
        decode_v2_session(other_cipher, token, ISSUER)
    with pytest.raises(IdentityInvalid):
        decode_v2_session(cipher, token, "https://another.synthetic.invalid")
    expired = cipher.encrypt_at_time(
        canonical(identity().record()), int(time.time()) - SESSION_SECONDS - 10
    )
    with pytest.raises(IdentityInvalid):
        decode_v2_session(cipher, expired.decode(), ISSUER)


@pytest.mark.parametrize("token", ["x" * (MAX_TOKEN_BYTES + 1), "", None, b"binary"])
def test_bound_precedes_decrypt(token):
    cipher = Mock()
    with pytest.raises(IdentityInvalid):
        decode_v2_session(cipher, token, ISSUER)
    cipher.decrypt.assert_not_called()


def test_key_factory_requires_exact_verified_identifier():
    assert VerifiedPrincipal.service_key("a" * 32).principal_id == "api-key:" + "a" * 32
    with pytest.raises(IdentityInvalid):
        VerifiedPrincipal.service_key("a" * 32 + "\0hidden")


def test_issuerless_or_mismatched_session_cannot_be_encoded(cipher):
    with pytest.raises(IdentityInvalid):
        SessionIdentity(VerifiedPrincipal.service_key("a" * 32), ISSUER, SUBJECT, CSRF)
    with pytest.raises(IdentityInvalid):
        encode_v2_session(cipher, {"role": "administrator"})


def test_unicode_surrogate_session_is_fixed_refusal(cipher):
    record = identity().record()
    record["subject"] = "\ud800"
    token = cipher.encrypt(json.dumps(record).encode()).decode()
    with pytest.raises(IdentityInvalid):
        decode_v2_session(cipher, token, ISSUER)
