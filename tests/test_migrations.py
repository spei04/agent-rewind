"""Actual SQLite install/adopt/refusal/rollback with frozen independent history."""

import hashlib
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from legacy_fixture import assert_preserved_rows, materialize_legacy, read_manifest
from sqlalchemy import create_engine, text

from agent_rewind.database import Database
from agent_rewind.migrations import service
from agent_rewind.migrations.inputs import read_mapping, source_digest, validate_mapping
from agent_rewind.migrations.schema import HEAD, MigrationRefused, catalog, checksum


def mapping_for(engine):
    with engine.connect() as connection:
        digest = source_digest(connection)
    return {
        "schema_version": 1,
        "installation_key": "synthetic-installation",
        "source_dataset_digest": digest,
        "organization_id": "8" * 32,
        "project_id": "9" * 32,
        "selector": "all-verified-legacy-resources",
        "principal_grants": [
            {"principal_id": "oidc:" + "a" * 64, "role": "maintainer", "legacy_default": True}
        ],
        "key_dispositions": [],
        "legacy_writer_roles": [],
    }


@pytest.fixture
def legacy(tmp_path):
    database = materialize_legacy(tmp_path / "legacy")
    engine = create_engine(f"sqlite:///{database}")
    yield database, engine, mapping_for(engine)
    engine.dispose()


def test_fresh_install_replay_readonly_status_and_explicit_upgrade(tmp_path):
    database = tmp_path / "fresh.sqlite"
    engine = create_engine(f"sqlite:///{database}")
    assert service.schema_status(engine)["state"] == "empty"
    assert not database.exists(), "status must not create a database"
    first = service.install(engine, "synthetic-installation")
    before = database.read_bytes()
    assert first["revision"] == HEAD and first["state"] == "prepared"
    assert first["customer_ready"] is False
    assert service.install(engine, "synthetic-installation") == first
    assert service.upgrade(engine) == first
    assert service.schema_status(engine) == first
    assert database.read_bytes() == before
    with engine.connect() as connection:
        row = connection.execute(text("SELECT * FROM installation_adoptions")).mappings().one()
        assert row["source_kind"] == "fresh"
        assert row["organization_id"] is row["backup_evidence_digest"] is None
        assert row["project_id"] is row["drain_evidence_digest"] is None
    with pytest.raises(MigrationRefused, match="installation_conflict"):
        service.install(engine, "different-installation")
    with pytest.raises(MigrationRefused, match="unsupported_target_revision"):
        service.upgrade(engine, "unreviewed_future")
    engine.dispose()


def test_actual_adoption_preserves_frozen_rows_ciphertexts_and_holds(legacy):
    database, engine, mapping = legacy
    expected_objects = {p.name: p.read_bytes() for p in (database.parent / "objects").iterdir()}
    first = service.adopt(engine, mapping, "b" * 64, "d" * 64)
    assert first["source_kind"] == "legacy" and first["customer_ready"] is False
    assert_preserved_rows(database)
    manifest = read_manifest()
    for address, ciphertext in expected_objects.items():
        assert (database.parent / "objects" / address).read_bytes() == ciphertext
    with engine.connect() as connection:
        assert connection.execute(text("SELECT sum(reserved) FROM jobs")).scalar_one() == 245000
        assert connection.execute(text("SELECT created FROM records")).scalars().all() == [
            1700000000.125,
            1700000000.125,
        ]
    assert len(manifest["expected_rows"]["events"]) == 4
    assert service.adopt(engine, mapping, "b" * 64, "d" * 64) == first
    assert_preserved_rows(database)


@pytest.mark.parametrize("variant", ["unknown_schema", "partial_schema"])
def test_unknown_or_partial_fixture_is_not_repaired(tmp_path, variant):
    database = materialize_legacy(tmp_path / variant, variant)
    before = database.read_bytes()
    engine = create_engine(f"sqlite:///{database}")
    for operation in [
        lambda: service.install(engine, "synthetic"),
        lambda: service.upgrade(engine),
    ]:
        with pytest.raises(MigrationRefused, match="schema_incompatible"):
            operation()
        assert database.read_bytes() == before
    engine.dispose()


@pytest.mark.parametrize("variant", ["corrupt_ciphertext", "corrupt_address"])
def test_schema_preparation_never_claims_corrupt_history_is_activated(tmp_path, variant):
    database = materialize_legacy(tmp_path / variant, variant)
    engine = create_engine(f"sqlite:///{database}")
    before = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (database.parent / "objects").iterdir()
    }
    result = service.adopt(engine, mapping_for(engine), "b" * 64, "d" * 64)
    assert result["state"] == "prepared" and result["customer_ready"] is False
    assert before == {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (database.parent / "objects").iterdir()
    }
    assert_preserved_rows(database)
    engine.dispose()


