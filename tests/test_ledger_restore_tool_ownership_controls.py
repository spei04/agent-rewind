"""No-I/O controls for real tool handles and the actual fixture teardown boundaries."""

import json
from dataclasses import replace
from pathlib import Path

import ledger_restore_postgres_fixture as restore_fixture
import ledger_restore_tools as tools
import pytest
import test_ledger_recovery_restore_truncated_postgres as native
import test_migrations_postgres as migration_fixture
from ledger_restore_tool_ownership import ToolOwnership, install_tool_guard
from sqlalchemy import Connection, Engine, create_engine
from test_ledger_restore_controls import fake_tools, source_fixture


class Child:
    pid = 12345

    def __init__(self, code=None, error=None):
        self.code, self.error, self.polls = code, error, 0

    def poll(self):
        self.polls += 1
        if self.error is not None:
            raise self.error
        return self.code


@pytest.mark.parametrize("boundary", ["connect", "raw_connection", "execute", "exec_driver_sql"])
@pytest.mark.parametrize("code", [None, 0, 1, -9])
def test_each_actual_sqlalchemy_boundary_requires_terminal_owned_handle(
    monkeypatch, boundary, code
):
    calls = []
    kind = Engine if boundary in {"connect", "raw_connection"} else Connection
    monkeypatch.setattr(kind, boundary, lambda *args, **kwargs: calls.append("delegate"))
    monkeypatch.setattr(tools.subprocess, "Popen", lambda *args, **kwargs: Child(code))
    owner = install_tool_guard(monkeypatch, native)
    owner.spawn(["owned-tool"])
    receiver = object.__new__(kind)
    if code is None:
        with pytest.raises(AssertionError, match="ownership"):
            getattr(receiver, boundary)()
        assert calls == [] and not owner.report()["resolved"]
    else:
        getattr(receiver, boundary)()
        assert calls == ["delegate"] and owner.report()["resolved"]


@pytest.mark.parametrize("where", ["constructor", "poll"])
def test_uncertainty_is_sticky_and_preserves_first_exception_identity(where):
    original = KeyboardInterrupt("first")

    def fail(*args, **kwargs):
        raise original

    child = Child(error=original if where == "poll" else None)
    owner = ToolOwnership(fail if where == "constructor" else lambda *a: child, fail)
    if where == "constructor":
        with pytest.raises(KeyboardInterrupt) as caught:
            owner.spawn(["owned"])
        assert caught.value is original and owner.pending
    else:
        owner.spawn(["owned"])
        with pytest.raises(KeyboardInterrupt) as caught:
            owner.before_database("source capture")
        assert caught.value is original
        child.error, child.code = None, 0
    with pytest.raises(KeyboardInterrupt) as caught:
        owner.before_database("fixture teardown")
    assert caught.value is original and owner.uncertain and not owner.report()["resolved"]


def test_all_handles_remain_bound_and_next_launch_cannot_overlap():
    children = [Child(0), Child(1), Child(-9), Child()]
    iterator = iter(children)
    owner = ToolOwnership(lambda *args: next(iterator), lambda: None)
    for _ in range(4):
        owner.spawn(["tool"])
    assert owner.children == children
    with pytest.raises(AssertionError, match="ownership"):
        owner.spawn(["not launched"])
    children[-1].code = 0
    assert owner.resolved()
    with pytest.raises(AssertionError, match="launch bound"):
        owner.spawn(["fifth"])
    assert len(owner.children) == 4


@pytest.mark.parametrize("receipt", ["missing", "misleading"])
def test_live_handle_blocks_even_without_receipt_or_with_false_reaped_claim(
    monkeypatch, tmp_path, receipt
):
    original = TimeoutError("first tool failure")
    child = Child()
    owner = ToolOwnership(lambda *args: child, lambda *args: None)
    owner.spawn(["owned"])
    owner.remember(original)
    if receipt == "misleading":
        (tmp_path / "tool.json").write_text(json.dumps({"reaped": True, "returncode": 0}))
    with pytest.raises(TimeoutError) as caught:
        owner.before_database("target drop")
    assert caught.value is original and not owner.resolved()


