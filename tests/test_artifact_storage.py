"""Bounded format-1 reads and immutable local publication; no DB root publication."""

import hashlib
import io
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from legacy_fixture import materialize_legacy, read_manifest
from test_artifact_metadata import OTHER, object_value

from agent_rewind.artifact_metadata import ArtifactError
from agent_rewind.artifact_storage import LocalArtifactStorage
from agent_rewind.bounded_bytes import BoundedReadError, ciphertext_limit, read_ciphertext

DATA = b"frozen-content"


@pytest.fixture
def local(tmp_path):
    return LocalArtifactStorage(tmp_path, Fernet(Fernet.generate_key()), plaintext_limit=4096)


def test_write_is_verified_then_cache_hit_retains_ciphertext(local):
    value = object_value()
    first = local.put_verified(value, DATA)
    before = (local.root / value.locator).read_bytes()
    second = local.put_verified(value, DATA)
    assert local.read_verified(value) == DATA
    assert first.logical_writes == second.logical_writes == 1
    assert (first.write_requests, first.read_requests, first.cache_hit) == (1, 2, False)
    assert (second.write_requests, second.read_requests, second.cache_hit) == (0, 1, True)
    assert (local.root / value.locator).read_bytes() == before
    assert not list(local.root.rglob(".object-*"))


def test_concurrent_puts_never_clobber_winner(local):
    value = object_value()
    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(lambda _: local.put_verified(value, DATA), range(4)))
    assert sum(not r.cache_hit for r in outcomes) == 1
    assert local.read_verified(value) == DATA
    before = (local.root / value.locator).read_bytes()
    local.put_verified(value, DATA)
    assert (local.root / value.locator).read_bytes() == before


def test_equal_bytes_different_projects_have_independent_locators(local):
    left, right = object_value(), object_value(OTHER)
    local.put_verified(left, DATA)
    local.put_verified(right, DATA)
    assert left.locator != right.locator
    assert (local.root / left.locator).read_bytes() != (local.root / right.locator).read_bytes()
    assert local.read_verified(left) == local.read_verified(right) == DATA


@pytest.mark.parametrize("corrupt", [b"invalid-ciphertext", b"x" * 200])
def test_existing_corruption_is_never_replaced(local, corrupt):
    value = object_value()
    path = local.root / value.locator
    path.parent.mkdir(parents=True)
    path.write_bytes(corrupt)
    with pytest.raises(ArtifactError, match="artifact_integrity"):
        local.put_verified(value, DATA)
    assert path.read_bytes() == corrupt


def test_declared_size_bound_precedes_decrypt(local, monkeypatch):
    value = object_value()
    path = local.root / value.locator
    path.parent.mkdir(parents=True)
    path.write_bytes(b"x" * (ciphertext_limit(value.byte_count) + 1))

    def forbidden(*args, **kwargs):
        raise AssertionError("decrypt should not run")

    monkeypatch.setattr(local.cipher, "decrypt", forbidden)
    with pytest.raises(ArtifactError, match="artifact_integrity"):
        local.read_verified(value)


@pytest.mark.parametrize("kind", ["symlink", "fifo", "directory"])
def test_nonregular_objects_refuse_without_blocking(local, kind, tmp_path):
    value = object_value()
    path = local.root / value.locator
    path.parent.mkdir(parents=True)
    if kind == "symlink":
        target = tmp_path / "target"
        target.write_bytes(local.cipher.encrypt(DATA))
        path.symlink_to(target)
    elif kind == "fifo":
        os.mkfifo(path)
    else:
        path.mkdir()
    with pytest.raises(ArtifactError, match="artifact_integrity"):
        local.read_verified(value)


def test_parent_symlink_is_not_followed(local, tmp_path):
    value = object_value()
    target = tmp_path / "foreign"
    target.mkdir()
    (local.root / "objects").symlink_to(target, target_is_directory=True)
    with pytest.raises(ArtifactError, match="artifact_integrity"):
        local.put_verified(value, DATA)
    assert not list(target.iterdir())


