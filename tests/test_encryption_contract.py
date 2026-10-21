"""Offline C07 composition vectors; no KMS, credentials, database or object service."""

import copy
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from legacy_fixture import FIXTURE_ROOT, read_manifest
from pydantic import ValidationError

from agent_rewind.artifact_metadata import ArtifactError, ArtifactObject
from agent_rewind.artifact_storage import LocalArtifactStorage
from agent_rewind.bounded_bytes import MAX_OBJECT_PLAINTEXT

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "encryption_contract", ROOT / "scripts/check_encryption_contract.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
FIXTURE = ROOT / "contracts/fixtures/encryption.synthetic.json"
VECTORS = json.loads(FIXTURE.read_text())["vectors"]


def vector(index=2):
    return copy.deepcopy(VECTORS[index])


def frame(item):
    return MODULE.decode64(item["frame"], 64 * 1024)


def expected(item):
    header = item["header"]
    return MODULE.Expected(header["project_id"], header["digest"], header["byte_count"])


def mock_unwrap(item, calls):
    def unwrap(version, wrapped, aad):
        calls.append(version)
        assert version == item["header"]["key_version"]
        assert len(wrapped) == 60
        return AESGCM(bytes.fromhex(item["public_test_kek_hex"])).decrypt(
            wrapped[:12], wrapped[12:], aad
        )

    return unwrap


def open_vector(item, *, body=None, context=None, unwrap=None, allowed=None, limit=65536):
    return MODULE.open_frame(
        frame(item) if body is None else body,
        expected(item) if context is None else context,
        mock_unwrap(item, []) if unwrap is None else unwrap,
        plaintext_limit=limit,
        allowed_key_versions=(
            frozenset({item["header"]["key_version"]}) if allowed is None else allowed
        ),
    )


def replace_header(item, value):
    original = frame(item)
    size = int.from_bytes(original[5:9], "big")
    body = MODULE.canonical(value)
    return MODULE.MAGIC + len(body).to_bytes(4, "big") + body + original[9 + size :]


def test_schema_and_committed_synthetic_vectors():
    assert json.loads((ROOT / "contracts/encryption-envelope.v1.schema.json").read_text()) == (
        MODULE.schema()
    )
    assert MODULE.check_fixture(FIXTURE) == 5
    assert MODULE.MAX_PLAINTEXT_BYTES == MAX_OBJECT_PLAINTEXT == 536870912
    assert MODULE.MAX_FRAME_BYTES == 536875033
    assert len({(v["public_test_dek_hex"], v["header"]["nonce"]) for v in VECTORS}) == 5


@pytest.mark.parametrize("index", range(5))
def test_known_bytes_decrypt_with_exact_content_and_context(index):
    item = vector(index)
    calls = []
    assert open_vector(item, unwrap=mock_unwrap(item, calls)) == bytes.fromhex(
        item["plaintext_hex"]
    )
    assert calls == [item["header"]["key_version"]]
    assert open_vector(item, limit=item["header"]["byte_count"]) == bytes.fromhex(
        item["plaintext_hex"]
    )


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("format_version", True),
        ("format_version", 2.0),
        ("format_version", "2"),
        ("format_version", 1),
        ("algorithm", "AES-128-GCM"),
        ("wrapping", "ambient"),
        ("project_id", "1" * 31),
        ("project_id", "1" * 32 + "\n"),
        ("digest", "A" * 64),
        ("byte_count", True),
        ("byte_count", -1),
        ("byte_count", 536870913),
        ("byte_count", 1.0),
        ("nonce", "A" * 15),
        ("nonce", "A" * 16 + "="),
        ("wrapped_dek", ""),
        ("wrapped_dek", "AB"),  # Nonzero unused bits, same decoded byte as canonical AA.
        ("wrapped_dek", "AA="),
        ("wrapped_dek", "A" * 1367),
        ("key_version", "https://attacker.invalid/metadata"),
        ("key_version", "projects/x/locations/y/keyRings/z/cryptoKeys/k/cryptoKeyVersions/01"),
        ("key_version", VECTORS[0]["header"]["key_version"] + "\n"),
        ("extra", "private-canary"),
    ],
)
def test_bad_headers_refuse_before_unwrap(field, bad):
    item = vector()
    changed = dict(item["header"], **{field: bad})
    calls = []
    with pytest.raises(MODULE.EnvelopeRefused, match="^envelope_unavailable$"):
        open_vector(item, body=replace_header(item, changed), unwrap=mock_unwrap(item, calls))
    assert calls == []


