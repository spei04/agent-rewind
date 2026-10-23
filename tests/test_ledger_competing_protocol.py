"""Negative protocol controls and real cleanup after an exhausted test work window."""

import json
import signal
from time import monotonic
from types import SimpleNamespace

import pytest
from ledger_competing_process import (
    CLEANUP_SECONDS,
    MAX_MESSAGES,
    CommandGroup,
    Conversation,
    validate_control,
)

IDENTITY = {
    "nonce": "bound-nonce",
    "pid": 123,
    "case": "initialize",
    "role": "winner",
    "intent_sha256": "a" * 64,
}


def response(sequence=1, phase="held"):
    return {
        **IDENTITY,
        "raw_id": 456,
        "engine_id": 789,
        "sequence": sequence,
        "phase": phase,
        "witness": {},
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("nonce", "wrong"),
        ("pid", True),
        ("case", "provision"),
        ("role", "loser"),
        ("intent_sha256", "b" * 64),
        ("sequence", True),
        ("sequence", 3),
        ("phase", "result"),
        ("raw_id", False),
        ("engine_id", 0),
        ("witness", []),
    ],
)
def test_competing_response_rejects_wrong_binding(field, value):
    conversation = Conversation(IDENTITY)
    message = response()
    message[field] = value
    with pytest.raises(AssertionError):
        conversation.accept(message)
    assert conversation.state == "held"


def test_competing_protocol_rejects_duplicate_or_early_messages():
    conversation = Conversation(IDENTITY)
    with pytest.raises(AssertionError, match="unexpected control"):
        conversation.control("continue")
    conversation.accept(response())
    with pytest.raises(AssertionError, match="unexpected response"):
        conversation.accept(response())
    with pytest.raises(AssertionError, match="unexpected control"):
        conversation.control("continue")
    probe = conversation.control("probe")
    validate_control(probe, IDENTITY, raw_id=456, engine_id=789, sequence=2, action="probe")
    with pytest.raises(AssertionError):
        conversation.accept(response())
    conversation.accept(response(3))
    resume = conversation.control("continue")
    validate_control(resume, IDENTITY, raw_id=456, engine_id=789, sequence=4, action="continue")
    with pytest.raises(AssertionError):
        validate_control(probe, IDENTITY, raw_id=456, engine_id=789, sequence=4, action="continue")
    conversation.accept(response(5, "result"))
    with pytest.raises(AssertionError, match="unexpected response"):
        conversation.accept(response(5, "result"))


@pytest.mark.parametrize(
    "field,value",
    [
        ("nonce", "wrong"),
        ("pid", 321),
        ("raw_id", 999),
        ("engine_id", 999),
        ("intent_sha256", "b" * 64),
        ("sequence", 4),
        ("action", "continue"),
    ],
)
def test_competing_child_rejects_wrong_continuation(field, value):
    conversation = Conversation(IDENTITY)
    conversation.accept(response())
    message = conversation.control("probe")
    message[field] = value
    with pytest.raises(AssertionError):
        validate_control(message, IDENTITY, raw_id=456, engine_id=789, sequence=2, action="probe")


def test_competing_message_budget_counts_both_directions(tmp_path):
    group = CommandGroup(tmp_path)
    child = SimpleNamespace(process=SimpleNamespace(pid=123))
    for index in range(MAX_MESSAGES):
        group.count(child, "parent-to-child" if index % 2 else "child-to-parent", 1)
    with pytest.raises(AssertionError, match="message budget exhausted"):
        group.count(child, "parent-to-child", 1)
    assert len(group.messages) == MAX_MESSAGES
    group.close()