def test_wrong_plaintext_digest_and_mismatched_size_refuse(local):
    value = object_value()
    with pytest.raises(ArtifactError, match="artifact_integrity"):
        local.put_verified(value, b"wrong")
    local.put_verified(value, DATA)
    path = local.root / value.locator
    path.write_bytes(local.cipher.encrypt(b"wrong-content!"))
    with pytest.raises(ArtifactError, match="artifact_integrity"):
        local.read_verified(value)


def test_configured_cap_checked_before_encrypt_or_read(local, monkeypatch):
    value = replace(object_value(), byte_count=4097)

    def forbidden(*args, **kwargs):
        raise AssertionError("crypto should not run")

    monkeypatch.setattr(local.cipher, "encrypt", forbidden)
    with pytest.raises(ArtifactError, match="artifact_limit"):
        local.put_verified(value, b"x" * 4097)
    with pytest.raises(ArtifactError, match="artifact_limit"):
        local.read_verified(value)


def test_short_reads_excess_byte_and_unchanged_sentinel_cap():
    class Short(io.BytesIO):
        def read(self, size=-1):
            return super().read(min(size, 3))

    assert read_ciphertext(Short(b"12345"), limit=5) == b"12345"
    with pytest.raises(BoundedReadError, match="ciphertext_limit"):
        read_ciphertext(Short(b"123456"), limit=5)
    assert ciphertext_limit(4096) == 5560
    with pytest.raises(BoundedReadError, match="ciphertext_limit"):
        read_ciphertext(io.BytesIO(b"x" * 5561))


def test_registered_legacy_format_read_does_not_reencrypt(local):
    value = object_value(legacy=True)
    path = local.root / value.locator
    path.parent.mkdir(parents=True)
    ciphertext = local.cipher.encrypt(DATA)
    path.write_bytes(ciphertext)
    assert local.read_verified(value) == DATA and path.read_bytes() == ciphertext
    with pytest.raises(ArtifactError, match="legacy_artifact_write_forbidden"):
        local.put_verified(value, DATA)


def test_fixed_legacy_ciphertext_is_still_readable(tmp_path):
    path = materialize_legacy(tmp_path / "legacy")
    manifest = read_manifest()
    # Exact public synthetic fixture key, never a production credential.
    key = manifest["synthetic_fernet_key"]
    storage = LocalArtifactStorage(
        path.parent, Fernet(key.encode()), plaintext_limit=512 * 1024 * 1024
    )
    for item in (path.parent / "objects").iterdir():
        original = item.read_bytes()
        plaintext = storage.cipher.decrypt(original)
        value = replace(
            object_value(legacy=True),
            digest=item.name,
            locator=f"objects/{item.name}",
            byte_count=len(plaintext),
        )
        assert hashlib.sha256(storage.read_verified(value)).hexdigest() == item.name
        assert item.read_bytes() == original


def test_structural_descriptor_is_validated_before_storage(local):
    value = object_value()
    local.put_verified(value, DATA)
    descriptor = SimpleNamespace(**asdict(value))
    assert local.read_verified(descriptor) == DATA
    descriptor.format_version = True
    with pytest.raises(ArtifactError, match="artifact_format_unsupported"):
        local.read_verified(descriptor)
    descriptor.format_version = 1
    descriptor.locator = "../../foreign"
    with pytest.raises(ArtifactError, match="artifact_locator_invalid"):
        local.read_verified(descriptor)


def test_failed_temporary_write_never_publishes_partial_ciphertext(local, monkeypatch):
    value = object_value()

    def fail_sync(descriptor):
        raise OSError("synthetic sync failure")

    monkeypatch.setattr(os, "fsync", fail_sync)
    with pytest.raises(ArtifactError, match="artifact_integrity"):
        local.put_verified(value, DATA)
    assert not (local.root / value.locator).exists()
    assert not list(local.root.rglob(".object-*"))
