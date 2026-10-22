"""Independent native SQLite observations for the dormant operator seam."""

import sqlite3
import sys
from types import SimpleNamespace

import pytest

from agent_rewind.migrations.ledger_engine import create_ledger_engine

_CONNECT = sqlite3.connect


def proof_rows(path):
    # A separate native connection, outside the command engine and its fault spies.
    with _CONNECT(path) as connection:
        return [row[0] for row in connection.execute("SELECT id FROM proof ORDER BY id")]


class SQLiteTrace:
    def __init__(self):
        self.events = []
        self.raws = []
        self.phase = "bootstrap"
        self.previous_profile = None

    def connect(self, *args, **kwargs):
        self.events.append(("connect_attempt", self.phase))
        raw = _CONNECT(*args, **kwargs)
        self.raws.append(raw)
        self.events.append(("connect_return", self.phase, id(raw)))
        raw.set_trace_callback(lambda sql: self.events.append(("sql", self.phase, id(raw), sql)))
        return raw

    def profile(self, frame, event, function):
        if event in {"c_call", "c_return", "c_exception"}:
            target = getattr(function, "__self__", None)
            if isinstance(target, sqlite3.Cursor):
                raw = target.connection
            elif isinstance(target, sqlite3.Connection):
                raw = target
            else:
                raw = None
            name = getattr(function, "__name__", "")
            if (
                raw is not None
                and any(raw is owned for owned in self.raws)
                and name
                in {
                    "execute",
                    "executemany",
                    "commit",
                    "rollback",
                    "close",
                    "create_function",
                    "set_progress_handler",
                }
            ):
                self.events.append((event, self.phase, id(raw), name))
        if self.previous_profile is not None:
            self.previous_profile(frame, event, function)

    def sql(self, start=0):
        return [event[3] for event in self.events[start:] if event[0] == "sql"]

    def calls(self, name, start=0):
        return [event for event in self.events[start:] if event[0] == "c_call" and event[3] == name]


@pytest.fixture
def ledger_case(tmp_path, monkeypatch):
    path = tmp_path / "ledger-boundary.sqlite"
    with _CONNECT(path) as raw:
        raw.execute("CREATE TABLE proof (id INTEGER PRIMARY KEY)")
    trace = SQLiteTrace()
    monkeypatch.setattr(sqlite3, "connect", trace.connect)
    trace.previous_profile = sys.getprofile()
    sys.setprofile(trace.profile)
    engine = None
    try:
        engine = create_ledger_engine(f"sqlite:///{path}")
        yield SimpleNamespace(path=path, engine=engine, trace=trace)
    finally:
        try:
            if engine is not None:
                engine.dispose()
        finally:
            sys.setprofile(trace.previous_profile)


def assert_pool_released(case):
    assert case.engine.pool.checkedout() == 0


def assert_closed(raw):
    with pytest.raises(sqlite3.ProgrammingError):
        raw.execute("SELECT 1")
