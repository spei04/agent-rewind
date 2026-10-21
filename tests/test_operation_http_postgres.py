"""Independent operation HTTP proof on real PostgreSQL and real app credentials.

The owner only provisions synthetic ar6 data and models concurrent administrators.
Requests use create_app's restricted engine; readiness overrides are per instance.
No IdP, provider, worker activation or customer-ready profile is implied.
"""

import asyncio
import hashlib
import re
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
import test_migrations_postgres as migrations
from fastapi.testclient import TestClient
from http_app_cleanup import http_application_cache_cleanup as http_application_cache_cleanup
from postgres_control import wait_for_database_drain
from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError
from test_admission_envelope import descriptor
from test_admission_publication_postgres import TABLES, poison_new_work, runtime, snapshot
from test_admission_repository import PROJECT
from test_admission_request import submission
from test_artifact_metadata import OTHER
from test_artifact_postgres import prepare_postgres
from test_operation_sources import roots
from test_scoped_actions_postgres import wait_blocked

from agent_rewind import operation_service
from agent_rewind.admission_coordinator import AdmissionCoordinator
from agent_rewind.api import create_app
from agent_rewind.artifact_metadata import record_verified, register_ref
from agent_rewind.database import keys
from agent_rewind.migrations.admission_service import initialize_admission
from agent_rewind.migrations.compatibility import CompatibilityResult
from agent_rewind.migrations.projection_service import initialize_projection
from agent_rewind.models import canonical
from agent_rewind.publication_journal import JournalSession
from agent_rewind.request_identity import SessionIdentity, VerifiedPrincipal, encode_v2_session

pg = migrations.pg
pytestmark = pytest.mark.skipif(
    not migrations.POSTGRES, reason="Opt-in synthetic PostgreSQL operation HTTP"
)
ISSUER = "https://pg-operation-http.invalid"
SUBJECT = "operator"
CSRF = "c" * 32
IDEMPOTENCY = "PG-http.Key:123"
KEY_ID = "d" * 32
TOKEN = "synthetic-operation-http-key"
PREFIX = "/api/v1/projects/"


def initialize(pg):
    prepare_postgres(pg)
    wait_for_database_drain(pg["control"], pg["owner"].url.database)
    initialize_projection(pg["owner"])
    wait_for_database_drain(pg["control"], pg["owner"].url.database)
    initialize_admission(pg["owner"])


def safe(response, status, code=None):
    assert response.status_code == status, response.text
    request_id = response.headers["x-request-id"]
    assert re.fullmatch("[0-9a-f]{32}", request_id)
    assert response.headers["cache-control"] == "no-store"
    value = response.json()
    if code is not None:
        assert set(value) == {"code", "message", "request_id", "retryable"}
        assert value["code"] == code and value["request_id"] == request_id
        assert type(value["retryable"]) is bool
        assert "PRIVATE" not in response.text
        if code == "outcome_uncertain":
            assert value["retryable"] is False
        if status == 401:
            assert response.headers["www-authenticate"] == "Bearer"
    return value


def cookie(app, subject=SUBJECT):
    principal = VerifiedPrincipal.oidc(ISSUER, subject)
    token = encode_v2_session(
        app.state.auth.cipher, SessionIdentity(principal, ISSUER, subject, CSRF)
    )
    return {
        "Cookie": "rewind_session=" + token,
        "X-Rewind-CSRF": CSRF,
        "Origin": app.state.auth.settings.public_url.rstrip("/"),
        "Content-Type": "application/json",
        "Idempotency-Key": IDEMPOTENCY,
    }


def headers(f, key=False):
    if not key:
        return dict(f.headers)
    return {
        "Authorization": "Bearer " + TOKEN,
        "Content-Type": "application/json",
        "Idempotency-Key": IDEMPOTENCY,
    }


def submit(f, *, body=None, request_headers=None, project=PROJECT):
    return f.client.post(
        PREFIX + project + "/runs",
        content=canonical(submission() if body is None else body),
        headers=f.headers if request_headers is None else request_headers,
    )


def operation_path(accepted, *, project=PROJECT):
    return PREFIX + project + "/operations/" + accepted["operation_id"]


def rows(f):
    return snapshot(SimpleNamespace(owner=f.owner))


def origin(f):
    with f.owner.connect() as connection:
        return connection.exec_driver_sql(
            "SELECT failure_correlation_id FROM operations"
        ).scalar_one()


