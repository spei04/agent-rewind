"""P2 opt-in work/lock semantics preserve the existing defaults."""

from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql
from test_admission_transaction import engine, rows

from agent_rewind import operation_work, scoped_locks
from agent_rewind.admission_transaction import (
    AdmissionError,
    TransactionOutcome,
    admission_transaction,
)
from agent_rewind.operation_work import OperationWork
from agent_rewind.request_identity import VerifiedPrincipal
from agent_rewind.reservation_checks import (
    SourceStats,
    database_tick,
    lease_live,
    money_total,
    new_lease,
    require_budget,
    require_source_headroom,
    require_window,
    utc_microseconds,
    window_on_grid,
)
from agent_rewind.reservation_types import MAX_MONEY, ReservationRefusal
from agent_rewind.scoped_repositories import ProjectContext

__all__ = ["engine"]


@pytest.mark.parametrize("include", [False, True], ids=["existing", "acquisition-inclusive"])
def test_acquisition_clock_is_opt_in_and_does_not_reset_on_attach(engine, monkeypatch, include):
    clock = [0.0]
    monkeypatch.setattr(operation_work, "perf_counter", lambda: clock[0])
    work = OperationWork(include_acquisition=include)
    clock[0] = 9.5
    outcome = TransactionOutcome()
    if include:
        with (
            pytest.raises(AdmissionError, match="^dependency_unavailable$"),
            admission_transaction(engine, outcome, work=work) as connection,
        ):
            connection.exec_driver_sql("INSERT INTO proof VALUES(1)")
            clock[0] = 10.0
        assert outcome.confirmed_precommit_rollback and rows(engine) == []
    else:
        with admission_transaction(engine, outcome, work=work) as connection:
            connection.exec_driver_sql("INSERT INTO proof VALUES(1)")
            clock[0] = 10.0
        assert outcome.commit_acknowledged and rows(engine) == [1]