def test_interrupted_actual_runner_receipt_cannot_authorize_unreaped_tool(monkeypatch, tmp_path):
    process, _ = fake_tools(monkeypatch, {}, interruption=KeyboardInterrupt("first"), hang=True)
    process.kill = lambda: process.actions.append(("kill-without-ack",))
    original_open = Path.open

    def open_file(path, *args, **kwargs):
        if path.name == "missing.json":
            raise OSError("receipt unavailable")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_file)
    owner = install_tool_guard(monkeypatch, native)
    with pytest.raises(KeyboardInterrupt) as caught:
        owner.run_tool(["tool"], tmp_path, label="missing", env={})
    original = caught.value
    assert not (tmp_path / "missing.json").exists()
    assert owner.children == [process] and not owner.resolved()
    with pytest.raises(KeyboardInterrupt) as blocked:
        Engine.connect(object.__new__(Engine))
    assert blocked.value is original and owner.first_error is original


@pytest.mark.parametrize("code", [0, 1])
def test_actual_runner_confirmed_exit_preserves_normal_database_delegation(
    monkeypatch, tmp_path, code
):
    process, _ = fake_tools(monkeypatch, {100: [b""], 101: [b""]}, code=code)
    calls = []
    monkeypatch.setattr(Engine, "connect", lambda *args: calls.append("database"))
    owner = install_tool_guard(monkeypatch, native)
    if code:
        with pytest.raises(RuntimeError) as caught:
            owner.run_tool(["tool"], tmp_path, label="terminal", env={})
        assert owner.first_error is caught.value
    else:
        owner.run_tool(["tool"], tmp_path, label="terminal", env={})
    Engine.connect(object.__new__(Engine))
    assert calls == ["database"] and process.poll() == code and owner.resolved()


class Database:
    """Controlled delegates let actual fixture generators reach their finalizers."""

    def __init__(self):
        self.calls = []

    def connect(self, engine, *args, **kwargs):
        self.calls.append(("connect", engine.url.database))
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def begin(self):
        return self

    def execution_options(self, **kwargs):
        return self

    def exec_driver_sql(self, sql, *args):
        self.calls.append(("sql", sql))
        return self

    def execute(self, sql, *args):
        self.calls.append(("sql", str(sql)))
        return self

    def scalar_one(self):
        return "160015" if self.calls[-1][1].startswith("SHOW ") else 0

    def one(self):
        return (False, False)

    def all(self):
        return []


def guarded_database(monkeypatch):
    database, child = Database(), Child()
    monkeypatch.setattr(Engine, "connect", lambda engine, *args, **kwargs: database.connect(engine))
    monkeypatch.setattr(tools.subprocess, "Popen", lambda *args, **kwargs: child)
    owner = install_tool_guard(monkeypatch, native)
    return database, child, owner


@pytest.mark.parametrize("terminal", [False, True])
def test_actual_pg_fixture_teardown_waits_for_confirmed_tool_exit(monkeypatch, terminal):
    database, child, owner = guarded_database(monkeypatch)
    monkeypatch.setattr(migration_fixture, "POSTGRES", "postgresql+psycopg://postgres@/postgres")
    generator = migration_fixture.pg.__wrapped__(monkeypatch)
    pg = next(generator)
    assert pg["owner_role"].endswith("_owner")
    owner.spawn(["dump"])
    first = TimeoutError("dump failure before target entry")
    owner.remember(first)
    child.code = 1 if terminal else None
    database.calls.clear()
    if terminal:
        generator.close()
        assert any(
            kind == "sql" and value.startswith("DROP DATABASE") for kind, value in database.calls
        )
        assert (
            sum(kind == "sql" and value.startswith("DROP ROLE") for kind, value in database.calls)
            == 3
        )
    else:
        with pytest.raises(TimeoutError) as caught:
            generator.close()
        assert caught.value is first and database.calls == []


@pytest.mark.parametrize("terminal", [False, True])
def test_actual_target_finalizer_never_drains_or_drops_for_live_tool(
    monkeypatch, tmp_path, terminal
):
    database, child, owner = guarded_database(monkeypatch)
    token = "ar_migration_" + "a" * 32
    owner_role = token + "_owner"
    pg = {
        name: create_engine(
            "postgresql+psycopg://postgres@/" + ("postgres" if name == "control" else token)
        )
        for name in ("control", "owner", "app", "admin")
    }
    pg["owner_role"] = owner_role
    first = TimeoutError("restore cleanup unconfirmed")
    with (
        pytest.raises(TimeoutError) as caught,
        restore_fixture.empty_target(source_fixture(), pg, tmp_path, lambda *args: None),
    ):
        owner.spawn(["restore"])
        owner.remember(first)
        child.code = 1 if terminal else None
        database.calls.clear()
        raise first
    assert caught.value is first
    record = json.loads((tmp_path / "target-cleanup.json").read_text())
    if terminal:
        assert record["absence_observed"] and record["errors"] == []
        assert any(
            kind == "sql" and value.startswith("DROP DATABASE") for kind, value in database.calls
        )
    else:
        assert not record["absence_observed"] and database.calls == []
        assert {row["phase"] for row in record["errors"]} == {"drain-target", "drop-target"}