@pytest.mark.parametrize(
    "sql",
    [
        "ALTER TABLE jobs ADD COLUMN unknown INTEGER",
        "CREATE INDEX unexpected ON jobs(created)",
        "CREATE TRIGGER unexpected AFTER INSERT ON jobs BEGIN DELETE FROM audit; END",
        "CREATE VIEW unexpected AS SELECT id FROM jobs",
    ],
)
def test_structural_drift_blocks_adoption_without_writes(legacy, sql):
    database, engine, mapping = legacy
    with engine.begin() as connection:
        connection.exec_driver_sql(sql)
    before = database.read_bytes()
    with pytest.raises(MigrationRefused, match="schema_incompatible"):
        service.adopt(engine, mapping, "b" * 64, "d" * 64)
    assert database.read_bytes() == before


@pytest.mark.parametrize("status", ["queued", "running", "unknown"])
def test_nonterminal_legacy_jobs_block_including_expired_lease(legacy, status):
    database, engine, _ = legacy
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE jobs SET status=:status, lease_until=1"), {"status": status}
        )
    mapping = mapping_for(engine)
    before = database.read_bytes()
    with pytest.raises(MigrationRefused, match="legacy_jobs_not_terminal"):
        service.adopt(engine, mapping, "b" * 64, "d" * 64)
    assert database.read_bytes() == before


def test_no_implicit_adoption_and_changed_intent_source_or_evidence_conflicts(legacy, settings):
    database, engine, mapping = legacy
    settings.database_url = f"sqlite:///{database}"
    db = Database(settings)
    with pytest.raises(MigrationRefused, match="schema_incompatible"):
        db.migrate()
    service.adopt(engine, mapping, "b" * 64, "d" * 64)
    changed = {**mapping, "project_id": "a" * 32}
    for candidate, backup in [(changed, "b" * 64), (mapping, "c" * 64)]:
        with pytest.raises(MigrationRefused, match="adoption_conflict"):
            service.adopt(engine, candidate, backup, "d" * 64)
    with engine.begin() as connection:
        connection.execute(text("UPDATE jobs SET reserved=reserved+1"))
    with pytest.raises(MigrationRefused, match="source_digest_mismatch"):
        service.adopt(engine, mapping, "b" * 64, "d" * 64)
    db.engine.dispose()


def test_interruption_rolls_back_revision_ddl_and_retry_then_restore(legacy, monkeypatch):
    database, engine, mapping = legacy
    backup = database.with_name("verified-backup.sqlite")
    with sqlite3.connect(database) as source, sqlite3.connect(backup) as target:
        source.backup(target)
    backup.chmod(0o600)
    original = service._record

    def interrupted(*args, **kwargs):
        raise RuntimeError("synthetic interruption after migration DDL")

    monkeypatch.setattr(service, "_record", interrupted)
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        service.adopt(engine, mapping, "b" * 64, "d" * 64)
    assert service.schema_status(engine)["state"] == "legacy_unversioned"
    assert_preserved_rows(database)
    monkeypatch.setattr(service, "_record", original)
    service.adopt(engine, mapping, "b" * 64, "d" * 64)
    engine.dispose()
    with sqlite3.connect(backup) as source, sqlite3.connect(database) as target:
        source.backup(target)
    assert_preserved_rows(database)
    assert service.schema_status(engine)["state"] == "legacy_unversioned"


def test_exclusive_sqlite_transaction_fences_an_old_writer(legacy):
    database, engine, _ = legacy
    with service.migration_transaction(engine):
        old_writer = sqlite3.connect(database, timeout=0.01)
        try:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                old_writer.execute("UPDATE jobs SET reserved=reserved+1")
        finally:
            old_writer.close()
    assert_preserved_rows(database)


def test_existing_old_writer_blocks_migration_with_finite_wait(legacy):
    database, engine, mapping = legacy
    old_writer = sqlite3.connect(database)
    old_writer.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(MigrationRefused, match="migration_busy"):
            service.adopt(engine, mapping, "b" * 64, "d" * 64, timeout_seconds=1)
    finally:
        old_writer.rollback()
        old_writer.close()
    assert_preserved_rows(database)


