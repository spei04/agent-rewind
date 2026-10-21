"""Offline C07 wire reference and synthetic-vector check; never a runtime KMS adapter."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import stat
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

MAGIC = b"RWE2\x00"
PREFIX_BYTES = len(MAGIC) + 4
MAX_HEADER_BYTES = 4096
MAX_WRAPPED_DEK_BYTES = 1024
MAX_KEY_VERSION_BYTES = 1024
MAX_ALLOWED_KEY_VERSIONS = 32
MAX_PLAINTEXT_BYTES = 512 * 1024 * 1024
TAG_BYTES = 16
MAX_FRAME_BYTES = PREFIX_BYTES + MAX_HEADER_BYTES + MAX_PLAINTEXT_BYTES + TAG_BYTES
MAX_FIXTURE_BYTES = 128 * 1024
DATA_DOMAIN = b"agent-rewind:artifact-data:v2\x00"
KEY_VERSION_PATTERN = (
    r"projects/[a-z0-9][a-z0-9-]*/locations/[a-z0-9-]+/"
    r"keyRings/[A-Za-z0-9_-]+/cryptoKeys/[A-Za-z0-9_-]+/"
    r"cryptoKeyVersions/[1-9][0-9]{0,19}"
)
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Project = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
Unwrap = Callable[[str, bytes, bytes], bytes]


class EnvelopeRefused(ValueError):
    """Fixed offline diagnostic: no key, resource, bytes or provider error is echoed."""

    def __init__(self) -> None:
        super().__init__("envelope_unavailable")


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def encode64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def decode64(value: str, maximum: int) -> bytes:
    if len(value) > (maximum * 8 + 5) // 6 or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise EnvelopeRefused()
    try:
        result = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, binascii.Error):
        raise EnvelopeRefused() from None
    if not 1 <= len(result) <= maximum or encode64(result) != value:
        raise EnvelopeRefused()
    return result


class Header(BaseModel):
    """Schema version 1 describes proposed ciphertext format 2, not current format 1."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    format_version: Literal[2]
    algorithm: Literal["AES-256-GCM"]
    wrapping: Literal["gcp-kms-symmetric-v1"]
    project_id: Project
    digest: Digest
    byte_count: Annotated[int, Field(ge=0, le=MAX_PLAINTEXT_BYTES)]
    nonce: Annotated[str, Field(min_length=16, max_length=16, pattern=r"^[A-Za-z0-9_-]{16}$")]
    key_version: Annotated[
        str,
        Field(
            min_length=1, max_length=MAX_KEY_VERSION_BYTES, pattern="^" + KEY_VERSION_PATTERN + "$"
        ),
    ]
    wrapped_dek: Annotated[str, Field(min_length=2, max_length=1366, pattern=r"^[A-Za-z0-9_-]+$")]

    @model_validator(mode="before")
    @classmethod
    def exact_version(cls, value: object) -> object:
        if isinstance(value, dict) and type(value.get("format_version")) is not int:
            raise ValueError("Invalid format type.")
        return value

    @model_validator(mode="after")
    def canonical_fields(self) -> Header:
        if (
            not re.fullmatch(r"[0-9a-f]{32}", self.project_id)
            or not re.fullmatch(r"[0-9a-f]{64}", self.digest)
            or not re.fullmatch(KEY_VERSION_PATTERN, self.key_version)
            or len(decode64(self.nonce, 12)) != 12
        ):
            raise EnvelopeRefused()
        decode64(self.wrapped_dek, MAX_WRAPPED_DEK_BYTES)
        return self


@dataclass(frozen=True)
class Expected:
    """Three content fields taken from an already authorized complete descriptor."""

    project_id: str
    digest: str
    byte_count: int


def wrapping_aad(header: Header) -> bytes:
    return canonical(
        {
            "purpose": "agent-rewind-artifact-dek",
            "format_version": 2,
            "project_id": header.project_id,
            "digest": header.digest,
            "byte_count": header.byte_count,
        }
    )


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise EnvelopeRefused()
        value[key] = item
    return value


def _header(body: bytes) -> Header:
    try:
        value = json.loads(body, object_pairs_hook=_unique)
        header = Header.model_validate(value)
        if canonical(header.model_dump()) != body:
            raise EnvelopeRefused()
    except (ValueError, UnicodeError, RecursionError):
        raise EnvelopeRefused() from None
    return header


def parse_frame(
    frame: bytes, expected: Expected, *, plaintext_limit: int
) -> tuple[Header, bytes, bytes]:
    """Reference byte parser only. Runtime must cap transport before allocation."""
    if (
        type(plaintext_limit) is not int
        or not 0 <= plaintext_limit <= MAX_PLAINTEXT_BYTES
        or type(expected.byte_count) is not int
        or not 0 <= expected.byte_count <= plaintext_limit
        or type(expected.project_id) is not str
        or type(expected.digest) is not str
        or not re.fullmatch(r"[0-9a-f]{32}", expected.project_id)
        or not re.fullmatch(r"[0-9a-f]{64}", expected.digest)
        or len(frame) < PREFIX_BYTES
        or len(frame) > PREFIX_BYTES + MAX_HEADER_BYTES + plaintext_limit + TAG_BYTES
        or not frame.startswith(MAGIC)
    ):
        raise EnvelopeRefused()
    size = int.from_bytes(frame[len(MAGIC) : PREFIX_BYTES], "big")
    if not 1 <= size <= MAX_HEADER_BYTES or len(frame) < PREFIX_BYTES + size:
        raise EnvelopeRefused()
    header = _header(frame[PREFIX_BYTES : PREFIX_BYTES + size])
    if (
        header.project_id != expected.project_id
        or header.digest != expected.digest
        or header.byte_count != expected.byte_count
        or len(frame) != PREFIX_BYTES + size + header.byte_count + TAG_BYTES
    ):
        raise EnvelopeRefused()
    return header, DATA_DOMAIN + frame[: PREFIX_BYTES + size], frame[PREFIX_BYTES + size :]


