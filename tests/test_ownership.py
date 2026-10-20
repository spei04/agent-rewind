"""Ownership decisions, literal preservation and bounded resumable migration failures."""

import json

import pytest
from legacy_fixture import assert_preserved_rows, materialize_legacy
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from test_migrations import mapping_for

from agent_rewind.migrations import ownership_lineage, ownership_service, service
from agent_rewind.migrations.compatibility import runtime_schema_compatibility
from agent_rewind.migrations.inputs import source_digest
from agent_rewind.migrations.ownership_inputs import read_fresh, validate_fresh
from agent_rewind.migrations.ownership_service import initialize_ownership
from agent_rewind.migrations.schema import (
    HEAD,
    OWNERSHIP,
    MigrationRefused,
    catalog,
    installed_profile,
)
from agent_rewind.ownership import allows_project_action, oidc_principal_id

FRESH = {
    "schema_version": 1,
    "installation_key": "synthetic-installation",
    "organization_id": "8" * 32,
    "project_id": "9" * 32,
    "project_name": "Synthetic project",
    "principal_grants": [
        {"principal_id": "oidc:" + "a" * 64, "role": "maintainer", "legacy_default": True}
    ],
}


@pytest.fixture
def fresh(tmp_path):
    path = tmp_path / "fresh.sqlite"
    engine = create_engine(f"sqlite:///{path}")
    service.install(engine, FRESH["installation_key"])
    yield path, engine
    engine.dispose()


@pytest.fixture
def legacy(tmp_path):
    path = materialize_legacy(tmp_path / "legacy")
    engine = create_engine(f"sqlite:///{path}")
    yield path, engine
    engine.dispose()


def adopt(engine, customize=None):
    mapping = mapping_for(engine)
    if customize:
        customize(mapping)
    service.adopt(engine, mapping, "b" * 64, "d" * 64)
    return mapping


def row(engine):
    with engine.connect() as connection:
        return dict(
            connection.execute(text("SELECT * FROM installation_adoptions")).mappings().one()
        )


def original_digest(engine):
    with engine.connect() as connection:
        return source_digest(connection)


def progress(engine):
    with engine.connect() as connection:
        result = dict(connection.execute(text("SELECT * FROM migration_progress")).mappings().one())
        result["cursor"] = json.loads(result["cursor"])
        return result


def put_record(connection, identifier, kind, data):
    connection.execute(
        text("INSERT INTO records(id,kind,created,data) VALUES (:id,:kind,1,:data)"),
        {"id": identifier, "kind": kind, "data": json.dumps(data)},
    )


def put_job(connection, identifier, kind):
    connection.execute(
        text(
            "INSERT INTO jobs(id,kind,created,payload,status,cancel,budget,reserved) "
            "VALUES (:id,:kind,1,:payload,'failed',false,10,3)"
        ),
        {"id": identifier, "kind": kind, "payload": "a" * 64},
    )


def edit_record(engine, identifier, mutate):
    with engine.begin() as connection:
        data = json.loads(
            connection.execute(
                text("SELECT data FROM records WHERE id=:id"), {"id": identifier}
            ).scalar_one()
        )
        mutate(data)
        connection.execute(
            text("UPDATE records SET data=:data WHERE id=:id"),
            {"id": identifier, "data": json.dumps(data)},
        )