def clean(f):
    assert f.engine.pool.checkedout() == 0
    with f.engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT current_setting('transaction_read_only'),"
            "current_setting('transaction_isolation')"
        ).one() == ("off", "read committed")
    assert f.engine.pool.checkedout() == 0


@pytest.fixture
def http_pg(pg, settings, tmp_path, monkeypatch):
    initialize(pg)
    principal = VerifiedPrincipal.oidc(ISSUER, SUBJECT)
    viewer = VerifiedPrincipal.oidc(ISSUER, "viewer")
    settings.database_url = pg["app"].url.render_as_string(hide_password=False)
    settings.oidc_issuer = ISSUER
    # Settings/Database stays the real application constructor and pool.
    app = create_app(settings)
    role = pg["app_role"]
    assert re.fullmatch(r"ar_migration_[0-9a-f]{32}_app", role)
    with pg["owner"].begin() as connection:
        _organization, name = connection.execute(
            text("SELECT organization_id,name FROM projects WHERE id=:id"), {"id": PROJECT}
        ).one()
        connection.execute(
            text(
                "INSERT INTO projects(id,organization_id,name,created_at) "
                "SELECT :other,organization_id,name,created_at FROM projects WHERE id=:source"
            ),
            {"other": OTHER, "source": PROJECT},
        )
        for project, identity, member_role in (
            (PROJECT, principal.principal_id, "operator"),
            (OTHER, principal.principal_id, "operator"),
            (PROJECT, viewer.principal_id, "viewer"),
            (PROJECT, "api-key:" + KEY_ID, "operator"),
        ):
            connection.execute(
                text("INSERT INTO project_memberships VALUES(:p,:id,:role,NULL,false)"),
                {"p": project, "id": identity, "role": member_role},
            )
        connection.execute(
            keys.insert().values(
                id=KEY_ID,
                hash=hashlib.sha256(TOKEN.encode("ascii")).hexdigest(),
                role="operator",
                name="synthetic-http",
                expires=time.time() + 3600,
                revoked=False,
            )
        )
        connection.execute(
            text("INSERT INTO resource_scopes VALUES('key',:id,:project)"),
            {"id": KEY_ID, "project": PROJECT},
        )
        for table in (
            "projects",
            "organizations",
            "project_memberships",
            "resource_scopes",
            "api_keys",
            "jobs",
            "records",
            "artifact_objects",
            "artifact_refs",
            "operations",
            "operation_keys",
        ):
            connection.exec_driver_sql(f"GRANT SELECT ON {table} TO {role}")
        for table, column in (
            ("projects", "id"),
            ("organizations", "id"),
            ("project_memberships", "principal_id"),
            ("resource_scopes", "resource_id"),
            ("api_keys", "id"),
            ("jobs", "id"),
            ("operations", "kind"),
        ):
            connection.exec_driver_sql(f"GRANT UPDATE({column}) ON {table} TO {role}")
        connection.exec_driver_sql(f"GRANT UPDATE(cancel,status) ON jobs TO {role}")
        for table in TABLES:
            connection.exec_driver_sql(f"GRANT INSERT ON {table} TO {role}")
    context = app.state.authority.named(principal, PROJECT).context
    f = runtime(
        app.state.db.engine,
        principal=principal,
        context=context,
        name=name,
        root=tmp_path / "journal",
        objects=settings.data_dir,
        key=settings.encryption_key.get_secret_value().encode(),
    )
    f.owner, f.pg, f.app = pg["owner"], pg, app
    app.state.operation_coordinator = f.service
    for owner in (app.state.db, f.service, app.state.operation_service):
        monkeypatch.setattr(
            owner,
            "schema_compatibility",
            lambda: CompatibilityResult("ready", "synthetic_http_only"),
        )
    # These legacy paths are not operation admission dependencies.
    forbidden = Mock(side_effect=AssertionError("PRIVATE legacy downstream path reached"))
    monkeypatch.setattr(app.state.admission, "require_available", forbidden)
    monkeypatch.setattr(app.state.readiness, "check", forbidden)
    monkeypatch.setattr(app.state.db, "enqueue", forbidden)
    f.forbidden = forbidden
    for method in ("freeze", "append"):
        original = getattr(JournalSession, method)

        def outside(session, *args, _original=original, **kwargs):
            f.outside()
            return _original(session, *args, **kwargs)

        monkeypatch.setattr(JournalSession, method, outside)
    f.headers = cookie(app)
    f.client = TestClient(app)
    before = rows(f)
    assert all(not before[table] for table in TABLES if table != "resource_scopes")
    assert not any(row["resource_kind"] == "job" for row in before["resource_scopes"])
    try:
        yield f
    finally:
        f.client.close()
        try:
            forbidden.assert_not_called()
            assert f.engine.pool.checkedout() == 0
        finally:
            for event_name, callback in f.listeners:
                event.remove(f.engine, event_name, callback)
            f.engine.dispose()


