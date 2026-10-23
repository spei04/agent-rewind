"""CPU-only negative controls for the actual restore witnesses and tool runner."""

import hashlib
import json
import subprocess
from copy import deepcopy
from types import SimpleNamespace

import ledger_restore_tools as tools
import pytest
from ledger_provisioning_fixture import ProvisioningFixture
from ledger_reader_fixture import ReaderFixture
from ledger_restore_authority import (
    TRIGGER_TABLES,
    assert_ledger_authority,
    assert_same_authority,
    typed,
)
from ledger_restore_postgres_fixture import denied_probe, target_view
from sqlalchemy.exc import DBAPIError

EXPECTED_FUNCTION = {
    "settings": ["search_path=pg_catalog, public"],
    "definition": "BEGIN RETURN; END;",
}


def authority():
    relations = [
        {"oid": i + 10, "name": name, "kind": "r", "owner": "owner", "acl": None}
        for i, name in enumerate(["installation_adoptions", *TRIGGER_TABLES.values()])
    ]
    relation_ids = {row["name"]: row["oid"] for row in relations}
    return {
        "database": [{"name": "source", "owner": "owner", "acl": None}],
        "schemas": [{"name": "public", "owner": "pg_database_owner", "acl": "{owner=UC/owner}"}],
        "relations": relations,
        "functions": [
            {
                "oid": 100,
                "name": "ar7_ledger_constraint",
                "arguments": "",
                "owner": "owner",
                "acl": "{owner=X/owner}",
                "security_definer": False,
                "language": "plpgsql",
                "body": "RETURN;",
                "body_sha256": hashlib.sha256(b"RETURN;").hexdigest(),
                **EXPECTED_FUNCTION,
            }
        ],
        "triggers": [
            {
                "oid": 200 + i,
                "name": name,
                "relation_oid": relation_ids[table],
                "function_oid": 100,
                "constraint_oid": 300 + i,
                "relation": table,
                "function_name": "ar7_ledger_constraint",
                "function_schema": "public",
                "function_arguments": "",
                "enabled": "O",
                "deferrable": True,
                "initially_deferred": True,
                "definition": "trigger " + name,
                "constraint_name": name,
                "constraint_relation_oid": relation_ids[table],
                "constraint_deferrable": True,
                "constraint_initially_deferred": True,
            }
            for i, (name, table) in enumerate(TRIGGER_TABLES.items())
        ],
        "grants": [
            {
                "kind": "function",
                "name": "ar7_ledger_constraint",
                "arguments": "",
                "grantor": "owner",
                "grantee": "owner",
                "privilege": "EXECUTE",
                "grantable": False,
            }
        ],
        "roles": [{"name": "owner", "rolsuper": False}],
        "memberships": [],
    }


def restored(source):
    target = deepcopy(source)
    target["database"][0]["name"] = "target"
    for family in ("relations", "functions", "triggers"):
        for row in target[family]:
            for field in row:
                if field == "oid" or field.endswith("_oid"):
                    row[field] += 1000
    return target


def test_distinct_database_oids_require_correct_native_associations_without_rewriting_source():
    source = authority()
    retained = deepcopy(source)
    target = restored(source)
    assert_same_authority(source, target)
    assert_ledger_authority(source, "owner", EXPECTED_FUNCTION)
    assert_ledger_authority(target, "owner", EXPECTED_FUNCTION)
    assert source == retained
    assert source["functions"][0]["oid"] != target["functions"][0]["oid"]


