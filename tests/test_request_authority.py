import math
import time
from dataclasses import replace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from test_scoped_repositories import ALICE, ORG, RUN_A, RUN_B, A, B, add_key, populate

from agent_rewind.ownership import ROLE_ACTIONS
from agent_rewind.request_authority import ActionForbidden, RequestAuthority
from agent_rewind.request_identity import IdentityInvalid, VerifiedPrincipal
from agent_rewind.scoped_lineage import ResourceNotFound
from agent_rewind.scoped_repositories import RepositoryUnavailable

ALICE_ID = VerifiedPrincipal.oidc("https://synthetic.invalid", "alice")


@pytest.fixture
def authority(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'authority.sqlite'}")
    populate(engine)
    yield engine, RequestAuthority(engine)
    engine.dispose()


def change(engine, statement, parameters=None):
    with engine.begin() as connection:
        connection.execute(text(statement), parameters or {})


def test_explicit_default_and_named_scope(authority):
    _, policy = authority
    default = policy.legacy(ALICE_ID)
    named = policy.named(ALICE_ID, A)
    assert default == named
    assert (default.context.organization_id, default.context.project_id, default.role) == (
        ORG,
        A,
        "maintainer",
    )
    with pytest.raises(ResourceNotFound):
        policy.named(ALICE_ID, B)


def test_missing_default_never_uses_only_membership(authority):
    engine, policy = authority
    change(engine, "UPDATE project_memberships SET legacy_default=false")
    assert policy.legacy_role(ALICE_ID) is None
    with pytest.raises(ResourceNotFound):
        policy.legacy(ALICE_ID)
    assert policy.named(ALICE_ID, A).role == "maintainer"


def test_ambiguous_default_refuses_instead_of_selecting_first(authority):
    engine, policy = authority
    # Synthetic corrupt metadata, not a supported migration shape.
    change(engine, "DROP INDEX membership_active_legacy_default")
    change(
        engine,
        "INSERT INTO project_memberships VALUES(:p,:id,'viewer',NULL,true)",
        {"p": B, "id": ALICE},
    )
    assert policy.legacy_role(ALICE_ID) is None
    with pytest.raises(ResourceNotFound):
        policy.legacy(ALICE_ID)


@pytest.mark.parametrize("role", ROLE_ACTIONS)
def test_live_role_actions_and_visibility_precedence(authority, role):
    engine, policy = authority
    change(
        engine,
        "UPDATE project_memberships SET role=:role WHERE project_id=:p",
        {"role": role, "p": A},
    )
    for action in set.union(*(set(actions) for actions in ROLE_ACTIONS.values())) | {"unknown"}:
        if action in ROLE_ACTIONS[role]:
            assert (
                policy.legacy(ALICE_ID, action, resource_kind="run", resource_id=RUN_A).role == role
            )
        else:
            with pytest.raises(ActionForbidden, match="^This action is not permitted.$"):
                policy.legacy(ALICE_ID, action, resource_kind="run", resource_id=RUN_A)
        # Even an insufficient role must not classify an inaccessible ID as403.
        with pytest.raises(ResourceNotFound, match="^Resource not found.$"):
            policy.legacy(ALICE_ID, action, resource_kind="run", resource_id=RUN_B)


@pytest.mark.parametrize("principal", ["alice", "bootstrap", "administrator", None])
def test_unverified_caller_is_identity_failure(authority, principal):
    _, policy = authority
    with pytest.raises(IdentityInvalid):
        policy.legacy(principal)
    with pytest.raises(IdentityInvalid):
        policy.named(principal, A)


def test_issuer_collision_and_bound_context_after_default_change(authority):
    engine, policy = authority
    with pytest.raises(ResourceNotFound):
        policy.legacy(VerifiedPrincipal.oidc("https://other.invalid", "alice"))
    decision = policy.legacy(ALICE_ID)
    change(
        engine,
        "UPDATE project_memberships SET legacy_default=false WHERE principal_id=:id",
        {"id": ALICE},
    )
    change(
        engine,
        "INSERT INTO project_memberships VALUES(:p,:id,'viewer',NULL,true)",
        {"p": B, "id": ALICE},
    )
    assert policy.legacy(ALICE_ID).context.project_id == B
    with engine.connect() as connection:
        assert policy.check(connection, ALICE_ID, decision.context).context.project_id == A
        with pytest.raises(ResourceNotFound):
            policy.check(
                connection, ALICE_ID, replace(decision.context, principal_id="oidc:" + "0" * 64)
            )
    change(
        engine,
        "UPDATE project_memberships SET revoked_at='2026-01-01' WHERE project_id=:p",
        {"p": A},
    )
    with engine.connect() as connection, pytest.raises(ResourceNotFound):
        policy.check(connection, ALICE_ID, decision.context)


@pytest.mark.parametrize(
    ("key_role", "member_role", "expected"),
    [
        ("viewer", "operator", "viewer"),
        ("operator", "viewer", "viewer"),
        ("operator", "maintainer", "operator"),
        ("administrator", "maintainer", "operator"),
    ],
)
def test_key_authority_is_live_intersection_and_never_key_administration(
    authority, key_role, member_role, expected
):
    engine, policy = authority
    add_key(engine, key_role=key_role, member_role=member_role)
    principal = VerifiedPrincipal.service_key(RUN_A)
    assert policy.named(principal, A).role == expected
    assert policy.legacy_role(principal) is None  # No implicit default for a new caller.
    for action in ("create_key", "revoke_key"):
        with pytest.raises(ActionForbidden):
            policy.named(principal, A, action)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("expires", "never"),
        ("expires", b""),
        ("expires", math.inf),
        ("expires", -math.inf),
        ("expires", time.time() - 10),
        ("revoked", ""),
        ("revoked", b""),
        ("revoked", True),
    ],
)
def test_malformed_expired_or_revoked_key_cannot_acquire_scope(authority, field, value):
    engine, policy = authority
    add_key(engine)
    change(engine, f"UPDATE api_keys SET {field}=:value", {"value": value})
    with pytest.raises(ResourceNotFound):
        policy.named(VerifiedPrincipal.service_key(RUN_A), A)


def test_key_scope_must_match_membership(authority):
    engine, policy = authority
    add_key(engine, project=B)
    with pytest.raises(ResourceNotFound):
        policy.named(VerifiedPrincipal.service_key(RUN_A), A)


def test_connection_bound_check_does_not_open_another_connection(authority, monkeypatch):
    engine, policy = authority
    decision = policy.legacy(ALICE_ID)
    with engine.connect() as connection:

        def forbidden():
            raise AssertionError("unexpected independent connection")

        monkeypatch.setattr(engine, "connect", forbidden)
        assert policy.check(connection, ALICE_ID, decision.context).role == "maintainer"


def test_database_failure_is_not_missing_membership(authority, monkeypatch):
    engine, policy = authority

    def failed():
        raise OperationalError("private-canary", {}, ValueError("private-canary"))

    monkeypatch.setattr(engine, "connect", failed)
    with pytest.raises(RepositoryUnavailable, match="^Resource service unavailable.$"):
        policy.legacy_role(ALICE_ID)


def test_invalid_identity_refuses_before_database_access(authority, monkeypatch):
    engine, policy = authority

    def forbidden():
        raise AssertionError("unexpected database access")

    monkeypatch.setattr(engine, "connect", forbidden)
    for resolve in (policy.legacy, policy.legacy_role):
        with pytest.raises(IdentityInvalid):
            resolve("alice")