def test_largest_declared_header_fields_remain_bounded_and_round_trip():
    value = vector()["header"]
    prefix = "projects/p/locations/l/keyRings/r/cryptoKeys/"
    suffix = "/cryptoKeyVersions/1"
    value["key_version"] = prefix + "x" * (1024 - len(prefix) - len(suffix)) + suffix
    value["wrapped_dek"] = MODULE.encode64(b"x" * 1024)
    value["byte_count"] = MODULE.MAX_PLAINTEXT_BYTES
    header = MODULE.Header.model_validate(value)
    assert len(header.key_version) == 1024
    assert len(MODULE.decode64(header.wrapped_dek, 1024)) == 1024
    assert len(MODULE.canonical(header.model_dump())) <= MODULE.MAX_HEADER_BYTES
    # A claimed maximum object with no ciphertext must refuse, never count as a valid empty object.
    truncated = MODULE.MAGIC + (1).to_bytes(4, "big") + b"{}"
    with pytest.raises(MODULE.EnvelopeRefused):
        MODULE.parse_frame(
            truncated,
            MODULE.Expected(header.project_id, header.digest, header.byte_count),
            plaintext_limit=MODULE.MAX_PLAINTEXT_BYTES,
        )
    value["key_version"] += "x"
    with pytest.raises(ValidationError):
        MODULE.Header.model_validate(value)


@pytest.mark.parametrize(
    "change",
    [
        lambda b: b"",
        lambda b: b[:8],
        lambda b: b"RWE3\0" + b[5:],
        lambda b: b[:5] + (0).to_bytes(4, "big") + b[9:],
        lambda b: b[:5] + (4097).to_bytes(4, "big") + b[9:],
        lambda b: b[:5] + (2**32 - 1).to_bytes(4, "big") + b[9:],
        lambda b: b[:-1],
        lambda b: b + b"trailing",
    ],
)
def test_frame_lengths_and_magic_refuse_before_unwrap(change):
    item = vector()
    calls = []
    with pytest.raises(MODULE.EnvelopeRefused):
        open_vector(item, body=change(frame(item)), unwrap=mock_unwrap(item, calls))
    assert calls == []


@pytest.mark.parametrize(
    "header_body",
    [
        b'{"format_version":2,"format_version":2}',
        b'{"byte_count":NaN}',
        b'{"byte_count":Infinity}',
        b"[" * 1000,
        b"\xff",
        b"null",
        b"[]",
    ],
)
def test_bad_json_is_fixed_refusal_before_provider(header_body):
    item = vector()
    calls = []
    body = MODULE.MAGIC + len(header_body).to_bytes(4, "big") + header_body + b"x" * 100
    with pytest.raises(MODULE.EnvelopeRefused):
        open_vector(item, body=body, unwrap=mock_unwrap(item, calls))
    assert calls == []


def test_noncanonical_equivalent_header_refuses():
    item = vector()
    encoded = json.dumps(item["header"], indent=2).encode()
    original = frame(item)
    size = int.from_bytes(original[5:9], "big")
    body = MODULE.MAGIC + len(encoded).to_bytes(4, "big") + encoded + original[9 + size :]
    calls = []
    with pytest.raises(MODULE.EnvelopeRefused):
        open_vector(item, body=body, unwrap=mock_unwrap(item, calls))
    assert calls == []


@pytest.mark.parametrize("field", ["project_id", "digest", "byte_count"])
def test_authorized_content_mismatch_precedes_unwrap(field):
    item = vector()
    values = vars(expected(item)) | {
        field: {"project_id": "f" * 32, "digest": "f" * 64, "byte_count": 0}[field]
    }
    calls = []
    with pytest.raises(MODULE.EnvelopeRefused):
        open_vector(item, context=MODULE.Expected(**values), unwrap=mock_unwrap(item, calls))
    assert calls == []


@pytest.mark.parametrize("limit", [-1, True, 536870913, 0])
def test_caller_limit_cannot_be_bypassed(limit):
    calls = []
    item = vector()
    with pytest.raises(MODULE.EnvelopeRefused):
        open_vector(item, limit=limit, unwrap=mock_unwrap(item, calls))
    assert calls == []


def test_cross_project_same_plaintext_and_key_rotation_do_not_adopt_ciphertext():
    a, b, rotated = vector(2), vector(3), vector(4)
    assert a["header"]["digest"] == b["header"]["digest"] == rotated["header"]["digest"]
    assert a["wrapping_aad_hex"] != b["wrapping_aad_hex"]
    assert a["frame"] != b["frame"] != rotated["frame"]
    with pytest.raises(MODULE.EnvelopeRefused):
        open_vector(b, body=frame(a))
    # Old retained version remains readable after a new active write; removing it fails closed.
    allowed = frozenset({a["header"]["key_version"], rotated["header"]["key_version"]})
    assert open_vector(a, allowed=allowed) == open_vector(rotated, allowed=allowed)
    calls = []
    with pytest.raises(MODULE.EnvelopeRefused):
        open_vector(
            a, allowed=frozenset({rotated["header"]["key_version"]}), unwrap=mock_unwrap(a, calls)
        )
    assert calls == []