def test_postgres_http_pristine_ar6_real_guard_has_zero_customer_sinks(pg, settings, monkeypatch):
    initialize(pg)
    settings.database_url = pg["owner"].url.render_as_string(hide_password=False)
    app = create_app(settings)
    compatibility = app.state.db.schema_compatibility()
    assert (compatibility.status, compatibility.code) == ("incompatible", "migration_only")
    state = SimpleNamespace(owner=pg["owner"])
    before = snapshot(state)
    forbidden = Mock(side_effect=AssertionError("PRIVATE real guard entered customer code"))
    for owner, name in (
        (app.state.auth, "principal"),
        (app.state.authority, "named"),
        (app.state.operation_coordinator, "submit"),
        (app.state.operation_service, "read_operation"),
        (app.state.operation_service, "cancel_operation"),
        (app.state.readiness, "check"),
        (app.state.operation_service, "artifact_loader"),
        (app.state.operation_service._actions, "_cancel_effect"),
    ):
        monkeypatch.setattr(owner, name, forbidden)
    client = TestClient(app)
    try:
        for method, path in (
            ("POST", PREFIX + PROJECT + "/runs"),
            ("GET", PREFIX + PROJECT + "/operations/" + "0" * 32),
            ("POST", PREFIX + PROJECT + "/operations/" + "0" * 32 + "/cancel"),
        ):
            safe(
                client.request(method, path, content=b"{", headers={"Content-Encoding": "gzip"}),
                503,
                "schema_incompatible",
            )
        forbidden.assert_not_called()
        assert snapshot(state) == before
        assert app.state.db.schema_compatibility() == compatibility
    finally:
        client.close()
        app.state.db.engine.dispose()


@pytest.mark.parametrize("key", [False, True])
def test_postgres_http_exact_roundtrip_original_origin_alias_and_outage_replay(
    http_pg, monkeypatch, key
):
    f = http_pg
    credential = headers(f, key)
    first = submit(f, request_headers={**credential, "X-Request-ID": "attacker"})
    accepted = safe(first, 202)
    assert set(accepted) == {"operation_id", "job_id"}
    assert origin(f) == first.headers["x-request-id"] != "attacker"
    path = operation_path(accepted)
    view = safe(f.client.get(path, headers=credential), 200)
    assert view == {
        "id": accepted["operation_id"],
        "project_id": PROJECT,
        "job_id": accepted["job_id"],
        "client_operation_id": submission()["client_operation_id"],
        "status": "queued",
        "cancel_requested": False,
        "result_run_id": None,
        "budget_microusd": 1,
        "reserved_microusd": 0,
        "error": None,
    }
    assert safe(f.client.post(path + "/cancel", headers=credential), 202) == {
        "operation_id": accepted["operation_id"],
        "cancel_requested": True,
        "status": "cancelled",
    }
    poison_new_work(f, monkeypatch)
    before = rows(f)
    replay = submit(f, request_headers=credential)
    assert safe(replay, 202) == accepted
    assert replay.headers["x-request-id"] != first.headers["x-request-id"]
    assert rows(f) == before
    alias = submit(f, request_headers={**credential, "Idempotency-Key": "New-alias:456"})
    assert safe(alias, 202) == accepted
    after = rows(f)
    assert len(after["operation_keys"]) == 2
    assert after["jobs"] == before["jobs"] and after["audit"] == before["audit"]
    assert {r["key_hash"] for r in after["operation_keys"]} == {
        hashlib.sha256(IDEMPOTENCY.encode()).hexdigest(),
        hashlib.sha256(b"New-alias:456").hexdigest(),
    }
    assert len(f.storage.calls) == 3
    clean(f)