def test_fresh_explicit_atomic_transition_preserves_origin_and_null_evidence(fresh):
    path, engine = fresh
    before = row(engine)
    first = initialize_ownership(engine, FRESH)
    assert first == {
        "revision": OWNERSHIP,
        "state": "ownership_complete",
        "source_kind": "fresh",
        "installation_key": FRESH["installation_key"],
        "customer_ready": False,
        "ownership_rows_verified": 0,
        "ownership_rows_total": 0,
    }
    after = row(engine)
    for field in (
        "source_kind",
        "source_baseline",
        "schema_fingerprint",
        "mapping",
        "mapping_digest",
        "created_at",
        "backup_evidence_digest",
        "drain_evidence_digest",
    ):
        assert after[field] == before[field]
    assert after["backup_evidence_digest"] is after["drain_evidence_digest"] is None
    assert after["organization_id"] == FRESH["organization_id"]
    assert after["project_id"] == FRESH["project_id"]
    snapshot = path.read_bytes()
    assert initialize_ownership(engine, FRESH) == first
    assert path.read_bytes() == snapshot
    assert runtime_schema_compatibility(engine).code == "migration_only"
    assert service.schema_status(engine)["customer_ready"] is False
    assert service.upgrade(engine, OWNERSHIP)["state"] == "ownership_complete"
    with pytest.raises(MigrationRefused, match="installation_conflict"):
        service.install(engine, FRESH["installation_key"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("installation_key", "different"),
        ("organization_id", "7" * 32),
        ("project_id", "6" * 32),
        ("project_name", "Different"),
        (
            "principal_grants",
            [{"principal_id": "oidc:" + "b" * 64, "role": "viewer", "legacy_default": False}],
        ),
    ],
)
def test_fresh_replay_binds_every_identity(fresh, field, value):
    path, engine = fresh
    initialize_ownership(engine, FRESH)
    before = path.read_bytes()
    with pytest.raises(MigrationRefused, match="ownership_intent_conflict"):
        initialize_ownership(engine, {**FRESH, field: value})
    assert path.read_bytes() == before


def test_explicit_fresh_input_required_and_legacy_replacement_forbidden(fresh, legacy):
    path, engine = fresh
    with pytest.raises(MigrationRefused, match="fresh_ownership_input_required"):
        initialize_ownership(engine)
    assert service.schema_status(engine)["revision"] == HEAD
    legacy_path, legacy_engine = legacy
    adopt(legacy_engine)
    before = legacy_path.read_bytes()
    with pytest.raises(MigrationRefused, match="legacy_ownership_input_forbidden"):
        initialize_ownership(legacy_engine, FRESH)
    assert legacy_path.read_bytes() == before


def test_legacy_batches_preserve_literal_rows_ciphertexts_and_reservations(legacy):
    path, engine = legacy
    objects = {p.name: p.read_bytes() for p in (path.parent / "objects").iterdir()}
    mapping = adopt(engine)
    before = row(engine)
    for count in range(1, 8):
        result = initialize_ownership(engine, batch_size=1)
        assert result["ownership_rows_verified"] == count
        assert result["ownership_rows_total"] == 7
        assert result["state"] == ("ownership_complete" if count == 7 else "prepared")
        assert result["customer_ready"] is False
        checkpoint = progress(engine)
        assert checkpoint["rows_verified"] == count
        assert checkpoint["source_digest"] == mapping["source_dataset_digest"]
        assert checkpoint["cursor"]["intent"] == {
            "source_kind": "legacy",
            "mapping_digest": before["mapping_digest"],
        }
        assert runtime_schema_compatibility(engine).status == "incompatible"
        assert_preserved_rows(path)
    after = row(engine)
    for field in before:
        if field not in {"state", "installed_schema_fingerprint"}:
            assert after[field] == before[field]
    assert {p.name: p.read_bytes() for p in (path.parent / "objects").iterdir()} == objects
    snapshot = path.read_bytes()
    assert initialize_ownership(engine, batch_size=1) == result
    assert path.read_bytes() == snapshot


def test_each_batch_rolls_back_scopes_cursor_and_revision_together(legacy, monkeypatch):
    path, engine = legacy
    adopt(engine)
    original = ownership_service._write_progress

    def interrupted(*args, **kwargs):
        raise RuntimeError("synthetic interruption")

    before = path.read_bytes()
    monkeypatch.setattr(ownership_service, "_write_progress", interrupted)
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        initialize_ownership(engine, batch_size=1)
    assert path.read_bytes() == before
    assert service.schema_status(engine)["revision"] == HEAD
    monkeypatch.setattr(ownership_service, "_write_progress", original)
    initialize_ownership(engine, batch_size=1)
    before = path.read_bytes()
    monkeypatch.setattr(ownership_service, "_write_progress", interrupted)
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        initialize_ownership(engine, batch_size=1)
    assert path.read_bytes() == before
    assert progress(engine)["rows_verified"] == 1
    assert_preserved_rows(path)


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE resource_scopes SET resource_id='ffffffffffffffffffffffffffffffff'",
        "DELETE FROM resource_scopes",
        "INSERT INTO resource_scopes VALUES('provider_call','ffffffffffffffffffffffffffffffff',"
        "'99999999999999999999999999999999')",
    ],
)
def test_changed_or_extra_prefix_is_not_repaired(legacy, mutation):
    path, engine = legacy
    adopt(engine)
    initialize_ownership(engine, batch_size=1)
    with engine.begin() as connection:
        connection.exec_driver_sql(mutation)
    before = path.read_bytes()
    with pytest.raises(MigrationRefused, match="ownership_scope_conflict"):
        initialize_ownership(engine)
    assert path.read_bytes() == before


