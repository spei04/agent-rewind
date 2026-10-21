"""Atomic mutation boundaries on the actual SQLite ownership schema."""

import hashlib
import sqlite3
import time
from dataclasses import replace
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.exc import OperationalError
from test_scoped_repositories import (
    ALICE,
    CA,
    JOB_A,
    JOB_B,
    RUN_A,
    A,
    B,
    add_key,
    populate,
)

from agent_rewind import scoped_actions
from agent_rewind.database import audit, jobs, keys
from agent_rewind.request_authority import ActionForbidden, RequestAuthority
from agent_rewind.request_identity import IdentityInvalid, VerifiedPrincipal
from agent_rewind.scoped_actions import ScopedActionError, ScopedActions
from agent_rewind.scoped_lineage import ResourceNotFound

HUMAN = VerifiedPrincipal.oidc("https://synthetic.invalid", "alice")
CANARY = "private-driver-and-token-canary"


@pytest.fixture
def actions(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'actions.sqlite'}")

    @event.listens_for(engine, "connect")
    def foreign_keys(raw, record):
        raw.execute("PRAGMA foreign_keys=ON")

    populate(engine)
    yield engine, ScopedActions(engine, RequestAuthority(engine))
    engine.dispose()


def change(engine, sql, **params):
    with engine.begin() as connection:
        connection.execute(text(sql), params)


def snapshot(engine):
    with engine.connect() as connection:
        return {
            name: [
                tuple(row)
                for row in connection.exec_driver_sql(f"SELECT * FROM {name} ORDER BY 1,2")
            ]
            for name in ("jobs", "api_keys", "project_memberships", "resource_scopes", "audit")
        }


def call(actions, operation):
    if operation == "cancel":
        return actions.cancel(HUMAN, CA, JOB_A)
    if operation == "issue":
        return actions.issue_key(HUMAN, CA, "operator", "Synthetic key", 30)
    return actions.revoke_key(HUMAN, CA, RUN_A)


@pytest.mark.parametrize("status", ["queued", "running", "succeeded", "failed", "cancelled"])
def test_cancel_preserves_outcome_money_and_repeated_transition(actions, status):
    engine, service = actions
    change(
        engine,
        "UPDATE jobs SET status=:status,owner=:owner,lease_until=:lease,"
        "result=:result,error=:error,budget=100,reserved=37 WHERE id=:id",
        id=JOB_A,
        status=status,
        owner="worker",
        lease=9999999999.0,
        result="c" * 64,
        error="preserved failure",
    )
    with engine.connect() as connection:
        original = dict(connection.execute(select(jobs).where(jobs.c.id == JOB_A)).mappings().one())
    for _ in range(2):
        assert service.cancel(HUMAN, CA, JOB_A) is None
        with engine.connect() as connection:
            current = dict(
                connection.execute(select(jobs).where(jobs.c.id == JOB_A)).mappings().one()
            )
        assert current == {
            **original,
            "cancel": True,
            "status": "cancelled" if status == "queued" else status,
        }
    with engine.connect() as connection:
        assert connection.execute(select(audit.c.actor, audit.c.action, audit.c.target)).all() == [
            (ALICE, "job.cancel", JOB_A),
            (ALICE, "job.cancel", JOB_A),
        ]


@pytest.mark.parametrize("operation", ["cancel", "revoke"])
@pytest.mark.parametrize("service_key", [False, True])
def test_visibility_precedes_action_denial(actions, operation, service_key):
    engine, service = actions
    add_key(engine)
    if service_key:
        principal = VerifiedPrincipal.service_key(RUN_A)
        context = replace(CA, principal_id=principal.principal_id)
        change(engine, "UPDATE api_keys SET role='viewer'")
    else:
        principal, context = HUMAN, CA
        change(
            engine, "UPDATE project_memberships SET role='viewer' WHERE principal_id=:id", id=ALICE
        )
    method = service.cancel if operation == "cancel" else service.revoke_key
    known = JOB_A if operation == "cancel" else RUN_A
    before = snapshot(engine)
    with pytest.raises(ActionForbidden):
        method(principal, context, known)
    for target in (JOB_B, "0" * 32):
        with pytest.raises(ResourceNotFound):
            method(principal, context, target)
    assert snapshot(engine) == before


@pytest.mark.parametrize("operation", ["cancel", "issue", "revoke"])
def test_unverified_and_mismatched_identity_never_connect(actions, monkeypatch, operation):
    engine, service = actions
    forbidden = Mock(side_effect=AssertionError("unexpected database access"))
    monkeypatch.setattr(engine, "connect", forbidden)
    args = (
        (JOB_A,)
        if operation == "cancel"
        else (("operator", "synthetic", 30) if operation == "issue" else (RUN_A,))
    )
    method = {"cancel": service.cancel, "issue": service.issue_key, "revoke": service.revoke_key}[
        operation
    ]
    with pytest.raises(IdentityInvalid):
        method("administrator", CA, *args)
    with pytest.raises(ResourceNotFound):
        method(HUMAN, replace(CA, principal_id="oidc:" + "0" * 64), *args)
    forbidden.assert_not_called()