def test_two_migrators_cannot_duplicate_installation(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'concurrent.sqlite'}")
    entered, release = Event(), Event()
    original = service._record

    def held_record(*args, **kwargs):
        entered.set()
        assert release.wait(5), "second migrator did not finish bounded refusal"
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "_record", held_record)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(service.install, engine, "synthetic")
        assert entered.wait(5)
        try:
            with pytest.raises(MigrationRefused, match="migration_busy"):
                service.install(engine, "synthetic", timeout_seconds=1)
        finally:
            release.set()
        assert first.result(timeout=5)["state"] == "prepared"
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM installation_adoptions")).scalar_one()
            == 1
        )
    engine.dispose()


def test_foreign_metadata_shape_cannot_self_authorize_with_its_own_fingerprint(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'foreign.sqlite'}")
    service.install(engine, "synthetic")
    with engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE migration_progress ADD COLUMN unreviewed INTEGER")
        forged = checksum(catalog(connection))
        connection.execute(
            text("UPDATE installation_adoptions SET installed_schema_fingerprint=:v"), {"v": forged}
        )
    with pytest.raises(MigrationRefused, match="schema_incompatible"):
        service.schema_status(engine)
    engine.dispose()


@pytest.mark.parametrize("value", ["not-json", "[]", '{"schema":1,"source_kind":"legacy"}'])
def test_malformed_or_wrong_origin_mapping_refuses_safely(tmp_path, value):
    engine = create_engine(f"sqlite:///{tmp_path / 'bad-metadata.sqlite'}")
    service.install(engine, "synthetic")
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE installation_adoptions SET mapping=:value"), {"value": value}
        )
    with pytest.raises(MigrationRefused, match="adoption_metadata_drift"):
        service.schema_status(engine)
    engine.dispose()


def test_fresh_metadata_can_transition_without_invented_legacy_evidence(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'transition.sqlite'}")
    service.install(engine, "synthetic")
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE installation_adoptions SET state='ownership_complete', "
                "organization_id=:o,project_id=:p"
            ),
            {"o": "a" * 32, "p": "b" * 32},
        )
        row = connection.execute(
            text("SELECT backup_evidence_digest,drain_evidence_digest FROM installation_adoptions")
        ).one()
        assert tuple(row) == (None, None)
    # This first release does not claim to support a later ownership transition.
    with pytest.raises(MigrationRefused, match="adoption_metadata_drift"):
        service.schema_status(engine)
    engine.dispose()


def test_mapping_file_is_private_regular_bounded_and_duplicate_free(legacy, tmp_path):
    _, _, mapping = legacy
    path = tmp_path / "mapping.json"
    path.write_text(json.dumps(mapping))
    path.chmod(0o600)
    assert read_mapping(path).model_dump() == mapping
    path.chmod(0o644)
    with pytest.raises(MigrationRefused, match="invalid_mapping_file"):
        read_mapping(path)
    path.chmod(0o600)
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(MigrationRefused, match="invalid_mapping_file"):
        read_mapping(link)
    path.write_text('{"schema_version":1,"schema_version":1}')
    with pytest.raises(MigrationRefused, match="invalid_mapping_file"):
        read_mapping(path)
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo, 0o600)
    with pytest.raises(MigrationRefused, match="invalid_mapping_file"):
        read_mapping(fifo)


def test_mapping_duplicate_grants_and_unknown_members_rejected(legacy):
    _, _, mapping = legacy
    for changed in [
        {**mapping, "secret": "must-not-echo"},
        {**mapping, "principal_grants": mapping["principal_grants"] * 2},
    ]:
        with pytest.raises(MigrationRefused, match="invalid_mapping") as failure:
            validate_mapping(changed)
        assert "must-not-echo" not in str(failure.value)


@pytest.mark.parametrize("legacy_origin", [False, True])
def test_source_schema_provenance_cannot_be_replaced(legacy, tmp_path, legacy_origin):
    _, legacy_engine, mapping = legacy
    engine = (
        legacy_engine if legacy_origin else create_engine(f"sqlite:///{tmp_path / 'origin.sqlite'}")
    )
    if legacy_origin:
        service.adopt(engine, mapping, "b" * 64, "d" * 64)
    else:
        service.install(engine, "synthetic")
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE installation_adoptions SET schema_fingerprint=:v"), {"v": "f" * 64}
        )
    with pytest.raises(MigrationRefused, match="adoption_metadata_drift"):
        service.schema_status(engine)
    if not legacy_origin:
        engine.dispose()


