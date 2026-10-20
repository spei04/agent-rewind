import hashlib
import io
import json
import os
import time
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr, ValidationError

from agent_rewind.bounded_bytes import (
    MAX_CIPHERTEXT,
    BoundedReadError,
    decrypt_checked,
    read_ciphertext,
    regular_reader,
)
from agent_rewind.sentinel import (
    SentinelConfig,
    SentinelSettings,
    _Store,
    canonical_payload,
    load_config,
    provision,
    read_system_sentinel,
)


@pytest.fixture
def sentinel(settings):
    return SentinelSettings(
        _env_file=None,
        data_dir=settings.data_dir,
        encryption_key=settings.encryption_key,
        installation_key=SecretStr("synthetic-install"),
    )


def test_explicit_install_exact_identity_and_idempotence(sentinel):
    provision(sentinel)
    config = load_config(sentinel.data_dir)
    assert config.locator == "system/synthetic-install/readiness-v1"
    assert config.digest == hashlib.sha256(canonical_payload("synthetic-install")).hexdigest()
    path = sentinel.data_dir / config.locator
    original = path.read_bytes()
    provision(sentinel)
    assert path.read_bytes() == original
    assert read_system_sentinel(
        sentinel, time.monotonic() + 1, installation_key="synthetic-install"
    ) == (b'{"installation_key":"synthetic-install","purpose":"readiness","schema":1}')
    assert (sentinel.data_dir / "readiness.json").stat().st_mode & 0o777 == 0o600


def test_read_missing_sentinel_never_writes(sentinel):
    with pytest.raises(FileNotFoundError):
        read_system_sentinel(sentinel, time.monotonic() + 1, installation_key="synthetic-install")
    assert not list(sentinel.data_dir.iterdir())


def test_cipher_bound_checks_short_reads_and_first_excess():
    class Chunks(io.BytesIO):
        def read(self, amount):
            assert 0 < amount <= MAX_CIPHERTEXT + 1
            return super().read(min(amount, 3))

    assert read_ciphertext(Chunks(b"abcde")) == b"abcde"
    excessive = Chunks(b"x" * (MAX_CIPHERTEXT + 1000))
    with pytest.raises(BoundedReadError, match="ciphertext_limit"):
        read_ciphertext(excessive)
    assert excessive.tell() == MAX_CIPHERTEXT + 1


def test_reject_oversize_before_decrypt_and_plaintext_limit():
    def forbidden(*args):
        pytest.fail("decrypt called on oversized ciphertext")

    with pytest.raises(BoundedReadError, match="ciphertext_limit"):
        decrypt_checked(b"x" * 5561, SimpleNamespace(decrypt=forbidden), "0" * 64)
    cipher = Fernet(Fernet.generate_key())
    oversized = b"x" * 4097
    assert len(cipher.encrypt(oversized)) == 5560
    with pytest.raises(BoundedReadError, match="plaintext_limit"):
        decrypt_checked(cipher.encrypt(oversized), cipher, hashlib.sha256(oversized).hexdigest())


@pytest.mark.parametrize("kind", ["fifo", "symlink", "oversize"])
def test_local_special_files_and_oversize_refused(tmp_path, kind):
    path = tmp_path / "sentinel"
    if kind == "fifo":
        os.mkfifo(path)
    elif kind == "symlink":
        path.symlink_to(tmp_path / "missing")
    else:
        path.write_bytes(b"x" * 5561)
    with pytest.raises((OSError, BoundedReadError)), regular_reader(path) as stream:
        read_ciphertext(stream)


@pytest.mark.parametrize("corruption", ["key", "cipher", "digest", "customer", "mode", "directory"])
def test_sentinel_corruption_refuses(sentinel, corruption):
    provision(sentinel)
    config_path = sentinel.data_dir / "readiness.json"
    config = load_config(sentinel.data_dir)
    if corruption == "key":
        sentinel.encryption_key = SecretStr(Fernet.generate_key().decode())
    elif corruption == "cipher":
        (sentinel.data_dir / config.locator).write_bytes(b"not-a-token")
    elif corruption in {"digest", "customer"}:
        data = json.loads(config_path.read_text())
        data["digest" if corruption == "digest" else "locator"] = (
            "0" * 64 if corruption == "digest" else "objects/" + config.digest
        )
        config_path.write_text(json.dumps(data))
    elif corruption == "mode":
        config_path.chmod(0o644)
    else:
        directory = sentinel.data_dir / "system"
        directory.rename(sentinel.data_dir / "elsewhere")
        directory.symlink_to(sentinel.data_dir / "elsewhere", target_is_directory=True)
    with pytest.raises((ValueError, OSError, InvalidToken)):
        read_system_sentinel(sentinel, time.monotonic() + 1, installation_key="synthetic-install")


