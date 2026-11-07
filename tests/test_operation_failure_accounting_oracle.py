"""Independent D3 wire and finite-buffer accounting controls.

Synthetic serializer ceilings below are not native supported-cohort evidence.
Healthy GET259 and verified-failure258 identities, full cancellation84/85,
and actual SQL transfer/compiled-bind fit require the complete native services.
"""

import hashlib
import json
from dataclasses import replace

import pytest

from agent_rewind.admission_records import AdmissionStorageError
from agent_rewind.operation_failure_reads import JobObservation, SuccessorReceiptBook
from agent_rewind.operation_reads import RawReceipt, ReceiptBook

JOB = "a" * 32
RUN_FIELDS = ("id", "kind", "created", "body")
JOB_FIELDS = (
    "id",
    "kind",
    "created",
    "payload",
    "status",
    "owner",
    "lease_until",
    "cancel",
    "budget",
    "reserved",
    "result",
    "error",
    "actor",
    "payload_version",
    "execution_config_ref",
    "execution_config_digest",
)
BOOK_LIMIT = 4 * 1024 * 1024


def canonical(value):
    """Independent JSON oracle; no product serializer or field-array import."""
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def job(*, status="failed", cancel=False):
    return RawReceipt(
        "job",
        JOB,
        JOB_FIELDS,
        (
            JOB,
            "run",
            0.0,
            "b" * 64,
            status,
            None,
            None,
            cancel,
            7,
            0,
            None,
            None,
            None,
            2,
            "c" * 64,
            "d" * 64,
        ),
    )


def evidence():
    return (
        1,
        "verified_failure",
        "e" * 32,
        "job",
        JOB,
        "f" * 32,
        1,
        "failed",
        "dependency_failed",
        "outcome_unknown",
        "admission",
        "1" * 32,
        "2" * 64,
        "3" * 64,
        0,
    )


def run_row(number, body=""):
    identity = f"{number:032x}"
    return {
        "id": identity,
        "kind": "run",
        "created": "2026-01-02 03:04:05.000006+00:00",
        "body": body,
    }


def remember_run(book, row):
    return book.remember("run", row["id"], RUN_FIELDS, row)


def fingerprint(book):
    wire = book.encoded()
    return (
        len(wire),
        hashlib.sha256(wire).hexdigest(),
        book.byte_count,
        book._wire_bytes,
        len(book.receipts),
        book.active_frame_bytes,
    )


def assert_wire(book, rows, observations):
    expected = canonical({"v": 1, "rows": rows, "observations": observations})
    actual = book.encoded()
    assert actual == expected
    assert book.byte_count == book._wire_bytes == len(expected)
    assert book.remaining == BOOK_LIMIT - len(expected)


def test_wire_counter_uses_ascii_escaped_json_and_independent_array_layout():
    book = SuccessorReceiptBook()
    rows, observations = [], []
    assert_wire(book, rows, observations)
    assert book.byte_count == 35

    row = run_row(1, 'quoted" slash\\ control\n snowman\u2603')
    assert canonical(row["body"]) == b'"quoted\\" slash\\\\ control\\n snowman\\u2603"'
    assert b"\\u2603" in canonical(row)
    assert "\u2603".encode() not in canonical(row)
    remember_run(book, row)
    rows.append(["run", row["id"], [row[field] for field in RUN_FIELDS]])
    assert_wire(book, rows, observations)

    receipt, cells = job(), evidence()
    observation = JobObservation(1, 1, False, cells)
    book.remember_job(receipt, observation)
    rows.append(["job", JOB, list(receipt.values), [1, 1, False, list(cells)]])
    assert len(book.receipts) == 2
    assert book.job_observation(JOB) is observation
    assert_wire(book, rows, observations)

    book.observe("result_count", JOB, (0,))
    observations.append(["result_count", JOB, [0]])
    assert_wire(book, rows, observations)
    book.observe("cohort", JOB, (row["id"],))
    observations.append(["cohort", JOB, [row["id"]]])
    assert_wire(book, rows, observations)

    before = fingerprint(book)
    assert remember_run(book, row) is book.receipts[0]
    assert book.remember_job(receipt, JobObservation(1, 1, False, cells)) is receipt
    book.observe("result_count", JOB, (0,))
    book.observe("cohort", JOB, (row["id"],))
    assert fingerprint(book) == before