@pytest.mark.parametrize("legacy_default", [False, True])
def test_postgres_http_two_populated_projects_ignore_legacy_default(http_pg, legacy_default):
    f = http_pg
    if legacy_default:
        with f.owner.begin() as connection:
            connection.execute(
                text(
                    "UPDATE project_memberships SET legacy_default=TRUE "
                    "WHERE project_id=:p AND principal_id=:id"
                ),
                {"p": OTHER, "id": f.principal.principal_id},
            )
    first = safe(submit(f), 202)
    second = safe(submit(f, project=OTHER), 202)
    assert first != second
    for project, accepted in ((PROJECT, first), (OTHER, second)):
        value = safe(
            f.client.get(operation_path(accepted, project=project), headers=f.headers), 200
        )
        assert value["project_id"] == project and value["job_id"] == accepted["job_id"]
        foreign = OTHER if project == PROJECT else PROJECT
        safe(
            f.client.get(operation_path(accepted, project=foreign), headers=f.headers),
            404,
            "not_found",
        )
    safe(
        f.client.get(operation_path(second, project=OTHER), headers=headers(f, True)),
        404,
        "not_found",
    )
    assert len(rows(f)["operations"]) == 2


@pytest.mark.parametrize("key", [False, True])
def test_postgres_http_current_viewer_and_revocation_preserve_target_precedence(http_pg, key):
    f = http_pg
    accepted = safe(submit(f), 202)
    credential = headers(f, True) if key else cookie(f.app, "viewer")
    principal = (
        "api-key:" + KEY_ID if key else VerifiedPrincipal.oidc(ISSUER, "viewer").principal_id
    )
    if key:
        with f.owner.begin() as connection:
            connection.execute(
                text("UPDATE api_keys SET role='viewer' WHERE id=:id"), {"id": KEY_ID}
            )
    path = operation_path(accepted)
    assert safe(f.client.get(path, headers=credential), 200)["id"] == accepted["operation_id"]
    before = rows(f)
    safe(submit(f, request_headers=credential), 403, "forbidden")
    safe(f.client.post(path + "/cancel", headers=credential), 403, "forbidden")
    for identifier in ("invalid", "0" * 32):
        missing = PREFIX + PROJECT + "/operations/" + identifier + "/cancel"
        safe(f.client.post(missing, headers=credential), 404, "not_found")
    assert rows(f) == before
    with f.owner.begin() as connection:
        connection.execute(
            text("UPDATE project_memberships SET revoked_at=now() WHERE principal_id=:id"),
            {"id": principal},
        )
    safe(f.client.get(path, headers=credential), 404, "not_found")
    safe(f.client.post(path + "/cancel", headers=credential), 404, "not_found")


@pytest.mark.parametrize(
    "case", ["bad_bearer", "duplicate_bearer", "duplicate_origin", "duplicate_csrf"]
)
def test_postgres_http_actual_credentials_refuse_before_transport_and_sql_effect(http_pg, case):
    f = http_pg
    values = list(f.headers.items())
    if case == "bad_bearer":
        values.append(("Authorization", "Bearer bad"))
        expected = (401, "unauthenticated")
    elif case == "duplicate_bearer":
        values += [("Authorization", "Bearer " + TOKEN), ("authorization", "Bearer " + TOKEN)]
        expected = (401, "unauthenticated")
    else:
        name = "Origin" if case == "duplicate_origin" else "X-Rewind-CSRF"
        values.append((name.lower(), f.headers[name]))
        expected = (403, "forbidden")
    before = rows(f)
    safe(f.client.post(PREFIX + PROJECT + "/runs", content=b"{", headers=values), *expected)
    assert rows(f) == before and not f.policy.calls and not f.storage.calls


def test_postgres_http_valid_key_ignores_invalid_cookie_without_csrf_or_origin(http_pg):
    f = http_pg
    credential = {**headers(f, True), "Cookie": "rewind_session=invalid"}
    accepted = safe(submit(f, request_headers=credential), 202)
    assert (
        safe(f.client.post(operation_path(accepted) + "/cancel", headers=credential), 202)[
            "cancel_requested"
        ]
        is True
    )
    assert rows(f)["jobs"][0]["actor"] == "api-key:" + KEY_ID


@pytest.mark.parametrize("conflict", ["request", "client", "both"])
def test_postgres_http_identity_conflicts_are_fixed_409_without_new_objects(http_pg, conflict):
    f = http_pg
    safe(submit(f), 202)
    before, calls = rows(f), len(f.storage.calls)
    body = submission()
    if conflict in {"request", "both"}:
        body["budget_microusd"] = 2
    if conflict in {"client", "both"}:
        body["client_operation_id"] = "b" * 32
    safe(submit(f, body=body), 409, "idempotency_conflict")
    assert rows(f) == before and len(f.storage.calls) == calls


