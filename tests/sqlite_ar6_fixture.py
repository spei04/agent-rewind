"""Opt-in fresh ar6 copies for downstream SQLite behavior tests only."""

from __future__ import annotations

import hashlib
import os
import stat
from copy import deepcopy
from dataclasses import fields
from pathlib import Path

from ledger_reader_fixture import ReaderFixture, capture_ar6, complete_ar6
from sqlalchemy import create_engine

from agent_rewind.artifact_metadata import configure_artifact_engine
from agent_rewind.migrations.schema import ADMISSION

_INVALID = "fresh_ar6_template_invalid"
_SIDECARS = ("-wal", "-shm", "-journal")


def _checked_path(path: Path) -> None:
    if not isinstance(path, Path) or not path.is_absolute() or ".." in path.parts:
        raise ValueError(_INVALID)
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError(_INVALID)


def _identity(path: Path) -> tuple[int, int, int, int, int]:
    _checked_path(path)
    try:
        value = path.lstat()
    except OSError:
        raise ValueError(_INVALID) from None
    if not stat.S_ISREG(value.st_mode) or value.st_uid != os.getuid() or value.st_nlink != 1:
        raise ValueError(_INVALID)
    return value.st_dev, value.st_ino, value.st_uid, stat.S_IMODE(value.st_mode), value.st_size


def _digest(path: Path) -> str:
    before = _identity(path)
    result = hashlib.sha256()
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != before[:2]:
            raise ValueError(_INVALID)
        remaining = before[-1]
        while remaining:
            chunk = stream.read(min(remaining, 1024 * 1024))
            if not chunk:
                raise ValueError(_INVALID)
            result.update(chunk)
            remaining -= len(chunk)
        if stream.read(1):
            raise ValueError(_INVALID)
    if _identity(path) != before:
        raise ValueError(_INVALID)
    return result.hexdigest()


def _observations(case: ReaderFixture) -> dict:
    if (
        case.legacy is not False
        or case.revision != ADMISSION
        or case.manifest is not None
        or case.cursor is not None
        or case.opening is not None
        or case.expected["status"] != "absent"
    ):
        raise ValueError(_INVALID)
    return deepcopy(
        {
            field.name: getattr(case, field.name)
            for field in fields(case)
            if field.name not in {"path", "engine"}
        }
    )


def _remove_owned(path: Path, identity: tuple[int, int]) -> None:
    if not os.path.lexists(path):
        return
    if _identity(path)[:2] != identity:
        raise ValueError(_INVALID)
    path.unlink()


