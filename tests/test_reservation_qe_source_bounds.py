"""Independent actual-encoder vectors for P2 conservative source headroom."""

import json
import sqlite3

import pytest

from agent_rewind.migrations.schema import canonical
from agent_rewind.reservation_checks import (
    SourceStats,
    require_source_headroom,
    source_canonical_upper,
)
from agent_rewind.reservation_types import ReservationRefusal

MAX_MONEY = 2**63 - 1


@pytest.mark.parametrize(
    "document",
    [
        "null",
        "[null,true,false]",
        '{"z":-9223372036854775808,"a":9223372036854775807}',
        "[9007199254740993,5e-324,-0.0,1.7976931348623157e308]",
        json.dumps({"text": '\x00\n\t"\\\u03bb\U0001f600'}, ensure_ascii=False),
        '{"surrogate":"\\ud800"}',
        ' { "z" : [1e0, {"a": true}], "a" : "\\u03bb" } ',
    ],
    ids=[
        "null",
        "booleans",
        "signed64",
        "float_formats",
        "utf8_escapes",
        "surrogate",
        "nested_reordered",
    ],
)
def test_source_upper_bound_covers_actual_records_json_reserialization(document):
    raw = ["a" * 32, "run", -0.0, document]
    with sqlite3.connect(":memory:") as connection:
        native_bytes = sum(
            connection.execute("SELECT coalesce(length(CAST(? AS BLOB)),0)", (value,)).fetchone()[0]
            for value in raw
        )
    decoded = [*raw[:3], json.loads(document)]
    actual = canonical(decoded)
    assert len(actual) <= source_canonical_upper(native_bytes, 1, 4)
    # In particular the surrogate is re-escaped; no UTF-8 replacement or lossy
    # serialization may be used as a smaller capacity witness.
    assert json.loads(actual) == decoded


@pytest.mark.parametrize(
    "cell",
    [
        None,
        False,
        True,
        -0.0,
        5e-324,
        1.7976931348623157e308,
        -(2**63),
        2**53 + 1,
        MAX_MONEY,
        "",
        '\x00\n\t"\\',
        "\u03bb\U0001f600",
    ],
    ids=[
        "null",
        "false",
        "true",
        "negative_zero",
        "subnormal",
        "large_float",
        "min_int",
        "wide_int",
        "max_int",
        "empty",
        "controls",
        "unicode",
    ],
)
def test_source_upper_bound_uses_native_cells_and_actual_bool_normalization(cell):
    with sqlite3.connect(":memory:") as connection:
        native = connection.execute(
            "SELECT coalesce(length(CAST(? AS BLOB)),0)", (cell,)
        ).fetchone()[0]
    value = int(cell) if isinstance(cell, bool) else cell
    encoded = canonical([value])
    assert len(encoded) <= source_canonical_upper(native, 1, 1)


def source_receipts(**changes):
    result = {
        name: SourceStats(0, 0, 0) for name in ("api_keys", "audit", "events", "jobs", "records")
    }
    result.update(changes)
    return result


def test_source_cumulative_exact_cap_and_first_native_byte_above_are_distinct():
    # Contract-derived fixture: 80 thirteen-column jobs, not an online 1 GiB scan.
    exact = SourceStats(80, 33_552_347, 419_405)
    assert source_canonical_upper(exact.native_bytes, exact.rows, 13) == 1_073_741_824
    require_source_headroom(source_receipts(jobs=exact), prospective_job_growth=False)
    with pytest.raises(ReservationRefusal) as caught:
        require_source_headroom(
            source_receipts(jobs=SourceStats(80, 33_552_348, 419_405)),
            prospective_job_growth=False,
        )
    assert caught.value.reason == "capacity_exceeded"


def test_source_row_cap_uses_the_nearest_representable_bound_without_rounding_down():
    # V=32*m+834 cannot equal 16 MiB: 524261 is the largest admissible native m;
    # 524262 yields 16 MiB + 2. Accepting the latter would silently weaken the cap.
    require_source_headroom(
        source_receipts(jobs=SourceStats(1, 524_261, 524_261)), prospective_job_growth=False
    )
    with pytest.raises(ReservationRefusal) as caught:
        require_source_headroom(
            source_receipts(jobs=SourceStats(1, 524_262, 524_262)), prospective_job_growth=False
        )
    assert caught.value.reason == "capacity_exceeded"


def test_prospective_job_margin_is_reserved_once_and_checked_again_as_actual_state():
    before = SourceStats(80, 33_552_219, 419_405)
    require_source_headroom(source_receipts(jobs=before), prospective_job_growth=True)
    after = SourceStats(80, before.native_bytes + 128, before.max_native_bytes + 128)
    require_source_headroom(source_receipts(jobs=after), prospective_job_growth=False)
    with pytest.raises(ReservationRefusal) as caught:
        require_source_headroom(source_receipts(jobs=after), prospective_job_growth=True)
    assert caught.value.reason == "capacity_exceeded"


def test_source_zero_rows_and_incomplete_receipt_keys_are_not_capacity_credit():
    require_source_headroom(source_receipts(), prospective_job_growth=False)
    missing = source_receipts()
    del missing["records"]
    with pytest.raises(ReservationRefusal) as caught:
        require_source_headroom(missing, prospective_job_growth=False)
    assert caught.value.reason == "ledger_state_invalid"


def test_combined_claim_and_gross_growth_fits_the_original_job_delta_bound():
    # Original jobs projection has 13 columns. Generation is deliberately absent.
    # This is an encoding adversary, not a fabricated admitted financial state.
    before = [
        "a" * 32,
        "run",
        1.0,
        "b" * 64,
        "queued",
        None,
        None,
        False,
        200_000_000,
        0,
        None,
        None,
        "oidc:" + "c" * 64,
    ]
    after = list(before)
    after[4:7] = ["running", "d" * 32, 1.7976931348623157e308]
    after[9] = MAX_MONEY
    with sqlite3.connect(":memory:") as connection:

        def native(row):
            return sum(
                connection.execute(
                    "SELECT coalesce(length(CAST(? AS BLOB)),0)", (value,)
                ).fetchone()[0]
                for value in row
            )

        old, new = native(before), native(after)
    assert 0 < new - old <= 128
    encoded = canonical([int(value) if isinstance(value, bool) else value for value in after])
    assert len(encoded) <= source_canonical_upper(old + 128, 1, 13)