@pytest.mark.parametrize("phase", ["before_ack", "after_ack", "journal"])
def test_postgres_http_commit_uncertainty_retains_original_identity_and_origin(
    http_pg, monkeypatch, phase
):
    f, staged = http_pg, set()
    faults, pending = [], []
    before = rows(f)
    real_commit, real_append = Connection.commit, JournalSession.append

    def written(connection, cursor, statement, *args):
        if statement.strip().startswith("INSERT INTO audit"):
            staged.add(id(connection))

    def commit(connection):
        if connection.engine is f.engine and id(connection) in staged:
            staged.remove(id(connection))
            if phase == "after_ack":
                real_commit(connection)
            if phase != "journal":
                faults.append(phase)
                raise RuntimeError("PRIVATE lost COMMIT acknowledgement")
        return real_commit(connection)

    def append(session, kind, data):
        if phase == "journal" and kind == "commit_confirmed":
            faults.append(phase)
            raise OSError("PRIVATE durable confirmation failure")
        result = real_append(session, kind, data)
        if kind == "commit_pending":
            pending.append(kind)
        return result

    event.listen(f.engine, "after_cursor_execute", written)
    monkeypatch.setattr(Connection, "commit", commit)
    monkeypatch.setattr(JournalSession, "append", append)
    try:
        failed = submit(f)
    finally:
        event.remove(f.engine, "after_cursor_execute", written)
        monkeypatch.setattr(Connection, "commit", real_commit)
        monkeypatch.setattr(JournalSession, "append", real_append)
    safe(failed, 503, "outcome_uncertain")
    assert faults == [phase] and pending == ["commit_pending"]
    assert len(f.storage.calls) == 3
    if phase == "before_ack":
        assert rows(f) == before
        f.service.registry = f.service.storage = f.service.readiness = None
        monkeypatch.setattr(
            f.policy, "require_available", lambda: pytest.fail("new work after pending")
        )
        safe(submit(f), 503, "outcome_uncertain")
        assert rows(f) == before
    else:
        committed = rows(f)
        assert (
            len(committed["operations"]) == len(committed["jobs"]) == len(committed["audit"]) == 1
        )
        assert origin(f) == failed.headers["x-request-id"]
        poison_new_work(f, monkeypatch)
        replay = safe(submit(f), 202)
        assert replay == {
            "operation_id": committed["operations"][0]["id"],
            "job_id": committed["jobs"][0]["id"],
        }
        assert rows(f) == committed
    clean(f)


def test_postgres_http_eight_fresh_requests_cross_real_guard_then_contend(http_pg, monkeypatch):
    f = http_pg
    entered = [Event() for _ in range(8)]
    release, lock, calls = Event(), Lock(), []
    original = f.service.submit

    def submit_after_guard(*args, **kwargs):
        with lock:
            index = len(calls)
            calls.append(index)
        assert index < 8
        entered[index].set()
        assert release.wait(15), "Eight-request release was not observed"
        return original(*args, **kwargs)

    monkeypatch.setattr(f.service, "submit", submit_after_guard)

    async def concurrent():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=f.app), base_url="http://testserver"
        ) as client:
            tasks = []
            try:
                # Each request has completed the real four-slot guard before the
                # next starts. All eight still contend at the coordinator itself.
                for index in range(8):
                    tasks.append(
                        asyncio.create_task(
                            client.post(
                                PREFIX + PROJECT + "/runs",
                                content=canonical(submission()),
                                headers=f.headers,
                            )
                        )
                    )
                    assert await asyncio.to_thread(entered[index].wait, 10)
                release.set()
                return await asyncio.wait_for(asyncio.gather(*tasks), 30)
            finally:
                release.set()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

    before = rows(f)
    assert not before["jobs"] and not before["operations"] and not before["artifact_refs"]
    responses = asyncio.run(concurrent())
    monkeypatch.setattr(f.service, "submit", original)
    winners = [safe(response, 202) for response in responses if response.status_code == 202]
    assert winners and len(calls) == 8
    for response in responses:
        if response.status_code != 202:
            safe(response, 503, "outcome_uncertain")
    assert all(value == winners[0] for value in winners)
    committed = rows(f)
    assert (
        len(committed["jobs"])
        == len(committed["operations"])
        == len(committed["operation_keys"])
        == 1
    )
    assert len(committed["artifact_refs"]) == len(committed["artifact_objects"]) == 3
    assert len(committed["audit"]) == 1 and len(f.storage.calls) == 3
    assert origin(f) in {response.headers["x-request-id"] for response in responses}
    poison_new_work(f, monkeypatch)
    for _ in range(8):
        assert safe(submit(f), 202) == winners[0]
    assert rows(f) == committed
    clean(f)


