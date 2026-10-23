"""Offline controls for the actual fixed-defect and native-failure classifiers."""

import hashlib
import json
from copy import deepcopy

import ledger_restore_truncation as truncation
import pytest
from ledger_restore_tools import run_tool, tool_command
from test_ledger_restore_controls import fake_tools


def pair(tmp_path, size=8192):
    source = tmp_path / "intact.archive"
    source.write_bytes(
        b"PGDMP" + bytes(range(251)) * ((size - 5) // 251) + b"x" * ((size - 5) % 251)
    )
    return source, tmp_path / "truncated.archive"


def test_fixed_prefix_retains_intact_bytes_hashes_and_private_exclusive_output(tmp_path):
    source, destination = pair(tmp_path)
    original = source.read_bytes()
    witness = truncation.truncate_archive(source, destination)
    assert source.read_bytes() == original and destination.read_bytes() == original[:-64]
    assert witness["removed_bytes"] == 64 and witness["cut_offset"] == len(original) - 64
    assert witness["source_identity"]["sha256"] == hashlib.sha256(original).hexdigest()
    assert witness["truncated_identity"]["sha256"] == hashlib.sha256(original[:-64]).hexdigest()
    assert destination.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        truncation.truncate_archive(source, destination)
    assert source.read_bytes() == original and destination.read_bytes() == original[:-64]


@pytest.mark.parametrize("size", [4096, 2 * 1024 * 1024])
def test_fixed_prefix_accepts_both_actual_size_boundaries(tmp_path, size):
    source, destination = pair(tmp_path, size)
    witness = truncation.truncate_archive(source, destination)
    assert witness["source_identity"]["bytes"] == size
    assert witness["truncated_identity"]["bytes"] == size - 64


@pytest.mark.parametrize("change", ["short", "large", "header", "same-path", "symlink"])
def test_invalid_intact_archive_never_creates_truncated_output(tmp_path, change):
    source, destination = pair(tmp_path, 4095 if change == "short" else 8192)
    if change == "large":
        source.write_bytes(b"PGDMP" + b"x" * (2 * 1024 * 1024))
    elif change == "header":
        source.write_bytes(b"wrong" + source.read_bytes()[5:])
    elif change == "same-path":
        destination = source
    elif change == "symlink":
        link = tmp_path / "input-link"
        link.symlink_to(source)
        source = link
    retained = source.read_bytes()
    with pytest.raises(AssertionError):
        truncation.truncate_archive(source, destination)
    assert source.read_bytes() == retained
    if destination != source:
        assert not destination.exists()


@pytest.mark.parametrize(
    "change", ["source", "truncated", "cut", "removed", "source-hash", "prefix-hash"]
)
def test_post_restore_archive_mutations_fail_without_repair(tmp_path, change):
    source, destination = pair(tmp_path)
    witness = truncation.truncate_archive(source, destination)
    if change in {"source", "truncated"}:
        path = source if change == "source" else destination
        path.write_bytes(path.read_bytes()[:-1] + b"!")
    elif change in {"cut", "removed"}:
        witness["cut_offset" if change == "cut" else "removed_bytes"] += 1
    else:
        witness["source_identity" if change == "source-hash" else "truncated_identity"][
            "sha256"
        ] = "0" * 64
    with pytest.raises(AssertionError):
        truncation.assert_archive_pair(witness)


def failed_tool(monkeypatch, tmp_path, *, code=1, stderr=truncation.EOF_DIAGNOSTIC):
    binary = tmp_path / "pg_restore"
    binary.write_bytes(b"offline tool identity; never executed")
    monkeypatch.setattr(
        truncation, "RESTORE_BINARY_SHA256", hashlib.sha256(binary.read_bytes()).hexdigest()
    )
    source, destination = pair(tmp_path)
    witness = truncation.truncate_archive(source, destination)
    command = tool_command(
        binary, "pg_restore", "ar_restore_" + "a" * 32, tmp_path, 55432, archive=destination
    )
    process, calls = fake_tools(monkeypatch, {100: [b""], 101: [stderr, b""]}, code=code)
    with pytest.raises(RuntimeError) as caught:
        run_tool(command, tmp_path, label="truncated-restore", env={})
    assert len(calls) == 1 and process.stdout.closed and process.stderr.closed
    return caught.value, command, witness


def test_actual_runner_native_failure_is_classified_without_replacing_exception(
    monkeypatch, tmp_path
):
    error, command, witness = failed_tool(monkeypatch, tmp_path)
    record = truncation.assert_native_truncation(error, tmp_path, command, witness)
    assert record["returncode"] == 1 and record["reaped"] is True
    assert error.args == ("restore tool failed",)


@pytest.mark.parametrize(
    "change",
    [
        "success",
        "signal",
        "boolean-code",
        "missing-code",
        "unreaped",
        "cleanup",
        "signals",
        "timeout",
        "overflow",
        "argv",
        "file-hash",
        "file-size",
        "extra-file",
        "timeout-bound",
        "stream-bound",
        "pid",
        "binary",
        "archive",
    ],
)
def test_native_failure_requires_complete_exact_tool_and_archive_evidence(
    monkeypatch, tmp_path, change
):
    error, command, witness = failed_tool(monkeypatch, tmp_path)
    path = tmp_path / "truncated-restore.json"
    record = json.loads(path.read_text())
    if change in {"success", "signal", "boolean-code", "missing-code"}:
        record["returncode"] = {
            "success": 0,
            "signal": -9,
            "boolean-code": True,
            "missing-code": None,
        }[change]
    elif change == "unreaped":
        record["reaped"] = False
    elif change == "cleanup":
        record["cleanup_errors"] = ["RuntimeError"]
    elif change == "signals":
        record["signals"] = ["terminate"]
    elif change in {"timeout", "overflow"}:
        record["first_error"] = "TimeoutError" if change == "timeout" else "ValueError"
    elif change == "argv":
        record["argv"].insert(-1, "--no-owner")
    elif change in {"file-hash", "file-size"}:
        record["files"]["truncated-restore.stderr"][
            "sha256" if change == "file-hash" else "bytes"
        ] = "0" * 64 if change == "file-hash" else 0
    elif change == "extra-file":
        record["files"]["unbound"] = deepcopy(record["files"]["truncated-restore.stderr"])
    elif change == "timeout-bound":
        record["timeout_seconds"] = 300
    elif change == "stream-bound":
        record["stream_limits"]["stderr"] += 1
    elif change == "pid":
        record["pid"] = True
    elif change == "binary":
        (tmp_path / "pg_restore").write_bytes(b"different")
    else:
        assert change == "archive"
        (tmp_path / "truncated.archive").write_bytes(b"different")
    path.write_text(json.dumps(record))
    with pytest.raises(AssertionError):
        truncation.assert_native_truncation(error, tmp_path, command, witness)


class OtherFailure(RuntimeError):
    pass


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("unrelated"),
        RuntimeError("restore tool failed", "extra"),
        OtherFailure("restore tool failed"),
        TimeoutError("restore tool failed"),
        ValueError("restore tool failed"),
        KeyboardInterrupt("restore tool failed"),
    ],
)
def test_unrelated_exception_never_becomes_expected_native_failure(monkeypatch, tmp_path, error):
    _, command, witness = failed_tool(monkeypatch, tmp_path)
    with pytest.raises(AssertionError):
        truncation.assert_native_truncation(error, tmp_path, command, witness)


@pytest.mark.parametrize(
    "diagnostic",
    [
        b"connection refused\n",
        b"permission denied\n",
        b"pg_restore: error: input file is too short (read 0, expected 5)\n",
        b"could not read from input file: end of file\n",
        b"prefix " + truncation.EOF_DIAGNOSTIC,
        truncation.EOF_DIAGNOSTIC + b"another error\n",
        truncation.EOF_DIAGNOSTIC * 2,
        b"",
    ],
)
def test_complete_native_stderr_must_match_prebound_form(monkeypatch, tmp_path, diagnostic):
    error, command, witness = failed_tool(monkeypatch, tmp_path, stderr=diagnostic)
    with pytest.raises(AssertionError):
        truncation.assert_native_truncation(error, tmp_path, command, witness)
