"""Pure successor accounting controls; native validity is a separate oracle."""

import hashlib
import json
from dataclasses import replace

import pytest

from agent_rewind import failure_encoding
from agent_rewind.admission_records import AdmissionStorageError
from agent_rewind.operation_failure_reads import JobObservation, SuccessorReceiptBook
from agent_rewind.operation_reads import JOB_LIMITS, MAX_RECEIPT_BYTES, RawReceipt


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def job():
    values = {
        "id": "a" * 32,
        "kind": "run",
        "created": 1.25,
        "payload": "b" * 64,
        "status": "queued",
        "owner": None,
        "lease_until": None,
        "cancel": 0,
        "budget": 100,
        "reserved": 0,
        "result": None,
        "error": None,
        "actor": "oidc:" + "c" * 64,
        "payload_version": 2,
        "execution_config_ref": "d" * 64,
        "execution_config_digest": "d" * 64,
    }
    return RawReceipt("job", values["id"], tuple(values), tuple(values.values()))


def test_successor_wire_counters_include_header_rows_observations_and_escaping():
    book = SuccessorReceiptBook()
    expected = {"v": 1, "rows": [], "observations": []}
    assert book.byte_count == book._wire_bytes == len(encoded(expected)) == 35
    run = {"id": "e" * 32, "kind": "run", "created": 1.25, "body": '"\\\n\u2603'}
    receipt = book.remember("run", run["id"], tuple(run), run)
    expected["rows"].append(["run", run["id"], list(run.values())])
    book.observe("cohort", "a" * 32, (run["id"],))
    expected["observations"].append(["cohort", "a" * 32, [run["id"]]])
    assert book.encoded() == encoded(expected)
    assert book.byte_count == book._wire_bytes == len(encoded(expected))
    before = book.byte_count
    assert book.remember("run", run["id"], tuple(run), run) is receipt
    book.observe("cohort", "a" * 32, (run["id"],))
    assert book.byte_count == before


def test_job_extension_uses_the_existing_identity_and_fixed_raw_field_order():
    book = SuccessorReceiptBook()
    receipt = job()
    observation = JobObservation(0, 0, False, None)
    assert receipt.fields == tuple(JOB_LIMITS)
    assert book.remember_job(receipt, observation) is receipt
    expected = {
        "v": 1,
        "rows": [["job", receipt.identity, list(receipt.values), [0, 0, False, None]]],
        "observations": [],
    }
    assert book.receipts == (receipt,)
    assert book.job_observation(receipt.identity) == observation
    assert book.encoded() == encoded(expected)
    assert book.byte_count == book._wire_bytes == len(encoded(expected))
    assert book.remember_job(receipt, JobObservation(0, 0, False, None)) is receipt
    assert book.encoded() == encoded(expected)


@pytest.mark.parametrize("change", ["raw_type", "generation", "any_call", "evidence"])
def test_job_conflict_refuses_without_replacing_original_or_charging(change):
    book = SuccessorReceiptBook()
    original = job()
    observation = JobObservation(0, 0, False, None)
    book.remember_job(original, observation)
    before = book.encoded(), book.byte_count, book.receipts
    current, fresh = original, observation
    if change == "raw_type":
        values = list(original.values)
        values[7] = False  # equal to native integer0, distinct raw type
        current = replace(original, values=tuple(values))
    elif change == "generation":
        fresh = JobObservation(1, 0, False, None)
    elif change == "any_call":
        fresh = JobObservation(0, 0, True, None)
    else:
        fresh = JobObservation(0, 1, False, (None,) * 15)
    with pytest.raises(AdmissionStorageError):
        book.remember_job(current, fresh)
    assert (book.encoded(), book.byte_count, book.receipts) == before


def test_evidence_scalar_type_is_not_hidden_by_python_numeric_equality():
    book = SuccessorReceiptBook()
    receipt = job()
    original = (1,) + (None,) * 14
    book.remember_job(receipt, JobObservation(0, 1, False, original))
    before = book.encoded(), book.byte_count
    with pytest.raises(AdmissionStorageError):
        book.remember_job(receipt, JobObservation(0, 1, False, (True,) + (None,) * 14))
    assert (book.encoded(), book.byte_count) == before


