"""Explicit operator projection commands without unrelated runtime credentials."""

import json

import pytest
import test_run_projection_backfill as backfill_tests
from legacy_fixture import read_manifest
from sqlalchemy import text

from agent_rewind.cli import main
from agent_rewind.migrations.schema import PROJECTION

legacy = backfill_tests.legacy


def configure(monkeypatch, tmp_path, engine):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REWIND_DATABASE_URL", str(engine.url))
    monkeypatch.delenv("REWIND_MIGRATION_DATABASE_URL", raising=False)
    for name in ("REWIND_ENCRYPTION_KEY", "REWIND_MODEL_API_KEY", "REWIND_OIDC_CLIENT_SECRET"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("REWIND_MODE", "production")


def invoke(monkeypatch, *args):
    monkeypatch.setattr("sys.argv", ["rewind", "migrate", *args])
    main()


def test_projection_schema_only_and_explicit_key_backfill(legacy, monkeypatch, tmp_path, capsys):
    path, engine, _ = legacy
    configure(monkeypatch, tmp_path, engine)
    invoke(monkeypatch, "upgrade", "--target", PROJECTION)
    installed = json.loads(capsys.readouterr().out)
    assert installed["projection_status"] == "running"
    monkeypatch.setenv("REWIND_ENCRYPTION_KEY", read_manifest()["synthetic_fernet_key"])
    invoke(
        monkeypatch, "projection-backfill", "--source-root", str(path.parent), "--batch-size", "1"
    )
    first = json.loads(capsys.readouterr().out)
    assert first["projection_rows_verified"] == 1 and not first["customer_ready"]
    invoke(
        monkeypatch, "projection-backfill", "--source-root", str(path.parent), "--batch-size", "1"
    )
    second = json.loads(capsys.readouterr().out)
    assert second["projection_status"] == "complete" and not second["customer_ready"]


@pytest.mark.parametrize("key", [None, "synthetic-private-canary"])
def test_missing_or_invalid_projection_key_refuses_safely(
    legacy, monkeypatch, tmp_path, capsys, key
):
    path, engine, _ = legacy
    configure(monkeypatch, tmp_path, engine)
    invoke(monkeypatch, "upgrade", "--target", PROJECTION)
    capsys.readouterr()
    if key is not None:
        monkeypatch.setenv("REWIND_ENCRYPTION_KEY", key)
    with pytest.raises(SystemExit) as error:
        invoke(monkeypatch, "projection-backfill", "--source-root", str(path.parent))
    assert error.value.code == 2
    output = capsys.readouterr()
    assert "valid_projection_encryption_key_required" in output.err
    assert "synthetic-private-canary" not in output.err
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM run_index")).scalar_one() == 0


def test_projection_pg_mutation_requires_separate_dsn_before_connect(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "REWIND_DATABASE_URL", "postgresql+psycopg://fixture:fixture@127.0.0.1/fixture"
    )
    monkeypatch.delenv("REWIND_MIGRATION_DATABASE_URL", raising=False)
    monkeypatch.setattr("agent_rewind.cli.create_engine", lambda *_: pytest.fail("connected"))
    with pytest.raises(SystemExit):
        invoke(monkeypatch, "projection-backfill", "--source-root", str(tmp_path))
    assert "dedicated_migration_database_url_required" in capsys.readouterr().err