@pytest.mark.parametrize(
    ("family", "field", "value"),
    [
        ("database", "owner", "other"),
        ("database", "acl", "{other=C/owner}"),
        ("schemas", "owner", "other"),
        ("schemas", "acl", None),
        ("relations", "owner", "other"),
        ("relations", "acl", "{other=r/owner}"),
        ("functions", "owner", "other"),
        ("functions", "acl", "{other=X/owner}"),
        ("functions", "language", "sql"),
        ("functions", "security_definer", True),
        ("functions", "settings", ["search_path=public"]),
        ("functions", "body", "MUTATED;"),
        ("functions", "definition", "different"),
        ("functions", "body_sha256", "0" * 64),
        ("grants", "grantor", "other"),
        ("grants", "grantee", "other"),
        ("grants", "privilege", "UPDATE"),
        ("grants", "grantable", True),
        ("triggers", "definition", "different"),
        ("triggers", "enabled", "D"),
        ("triggers", "deferrable", False),
        ("triggers", "initially_deferred", False),
        ("triggers", "function_oid", 101),
        ("triggers", "relation_oid", 11),
        ("triggers", "constraint_relation_oid", 11),
        ("triggers", "constraint_oid", 0),
        ("triggers", "constraint_name", "other"),
        ("triggers", "function_schema", "other"),
        ("roles", "rolsuper", True),
    ],
)
def test_changed_raw_authority_never_compares_equal(family, field, value):
    source = authority()
    target = restored(source)
    target[family][0][field] = value
    with pytest.raises((AssertionError, KeyError)):
        assert_same_authority(source, target)


@pytest.mark.parametrize("family", ["relations", "functions", "triggers", "grants"])
@pytest.mark.parametrize("change", ["duplicate", "missing", "extra"])
def test_authority_cardinality_is_not_hidden_by_mapping_or_set_conversion(family, change):
    source = authority()
    target = restored(source)
    if change == "duplicate":
        target[family].append(deepcopy(target[family][0]))
    elif change == "missing":
        target[family].pop()
    else:
        extra = deepcopy(target[family][0])
        extra["name"] = "unexpected"
        if "oid" in extra:
            extra["oid"] += 9000
        target[family].append(extra)
    with pytest.raises((AssertionError, KeyError)):
        assert_same_authority(source, target)


@pytest.mark.parametrize(
    ("family", "field", "value"),
    [
        ("relations", "owner", "other"),
        ("functions", "owner", "other"),
        ("functions", "security_definer", True),
        ("functions", "language", "sql"),
        ("functions", "definition", "different"),
        ("functions", "body", "different"),
        ("functions", "body_sha256", "0" * 64),
        ("functions", "settings", ["search_path=public"]),
        ("grants", "grantable", True),
        ("grants", "grantor", "other"),
        ("grants", "grantee", "other"),
        ("grants", "privilege", "UPDATE"),
        ("triggers", "enabled", "D"),
        ("triggers", "deferrable", False),
        ("triggers", "initially_deferred", False),
    ],
)
def test_mutually_matching_copies_do_not_replace_independent_ledger_authority_check(
    family,
    field,
    value,
):
    value_set = authority()
    value_set[family][0][field] = value
    with pytest.raises(AssertionError):
        assert_ledger_authority(value_set, "owner", EXPECTED_FUNCTION)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (False, 0),
        (True, 1),
        (1, 1.0),
        (b"a", "a"),
        ((1,), [1]),
        ({"cursor": '{"x":1}'}, {"cursor": '{"x":true}'}),
    ],
)
def test_native_scalar_and_raw_cursor_changes_are_distinct(left, right):
    assert typed(left) != typed(right)


def source_fixture():
    case = ReaderFixture(None, object(), True, "ar6", "source", {}, {"id": "source"}, [], {})
    return ProvisioningFixture(
        case, {"source": "before"}, {"jobs": []}, "digest", {"cipher": "hash"}, [], "org", "project"
    )


def test_target_view_retains_every_source_witness():
    source = source_fixture()
    target, pg = target_view(source, {"control": "separate"}, {"owner": "target"})
    assert target is not source and target.case is not source.case
    assert target.case.engine == "target" and pg["control"] == "separate"
    for name in ("before", "original", "source", "encrypted", "jobs", "organization", "project"):
        assert getattr(target, name) is getattr(source, name)
    for name in ("adoption", "previous_progress", "original_rows", "expected", "original_digest"):
        assert getattr(target.case, name) is getattr(source.case, name)