@pytest.mark.parametrize("field", ["nonce", "wrapped_dek", "key_version"])
def test_authenticated_header_fields_cannot_be_changed_after_wrapping(field):
    item = vector()
    changed = dict(item["header"])
    if field == "key_version":
        changed[field] = changed[field][:-1] + "2"
    else:
        raw = MODULE.decode64(changed[field], 1024)
        changed[field] = MODULE.encode64(bytes([raw[0] ^ 1]) + raw[1:])
    # Even a permissive mock returning the original DEK cannot authenticate an altered header.
    with pytest.raises(MODULE.EnvelopeRefused):
        open_vector(
            item,
            body=replace_header(item, changed),
            allowed=frozenset({changed["key_version"]}),
            unwrap=lambda *_: bytes.fromhex(item["public_test_dek_hex"]),
        )


def test_corrupt_tag_and_wrong_plaintext_digest_return_no_plaintext():
    item = vector()
    body = frame(item)
    with pytest.raises(MODULE.EnvelopeRefused):
        open_vector(item, body=body[:-1] + bytes([body[-1] ^ 1]))
    changed = dict(item["header"], digest="f" * 64)
    header_body = MODULE.canonical(changed)
    prefix = MODULE.MAGIC + len(header_body).to_bytes(4, "big") + header_body
    # Valid tag over deliberately dishonest declared digest must still fail the plaintext check.
    ciphertext = AESGCM(bytes.fromhex(item["public_test_dek_hex"])).encrypt(
        MODULE.decode64(changed["nonce"], 12),
        bytes.fromhex(item["plaintext_hex"]),
        MODULE.DATA_DOMAIN + prefix,
    )
    with pytest.raises(MODULE.EnvelopeRefused):
        open_vector(
            item,
            body=prefix + ciphertext,
            context=MODULE.Expected(
                changed["project_id"], changed["digest"], changed["byte_count"]
            ),
            unwrap=lambda *_: bytes.fromhex(item["public_test_dek_hex"]),
        )


@pytest.mark.parametrize("failure", ["denied", "disabled", "destroyed", "timeout", "integrity"])
def test_provider_errors_are_fixed_and_do_not_retry_or_fall_back(failure):
    calls = []

    def refused(*_):
        calls.append(failure)
        raise RuntimeError("private-provider-canary " + failure)

    with pytest.raises(MODULE.EnvelopeRefused) as caught:
        open_vector(vector(), unwrap=refused)
    assert calls == [failure]
    assert str(caught.value) == "envelope_unavailable"
    assert caught.value.__suppress_context__
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("key", [b"x" * 16, b"x" * 24, b"x" * 31, b"x" * 33, "private-key-canary"])
def test_unwrap_must_return_exact_256_bit_bytes(key):
    with pytest.raises(MODULE.EnvelopeRefused):
        open_vector(vector(), unwrap=lambda *_: key)


