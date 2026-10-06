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