@pytest.mark.parametrize("change", ["member", "role", "association"])
def test_postgres_http_cancel_reauthorizes_after_observed_project_lock(
    http_pg, monkeypatch, change
):
    f = http_pg
    accepted = safe(submit(f), 202)
    second = {"job_id": "e" * 32}
    if change == "association":
        # A real scoped configured job without its own operation is a legal
        # reassociation target. Another operation's job is UNIQUE and would only
        # exercise the fixture constraint, not the waiting request's receipts.
        with f.owner.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO jobs(id,kind,created,payload,status,owner,lease_until,cancel,"
                    "budget,reserved,result,error,actor,payload_version,execution_config_ref,"
                    "execution_config_digest) SELECT :new,kind,created,payload,status,owner,"
                    "lease_until,cancel,budget,reserved,result,error,actor,payload_version,"
                    "execution_config_ref,execution_config_digest FROM jobs WHERE id=:old"
                ),
                {"new": second["job_id"], "old": accepted["job_id"]},
            )
            connection.execute(
                text("INSERT INTO resource_scopes VALUES('job',:id,:project)"),
                {"id": second["job_id"], "project": PROJECT},
            )
            connection.execute(
                text(
                    "INSERT INTO artifact_refs(project_id,owner_kind,owner_id,artifact_id,role) "
                    "SELECT project_id,owner_kind,:new,artifact_id,role FROM artifact_refs "
                    "WHERE owner_kind='job' AND owner_id=:old"
                ),
                {"new": second["job_id"], "old": accepted["job_id"]},
            )
    before = rows(f)
    entered, actor = Event(), []
    original = operation_service.lock_authority

    def observed(authority, connection, *args, **kwargs):
        if connection.engine is f.engine:
            actor.append(connection.connection.driver_connection.info.backend_pid)
            entered.set()
        return original(authority, connection, *args, **kwargs)

    monkeypatch.setattr(operation_service, "lock_authority", observed)
    writer = f.owner.connect()
    try:
        writer.execute(text("SELECT id FROM projects WHERE id=:id FOR UPDATE"), {"id": PROJECT})
        blocker = writer.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                f.client.post, operation_path(accepted) + "/cancel", headers=f.headers
            )
            try:
                assert entered.wait(5)
                wait_blocked(f.pg, actor[0], blocker)
                if change == "association":
                    writer.execute(
                        text(
                            "UPDATE operations SET job_id=:job,accepted_response=:response "
                            "WHERE id=:id"
                        ),
                        {
                            "job": second["job_id"],
                            "id": accepted["operation_id"],
                            "response": canonical(
                                {
                                    "operation_id": accepted["operation_id"],
                                    "job_id": second["job_id"],
                                }
                            ).decode(),
                        },
                    )
                else:
                    statement = (
                        "UPDATE project_memberships SET revoked_at=now() WHERE principal_id=:id"
                        if change == "member"
                        else "UPDATE project_memberships SET role='viewer' WHERE principal_id=:id"
                    )
                    writer.execute(text(statement), {"id": f.principal.principal_id})
                writer.commit()
            finally:
                if writer.in_transaction():
                    writer.rollback()
            response = future.result(timeout=10)
    finally:
        writer.close()
    status, code = {
        "member": (404, "not_found"),
        "role": (403, "forbidden"),
        "association": (503, "dependency_unavailable"),
    }[change]
    safe(response, status, code)
    after = rows(f)
    assert after["jobs"] == before["jobs"] and after["audit"] == before["audit"]
    clean(f)


