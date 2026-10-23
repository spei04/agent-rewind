"""Bounded resumable IPC for three explicit competing-operator invocations."""

import json
import os
import socket
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from time import monotonic
from uuid import uuid4

from ledger_process_fixture import FRAME_LIMIT, receive_frame, remaining, send_frame

WORK_SECONDS = 60
CLEANUP_SECONDS = 15
MAX_COMMANDS = 3
MAX_MESSAGES = 10
IDENTITY_KEYS = {"nonce", "pid", "case", "role", "intent_sha256"}


def validate_identity(message, identity):
    for key in IDENTITY_KEYS:
        assert type(message[key]) is type(identity[key]) and message[key] == identity[key]


def validate_control(message, identity, *, raw_id, engine_id, sequence, action):
    assert type(message) is dict
    assert set(message) == IDENTITY_KEYS | {"raw_id", "engine_id", "sequence", "action"}
    validate_identity(message, identity)
    assert type(message["raw_id"]) is int and message["raw_id"] == raw_id
    assert type(message["engine_id"]) is int and message["engine_id"] == engine_id
    assert type(message["sequence"]) is int and message["sequence"] == sequence
    assert message["action"] == action


class Conversation:
    """Each legal receive/send advances a single non-retryable conversation."""

    def __init__(self, identity):
        self.identity = identity
        self.state = "held" if identity["role"] == "winner" else "result"
        self.sequence = 1
        self.raw_id = self.engine_id = None

    def accept(self, message):
        assert self.state in {"held", "held_again", "result"}, "unexpected response"
        assert type(message) is dict
        assert set(message) == IDENTITY_KEYS | {
            "raw_id",
            "engine_id",
            "sequence",
            "phase",
            "witness",
        }
        validate_identity(message, self.identity)
        assert type(message["sequence"]) is int and message["sequence"] == self.sequence
        expected = "result" if self.state == "result" else "held"
        assert message["phase"] == expected and type(message["witness"]) is dict
        for key in ("raw_id", "engine_id"):
            assert type(message[key]) is int and message[key] > 0
            assert getattr(self, key) in {None, message[key]}
        self.raw_id, self.engine_id = message["raw_id"], message["engine_id"]
        self.state = {"held": "probe", "held_again": "continue", "result": "done"}[self.state]
        self.sequence += 1

    def control(self, action):
        assert self.state == action and action in {"probe", "continue"}, "unexpected control"
        result = {
            **self.identity,
            "raw_id": self.raw_id,
            "engine_id": self.engine_id,
            "sequence": self.sequence,
            "action": action,
        }
        self.state = "held_again" if action == "probe" else "result"
        self.sequence += 1
        return result


class CommandGroup:
    """One shared work deadline and a separate absolute cleanup reserve."""

    message_limit = MAX_MESSAGES
    conversation_type = Conversation

    def __init__(self, directory):
        self.directory = directory
        self.started = monotonic()
        self.work_deadline = self.started + WORK_SECONDS
        self.deadline = self.work_deadline + CLEANUP_SECONDS
        self.children = []
        self.messages = []
        self.closed = False
        self.cleanup = []

    def count(self, child, direction, payload_bytes):
        assert len(self.messages) < self.message_limit, "case message budget exhausted"
        assert 0 < payload_bytes <= FRAME_LIMIT
        self.messages.append(
            {
                "pid": child.process.pid,
                "direction": direction,
                "payload_bytes": payload_bytes,
                "framed_bytes": payload_bytes + 4,
                "completed": False,
            }
        )
        return self.messages[-1]

    def spawn(self, *, worker, case, role, intent_sha256, configuration):
        assert not self.closed and len(self.children) < MAX_COMMANDS
        assert role not in {child.role for child in self.children}
        remaining(self.work_deadline)
        return CommandProcess(
            self,
            worker=worker,
            case=case,
            role=role,
            intent_sha256=intent_sha256,
            configuration=configuration,
        )

    def close(self):
        if self.closed:
            return
        errors = []
        for child in reversed(self.children):
            try:
                child.close()
            except BaseException as error:
                errors.append(error)
                self.cleanup.append(
                    {"pid": getattr(child.process, "pid", None), "error": type(error).__name__}
                )
        self.closed = all(child.closed for child in self.children)
        self.record = {
            "work_seconds": WORK_SECONDS,
            "cleanup_seconds": CLEANUP_SECONDS,
            "work_deadline": self.work_deadline,
            "deadline": self.deadline,
            "elapsed_seconds": monotonic() - self.started,
            "work_exhausted_at_cleanup": monotonic() >= self.work_deadline,
            "messages": self.messages,
            "cleanup_errors": self.cleanup,
            "commands": [child.record for child in self.children],
        }
        (self.directory / "command-group.json").write_text(json.dumps(self.record, allow_nan=False))
        if errors:
            raise BaseExceptionGroup("competing command cleanup failed", errors)
        assert self.record["elapsed_seconds"] <= WORK_SECONDS + CLEANUP_SECONDS