@pytest.mark.parametrize("field,value", [("cancel", 0), ("created", 0)])
def test_equal_python_values_cannot_replace_original_native_job_types(field, value):
    book = SuccessorReceiptBook()
    receipt = job()
    observed = JobObservation(1, 0, False, None)
    book.remember_job(receipt, observed)
    before = fingerprint(book)
    changed = list(receipt.values)
    changed[JOB_FIELDS.index(field)] = value
    with pytest.raises(AdmissionStorageError):
        book.remember_job(replace(receipt, values=tuple(changed)), observed)
    assert fingerprint(book) == before


def test_equal_numeric_evidence_cells_still_require_original_type_identity():
    book = SuccessorReceiptBook()
    cells = evidence()
    book.remember_job(job(), JobObservation(1, 1, False, cells))
    before = fingerprint(book)
    # Generic receipt retention must not hide a raw native integer/bool change.
    # This altered row is not claimed to be valid native failure evidence.
    changed = (*cells[:-1], False)
    with pytest.raises(AdmissionStorageError):
        book.remember_job(job(), JobObservation(1, 1, False, changed))
    assert fingerprint(book) == before


@pytest.mark.parametrize(
    "observation",
    [
        (True, 0, False, None),
        (1, True, False, None),
        (1, 0, 0, None),
        (1, 2, False, None),
        (1, 1, False, None),
        (-1, 0, False, None),
        (2**63, 0, False, None),
    ],
)
def test_malformed_extension_never_enters_the_existing_job_identity(observation):
    book = SuccessorReceiptBook()
    before = fingerprint(book)
    with pytest.raises(AdmissionStorageError):
        book.remember_job(job(), JobObservation(*observation))
    assert fingerprint(book) == before


def test_mutated_frozen_extension_is_revalidated_before_retention():
    book = SuccessorReceiptBook()
    before = fingerprint(book)
    observation = JobObservation(1, 0, False, None)
    object.__setattr__(observation, "generation", True)
    with pytest.raises(AdmissionStorageError):
        book.remember_job(job(), observation)
    assert fingerprint(book) == before


def test_fixed_fields_and_job_extension_are_required_without_partial_retention():
    book = SuccessorReceiptBook()
    receipt = job()
    before = fingerprint(book)
    with pytest.raises(AdmissionStorageError):
        book.remember("job", JOB, JOB_FIELDS, receipt.row())
    with pytest.raises(AdmissionStorageError):
        book.remember_job(
            replace(receipt, fields=(*JOB_FIELDS[:-1], "execution_config_ref")),
            JobObservation(1, 0, False, None),
        )
    assert fingerprint(book) == before


def test_serializer_259_identity_ceiling_does_not_allocate_a_260th_job_extension():
    book = SuccessorReceiptBook()
    for number in range(259):
        remember_run(book, run_row(number))
    assert len(book.receipts) == 259
    before = fingerprint(book)
    with pytest.raises(AdmissionStorageError):
        book.remember_job(job(), JobObservation(1, 0, False, None))
    assert fingerprint(book) == before
    with pytest.raises(AdmissionStorageError):
        book.job_observation(JOB)