def test_expired_acquisition_budget_never_enters_a_transaction(engine, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(operation_work, "perf_counter", lambda: clock[0])
    work = OperationWork(include_acquisition=True)
    clock[0] = 10.0
    outcome = TransactionOutcome()
    with (
        pytest.raises(AdmissionError, match="^dependency_unavailable$"),
        admission_transaction(engine, outcome, work=work),
    ):
        pytest.fail("body")
    assert not outcome.begun and not outcome.commit_attempted
    assert engine.pool.checkedout() == 0


@pytest.mark.parametrize("exclusive", [False, True], ids=["default-share", "initial-update"])
def test_authority_lock_order_and_first_organization_mode(monkeypatch, exclusive):
    observed = []
    principal = VerifiedPrincipal("oidc:" + "a" * 64)
    context = ProjectContext("1" * 32, "2" * 32, principal.principal_id)
    authority = SimpleNamespace(check=lambda *args, **kwargs: observed.append(("visibility", None)))

    def lock(_connection, statement, *, shared):
        sql = str(statement.with_for_update(read=shared).compile(dialect=postgresql.dialect()))
        observed.append((str(statement.get_final_froms()[0]), sql))

    monkeypatch.setattr(scoped_locks, "_lock_row", lock)
    scoped_locks.lock_authority(
        authority,
        object(),
        principal,
        context,
        "job",
        "3" * 32,
        exclusive_organization=exclusive,
    )
    assert [table for table, _sql in observed] == [
        "visibility",
        "projects",
        "organizations",
        "project_memberships",
        "resource_scopes",
        "jobs",
    ]
    assert observed[1][1].endswith("FOR UPDATE")
    assert observed[2][1].endswith("FOR UPDATE" if exclusive else "FOR SHARE")
    assert observed[3][1].endswith("FOR SHARE")
    assert observed[5][1].endswith("FOR UPDATE")


def test_money_remains_exact_above_float_precision_and_at_signed64_limit():
    assert money_total([2**53, 1]) == 2**53 + 1
    assert money_total([MAX_MONEY - 1, 1]) == MAX_MONEY
    require_budget(MAX_MONEY - 1, 1, MAX_MONEY)
    with pytest.raises(ReservationRefusal) as caught:
        require_budget(MAX_MONEY, 1, MAX_MONEY)
    assert caught.value.reason == "budget_exceeded"
    # Valid older holds can exceed a smaller current limit after rollover.
    with pytest.raises(ReservationRefusal) as caught:
        require_budget(10, 0, 9)
    assert caught.value.reason == "budget_exceeded"


@pytest.mark.parametrize(
    "values",
    [[True], [1.0], [-1], [MAX_MONEY, 1], [MAX_MONEY + 1]],
    ids=["bool", "float", "negative", "sum-overflow", "cell-overflow"],
)
def test_invalid_native_money_is_never_coerced(values):
    with pytest.raises(ReservationRefusal) as caught:
        money_total(values)
    assert caught.value.reason == "ledger_state_invalid"


def source_receipts():
    return {
        "api_keys": SourceStats(0, 0, 0),
        "audit": SourceStats(0, 0, 0),
        "events": SourceStats(0, 0, 0),
        "jobs": SourceStats(1, 256, 256),
        "records": SourceStats(0, 0, 0),
    }


def test_source_headroom_accepts_small_native_state_and_refuses_oversize_canonical_row():
    receipts = source_receipts()
    require_source_headroom(receipts, prospective_job_growth=True)
    receipts["records"] = SourceStats(1, 1_000_000, 1_000_000)
    with pytest.raises(ReservationRefusal) as caught:
        require_source_headroom(receipts, prospective_job_growth=False)
    assert caught.value.reason == "capacity_exceeded"


@pytest.mark.parametrize(
    "stats",
    [
        SourceStats(True, 0, 0),
        SourceStats(1, -1, 0),
        SourceStats(0, 1, 1),
        SourceStats(1, 2, 1),
        SourceStats(2, 1, 2),
    ],
    ids=["bool-count", "negative", "empty-nonzero", "sum-max-mismatch", "max-above-sum"],
)
def test_source_receipts_must_prove_consistent_complete_native_counts(stats):
    receipts = source_receipts()
    receipts["records"] = stats
    with pytest.raises(ReservationRefusal) as caught:
        require_source_headroom(receipts, prospective_job_growth=False)
    assert caught.value.reason == "ledger_state_invalid"


def test_source_receipts_cannot_omit_an_original_table():
    receipts = source_receipts()
    del receipts["audit"]
    with pytest.raises(ReservationRefusal) as caught:
        require_source_headroom(receipts, prospective_job_growth=False)
    assert caught.value.reason == "ledger_state_invalid"


@pytest.mark.parametrize(
    ("dialect", "sample", "expected"),
    [
        ("postgresql", "1970-01-01T00:00:00.000001Z", 1),
        ("sqlite", "1970-01-01T00:00:00.001Z", 1000),
        ("postgresql", "1969-12-31T23:59:59.999999Z", -1),
        ("sqlite", "1969-12-31T23:59:59.999Z", -1000),
    ],
    ids=["pg-microsecond", "sqlite-millisecond", "pg-before-epoch", "sqlite-before-epoch"],
)
def test_database_clock_decodes_integer_ticks_without_float_rounding(dialect, sample, expected):
    assert database_tick(sample, dialect) == expected


@pytest.mark.parametrize(
    ("dialect", "sample"),
    [
        ("sqlite", "1970-01-01T00:00:00.000001Z"),
        ("postgresql", "1970-02-30T00:00:00.000000Z"),
        ("postgresql", "1970-01-01T00:00:00.000000+00:00"),
        ("postgresql", "1970-01-01T00:00:00.000000Z\n"),
    ],
    ids=["false-sqlite-precision", "invalid-calendar", "noncanonical-zone", "trailing-text"],
)
def test_invalid_database_clock_observation_is_not_an_eligibility_result(dialect, sample):
    with pytest.raises(ReservationRefusal) as caught:
        database_tick(sample, dialect)
    assert caught.value.reason == "ledger_state_invalid"


def test_half_open_windows_round_inward_on_sqlite_grid():
    start, end = "1970-01-01T00:00:00.000001Z", "1970-01-01T00:00:00.002999Z"
    assert window_on_grid(start, end, "sqlite") == (1000, 2000)
    require_window(1000, start, end, "sqlite")
    for now in (0, 2000):
        with pytest.raises(ReservationRefusal) as caught:
            require_window(now, start, end, "sqlite")
        assert caught.value.reason == "job_not_live"
    require_window(1, start, end, "postgresql")
    require_window(2998, start, end, "postgresql")


def test_unrepresentable_short_window_is_not_extended():
    start, end = "1970-01-01T00:00:00.000001Z", "1970-01-01T00:00:00.000999Z"
    with pytest.raises(ReservationRefusal) as caught:
        require_window(0, start, end, "sqlite")
    assert caught.value.reason == "job_not_live"


@pytest.mark.parametrize(
    "sample",
    [
        "1970-01-01T00:00:00.000001Z",
        "2026-10-28T23:59:59.123456Z",
        "2100-01-01T00:00:00.999999Z",
    ],
    ids=["epoch", "ordinary", "far-window"],
)
def test_new_lease_never_exceeds_exact_window_and_stays_strictly_live(sample):
    now = utc_microseconds(sample)
    target = now + 12345
    value = new_lease(now, 60, target)
    numerator, denominator = value.as_integer_ratio()
    assert numerator * 1_000_000 <= target * denominator
    assert lease_live(value, now)
    assert not lease_live(value, target)
    assert not lease_live(None, now)


def test_native_integer_lease_comparison_never_converts_money_sized_value_to_float():
    assert lease_live(MAX_MONEY, MAX_MONEY * 1_000_000 - 1)
    assert not lease_live(MAX_MONEY, MAX_MONEY * 1_000_000)
    for value in (True, float("nan"), float("inf"), 10**1000):
        with pytest.raises(ReservationRefusal) as caught:
            lease_live(value, 0)
        assert caught.value.reason == "ledger_state_invalid"
