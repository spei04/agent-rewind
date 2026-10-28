"""Bounded, owner-recorded local tools for the synthetic restore rehearsal."""

import hashlib
import json
import os
import re
import selectors
import subprocess
import time
from pathlib import Path

MAX_ARCHIVE = 2 * 1024 * 1024
MAX_DIAGNOSTIC = 1024 * 1024


def tool_command(binary, tool, database, socket, port, *, archive=None):
    assert tool in {"pg_dump", "pg_restore"}
    assert re.fullmatch(r"ar_(migration|restore)_[0-9a-f]{32}", database)
    assert Path(binary).name == tool and Path(binary).is_absolute()
    assert Path(socket).is_absolute() and port == 55432
    command = [
        str(binary),
        "--host=" + str(socket),
        "--port=" + str(port),
        "--username=postgres",
        "--dbname=" + database,
    ]
    if tool == "pg_dump":
        assert archive is None
        command.append("--format=custom")
    else:
        assert archive is not None and Path(archive).is_absolute()
        command.extend(["--single-transaction", "--exit-on-error", str(archive)])
    return command


def tool_environment(socket, application):
    assert re.fullmatch(r"ar_restore_[0-9a-f]{32}_(dump|restore|version)", application)
    result = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
    result.update(
        PGHOST=str(socket),
        PGPORT="55432",
        PGUSER="postgres",
        PGDATABASE="postgres",
        PGCONNECT_TIMEOUT="3",
        PGAPPNAME=application,
        PGOPTIONS="-c statement_timeout=20000 -c lock_timeout=1000",
    )
    return result


def stop_owned(process, record, *, deadline, clock=None):
    """Always signal an owned live process, even when waiting time has expired."""
    clock = time.monotonic if clock is None else clock
    errors = []
    for name in ("terminate", "kill"):
        if process.poll() is not None:
            break
        try:
            getattr(process, name)()
            record["signals"].append(name)
        except ProcessLookupError:
            pass
        except BaseException as error:
            errors.append(type(error).__name__)
        remaining = max(0.0, min(5.0, deadline - clock()))
        if remaining:
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                pass
            except BaseException as error:
                errors.append(type(error).__name__)
    record["reaped"] = process.poll() is not None
    record["cleanup_errors"] = errors
    if not record["reaped"] or errors:
        raise RuntimeError("owned restore tool cleanup was not fully acknowledged")


def run_tool(command, directory, *, label, env, timeout=30, archive=False):
    """Drain bounded streams; retain failed attempts and preserve first exceptions."""
    assert re.fullmatch(r"[a-z][a-z0-9-]*", label) and 0 < timeout <= 30
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    output, diagnostic = directory / (label + ".stdout"), directory / (label + ".stderr")
    record_path = directory / (label + ".json")
    assert not any(path.exists() for path in (output, diagnostic, record_path))
    process = None
    first = None
    started = time.monotonic()
    record = {
        "argv": list(command),
        "pid": None,
        "process_group": os.getpgrp(),
        "group_policy": "inherits the containing pytest child group",
        "signals": [],
        "cleanup_errors": [],
        "reaped": False,
        "timeout_seconds": timeout,
        "stream_limits": {
            "stdout": MAX_ARCHIVE if archive else MAX_DIAGNOSTIC,
            "stderr": MAX_DIAGNOSTIC,
        },
    }
    streams = {}
    try:
        with output.open("xb") as stdout, diagnostic.open("xb") as stderr:
            os.chmod(output, 0o600)
            os.chmod(diagnostic, 0o600)
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                start_new_session=False,
            )
            record["pid"] = process.pid
            streams = {"stdout": process.stdout, "stderr": process.stderr}
            with selectors.DefaultSelector() as selector:
                for name, stream in streams.items():
                    selector.register(stream, selectors.EVENT_READ, name)
                counts = dict.fromkeys(streams, 0)
                while selector.get_map():
                    remaining = started + timeout - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("restore tool deadline exceeded")
                    for key, _ in selector.select(timeout=min(0.1, remaining)):
                        name = key.data
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        limit = record["stream_limits"][name]
                        available = limit - counts[name]
                        (stdout if name == "stdout" else stderr).write(chunk[:available])
                        counts[name] += min(len(chunk), available)
                        if len(chunk) > available:
                            raise ValueError("restore tool " + name + " bound exceeded")
                remaining = started + timeout - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("restore tool deadline exceeded before reap")
                process.wait(timeout=remaining)
                record["reaped"] = True
                if process.returncode != 0:
                    raise RuntimeError("restore tool failed")
        if archive:
            with output.open("rb") as handle:
                if handle.read(5) != b"PGDMP":
                    raise ValueError("custom archive header missing")
    except BaseException as error:
        first = error
    finally:
        if process is not None:
            try:
                stop_owned(process, record, deadline=time.monotonic() + 10)
            except BaseException as error:
                if first is None:
                    first = error
            finally:
                for stream in streams.values():
                    if stream is not None:
                        try:
                            stream.close()
                        except BaseException as error:
                            record["cleanup_errors"].append(type(error).__name__)
                            if first is None:
                                first = error
            record["returncode"] = process.returncode
        record["elapsed_seconds"] = time.monotonic() - started
        record["first_error"] = None if first is None else type(first).__name__
        record["files"] = {
            path.name: {
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in (output, diagnostic)
            if path.exists()
        }
        try:
            with record_path.open("x") as handle:
                os.chmod(record_path, 0o600)
                json.dump(record, handle, indent=2, sort_keys=True)
        except BaseException as error:
            if first is None:
                first = error
            else:
                first.add_note("restore tool evidence write failed")
    if first is not None:
        raise first
    return output
