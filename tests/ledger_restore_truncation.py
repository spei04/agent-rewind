"""A fixed archive defect and a strictly bound native failure witness."""

import hashlib
import json
import os
from pathlib import Path

from ledger_restore_tools import MAX_ARCHIVE, MAX_DIAGNOSTIC

TAIL_BYTES = 64
MIN_ARCHIVE = 4096
RESTORE_BINARY_SHA256 = "eb91db5f9ce7a1e4d8a72a9319544f5944ef00b6741c948b85e0a2ed532f9ad4"
EOF_DIAGNOSTIC = b"pg_restore: error: could not read from input file: end of file\n"


def bounded_bytes(path, limit):
    path = Path(path)
    assert path.is_file() and not path.is_symlink()
    assert path.stat().st_size <= limit
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    assert len(data) <= limit
    return data


def file_identity(path, limit):
    data = bounded_bytes(path, limit)
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def truncate_archive(source, destination):
    """Retain the intact archive and create exactly one exclusive prefix copy."""
    source, destination = Path(source), Path(destination)
    assert source.is_absolute() and destination.is_absolute() and source != destination
    original = bounded_bytes(source, MAX_ARCHIVE)
    assert len(original) >= MIN_ARCHIVE and original[:5] == b"PGDMP"
    truncated = original[:-TAIL_BYTES]
    with destination.open("xb") as handle:
        os.chmod(destination, 0o600)
        assert handle.write(truncated) == len(truncated)
    witness = {
        "source": str(source),
        "truncated": str(destination),
        "removed_bytes": TAIL_BYTES,
        "cut_offset": len(truncated),
        "source_identity": file_identity(source, MAX_ARCHIVE),
        "truncated_identity": file_identity(destination, MAX_ARCHIVE),
    }
    assert bounded_bytes(source, MAX_ARCHIVE) == original
    assert_archive_pair(witness)
    return witness


def assert_archive_pair(witness):
    source = bounded_bytes(witness["source"], MAX_ARCHIVE)
    truncated = bounded_bytes(witness["truncated"], MAX_ARCHIVE)
    assert len(source) >= MIN_ARCHIVE and source[:5] == b"PGDMP"
    assert type(witness["removed_bytes"]) is int and witness["removed_bytes"] == TAIL_BYTES
    assert type(witness["cut_offset"]) is int and witness["cut_offset"] == len(source) - TAIL_BYTES
    assert truncated == source[:-TAIL_BYTES]
    for key, data in (("source_identity", source), ("truncated_identity", truncated)):
        assert witness[key] == {
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }


def assert_native_truncation(error, directory, command, witness):
    """Only the original, fully reaped native EOF failure is the expected result."""
    assert type(error) is RuntimeError and error.args == ("restore tool failed",)
    assert type(error.args[0]) is str
    assert not getattr(error, "__notes__", ())
    directory = Path(directory)
    record = json.loads(bounded_bytes(directory / "truncated-restore.json", MAX_DIAGNOSTIC))
    assert type(record["argv"]) is list and all(type(arg) is str for arg in record["argv"])
    assert record["argv"] == command
    assert command[-3:] == [
        "--single-transaction",
        "--exit-on-error",
        witness["truncated"],
    ]
    assert Path(command[0]).name == "pg_restore"
    assert hashlib.sha256(Path(command[0]).read_bytes()).hexdigest() == RESTORE_BINARY_SHA256
    assert type(record["pid"]) is int and record["pid"] > 0
    assert type(record["returncode"]) is int and 0 < record["returncode"] <= 255
    assert record["reaped"] is True and record["signals"] == record["cleanup_errors"] == []
    assert record["first_error"] == "RuntimeError"
    assert type(record["timeout_seconds"]) is int and record["timeout_seconds"] == 30
    assert record["stream_limits"] == {"stdout": MAX_DIAGNOSTIC, "stderr": MAX_DIAGNOSTIC}
    expected_files = {}
    for stream in ("stdout", "stderr"):
        path = directory / ("truncated-restore." + stream)
        expected_files[path.name] = file_identity(path, MAX_DIAGNOSTIC)
    assert record["files"] == expected_files
    for item in record["files"].values():
        assert type(item["bytes"]) is int and type(item["sha256"]) is str
    assert bounded_bytes(directory / "truncated-restore.stdout", MAX_DIAGNOSTIC) == b""
    assert bounded_bytes(directory / "truncated-restore.stderr", MAX_DIAGNOSTIC) == EOF_DIAGNOSTIC
    assert_archive_pair(witness)
    return record
