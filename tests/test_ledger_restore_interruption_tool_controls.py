"""Offline stream scheduling and failure receipts for the concrete data runner."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import ledger_restore_interruption_tool as runner
import pytest
from ledger_restore_interruption_contracts import COPY, PROFILE
from ledger_restore_interruption_oracles import assert_cancelled_restore
from test_ledger_restore_controls import Stream
from test_ledger_restore_interruption_wire_controls import control


def setup(monkeypatch, tmp_path, *, fault=None):
    value = control(monkeypatch)
    value.prepared, value.phase = True, "prepared"
    value.control = SimpleNamespace(interest=1, fd=102, query=None, deadline=105)
    chunks = {
        100: [
            b"",
        ],
        101: [b"diagnostic", b""],
    }
    history, now = [], [100.0]
    injected = KeyboardInterrupt("first I/O interruption")

    class Process:
        pid, returncode = 333, None
        stdout, stderr = Stream(100), Stream(101)

        def poll(self):
            if fault == "poll":
                raise injected
            return self.returncode

        def terminate(self):
            history.append("terminate")
            self.returncode = -15

        def kill(self):
            history.append("kill")
            self.returncode = -9

        def wait(self, timeout):
            assert 0 <= timeout <= 5
            return self.returncode

    process = Process()
    value.owner.popen = lambda *a, **kw: process

    def clock():
        now[0] += 0.01 if fault != "deadline" else 0.2
        return now[0]

    def tick(mask=0):
        history.append("control")
        if fault == "tick":
            raise injected
        if not value.cancel_attempted:
            value.cancel_attempted = True
        elif fault != "deadline":
            value.cancel_ack = value.restore_absent = True
            value.deadline = value.work_deadline
            process.returncode = 1

    def finish():
        history.append("finish")
        assert value.cancel_ack and value.restore_absent
        assert process.poll() == 1 and not chunks[100] and not chunks[101]
        if fault == "finish":
            raise injected
        value.completed, value.phase = True, "complete"

    class Selector:
        def __init__(self):
            self.values = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def register(self, fileobj, events, data=None):
            key = SimpleNamespace(fileobj=fileobj, data=data)
            self.values[fileobj] = key
            return key

        def unregister(self, fileobj):
            return self.values.pop(fileobj)

        def get_map(self):
            return self.values

        def select(self, timeout):
            assert 0 <= timeout <= 0.02
            # Both pipes are continuously ready; the control operation still runs.
            return [(key, 1) for key in self.values.values()]

    def read(fd, count):
        assert count == 65536
        history.append(fd)
        if fault == "read":
            raise injected
        if fault == "overflow" and fd == 101:
            return b"x" * 65536
        if fault in {"missing-eof", "deadline"} and fd == 101:
            return b"x"
        return chunks[fd].pop(0)

    monkeypatch.setattr(runner.time, "monotonic", clock)
    monkeypatch.setattr(value, "tick", tick)
    monkeypatch.setattr(value, "finish", finish)
    monkeypatch.setattr(runner.selectors, "DefaultSelector", Selector)
    monkeypatch.setattr(runner.os, "read", read)
    monkeypatch.setattr(runner.os, "set_blocking", lambda *a: None)
    command = runner.split_command(
        Path("/pinned/pg_restore"), value.database, value.socket, tmp_path / "archive", "data"
    )
    environment = runner.data_environment(value.socket, value.token)
    return value, process, history, injected, command, environment


def test_concrete_loop_drains_both_pipes_without_starving_control(monkeypatch, tmp_path):
    value, process, history, _, command, env = setup(monkeypatch, tmp_path)
    with pytest.raises(RuntimeError) as caught:
        runner.run_interrupted_data_restore(command, tmp_path, env=env, control=value)
    assert value.owner.first_error is caught.value and value.completed and value.owner.resolved()
    assert history.index(100) < history.index("finish")
    assert history.index(101) < history.index("finish") and history.count("control") >= 2
    assert process.stdout.closed and process.stderr.closed
    record = json.loads((tmp_path / "data-restore.json").read_text())
    assert record["reaped"] and record["signals"] == record["cleanup_errors"] == []
    assert record["returncode"] == 1 and record["cleanup_deadline"] < 140.1
    assert (tmp_path / "data-restore.stderr").read_bytes() == b"diagnostic"


@pytest.mark.parametrize(
    "fault",
    [
        "tick",
        "read",
        "poll",
        "finish",
        "overflow",
        "missing-eof",
        "deadline",
    ],
)
def test_abnormal_loop_retains_first_failure_and_unresolved_fence(monkeypatch, tmp_path, fault):
    value, _, _, injected, command, env = setup(monkeypatch, tmp_path, fault=fault)
    with pytest.raises(BaseException) as caught:
        runner.run_interrupted_data_restore(command, tmp_path, env=env, control=value)
    if fault in {"tick", "read", "poll"}:
        assert caught.value is injected
    elif fault == "finish":
        # Native failure is first; later closure uncertainty cannot replace it.
        assert type(caught.value) is RuntimeError and str(caught.value) == "restore tool failed"
    elif fault == "overflow":
        assert isinstance(caught.value, AssertionError)
        assert (tmp_path / "data-restore.stderr").stat().st_size == runner.MAX_DIAGNOSTIC
    else:
        assert isinstance(caught.value, TimeoutError)
    assert not value.owner.resolved() and value.uncertain
    assert value.owner.first_error is caught.value
    record = json.loads((tmp_path / "data-restore.json").read_text())
    assert record["control"]["uncertain"]
    assert record["cleanup_deadline"] <= 141


def test_receipt_failure_preserves_original_and_completed_ownership(monkeypatch, tmp_path):
    value, _, _, _, command, env = setup(monkeypatch, tmp_path)
    original_open = Path.open

    def fail_receipt(path, *args, **kwargs):
        if path.name == "data-restore.json":
            raise OSError("receipt failed")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_receipt)
    with pytest.raises(RuntimeError) as caught:
        runner.run_interrupted_data_restore(command, tmp_path, env=env, control=value)
    assert value.owner.first_error is caught.value and value.completed
    assert "data restore evidence write failed" in caught.value.__notes__
    assert not (tmp_path / "data-restore.json").exists()


def make_failure(tmp_path):
    stdout = tmp_path / "data-restore.stdout"
    stderr = tmp_path / "data-restore.stderr"
    stdout.write_bytes(b"")
    stderr.write_bytes(
        b"pg_restore: error: could not execute query: ERROR:  "
        b"canceling statement due to user request\nCommand was: " + COPY + b"\n"
    )
    control = SimpleNamespace(
        completed=True,
        uncertain=False,
        cancel_attempted=True,
        cancel_ack=True,
        restore_absent=True,
        report=lambda: {"complete": True},
        owner=SimpleNamespace(
            report=lambda: {
                "resolved": True,
                "profile": list(PROFILE),
                "steps": [{"label": item} for item in PROFILE],
                "children": [{"returncode": item} for item in (0, 0, 0, 0, 1)],
            }
        ),
    )
    record = {
        "argv": ["exact"],
        "returncode": 1,
        "first_error": "RuntimeError",
        "signals": [],
        "cleanup_errors": [],
        "reaped": True,
        "control": control.report(),
        "files": {
            path.name: {
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in (stdout, stderr)
        },
    }
    return control, record


@pytest.mark.parametrize(
    "change",
    [
        None,
        "signal",
        "cleanup",
        "timeout",
        "exit",
        "unreaped",
        "wrong-command",
        "no-ack",
        "lock-timeout",
        "extra-stderr",
        "partial-stderr",
        "wrong-copy",
        "hash",
    ],
)
def test_native_failure_oracle_is_not_an_error_substring_gate(tmp_path, change):
    value, record = make_failure(tmp_path)
    error = RuntimeError("restore tool failed")
    if change == "signal":
        record["signals"] = ["terminate"]
    elif change == "cleanup":
        record["cleanup_errors"] = ["TimeoutError"]
    elif change == "timeout":
        error = TimeoutError("restore tool failed")
    elif change == "exit":
        record["returncode"] = -15
    elif change == "unreaped":
        record["reaped"] = False
    elif change == "wrong-command":
        record["argv"] = ["different"]
    elif change == "no-ack":
        value.cancel_ack = False
    elif change == "hash":
        record["files"]["data-restore.stderr"]["sha256"] = "0" * 64
    elif change in {"lock-timeout", "extra-stderr", "partial-stderr", "wrong-copy"}:
        path = tmp_path / "data-restore.stderr"
        text = path.read_bytes()
        if change == "lock-timeout":
            text = text.replace(b"due to user request", b"due to lock timeout")
        elif change == "extra-stderr":
            text += b"pg_restore: connection failed\n"
        elif change == "partial-stderr":
            text = text[:-1]
        else:
            text = text.replace(b"public.api_keys", b"public.jobs")
        path.write_bytes(text)
        record["files"][path.name] = {
            "bytes": len(text),
            "sha256": hashlib.sha256(text).hexdigest(),
        }
    (tmp_path / "data-restore.json").write_text(json.dumps(record))
    if change is None:
        assert assert_cancelled_restore(error, tmp_path, ["exact"], value, "owner") == record
    else:
        with pytest.raises(AssertionError):
            assert_cancelled_restore(error, tmp_path, ["exact"], value, "owner")


def test_data_timeout_override_does_not_change_default_tool_profile(monkeypatch):
    for key in tuple(runner.os.environ):
        if key.startswith("PG"):
            monkeypatch.delenv(key)
    token = "a" * 32
    original = runner.tool_environment("/fixed", "ar_restore_" + token + "_restore")
    changed = runner.data_environment("/fixed", token)
    assert original["PGOPTIONS"] == "-c statement_timeout=20000 -c lock_timeout=1000"
    assert changed["PGOPTIONS"] == "-c statement_timeout=20000 -c lock_timeout=15000"
    assert {
        key: item for key, item in changed.items() if key not in {"PGOPTIONS", "LC_ALL", "LANG"}
    } == {key: item for key, item in original.items() if key not in {"PGOPTIONS", "LC_ALL", "LANG"}}