def test_source_drift_refuses_without_advancing_cursor(legacy):
    path, engine = legacy
    adopt(engine)
    initialize_ownership(engine, batch_size=1)
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE jobs SET reserved=reserved+1")
    before = path.read_bytes()
    with pytest.raises(MigrationRefused, match="source_digest_mismatch"):
        initialize_ownership(engine)
    assert path.read_bytes() == before
    assert progress(engine)["rows_verified"] == 1


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data.update(parent_id="f" * 32),
        lambda data: data.pop("parent_id"),
        lambda data: data.update(job_id="f" * 32),
        lambda data: data.update(job_id=123),
    ],
)
def test_missing_malformed_or_foreign_run_ancestry_blocks_completion(legacy, mutation):
    path, engine = legacy
    edit_record(engine, "2" * 32, mutation)
    adopt(engine)
    before = path.read_bytes()
    with pytest.raises(MigrationRefused, match="ownership_lineage_invalid"):
        initialize_ownership(engine)
    assert path.read_bytes() == before
    assert service.schema_status(engine)["revision"] == HEAD


def test_cycle_refuses_without_recursive_walk_or_writes(legacy):
    path, engine = legacy
    edit_record(engine, "1" * 32, lambda data: data.update(parent_id="2" * 32))
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE jobs SET kind='branch' WHERE id='" + "a" * 32 + "'")
    adopt(engine)
    before = path.read_bytes()
    with pytest.raises(MigrationRefused, match="ownership_lineage_invalid"):
        initialize_ownership(engine)
    assert path.read_bytes() == before


def add_study(engine, *, duplicate=False, foreign=False):
    with engine.begin() as connection:
        put_job(connection, "d" * 32, "study")
        put_record(connection, "6" * 32, "run", {"job_id": "d" * 32, "parent_id": "1" * 32})
        pair = {"control_run": "6" * 32, "control_success": False, "treatment_success": None}
        if duplicate:
            pair["treatment_run"] = "6" * 32
        if foreign:
            pair["control_run"] = "2" * 32
        put_record(
            connection,
            "7" * 32,
            "study",
            {
                "job_id": "d" * 32,
                "source_run": "1" * 32,
                "request": {"run_id": "1" * 32},
                "candidates": [{"pairs": [pair]}],
                "confirmation": None,
            },
        )


def test_synthetic_incomplete_study_missing_outcome_has_unambiguous_sql_closure(legacy):
    _, engine = legacy
    add_study(engine)
    digest = original_digest(engine)
    adopt(engine)
    result = initialize_ownership(engine)
    assert result["state"] == "ownership_complete"
    assert result["ownership_rows_total"] == 10
    assert original_digest(engine) == digest


