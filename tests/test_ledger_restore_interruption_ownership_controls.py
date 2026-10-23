"""Offline ownership, closure-handshake, and actual finalizer controls."""

import json
from types import SimpleNamespace

import ledger_restore_interruption_control as capability
import ledger_restore_postgres_fixture as restore_fixture
import pytest
import test_ledger_recovery_restore_interrupted_postgres as native
import test_migrations_postgres as migration_fixture
from ledger_restore_interruption_ownership import InterruptedOwnership
from ledger_restore_tool_ownership import ToolOwnership, install_tool_guard
from sqlalchemy import Engine, create_engine
from test_ledger_restore_controls import source_fixture
from test_ledger_restore_interruption_wire_controls import control
from test_ledger_restore_tool_ownership_controls import Child, Database


@pytest.mark.parametrize(
    "failure",
    [
        None,
        "rollback",
        "blocker-close",
        "blocker-absence",
        "control-close",
        "construct-final",
        "final-query",
        "final-close",
        "final-record",
    ],
)
def test_final_handshake_keeps_fence_continuous_at_every_interruption(monkeypatch, failure):
    value = control(monkeypatch)
    value.prepared = value.cancel_attempted = value.cancel_ack = value.restore_absent = True
    value.cleanup_deadline = 140
    child = Child(1)
    value.owner.children.append(child)
    value.child = child
    value.control_identity = {"pid": b"11", "started": b"original"}
    value.blocker_identity = {"pid": b"12", "started": b"blocker"}
    first, injected = RuntimeError("restore tool failed"), KeyboardInterrupt("closure interrupted")
    value.owner.remember(first)
    calls = []

    def point(name):
        calls.append(name)
        assert not value.completed and not value.owner.resolved()
        if name == failure:
            raise injected

    class Channel:
        def __init__(self, name):
            self.name, self.closed = name, False
            self.raw = SimpleNamespace(backend_pid=44, db=b"postgres", user=b"postgres")

        def close(self):
            point(self.name + "-close")
            self.closed = True

    value.control, value.blocker = Channel("control"), Channel("blocker")
    value.channels = [value.control, value.blocker]
    value.constructions = 2
    original_record = value.record

    def record(event):
        if "final_observer_complete" in event:
            point("final-record")
        original_record(event)

    def query(channel, name, parameters, deadline, **kwargs):
        if name == "final-absence":
            point("final-query")
            assert deadline == 103.5 and len(parameters) == 5
            return [{"control": b"0", "restores": b"0", "targets": b"0", "observer": b"44"}]
        point(name)
        assert deadline == 140
        return [] if name == "rollback" else [{"remaining": b"0"}]

    def constructor(info, **kwargs):
        point("construct-final")
        assert value.constructions == 3 and value.pending_connections == 1
        assert kwargs["deadline"] == 103
        return Channel("final")

    monkeypatch.setattr(value, "query", query)
    monkeypatch.setattr(value, "record", record)
    monkeypatch.setattr(capability, "Channel", constructor)
    monkeypatch.setattr(value, "pump", lambda *a, **kw: None)
    if failure is None:
        value.finish()
        assert value.completed and value.owner.resolved() and value.constructions == 3
        assert value.channels[-1].closed
        assert value.events[-1]["own_server_disappearance_claimed"] is False
    else:
        with pytest.raises(KeyboardInterrupt) as caught:
            value.finish()
        assert caught.value is injected
        assert not value.completed and not value.owner.resolved()
        with pytest.raises(RuntimeError) as blocked:
            value.owner.before_database("fixture-teardown")
        assert blocked.value is first
    assert calls[:1] == ["rollback"]


@pytest.mark.parametrize(
    "result",
    [
        {"control": b"1", "restores": b"0", "targets": b"0", "observer": b"44"},
        {"control": b"0", "restores": b"1", "targets": b"0", "observer": b"44"},
        {"control": b"0", "restores": b"0", "targets": b"1", "observer": b"44"},
        {"control": b"0", "restores": b"0", "targets": b"0", "observer": b"45"},
    ],
)
def test_final_observer_cannot_discharge_fence_with_remaining_or_wrong_backend(monkeypatch, result):
    value = control(monkeypatch)
    value.prepared = value.cancel_attempted = value.cancel_ack = value.restore_absent = True
    value.cleanup_deadline = 140
    child = Child(1)
    value.owner.children.append(child)
    value.child = child
    value.control_identity = value.blocker_identity = {"pid": b"11", "started": b"stamp"}
    channel = SimpleNamespace(
        close=lambda: None, raw=SimpleNamespace(backend_pid=44, db=b"postgres", user=b"postgres")
    )
    value.control = value.blocker = channel
    monkeypatch.setattr(value, "connect", lambda *a, **kw: channel)
    monkeypatch.setattr(
        value,
        "query",
        lambda ch, name, *a, **kw: result and [result]
        if name == "final-absence"
        else []
        if name == "rollback"
        else [{"remaining": b"0"}],
    )
    with pytest.raises(AssertionError):
        value.finish()
    assert not value.completed and not value.owner.resolved()


def install(monkeypatch):
    database = Database()
    monkeypatch.setattr(Engine, "connect", lambda engine, *a, **kw: database.connect(engine))
    owner = InterruptedOwnership(lambda *a, **kw: Child(0), lambda *a, **kw: None)
    install_tool_guard(monkeypatch, native, owner=owner)
    return database, owner


