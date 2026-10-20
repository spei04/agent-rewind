"""Bounded encrypted byte reads; callers own namespace authorization and deadlines."""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

from cryptography.fernet import Fernet

MAX_PLAINTEXT = 4096
MAX_CIPHERTEXT = 5560


class BoundedReadError(ValueError):
    """Fixed failure category; never include a path, value or crypto exception."""


def read_ciphertext(stream: BinaryIO) -> bytes:
    # Short reads are not EOF. Read the first excess byte, never the whole object.
    content = bytearray()
    while len(content) <= MAX_CIPHERTEXT:
        chunk = stream.read(MAX_CIPHERTEXT + 1 - len(content))
        if not isinstance(chunk, bytes):
            raise BoundedReadError("invalid_byte_stream")
        if not chunk:
            return bytes(content)
        content.extend(chunk)
    raise BoundedReadError("ciphertext_limit")


@contextmanager
def regular_reader(path: Path | str, *, dir_fd: int | None = None) -> Iterator[BinaryIO]:
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=dir_fd)
    try:
        information = os.fstat(descriptor)
        if not stat.S_ISREG(information.st_mode):
            raise BoundedReadError("regular_file_required")
        if information.st_size > MAX_CIPHERTEXT:
            raise BoundedReadError("ciphertext_limit")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            yield stream
    finally:
        os.close(descriptor)


def decrypt_checked(ciphertext: bytes, cipher: Fernet, address: str) -> bytes:
    if len(ciphertext) > MAX_CIPHERTEXT:
        raise BoundedReadError("ciphertext_limit")
    plaintext = cipher.decrypt(ciphertext)
    if len(plaintext) > MAX_PLAINTEXT:
        raise BoundedReadError("plaintext_limit")
    if hashlib.sha256(plaintext).hexdigest() != address:
        raise BoundedReadError("address_mismatch")
    return plaintext