@pytest.mark.parametrize("tool", ["pg_dump", "pg_restore"])
def test_native_commands_preserve_owners_acls_and_transactions(tool, tmp_path):
    database = "ar_migration_" + "a" * 32 if tool == "pg_dump" else "ar_restore_" + "a" * 32
    archive = None if tool == "pg_dump" else tmp_path / "custom.archive"
    command = tools.tool_command(tmp_path / tool, tool, database, tmp_path, 55432, archive=archive)
    assert "--no-owner" not in command and "--no-acl" not in command
    assert "--role" not in command and "--clean" not in command
    assert "--username=postgres" in command
    if tool == "pg_restore":
        assert command[-3:] == ["--single-transaction", "--exit-on-error", str(archive)]
    else:
        assert command[-1] == "--format=custom"


@pytest.mark.parametrize(
    "database", ["postgres", "ar_restore_bad", "a; DROP DATABASE x", "x" * 100]
)
def test_tool_command_rejects_unowned_database(database, tmp_path):
    with pytest.raises(AssertionError):
        tools.tool_command(tmp_path / "pg_dump", "pg_dump", database, tmp_path, 55432)


def test_tool_environment_does_not_inherit_pg_authority(monkeypatch, tmp_path):
    for key in ("PGPASSWORD", "PGSERVICE", "PGSERVICEFILE", "PGSSLMODE", "PGOPTIONS"):
        monkeypatch.setenv(key, "untrusted")
    result = tools.tool_environment(tmp_path, "ar_restore_" + "a" * 32 + "_dump")
    assert not {"PGPASSWORD", "PGSERVICE", "PGSERVICEFILE", "PGSSLMODE"} & result.keys()
    assert result["PGHOST"] == str(tmp_path) and result["PGUSER"] == "postgres"
    assert result["PGOPTIONS"] != "untrusted"


class Stream:
    def __init__(self, number):
        self.number = number
        self.closed = False

    def fileno(self):
        return self.number

    def close(self):
        self.closed = True


class Process:
    pid = 12345

    def __init__(self, *, code=0, hang=False):
        self.stdout, self.stderr = Stream(100), Stream(101)
        self.code, self.hang = code, hang
        self.returncode = None
        self.actions = []

    def poll(self):
        return self.returncode

    def wait(self, timeout):
        self.actions.append(("wait", timeout))
        if self.hang and self.returncode is None:
            raise subprocess.TimeoutExpired("owned", timeout)
        if self.returncode is None:
            self.returncode = self.code
        return self.returncode

    def terminate(self):
        self.actions.append(("terminate",))

    def kill(self):
        self.actions.append(("kill",))
        self.returncode = -9


def fake_tools(monkeypatch, chunks, *, code=0, interruption=None, hang=False):
    process = Process(code=code, hang=hang)
    calls = []
    clock = [0.0]

    def now():
        clock[0] += 0.01
        return clock[0]

    def popen(argv, **kwargs):
        calls.append((argv, kwargs))
        return process

    class Selector:
        def __init__(self):
            self.mapping = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def register(self, stream, event, name):
            self.mapping[stream.number] = SimpleNamespace(fileobj=stream, data=name)

        def unregister(self, stream):
            del self.mapping[stream.number]

        def get_map(self):
            return self.mapping

        def select(self, timeout):
            if interruption is not None:
                raise interruption
            return [(key, 1) for key in self.mapping.values()]

    monkeypatch.setattr(tools.subprocess, "Popen", popen)
    monkeypatch.setattr(tools.selectors, "DefaultSelector", Selector)
    monkeypatch.setattr(tools.time, "monotonic", now)
    monkeypatch.setattr(tools.os, "read", lambda fd, size: chunks[fd].pop(0))
    return process, calls