def latch(owner, terminal):
    owner.children = [Child(0) for _ in range(4)]
    state = SimpleNamespace(completed=terminal, uncertain=False, report=lambda: {})
    owner.bind_control(state)
    error = TimeoutError("control backend uncertainty")
    owner.remember(error)
    return error


@pytest.mark.parametrize("terminal", [False, True])
def test_actual_pg_finalizer_waits_for_control_backend_fence(monkeypatch, terminal):
    database, owner = install(monkeypatch)
    monkeypatch.setattr(migration_fixture, "POSTGRES", "postgresql+psycopg://postgres@/postgres")
    generator = migration_fixture.pg.__wrapped__(monkeypatch)
    next(generator)
    first = latch(owner, terminal)
    database.calls.clear()
    if terminal:
        generator.close()
        assert any(
            kind == "sql" and sql.startswith("DROP DATABASE") for kind, sql in database.calls
        )
    else:
        with pytest.raises(TimeoutError) as caught:
            generator.close()
        assert caught.value is first and database.calls == []


@pytest.mark.parametrize("terminal", [False, True])
def test_actual_empty_target_finalizer_waits_for_control_backend_fence(
    monkeypatch, tmp_path, terminal
):
    database, owner = install(monkeypatch)
    token = "ar_migration_" + "a" * 32
    pg = {
        name: create_engine(
            "postgresql+psycopg://postgres@/" + ("postgres" if name == "control" else token)
        )
        for name in ("control", "owner", "app", "admin")
    }
    pg["owner_role"] = token + "_owner"
    with (
        pytest.raises(TimeoutError) as caught,
        restore_fixture.empty_target(source_fixture(), pg, tmp_path, lambda *a: None),
    ):
        first = latch(owner, terminal)
        database.calls.clear()
        raise first
    assert caught.value is first
    record = json.loads((tmp_path / "target-cleanup.json").read_text())
    assert record["absence_observed"] is terminal
    if terminal:
        assert any(
            kind == "sql" and sql.startswith("DROP DATABASE") for kind, sql in database.calls
        )
    else:
        assert database.calls == []
        assert {row["phase"] for row in record["errors"]} == {"drain-target", "drop-target"}


def test_five_tool_profile_is_explicit_and_default_limit_stays_four(monkeypatch):
    value = control(monkeypatch)
    assert ToolOwnership(None, None).tool_limit == 4 and value.owner.tool_limit == 5
    value.prepared = True
    child = Child(1)
    value.owner.popen = lambda *a, **kw: child
    assert value.owner.spawn_data(["fixed"], {}) is child
    assert len(value.owner.children) == 5 and value.owner.steps[0]["label"] == "data-restore"
    assert not value.owner.resolved()
    with pytest.raises(AssertionError):
        value.owner.spawn_data(["sixth"], {})
    with pytest.raises(AssertionError):
        value.owner.run_tool(["sixth"], label="dump", env={})
    assert len(value.owner.children) == 5


def test_new_autouse_fixture_outlives_pg_and_legacy_teardown(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(Engine, "connect", lambda *a, **kw: None)
    probe = tmp_path / "test_interrupted_order.py"
    output = tmp_path / "order.json"
    probe.write_text(
        "import json\nfrom pathlib import Path\nfrom types import SimpleNamespace\n"
        "import pytest\nfrom sqlalchemy import Engine\nfrom ledger_restore_tools import run_tool\n"
        "from test_ledger_recovery_restore_interrupted_postgres import interrupted_tool_ownership\n"
        "events=[]\n"
        "@pytest.fixture\ndef pg(request):\n"
        " owner=request.getfixturevalue('interrupted_tool_ownership')\n"
        " events.append('pg-setup')\n yield owner\n"
        " events.append('pg-teardown')\n"
        " try: Engine.connect(object.__new__(Engine))\n"
        " except TimeoutError as e: assert e is owner.first_error\n"
        " else: raise AssertionError('unsafe delegation')\n"
        "@pytest.fixture\ndef legacy(pg):\n"
        " events.append('legacy-setup')\n yield pg\n events.append('legacy-teardown')\n"
        "def test_body(legacy):\n"
        " owner=legacy\n"
        " class Child:\n  pid=123\n  def poll(self): return 0\n"
        " owner.children=[Child() for _ in range(4)]\n"
        " owner.bind_control(SimpleNamespace(completed=False,uncertain=True,report=lambda:{}))\n"
        " owner.remember(TimeoutError('control-fence-original'))\n events.append('body')\n"
        "@pytest.fixture(autouse=True)\ndef events_record():\n yield\n"
        " Path(" + repr(str(output)) + ").write_text(json.dumps(events))\n"
    )
    code = pytest.main(
        [str(probe), "-q", "-p", "no:cacheprovider", "--basetemp=" + str(tmp_path / "nested")]
    )
    text = capsys.readouterr().out
    assert code == 1 and "control-fence-original" in text, text
    assert json.loads(output.read_text()) == [
        "pg-setup",
        "legacy-setup",
        "body",
        "legacy-teardown",
        "pg-teardown",
    ]
    record = json.loads(next((tmp_path / "nested").rglob("tool-ownership.json")).read_text())
    assert not record["resolved"] and record["limits"]["tools"] == 5