def test_legacy_fixture_bytes_stay_format_one_and_do_not_fall_back():
    manifest = read_manifest()
    cipher = Fernet(manifest["synthetic_fernet_key"].encode())
    storage = LocalArtifactStorage(FIXTURE_ROOT, cipher, plaintext_limit=MAX_OBJECT_PLAINTEXT)
    objects = sorted((FIXTURE_ROOT / "objects").iterdir())
    assert len(objects) == 18
    for path in objects:
        original = path.read_bytes()
        plaintext = cipher.decrypt(original)
        descriptor = ArtifactObject(
            id="a" * 32,
            project_id="1" * 32,
            digest=path.name,
            locator="objects/" + path.name,
            format_version=1,
            byte_count=len(plaintext),
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        assert storage.read_verified(descriptor) == plaintext
        assert hashlib.sha256(plaintext).hexdigest() == path.name
        assert path.read_bytes() == original
        calls = []
        with pytest.raises(MODULE.EnvelopeRefused):
            MODULE.open_frame(
                original,
                MODULE.Expected("1" * 32, path.name, len(plaintext)),
                mock_unwrap(vector(), calls),
                plaintext_limit=MAX_OBJECT_PLAINTEXT,
                allowed_key_versions=frozenset({vector()["header"]["key_version"]}),
            )
        assert calls == []


def test_cli_reports_only_offline_validity_and_fixed_invalid_input(tmp_path):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env.pop("PYTHONPATH", None)
    script = ROOT / "scripts/check_encryption_contract.py"
    good = subprocess.run(
        [sys.executable, str(script), str(FIXTURE)],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(good.stdout) == {"valid": True, "deployable": False, "synthetic_vectors": 5}
    bad = tmp_path / "bad.json"
    bad.write_text('{"private-canary":')
    failed = subprocess.run(
        [sys.executable, str(script), str(bad)],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert failed.returncode == 2 and not failed.stderr
    assert json.loads(failed.stdout) == {
        "valid": False,
        "deployable": False,
        "error": "invalid-encryption-fixture",
    }
    assert "private-canary" not in failed.stdout


def test_fixture_reader_caps_size_and_refuses_nonregular_files(tmp_path):
    huge = tmp_path / "huge"
    huge.write_bytes(b" " * (MODULE.MAX_FIXTURE_BYTES + 1))
    link = tmp_path / "link"
    link.symlink_to(FIXTURE)
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    for path in (huge, link, fifo, tmp_path):
        with pytest.raises((MODULE.EnvelopeRefused, OSError)):
            MODULE.check_fixture(path)


def test_key_configuration_is_bounded_without_evicting_retained_keys():
    item = vector()
    version = item["header"]["key_version"]
    base = version.rsplit("/", 1)[0]
    maximum = frozenset(base + "/" + str(n) for n in range(1, 33))
    assert open_vector(item, allowed=maximum) == bytes.fromhex(item["plaintext_hex"])
    for allowed in (frozenset(), maximum | {base + "/33"}, frozenset({version, "invalid"})):
        calls = []
        with pytest.raises(MODULE.EnvelopeRefused):
            open_vector(item, allowed=allowed, unwrap=mock_unwrap(item, calls))
        assert calls == []


def test_wrong_wrapping_aad_cannot_unwrap_even_same_ciphertext_and_key():
    item = vector()
    calls = []
    unwrap = mock_unwrap(item, calls)

    def wrong_context(version, wrapped, aad):
        value = json.loads(aad)
        value["project_id"] = "f" * 32
        return unwrap(version, wrapped, MODULE.canonical(value))

    with pytest.raises(MODULE.EnvelopeRefused):
        open_vector(item, unwrap=wrong_context)
    assert calls == [item["header"]["key_version"]]


def test_contract_does_not_enable_current_runtime_format_two(tmp_path):
    item = vector()
    path = tmp_path / "objects"
    path.mkdir()
    blob = path / item["header"]["digest"]
    blob.write_bytes(frame(item))
    storage = LocalArtifactStorage(
        tmp_path, Fernet(read_manifest()["synthetic_fernet_key"].encode()), plaintext_limit=4096
    )
    descriptor = SimpleNamespace(
        id="a" * 32,
        project_id=item["header"]["project_id"],
        digest=blob.name,
        locator="objects/" + blob.name,
        format_version=2,
        byte_count=item["header"]["byte_count"],
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    with pytest.raises(ArtifactError, match="^artifact_format_unsupported$"):
        storage.read_verified(descriptor)
    assert blob.read_bytes() == frame(item)


def exported_string_accepts(field, value):
    """Evaluate the exported string-keyword subset using JSON Schema search semantics."""
    exported = json.loads((ROOT / "contracts/encryption-envelope.v1.schema.json").read_text())
    rule = exported["properties"][field]
    assert set(rule) <= {"type", "title", "pattern", "minLength", "maxLength", "not"}
    assert rule["type"] == "string"
    if not rule.get("minLength", 0) <= len(value) <= rule.get("maxLength", 100000):
        return False
    if re.search(rule["pattern"], value) is None:
        return False
    if "not" in rule:
        assert set(rule["not"]) == {"pattern"}
        if re.search(rule["not"]["pattern"], value) is not None:
            return False
    return True


@pytest.mark.parametrize("field", ["project_id", "digest", "nonce", "key_version", "wrapped_dek"])
@pytest.mark.parametrize("control", ["\n", "\r", "\r\n", "\u2028", "\u2029", "\x00", "\x7f"])
def test_exported_schema_rejects_terminal_controls_without_fullmatch(field, control):
    value = vector()["header"]
    value[field] += control
    assert not exported_string_accepts(field, value[field])
    with pytest.raises(ValidationError):
        MODULE.Header.model_validate(value)


def test_exported_schema_retains_existing_valid_ascii_vectors():
    for item in VECTORS:
        for field in ["project_id", "digest", "nonce", "key_version", "wrapped_dek"]:
            assert exported_string_accepts(field, item["header"][field])