def test_key_creation_has_one_explicit_scope_membership_and_private_audit(actions):
    engine, service = actions
    issued = service.issue_key(HUMAN, CA, "viewer", "secret-name-canary", 2)
    assert issued.token.startswith("rw_") and issued.token not in repr(issued)
    with engine.connect() as connection:
        row = dict(connection.execute(select(keys)).mappings().one())
        assert row["id"] == issued.id and row["role"] == "viewer" and row["revoked"] is False
        assert row["hash"] == hashlib.sha256(issued.token.encode()).hexdigest()
        assert time.time() + 86400 < row["expires"] <= time.time() + 2 * 86400
        assert connection.execute(
            text("SELECT * FROM resource_scopes WHERE resource_kind='key'")
        ).one() == (
            "key",
            issued.id,
            A,
        )
        assert connection.execute(
            text("SELECT * FROM project_memberships WHERE principal_id=:id"),
            {"id": "api-key:" + issued.id},
        ).one() == (A, "api-key:" + issued.id, "viewer", None, 1)
        audit_row = connection.execute(select(audit)).mappings().one()
        assert (audit_row["actor"], audit_row["action"], audit_row["target"]) == (
            ALICE,
            "key.create",
            issued.id,
        )
        assert all(
            value not in repr(audit_row) for value in (issued.token, row["hash"], row["name"])
        )
    assert (
        service.authority.legacy(VerifiedPrincipal.service_key(issued.id)).context.project_id == A
    )


@pytest.mark.parametrize(
    "role,name,days",
    [
        ("maintainer", "ok", 30),
        ("administrator", "ok", 30),
        ("operator", "", 30),
        ("operator", "x" * 121, 30),
        ("operator", "a\x00b", 30),
        ("operator", "\ud800", 30),
        ("operator", "ok", True),
        ("operator", "ok", 0),
        ("operator", "ok", 91),
    ],
)
def test_invalid_key_input_has_fixed_failure_without_database(
    actions, monkeypatch, role, name, days
):
    engine, service = actions
    forbidden = Mock(side_effect=AssertionError("unexpected SQL"))
    monkeypatch.setattr(engine, "connect", forbidden)
    with pytest.raises(ScopedActionError, match="^action_invalid_input$"):
        service.issue_key(HUMAN, CA, role, name, days)
    forbidden.assert_not_called()


@pytest.mark.parametrize("operation", ["issue", "revoke"])
def test_service_key_never_administers_keys_even_its_own(actions, operation):
    engine, service = actions
    context = add_key(engine, key_role="administrator", member_role="maintainer")
    principal = VerifiedPrincipal.service_key(RUN_A)
    before = snapshot(engine)
    with pytest.raises(ActionForbidden):
        if operation == "issue":
            service.issue_key(principal, context, "operator", "blocked", 30)
        else:
            service.revoke_key(principal, context, RUN_A)
    assert snapshot(engine) == before


@pytest.mark.parametrize("member_present", [False, True])
def test_revoke_expired_or_revoked_key_preserves_hash_and_scope(actions, member_present):
    engine, service = actions
    add_key(engine)
    change(engine, "UPDATE api_keys SET expires=1,revoked=true")
    if not member_present:
        change(
            engine, "DELETE FROM project_memberships WHERE principal_id=:id", id="api-key:" + RUN_A
        )
    with engine.connect() as connection:
        original = dict(connection.execute(select(keys)).mappings().one())
    for _ in range(2):
        assert service.revoke_key(HUMAN, CA, RUN_A) is None
    with engine.connect() as connection:
        assert dict(connection.execute(select(keys)).mappings().one()) == original
        members = connection.execute(
            text("SELECT revoked_at FROM project_memberships WHERE principal_id=:id"),
            {"id": "api-key:" + RUN_A},
        ).all()
        assert len(members) == int(member_present)
        if member_present:
            assert members[0].revoked_at is not None
        assert (
            connection.execute(
                text("SELECT count(*) FROM resource_scopes WHERE resource_kind='key'")
            ).scalar_one()
            == 1
        )


@pytest.mark.parametrize("stage", ["api_keys", "resource_scopes", "project_memberships", "audit"])
def test_key_failure_rolls_back_every_prior_write_and_redacts_driver(actions, stage):
    engine, service = actions
    before = snapshot(engine)

    def fail(connection, cursor, sql, params, context, many):
        if sql.startswith("INSERT INTO " + stage):
            raise OperationalError(CANARY, {}, RuntimeError(CANARY))

    event.listen(engine, "after_cursor_execute", fail)
    try:
        with pytest.raises(ScopedActionError, match="^action_unavailable$") as failure:
            service.issue_key(HUMAN, CA, "operator", "synthetic", 30)
        assert CANARY not in str(failure.value)
    finally:
        event.remove(engine, "after_cursor_execute", fail)
    assert snapshot(engine) == before


