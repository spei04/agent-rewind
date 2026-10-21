"""Actual PostgreSQL authority evidence; no HTTP activation or mutation adapter.

The runtime role has SELECT only. Separate owner transactions model changes
between checks deterministically; a ProjectDecision never authorizes a later
write or promises a repeatable snapshot under READ COMMITTED.
"""

from dataclasses import replace

import pytest
import test_migrations_postgres as migrations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from test_scoped_repositories import ALICE, ORG, RUN_A, RUN_B, A, B, add_key
from test_scoped_repositories_postgres import prepare as prepare_scoped

from agent_rewind.request_authority import ActionForbidden, RequestAuthority
from agent_rewind.request_identity import VerifiedPrincipal
from agent_rewind.scoped_repositories import RepositoryUnavailable, ResourceNotFound

pg = migrations.pg
pytestmark = pytest.mark.skipif(not migrations.POSTGRES, reason="Opt-in synthetic PostgreSQL")
HUMAN = VerifiedPrincipal.oidc("https://synthetic.invalid", "alice")


@pytest.fixture
def authority(pg):
    prepare_scoped(pg)
    return RequestAuthority(pg["app"])


def change_membership(connection, **changes):
    # Only test-authored column names enter this statement.
    assert set(changes) <= {"role", "legacy_default", "revoked_at"}
    connection.execute(
        text(
            "UPDATE project_memberships SET "
            + ",".join(f"{column}=:{column}" for column in changes)
            + " WHERE project_id=:project AND principal_id=:principal"
        ),
        {**changes, "project": A, "principal": ALICE},
    )


def service_key(pg, *, key_role="operator", member_role="maintainer", project=A):
    context = add_key(pg["owner"], key_role=key_role, member_role=member_role, project=project)
    with pg["owner"].begin() as connection:
        connection.execute(
            text("UPDATE api_keys SET expires=:expires WHERE id=:id"),
            {"expires": 253402300799.0, "id": RUN_A},
        )
    return VerifiedPrincipal.service_key(RUN_A), context


def test_postgres_explicit_default_and_named_scope_need_only_select(pg, authority):
    decision = authority.legacy(HUMAN, resource_kind="run", resource_id=RUN_A)
    assert decision.context.organization_id == ORG
    assert decision.context.project_id == A
    assert decision.role == "maintainer"
    assert authority.named(HUMAN, A) == decision
    with pg["app"].connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        assert connection.execute(
            text(
                "SELECT has_table_privilege(current_user,'public.project_memberships','UPDATE'),"
                "has_table_privilege(current_user,'public.api_keys','INSERT'),"
                "has_schema_privilege(current_user,'public','CREATE')"
            )
        ).one() == (False, False, False)
        assert authority.check(connection, HUMAN, decision.context) == decision
    with pytest.raises(ResourceNotFound, match="^Resource not found.$"):
        authority.named(HUMAN, B)


def test_postgres_only_membership_is_not_an_implicit_legacy_default(pg, authority):
    with pg["owner"].begin() as connection:
        change_membership(connection, legacy_default=False)
    assert authority.legacy_role(HUMAN) is None
    with pytest.raises(ResourceNotFound):
        authority.legacy(HUMAN)
    assert authority.named(HUMAN, A).role == "maintainer"


def test_postgres_second_active_default_is_rejected_without_losing_first(pg, authority):
    with pytest.raises(IntegrityError), pg["owner"].begin() as connection:
        connection.execute(
            text("INSERT INTO project_memberships VALUES (:project,:principal,'viewer',NULL,true)"),
            {"project": B, "principal": ALICE},
        )
    assert authority.legacy(HUMAN).context.project_id == A
    with pytest.raises(ResourceNotFound):
        authority.named(HUMAN, B)


def test_postgres_resource_visibility_precedes_accessible_action_denial(pg, authority):
    with pg["owner"].begin() as connection:
        change_membership(connection, role="viewer")
    assert authority.named(HUMAN, A, resource_kind="run", resource_id=RUN_A).role == "viewer"
    with pytest.raises(ActionForbidden, match="^This action is not permitted.$"):
        authority.named(HUMAN, A, "branch", resource_kind="run", resource_id=RUN_A)
    for run_id in (RUN_B, "0" * 32):
        with pytest.raises(ResourceNotFound, match="^Resource not found.$"):
            authority.named(HUMAN, A, "branch", resource_kind="run", resource_id=run_id)
    with pytest.raises(ResourceNotFound):
        authority.named(HUMAN, B, "branch")


