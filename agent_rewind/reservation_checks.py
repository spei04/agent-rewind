"""Exact arithmetic, database-clock decoding and consumer headroom for P2.

These pure checks grant neither transaction ownership nor dispatch permission.
Source capacity is a conservative size proof for supported original rows, not
a new assertion that arbitrary JSON/graph contents are valid.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from .migrations.inputs import MAX_ROW_BYTES, MAX_SOURCE_BYTES
from .migrations.schema import COLUMNS, TABLES
from .reservation_types import MAX_MONEY, ReservationRefusal

Dialect = Literal["sqlite", "postgresql"]
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z")


@dataclass(frozen=True)
class SourceStats:
    rows: int
    native_bytes: int
    max_native_bytes: int


def _nonnegative(value: int) -> None:
    if type(value) is not int or value < 0:
        raise ReservationRefusal("ledger_state_invalid")


def source_canonical_upper(native_bytes: int, rows: int, columns: int) -> int:
    """Conservative bound for original row-data bytes, excluding hash headers."""
    _nonnegative(native_bytes)
    _nonnegative(rows)
    if type(columns) is not int or not 1 <= columns <= 13:
        raise ReservationRefusal("ledger_state_invalid")
    return 32 * native_bytes + (64 * columns + 2) * rows


def require_source_headroom(
    receipts: Mapping[str, SourceStats], *, prospective_job_growth: bool
) -> None:
    """Apply original native caps and a separate conservative canonical bound.

    The one prospective job can grow by at most128 native bytes: owner32,
    status1, finite lease64 and gross counter19 total116. Generation is not in
    the original13 fields. Actual post-state checks add no second reserve.
    """
    if type(prospective_job_growth) is not bool or set(receipts) != set(TABLES):
        raise ReservationRefusal("ledger_state_invalid")
    total_rows = total_native = total_canonical = 0
    for table in TABLES:
        receipt = receipts[table]
        if type(receipt) is not SourceStats:
            raise ReservationRefusal("ledger_state_invalid")
        count, native, maximum = (
            receipt.rows,
            receipt.native_bytes,
            receipt.max_native_bytes,
        )
        for value in (count, native, maximum):
            _nonnegative(value)
        if maximum > native or native > count * maximum:
            raise ReservationRefusal("ledger_state_invalid")
        if count == 0 and (native or maximum):
            raise ReservationRefusal("ledger_state_invalid")
        if prospective_job_growth and table == "jobs":
            if count == 0:
                raise ReservationRefusal("ledger_state_invalid")
            native += 128
            maximum += 128
        total_rows += count
        total_native += native
        columns = len(COLUMNS[table])
        total_canonical += source_canonical_upper(native, count, columns)
        row_upper = source_canonical_upper(maximum, 1, columns) if count else 0
        if (
            total_rows > 1_000_000
            or total_native > MAX_SOURCE_BYTES
            or maximum > MAX_ROW_BYTES
            or total_canonical > MAX_SOURCE_BYTES
            or row_upper > MAX_ROW_BYTES
        ):
            raise ReservationRefusal("capacity_exceeded")


def money_total(values: Sequence[int]) -> int:
    """Add native nonnegative signed64 values without float/SQL arithmetic."""
    total = 0
    for value in values:
        if type(value) is not int or not 0 <= value <= MAX_MONEY - total:
            raise ReservationRefusal("ledger_state_invalid")
        total += value
    return total


def require_budget(used: int, amount: int, limit: int) -> None:
    """A valid prospective amount can be too large without invalidating state."""
    for value in (used, amount, limit):
        if type(value) is not int or not 0 <= value <= MAX_MONEY:
            raise ReservationRefusal("ledger_state_invalid")
    if used > limit or amount > limit - used:
        raise ReservationRefusal("budget_exceeded")


def utc_microseconds(value: str) -> int:
    if type(value) is not str or len(value) != 27 or _UTC.fullmatch(value) is None:
        raise ReservationRefusal("ledger_state_invalid")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    except ValueError:
        raise ReservationRefusal("ledger_state_invalid") from None
    delta = parsed - _EPOCH
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def _quantum(dialect: Dialect) -> int:
    if dialect == "sqlite":
        return 1000
    if dialect == "postgresql":
        return 1
    raise ReservationRefusal("ledger_state_invalid")


def database_tick(value: str, dialect: Dialect) -> int:
    """Decode a native UTC sample; SQLite exposes only millisecond precision."""
    _quantum(dialect)
    if dialect == "sqlite":
        if type(value) is not str or len(value) != 24 or not value.endswith("Z"):
            raise ReservationRefusal("ledger_state_invalid")
        return utc_microseconds(value[:-1] + "000Z")
    return utc_microseconds(value)


def window_on_grid(start: str, end: str, dialect: Dialect) -> tuple[int, int]:
    quantum = _quantum(dialect)
    first, last = utc_microseconds(start), utc_microseconds(end)
    if first >= last:
        raise ReservationRefusal("ledger_state_invalid")
    return -(-first // quantum) * quantum, (last // quantum) * quantum


def require_window(now: int, start: str, end: str, dialect: Dialect) -> None:
    quantum = _quantum(dialect)
    if type(now) is not int or now % quantum:
        raise ReservationRefusal("ledger_state_invalid")
    first, last = window_on_grid(start, end, dialect)
    if not first <= now < last:
        raise ReservationRefusal("job_not_live")


def lease_live(value: int | float | None, now: int) -> bool:
    if type(now) is not int:
        raise ReservationRefusal("ledger_state_invalid")
    if value is None:
        return False
    if type(value) is int:
        if not -MAX_MONEY - 1 <= value <= MAX_MONEY:
            raise ReservationRefusal("ledger_state_invalid")
        numerator, denominator = value, 1
    elif type(value) is float and math.isfinite(value):
        numerator, denominator = value.as_integer_ratio()
    else:
        raise ReservationRefusal("ledger_state_invalid")
    return now * denominator < numerator * 1_000_000


def new_lease(now: int, seconds: int, window_end: int) -> float:
    if (
        type(now) is not int
        or type(window_end) is not int
        or type(seconds) is not int
        or not 1 <= seconds <= 60
        or not -62_135_596_800_000_000 <= now < 253_402_300_800_000_000
        or not -62_135_596_800_000_000 <= window_end <= 253_402_300_800_000_000
    ):
        raise ReservationRefusal("ledger_state_invalid")
    target = min(now + seconds * 1_000_000, window_end)
    if target <= now:
        raise ReservationRefusal("job_not_live")
    value = target / 1_000_000
    numerator, denominator = value.as_integer_ratio()
    if numerator * 1_000_000 > target * denominator:
        value = math.nextafter(value, -math.inf)
    if not math.isfinite(value) or len(str(value)) > 64 or not lease_live(value, now):
        raise ReservationRefusal("job_not_live")
    return value
