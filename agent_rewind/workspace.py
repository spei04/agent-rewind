"""Portable workspace archives. Never extract untrusted archives onto the host."""

import io
import tarfile
from dataclasses import dataclass
from typing import Any, Literal

from .models import valid_path


@dataclass(frozen=True)
class File:
    data: bytes
    mode: int = 0o644
    kind: Literal["file", "directory"] = "file"
    mtime: int = 0


def pack(files: dict[str, File]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        for path, file in sorted(files.items()):
            valid_path(path)
            info = tarfile.TarInfo(path)
            info.type = tarfile.DIRTYPE if file.kind == "directory" else tarfile.REGTYPE
            info.mtime = file.mtime
            info.size = len(file.data)
            info.mode = file.mode & 0o777
            info.uid = info.gid = 1000
            archive.addfile(info, io.BytesIO(file.data))
    return output.getvalue()


def unpack(data: bytes, limit: int, docker_prefix: bool = False) -> dict[str, File]:
    if len(data) > limit + 16 * 1024 * 1024:
        raise ValueError("Workspace archive exceeds its size limit.")
    files: dict[str, File] = {}
    total = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
        for count, member in enumerate(archive):
            if count > 10000:
                raise ValueError("Workspace exceeds 10,000 entries.")
            path = member.name
            if docker_prefix:
                if path == "workspace" and member.isdir():
                    continue
                if not path.startswith("workspace/"):
                    raise ValueError("Unexpected archive root.")
                path = path[len("workspace/") :]
            valid_path(path.rstrip("/") if member.isdir() else path)
            if member.isdir():
                path = path.rstrip("/")
                if path in files:
                    raise ValueError("Duplicate archive path.")
                files[path] = File(b"", member.mode & 0o777, "directory", int(member.mtime))
                continue
            if not member.isfile() or member.issym() or member.islnk():
                raise ValueError("Symlinks, hard links, and special files cannot be checkpointed.")
            if path in files:
                raise ValueError("Duplicate archive path.")
            total += member.size
            if total > limit or member.size < 0:
                raise ValueError("Workspace exceeds its byte limit.")
            handle = archive.extractfile(member)
            if handle is None:
                raise ValueError("Missing archive entry.")
            files[path] = File(handle.read(), member.mode & 0o777, "file", int(member.mtime))
    return files


def summary(before: dict[str, File], after: dict[str, File]) -> list[dict[str, Any]]:
    return [
        {
            "path": path,
            "change": "added"
            if path not in before
            else "removed"
            if path not in after
            else "modified",
        }
        for path in sorted(before.keys() | after.keys())
        if before.get(path) != after.get(path)
    ]