@pytest.mark.parametrize("value", ["not-json", '{"secret":"never-echo","secret":2}'])
def test_invalid_source_json_has_safe_diagnostic_and_no_adoption(legacy, value):
    database, engine, mapping = legacy
    with engine.begin() as connection:
        connection.execute(text("UPDATE records SET data=:v"), {"v": value})
    before = database.read_bytes()
    with pytest.raises(MigrationRefused, match="invalid_source_data") as failure:
        service.adopt(engine, mapping, "b" * 64, "d" * 64)
    assert "never-echo" not in str(failure.value)
    assert database.read_bytes() == before


def test_cli_status_install_upgrade_and_safe_refusal(tmp_path, monkeypatch, capsys):
    from agent_rewind.cli import main

    monkeypatch.chdir(tmp_path)
    database = tmp_path / "cli.sqlite"
    monkeypatch.setenv("REWIND_DATABASE_URL", f"sqlite:///{database}")
    monkeypatch.delenv("REWIND_MIGRATION_DATABASE_URL", raising=False)
    monkeypatch.delenv("REWIND_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("REWIND_MODE", "production")
    for args, expected in [
        (["status"], "empty"),
        (["install", "--installation-key", "synthetic"], "prepared"),
        (["upgrade"], "prepared"),
        (["status"], "prepared"),
    ]:
        monkeypatch.setattr("sys.argv", ["rewind", "migrate", *args])
        main()
        assert json.loads(capsys.readouterr().out)["state"] == expected
    monkeypatch.setattr("sys.argv", ["rewind", "migrate", "install", "--installation-key", "other"])
    with pytest.raises(SystemExit) as failure:
        main()
    assert failure.value.code == 2
    assert "installation_conflict" in capsys.readouterr().err


def test_cli_adoption_and_status_use_real_private_mapping(legacy, monkeypatch, capsys, tmp_path):
    from agent_rewind.cli import main

    database, _, mapping = legacy
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REWIND_DATABASE_URL", f"sqlite:///{database}")
    monkeypatch.delenv("REWIND_MIGRATION_DATABASE_URL", raising=False)
    monkeypatch.delenv("REWIND_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("REWIND_MODE", "production")
    path = tmp_path / "private-mapping.json"
    path.write_text(json.dumps(mapping))
    path.chmod(0o600)
    monkeypatch.setattr(
        "sys.argv",
        [
            "rewind",
            "migrate",
            "adopt",
            "--mapping",
            str(path),
            "--backup-evidence",
            "b" * 64,
            "--drain-evidence",
            "d" * 64,
        ],
    )
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["state"] == "prepared" and result["customer_ready"] is False
    assert "principal_grants" not in result
    assert_preserved_rows(database)


@pytest.mark.parametrize("action", [["status"], ["install", "--installation-key", "synthetic"]])
def test_cli_migration_requires_explicit_dsn_without_loading_application_secrets(
    tmp_path, monkeypatch, capsys, action
):
    from agent_rewind.cli import main

    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.startswith("REWIND_"):
            monkeypatch.delenv(name)
    monkeypatch.setattr("sys.argv", ["rewind", "migrate", *action])
    with pytest.raises(SystemExit) as failure:
        main()
    assert failure.value.code == 2
    assert "migration_database_url_required" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []
    monkeypatch.setenv("REWIND_MIGRATION_DATABASE_URL", "bad-url-with-synthetic-secret")
    with pytest.raises(SystemExit):
        main()
    error = capsys.readouterr().err
    assert "invalid_migration_database_url" in error and "synthetic-secret" not in error


def test_cli_only_migration_dsn_is_sufficient_for_install_and_status(tmp_path, monkeypatch, capsys):
    from agent_rewind.cli import main

    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.startswith("REWIND_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("REWIND_MIGRATION_DATABASE_URL", f"sqlite:///{tmp_path / 'metadata.sqlite'}")
    monkeypatch.setenv("REWIND_MODE", "production")
    for action in [["install", "--installation-key", "synthetic"], ["status"]]:
        monkeypatch.setattr("sys.argv", ["rewind", "migrate", *action])
        main()
        assert json.loads(capsys.readouterr().out)["state"] == "prepared"


def test_sqlite_json_size_preflight_precedes_decode(legacy, monkeypatch):
    from agent_rewind.migrations import inputs

    _, engine, _ = legacy
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE records SET data=:value"), {"value": json.dumps({"large": "x" * 5000})}
        )
    monkeypatch.setattr(inputs, "MAX_ROW_BYTES", 4096)

    def unexpected_decode(*args, **kwargs):
        raise AssertionError("Oversized JSON reached the decoder")

    monkeypatch.setattr(inputs.json, "loads", unexpected_decode)
    with (
        engine.connect() as connection,
        pytest.raises(MigrationRefused, match="source_limit_exceeded"),
    ):
        source_digest(connection)


@pytest.mark.parametrize(
    "clause",
    ["COLLATE NOCASE", "COLLATE/* synthetic */NOCASE", "CHECK(length(kind)>0)", "DEFAULT 'run'"],
)
def test_sqlite_unreflected_baseline_clauses_fail_closed(clause):
    from legacy_fixture import FIXTURE_ROOT

    sql = (FIXTURE_ROOT / "baseline.sql").read_text()
    assert hashlib.sha256(sql.encode()).hexdigest() == read_manifest()["baseline_sql_sha256"]
    changed = sql.replace("kind VARCHAR(20) NOT NULL", f"kind VARCHAR(20) {clause} NOT NULL", 1)
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.connection.driver_connection.executescript(changed)
        with pytest.raises(MigrationRefused, match="schema_incompatible"):
            catalog(connection)
    engine.dispose()


def test_sqlite_clause_scanner_treats_comments_and_quoted_identifiers_deliberately():
    from legacy_fixture import FIXTURE_ROOT

    from agent_rewind.migrations.schema import verify_baseline

    sql = (FIXTURE_ROOT / "baseline.sql").read_text()
    changed = sql.replace(
        "kind VARCHAR(20) NOT NULL",
        "\"kind\" VARCHAR(20) /* COLLATE NOCASE, 'CHECK' */ NOT NULL",
        1,
    )
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.connection.driver_connection.executescript(changed)
        verify_baseline(catalog(connection), "sqlite")
    engine.dispose()


@pytest.mark.parametrize("multiple", [False, True])
def test_stored_future_or_multiple_revisions_refuse_without_source_changes(legacy, multiple):
    database, engine, mapping = legacy
    service.adopt(engine, mapping, "b" * 64, "d" * 64)
    with engine.begin() as connection:
        if multiple:
            connection.exec_driver_sql("INSERT INTO alembic_version VALUES ('ar_9999_unknown')")
        else:
            connection.exec_driver_sql("UPDATE alembic_version SET version_num='ar_9999_unknown'")
    before = database.read_bytes()
    for operation in [
        lambda: service.schema_status(engine),
        lambda: service.upgrade(engine),
        lambda: service.adopt(engine, mapping, "b" * 64, "d" * 64),
    ]:
        with pytest.raises(MigrationRefused, match="schema_incompatible"):
            operation()
        assert database.read_bytes() == before
    assert_preserved_rows(database)


def test_sqlite_oversized_nonjson_cell_never_reaches_encoder_or_key_inventory(legacy, monkeypatch):
    from agent_rewind.migrations import inputs

    _, engine, mapping = legacy
    with engine.begin() as connection:
        connection.execute(text("UPDATE audit SET actor=:value"), {"value": "x" * 5000})
    monkeypatch.setattr(inputs, "MAX_ROW_BYTES", 4096)

    def unexpected_encode(*args, **kwargs):
        raise AssertionError("Oversized source reached canonical encoding")

    monkeypatch.setattr(inputs, "canonical", unexpected_encode)
    parsed = inputs.AdoptionMapping.model_validate(mapping)
    with (
        engine.connect() as connection,
        pytest.raises(MigrationRefused, match="source_limit_exceeded"),
    ):
        inputs.validate_legacy_rows(connection, parsed)


@pytest.mark.parametrize(
    "table,column", [("installation_adoptions", "mapping"), ("migration_progress", "cursor")]
)
def test_sqlite_additive_metadata_unindexed_collation_is_not_self_authorized(
    tmp_path, table, column
):
    engine = create_engine(f"sqlite:///{tmp_path / 'metadata-collation.sqlite'}")
    service.install(engine, "synthetic")
    with engine.begin() as connection:
        sql = connection.execute(
            text("SELECT sql FROM sqlite_master WHERE name=:name"), {"name": table}
        ).scalar_one()
        changed = sql.replace(f"{column} JSON NOT NULL", f"{column} JSON COLLATE NOCASE NOT NULL")
        assert changed != sql
        connection.exec_driver_sql(f"ALTER TABLE {table} RENAME TO old_metadata")
        connection.exec_driver_sql(changed)
        connection.exec_driver_sql(f"INSERT INTO {table} SELECT * FROM old_metadata")
        connection.exec_driver_sql("DROP TABLE old_metadata")
    with pytest.raises(MigrationRefused, match="schema_incompatible"):
        service.schema_status(engine)
    engine.dispose()