@pytest.mark.parametrize("operation", ["cancel", "revoke"])
def test_mutation_and_audit_rollback_together(actions, monkeypatch, operation):
    engine, service = actions
    add_key(engine)
    before = snapshot(engine)

    def fail(*args):
        raise OperationalError(CANARY, {}, RuntimeError(CANARY))

    monkeypatch.setattr(service, "_audit", fail)
    with pytest.raises(ScopedActionError, match="^action_unavailable$"):
        call(service, operation)
    assert snapshot(engine) == before


@pytest.mark.parametrize("committed", [False, True])
def test_commit_failure_never_returns_token_or_retries(actions, monkeypatch, committed):
    engine, service = actions
    before = snapshot(engine)
    commit = engine.dialect.do_commit
    attempts = []

    def fail(raw):
        attempts.append(1)
        if committed:
            commit(raw)
        raise OperationalError(CANARY, {}, RuntimeError(CANARY))

    with monkeypatch.context() as patch:
        patch.setattr(engine.dialect, "do_commit", fail)
        with pytest.raises(ScopedActionError, match="^outcome_uncertain$"):
            service.issue_key(HUMAN, CA, "operator", "synthetic", 30)
    assert attempts == [1]
    current = snapshot(engine)
    if committed:
        assert len(current["api_keys"]) == 1
        assert len(current["audit"]) == 1
    else:
        assert current == before


def test_duplicate_key_identity_refuses_without_overwriting(actions, monkeypatch):
    engine, service = actions
    issued = service.issue_key(HUMAN, CA, "viewer", "first", 30)
    before = snapshot(engine)
    monkeypatch.setattr(scoped_actions.uuid, "uuid4", lambda: type("ID", (), {"hex": issued.id})())
    with pytest.raises(ScopedActionError, match="^action_unavailable$"):
        service.issue_key(HUMAN, CA, "operator", "second", 30)
    assert snapshot(engine) == before


def test_duplicate_token_hash_refuses_without_overwriting(actions, monkeypatch):
    engine, service = actions
    monkeypatch.setattr(
        scoped_actions.secrets, "token_urlsafe", lambda size: "synthetic-fixed-token"
    )
    service.issue_key(HUMAN, CA, "viewer", "first", 30)
    before = snapshot(engine)
    with pytest.raises(ScopedActionError, match="^action_unavailable$"):
        service.issue_key(HUMAN, CA, "operator", "second", 30)
    assert snapshot(engine) == before


def test_original_context_survives_default_switch_and_rechecks_role(actions, monkeypatch):
    engine, service = actions
    decision = service.authority.legacy(HUMAN)
    change(engine, "UPDATE project_memberships SET legacy_default=false")
    change(
        engine, "INSERT INTO project_memberships VALUES(:p,:id,'viewer',NULL,true)", p=B, id=ALICE
    )
    assert service.authority.legacy(HUMAN).context.project_id == B
    issued = service.issue_key(HUMAN, decision.context, "viewer", "bound", 30)
    assert (
        service.authority.legacy(VerifiedPrincipal.service_key(issued.id)).context.project_id == A
    )

    lock = service._locks

    def downgrade(connection, principal, context, kind, resource_id):
        lock(connection, principal, context, kind, resource_id)
        connection.execute(
            text(
                "UPDATE project_memberships SET role='viewer' "
                "WHERE project_id=:p AND principal_id=:id"
            ),
            {"p": A, "id": ALICE},
        )

    monkeypatch.setattr(service, "_locks", downgrade)
    before = snapshot(engine)
    with pytest.raises(ActionForbidden):
        service.cancel(HUMAN, decision.context, JOB_A)
    assert snapshot(engine) == before


def test_connection_bound_checks_use_only_one_connection(actions, monkeypatch):
    engine, service = actions
    original = service.authority.check
    connections = []

    def checked(connection, *args, **kwargs):
        connections.append(connection)
        return original(connection, *args, **kwargs)

    monkeypatch.setattr(service.authority, "check", checked)
    service.cancel(HUMAN, CA, JOB_A)
    assert len(connections) >= 2 and len({id(value) for value in connections}) == 1


@pytest.mark.parametrize(
    "mode", ["isolation_none", "autocommit_true", "autocommit_false", "fk_off"]
)
def test_unsupported_sqlite_modes_refuse_without_mutation(actions, mode):
    engine, service = actions
    if mode.startswith("autocommit") and not hasattr(sqlite3.Connection, "autocommit"):
        pytest.skip("sqlite3 explicit autocommit modes require Python 3.12")
    before = snapshot(engine)
    used = []

    def mutate(raw, record, proxy):
        if not used:
            used.append(raw)
            if mode == "isolation_none":
                raw.isolation_level = None
            elif mode == "fk_off":
                raw.execute("PRAGMA foreign_keys=OFF")
            else:
                raw.autocommit = mode == "autocommit_true"

    event.listen(engine, "checkout", mutate)
    try:
        with pytest.raises(ScopedActionError, match="^action_unavailable$"):
            service.cancel(HUMAN, CA, JOB_A)
    finally:
        event.remove(engine, "checkout", mutate)
    with pytest.raises(sqlite3.ProgrammingError):
        used[0].execute("SELECT 1")
    assert snapshot(engine) == before
