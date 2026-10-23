"""Bounded private IPC and child ownership for actual process-death tests."""

import json
import os
import signal
import socket
import struct
import subprocess
import sys
from pathlib import Path
from time import monotonic
from uuid import uuid4

FRAME_LIMIT = 4 * 1024 * 1024
LIFECYCLE_SECONDS = 45
CLEANUP_SECONDS = 10


def remaining(deadline):
    value = deadline - monotonic()
    if value <= 0:
        raise TimeoutError("process barrier deadline exceeded")
    return value


def send_frame(channel, value, deadline):
    payload = json.dumps(value, allow_nan=False, separators=(",", ":")).encode()
    if len(payload) > FRAME_LIMIT:
        raise ValueError("process barrier frame too large")
    channel.settimeout(remaining(deadline))
    channel.sendall(struct.pack("!I", len(payload)) + payload)


def receive_frame(channel, deadline, *, sizes=None):
    def read(size):
        data = bytearray()
        while len(data) < size:
            channel.settimeout(remaining(deadline))
            part = channel.recv(size - len(data))
            if not part:
                raise EOFError("process barrier closed before complete frame")
            data.extend(part)
        return bytes(data)

    size = struct.unpack("!I", read(4))[0]
    if not 0 < size <= FRAME_LIMIT:
        raise ValueError("invalid process barrier frame length")
    payload = read(size)
    if sizes is not None:
        sizes.append({"payload_bytes": len(payload), "framed_bytes": len(payload) + 4})
    return json.loads(payload)


def validate_marker(marker, *, nonce, pid, case, phase):
    assert type(marker) is dict
    assert set(marker) == {"nonce", "pid", "case", "phase", "sequence", "raw_id", "witness"}
    assert marker["nonce"] == nonce and marker["case"] == case and marker["phase"] == phase
    assert type(marker["pid"]) is int and marker["pid"] == pid
    assert type(marker["sequence"]) is int and marker["sequence"] == 1
    assert type(marker["raw_id"]) is int and marker["raw_id"] > 0
    assert type(marker["witness"]) is dict


class HeldProcess:
    """One fresh process, one witnessed gate, and unconditional bounded reaping."""

    def __init__(self, directory, *, worker, case, phase, configuration):
        self.started_at = monotonic()
        self.deadline = self.started_at + LIFECYCLE_SECONDS
        self.work_deadline = self.deadline - CLEANUP_SECONDS
        self.nonce, self.case, self.phase = uuid4().hex, case, phase
        self.record = {"case": case, "phase": phase, "nonce": self.nonce, "events": []}
        self.record_path = directory / "child-lifecycle.json"
        self.process = None
        self.channel = None
        self.log = None
        self.received = False
        parent, child = socket.socketpair()
        try:
            self.channel = parent
            self.log = (directory / "child.log").open("xb")
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
            self.record["pid"] = self.process.pid
            self.record["events"].append("spawned")
            child.close()
            send_frame(
                parent,
                {
                    "nonce": self.nonce,
                    "case": case,
                    "phase": phase,
                    "deadline": self.work_deadline,
                    "configuration": configuration,
                },
                self.work_deadline,
            )
        except BaseException:
            self.close()
            raise
        finally:
            child.close()

    def barrier(self):
        assert not self.received, "duplicate barrier receive"
        marker = receive_frame(
            self.channel, self.work_deadline, sizes=self.record.setdefault("frames", [])
        )
        self.record["marker"] = marker  # Preserve a wrong marker before validation.
        validate_marker(
            marker, nonce=self.nonce, pid=self.process.pid, case=self.case, phase=self.phase
        )
        assert self.process.poll() is None, "child exited instead of holding the barrier"
        self.received = True
        self.record["events"].append("barrier_received")
        return marker

    def kill_and_reap(self):
        assert self.received and self.process.poll() is None
        self.process.kill()
        self.record["events"].append("sigkill_sent")
        code = self.process.wait(timeout=min(5, remaining(self.deadline)))
        self.record.update(returncode=code, reaped=True)
        self.record["events"].append("reaped")
        assert code == -signal.SIGKILL
        # A held child sends exactly one frame. A duplicate/response is a failure.
        self.channel.settimeout(remaining(self.deadline))
        assert self.channel.recv(1) == b"", "unexpected message after the held barrier"
        self.record["events"].append("pipe_eof")
        return self.record

    def close(self):
        try:
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()
                self.record["events"].append("cleanup_sigterm")
                try:
                    self.process.wait(timeout=min(2, max(0, self.deadline - monotonic() - 3)))
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.record["events"].append("cleanup_sigkill")
                    self.process.wait(timeout=max(0, self.deadline - monotonic()))
            if self.process is not None:
                assert self.process.poll() is not None, "child not reaped"
                self.record.update(returncode=self.process.returncode, reaped=True)
        finally:
            if self.channel is not None:
                self.channel.close()
            if self.log is not None:
                self.log.close()
            self.record["elapsed_seconds"] = monotonic() - self.started_at
            self.record_path.write_text(json.dumps(self.record, allow_nan=False))
