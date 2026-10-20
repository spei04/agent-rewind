"""Bounded format-1 local storage; no SQL authorization or graph publication."""

from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from cryptography.fernet import Fernet, InvalidToken

from .artifact_metadata import (
    ArtifactDescriptor,
    ArtifactError,
    ArtifactObject,
    object_locator,
)
from .bounded_bytes import (
    BoundedReadError,
    ciphertext_limit,
    decrypt_checked,
    directory,
    read_ciphertext,
    regular_reader,
)


@dataclass(frozen=True)
class ObjectWriteResult:
    """Logical and actual adapter work; later publication persists these counters."""

    object: ArtifactObject
    logical_writes: int
    write_requests: int
    read_requests: int
    plaintext_bytes: int
    ciphertext_bytes: int
    cache_hit: bool


class ArtifactStorage(Protocol):
    def put_verified(self, value: ArtifactObject, data: bytes) -> ObjectWriteResult: ...
    def read_verified(self, value: ArtifactDescriptor) -> bytes: ...


class LocalArtifactStorage:
    def __init__(self, root: Path, cipher: Fernet, *, plaintext_limit: int):
        # Required application bound, capped at the existing 512 MiB workspace maximum.
        self.ciphertext_limit = ciphertext_limit(plaintext_limit)
        self.plaintext_limit = plaintext_limit
        self.root = root
        self.cipher = cipher

    def _validate(self, value: ArtifactObject) -> tuple[str, ...]:
        value.__post_init__()
        if value.byte_count > self.plaintext_limit:
            raise ArtifactError("artifact_limit")
        return tuple(value.locator.split("/"))

    def _read(self, value: ArtifactObject, parent: int, filename: str) -> tuple[bytes, int]:
        # Metadata-sized envelope is tighter than the configured maximum. One
        # excess byte is detected even when a backend's declared size is wrong.
        limit = ciphertext_limit(value.byte_count)
        with regular_reader(filename, dir_fd=parent, limit=limit) as stream:
            ciphertext = read_ciphertext(stream, limit=limit)
        data = decrypt_checked(
            ciphertext, self.cipher, value.digest, plaintext_limit=value.byte_count
        )
        if len(data) != value.byte_count:
            raise ArtifactError("artifact_integrity")
        return data, len(ciphertext)

    def read_verified(self, value: ArtifactDescriptor) -> bytes:
        """Only an already authorized, freshly resolved scoped descriptor is valid."""
        # Copy the structural descriptor once, then validate that immutable snapshot.
        # This checks storage identity; caller authorization is still mandatory.
        version = value.format_version
        if type(version) is not int or version != 1:
            raise ArtifactError("artifact_format_unsupported")
        snapshot = ArtifactObject(
            id=value.id,
            project_id=value.project_id,
            digest=value.digest,
            locator=value.locator,
            format_version=1,
            byte_count=value.byte_count,
            created_at=value.created_at,
        )
        parts = self._validate(snapshot)
        try:
            with directory(self.root, parts[:-1]) as parent:
                return self._read(snapshot, parent, parts[-1])[0]
        except FileNotFoundError:
            raise ArtifactError("artifact_missing") from None
        except (OSError, BoundedReadError, InvalidToken):
            raise ArtifactError("artifact_integrity") from None

    def put_verified(self, value: ArtifactObject, data: bytes) -> ObjectWriteResult:
        parts = self._validate(value)
        if value.locator != object_locator(value.project_id, value.digest):
            raise ArtifactError("legacy_artifact_write_forbidden")
        if (
            not isinstance(data, bytes)
            or len(data) != value.byte_count
            or hashlib.sha256(data).hexdigest() != value.digest
        ):
            raise ArtifactError("artifact_integrity")
        try:
            with directory(self.root, parts[:-1], create=True) as parent:
                try:
                    _, length = self._read(value, parent, parts[-1])
                except FileNotFoundError:
                    pass
                else:
                    return ObjectWriteResult(value, 1, 0, 1, len(data), length, True)
                ciphertext = self.cipher.encrypt(data)
                if len(ciphertext) > self.ciphertext_limit:
                    raise ArtifactError("artifact_limit")
                temporary = ".object-" + secrets.token_hex(16)
                descriptor = os.open(
                    temporary,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=parent,
                )
                won = False
                try:
                    with os.fdopen(descriptor, "wb") as stream:
                        stream.write(ciphertext)
                        stream.flush()
                        os.fsync(stream.fileno())
                    try:
                        os.link(
                            temporary,
                            parts[-1],
                            src_dir_fd=parent,
                            dst_dir_fd=parent,
                            follow_symlinks=False,
                        )
                        won = True
                    except FileExistsError:
                        pass  # Verify the winner; never overwrite it, including corruption.
                    os.fsync(parent)
                    _, length = self._read(value, parent, parts[-1])
                finally:
                    os.unlink(temporary, dir_fd=parent)
                # Includes the absent lookup and verified read. A raced temporary
                # write is still actual work even when another complete inode won.
                return ObjectWriteResult(value, 1, 1, 2, len(data), length, not won)
        except FileNotFoundError:
            raise ArtifactError("artifact_missing") from None
        except (OSError, BoundedReadError, InvalidToken):
            raise ArtifactError("artifact_integrity") from None
