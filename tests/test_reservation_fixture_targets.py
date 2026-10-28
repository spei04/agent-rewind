"""Real distinct-identity admission setups; no runtime guard bypass."""

import ledger_eligibility_fixture as eligibility
from ledger_provisioning_fixture import build_case, initial_manifest, invoke


def test_explicit_second_job_is_really_admitted_before_provisioning(tmp_path, monkeypatch):
    fixture = build_case(tmp_path / "two-projects.db", legacy=False)
    try:
        fixture, first = eligibility.admit_existing_fixture(fixture, monkeypatch, lambda *_: None)
        principal, _binding = eligibility.existing_admission_principal(fixture)
        project = fixture.project
        namespace = tmp_path / "second-admission"
        namespace.mkdir(mode=0o700)
        fixture, second = eligibility.admit_existing_fixture(
            fixture,
            monkeypatch,
            lambda *_: None,
            principal=principal,
            project_id=project,
            client_operation_id="2" * 32,
            key_hash="3" * 64,
            admission_root=namespace,
        )
        assert first.accepted["job_id"] != second.accepted["job_id"]
        assert second.association["operation"]["project_id"] == project
        assert second.association["operation"]["principal_id"] == principal.principal_id
        assert first.ciphertexts and second.ciphertexts
        assert first.journal != second.journal and first.objects != second.objects
        manifest = initial_manifest(fixture)
        receipt = invoke(fixture, manifest)
        assert receipt is not None
        jobs = {row["id"]: row for row in fixture.jobs}
        assert jobs[second.accepted["job_id"]]["project_id"] == project
        assert jobs[first.accepted["job_id"]]["project_id"] == fixture.project
    finally:
        fixture.close()


def test_post_p1_second_project_has_real_admission_and_accounts(
    tmp_path, monkeypatch, record_property
):
    """Test-only setup; actual migration_only guard precedes the existing adapter."""
    import json
    from datetime import UTC, datetime

    from ledger_eligibility_fixture import rows
    from ledger_provisioning_fixture import digest, identity, inspect, snapshot
    from ledger_restore_authority import typed
    from sqlalchemy import text

    from agent_rewind.scoped_repositories import members

    def record(name, value):
        record_property(name, json.dumps(typed(value), allow_nan=False))

    fixture = build_case(tmp_path / "post-p1-projects.db", legacy=False)
    try:
        fixture, first = eligibility.admit_existing_fixture(fixture, monkeypatch, record)
        principal, _binding = eligibility.existing_admission_principal(fixture)
        initial = initial_manifest(fixture)
        initial_receipt = invoke(fixture, initial)
        fixture = eligibility.refreshed(fixture)
        initialized = fixture.before
        record("initial_state", initialized)
        record("initial_receipt", initial_receipt.model_dump(mode="json"))
        project = "8" * 32
        with fixture.case.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO projects(id,organization_id,name,created_at) "
                    "VALUES(:id,:organization,:name,:created)"
                ),
                {
                    "id": project,
                    "organization": fixture.organization,
                    "name": "second-project",
                    "created": datetime.now(UTC).isoformat(),
                },
            )
            connection.execute(
                members.insert().values(
                    project_id=project,
                    principal_id=principal.principal_id,
                    role="maintainer",
                    revoked_at=None,
                    legacy_default=False,
                )
            )
        fixture = eligibility.refreshed(fixture)
        pre_admission = fixture.before
        assert rows(pre_admission, "budget_accounts") == rows(initialized, "budget_accounts")
        assert rows(pre_admission, "migration_progress") == rows(initialized, "migration_progress")
        namespace = tmp_path / "second-admission"
        namespace.mkdir(mode=0o700)
        fixture, second = eligibility.admit_existing_fixture(
            fixture,
            monkeypatch,
            lambda name, value: record("second_" + name, value),
            principal=principal,
            project_id=project,
            client_operation_id="2" * 32,
            key_hash="3" * 64,
            admission_root=namespace,
        )
        assert second.compatibility == {
            "status": "incompatible",
            "code": "migration_only",
            "installation_key": None,
        }
        assert first.accepted["job_id"] != second.accepted["job_id"]
        assert second.association["operation"]["project_id"] == project
        assert second.association["operation"]["principal_id"] == principal.principal_id
        assert first.ciphertexts and second.ciphertexts
        assert first.journal != second.journal and first.objects != second.objects
        assert rows(fixture.before, "budget_accounts") == rows(initialized, "budget_accounts")
        assert rows(fixture.before, "migration_progress") == rows(initialized, "migration_progress")
        original_project = next(row for row in initial["accounts"] if row["scope"] == "project")
        original_job = next(row for row in initial["accounts"] if row["scope"] == "job")
        manifest = {
            **initial,
            "manifest_id": identity(9000),
            "operation": "provision",
            "source_digest": fixture.source,
            "parent_manifest_digest": digest(initial),
            "opening_accounts": None,
            "accounts": [
                {
                    **original_project,
                    "id": identity(9001),
                    "scope_id": project,
                    "project_id": project,
                },
                {
                    **original_job,
                    "id": identity(9002),
                    "scope_id": second.accepted["job_id"],
                    "project_id": project,
                    "job_id": second.accepted["job_id"],
                    "limit_microusd": second.association["job"]["budget"],
                },
            ],
        }
        provisioned = invoke(fixture, manifest)
        after = snapshot(fixture.case.path)
        state = inspect(eligibility.refreshed(fixture))
        assert provisioned.sequence == 1 and provisioned.account_rows == 2
        assert provisioned.imported_jobs == provisioned.imported_opening_microusd == 0
        assert state.account_count == 5 and state.manifest_count == 2
        assert rows(after, "jobs") == rows(fixture.before, "jobs")
        old_accounts = {row["id"]: row for row in rows(initialized, "budget_accounts")}
        final_accounts = {row["id"]: row for row in rows(after, "budget_accounts")}
        assert all(final_accounts[key] == value for key, value in old_accounts.items())
        assert set(final_accounts) == set(old_accounts) | {identity(9001), identity(9002)}
        assert all(
            final_accounts[key][field] == 0
            for key in (identity(9001), identity(9002))
            for field in ("opening_held_microusd", "held_microusd", "accounted_microusd")
        )
        jobs = {row["id"]: row for row in fixture.jobs}
        assert jobs[second.accepted["job_id"]]["project_id"] == project
        assert jobs[first.accepted["job_id"]]["project_id"] == fixture.project
        assert len(rows(after, "organizations")) == 1
        record("second_association", second.association)
        record("provision_manifest", manifest)
        record("provision_receipt", provisioned.model_dump(mode="json"))
        record("final_state", after)
        record("final_inspection", state.model_dump(mode="json"))
    finally:
        fixture.close()
