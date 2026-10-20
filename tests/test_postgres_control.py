"""Deterministic drain-observer behavior without a local database server."""

import json
import traceback
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from postgres_control import observe_exclusion_failure, wait_for_database_drain

from agent_rewind.migrations.schema import MigrationRefused


class Control:
    url = SimpleNamespace(database="control")

    def __init__(self, observations):
        self.observations = iter(observations)
        self.reads = 0

    def connect(self):
        return self

    def execution_options(self, **options):
        assert options == {"isolation_level": "AUTOCOMMIT"}
        return nullcontext(self)

    def exec_driver_sql(self, statement):
        assert statement == "SET statement_timeout = '1s'"

    def execute(self, statement, parameters):
        assert parameters == {"database": "target"}
        self.reads += 1
        rows = next(self.observations)
        return SimpleNamespace(all=lambda: rows)


def test_drain_requires_fresh_observed_absence(monkeypatch):
    control = Control([[(11,)], [(11,), (12,)], []])
    pauses = []
    monkeypatch.setattr("postgres_control.time.sleep", pauses.append)
    wait_for_database_drain(control, "target")
    assert control.reads == 3 and len(pauses) == 2


def test_deadline_never_turns_a_live_session_into_success(monkeypatch):
    control = Control([[(11,)]])
    clock = iter([1.0, 2.0])
    monkeypatch.setattr("postgres_control.time.monotonic", lambda: next(clock))
    with pytest.raises(AssertionError, match="did not drain before deadline"):
        wait_for_database_drain(control, "target", timeout=0.5)
    assert control.reads == 1


def test_observer_cannot_connect_to_the_database_it_is_draining():
    with pytest.raises(ValueError, match="Invalid synthetic"):
        wait_for_database_drain(Control([]), "control")


class RefusalConnection:
    def __init__(self, rows=(), fail_at=None):
        self.rows = rows
        self.fail_at = fail_at
        self.statements = []
        self.fetch_limits = []
        self.snapshot_closed = False

    def exec_driver_sql(self, statement):
        self.statements.append(statement)
        if self.fail_at == "timeout":
            raise RuntimeError("PRIVATE diagnostic timeout marker")
        assert statement in {
            "SET LOCAL statement_timeout = '1s'",
            "SELECT pg_catalog.pg_stat_clear_snapshot()",
        }
        if "clear_snapshot" in statement:
            if self.fail_at == "snapshot":
                raise RuntimeError("PRIVATE diagnostic snapshot marker")
            return SimpleNamespace(close=lambda: setattr(self, "snapshot_closed", True))

    def execute(self, statement):
        self.statements.append(str(statement))
        assert str(statement) == (
            "SELECT backend_type,state FROM pg_catalog.pg_stat_activity "
            "WHERE datname=pg_catalog.current_database() "
            "AND pid<>pg_catalog.pg_backend_pid() LIMIT 9"
        )
        if self.fail_at == "query":
            raise RuntimeError("PRIVATE diagnostic query marker")
        return SimpleNamespace(fetchmany=self.fetchmany)

    def fetchmany(self, limit):
        self.fetch_limits.append(limit)
        if self.fail_at == "fetch":
            raise RuntimeError("PRIVATE diagnostic fetch marker")
        return self.rows[:limit]


def refusal_check(refused, calls):
    def check(connection, tables):
        calls.append((connection, tables))
        raise refused

    return check


def test_post_refusal_observation_is_later_bounded_and_allowlisted():
    connection = RefusalConnection(
        [("client backend", "idle"), (None, None), ("PRIVATE backend", "PRIVATE state")]
        + [("parallel worker", "active")] * 7
    )
    original = MigrationRefused("writers_not_drained")
    calls, tables = [], ["records"]
    with pytest.raises(MigrationRefused) as captured:
        observe_exclusion_failure(refusal_check(original, calls), connection, tables)
    assert captured.value is original
    assert calls == [(connection, tables)]
    assert connection.snapshot_closed
    assert connection.fetch_limits == [9]
    (note,) = original.__notes__
    label, payload = note.split("=", 1)
    assert label == "post_refusal_backend_observation"
    observation = json.loads(payload)
    assert observation["more_than_eight"] is True
    assert len(observation["rows"]) == 8
    assert observation["rows"][:3] == [
        {"backend_type": "client backend", "state": "idle"},
        {"backend_type": None, "state": None},
        {"backend_type": "other", "state": "other"},
    ]
    assert "PRIVATE" not in note
    assert all(set(row) == {"backend_type", "state"} for row in observation["rows"])


def test_post_refusal_observation_may_find_no_remaining_backend():
    connection = RefusalConnection()
    original = MigrationRefused("writers_not_drained")
    with pytest.raises(MigrationRefused) as captured:
        observe_exclusion_failure(refusal_check(original, []), connection, [])
    assert captured.value is original
    assert json.loads(original.__notes__[0].split("=", 1)[1]) == {
        "rows": [],
        "more_than_eight": False,
    }


@pytest.mark.parametrize("fail_at", ["timeout", "snapshot", "query", "fetch"])
def test_diagnostic_failure_preserves_original_refusal_without_error_text(fail_at):
    connection = RefusalConnection(fail_at=fail_at)
    original = MigrationRefused("writers_not_drained")
    calls = []
    with pytest.raises(MigrationRefused) as captured:
        observe_exclusion_failure(refusal_check(original, calls), connection, [])
    assert captured.value is original
    assert len(calls) == 1
    assert original.__notes__ == ["post_refusal_backend_observation=unavailable"]
    assert str(original) == "writers_not_drained"
    assert "PRIVATE" not in "".join(traceback.format_exception(captured.value))


@pytest.mark.parametrize("refusal", [None, "migration_owner_required", "writer_privileges_present"])
def test_success_and_other_refusals_do_not_observe_or_retry(refusal):
    connection = RefusalConnection()
    calls, tables = [], ["records"]
    original = MigrationRefused(refusal) if refusal else None

    def check(actual_connection, actual_tables):
        calls.append((actual_connection, actual_tables))
        if original is not None:
            raise original

    if original is None:
        assert observe_exclusion_failure(check, connection, tables) is None
    else:
        with pytest.raises(MigrationRefused) as captured:
            observe_exclusion_failure(check, connection, tables)
        assert captured.value is original
        assert not hasattr(original, "__notes__")
    assert calls == [(connection, tables)]
    assert connection.statements == []