@pytest.mark.parametrize(
    "variant", ["duplicate", "foreign", "request", "missing_owner", "wrong_source", "orphan_event"]
)
def test_study_ambiguity_wrong_kind_or_orphan_events_refuse(legacy, variant):
    path, engine = legacy
    add_study(engine, duplicate=variant == "duplicate", foreign=variant == "foreign")
    if variant == "request":
        edit_record(engine, "7" * 32, lambda data: data.update(request={"run_id": "2" * 32}))
    if variant in {"missing_owner", "wrong_source"}:
        edit_record(engine, "7" * 32, lambda data: data.update(candidates=[]))
        if variant == "missing_owner":
            with engine.begin() as connection:
                connection.execute(text("DELETE FROM records WHERE id=:id"), {"id": "7" * 32})
        else:
            edit_record(engine, "6" * 32, lambda data: data.update(parent_id="2" * 32))
    if variant == "orphan_event":
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE events SET run_id='" + "f" * 32 + "' WHERE run_id='" + "2" * 32 + "'"
            )
    adopt(engine)
    before = path.read_bytes()
    with pytest.raises(MigrationRefused, match="ownership_(lineage_invalid|ambiguous_trial)"):
        initialize_ownership(engine)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "limit,value",
    [
        ("MAX_RESOURCES", 1),
        ("MAX_EDGES", 1),
        ("MAX_RETAINED_BYTES", 8),
        ("MAX_PARENT_DEPTH", 0),
    ],
)
def test_closure_limits_refuse_before_scope_or_cursor_writes(legacy, monkeypatch, limit, value):
    path, engine = legacy
    adopt(engine)
    before = path.read_bytes()
    monkeypatch.setattr(ownership_lineage, limit, value)
    with pytest.raises(MigrationRefused, match="ownership_(closure_limit|ancestry_limit)"):
        initialize_ownership(engine, batch_size=1)
    assert path.read_bytes() == before


def test_cross_kind_same_identifier_keeps_distinct_scopes(legacy):
    _, engine = legacy
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE api_keys SET id='" + "1" * 32 + "' WHERE id='" + "3" * 32 + "'"
        )
    adopt(engine)
    initialize_ownership(engine)
    with engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT resource_kind FROM resource_scopes WHERE resource_id=:id "
                "ORDER BY resource_kind"
            ),
            {"id": "1" * 32},
        ).scalars().all() == ["key", "run"]


def test_revoked_expired_and_unmapped_keys_are_never_reactivated(legacy):
    _, engine = legacy

    def grants(mapping):
        mapping["key_dispositions"] = [
            {"key_id": "3" * 32, "role": "viewer"},
            {"key_id": "4" * 32, "role": "operator"},
        ]
        mapping["principal_grants"] += [
            {"principal_id": "api-key:" + "3" * 32, "role": "viewer", "legacy_default": False},
            {"principal_id": "api-key:" + "4" * 32, "role": "operator", "legacy_default": False},
        ]

    before = original_digest(engine)
    adopt(engine, grants)
    initialize_ownership(engine)
    assert original_digest(engine) == before
    with engine.connect() as connection:
        members = connection.execute(
            text(
                "SELECT principal_id,revoked_at FROM project_memberships "
                "WHERE principal_id LIKE 'api-key:%'"
            )
        ).all()
        assert len(members) == 2
        assert all(member.revoked_at is not None for member in members)


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO organizations VALUES('77777777777777777777777777777777',"
        "'synthetic-installation','2026-01-01T00:00:00+00:00')",
        "INSERT INTO project_memberships VALUES('99999999999999999999999999999999',"
        "'oidc:bad','viewer',NULL,false)",
        "INSERT INTO project_memberships VALUES('99999999999999999999999999999999',"
        "'api-key:11111111111111111111111111111111','admin',NULL,false)",
        "INSERT INTO resource_scopes VALUES('run','bad','99999999999999999999999999999999')",
        "INSERT INTO resource_scopes VALUES('run','11111111111111111111111111111111',"
        "'77777777777777777777777777777777')",
    ],
)
def test_database_constraints_enforce_owned_identity_and_grammar(fresh, statement):
    _, engine = fresh
    initialize_ownership(engine, FRESH)
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.exec_driver_sql(statement)


def test_sqlite_catalog_matches_checked_in_literal_profile(fresh):
    _, engine = fresh
    initialize_ownership(engine, FRESH)
    with engine.connect() as connection:
        assert catalog(connection) == installed_profile("sqlite", OWNERSHIP)