def test_tool_streams_identity_bounds_and_exit_are_recorded(monkeypatch, tmp_path):
    process, calls = fake_tools(monkeypatch, {100: [b"PGDMPdata", b""], 101: [b"note", b""]})
    result = tools.run_tool(["pg_dump"], tmp_path, label="dump", env={}, archive=True)
    record = json.loads((tmp_path / "dump.json").read_text())
    assert result.read_bytes() == b"PGDMPdata"
    assert record["pid"] == process.pid and record["reaped"] and record["returncode"] == 0
    assert record["first_error"] is None and record["signals"] == []
    assert process.stdout.closed and process.stderr.closed
    assert calls[0][1]["start_new_session"] is False
    assert calls[0][1]["stdin"] is subprocess.DEVNULL


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_tool_overflow_retains_only_bounded_bytes_then_reaps(monkeypatch, tmp_path, stream):
    monkeypatch.setattr(tools, "MAX_DIAGNOSTIC", 4)
    chunks = {
        100: [b"12345" if stream == "stdout" else b"", b""],
        101: [b"12345" if stream == "stderr" else b"", b""],
    }
    process, _ = fake_tools(monkeypatch, chunks, hang=True)
    with pytest.raises(ValueError, match="bound"):
        tools.run_tool(["tool"], tmp_path, label="bounded", env={})
    record = json.loads((tmp_path / "bounded.json").read_text())
    assert (tmp_path / ("bounded." + stream)).read_bytes() == b"1234"
    assert record["first_error"] == "ValueError" and record["reaped"]
    assert record["signals"] == ["terminate", "kill"]
    assert process.stdout.closed and process.stderr.closed


@pytest.mark.parametrize("failure", ["exit", "header", "deadline"])
def test_tool_failures_are_recorded_without_retry(monkeypatch, tmp_path, failure):
    process, calls = fake_tools(
        monkeypatch,
        {100: [b"wrong", b""], 101: [b"error", b""]},
        code=1 if failure == "exit" else 0,
        hang=failure == "deadline",
    )
    expected = {"exit": RuntimeError, "header": ValueError, "deadline": TimeoutError}[failure]
    with pytest.raises(expected):
        tools.run_tool(
            ["tool"],
            tmp_path,
            label="failed",
            env={},
            timeout=0.001 if failure == "deadline" else 30,
            archive=failure == "header",
        )
    record = json.loads((tmp_path / "failed.json").read_text())
    assert len(calls) == 1 and record["first_error"] == expected.__name__
    assert record["reaped"] and process.stdout.closed and process.stderr.closed


def test_first_interrupt_survives_cleanup_failure(monkeypatch, tmp_path):
    interruption = KeyboardInterrupt("first")
    process, _ = fake_tools(monkeypatch, {}, interruption=interruption, hang=True)

    def broken_terminate():
        raise RuntimeError("cleanup")

    process.terminate = broken_terminate
    with pytest.raises(KeyboardInterrupt) as caught:
        tools.run_tool(["tool"], tmp_path, label="interrupt", env={})
    assert caught.value is interruption
    record = json.loads((tmp_path / "interrupt.json").read_text())
    assert record["cleanup_errors"] == ["RuntimeError"] and record["reaped"]


def test_expired_cleanup_still_signals_but_does_not_claim_unobserved_reaping():
    process = Process(hang=True)

    def kill_without_ack():
        process.actions.append(("kill",))

    process.kill = kill_without_ack
    record = {"signals": []}
    with pytest.raises(RuntimeError, match="cleanup"):
        tools.stop_owned(process, record, deadline=0, clock=lambda: 1)
    assert record["signals"] == ["terminate", "kill"]
    assert not record["reaped"]
    assert process.actions == [("terminate",), ("kill",)]


@pytest.mark.parametrize("sqlstate", ["42501", "23505", None, "interrupt"])
def test_permission_probe_rolls_back_before_accepting_only_permission_denial(sqlstate):
    native = Exception("native")
    native.sqlstate = sqlstate
    interruption = KeyboardInterrupt("first")
    events = []

    class Connection:
        is_active = True

        def __enter__(self):
            return self

        def __exit__(self, *args):
            events.append("closed")

        def begin(self):
            return self

        def execute(self, *args):
            events.append("execute")
            if sqlstate == "interrupt":
                raise interruption
            if sqlstate is not None:
                raise DBAPIError("probe", {}, native)

        def rollback(self):
            events.append("rollback")
            self.is_active = False

    engine = SimpleNamespace(connect=Connection)
    if sqlstate == "42501":
        assert denied_probe(engine, "UPDATE t SET x=x", {})["sqlstate"] == "42501"
    elif sqlstate == "interrupt":
        with pytest.raises(KeyboardInterrupt) as caught:
            denied_probe(engine, "UPDATE t SET x=x", {})
        assert caught.value is interruption
    else:
        with pytest.raises(AssertionError):
            denied_probe(engine, "UPDATE t SET x=x", {})
    assert events == ["execute", "rollback", "closed"]