@pytest.mark.parametrize("extra", [0, 1])
def test_synthetic_serialized_book_exact_byte_ceiling_and_one_over(extra):
    book = SuccessorReceiptBook()
    row = run_row(1)
    empty = canonical(
        {
            "v": 1,
            "rows": [["run", row["id"], [row[field] for field in RUN_FIELDS]]],
            "observations": [],
        }
    )
    # Deliberately serializer-only: this body exceeds the native source-body
    # ceiling and supplies no supported GET or complete-service fit credit.
    row["body"] = "x" * (BOOK_LIMIT - len(empty) + extra)
    before = fingerprint(book)
    if extra:
        with pytest.raises(AdmissionStorageError):
            remember_run(book, row)
        assert fingerprint(book) == before
    else:
        remember_run(book, row)
        expected = canonical(
            {
                "v": 1,
                "rows": [["run", row["id"], [row[field] for field in RUN_FIELDS]]],
                "observations": [],
            }
        )
        actual = book.encoded()
        assert len(actual) == book.byte_count == book._wire_bytes == BOOK_LIMIT
        assert hashlib.sha256(actual).digest() == hashlib.sha256(expected).digest()
        assert book.remaining == 0
        before = fingerprint(book)
        with pytest.raises(AdmissionStorageError):
            book.observe("result_count", JOB, (0,))
        assert fingerprint(book) == before


@pytest.mark.parametrize("size", [False, 0, -1, 4097])
def test_frame_rejects_noninteger_or_oversize_before_reservation(size):
    book = SuccessorReceiptBook()
    before = fingerprint(book)
    with (
        pytest.raises(AdmissionStorageError),
        book.frame(size),
    ):
        pytest.fail("Invalid frame was entered")
    assert fingerprint(book) == before


def test_frame_reservation_covers_remaining_capacity_and_blocks_cohort_loading():
    book = SuccessorReceiptBook()
    row = run_row(1)
    empty = canonical(
        {
            "v": 1,
            "rows": [["run", row["id"], [row[field] for field in RUN_FIELDS]]],
            "observations": [],
        }
    )
    row["body"] = "x" * (BOOK_LIMIT - 4096 - len(empty))
    remember_run(book, row)
    before = fingerprint(book)
    with book.frame(4096):
        assert book.active_frame_bytes == 4096 and book.remaining == 0
        with pytest.raises(AdmissionStorageError):
            book.observe("result_count", JOB, (0,))
        with pytest.raises(AdmissionStorageError):
            book.encoded()
        with pytest.raises(AdmissionStorageError):
            book._before_cohort()
        with (
            pytest.raises(AdmissionStorageError),
            book.frame(1),
        ):
            pytest.fail("Nested frame was entered")
        assert book.active_frame_bytes == 4096
    assert fingerprint(book) == before


def test_frame_release_preserves_the_original_error_and_does_not_refund_retained_rows():
    book = SuccessorReceiptBook()
    before = fingerprint(book)
    failure = RuntimeError("synthetic_frame_failure")
    with (
        pytest.raises(RuntimeError) as error,
        book.frame(4096),
    ):
        raise failure
    assert error.value is failure
    assert fingerprint(book) == before
    row = run_row(1, "retained")
    with book.frame(32):
        remember_run(book, row)
    assert_wire(book, [["run", row["id"], [row[field] for field in RUN_FIELDS]]], [])


@pytest.mark.parametrize("field", ["byte_count", "_wire_bytes", "both"])
def test_serialization_refuses_inconsistent_accounting_before_return(field):
    book = SuccessorReceiptBook()
    remember_run(book, run_row(1, "small"))
    if field in {"byte_count", "both"}:
        book.byte_count += 1
    if field in {"_wire_bytes", "both"}:
        book._wire_bytes += 1
    with pytest.raises(AdmissionStorageError):
        book.encoded()


def test_original_ar7_wire_remains_distinct_after_successor_use():
    original = ReceiptBook()
    successor = SuccessorReceiptBook()
    row = run_row(1, "unchanged")
    remember_run(original, row)
    old_expected = canonical(
        {
            "rows": [["run", row["id"], list(RUN_FIELDS), [row[field] for field in RUN_FIELDS]]],
            "observations": [],
        }
    )
    before = (original.encoded(), original.byte_count, original._wire_bytes)
    assert before[0] == old_expected
    remember_run(successor, row)
    successor.observe("result_count", JOB, (0,))
    assert (original.encoded(), original.byte_count, original._wire_bytes) == before
    assert successor.encoded() != before[0]