def open_frame(
    frame: bytes,
    expected: Expected,
    unwrap: Unwrap,
    *,
    plaintext_limit: int,
    allowed_key_versions: frozenset[str],
) -> bytes:
    """Offline only: tests inject a local mock; no credentials or network are discovered."""
    header, aad, ciphertext = parse_frame(frame, expected, plaintext_limit=plaintext_limit)
    if (
        not 1 <= len(allowed_key_versions) <= MAX_ALLOWED_KEY_VERSIONS
        or header.key_version not in allowed_key_versions
        or any(
            len(item) > MAX_KEY_VERSION_BYTES or not re.fullmatch(KEY_VERSION_PATTERN, item)
            for item in allowed_key_versions
        )
    ):
        raise EnvelopeRefused()
    try:
        key = unwrap(
            header.key_version,
            decode64(header.wrapped_dek, MAX_WRAPPED_DEK_BYTES),
            wrapping_aad(header),
        )
        if type(key) is not bytes or len(key) != 32:
            raise EnvelopeRefused()
        plaintext = AESGCM(key).decrypt(decode64(header.nonce, 12), ciphertext, aad)
    except Exception:
        # Unknown, denied, disabled, unavailable and invalid-tag cases share the fixed boundary.
        raise EnvelopeRefused() from None
    if (
        len(plaintext) != expected.byte_count
        or hashlib.sha256(plaintext).hexdigest() != expected.digest
    ):
        raise EnvelopeRefused()
    return plaintext


def schema() -> dict[str, object]:
    result = Header.model_json_schema()
    # JSON Schema regexes search; "$" may stop before a final line terminator.
    # Portable unanchored exclusion also works in ECMAScript, unlike Python-only
    # fullmatch/\Z or lookaround passed to Pydantic's Rust regex engine.
    for name, length in (("project_id", 32), ("digest", 64)):
        result["properties"][name].update(minLength=length, maxLength=length)
    alphabets = {
        "project_id": "0-9a-f",
        "digest": "0-9a-f",
        "nonce": "A-Za-z0-9_-",
        "key_version": "A-Za-z0-9_/-",
        "wrapped_dek": "A-Za-z0-9_-",
    }
    for name, alphabet in alphabets.items():
        result["properties"][name]["not"] = {"pattern": f"[^{alphabet}]"}
    result["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    result["$id"] = (
        "https://github.com/spei04/agent-rewind/contracts/encryption-envelope.v1.schema.json"
    )
    result["description"] = (
        "C07 canonical header for proposed format 2; framing, decoded byte bounds, "
        "scope, KMS allowlist and authenticated bytes are additional mandatory checks."
    )
    return result


def _read_fixture(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_FIXTURE_BYTES:
            raise EnvelopeRefused()
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            body = stream.read(MAX_FIXTURE_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(body) > MAX_FIXTURE_BYTES:
        raise EnvelopeRefused()
    return body


def _synthetic_unwrap(key_version: str, key: bytes) -> Unwrap:
    def unwrap(version: str, wrapped: bytes, aad: bytes) -> bytes:
        if version != key_version or len(wrapped) != 60:
            raise EnvelopeRefused()
        return AESGCM(key).decrypt(wrapped[:12], wrapped[12:], aad)

    return unwrap


def check_fixture(path: Path) -> int:
    value = json.loads(_read_fixture(path), object_pairs_hook=_unique)
    if (
        not isinstance(value, dict)
        or value.get("contract_id") != "C07"
        or value.get("synthetic") is not True
        or value.get("deployable") is not False
        or value.get("mock_wrapping") != "local-aesgcm-nonce-prefix-NOT-KMS-WIRE"
        or not isinstance(value.get("vectors"), list)
        or not 1 <= len(value["vectors"]) <= 8
    ):
        raise EnvelopeRefused()
    count = 0
    for vector in value["vectors"]:
        header = Header.model_validate(vector["header"])
        expected = Expected(header.project_id, header.digest, header.byte_count)
        frame = decode64(vector["frame"], 64 * 1024)
        plaintext = bytes.fromhex(vector["plaintext_hex"])
        key = bytes.fromhex(vector["public_test_kek_hex"])
        dek = bytes.fromhex(vector["public_test_dek_hex"])

        mock_unwrap = _synthetic_unwrap(header.key_version, key)

        parsed, aad, ciphertext = parse_frame(frame, expected, plaintext_limit=64 * 1024)
        if (
            parsed != header
            or wrapping_aad(header).hex() != vector["wrapping_aad_hex"]
            or hashlib.sha256(aad).hexdigest() != vector["data_aad_sha256"]
            or AESGCM(dek).encrypt(decode64(header.nonce, 12), plaintext, aad) != ciphertext
            or len(key) != 32
            or len(dek) != 32
            or open_frame(
                frame,
                expected,
                mock_unwrap,
                plaintext_limit=64 * 1024,
                allowed_key_versions=frozenset({header.key_version}),
            )
            != plaintext
        ):
            raise EnvelopeRefused()
        count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "fixture",
        type=Path,
        nargs="?",
        default=Path("contracts/fixtures/encryption.synthetic.json"),
    )
    args = parser.parse_args()
    try:
        count = check_fixture(args.fixture)
    except (OSError, ValueError, TypeError, KeyError, RecursionError, InvalidTag, ValidationError):
        print('{"valid":false,"deployable":false,"error":"invalid-encryption-fixture"}')
        return 2
    print(json.dumps({"valid": True, "deployable": False, "synthetic_vectors": count}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