@pytest.mark.parametrize("after_ack", [False, True])
def test_postgres_http_cancel_lost_commit_ack_never_repeats_effect(http_pg, monkeypatch, after_ack):
    f = http_pg
    accepted = safe(submit(f), 202)
    real_commit, staged = Connection.commit, set()
    faults = []

    def written(connection, cursor, statement, *args):
        if statement.strip().startswith("INSERT INTO audit"):
            staged.add(id(connection))

    def commit(connection):
        if connection.engine is f.engine and id(connection) in staged:
            staged.remove(id(connection))
            if after_ack:
                real_commit(connection)
            faults.append(after_ack)
            raise RuntimeError("PRIVATE cancellation ACK")
        return real_commit(connection)

    event.listen(f.engine, "after_cursor_execute", written)
    monkeypatch.setattr(Connection, "commit", commit)
    try:
        response = f.client.post(operation_path(accepted) + "/cancel", headers=f.headers)
    finally:
        event.remove(f.engine, "after_cursor_execute", written)
        monkeypatch.setattr(Connection, "commit", real_commit)
    safe(response, 503, "outcome_uncertain")
    assert faults == [after_ack]
    after = rows(f)
    assert after["jobs"][0]["cancel"] is after_ack
    assert [row["action"] for row in after["audit"]].count("job.cancel") == int(after_ack)
    safe(f.client.get(operation_path(accepted), headers=f.headers), 200)
    assert rows(f) == after
    clean(f)


@pytest.mark.parametrize("change", ["worker", "revoke"])
def test_postgres_http_post_ack_disclosure_keeps_captured_response_or_current_denial(
    http_pg, monkeypatch, change
):
    f = http_pg
    accepted = safe(submit(f), 202)
    original = f.app.state.operation_service._cancel_disclose

    def disclose(*args, **kwargs):
        f.outside()
        with f.owner.begin() as connection:
            if change == "worker":
                connection.execute(
                    text("UPDATE jobs SET status='succeeded' WHERE id=:id"),
                    {"id": accepted["job_id"]},
                )
            else:
                connection.execute(
                    text("UPDATE project_memberships SET revoked_at=now() WHERE principal_id=:id"),
                    {"id": f.principal.principal_id},
                )
        return original(*args, **kwargs)

    monkeypatch.setattr(f.app.state.operation_service, "_cancel_disclose", disclose)
    response = f.client.post(operation_path(accepted) + "/cancel", headers=f.headers)
    if change == "worker":
        assert safe(response, 202) == {
            "operation_id": accepted["operation_id"],
            "cancel_requested": True,
            "status": "cancelled",
        }
    else:
        safe(response, 404, "not_found")
    after = rows(f)
    assert after["jobs"][0]["cancel"] is True
    assert sum(row["action"] == "job.cancel" for row in after["audit"]) == 1
    clean(f)


@pytest.mark.parametrize("change", ["descriptor", "revoke"])
def test_postgres_http_get_result_io_preserves_receipts_and_fresh_authority(
    http_pg, monkeypatch, change
):
    f = http_pg
    accepted = safe(submit(f), 202)
    run = roots(SimpleNamespace(engine=f.owner), 1, job=accepted["job_id"])[0]
    data = canonical({"run_id": run})
    result = descriptor(data, object_id="e" * 32, project=PROJECT)
    f.storage.local.put_verified(result, data)
    with f.owner.begin() as connection:
        record_verified(connection, result)
        register_ref(
            connection,
            project_id=PROJECT,
            owner_kind="job",
            owner_id=accepted["job_id"],
            role="result",
            artifact_id=result.id,
        )
        connection.execute(
            text("UPDATE jobs SET result=:v,status='succeeded' WHERE id=:id"),
            {"v": result.digest, "id": accepted["job_id"]},
        )
    path = operation_path(accepted)
    assert safe(f.client.get(path, headers=f.headers), 200)["result_run_id"] == run
    loader = f.app.state.operation_service.artifact_loader
    seen, mutations = [], []

    def changed(value):
        f.outside()
        body = loader(value)
        seen.append(value)
        with f.owner.begin() as connection:
            if change == "descriptor":
                connection.execute(
                    text("UPDATE artifact_objects SET byte_count=byte_count+1 WHERE id=:id"),
                    {"id": result.id},
                )
            else:
                connection.execute(
                    text("UPDATE project_memberships SET revoked_at=now() WHERE principal_id=:id"),
                    {"id": f.principal.principal_id},
                )
        mutations.append(change)
        return body

    monkeypatch.setattr(f.app.state.operation_service, "artifact_loader", changed)
    response = f.client.get(path, headers=f.headers)
    safe(
        response,
        503 if change == "descriptor" else 404,
        "dependency_unavailable" if change == "descriptor" else "not_found",
    )
    assert len(seen) == 1 and mutations == [change]
    assert len(rows(f)["audit"]) == 1
    clean(f)


