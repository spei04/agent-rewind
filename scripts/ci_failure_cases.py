"""Bind disposable PostgreSQL cases to the existing Actions core session.

These records describe one hosted test session. They neither grant a new
deadline nor replace the public terminal coverage receipt.
"""

import hashlib
import json
import math
import os
import stat
import time
import uuid
from pathlib import Path

from scripts.ci_receipts import (
    git_output,
    load_json,
    observe_identity,
    require,
    session_limit_seconds,
)

MAX_MANIFEST_BYTES = 128 * 1024
MAX_SOURCE_MAP_BYTES = 1024 * 1024
MAX_SOURCE_FILES = 4096
MAX_SOURCE_BYTES = 512 * 1024 * 1024
FIXED_DSN = "postgresql+psycopg://postgres:test-only@127.0.0.1:5432/rewind"


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _runner_path(value, environment):
    temporary = environment.get("RUNNER_TEMP")
    require(type(temporary) is str and bool(temporary), "Missing runner temporary directory")
    runner = Path(temporary)
    require(runner.is_absolute() and runner.resolve(strict=True) == runner, "Unsafe runner root")
    path = Path(value)
    require(path.is_absolute() and path != runner, "Absolute runner output required")
    require(path.is_relative_to(runner), "Output is outside runner temporary directory")
    require(path.resolve() == path, "Output contains a symlink or traversal")
    return path


def _private_directory(path, *, create=False):
    if create:
        path.mkdir(mode=0o700)
    observed = path.lstat()
    require(
        stat.S_ISDIR(observed.st_mode)
        and observed.st_uid == os.getuid()
        and stat.S_IMODE(observed.st_mode) == 0o700,
        "Directory is not private",
    )


def _write_new(path, data, limit):
    require(type(data) is bytes and len(data) <= limit, "Record exceeds byte bound")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _read_private(path, limit):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        observed = os.fstat(stream.fileno())
        require(
            stat.S_ISREG(observed.st_mode)
            and observed.st_uid == os.getuid()
            and stat.S_IMODE(observed.st_mode) == 0o600
            and observed.st_size <= limit,
            "Record is not private or exceeds bound",
        )
        data = stream.read(limit + 1)
    require(len(data) <= limit, "Record exceeds byte bound")
    return data


def _boot_id():
    value = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    require(str(uuid.UUID(value)) == value, "Invalid host boot identity")
    return value


def _controller():
    pid = os.getpid()
    raw = Path(f"/proc/{pid}/stat").read_text()
    fields = raw[raw.rindex(")") + 2 :].split()
    result = {
        "pid": pid,
        "start_ticks": int(fields[19]),
        "pgid": int(fields[2]),
        "sid": int(fields[3]),
    }
    require(all(type(value) is int and value > 0 for value in result.values()), "Invalid owner")
    return result


def write_service_receipt(environment, *, image):
    """Called only after the pinned service's effective setting was verified."""
    path = _runner_path(environment["REWIND_CI_POSTGRES_RECEIPT"], environment)
    require(environment.get("GITHUB_ACTIONS") == "true", "Actions service required")
    require(environment.get("GITHUB_JOB") == "core", "Core service required")
    _private_directory(path.parent, create=True)
    value = {
        "schema_version": 1,
        "boot_id": _boot_id(),
        "run_id": environment["GITHUB_RUN_ID"],
        "run_attempt": environment["GITHUB_RUN_ATTEMPT"],
        "verified_at_monotonic": time.monotonic(),
        "service": {
            "container_id": environment["REWIND_CI_POSTGRES_CONTAINER"],
            "image": image,
            "run_label": environment["GITHUB_RUN_ID"] + "-" + environment["GITHUB_RUN_ATTEMPT"],
            "ordinary_autovacuum_off_verified": True,
        },
    }
    _write_new(path, _encoded(value), 4096)


def _service(environment, origin, now):
    from scripts.ci_postgres import IMAGE

    path = _runner_path(environment["REWIND_CI_POSTGRES_RECEIPT"], environment)
    _private_directory(path.parent)
    value = load_json(_read_private(path, 4096), limit=4096)
    require(
        type(value) is dict
        and set(value) == {
            "schema_version", "boot_id", "run_id", "run_attempt",
            "verified_at_monotonic", "service",
        },
        "Malformed service receipt",
    )
    expected = {
        "container_id": environment["REWIND_TEST_POSTGRES_CONTAINER"],
        "image": IMAGE,
        "run_label": environment["GITHUB_RUN_ID"] + "-" + environment["GITHUB_RUN_ATTEMPT"],
        "ordinary_autovacuum_off_verified": True,
    }
    verified = value["verified_at_monotonic"]
    require(
        value["schema_version"] == 1
        and type(value["schema_version"]) is int
        and value["boot_id"] == _boot_id()
        and value["run_id"] == environment["GITHUB_RUN_ID"]
        and value["run_attempt"] == environment["GITHUB_RUN_ATTEMPT"]
        and value["service"] == expected
        and type(value["service"]["ordinary_autovacuum_off_verified"]) is bool
        and type(verified) in (int, float)
        and math.isfinite(verified)
        and 0 < verified <= origin <= now,
        "Service receipt does not match this core session",
    )
    require(
        environment.get("REWIND_TEST_POSTGRES") == FIXED_DSN
        and environment.get("REWIND_TEST_POSTGRES_URL") == FIXED_DSN,
        "Unexpected test service DSN",
    )
    return expected