def test_competing_exhausted_work_still_kills_and_reaps_owned_child(tmp_path):
    worker = synthetic_peer(tmp_path)
    group = CommandGroup(tmp_path)
    try:
        child = group.spawn(
            worker=worker,
            case="initialize",
            role="winner",
            intent_sha256="a" * 64,
            configuration={},
        )
        child.receive()
        # Deliberately exhaust only the test harness work window. The cleanup
        # reserve uses its own deadline and no production clock is changed.
        group.work_deadline = monotonic() - 0.001
        group.deadline = min(group.deadline, monotonic() + CLEANUP_SECONDS)
        with pytest.raises(TimeoutError):
            child.probe()
    finally:
        group.close()
    assert child.process.returncode == -signal.SIGKILL
    assert child.record["reaped"]
    assert child.record["events"][-2:] == ["cleanup_sigterm", "cleanup_sigkill"]
    assert group.record["work_exhausted_at_cleanup"]
    assert group.record["cleanup_errors"] == []
    saved = json.loads((tmp_path / "command-group.json").read_text())
    assert saved["commands"][0]["returncode"] == -signal.SIGKILL


def synthetic_peer(tmp_path):
    # This synthetic peer exercises only IPC/cleanup. It never opens a database.
    worker = tmp_path / "synthetic_peer.py"
    worker.write_text(
        "import json,os,signal,socket,struct,sys\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "with socket.socket(fileno=int(sys.argv[1])) as channel:\n"
        " def read(n):\n"
        "  value=b''\n"
        "  while len(value)<n:\n"
        "   part=channel.recv(n-len(value))\n"
        "   if not part: raise EOFError('unexpected EOF')\n"
        "   value+=part\n"
        "  return value\n"
        " request=json.loads(read(struct.unpack('!I',read(4))[0]))\n"
        " value={k:request[k] for k in ('nonce','pid','case','role','intent_sha256')}\n"
        " value.update(raw_id=1,engine_id=2,sequence=1,phase='held',witness={})\n"
        " payload=json.dumps(value).encode()\n"
        " channel.sendall(struct.pack('!I',len(payload))+payload)\n"
        " read(1)\n"
        " raise AssertionError('unexpected continuation')\n"
    )
    return worker


def test_competing_expired_cleanup_signals_without_resetting_deadline(tmp_path, record_property):
    group = CommandGroup(tmp_path)
    child = None
    first = None
    try:
        child = group.spawn(
            worker=synthetic_peer(tmp_path),
            case="initialize",
            role="winner",
            intent_sha256="a" * 64,
            configuration={},
        )
        child.receive()
        # This is an injected harness-deadline failure, not a production clock.
        group.work_deadline = monotonic() - 2
        group.deadline = monotonic() - 1
        expired = group.deadline
        try:
            group.close()
        except BaseExceptionGroup as error:
            assert all(isinstance(item, TimeoutError) for item in error.exceptions)
        first = json.loads((tmp_path / "command-group.json").read_text())
        record_property("helper_expired_cleanup", json.dumps(first))
        assert group.deadline == expired
        command = first["commands"][0]
        assert command["events"][-1] == "cleanup_sigkill"
        attempt = command["cleanup_attempts"][-1]
        assert attempt["remaining_at_entry"] < 0 and attempt["waits"] == [0]
        assert attempt["closed"] is attempt["reaped"]
        if not attempt["reaped"]:
            assert command["returncode"] is None and not child.closed
            assert attempt["unreaped_at_wait_expiry"]
        # Preserve the helper's immediate result before a separately bounded
        # control-harness wait. This wait is never claimed as an in-budget reap.
        code = child.process.wait(timeout=3)
        harness = {
            "scope": "post-helper control-harness reap",
            "returncode": code,
            "helper_reported_reaped": attempt["reaped"],
            "unchanged_deadline": group.deadline == expired,
        }
        (tmp_path / "post-helper-reap.json").write_text(json.dumps(harness))
        record_property("post_helper_reap", json.dumps(harness))
        assert code == -signal.SIGKILL and group.deadline == expired
        # A second close can observe/reap an already-exited process without
        # granting a new wait budget. The first failed attempt remains retained.
        group.close()
        assert child.closed and child.record["reaped"]
        assert group.deadline == expired
    finally:
        if child is not None and child.process.poll() is None:
            child.process.kill()
            child.process.wait(timeout=3)
        if first is not None:
            (tmp_path / "first-expired-cleanup.json").write_text(json.dumps(first))
        group.close()
