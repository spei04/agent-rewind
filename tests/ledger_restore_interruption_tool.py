"""One fixed data-only restore loop, with bounded streams and owned control sockets."""

import hashlib
import json
import os
import selectors
import subprocess
import time
from pathlib import Path

from ledger_restore_interruption_control import InterruptionControl
from ledger_restore_interruption_pq import check
from ledger_restore_tools import MAX_DIAGNOSTIC, stop_owned, tool_command, tool_environment


def data_environment(socket, token):
    environment = tool_environment(socket, "ar_restore_" + token + "_restore")
    environment.update(
        PGOPTIONS="-c statement_timeout=20000 -c lock_timeout=15000", LC_ALL="C", LANG="C"
    )
    return environment


def split_command(binary, database, socket, archive, stage):
    assert stage in {"schema", "data"}
    command = tool_command(binary, "pg_restore", database, socket, 55432, archive=archive)
    command.insert(-1, "--" + stage + "-only")
    return command


def run_interrupted_data_restore(command, directory, *, env, control):
    assert type(control) is InterruptionControl and control.prepared
    assert command == split_command(
        Path(command[0]), control.database, control.socket, Path(command[-1]), "data"
    )
    assert env == data_environment(control.socket, control.token)
    directory = Path(directory)
    paths = {name: directory / ("data-restore." + name) for name in ("stdout", "stderr", "json")}
    assert not any(path.exists() for path in paths.values())
    started = time.monotonic()
    cleanup_deadline = min(started + 40, control.parent_deadline)
    work_deadline = min(started + 30, control.parent_deadline)
    child, first = None, None
    streams, handles = {}, {}
    record = {
        "argv": list(command),
        "pid": None,
        "signals": [],
        "cleanup_errors": [],
        "reaped": False,
        "timeout_seconds": 30,
        "cleanup_deadline": cleanup_deadline,
        "environment": {
            key: value
            for key, value in env.items()
            if key.startswith("PG") or key in {"LC_ALL", "LANG"}
        },
        "stream_limits": {"stdout": MAX_DIAGNOSTIC, "stderr": MAX_DIAGNOSTIC},
    }
    try:
        for name in ("stdout", "stderr"):
            handles[name] = paths[name].open("xb")
            os.chmod(paths[name], 0o600)
        child = control.owner.spawn_data(
            command,
            env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=False,
        )
        record["pid"] = child.pid
        control.attach(child, started)
        streams = {"stdout": child.stdout, "stderr": child.stderr}
        counts = dict.fromkeys(streams, 0)
        for stream in streams.values():
            os.set_blocking(stream.fileno(), False)
        with selectors.DefaultSelector() as selector:
            for name, stream in streams.items():
                selector.register(stream, selectors.EVENT_READ, name)
            while True:
                check(work_deadline)
                control.tick()
                code = child.poll()
                if (
                    not any(key.data in streams for key in selector.get_map().values())
                    and code is not None
                    and control.restore_absent
                    and control.cancel_ack
                ):
                    break
                # One fixed channel is active during the tool interval.
                for key in list(selector.get_map().values()):
                    if key.data == "control":
                        selector.unregister(key.fileobj)
                channel = control.control
                if channel.interest:
                    selector.register(channel.fd, channel.interest, "control")
                deadline = min(
                    work_deadline,
                    control.deadline,
                    channel.deadline if channel.query else work_deadline,
                )
                check(deadline)
                ready = selector.select(min(0.02, deadline - time.monotonic()))
                # Each readiness class gets at most one bounded operation per turn.
                for key, mask in ready:
                    if key.data == "control":
                        control.tick(mask)
                    else:
                        name = key.data
                        try:
                            chunk = os.read(key.fileobj.fileno(), 65536)
                        except BlockingIOError:
                            continue
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        available = MAX_DIAGNOSTIC - counts[name]
                        handles[name].write(chunk[:available])
                        counts[name] += min(len(chunk), available)
                        assert len(chunk) <= available, "data restore diagnostic bound exceeded"
                    check(min(work_deadline, control.deadline))
        record["reaped"] = child.poll() is not None
        assert record["reaped"] and child.returncode != 0, "cancelled restore must fail natively"
        first = RuntimeError("restore tool failed")
        control.owner.remember(first)
        control.finish()
    except BaseException as error:
        first = first or error
        record["control_error"] = type(error).__name__
        control.remember(first)
    finally:
        if child is not None:
            try:
                stop_owned(child, record, deadline=cleanup_deadline)
            except BaseException as error:
                first = first or error
                control.remember(error)
        if not control.completed or record["cleanup_errors"] or not record["reaped"]:
            control.abort()
        for handle in (*streams.values(), *handles.values()):
            try:
                handle.close()
            except BaseException as error:
                record["cleanup_errors"].append(type(error).__name__)
                first = first or error
                control.remember(error)
        record.update(
            returncode=None if child is None else child.returncode,
            elapsed_seconds=time.monotonic() - started,
            first_error=None if first is None else type(first).__name__,
            control=control.report(),
        )
        record["files"] = {
            path.name: {
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for name, path in paths.items()
            if name != "json" and path.exists()
        }
        try:
            with paths["json"].open("x") as handle:
                os.chmod(paths["json"], 0o600)
                json.dump(record, handle, indent=2, sort_keys=True, allow_nan=False)
        except BaseException as error:
            first = first or error
            first.add_note("data restore evidence write failed")
        if first is not None:
            control.owner.remember(first)
    if first is not None:
        raise first
    raise AssertionError("data restore returned without the required native failure")