class CommandProcess:
    def __init__(self, group, *, worker, case, role, intent_sha256, configuration):
        assert role in {"winner", "loser", "replay"}
        self.group, self.role = group, role
        self.process = self.channel = self.log = None
        self.closed = False
        self.record = {"role": role, "events": [], "received": []}
        self.directory = group.directory / role
        self.directory.mkdir(mode=0o700)
        group.children.append(self)
        parent, child = socket.socketpair()
        try:
            self.channel = parent
            self.log = (self.directory / "child.log").open("xb")
            environment = {
                key: value
                for key, value in os.environ.items()
                if not key.startswith(("PG", "REWIND_TEST_POSTGRES"))
                and key not in {"PYTHONPATH", "PYTEST_ADDOPTS", "PYTEST_PLUGINS"}
            }
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            self.process = subprocess.Popen(
                [sys.executable, "-B", str(Path(worker).resolve()), str(child.fileno())],
                pass_fds=(child.fileno(),),
                stdin=subprocess.DEVNULL,
                stdout=self.log,
                stderr=self.log,
                env=environment,
                start_new_session=True,
            )
            self.identity = {
                "nonce": uuid4().hex,
                "pid": self.process.pid,
                "case": case,
                "role": role,
                "intent_sha256": intent_sha256,
            }
            self.protocol = group.conversation_type(self.identity)
            self.record.update(pid=self.process.pid, identity=self.identity)
            self.record["events"].append("spawned")
            child.close()
            self.send(
                {
                    **self.identity,
                    "deadline": group.work_deadline,
                    "configuration": configuration,
                }
            )
        except BaseException:
            self.close()
            raise
        finally:
            child.close()

    def send(self, message):
        payload = json.dumps(message, allow_nan=False, separators=(",", ":")).encode()
        attempt = self.group.count(self, "parent-to-child", len(payload))
        send_frame(self.channel, message, self.group.work_deadline)
        attempt["completed"] = True

    def receive(self):
        sizes = []
        message = receive_frame(self.channel, self.group.work_deadline, sizes=sizes)
        attempt = self.group.count(self, "child-to-parent", sizes[0]["payload_bytes"])
        attempt["completed"] = True
        self.record["received"].append(message)
        self.protocol.accept(message)
        self.record["events"].append(message["phase"])
        if message["phase"] == "held":
            assert self.process.poll() is None, "winner did not remain held"
        else:
            code = self.process.wait(timeout=min(5, remaining(self.group.work_deadline)))
            self.record.update(returncode=code, reaped=True)
            self.record["events"].append("reaped")
            assert code == 0
            self.channel.settimeout(remaining(self.group.work_deadline))
            assert self.channel.recv(1) == b"", "unexpected message after final result"
            self.record["events"].append("pipe_eof")
        return message

    def probe(self):
        self.send(self.protocol.control("probe"))
        return self.receive()

    def resume(self):
        self.send(self.protocol.control("continue"))

    def close(self):
        if self.closed:
            return
        attempt = {
            "remaining_at_entry": self.group.deadline - monotonic(),
            "waits": [],
            "unreaped_at_wait_expiry": False,
        }
        try:
            if self.process is not None and self.process.poll() is None:
                if monotonic() < self.group.deadline:
                    self.process.terminate()
                    self.record["events"].append("cleanup_sigterm")
                    timeout = min(1, max(0, self.group.deadline - monotonic()))
                    attempt["waits"].append(timeout)
                    with suppress(subprocess.TimeoutExpired):
                        self.process.wait(timeout=timeout)
                if self.process.poll() is None:
                    # An exhausted budget must never skip signaling the owned
                    # child. With no time left, only a nonblocking reap is legal.
                    self.process.kill()
                    self.record["events"].append("cleanup_sigkill")
                    timeout = min(4, max(0, self.group.deadline - monotonic()))
                    attempt["waits"].append(timeout)
                    try:
                        self.process.wait(timeout=timeout)
                    except subprocess.TimeoutExpired as error:
                        attempt["unreaped_at_wait_expiry"] = True
                        raise TimeoutError("owned child unreaped at cleanup deadline") from error
        finally:
            code = self.process.poll() if self.process is not None else None
            reaped = self.process is None or code is not None
            self.record.update(returncode=code, reaped=reaped)
            self.closed = reaped
            attempt.update(returncode=code, reaped=reaped, closed=self.closed)
            self.record.setdefault("cleanup_attempts", []).append(attempt)
            if self.channel is not None:
                self.channel.close()
            if self.log is not None:
                self.log.close()
            self.record["elapsed_seconds"] = monotonic() - self.group.started
            (self.directory / "lifecycle.json").write_text(json.dumps(self.record, allow_nan=False))