def test_private_fresh_file_validation_and_no_secret_diagnostics(tmp_path):
    path = tmp_path / "fresh.json"
    path.write_text(json.dumps(FRESH))
    path.chmod(0o600)
    assert read_fresh(path).model_dump() == FRESH
    path.chmod(0o644)
    with pytest.raises(MigrationRefused, match="^invalid_fresh_ownership_file$"):
        read_fresh(path)
    path.chmod(0o600)
    path.write_text('{"schema_version":1,"schema_version":1,"secret":"never-echo"}')
    with pytest.raises(MigrationRefused, match="^invalid_fresh_ownership_file$"):
        read_fresh(path)
    path.write_text(json.dumps(FRESH))
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(MigrationRefused, match="^invalid_fresh_ownership_file$"):
        read_fresh(link)


@pytest.mark.parametrize(
    "change",
    [
        {"organization_id": "bad"},
        {"project_name": "\n"},
        {"schema_version": True},
        {
            "principal_grants": [
                {"principal_id": "api-key:" + "3" * 32, "role": "viewer", "legacy_default": False}
            ]
        },
        {"principal_grants": FRESH["principal_grants"] * 2},
        {"secret": "never-echo"},
    ],
)
def test_invalid_fresh_contract_refuses(change):
    with pytest.raises(MigrationRefused, match="^invalid_fresh_ownership_intent$"):
        validate_fresh({**FRESH, **change})


def test_role_matrix_and_exact_issuer_bound_identity():
    expected = {
        "viewer": {"read", "list", "compare"},
        "operator": {
            "read",
            "list",
            "compare",
            "record",
            "branch",
            "study",
            "investigate",
            "cancel",
        },
        "maintainer": {
            "read",
            "list",
            "compare",
            "record",
            "branch",
            "study",
            "investigate",
            "cancel",
            "create_key",
            "revoke_key",
        },
        "admin": set(),
        "unknown": set(),
    }
    actions = set.union(*expected.values()) | {"delete_project", "unknown"}
    for role, allowed in expected.items():
        for action in actions:
            assert allows_project_action(role, action) == (action in allowed)
    assert oidc_principal_id("https://issuer", "alice") != oidc_principal_id(
        "https://other", "alice"
    )
    assert oidc_principal_id("https://issuer", "alice") != oidc_principal_id(
        "https://issuer/", "alice"
    )
    assert oidc_principal_id("https://issuer", "alice") == oidc_principal_id(
        "https://issuer", "alice"
    )


def test_expiry_crossing_batches_never_rewrites_key_or_frozen_membership(legacy, monkeypatch):
    from datetime import UTC, datetime

    path, engine = legacy
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE api_keys SET expires=:expiry,revoked=false WHERE id=:id"),
            {"expiry": 2000000000.0, "id": "3" * 32},
        )

    def grants(mapping):
        mapping["key_dispositions"] = [{"key_id": "3" * 32, "role": "viewer"}]
        mapping["principal_grants"].append(
            {"principal_id": "api-key:" + "3" * 32, "role": "viewer", "legacy_default": False}
        )

    adopt(engine, grants)
    digest = original_digest(engine)

    class Clock(datetime):
        current = 1900000000

        @classmethod
        def now(cls, tz=None):
            return datetime.fromtimestamp(cls.current, UTC)

    monkeypatch.setattr(ownership_service, "datetime", Clock)
    initialize_ownership(engine, batch_size=1)
    initialized = progress(engine)["cursor"]["initialized_at"]
    Clock.current = 2100000000
    assert initialize_ownership(engine)["state"] == "ownership_complete"
    assert progress(engine)["cursor"]["initialized_at"] == initialized
    assert original_digest(engine) == digest
    with engine.connect() as connection:
        expires = connection.execute(
            text("SELECT expires FROM api_keys WHERE id=:id"), {"id": "3" * 32}
        ).scalar_one()
        revoked_at = connection.execute(
            text("SELECT revoked_at FROM project_memberships WHERE principal_id=:id"),
            {"id": "api-key:" + "3" * 32},
        ).scalar_one()
    assert expires < Clock.current and revoked_at is None
    # Frozen membership is not an access grant: later authorization must also
    # evaluate this unchanged, now-expired key at the request's current time.
    assert runtime_schema_compatibility(engine).status == "incompatible"