def test_postgres_read_committed_check_observes_membership_commit_on_same_connection(pg, authority):
    decision = authority.named(HUMAN, A, "branch")
    with pg["app"].connect() as reader, pg["owner"].connect() as writer:
        reader.exec_driver_sql("SET TRANSACTION READ ONLY")
        assert reader.exec_driver_sql("SHOW transaction_isolation").scalar_one() == (
            "read committed"
        )
        backend = reader.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
        transaction = reader.get_transaction()
        change_membership(writer, role="viewer")
        # The uncommitted change must not appear, but neither may the old role
        # survive the other connection's commit on the next authority check.
        assert authority.check(reader, HUMAN, decision.context, "branch").role == "maintainer"
        writer.commit()
        assert authority.check(reader, HUMAN, decision.context).role == "viewer"
        with pytest.raises(ActionForbidden):
            authority.check(reader, HUMAN, decision.context, "branch")
        change_membership(writer, revoked_at="2026-01-01T00:00:00+00:00")
        writer.commit()
        with pytest.raises(ResourceNotFound):
            authority.check(reader, HUMAN, decision.context)
        assert reader.get_transaction() is transaction and transaction.is_active
        assert reader.exec_driver_sql("SELECT pg_backend_pid()").scalar_one() == backend


def test_postgres_default_switch_does_not_rebind_an_existing_decision(pg, authority):
    decision = authority.legacy(HUMAN)
    with pg["app"].connect() as reader:
        reader.exec_driver_sql("SET TRANSACTION READ ONLY")
        assert authority.check(reader, HUMAN, decision.context) == decision
        with pg["owner"].begin() as writer:
            change_membership(writer, legacy_default=False)
            writer.execute(
                text(
                    "INSERT INTO project_memberships "
                    "VALUES (:project,:principal,'viewer',NULL,true)"
                ),
                {"project": B, "principal": ALICE},
            )
        assert authority.legacy(HUMAN).context.project_id == B
        assert authority.check(reader, HUMAN, decision.context).context.project_id == A
        with pytest.raises(ResourceNotFound):
            authority.check(reader, HUMAN, decision.context, resource_kind="run", resource_id=RUN_B)
        with pg["owner"].begin() as writer:
            change_membership(writer, revoked_at="2026-01-01T00:00:00+00:00")
        with pytest.raises(ResourceNotFound):
            authority.check(reader, HUMAN, decision.context)
        assert authority.legacy_role(HUMAN) == "viewer"


@pytest.mark.parametrize("changed_kind,changed_id", [("run", RUN_A), ("job", "a" * 32)])
def test_postgres_bound_resource_rechecks_current_scope_and_lineage(
    pg, authority, changed_kind, changed_id
):
    decision = authority.named(HUMAN, A)
    with pg["app"].connect() as reader:
        reader.exec_driver_sql("SET TRANSACTION READ ONLY")
        assert (
            authority.check(reader, HUMAN, decision.context, resource_kind="run", resource_id=RUN_A)
            == decision
        )
        with pg["owner"].begin() as writer:
            writer.execute(
                text(
                    "UPDATE resource_scopes SET project_id=:project "
                    "WHERE resource_kind=:kind AND resource_id=:id"
                ),
                {"project": B, "kind": changed_kind, "id": changed_id},
            )
        with pytest.raises(ResourceNotFound):
            authority.check(reader, HUMAN, decision.context, resource_kind="run", resource_id=RUN_A)


def test_postgres_caller_transaction_is_used_without_connection_or_commit(
    pg, authority, monkeypatch
):
    decision = authority.named(HUMAN, A)

    def forbidden_connection(*args, **kwargs):
        pytest.fail("Authority escaped the supplied connection")

    monkeypatch.setattr(authority.engine, "connect", forbidden_connection)
    with pg["owner"].connect() as connection:
        transaction = connection.begin()
        change_membership(connection, role="viewer")
        assert authority.check(connection, HUMAN, decision.context).role == "viewer"
        with pytest.raises(ActionForbidden):
            authority.check(connection, HUMAN, decision.context, "branch")
        assert connection.get_transaction() is transaction and transaction.is_active
        transaction.rollback()
    with pg["owner"].connect() as connection:
        assert authority.check(connection, HUMAN, decision.context).role == "maintainer"


