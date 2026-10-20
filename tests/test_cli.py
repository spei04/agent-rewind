from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import dotenv_values

from agent_rewind.cli import main


def test_init_fills_empty_keys_and_preserves_existing_provider_secret(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["rewind", "init"])
    Path(".env").write_text(
        "REWIND_ENCRYPTION_KEY=\nREWIND_BOOTSTRAP_KEY=\nREWIND_MODEL_API_KEY=fixture-secret\n"
    )
    main()
    before = dotenv_values(".env")
    Fernet(before["REWIND_ENCRYPTION_KEY"].encode())
    assert before["REWIND_MODEL_API_KEY"] == "fixture-secret"
    assert len(before["REWIND_BOOTSTRAP_KEY"]) >= 32
    main()
    assert dotenv_values(".env") == before


def test_init_without_key_does_not_initialize_metadata(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["rewind", "init"])

    def forbidden(*args, **kwargs):
        raise AssertionError("Secret initialization invoked a metadata migration")

    monkeypatch.setattr("agent_rewind.migrations.service.install", forbidden)
    monkeypatch.setattr("agent_rewind.database.Database.migrate", forbidden)
    main()
    assert Path(".env").is_file()
    assert not Path(".rewind/metadata.sqlite").exists()


def test_init_with_explicit_key_creates_only_prepared_metadata(tmp_path, monkeypatch):
    from sqlalchemy import create_engine

    from agent_rewind.migrations.compatibility import runtime_schema_compatibility
    from agent_rewind.migrations.service import schema_status

    monkeypatch.chdir(tmp_path)
    database = tmp_path / "explicit.sqlite"
    monkeypatch.setenv("REWIND_DATABASE_URL", f"sqlite:///{database}")
    monkeypatch.delenv("REWIND_MIGRATION_DATABASE_URL", raising=False)
    monkeypatch.setattr("sys.argv", ["rewind", "init", "--installation-key", "synthetic-cli"])
    main()
    engine = create_engine(f"sqlite:///{database}")
    try:
        assert schema_status(engine)["state"] == "prepared"
        assert runtime_schema_compatibility(engine).code == "migration_only"
    finally:
        engine.dispose()