class FreshSqliteAr6Template:
    """Own one sealed file and read-only descriptor, never a live SQL handle."""

    def __init__(self, root: Path):
        _checked_path(root)
        try:
            info = root.stat()
        except OSError:
            raise ValueError(_INVALID) from None
        if (
            not root.is_dir()
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700
            or any(root.iterdir())
        ):
            raise ValueError(_INVALID)
        self.root = root
        self.source = root / "fresh.sqlite"
        self._root_identity = info.st_dev, info.st_ino
        self._owned_source = None
        self._source_descriptor = None
        self._sealed_identity = None
        self._sealed_digest = None
        self._baseline = None
        self._failed = False
        self._closed = False

    def _check_root(self) -> None:
        _checked_path(self.root)
        try:
            info = self.root.stat()
        except OSError:
            raise ValueError(_INVALID) from None
        if (info.st_dev, info.st_ino) != self._root_identity:
            raise ValueError(_INVALID)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError(_INVALID)

    def _check_source(self) -> None:
        self._check_root()
        if set(self.root.iterdir()) != {self.source}:
            raise ValueError(_INVALID)
        if _identity(self.source) != self._sealed_identity:
            raise ValueError(_INVALID)
        if _digest(self.source) != self._sealed_digest:
            raise ValueError(_INVALID)

    def _build(self) -> None:
        self._check_root()
        if any(self.root.iterdir()):
            raise ValueError(_INVALID)
        descriptor = os.open(
            self.source, os.O_RDONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        self._source_descriptor = descriptor
        try:
            owned = os.fstat(descriptor)
            self._owned_source = owned.st_dev, owned.st_ino
            case = None
            try:
                case = complete_ar6(self.source, legacy=False)
                self._baseline = _observations(case)
            except BaseException as error:
                if case is not None:
                    try:
                        case.dispose()
                    except BaseException:
                        error.add_note("Fresh ar6 source disposal also failed.")
                raise
            else:
                case.dispose()
            if (
                set(self.root.iterdir()) != {self.source}
                or _identity(self.source)[:2] != self._owned_source
            ):
                raise ValueError(_INVALID)
        except BaseException as error:
            try:
                self._discard_source()
            except BaseException:
                error.add_note("Fresh ar6 source cleanup also failed.")
            raise
        self.source.chmod(0o400)
        identity = _identity(self.source)
        if identity[:2] != self._owned_source:
            raise ValueError(_INVALID)
        digest = _digest(self.source)
        self._sealed_identity = identity
        self._sealed_digest = digest

    def _discard_source(self) -> None:
        primary = None
        try:
            self._check_root()
            if self._owned_source is not None:
                # Stored identity alone cannot authorize deletion after pin retirement.
                if self._source_descriptor is None:
                    if os.path.lexists(self.source):
                        raise ValueError(_INVALID)
                else:
                    _remove_owned(self.source, self._owned_source)
        except BaseException as error:
            primary = error
            raise
        finally:
            descriptor = self._source_descriptor
            # Retire deletion authority before a close with uncertain failure state.
            self._source_descriptor = None
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except BaseException:
                    if primary is None:
                        raise
                    primary.add_note("Fresh ar6 source descriptor close also failed.")

    def copy_to(self, path: Path) -> ReaderFixture:
        if self._closed:
            raise RuntimeError("fresh_ar6_template_closed")
        if self._failed:
            raise RuntimeError("fresh_ar6_template_failed")
        _checked_path(path)
        if path == self.root or self.root in path.parents or not path.parent.is_dir():
            raise ValueError(_INVALID)
        if self._owned_source is not None and os.path.lexists(path):
            info = path.lstat()
            if (info.st_dev, info.st_ino) == self._owned_source:
                raise ValueError(_INVALID)
        # Refusal before acquisition leaves both a new and a ready template usable.
        if any(
            os.path.lexists(item)
            for item in (path, *(Path(str(path) + suffix) for suffix in _SIDECARS))
        ):
            raise FileExistsError(path)
        try:
            if self._sealed_identity is None:
                self._build()
            self._check_source()
        except BaseException:
            # A sealed source remains available for inspection until close.
            self._failed = True
            raise
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        owned = os.fstat(descriptor)
        target_identity = owned.st_dev, owned.st_ino
        engine = None
        close_attempted = False
        try:
            with (
                os.fdopen(descriptor, "wb", closefd=False) as target,
                os.fdopen(os.open(self.source, os.O_RDONLY | os.O_NOFOLLOW), "rb") as source,
            ):
                opened = os.fstat(source.fileno())
                if (opened.st_dev, opened.st_ino) != self._owned_source:
                    raise ValueError(_INVALID)
                remaining = self._sealed_identity[-1]
                while remaining:
                    chunk = source.read(min(remaining, 1024 * 1024))
                    if not chunk:
                        raise ValueError(_INVALID)
                    target.write(chunk)
                    remaining -= len(chunk)
                if source.read(1):
                    raise ValueError(_INVALID)
            if _identity(path)[:2] == self._owned_source or _digest(path) != self._sealed_digest:
                raise ValueError(_INVALID)
            self._check_source()
            if _identity(path)[:2] != target_identity:
                raise ValueError(_INVALID)
            engine = create_engine(f"sqlite:///{path}")
            configure_artifact_engine(engine)
            case = capture_ar6(path, engine, legacy=False)
            if _observations(case) != self._baseline:
                raise ValueError(_INVALID)
            self._check_source()
            close_attempted = True
            os.close(descriptor)
            return case
        except BaseException as error:
            self._failed = True
            if engine is not None:
                try:
                    engine.dispose()
                except BaseException:
                    error.add_note("Fresh ar6 copy disposal also failed.")
            try:
                _remove_owned(path, target_identity)
            except BaseException:
                error.add_note("Fresh ar6 copy cleanup also failed.")
            if not close_attempted:
                try:
                    os.close(descriptor)
                except BaseException:
                    error.add_note("Fresh ar6 copy descriptor close also failed.")
            raise

    def close(self) -> None:
        if self._closed:
            return
        primary = None
        try:
            if self._sealed_identity is not None and not self._failed:
                self._check_source()
        except BaseException as error:
            primary = error
            raise
        finally:
            self._closed = True
            try:
                self._discard_source()
            except BaseException:
                if primary is None:
                    raise
                primary.add_note("Fresh ar6 source cleanup also failed.")