def test_actual_outer_source_capture_cannot_query_after_dump_failure(monkeypatch, tmp_path):
    database, _, owner = guarded_database(monkeypatch)
    engine = create_engine("postgresql+psycopg://postgres@/source")
    fixture = source_fixture()
    fixture = replace(fixture, case=replace(fixture.case, engine=engine))
    owner.spawn(["dump"])
    first = TimeoutError("dump failure")
    owner.remember(first)
    with pytest.raises(TimeoutError) as caught:
        restore_fixture.capture(
            fixture,
            {"owner": engine, "control": create_engine("postgresql+psycopg://postgres@/postgres")},
            tmp_path,
            "source",
            lambda *a: None,
        )
    assert caught.value is first and database.calls == []


@pytest.mark.parametrize(
    "module",
    ["test_ledger_recovery_restore_postgres", "test_ledger_recovery_restore_truncated_postgres"],
)
def test_autouse_guard_outlives_actual_pytest_pg_and_legacy_finalizers(
    monkeypatch, tmp_path, capsys, module
):
    # This nested in-process test uses fake delegates, not a database or subprocess.
    # Its deliberate teardown failure must retain the original tool exception.
    monkeypatch.setattr(Engine, "connect", lambda *args, **kwargs: None)
    probe = tmp_path / ("test_order_" + module + ".py")
    probe.write_text(
        "import json\nfrom pathlib import Path\nimport pytest\n"
        "from sqlalchemy import Engine\n"
        "from " + module + " import restore_tool_ownership\n"
        "from ledger_restore_tools import run_tool\n"
        "events=[]\n"
        "@pytest.fixture\ndef pg(request):\n"
        " owner=request.getfixturevalue('restore_tool_ownership')\n"
        " events.append('pg-setup')\n yield owner\n"
        " events.append('pg-teardown')\n"
        " try: Engine.connect(object.__new__(Engine))\n"
        " except TimeoutError as error: assert error is owner.first_error\n"
        " else: raise AssertionError('teardown delegated')\n"
        "@pytest.fixture\ndef legacy(pg):\n"
        " events.append('legacy-setup')\n yield pg\n"
        " events.append('legacy-teardown')\n"
        "def test_probe(legacy,tmp_path):\n"
        " owner=legacy\n"
        " class Child:\n  pid=456\n  def poll(self): return None\n"
        " owner.popen=lambda *a,**k: Child()\n owner.spawn(['tool'])\n"
        " owner.remember(TimeoutError('original-tool-error'))\n"
        " events.append('body')\n"
        "@pytest.fixture(autouse=True)\ndef retained_order(request):\n"
        " yield\n"
        " Path(" + repr(str(tmp_path / "order.json")) + ").write_text(json.dumps(events))\n"
    )
    code = pytest.main(
        [str(probe), "-q", "-p", "no:cacheprovider", "--basetemp=" + str(tmp_path / "nested")]
    )
    output = capsys.readouterr().out
    assert code == 1 and "original-tool-error" in output, output
    events = json.loads((tmp_path / "order.json").read_text())
    assert events == ["pg-setup", "legacy-setup", "body", "legacy-teardown", "pg-teardown"]
    records = list((tmp_path / "nested").rglob("tool-ownership.json"))
    assert len(records) == 1
    record = json.loads(records[0].read_text())
    assert not record["resolved"] and record["first_error"] == "TimeoutError"
    assert any(row["boundary"] == "Engine.connect" for row in record["blocked"])


@pytest.mark.parametrize("terminal", [False, True])
def test_guard_record_failure_keeps_original_only_when_ownership_unresolved(terminal):
    child = Child(1 if terminal else None)
    owner = ToolOwnership(lambda *args: child, lambda: None)
    owner.spawn(["tool"])
    first, writing = TimeoutError("first tool error"), OSError("ownership receipt interrupted")
    owner.remember(first)

    def record(value):
        raise writing

    with pytest.raises((TimeoutError, OSError)) as caught:
        owner.finish(record)
    assert caught.value is (writing if terminal else first)
    assert owner.report()["resolved"] is terminal
