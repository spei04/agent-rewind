"""Actual PostgreSQL HTTP credential lookup, without route/release activation.

Only api_keys credential columns are readable by the synthetic app role. The
real Auth method and driver execute; no active-schema fixture, provider call,
mock result row or mutation adapter participates.
"""

import hashlib

import pytest
import test_migrations_postgres as migrations
from sqlalchemy import event, insert, select, text
from test_http_identity import request

from agent_rewind.auth import Auth
from agent_rewind.database import Database, audit, keys
from agent_rewind.request_identity import IdentityInvalid, VerifiedPrincipal
from agent_rewind.scoped_repositories import RepositoryUnavailable

pg = migrations.pg
pytestmark = pytest.mark.skipif(not migrations.POSTGRES, reason="Opt-in synthetic PostgreSQL")
KEY_ID = "a" * 32
TOKEN = "synthetic-http-credential"
EXPIRES = 253402300799.0


@pytest.fixture
def credential(pg, settings):
    migrations.service.install(pg["owner"], "synthetic-http-identity")
    with pg["owner"].begin() as connection:
        connection.execute(
            insert(keys).values(
                id=KEY_ID,
                hash=hashlib.sha256(TOKEN.encode()).hexdigest(),
                role="administrator",
                name="synthetic-secret-name-not-selected",
                expires=EXPIRES,
                revoked=False,
            )
        )
        connection.exec_driver_sql(
            "GRANT SELECT(id,hash,expires,revoked) ON api_keys TO " + pg["app_role"]
        )

    # Auth needs only the fixture-owned actual engine. Avoid constructing another
    # pool or invoking migration/schema/provider methods during authentication.
    db = object.__new__(Database)
    db.engine = pg["app"]
    auth = Auth(settings, db)

    def read_only(connection):
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")

    event.listen(pg["app"], "begin", read_only)
    try:
        yield auth
    finally:
        event.remove(pg["app"], "begin", read_only)


def authenticate(auth, token=TOKEN):
    return auth.principal(request(token="Bearer " + token))


def test_postgres_http_credential_lookup_uses_only_bounded_credential_columns(pg, credential):
    statements, columns = [], []

    def observed(connection, cursor, statement, parameters, context, many):
        if statement.startswith("SELECT"):
            statements.append(statement)
            columns.append(tuple(item[0] for item in cursor.description))

    with pg["app"].connect() as connection:
        assert connection.exec_driver_sql("SHOW transaction_read_only").scalar_one() == "on"
        assert connection.execute(
            text(
                "SELECT has_column_privilege(current_user,'api_keys','id','SELECT'),"
                "has_column_privilege(current_user,'api_keys','role','SELECT'),"
                "has_column_privilege(current_user,'api_keys','name','SELECT'),"
                "has_table_privilege(current_user,'api_keys','UPDATE'),"
                "has_table_privilege(current_user,'audit','INSERT'),"
                "has_schema_privilege(current_user,'public','CREATE')"
            )
        ).one() == (True, False, False, False, False, False)
    with pg["owner"].connect() as connection:
        before = connection.execute(select(keys)).mappings().all()
    event.listen(pg["app"], "after_cursor_execute", observed)
    try:
        identity = authenticate(credential)
    finally:
        event.remove(pg["app"], "after_cursor_execute", observed)
    assert identity.verified == VerifiedPrincipal.service_key(KEY_ID)
    assert identity.subject == "api-key:" + KEY_ID and identity.csrf == ""
    assert not hasattr(identity, "role")
    assert len(statements) == 1 and columns == [("id", "expires")]
    assert "CASE WHEN" in statements[0] and "LIMIT" in statements[0]
    assert "FOR UPDATE" not in statements[0] and "FOR SHARE" not in statements[0]
    with pg["owner"].connect() as connection:
        assert connection.execute(select(keys)).mappings().all() == before
        assert connection.execute(select(audit.c.id)).all() == []


@pytest.mark.parametrize("expires", ["NaN", "Infinity", "-Infinity", "0"])
def test_postgres_http_credential_nonfinite_or_expired_value_is_not_identity(
    pg, credential, expires
):
    assert authenticate(credential).verified == VerifiedPrincipal.service_key(KEY_ID)
    with pg["owner"].begin() as connection:
        connection.execute(
            text("UPDATE api_keys SET expires=CAST(:value AS double precision) WHERE id=:id"),
            {"value": expires, "id": KEY_ID},
        )
    with pytest.raises(IdentityInvalid, match="^Authentication required\\.$"):
        authenticate(credential)


@pytest.mark.parametrize("changed", ["revoked", "expires"])
def test_postgres_http_credential_checks_observe_committed_changes_not_cached_identity(
    pg, credential, changed
):
    assert authenticate(credential).subject == "api-key:" + KEY_ID
    with pg["owner"].connect() as writer:
        writer.execute(
            text(
                "UPDATE api_keys SET "
                + ("revoked=true" if changed == "revoked" else "expires=0")
                + " WHERE id=:id"
            ),
            {"id": KEY_ID},
        )
        # READ COMMITTED must see the prior committed credential while the owner
        # change is uncommitted, then refuse on the next call after commit.
        assert authenticate(credential).subject == "api-key:" + KEY_ID
        writer.commit()
    with pytest.raises(IdentityInvalid):
        authenticate(credential)


def test_postgres_http_missing_credential_and_invalid_id_fail_without_authority(pg, credential):
    with pytest.raises(IdentityInvalid):
        authenticate(credential, "different-synthetic-token")
    with pg["owner"].begin() as connection:
        connection.execute(
            text("UPDATE api_keys SET id=:invalid WHERE id=:id"),
            {"invalid": "not-hex", "id": KEY_ID},
        )
    # VARCHAR permits this shorter ID; SQL CASE must NULL both descriptor cells
    # rather than trusting it as a principal. No membership/scope query is allowed
    # by the role, so a failed credential cannot acquire project authority.
    with pytest.raises(IdentityInvalid):
        authenticate(credential)


def test_postgres_http_lookup_permission_failure_is_fixed_and_not_an_identity(pg, credential):
    assert authenticate(credential).subject == "api-key:" + KEY_ID
    with pg["owner"].begin() as connection:
        connection.exec_driver_sql("REVOKE SELECT(expires) ON api_keys FROM " + pg["app_role"])
    with pytest.raises(RepositoryUnavailable, match="^Resource service unavailable\\.$") as failure:
        authenticate(credential)
    assert TOKEN not in str(failure.value) and pg["app_role"] not in str(failure.value)
    with pg["owner"].connect() as connection:
        assert connection.execute(select(audit.c.id)).all() == []
