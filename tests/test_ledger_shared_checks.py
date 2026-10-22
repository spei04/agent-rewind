"""Cooperative pure-ledger checks, without issuing operator inspection rights."""

from datetime import date, timedelta

import pytest
from ledger_fixture import (
    DialectOnlyConnection,
    account,
    cursor_for,
    digest,
    manifest,
    opening_for,
    provision,
)

from agent_rewind.migrations import ledger_state, ledger_work
from agent_rewind.migrations.ledger_check import LedgerCheck
from agent_rewind.migrations.ledger_inputs import LedgerAccount
from agent_rewind.migrations.ledger_state import (
    ManifestCursor,
    OpeningJob,
    validate_ledger_chain,
    validate_manifest_cursor,
    validate_opening_cursor,
)
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import MigrationRefused


def parsed(raws, opening):
    return (
        tuple(
            validate_manifest_cursor(
                DialectOnlyConnection(),
                cursor_for(raw, sequence=i, opening=opening if i == 0 else None),
            )
            for i, raw in enumerate(raws)
        ),
        validate_opening_cursor(opening),
    )


@pytest.fixture
def cohort():
    initial = manifest(empty=True)
    opening = opening_for(initial)
    raws = [initial]
    origin = date(2026, 1, 1)
    for sequence in range(1, 4):
        rows = []
        for offset in range(64):
            start = origin + timedelta(days=(sequence - 1) * 64 + offset)
            rows.append(
                account(
                    sequence * 1000 + offset,
                    start=start.isoformat() + "T00:00:00.000000Z",
                    end=(start + timedelta(days=1)).isoformat() + "T00:00:00.000000Z",
                )
            )
        raws.append(provision(raws[-1], sequence, rows=rows))
    cursors, opening = parsed(raws, opening)
    assert sum(cursor.account_count for cursor in cursors) == 192
    assert validate_ledger_chain(cursors, opening).manifest_digest == digest(raws[-1])
    return cursors, opening


class CheckOnly:
    def __init__(self):
        self.calls = 0

    def check(self) -> None:
        self.calls += 1


def test_check_only_object_preserves_exact_receipt_without_authority(cohort):
    cursors, opening = cohort
    expected = validate_ledger_chain(cursors, opening)
    checker: LedgerCheck = CheckOnly()
    assert validate_ledger_chain(cursors, opening, check=checker.check) == expected
    assert checker.calls > 192
    assert not hasattr(checker, "connection")
    assert not hasattr(checker, "ordinary")
    assert validate_ledger_chain(cursors, opening, check=None) == expected


@pytest.mark.parametrize("fault", ["parent", "overlap", "projection"])
def test_callback_keeps_existing_invalid_history_refusals(cohort, fault):
    cursors, opening = cohort
    raw = cursors[-1].model_dump(mode="json")
    if fault == "parent":
        raw["manifest"]["parent_manifest_digest"] = "f" * 64
        raw["parent_manifest_digest"] = "f" * 64
    elif fault == "overlap":
        raw["manifest"]["accounts"][0]["period_start"] = "2026-05-08T00:00:00.000000Z"
    else:
        raw["account_projection_digest"] = "f" * 64
    raw["manifest_digest"] = digest(raw["manifest"])
    invalid = (*cursors[:-1], validate_manifest_cursor(DialectOnlyConnection(), raw))
    for check in (None, CheckOnly().check):
        with pytest.raises(MigrationRefused, match="^ledger_progress_invalid$"):
            validate_ledger_chain(invalid, opening, check=check)


@pytest.mark.parametrize(
    "error", [KeyboardInterrupt(), TimeoutError(), MigrationRefused("migration_busy")]
)
def test_check_interruptions_preserve_original_identity(cohort, error):
    def stop():
        raise error

    with pytest.raises(type(error)) as captured:
        validate_ledger_chain(*cohort, check=stop)
    assert captured.value is error


@pytest.mark.parametrize("phase", ["cursor", "account", "projection", "receipt"])
def test_expiry_after_actual_serialization_prevents_more_work_or_return(monkeypatch, cohort, phase):
    clock = [0.0]
    visits = []
    expired = [False]
    monkeypatch.setattr(ledger_work, "monotonic", lambda: clock[0])
    cursors, opening = cohort

    def observe(value):
        visits.append(value)
        if expired[0]:
            clock[0] = 121.0

    if phase == "cursor":
        original = ledger_state.canonical

        def serialized(value):
            result = original(value)
            observe(result)
            return result

        monkeypatch.setattr(ledger_state, "canonical", serialized)
    elif phase == "account":
        original_dump = LedgerAccount.model_dump

        def dumped(self, *args, **kwargs):
            result = original_dump(self, *args, **kwargs)
            observe(result)
            return result

        monkeypatch.setattr(LedgerAccount, "model_dump", dumped)
    elif phase == "projection":
        original_checksum = ledger_state.checksum

        def checksummed(value):
            result = original_checksum(value)
            observe(result)
            return result

        monkeypatch.setattr(ledger_state, "checksum", checksummed)
    else:
        original_receipt = ManifestCursor.receipt.fget

        def receipt(self):
            result = original_receipt(self)
            observe(result)
            return result

        monkeypatch.setattr(ManifestCursor, "receipt", property(receipt))

    expected = validate_ledger_chain(cursors, opening)
    assert visits
    visits.clear()
    expired[0] = True
    work = LedgerWork()
    with pytest.raises(MigrationRefused, match="^migration_busy$"):
        validate_ledger_chain(cursors, opening, check=work.check)
    assert len(visits) == 1
    # Identical observations without a callback retain the old pure behavior.
    assert validate_ledger_chain(cursors, opening) == expected