@pytest.mark.parametrize("fault", [None, "body", "drain", "drop", "body-and-drop"])
def test_owned_target_cleanup_precedes_source_roles_and_preserves_primary_error(
    monkeypatch,
    tmp_path,
    fault,
):
    import ledger_restore_postgres_fixture as restore_fixture
    from sqlalchemy.engine import URL

    events = []
    source = "ar_migration_" + "a" * 32
    target = "ar_restore_" + "a" * 32
    first = KeyboardInterrupt("original body")
    drain_count = 0

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, *args):
            return SimpleNamespace(scalar_one=lambda: 0)

        def exec_driver_sql(self, statement):
            events.append(statement)
            if statement.startswith("DROP DATABASE") and fault in {"drop", "body-and-drop"}:
                raise RuntimeError("owned drop failure")

    class Engine:
        def __init__(self, url):
            self.url = url

        def begin(self):
            return Connection()

        def connect(self):
            return Connection()

        def dispose(self):
            events.append("disposed-" + self.url.username)

    def drain(pg, engine):
        nonlocal drain_count
        drain_count += 1
        assert engine.url.database == target
        events.append("drain")
        if fault == "drain" and drain_count == 2:
            raise RuntimeError("drain failed")

    monkeypatch.setattr(restore_fixture, "create_engine", lambda url, **kwargs: Engine(url))
    monkeypatch.setattr(restore_fixture, "drain", drain)
    pg = {
        name: Engine(URL.create("postgresql", username=name, database=source))
        for name in ("owner", "app", "admin")
    }
    pg["owner_role"] = source + "_owner"
    pg["control"] = Engine(URL.create("postgresql", username="postgres", database="postgres"))

    def use_target():
        with restore_fixture.empty_target(source_fixture(), pg, tmp_path, lambda *args: None) as (
            fixture,
            target_pg,
        ):
            assert fixture.case.engine.url.database == target
            assert target_pg["control"] is pg["control"]
            events.append("body")
            if fault in {"body", "body-and-drop"}:
                raise first

    if fault in {"body", "body-and-drop"}:
        with pytest.raises(KeyboardInterrupt) as caught:
            use_target()
        assert caught.value is first
    elif fault:
        with pytest.raises(AssertionError, match="cleanup"):
            use_target()
    else:
        use_target()
    events.append("source-role-release")
    assert events.index(f'DROP DATABASE "{target}" WITH (FORCE)') < events.index(
        "source-role-release"
    )
    record = json.loads((tmp_path / "target-cleanup.json").read_text())
    assert record["absence_observed"] is (fault not in {"drop", "body-and-drop"})
    assert bool(record["errors"]) is (fault in {"drain", "drop", "body-and-drop"})


def test_archive_cap_is_distinct_from_diagnostic_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "MAX_ARCHIVE", 5)
    process, _ = fake_tools(monkeypatch, {100: [b"PGDMPx", b""], 101: [b"note", b""]}, hang=True)
    with pytest.raises(ValueError, match="bound"):
        tools.run_tool(["tool"], tmp_path, label="archive-cap", env={}, archive=True)
    assert (tmp_path / "archive-cap.stdout").read_bytes() == b"PGDMP"
    record = json.loads((tmp_path / "archive-cap.json").read_text())
    assert record["stream_limits"] == {"stdout": 5, "stderr": tools.MAX_DIAGNOSTIC}
    assert record["reaped"] and process.stdout.closed


def test_stream_close_failure_does_not_replace_first_error(monkeypatch, tmp_path):
    interruption = KeyboardInterrupt("body first")
    process, _ = fake_tools(monkeypatch, {}, interruption=interruption, hang=True)

    def close():
        raise OSError("close failure")

    process.stdout.close = close
    with pytest.raises(KeyboardInterrupt) as caught:
        tools.run_tool(["tool"], tmp_path, label="close-fault", env={})
    assert caught.value is interruption
    record = json.loads((tmp_path / "close-fault.json").read_text())
    assert record["cleanup_errors"] == ["OSError"] and record["reaped"]
    assert process.stderr.closed