def _source_map(root, deadline):
    """Hash every tracked file, preserving the exact serialized map as evidence."""
    names = git_output(root, "ls-files", "-z").split("\0")
    require(names[-1] == "", "Incomplete tracked source inventory")
    names.pop()
    require(0 < len(names) <= MAX_SOURCE_FILES and len(set(names)) == len(names), "Source count")
    rows = []
    total = 0
    for name in sorted(names):
        require(time.monotonic() < deadline, "Core session deadline reached")
        relative = Path(name)
        require(
            not relative.is_absolute() and ".." not in relative.parts
            and str(relative) == name and bool(name),
            "Unsafe tracked source path",
        )
        path = root / relative
        require(path.resolve(strict=True) == path, "Tracked source contains a symlink")
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode), "Tracked source is not a regular file")
            total += before.st_size
            require(total <= MAX_SOURCE_BYTES, "Tracked source bytes exceed bound")
            digest = hashlib.sha256()
            observed_bytes = 0
            while block := stream.read(1024 * 1024):
                require(time.monotonic() < deadline, "Core session deadline reached")
                observed_bytes += len(block)
                require(observed_bytes <= before.st_size, "Source changed while hashing")
                digest.update(block)
            after = os.fstat(stream.fileno())
        require(
            observed_bytes == before.st_size
            and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
            "Source changed while hashing",
        )
        rows.append({"path": name, "bytes": observed_bytes, "sha256": digest.hexdigest()})
    data = _encoded({"schema_version": 1, "files": rows})
    require(len(data) <= MAX_SOURCE_MAP_BYTES, "Source map exceeds bound")
    return data


def publish_actions_control(
    *, root, output, identity, python, leg, session_origin, session_limit, nodeids, environment
):
    """Publish once, after final selection; never infer permission from an old manifest."""
    root = Path(root).resolve(strict=True)
    output = _runner_path(output, environment)
    require(not output.is_relative_to(root), "Case records must be outside checkout")
    require(environment.get("GITHUB_ACTIONS") == "true", "Actions binding required")
    require(environment.get("GITHUB_JOB") == "core", "Core binding required")
    require(not environment.get("REWIND_F4_CASE_CONTROL"), "Case control already supplied")
    require(
        type(session_limit) is int and session_limit_seconds(python, leg) == session_limit,
        "Unknown core session limit",
    )
    now = time.monotonic()
    require(
        type(session_origin) in (int, float)
        and math.isfinite(session_origin) and 0 < session_origin <= now
        and now < session_origin + session_limit,
        "Core session deadline reached",
    )
    deadline = session_origin + session_limit
    require(observe_identity(root, environment) == identity, "Core source identity changed")
    require(
        type(nodeids) is list and len(set(nodeids)) == len(nodeids)
        and all(type(node) is str and 0 < len(node) <= 1024 for node in nodeids),
        "Invalid owned-case inventory",
    )
    service = _service(environment, session_origin, now)
    # An empty selected leg still gets an explicit, bounded source record. No
    # fixture may silently skip or use an implicit connection on that account.
    source_map = _source_map(root, deadline)
    fixture_rows = [
        row for row in json.loads(source_map)["files"]
        if row["path"] == "tests/failure_postgres_fixture.py"
    ]
    require(len(fixture_rows) == 1, "Owned fixture is missing from tracked source")
    fixture_hash = fixture_rows[0]["sha256"]
    cases = []
    for nodeid in nodeids:
        namespace = uuid.uuid4().hex
        cases.append({
            "nodeid": nodeid,
            "namespace": namespace,
            "record_path": str(output.parent / "cases" / namespace / "intent.json"),
        })
    manifest = {
        "schema_version": 1,
        "group_id": f"core-{python.replace('.', '')}-{leg}",
        "source_sha256": hashlib.sha256(source_map).hexdigest(),
        "source_commit": identity["checkout_commit"],
        "source_tree": identity["checkout_tree"],
        "fixture_sha256": fixture_hash,
        "boot_id": _boot_id(),
        "binding": {
            "kind": "actions_core",
            "controller": _controller(),
            "identity": identity,
            "job": "core",
            "python": python,
            "leg": leg,
            "session_origin_monotonic": session_origin,
            "session_limit_seconds": session_limit,
            "service": service,
            "case_count": len(cases),
            "cases_sha256": hashlib.sha256(_encoded(cases)).hexdigest(),
        },
        "body_deadline_monotonic": deadline,
        "cleanup_deadline_monotonic": deadline,
        "cases": cases,
    }
    encoded = _encoded(manifest)
    require(len(encoded) <= MAX_MANIFEST_BYTES, "Owned-case manifest exceeds byte bound")
    require(observe_identity(root, environment) == identity, "Source changed while binding")
    require(time.monotonic() < deadline, "Core session deadline reached")
    _private_directory(output.parent, create=True)
    _private_directory(output.parent / "cases", create=True)
    for case in cases:
        _private_directory(Path(case["record_path"]).parent, create=True)
    _write_new(output.parent / "source-map.json", source_map, MAX_SOURCE_MAP_BYTES)
    _write_new(output, encoded, MAX_MANIFEST_BYTES)
    require(time.monotonic() < deadline, "Core session deadline reached")
    return str(output)
