"""Private append-only publication evidence; never a substitute for SQL commit proof."""

from __future__ import annotations

import fcntl
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifact_graph import decode
from .artifact_metadata import ArtifactError, identifier
from .bounded_bytes import BoundedReadError, directory, read_ciphertext, regular_reader
from .models import canonical

MAX_INTENT_BYTES = 8 * 1024 * 1024
MAX_RECORD_BYTES = 16384
MAX_JOURNAL_BYTES = 32 * 1024 * 1024
MAX_RECORDS = 100000


@dataclass(frozen=True)
class JournalLimits:
    """Optional tighter consumer bounds, checked before file reads/retention."""

    intent_bytes: int
    records: int
    total_bytes: int

    def __post_init__(self) -> None:
        for value, minimum, maximum in (
            (self.intent_bytes, 1, MAX_INTENT_BYTES),
            (self.records, 0, MAX_RECORDS),
            (self.total_bytes, 1, MAX_JOURNAL_BYTES),
        ):
            if type(value) is not int or not minimum <= value <= maximum:
                raise ArtifactError("publication_journal_limit")


def _limits(limits: JournalLimits | None) -> JournalLimits:
    if limits is None:
        return JournalLimits(MAX_INTENT_BYTES, MAX_RECORDS, MAX_JOURNAL_BYTES)
    if type(limits) is not JournalLimits:
        raise ArtifactError("publication_journal_limit")
    limits.__post_init__()
    return limits


def _private(fd: int, *, folder: bool) -> None:
    info = os.fstat(fd)
    if (
        info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != (0o700 if folder else 0o600)
        or (not folder and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1))
    ):
        raise ArtifactError("publication_journal_unsafe")


class JournalSession:
    def __init__(self, fd: int, *, limits: JournalLimits | None = None):
        self.limits = _limits(limits)
        self.fd = fd
        names: list[str] = []
        with os.scandir(fd) as entries:
            for entry in entries:
                if len(names) >= self.limits.records + 2:
                    raise ArtifactError("publication_journal_limit")
                names.append(entry.name)
        if len(names) > self.limits.records + 2 or any(
            name not in {"lock", "intent.json"}
            and (len(name) != 16 or not name[:11].isdigit() or not name.endswith(".json"))
            for name in names
        ):
            raise ArtifactError("publication_journal_invalid")
        sequence = sorted(name for name in names if name not in {"lock", "intent.json"})
        if sequence != [f"{index:011d}.json" for index in range(len(sequence))]:
            raise ArtifactError("publication_journal_invalid")
        self.total = 0
        self.records: list[dict[str, Any]] = []
        self.intent: dict[str, Any] | None = None
        if "intent.json" in names:
            self.intent = self._read("intent.json", self.limits.intent_bytes)
        elif sequence:
            raise ArtifactError("publication_journal_invalid")
        for index, name in enumerate(sequence):
            record = self._read(name, MAX_RECORD_BYTES)
            if (
                type(record.get("sequence")) is not int
                or record.get("sequence") != index
                or set(record) != {"sequence", "kind", "data"}
            ):
                raise ArtifactError("publication_journal_invalid")
            if (
                not isinstance(record["kind"], str)
                or record["kind"]
                not in {
                    "upload_started",
                    "upload_verified",
                    "upload_unknown",
                    "commit_pending",
                    "commit_confirmed",
                    "commit_unknown",
                }
                or not isinstance(record["data"], dict)
            ):
                raise ArtifactError("publication_journal_invalid")
            self.records.append(record)

    def _read(self, name: str, limit: int) -> dict[str, Any]:
        limit = min(limit, self.limits.total_bytes - self.total)
        with regular_reader(name, dir_fd=self.fd, limit=limit) as stream:
            _private(stream.fileno(), folder=False)
            data = read_ciphertext(stream, limit=limit)
            # A prior complete write may have failed before its file fsync.
            # Recovery validates and durably flushes retained evidence first.
            os.fsync(stream.fileno())
        self.total += len(data)
        if self.total > self.limits.total_bytes:
            raise ArtifactError("publication_journal_limit")
        return decode(data)

    def _write(self, name: str, value: dict[str, Any], limit: int) -> None:
        data = canonical(value)
        if len(data) > limit or self.total + len(data) > self.limits.total_bytes:
            raise ArtifactError("publication_journal_limit")
        # A failed/partial file remains as evidence. It is never rewritten or
        # silently removed; subsequent sessions reject its truncated contents.
        fd = os.open(
            name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd
        )
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(self.fd)
        except BaseException:
            raise
        self.total += len(data)

    def freeze(self, intent: dict[str, Any]) -> None:
        if self.intent is not None:
            if canonical(self.intent) != canonical(intent):
                raise ArtifactError("publication_intent_conflict")
            return
        self._write("intent.json", intent, self.limits.intent_bytes)
        self.intent = intent

    def append(self, kind: str, data: dict[str, Any]) -> None:
        if kind not in {
            "upload_started",
            "upload_verified",
            "upload_unknown",
            "commit_pending",
            "commit_confirmed",
            "commit_unknown",
        }:
            raise ArtifactError("publication_journal_invalid")
        if self.intent is None or len(self.records) >= self.limits.records:
            raise ArtifactError("publication_journal_limit")
        record = {"sequence": len(self.records), "kind": kind, "data": data}
        self._write(f"{len(self.records):011d}.json", record, MAX_RECORD_BYTES)
        self.records.append(record)


class PublicationJournal:
    """One nonblocking process lock per intent, local filesystem only.

    The supplied directory must be private and outside the artifact object tree.
    An upload start without a verified receipt means backend work is UNKNOWN.
    Journal file I/O is separate from artifact backend counters.
    """

    def __init__(self, root: Path):
        self.root = root

    @contextmanager
    def open(
        self, publication_id: str, *, limits: JournalLimits | None = None
    ) -> Iterator[JournalSession]:
        identifier(publication_id)
        limits = _limits(limits)
        try:
            with directory(self.root, create=False, create_root=False) as root_fd:
                _private(root_fd, folder=True)
                with directory(self.root, (publication_id,), create=True) as fd:
                    _private(fd, folder=True)
                    lock = os.open(
                        "lock",
                        os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                        0o600,
                        dir_fd=fd,
                    )
                    try:
                        _private(lock, folder=False)
                        try:
                            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        except BlockingIOError:
                            raise ArtifactError("publication_in_progress") from None
                        os.fsync(fd)
                        session = JournalSession(fd, limits=limits)
                        os.fsync(fd)
                        yield session
                    finally:
                        os.close(lock)
        except (OSError, BoundedReadError):
            raise ArtifactError("publication_journal_unavailable") from None
