"""Synthetic supported-instance SQL recovery on real SQLite admission rows."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest
import test_admission_repository as fixtures
from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from agent_rewind import admission_coordinator
from agent_rewind.admission_coordinator import AdmissionCoordinator
from agent_rewind.admission_envelope import OriginCorrelation
from agent_rewind.admission_records import AdmissionStorageError
from agent_rewind.admission_request import parse_submit
from agent_rewind.admission_transaction import AdmissionError
from agent_rewind.migrations.compatibility import CompatibilityResult
from agent_rewind.models import canonical
from agent_rewind.request_authority import ActionForbidden
from agent_rewind.request_identity import IdentityInvalid, VerifiedPrincipal
from agent_rewind.scoped_lineage import ResourceNotFound
from agent_rewind.scoped_repositories import RepositoryUnavailable

admission_engine = fixtures.admission_engine
repository = fixtures.repository


def seed(f):
    with fixtures.transaction(f.engine) as connection:
        original = fixtures.insert(f, connection)
        fixtures.aliases(f, connection)
    return original


@pytest.fixture
def service(repository, monkeypatch):
    value = AdmissionCoordinator(repository.engine, repository.authority)
    # Per-instance synthetic route/profile proof; production manifest stays migration-only.
    monkeypatch.setattr(
        value, "schema_compatibility", lambda: CompatibilityResult("ready", "ready")
    )
    return value


def submit(service, f, **updates):
    values = dict(
        principal=f.principal,
        original_context=f.context,
        intent=f.value.intent,
        key_hash=fixtures.KEY,
        origin=OriginCorrelation("f" * 32),
    )
    values.update(updates)
    return service.submit(**values)


def reconcile(service, f, **updates):
    values = dict(
        principal=f.principal,
        original_context=f.context,
        client_operation_id=f.value.intent.client_operation_id,
        key_hash=fixtures.KEY,
        request_digest=f.value.intent.request_digest,
    )
    values.update(updates)
    return service.reconcile(**values)


def snapshot(f):
    with f.engine.connect() as connection:
        return {
            name: connection.exec_driver_sql(f"SELECT * FROM {name} ORDER BY 1,2").all()
            for name in (
                "jobs",
                "operations",
                "operation_keys",
                "audit",
                "artifact_objects",
                "artifact_refs",
            )
        }


def test_real_guard_refuses_before_any_identity_table_access(repository):
    f = repository
    service = AdmissionCoordinator(f.engine, f.authority)
    selected = []

    def observe(_conn, _cursor, statement, _parameters, _context, _many):
        selected.append(statement.lower())

    event.listen(f.engine, "before_cursor_execute", observe)
    try:
        with pytest.raises(AdmissionError, match="^schema_incompatible$"):
            submit(service, f)
    finally:
        event.remove(f.engine, "before_cursor_execute", observe)
    assert not any("from operations " in sql or "from operation_keys " in sql for sql in selected)


def test_matching_sql_winner_preserves_original_pair_config_origin_and_no_work(
    service, repository, monkeypatch
):
    f = repository
    original = seed(f)
    before = snapshot(f)

    def forbidden(*args, **kwargs):
        pytest.fail("replay invoked new-work dependency")

    from agent_rewind.admission_configuration import NativeRegistry
    from agent_rewind.artifact_storage import ArtifactStorage
    from agent_rewind.publication_journal import PublicationJournal

    monkeypatch.setattr(NativeRegistry, "resolve_new", forbidden)
    monkeypatch.setattr(ArtifactStorage, "put_verified", forbidden)
    monkeypatch.setattr(PublicationJournal, "open", forbidden)
    assert submit(service, f) == original.accepted_response
    assert reconcile(service, f) == original.accepted_response
    assert snapshot(f) == before
    with f.engine.connect() as connection:
        assert fixtures.get(f, connection) == original


def test_legitimate_missing_alias_is_atomic_and_does_not_create_audit(service, repository):
    f = repository
    original = seed(f)
    before = snapshot(f)
    assert submit(service, f, key_hash="8" * 64) == original.accepted_response
    after = snapshot(f)
    assert len(after.pop("operation_keys")) == len(before.pop("operation_keys")) + 1
    assert after == before
    assert reconcile(service, f, key_hash="8" * 64) == original.accepted_response


@pytest.mark.parametrize("entry", ["submit", "reconcile"])
def test_absence_has_no_new_job_alias_or_external_fallback(service, repository, entry):
    f = repository
    before = snapshot(f)
    with pytest.raises(
        AdmissionError,
        match="^" + ("dependency_unavailable" if entry == "submit" else "outcome_uncertain") + "$",
    ):
        (submit if entry == "submit" else reconcile)(service, f)
    assert snapshot(f) == before


@pytest.mark.parametrize("change", ["body", "client"])
def test_proven_dual_identity_conflict_is_fixed_409(service, repository, change):
    f = repository
    seed(f)
    before = snapshot(f)
    raw = fixtures.submission()
    if change == "body":
        raw["seed"] += 1
    else:
        raw["client_operation_id"] = "b" * 32
    with pytest.raises(AdmissionError, match="^idempotency_conflict$"):
        submit(service, f, intent=parse_submit(canonical(raw)))
    assert snapshot(f) == before


@pytest.mark.parametrize("denial", [IdentityInvalid, ResourceNotFound, ActionForbidden])
def test_disclosure_denial_survives_committed_alias_and_returns_no_ids(
    service, repository, monkeypatch, denial
):
    f = repository
    seed(f)
    disclose = service._disclose

    def refuse(*args, **kwargs):
        def no(*args, **kwargs):
            raise denial()

        monkeypatch.setattr(f.authority, "check", no)
        return disclose(*args, **kwargs)

    monkeypatch.setattr(service, "_disclose", refuse)
    with pytest.raises(denial):
        submit(service, f, key_hash="8" * 64)
    with f.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM operation_keys").scalar_one() == 2


def test_disclosure_database_failure_is_uncertain_not_retryable(service, repository, monkeypatch):
    f = repository
    seed(f)
    disclose = service._disclose

    def unavailable(*args, **kwargs):
        def no(*args, **kwargs):
            raise RepositoryUnavailable()

        monkeypatch.setattr(f.authority, "check", no)
        return disclose(*args, **kwargs)

    monkeypatch.setattr(service, "_disclose", unavailable)
    with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
        submit(service, f, key_hash="8" * 64)


@pytest.mark.parametrize("failure", ["storage_conflict", "integrity", "after_insert"])
def test_generic_alias_failure_is_dependency_and_rolls_back(
    service, repository, monkeypatch, failure
):
    f = repository
    seed(f)
    before = snapshot(f)
    bind = service.repository.bind_alias

    def broken(*args, **kwargs):
        if failure == "after_insert":
            bind(*args, **kwargs)
            raise RuntimeError("PRIVATE-CANARY")
        if failure == "integrity":
            raise IntegrityError("PRIVATE-SQL", {}, RuntimeError("PRIVATE"))
        raise AdmissionStorageError("admission_conflict")

    monkeypatch.setattr(service.repository, "bind_alias", broken)
    with pytest.raises(AdmissionError, match="^dependency_unavailable$"):
        submit(service, f, key_hash="8" * 64)
    assert snapshot(f) == before


def test_commit_ack_loss_then_same_submit_recovers_original_alias(service, repository, monkeypatch):
    f = repository
    original = seed(f)
    commit = Connection.commit
    once = True

    def lost(connection):
        nonlocal once
        commit(connection)
        if once:
            once = False
            raise RuntimeError("PRIVATE-ACK")

    monkeypatch.setattr(Connection, "commit", lost)
    with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
        submit(service, f, key_hash="8" * 64)
    assert submit(service, f, key_hash="8" * 64) == original.accepted_response
    with f.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM operation_keys").scalar_one() == 2


@pytest.mark.parametrize("change", ["role", "revoked", "foreign-context"])
def test_fresh_current_authority_refuses_before_alias(service, repository, change):
    f = repository
    seed(f)
    with f.engine.begin() as connection:
        if change == "role":
            connection.execute(text("UPDATE project_memberships SET role='viewer'"))
        elif change == "revoked":
            connection.execute(
                text("UPDATE project_memberships SET revoked_at=:now"),
                {"now": datetime.now(UTC).isoformat()},
            )
    before = snapshot(f)
    context = replace(f.context, project_id="0" * 32) if change == "foreign-context" else f.context
    with pytest.raises(ActionForbidden if change == "role" else ResourceNotFound):
        submit(service, f, key_hash="8" * 64, original_context=context)
    assert snapshot(f) == before


def test_reconciliation_unavailable_schema_is_uncertain(service, repository, monkeypatch):
    monkeypatch.setattr(
        service,
        "schema_compatibility",
        lambda: CompatibilityResult("unavailable", "schema_unavailable"),
    )
    with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
        reconcile(service, repository)


def test_changed_principal_cannot_recover_original_ids(service, repository):
    f = repository
    seed(f)
    with pytest.raises(ResourceNotFound):
        submit(service, f, principal=VerifiedPrincipal("oidc:" + "9" * 64))


def test_post_wait_authority_rechecked_on_same_context(service, repository, monkeypatch):
    f = repository
    seed(f)
    before = snapshot(f)
    locks = admission_coordinator.lock_authority

    def revoke(*args, **kwargs):
        locks(*args, **kwargs)
        connection = args[1]
        connection.execute(text("UPDATE project_memberships SET role='viewer'"))

    monkeypatch.setattr(admission_coordinator, "lock_authority", revoke)
    with pytest.raises(ActionForbidden):
        submit(service, f, key_hash="8" * 64)
    assert snapshot(f) == before


def test_actual_revocation_after_alias_commit_blocks_disclosure(service, repository, monkeypatch):
    f = repository
    seed(f)
    original = service._disclose

    def revoke(*args, **kwargs):
        assert f.engine.pool.checkedout() == 0
        with f.engine.begin() as connection:
            connection.execute(
                text("UPDATE project_memberships SET revoked_at=:now"),
                {"now": datetime.now(UTC).isoformat()},
            )
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "_disclose", revoke)
    with pytest.raises(ResourceNotFound):
        submit(service, f, key_hash="8" * 64)
    with f.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM operation_keys").scalar_one() == 2


def test_replay_stays_on_original_context_after_default_changes(service, repository):
    f = repository
    original = seed(f)
    with f.engine.begin() as connection:
        connection.execute(text("UPDATE project_memberships SET legacy_default=false"))
    assert submit(service, f) == original.accepted_response


def test_generic_select_integrity_failure_is_not_an_identity_conflict(
    service, repository, monkeypatch
):
    def broken(*args, **kwargs):
        raise AdmissionStorageError("admission_conflict")

    monkeypatch.setattr(service.repository, "resolve_identities", broken)
    # No verified SQL winner or absence: never claim a retryable dependency or 409.
    with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
        submit(service, repository)