@pytest.mark.parametrize(
    "key_role,member_role,expected",
    [
        ("viewer", "operator", "viewer"),
        ("operator", "viewer", "viewer"),
        ("operator", "maintainer", "operator"),
        ("administrator", "maintainer", "operator"),
    ],
)
def test_postgres_service_key_ceiling_and_default_are_explicit(
    pg, authority, key_role, member_role, expected
):
    principal, context = service_key(pg, key_role=key_role, member_role=member_role)
    assert authority.named(principal, A).role == expected
    assert authority.legacy_role(principal) is None
    with pg["owner"].begin() as writer:
        writer.execute(
            text(
                "UPDATE project_memberships SET legacy_default=true "
                "WHERE project_id=:project AND principal_id=:principal"
            ),
            {"project": A, "principal": principal.principal_id},
        )
    assert authority.legacy(principal).context == context
    for action in ("create_key", "revoke_key"):
        with pytest.raises(ActionForbidden):
            authority.named(principal, A, action)
    if expected == "viewer":
        with pytest.raises(ActionForbidden):
            authority.named(principal, A, "branch")
    else:
        assert authority.named(principal, A, "branch").role == "operator"


@pytest.mark.parametrize("change", ["role", "expiry", "revocation", "membership", "scope"])
def test_postgres_key_authority_rechecks_after_another_connection_commits(pg, authority, change):
    principal, context = service_key(pg)
    with pg["app"].connect() as reader:
        reader.exec_driver_sql("SET TRANSACTION READ ONLY")
        assert authority.check(reader, principal, context, "branch").role == "operator"
        with pg["owner"].begin() as writer:
            if change == "role":
                writer.execute(
                    text("UPDATE api_keys SET role='viewer' WHERE id=:id"), {"id": RUN_A}
                )
            elif change == "expiry":
                writer.execute(text("UPDATE api_keys SET expires=0 WHERE id=:id"), {"id": RUN_A})
            elif change == "revocation":
                writer.execute(text("UPDATE api_keys SET revoked=true WHERE id=:id"), {"id": RUN_A})
            elif change == "membership":
                writer.execute(
                    text(
                        "UPDATE project_memberships SET revoked_at=CURRENT_TIMESTAMP "
                        "WHERE project_id=:project AND principal_id=:principal"
                    ),
                    {"project": A, "principal": principal.principal_id},
                )
            else:
                writer.execute(
                    text(
                        "UPDATE resource_scopes SET project_id=:project "
                        "WHERE resource_kind='key' AND resource_id=:id"
                    ),
                    {"project": B, "id": RUN_A},
                )
        if change == "role":
            assert authority.check(reader, principal, context).role == "viewer"
            with pytest.raises(ActionForbidden):
                authority.check(reader, principal, context, "branch")
        else:
            with pytest.raises(ResourceNotFound):
                authority.check(reader, principal, context)


@pytest.mark.parametrize("expires", ["NaN", "Infinity", "-Infinity"])
def test_postgres_nonfinite_expiry_is_not_an_authority_capability(pg, authority, expires):
    principal, _ = service_key(pg)
    with pg["owner"].begin() as writer:
        writer.execute(
            text("UPDATE api_keys SET expires=CAST(:expires AS double precision) WHERE id=:id"),
            {"expires": expires, "id": RUN_A},
        )
    with pytest.raises(ResourceNotFound, match="^Resource not found.$"):
        authority.named(principal, A)


def test_postgres_context_cannot_substitute_principal_or_organization(pg, authority):
    decision = authority.named(HUMAN, A)
    other_issuer = VerifiedPrincipal.oidc("https://other.invalid", "alice")
    with pg["app"].connect() as connection:
        for principal, context in [
            (other_issuer, decision.context),
            (HUMAN, replace(decision.context, organization_id="0" * 32)),
            (HUMAN, replace(decision.context, project_id=B)),
        ]:
            with pytest.raises(ResourceNotFound):
                authority.check(connection, principal, context)


def test_postgres_database_failure_is_not_an_absent_default(pg, authority):
    assert authority.legacy_role(HUMAN) == "maintainer"
    with pg["owner"].begin() as writer:
        writer.exec_driver_sql(f"REVOKE SELECT ON project_memberships FROM {pg['app_role']}")
    with pytest.raises(RepositoryUnavailable):
        authority.legacy_role(HUMAN)