@pytest.mark.parametrize("extra", [0, 1])
def test_serializer_exact_limit_and_one_over_are_distinct_from_native_shape(extra):
    book = SuccessorReceiptBook()
    identity = "e" * 32
    empty = {"id": identity, "kind": "run", "created": 1, "body": ""}
    wire = {"v": 1, "rows": [["run", identity, list(empty.values())]], "observations": []}
    # This deliberately synthetic serializer frame is not a claim that a native
    # run may exceed the unchanged2MiB body limit.
    row = {**empty, "body": "x" * (MAX_RECEIPT_BYTES - len(encoded(wire)) + extra)}
    if extra:
        with pytest.raises(AdmissionStorageError):
            book.remember("run", identity, tuple(row), row)
        assert book.receipts == () and book.byte_count == book._wire_bytes == 35
    else:
        book.remember("run", identity, tuple(row), row)
        assert len(book.encoded()) == book.byte_count == book._wire_bytes == MAX_RECEIPT_BYTES
        assert book.remaining == 0


def test_frame_reservation_is_live_until_release_and_never_refunds_receipts():
    book = SuccessorReceiptBook()
    initial = book.remaining
    with (
        pytest.raises(RuntimeError, match="original"),
        book.frame(4096),
    ):
        assert book.active_frame_bytes == 4096 and book.remaining == initial - 4096
        with pytest.raises(AdmissionStorageError), book.frame(1):
            pass
        with pytest.raises(AdmissionStorageError):
            book._before_cohort()
        with pytest.raises(AdmissionStorageError):
            book.encoded()
        raise RuntimeError("original")
    assert book.active_frame_bytes == 0 and book.remaining == initial
    assert book.byte_count == book._wire_bytes == 35
    book._before_cohort()


def test_fixed_field_array_and_extension_requirement_refuse_without_retention():
    book = SuccessorReceiptBook()
    receipt = job()
    with pytest.raises(AdmissionStorageError):
        book.remember("job", receipt.identity, receipt.fields, receipt.row())
    row = {"id": "e" * 32, "kind": "run", "created": 1, "body": ""}
    with pytest.raises(AdmissionStorageError):
        book.remember("run", row["id"], ("id", "kind", "body", "created"), row)
    assert book.receipts == () and book.byte_count == book._wire_bytes == 35


def test_measured_frame_is_reserved_before_encoder_and_released_before_return(monkeypatch):
    book = SuccessorReceiptBook()
    frame = ["test-frame", 1, ["s", '"\\\n☃🚀'], ["i", "-9223372036854775808"]]
    expected = encoded(frame)
    original = failure_encoding.bounded_canonical
    observations = []

    def encode(value, **kwargs):
        observations.append((book.active_frame_bytes, book.remaining))
        return original(value, **kwargs)

    monkeypatch.setattr(failure_encoding, "bounded_canonical", encode)
    result = failure_encoding._digest(frame, book.remaining, _reserve=book.frame)
    assert result == (hashlib.sha256(expected).hexdigest(), len(expected))
    assert observations == [(len(expected), MAX_RECEIPT_BYTES - 35 - len(expected))]
    assert book.active_frame_bytes == 0 and book.remaining == MAX_RECEIPT_BYTES - 35
    # The existing no-hook digest result is unchanged.
    assert failure_encoding._digest(frame, book.remaining) == result


def test_frame_encoder_failure_keeps_original_exception_and_releases(monkeypatch):
    book = SuccessorReceiptBook()
    original = RuntimeError("original")
    observed = []

    def fail(value, **kwargs):
        observed.append(book.active_frame_bytes)
        raise original

    monkeypatch.setattr(failure_encoding, "bounded_canonical", fail)
    with pytest.raises(RuntimeError) as failure:
        failure_encoding._digest(["frame", 1], book.remaining, _reserve=book.frame)
    assert failure.value is original and observed == [len(encoded(["frame", 1]))]
    assert book.active_frame_bytes == 0 and book.byte_count == book._wire_bytes == 35