@pytest.mark.parametrize("change", ["length", "range", "overflow", "ignored-range"])
def test_s3_length_range_bound_and_close(sentinel, monkeypatch, change):
    key = "synthetic-install"
    config = SentinelConfig(
        installation_key=key,
        locator=f"system/{key}/readiness-v1",
        digest=hashlib.sha256(canonical_payload(key)).hexdigest(),
    )
    token = Fernet(sentinel.encryption_key.get_secret_value().encode()).encrypt(
        canonical_payload(key)
    )
    if change == "overflow":
        token = b"x" * 10000
    body = io.BytesIO(token)

    def get_object(**kwargs):
        assert kwargs == {
            "Bucket": "synthetic-bucket",
            "Key": config.locator,
            "Range": "bytes=0-5560",
        }
        response = {"Body": body, "ContentLength": len(token)}
        if change == "length":
            response["ContentLength"] = 1
        elif change == "range":
            response["ContentRange"] = f"bytes 1-{len(token)}/{len(token)}"
        return response

    monkeypatch.setattr(
        "agent_rewind.sentinel.boto3.client",
        lambda *a, **kw: SimpleNamespace(get_object=get_object),
    )
    sentinel.storage, sentinel.s3_bucket = "s3", "synthetic-bucket"
    if change == "ignored-range":
        assert _Store(sentinel).read(config) == canonical_payload(key)
    else:
        with pytest.raises(ValueError):
            _Store(sentinel).read(config)
    assert body.closed


def test_deadline_rejected_before_io(sentinel):
    with pytest.raises(TimeoutError):
        read_system_sentinel(sentinel, time.monotonic() - 1, installation_key="synthetic-install")
    assert not list(sentinel.data_dir.iterdir())


def test_invalid_identity_never_creates_customer_path(sentinel):
    sentinel.installation_key = SecretStr("../objects")
    with pytest.raises(ValidationError):
        provision(sentinel)
    assert not list(sentinel.data_dir.iterdir())


def test_doctor_provision_is_separate_from_database_and_model(sentinel, monkeypatch, capsys):
    from agent_rewind.cli import main

    monkeypatch.chdir(sentinel.data_dir)
    monkeypatch.setenv("REWIND_DATA_DIR", str(sentinel.data_dir))
    monkeypatch.setenv("REWIND_ENCRYPTION_KEY", sentinel.encryption_key.get_secret_value())
    monkeypatch.setenv("REWIND_INSTALLATION_KEY", "synthetic-install")
    monkeypatch.setenv("REWIND_DATABASE_URL", "invalid-private-database-canary")
    monkeypatch.setenv("REWIND_MODEL_API_KEY", "unused-provider-canary")
    monkeypatch.setattr("sys.argv", ["rewind", "doctor", "--provision-sentinel"])
    main()
    assert capsys.readouterr().out == '{"sentinel": "verified"}\n'
    assert load_config(sentinel.data_dir).installation_key == "synthetic-install"


def test_failed_provision_has_fixed_cli_error(sentinel, monkeypatch, capsys):
    from agent_rewind.sentinel_cli import provision_sentinel

    monkeypatch.chdir(sentinel.data_dir)
    monkeypatch.setenv("REWIND_DATA_DIR", str(sentinel.data_dir))
    monkeypatch.setenv("REWIND_ENCRYPTION_KEY", "invalid-private-encryption-canary")
    monkeypatch.setenv("REWIND_INSTALLATION_KEY", "synthetic-install")
    with pytest.raises(SystemExit, match="^sentinel_install_failed$"):
        provision_sentinel()
    captured = capsys.readouterr()
    assert "canary" not in captured.out + captured.err


def test_interrupted_local_publication_never_installs_partial_object(sentinel, monkeypatch):
    original = os.link

    def interrupted(*args, **kwargs):
        raise InterruptedError("synthetic-publication-interruption")

    monkeypatch.setattr("agent_rewind.sentinel.os.link", interrupted)
    with pytest.raises(InterruptedError):
        provision(sentinel)
    target = sentinel.data_dir / "system/synthetic-install"
    assert list(target.iterdir()) == []
    assert not (sentinel.data_dir / "readiness.json").exists()
    monkeypatch.setattr("agent_rewind.sentinel.os.link", original)
    provision(sentinel)
    assert load_config(sentinel.data_dir).installation_key == "synthetic-install"
