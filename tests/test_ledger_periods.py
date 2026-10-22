"""Half-open provenance periods: incremental validation and bounded comparisons."""

from datetime import UTC, datetime, timedelta
from math import ceil, log2

import pytest
from ledger_fixture import (
    DialectOnlyConnection,
    account,
    canonical_bytes,
    cursor_for,
    identifier,
    initial_bundle,
    provision,
)

from agent_rewind.migrations import ledger_state as state
from agent_rewind.migrations.schema import MigrationRefused


def chain(periods, *, batch_size=1, scopes=None):
    initial, first, opening = initial_bundle(empty=True)
    raws = [initial]
    cursors = [state.validate_manifest_cursor(DialectOnlyConnection(), first)]
    origin = datetime(2030, 1, 1, tzinfo=UTC)
    for start in range(0, len(periods), batch_size):
        rows = []
        for index in range(start, min(start + batch_size, len(periods))):
            left, right = periods[index]
            project = None if scopes is None else scopes[index]
            rows.append(
                account(
                    2_000_000 + index,
                    "organization" if project is None else "project",
                    project=project,
                    start=(origin + timedelta(days=left)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    end=(origin + timedelta(days=right)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                )
            )
        raw = provision(raws[-1], len(raws), rows=rows)
        cursors.append(
            state.validate_manifest_cursor(
                DialectOnlyConnection(), cursor_for(raw, sequence=len(raws))
            )
        )
        raws.append(raw)
    return tuple(cursors), state.validate_opening_cursor(opening)


@pytest.mark.parametrize(
    "periods",
    [
        [(0, 1), (1, 2), (2, 3)],
        [(2, 3), (1, 2), (0, 1)],
        [(10, 11), (0, 1), (5, 6), (1, 2), (9, 10)],
    ],
)
def test_disjoint_touching_periods_accept_any_manifest_insertion_order(periods):
    cursors, opening = chain(periods)
    assert state.validate_ledger_chain(cursors, opening).sequence == len(periods)


@pytest.mark.parametrize(
    "periods",
    [
        [(0, 2), (1, 3)],
        [(1, 3), (0, 2)],
        [(0, 4), (1, 2)],
        [(1, 2), (0, 4)],
        [(0, 2), (0, 1)],
        [(0, 1), (0, 2)],
    ],
)
def test_overlap_refuses_from_either_side_or_same_start(periods):
    cursors, opening = chain(periods)
    with pytest.raises(MigrationRefused, match="^ledger_progress_invalid$"):
        state.validate_ledger_chain(cursors, opening)


def test_identical_periods_in_independent_scopes_do_not_conflict():
    cursors, opening = chain([(0, 2)] * 3, scopes=[None, identifier(100), identifier(101)])
    assert state.validate_ledger_chain(cursors, opening).sequence == 3


@pytest.mark.parametrize("earlier_overlap", [True, False])
def test_prior_overlap_is_checked_before_later_projection(monkeypatch, earlier_overlap):
    periods = [(0, 2), (1, 3) if earlier_overlap else (2, 3), (5, 6)]
    cursors, opening = chain(periods)
    later_id = cursors[-1].manifest.accounts[0].id
    last = cursors[-1].model_copy(update={"account_projection_digest": "f" * 64})
    cursors = (*cursors[:-1], last)
    checksum = state.checksum
    visited = []

    def observe(value):
        if isinstance(value, list) and value and "id" in value[0]:
            visited.extend(row["id"] for row in value)
            if later_id in visited:
                raise AssertionError("later malformed projection reached")
        return checksum(value)

    monkeypatch.setattr(state, "checksum", observe)
    if earlier_overlap:
        with pytest.raises(MigrationRefused, match="^ledger_progress_invalid$"):
            state.validate_ledger_chain(cursors, opening)
        assert later_id not in visited
    else:
        # The same oracle must detect reaching the later cursor.
        with pytest.raises(AssertionError, match="later malformed projection reached"):
            state.validate_ledger_chain(cursors, opening)


class CountedTime(str):
    comparisons = 0
    __hash__ = str.__hash__

    def __lt__(self, other):
        type(self).comparisons += 1
        return str.__lt__(self, other)

    def __gt__(self, other):
        type(self).comparisons += 1
        return str.__gt__(self, other)

    def __eq__(self, other):
        type(self).comparisons += 1
        return str.__eq__(self, other)


def counted_periods(cursors):
    observed = []
    for cursor in cursors:
        accounts = tuple(
            row.model_copy(
                update={
                    "period_start": CountedTime(row.period_start),
                    "period_end": CountedTime(row.period_end),
                }
            )
            for row in cursor.manifest.accounts
        )
        manifest = cursor.manifest.model_copy(update={"accounts": accounts})
        copied = cursor.model_copy(update={"manifest": manifest})
        # All inputs were validated before transparent comparison instrumentation.
        assert canonical_bytes(copied.model_dump(mode="json")) == canonical_bytes(
            cursor.model_dump(mode="json")
        )
        observed.append(copied)
    CountedTime.comparisons = 0
    return tuple(observed)


@pytest.mark.parametrize("reverse", [False, True])
def test_period_comparisons_grow_subquadratically(reverse):
    measurements = []
    for count in (512, 1024):
        positions = list(range(count))
        if reverse:
            positions.reverse()
        periods = [(index, index + 1) for index in positions]
        cursors, opening = chain(periods, batch_size=64)
        observed = counted_periods(cursors)
        assert state.validate_ledger_chain(observed, opening).sequence == count // 64
        comparisons = CountedTime.comparisons
        assert count <= comparisons <= 4 * count * ceil(log2(count + 1))
        measurements.append(comparisons)
    assert measurements[1] <= measurements[0] * 2.5
    # This bounds Python comparisons, not list movement or total runtime complexity.


def test_deadline_after_period_search_refuses_before_insertion(monkeypatch):
    cursors, opening = chain([(0, 1)])
    search = state.bisect_left
    searched = []
    expired = False

    def observed(cohort, value):
        nonlocal expired
        result = search(cohort, value)
        searched.append(cohort)
        expired = True
        return result

    def check():
        if expired:
            raise TimeoutError("period search deadline")

    monkeypatch.setattr(state, "bisect_left", observed)
    with pytest.raises(TimeoutError, match="period search deadline"):
        state.validate_ledger_chain(cursors, opening, check=check)
    assert searched == [[]]
