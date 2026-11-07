"""Typed frame and encoder components; no native shape or service-fit claims."""

import hashlib
import json
from datetime import datetime

import pytest

from agent_rewind import failure_encoding
from agent_rewind.admission_request import AdmissionPreparationError, bounded_canonical
from agent_rewind.failure_evidence import FailureRefusal


def canonical(value):
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, ["n"]),
        (False, ["b", 0]),
        (True, ["b", 1]),
        (0, ["i", "0"]),
        (1, ["i", "1"]),
        (-1, ["i", "-1"]),
        (-(2**63), ["i", "-9223372036854775808"]),
        (2**63 - 1, ["i", "9223372036854775807"]),
        (0.0, ["f", "0x0.0p+0"]),
        (-0.0, ["f", "0x0.0p+0"]),
        (1.0, ["f", "0x1.0000000000000p+0"]),
        ('quote" slash\\ snowman\u2603\n', ["s", 'quote" slash\\ snowman\u2603\n']),
    ],
)
def test_typed_frame_matches_independent_literal_tags_and_ascii_bytes(value, expected):
    frame = failure_encoding._row("row", ("cell",), {"cell": value})
    wanted = ["row", [["cell", expected]]]
    assert frame == wanted
    wire = canonical(wanted)
    digest, size = failure_encoding._digest(frame, 4096)
    assert (digest, size) == (hashlib.sha256(wire).hexdigest(), len(wire))


def test_only_float_signed_zero_normalizes_not_types_or_timestamp_text():
    values = [False, 0, 0.0, "0", None]
    tags = [failure_encoding._tag(value) for value in values]
    assert len({canonical(tag) for tag in tags}) == len(values)
    assert failure_encoding._tag(-0.0) == failure_encoding._tag(0.0)
    first = "2026-01-02T03:04:05+00:00"
    second = "2026-01-02T03:04:05.000000Z"
    assert datetime.fromisoformat(first) == datetime.fromisoformat(second)
    assert failure_encoding._tag(first) == ["s", first]
    assert failure_encoding._tag(second) == ["s", second]
    assert failure_encoding._digest(["timestamp", ["s", first]], 4096) != (
        failure_encoding._digest(["timestamp", ["s", second]], 4096)
    )


@pytest.mark.parametrize(
    "value",
    [2**63, -(2**63) - 1, float("nan"), float("inf"), -float("inf"), "\ud800", b"x", []],
)
def test_typed_frame_refuses_unsupported_scalar_before_digest(value, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("invalid scalar reached the encoder")

    monkeypatch.setattr(failure_encoding, "_digest", forbidden)
    with pytest.raises(FailureRefusal) as caught:
        failure_encoding._row("row", ("cell",), {"cell": value})
    assert caught.value.reason == "invalid_intent"


@pytest.mark.parametrize("extra", [0, 1], ids=["exact", "one-over"])
def test_synthetic_frame_encoder_4096_boundary_is_not_native_reachability(extra):
    # Deliberate encoder input, not a claim that a native digest frame can reach this size.
    frame = ["synthetic", "x" * (4096 - len(canonical(["synthetic", ""])) + extra)]
    wire = canonical(frame)
    assert len(wire) == 4096 + extra
    if extra:
        with pytest.raises(FailureRefusal) as caught:
            failure_encoding._digest(frame, 4096)
        assert caught.value.reason == "capacity_exceeded"
    else:
        assert failure_encoding._digest(frame, 4096) == (hashlib.sha256(wire).hexdigest(), 4096)


@pytest.mark.parametrize("extra", [0, 1], ids=["exact", "one-over"])
def test_2048_response_encoder_ceiling_without_invented_operation_fields(extra):
    # The service uses this same encoder/limit. This object is an encoder control,
    # not a fabricated valid OperationView or a native maximum-response claim.
    value = {"component": "x" * (2048 - len(canonical({"component": ""})) + extra)}
    wanted = canonical(value)
    assert len(wanted) == 2048 + extra
    if extra:
        with pytest.raises(AdmissionPreparationError) as caught:
            bounded_canonical(value, limit=2048, limit_code="admission_body_limit")
        assert caught.value.code == "admission_body_limit"
    else:
        assert bounded_canonical(value, limit=2048, limit_code="admission_body_limit") == wanted
