"""Negative controls for the actual-death IPC proof."""

import socket
import struct
from time import monotonic

import pytest
from ledger_process_fixture import FRAME_LIMIT, receive_frame, validate_marker


@pytest.mark.parametrize(
    "field,value",
    [("nonce", "other"), ("pid", True), ("case", "other"), ("phase", "after"), ("sequence", 2)],
)
def test_barrier_rejects_wrong_identity_or_order(field, value):
    marker = {
        "nonce": "nonce",
        "pid": 123,
        "case": "initialize",
        "phase": "before",
        "sequence": 1,
        "raw_id": 456,
        "witness": {},
    }
    marker[field] = value
    with pytest.raises(AssertionError):
        validate_marker(marker, nonce="nonce", pid=123, case="initialize", phase="before")


@pytest.mark.parametrize("size", [0, FRAME_LIMIT + 1])
def test_barrier_rejects_oversize_or_empty_frame_before_body(size):
    receiver, sender = socket.socketpair()
    try:
        sender.sendall(struct.pack("!I", size))
        with pytest.raises(ValueError, match="invalid process barrier frame length"):
            receive_frame(receiver, monotonic() + 1)
    finally:
        receiver.close()
        sender.close()


def test_barrier_rejects_partial_frame_and_bounds_silent_peer():
    receiver, sender = socket.socketpair()
    try:
        sender.sendall(struct.pack("!I", 10) + b"{}")
        sender.close()
        with pytest.raises(EOFError):
            receive_frame(receiver, monotonic() + 1)
    finally:
        receiver.close()
    receiver, sender = socket.socketpair()
    try:
        with pytest.raises(TimeoutError):
            receive_frame(receiver, monotonic() + 0.02)
    finally:
        receiver.close()
        sender.close()
