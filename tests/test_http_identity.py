"""Real credential validation, independent of synthetic active-route fixtures."""

import math
import time

import pytest
from pydantic import SecretStr
from sqlalchemy import event, text
from starlette.requests import Request

from agent_rewind.auth import Auth
from agent_rewind.models import canonical
from agent_rewind.request_identity import (
    IdentityInvalid,
    SessionIdentity,
    VerifiedPrincipal,
    encode_v2_session,
)
from agent_rewind.scoped_repositories import RepositoryUnavailable


def request(token=None, cookie=None, method="GET", csrf=None, origin=None):
    headers = []
    for name, value in (
        ("authorization", token),
        ("cookie", cookie),
        ("x-rewind-csrf", csrf),
        ("origin", origin),
    ):
        if value is not None:
            headers.append((name.encode(), value.encode()))
    return Request({"type": "http", "method": method, "path": "/api/me", "headers": headers})


def test_cookie_v2_issuer_binding_and_no_bootstrap(settings, storage):
    db, _ = storage
    settings.oidc_issuer = "https://identity.invalid"
    auth = Auth(settings, db)
    principal = VerifiedPrincipal.oidc(settings.oidc_issuer, "person")
    cookie = encode_v2_session(
        auth.cipher, SessionIdentity(principal, settings.oidc_issuer, "person", "n" * 32)
    )
    value = auth.principal(request(cookie="rewind_session=" + cookie))
    assert value.verified == principal and value.csrf == "n" * 32
    assert value.subject == principal.principal_id and not hasattr(value, "role")
    for payload in (
        {"sub": "person", "role": "administrator", "csrf": "n" * 32},
        {"version": 1, "sub": "person"},
    ):
        old = auth.cipher.encrypt(canonical(payload)).decode()
        with pytest.raises(IdentityInvalid):
            auth.principal(request(cookie="rewind_session=" + old))
    # Even an accidentally persisted matching hash cannot turn the operator
    # bootstrap setting into a customer credential.
    db.issue_key(
        settings.bootstrap_key.get_secret_value(),
        "operator",
        "collision",
        time.time() + 1000,
        "fixture",
    )
    with pytest.raises(IdentityInvalid):
        auth.principal(request(token="Bearer " + settings.bootstrap_key.get_secret_value()))
    settings.oidc_issuer = "https://different.invalid"
    with pytest.raises(IdentityInvalid):
        auth.principal(request(cookie="rewind_session=" + cookie))


@pytest.mark.parametrize(
    "field,value",
    [
        ("expires", "never"),
        ("expires", b""),
        ("expires", math.inf),
        ("expires", -math.inf),
        ("expires", time.time() - 1),
        ("revoked", ""),
        ("revoked", b""),
        ("revoked", 1),
    ],
)
def test_key_invalid_dynamic_cells_never_authenticate(settings, storage, field, value):
    db, _ = storage
    auth = Auth(settings, db)
    key_id = db.issue_key("valid-token", "operator", "test", time.time() + 1000, "fixture")
    assert auth.principal(
        request(token="Bearer valid-token")
    ).verified == VerifiedPrincipal.service_key(key_id)
    with db.engine.begin() as connection:
        connection.execute(text(f"UPDATE api_keys SET {field}=:value"), {"value": value})
    with pytest.raises(IdentityInvalid):
        auth.principal(request(token="Bearer valid-token"))


def test_key_credential_prefetch_bound_and_real_database_failure(settings, storage, monkeypatch):
    db, _ = storage
    auth = Auth(settings, db)
    db.issue_key("token", "operator", "test", time.time() + 1000, "fixture")
    with db.engine.begin() as connection:
        connection.execute(text("UPDATE api_keys SET expires=:value"), {"value": "x" * 100000})
    # The body SELECT must retain its CASE bound, so it cannot rely solely on
    # a prior size query or a Python check after fetching the oversized cell.
    selected = []

    def statement(connection, cursor, sql, parameters, context, many):
        if sql.startswith("SELECT"):
            selected.append(sql)

    event.listen(db.engine, "before_cursor_execute", statement)
    with pytest.raises(IdentityInvalid):
        auth.principal(request(token="Bearer token"))
    assert selected and "CASE WHEN" in selected[-1]
    with db.engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE api_keys")
    with pytest.raises(RepositoryUnavailable):
        auth.principal(request(token="Bearer token"))


def test_non_ascii_bootstrap_does_not_break_service_key_authentication(settings, storage):
    db, _ = storage
    settings.bootstrap_key = SecretStr("é" * 32)
    auth = Auth(settings, db)
    key_id = db.issue_key("scoped-token", "operator", "test", time.time() + 1000, "fixture")
    assert auth.principal(
        request(token="Bearer scoped-token")
    ).verified == VerifiedPrincipal.service_key(key_id)
    # Accepted configuration cannot turn the operator-only secret into an HTTP
    # identity, even if an accidental matching legacy key hash exists.
    bootstrap = settings.bootstrap_key.get_secret_value()
    db.issue_key(bootstrap, "operator", "collision", time.time() + 1000, "fixture")
    with pytest.raises(IdentityInvalid):
        auth.principal(request(token="Bearer " + bootstrap))