def test_postgres_http_integer_precision_and_unsupported_failure_are_not_fabricated(http_pg):
    f = http_pg
    accepted = safe(submit(f), 202)
    path = operation_path(accepted)
    with f.owner.begin() as connection:
        connection.execute(
            text("UPDATE jobs SET reserved=:r,status='succeeded' WHERE id=:id"),
            {"r": 2**53 + 1, "id": accepted["job_id"]},
        )
    value = safe(f.client.get(path, headers=f.headers), 200)
    assert type(value["reserved_microusd"]) is int
    assert value["reserved_microusd"] == 2**53 + 1 > value["budget_microusd"]
    assert value["error"] is None
    for status, error in (("failed", None), ("succeeded", "PRIVATE worker detail")):
        with f.owner.begin() as connection:
            connection.execute(
                text("UPDATE jobs SET status=:s,error=:e WHERE id=:id"),
                {"s": status, "e": error, "id": accepted["job_id"]},
            )
        safe(f.client.get(path, headers=f.headers), 503, "dependency_unavailable")
    assert len(rows(f)["audit"]) == 1


def test_postgres_http_role_cannot_mutate_records_or_operation_association(http_pg):
    f = http_pg
    accepted = safe(submit(f), 202)
    with f.engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT rolsuper,has_table_privilege(current_user,'records','SELECT'),"
            "has_column_privilege(current_user,'operations','kind','UPDATE'),"
            "has_table_privilege(current_user,'records','UPDATE'),"
            "has_column_privilege(current_user,'operations','job_id','UPDATE'),"
            "has_schema_privilege(current_user,'public','CREATE') "
            "FROM pg_roles WHERE rolname=current_user"
        ).one() == (False, True, True, False, False, False)
    before = rows(f)
    for statement in ("UPDATE operations SET job_id=job_id", "UPDATE records SET data=data"):
        with pytest.raises(DBAPIError) as caught, f.engine.begin() as connection:
            connection.exec_driver_sql(statement)
        assert caught.value.orig.sqlstate == "42501"
    assert rows(f) == before
    assert (
        safe(f.client.get(operation_path(accepted), headers=f.headers), 200)["job_id"]
        == accepted["job_id"]
    )
    clean(f)


def test_postgres_http_default_unavailable_policy_refuses_without_preparation(http_pg, monkeypatch):
    f = http_pg
    default = AdmissionCoordinator(f.engine, f.app.state.authority)
    monkeypatch.setattr(
        default, "schema_compatibility", lambda: CompatibilityResult("ready", "synthetic_http_only")
    )
    f.app.state.operation_coordinator = default
    before = rows(f)
    safe(submit(f), 503, "dependency_unavailable")
    assert rows(f) == before and not f.storage.calls and not f.policy.calls
    assert not list(f.root.rglob("intent.json"))


def test_postgres_http_real_sql_permission_failure_is_safe_and_replay_recovers(
    http_pg, monkeypatch
):
    f = http_pg
    accepted = safe(submit(f), 202)
    before = rows(f)
    poison_new_work(f, monkeypatch)
    with f.owner.begin() as connection:
        connection.exec_driver_sql(f"REVOKE SELECT ON operations FROM {f.pg['app_role']}")
    try:
        safe(
            f.client.get(operation_path(accepted), headers=f.headers), 503, "dependency_unavailable"
        )
        safe(
            f.client.post(operation_path(accepted) + "/cancel", headers=f.headers),
            503,
            "dependency_unavailable",
        )
        safe(submit(f), 503, "outcome_uncertain")
    finally:
        with f.owner.begin() as connection:
            connection.exec_driver_sql(f"GRANT SELECT ON operations TO {f.pg['app_role']}")
    assert safe(submit(f), 202) == accepted
    assert rows(f) == before
    clean(f)


@pytest.mark.parametrize("key", [False, True])
def test_postgres_http_revocation_during_real_upload_refuses_publication(http_pg, key):
    f = http_pg
    credential = headers(f, key)
    principal = "api-key:" + KEY_ID if key else f.principal.principal_id
    before = rows(f)

    def revoke(descriptor, content):
        f.outside()
        with f.owner.begin() as connection:
            connection.execute(
                text("UPDATE project_memberships SET revoked_at=now() WHERE principal_id=:id"),
                {"id": principal},
            )

    f.storage.after = revoke
    safe(submit(f, request_headers=credential), 404, "not_found")
    assert len(f.storage.calls) == 1
    assert rows(f) == before
    clean(f)
