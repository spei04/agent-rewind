"""Deterministic drain-observer behavior without a local database server."""

from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from postgres_control import wait_for_database_drain


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
