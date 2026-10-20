"""Bounded encrypted byte reads; callers own namespace authorization and deadlines."""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import BinaryIO

from cryptography.fernet import Fernet

MAX_PLAINTEXT = 4096
MAX_CIPHERTEXT = 5560


class BoundedReadError(ValueError):
    """Fixed failure category; never include a path, value or crypto exception."""


MAX_OBJECT_PLAINTEXT = 512 * 1024 * 1024


def ciphertext_limit(plaintext_limit: int) -> int:
    if type(plaintext_limit) is not int or not 0 <= plaintext_limit <= MAX_OBJECT_PLAINTEXT:
        raise BoundedReadError("plaintext_limit_invalid")
    raw = 57 + 16 * (plaintext_limit // 16 + 1)
    return 4 * ((raw + 2) // 3)


def read_ciphertext(stream: BinaryIO, *, limit: int = MAX_CIPHERTEXT) -> bytes:
    if type(limit) is not int or not 0 <= limit <= ciphertext_limit(MAX_OBJECT_PLAINTEXT):
        raise BoundedReadError("ciphertext_limit_invalid")
    # Short reads are not EOF. Read the first excess byte, never the whole object.
    content = bytearray()
    while len(content) <= limit:
        chunk = stream.read(min(65536, limit + 1 - len(content)))
        if not isinstance(chunk, bytes):
            raise BoundedReadError("invalid_byte_stream")
        if not chunk:
            return bytes(content)
        content.extend(chunk)
    raise BoundedReadError("ciphertext_limit")


@contextmanager
def regular_reader(
    path: Path | str, *, dir_fd: int | None = None, limit: int = MAX_CIPHERTEXT
) -> Iterator[BinaryIO]:
    if type(limit) is not int or not 0 <= limit <= ciphertext_limit(MAX_OBJECT_PLAINTEXT):
        raise BoundedReadError("ciphertext_limit_invalid")
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=dir_fd)
    try:
        information = os.fstat(descriptor)
        if not stat.S_ISREG(information.st_mode):
            raise BoundedReadError("regular_file_required")
        if information.st_size > limit:
            raise BoundedReadError("ciphertext_limit")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            yield stream
    finally:
        os.close(descriptor)


def decrypt_checked(
    ciphertext: bytes, cipher: Fernet, address: str, *, plaintext_limit: int = MAX_PLAINTEXT
) -> bytes:
    if len(ciphertext) > ciphertext_limit(plaintext_limit):
        raise BoundedReadError("ciphertext_limit")
    plaintext = cipher.decrypt(ciphertext)
    if len(plaintext) > plaintext_limit:
        raise BoundedReadError("plaintext_limit")
    if hashlib.sha256(plaintext).hexdigest() != address:
        raise BoundedReadError("address_mismatch")
    return plaintext


@contextmanager
def directory(root: Path, parts: tuple[str, ...] = (), *, create: bool = False) -> Iterator[int]:
    if create:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts:
            if create:
                with suppress(FileExistsError):
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)