def test_expiry_during_period_lookup_refuses_before_insertion(monkeypatch, cohort):
    cursors, opening = cohort
    target = cursors[-1].manifest.accounts[-1]
    clock = [0.0]
    comparisons = []
    searches = []
    projections = []
    expire = [False]
    original = LedgerAccount.__getattribute__
    original_dump = LedgerAccount.model_dump
    search = ledger_state.bisect_left
    monkeypatch.setattr(ledger_work, "monotonic", lambda: clock[0])

    class ObservedStart(str):
        def __gt__(self, other):
            result = super().__gt__(other)
            comparisons.append(other)
            if expire[0]:
                clock[0] = 121.0
            return result

    def observed(self, name):
        result = original(self, name)
        if self is target and name == "period_start":
            return ObservedStart(result)
        return result

    def searched(intervals, period):
        result = search(intervals, period)
        if isinstance(period[0], ObservedStart):
            searches.append((intervals, len(intervals)))
        return result

    def dumped(self, *args, **kwargs):
        if self is target:
            projections.append(self.id)
        return original_dump(self, *args, **kwargs)

    monkeypatch.setattr(LedgerAccount, "__getattribute__", observed)
    monkeypatch.setattr(LedgerAccount, "model_dump", dumped)
    monkeypatch.setattr(ledger_state, "bisect_left", searched)
    expected = validate_ledger_chain(cursors, opening, check=LedgerWork().check)
    assert len(searches) == 1 and projections == [target.id]
    assert 1 <= len(comparisons) <= searches[0][1].bit_length()
    assert len(searches[0][0]) == searches[0][1] + 1
    comparisons.clear()
    searches.clear()
    projections.clear()
    expire[0] = True
    work = LedgerWork()
    with pytest.raises(MigrationRefused, match="^migration_busy$"):
        validate_ledger_chain(cursors, opening, check=work.check)
    assert len(searches) == 1 and not projections
    assert 1 <= len(comparisons) <= searches[0][1].bit_length()
    assert len(searches[0][0]) == searches[0][1]
    # Expiry during a bounded search is observed after it, before insertion.
    # Pure validation without an injected deadline retains the same receipt.
    assert validate_ledger_chain(cursors, opening, check=None) == expected


def test_expiry_inside_original_opening_job_walk_stops_next_job(monkeypatch):
    raw = manifest(projects=15, jobs=48)
    cursors, opening = parsed([raw], opening_for(raw))
    clock = [0.0]
    visits = []
    expire = [False]
    original = OpeningJob.__getattribute__
    monkeypatch.setattr(ledger_work, "monotonic", lambda: clock[0])

    def observed(self, name):
        result = original(self, name)
        if name == "job_id":
            visits.append(result)
            if expire[0]:
                clock[0] = 121.0
        return result

    monkeypatch.setattr(OpeningJob, "__getattribute__", observed)
    expected = validate_ledger_chain(cursors, opening, check=LedgerWork().check)
    assert len(set(visits)) == 48
    visits.clear()
    expire[0] = True
    work = LedgerWork()
    with pytest.raises(MigrationRefused, match="^migration_busy$"):
        validate_ledger_chain(cursors, opening, check=work.check)
    assert len(visits) == 1
    assert validate_ledger_chain(cursors, opening) == expected


def test_history_threads_check_only_callback_but_public_inspector_still_refuses(
    tmp_path, monkeypatch
):
    from ledger_reader_fixture import complete_ar6, seed_ar7

    from agent_rewind.migrations import ledger_reader_history
    from agent_rewind.migrations.ledger_inspection import inspect_ledger_state
    from agent_rewind.migrations.ledger_reader_catalog import inspect_catalog
    from agent_rewind.migrations.schema import LEDGER

    case = seed_ar7(complete_ar6(tmp_path / "history.sqlite"))
    checker = CheckOnly()
    received = []
    original = ledger_reader_history.validate_ledger_chain

    def checked(manifests, opening, *, check=None):
        assert check == checker.check
        received.append(check)
        return original(manifests, opening, check=check)

    monkeypatch.setattr(ledger_reader_history, "validate_ledger_chain", checked)
    try:
        with case.engine.connect() as connection:
            shape = inspect_catalog(connection, LEDGER, checker)
            history = ledger_reader_history.read_history(connection, LEDGER, shape, checker)
            assert len(history.manifests) == 1
            assert history.opening is not None
            assert received == [checker.check]
            assert checker.calls > 0
            with pytest.raises(MigrationRefused, match="^transactional_connection_required$"):
                inspect_ledger_state(connection)
    finally:
        case.engine.dispose()