@pytest.mark.parametrize("depth,accepted", [(64, True), (65, False)])
def test_existing_reader_depth_boundary_is_exact(legacy, depth, accepted):
    path, engine = legacy
    parent = "2" * 32
    with engine.begin() as connection:
        for offset in range(depth - 1):
            identifier = f"{offset + 100:032x}"
            job = f"{offset + 1000:032x}"
            put_job(connection, job, "branch")
            put_record(connection, identifier, "run", {"parent_id": parent, "job_id": job})
            parent = identifier
    adopt(engine)
    before = path.read_bytes()
    if accepted:
        assert initialize_ownership(engine)["state"] == "ownership_complete"
    else:
        with pytest.raises(MigrationRefused, match="ownership_ancestry_limit"):
            initialize_ownership(engine)
        assert path.read_bytes() == before


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE migration_progress SET rows_verified=999",
        "UPDATE migration_progress SET status='complete'",
        "UPDATE migration_progress SET cursor='{}'",
        "DELETE FROM migration_progress",
        "UPDATE projects SET name='different'",
        "UPDATE project_memberships SET role='viewer'",
    ],
)
def test_partial_ownership_metadata_drift_refuses_without_repair(legacy, mutation):
    path, engine = legacy
    adopt(engine)
    initialize_ownership(engine, batch_size=1)
    with engine.begin() as connection:
        connection.exec_driver_sql(mutation)
    before = path.read_bytes()
    with pytest.raises(MigrationRefused, match="ownership_progress_invalid"):
        initialize_ownership(engine)
    assert path.read_bytes() == before
    assert runtime_schema_compatibility(engine).status == "incompatible"


def test_owner_cli_needs_only_migration_metadata_configuration(
    fresh, tmp_path, monkeypatch, capsys
):
    import sys

    from agent_rewind.cli import main

    path, engine = fresh
    input_file = tmp_path / "ownership.json"
    input_file.write_text(json.dumps(FRESH))
    input_file.chmod(0o600)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REWIND_DATABASE_URL", f"sqlite:///{path}")
    monkeypatch.setattr(
        sys,
        "argv",
        ["rewind", "migrate", "ownership", "--input", str(input_file), "--batch-size", "2"],
    )
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["revision"] == OWNERSHIP and result["customer_ready"] is False


def test_interrupted_study_run_without_returned_arm_id_keeps_ownership_not_outcome(legacy):
    _, engine = legacy
    add_study(engine)
    failed_pair = {
        "seed": 1001,
        "control_success": None,
        "treatment_success": None,
        "order": ["control", "treatment"],
        "error": "JobStopped",
    }
    not_attempted = {
        "seed": 1002,
        "control_success": None,
        "treatment_success": None,
        "error": "not_attempted",
    }
    edit_record(
        engine,
        "7" * 32,
        lambda data: data.update(
            status="incomplete",
            error="JobStopped",
            candidates=[{"pairs": [failed_pair, not_attempted]}],
        ),
    )
    edit_record(
        engine,
        "6" * 32,
        lambda data: data.update(
            status="failed",
            branchable=False,
            error="Execution interrupted; inspect job status.",
        ),
    )
    before = original_digest(engine)
    adopt(engine)
    assert initialize_ownership(engine, batch_size=1)["state"] == "prepared"
    result = initialize_ownership(engine)
    assert result["state"] == "ownership_complete" and result["ownership_rows_total"] == 10
    assert original_digest(engine) == before
    with engine.connect() as connection:
        report = json.loads(
            connection.execute(
                text("SELECT data FROM records WHERE id=:id"), {"id": "7" * 32}
            ).scalar_one()
        )
        assert report["candidates"][0]["pairs"] == [failed_pair, not_attempted]
        assert (
            connection.execute(
                text(
                    "SELECT project_id FROM resource_scopes WHERE resource_kind='run' "
                    "AND resource_id=:id"
                ),
                {"id": "6" * 32},
            ).scalar_one()
            == "9" * 32
        )
    assert runtime_schema_compatibility(engine).code == "migration_only"
