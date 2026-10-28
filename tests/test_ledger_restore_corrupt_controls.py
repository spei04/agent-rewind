"""Offline controls for corruption deltas, raw bounds and service attribution."""

import json
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import ledger_restore_corrupt_observer as observer
import ledger_restore_corrupt_raw as raw
import psycopg
import pytest
import test_ledger_recovery_restore_corrupt_postgres as native
import test_ledger_restore_tool_ownership_controls as ownership_controls
from ledger_restore_authority import typed
from psycopg.types.json import Jsonb, JsonbDumper
from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg
from test_ledger_restore_interruption_raw_controls import restored_witness, witness

from agent_rewind.migrations.schema import MigrationRefused

PHASE = "ledger_manifest_m1"
PROGRESS = {
    "revision": raw.REVISION,
    "phase": PHASE,
    "cursor": '{"sequence":0}',
    "source_digest": "a" * 64,
    "rows_verified": 2,
    "status": "complete",
    "updated_at": "original",
}


def state():
    metadata = witness()
    metadata["inventory"]["routines"] = [
        {
            "schema": "public",
            "name": raw.FUNCTION,
            "kind": "f",
            "oid": 100,
            "arguments": "",
            "owner": "owner",
            "acl": "{owner=X/owner}",
        }
    ]
    columns = raw.source_columns(metadata)
    columns["migration_progress"] = ("revision", "phase", "cursor", "rows_verified", "updated_at")
    rows = []
    for index, phase in enumerate(("ledger_manifest_m0", PHASE)):
        cursor = {
            "sequence": index,
            "manifest": {
                "operation": "initialize" if index == 0 else "provision",
                "manifest_id": "m0" if index == 0 else "m1",
            },
        }
        rows.append(
            {
                "revision": raw.REVISION,
                "phase": phase,
                "cursor": cursor,
                "rows_verified": 2,
                "updated_at": "original",
                raw.CURSOR_TEXT: json.dumps(cursor),
            }
        )
    metadata["rows_present"]["migration_progress"] = True
    result = raw.RawRows(metadata, columns)
    for row in rows:
        result.append("migration_progress", row)
    return result.finish()


def cursor_changed(before):
    after = deepcopy(before)
    payload = raw.cursor_payload(before, PHASE)
    returned = json.dumps(payload, sort_keys=True)
    row = raw.selected_progress(after, PHASE)
    row["cursor"], row[raw.CURSOR_TEXT] = payload, returned
    after["tables"]["migration_progress"]["rows"].sort(key=raw.encoded)
    return after, payload, returned


def acl_changed(before):
    after = deepcopy(before)
    authority = after["metadata"]["authority"]
    authority["functions"][0]["acl"] = "{owner=X/owner,=X/owner}"
    after["metadata"]["inventory"]["routines"][0]["acl"] = "{owner=X/owner,=X/owner}"
    edge = {**authority["grants"][0], "grantee": "PUBLIC"}
    authority["grants"].insert(0, edge)
    return after


def test_exact_cursor_change_is_typed_and_does_not_mutate_original():
    before = state()
    retained = deepcopy(before)
    after, payload, returned = cursor_changed(before)
    raw.assert_cursor_delta(before, after, PHASE, payload, returned)
    assert typed(before) == typed(retained)
    assert json.loads(returned)["sequence"] == 0


@pytest.mark.parametrize(
    "change",
    [
        "second_row",
        "status",
        "timestamp",
        "bool_sequence",
        "extra_json",
        "raw_text",
        "column",
        "missing",
        "duplicate",
        "authority",
        "oid",
        "payload",
    ],
)
def test_cursor_delta_rejects_every_unrelated_or_missing_change(change):
    before = state()
    after, payload, returned = cursor_changed(before)
    rows = after["tables"]["migration_progress"]["rows"]
    selected = next(row for row in rows if row["phase"] == PHASE)
    if change == "second_row":
        next(row for row in rows if row["phase"] != PHASE)["cursor"]["sequence"] = 2
    elif change == "status":
        selected["rows_verified"] = 3
    elif change == "timestamp":
        selected["updated_at"] = "rewritten"
    elif change == "bool_sequence":
        selected["cursor"]["sequence"] = False
    elif change == "extra_json":
        selected["cursor"]["extra"] = 0
    elif change == "raw_text":
        selected[raw.CURSOR_TEXT] += " "
    elif change == "column":
        after["tables"]["api_keys"]["columns"] += ("extra",)
    elif change == "missing":
        rows.remove(selected)
    elif change == "duplicate":
        rows.append(deepcopy(selected))
    elif change == "authority":
        after["metadata"]["authority"]["roles"][0]["rolsuper"] = True
    elif change == "oid":
        after["metadata"]["inventory"]["relations"][0]["oid"] += 1
    else:
        payload["manifest"]["operation"] = "initialize"
    with pytest.raises((AssertionError, KeyError)):
        raw.assert_cursor_delta(before, after, PHASE, payload, returned)


@pytest.mark.parametrize("bad", [False, "1", 0, 2])
def test_only_the_original_native_m1_sequence_can_be_selected(bad):
    before = state()
    row = next(
        row for row in before["tables"]["migration_progress"]["rows"] if row["phase"] == PHASE
    )
    row["cursor"]["sequence"] = bad
    row[raw.CURSOR_TEXT] = json.dumps(row["cursor"])
    with pytest.raises(AssertionError):
        raw.cursor_payload(before, PHASE)


def test_acl_delta_requires_the_one_explicit_public_execute_edge():
    before = state()
    retained = deepcopy(before)
    raw.assert_acl_delta(before, acl_changed(before), "owner")
    assert typed(before) == typed(retained)


@pytest.mark.parametrize(
    "change",
    [
        "grantor",
        "grantee",
        "privilege",
        "grantable",
        "duplicate",
        "missing",
        "acl_order",
        "routine_acl",
        "body",
        "owner",
        "function_oid",
        "trigger_oid",
        "row",
        "constraint",
    ],
)
def test_acl_delta_rejects_widening_and_unrelated_native_changes(change):
    before = state()
    after = acl_changed(before)
    authority = after["metadata"]["authority"]
    edge = authority["grants"][0]
    if change in ("grantor", "grantee", "privilege"):
        edge[change] = "other"
    elif change == "grantable":
        edge["grantable"] = 0
    elif change == "duplicate":
        authority["grants"].append(deepcopy(edge))
    elif change == "missing":
        authority["grants"].pop(0)
    elif change == "acl_order":
        authority["functions"][0]["acl"] = "{=X/owner,owner=X/owner}"
    elif change == "routine_acl":
        after["metadata"]["inventory"]["routines"][0]["acl"] = "{owner=X/owner}"
    elif change in ("body", "owner"):
        authority["functions"][0][change] = "different"
    elif change == "function_oid":
        authority["functions"][0]["oid"] += 1
    elif change == "trigger_oid":
        authority["triggers"][0]["function_oid"] += 1
    elif change == "row":
        after["tables"]["migration_progress"]["rows"][0]["rows_verified"] = 0
    else:
        after["metadata"]["inventory"]["constraint_definitions"][0]["deferrable"] = True
    with pytest.raises(AssertionError):
        raw.assert_acl_delta(before, after, "owner")


def test_raw_restored_rows_require_exact_types_and_source_inventory():
    source = state()
    target = deepcopy(source)
    target["metadata"] = restored_witness(source["metadata"])
    raw.assert_restored_raw(source, target)
    target["tables"]["migration_progress"]["rows"][0]["rows_verified"] = 2.0
    with pytest.raises(AssertionError):
        raw.assert_restored_raw(source, target)


@pytest.mark.parametrize(
    "change", ["extra_table", "duplicate_column", "position", "empty", "reserved"]
)
def test_source_inventory_rejects_ambiguous_query_shapes(change):
    metadata = witness()
    if change == "extra_table":
        metadata["inventory"]["relations"].append({"name": "surprise", "kind": "r"})
    elif change == "duplicate_column":
        row = deepcopy(metadata["inventory"]["columns"][0])
        row["position"] = 2
        metadata["inventory"]["columns"].insert(1, row)
    elif change == "position":
        metadata["inventory"]["columns"][0]["position"] = 2
    elif change == "empty":
        metadata["inventory"]["columns"].pop(0)
    else:
        metadata["inventory"]["columns"][0]["name"] = raw.CURSOR_TEXT
    with pytest.raises(AssertionError):
        raw.source_columns(metadata)


@pytest.mark.parametrize("bound", ["rows", "cell", "total"])
def test_raw_retention_fails_before_appending_the_overflow_row(monkeypatch, bound):
    metadata = witness()
    columns = raw.source_columns(metadata)
    budget = raw.RawRows(metadata, columns)
    row = {"id": "a"}
    if bound == "rows":
        monkeypatch.setattr(raw, "MAX_ROWS", 1)
        budget.append("alembic_version", row)
    elif bound == "cell":
        monkeypatch.setattr(raw, "MAX_CELL", len(raw.encoded("a")) - 1)
    else:
        monkeypatch.setattr(raw, "MAX_SNAPSHOT", budget.bytes + len(raw.encoded(row)) - 1)
    original = deepcopy(budget.value)
    with pytest.raises(AssertionError):
        budget.append("alembic_version", row)
    assert typed(original) == typed(budget.value)


def test_raw_budget_accounts_for_table_envelopes_and_row_separators():
    metadata = witness()
    metadata["rows_present"]["alembic_version"] = True
    budget = raw.RawRows(metadata, raw.source_columns(metadata))
    budget.append("alembic_version", {"id": "second"})
    budget.append("alembic_version", {"id": "first"})
    value = budget.finish()
    assert budget.bytes == len(raw.encoded(value))
    assert value["tables"]["alembic_version"]["rows"] == [{"id": "first"}, {"id": "second"}]


def fake_watch():
    raw_handle = object()
    engine = object()
    connection = SimpleNamespace(
        engine=engine, connection=SimpleNamespace(driver_connection=raw_handle)
    )
    watch = SimpleNamespace(
        engine=engine,
        trace=SimpleNamespace(events=[("actual query",)]),
        owns=lambda candidate: candidate is raw_handle,
        work=SimpleNamespace(_raw=raw_handle),
        command_boundary={"trace_end": 100},
    )
    return watch, connection


def stage_path(kind):
    watch, connection = fake_watch()
    stages = observer.CorruptionStages(watch, PHASE)
    code = "ledger_progress_invalid" if kind == "cursor" else "schema_incompatible"
    error = MigrationRefused(code)

    def reject(*args):
        raise error

    executables = stages.wrap(reject if kind == "acl" else lambda c: object(), "executables")

    def catalog(c):
        return executables(c)

    progress = stages.wrap(reject, "progress")

    def history(c):
        return progress(c, PROGRESS)

    def inspection(c):
        stages.wrap(catalog, "catalog")(c)
        return stages.wrap(history, "history")(c)

    def service(engine, manifest):
        assert engine is watch.engine
        return stages.wrap(inspection, "inspection")(connection)

    return stages, error, service


@pytest.mark.parametrize("kind", ["cursor", "acl"])
def test_actual_stage_wrappers_forward_the_same_exception_and_original_arguments(monkeypatch, kind):
    stages, error, service = stage_path(kind)
    monkeypatch.setattr(observer.ledger_service, "_inspect_ledger_reentry", service)
    with pytest.raises(MigrationRefused) as caught:
        stages.invoke(object())
    assert caught.value is error
    assert stages.verify(kind, error, expected_progress=PROGRESS)["same_exception"]


@pytest.mark.parametrize(
    "change", ["early", "code", "identity", "phase", "raw", "order", "boundary"]
)
def test_refusal_attribution_rejects_unreached_or_replaced_service_failure(monkeypatch, change):
    stages, error, service = stage_path("cursor")
    monkeypatch.setattr(observer.ledger_service, "_inspect_ledger_reentry", service)
    with pytest.raises(MigrationRefused):
        stages.invoke(object())
    if change == "early":
        stages.events = stages.events[:1] + stages.events[-1:]
    elif change == "code":
        error.code = "schema_incompatible"
    elif change == "identity":
        first = stages.refusals[0]
        stages.refusals[0] = (first[0], MigrationRefused(error.code), first[2])
    elif change == "phase":
        first = stages.refusals[0]
        stages.refusals[0] = (first[0], first[1], "ledger_manifest_m0")
    elif change == "raw":
        stages.events[1]["raw_id"] += 1
    elif change == "order":
        stages.refusals.reverse()
    else:
        stages.events[2]["trace_index"] = 101
    with pytest.raises(AssertionError):
        stages.verify("cursor", error, expected_progress=PROGRESS)


def test_wrappers_do_not_replace_success_or_non_refusal_errors():
    watch, connection = fake_watch()
    stages = observer.CorruptionStages(watch, PHASE)
    expected = object()
    assert stages.wrap(lambda actual: expected, "catalog")(connection) is expected
    original = KeyboardInterrupt("original")

    def fail(actual):
        raise original

    with pytest.raises(KeyboardInterrupt) as caught:
        stages.wrap(fail, "catalog")(connection)
    assert caught.value is original


def test_observer_binds_actual_aliases_and_forbids_only_new_writer_work(monkeypatch):
    watch, _ = fake_watch()
    original = observer.ledger_service._inspect_ledger_context
    with monkeypatch.context() as patch, observer.observe_corruption(patch, watch, PHASE):
        assert observer.ledger_service._inspect_ledger_context is not original
        with pytest.raises(AssertionError, match="writer/source-refresh"):
            observer.ledger_service._provenance()
    assert observer.ledger_service._inspect_ledger_context is original


@pytest.mark.parametrize("failure", ["commit", "rollback", "cleanup", "physical"])
def test_zero_write_claim_requires_acknowledged_native_service_cleanup(failure):
    outcome = SimpleNamespace(
        commit_attempted=False,
        commit_acknowledged=False,
        rollback_attempted=True,
        rollback_acknowledged=True,
        cleanup_failed=False,
    )
    watch = SimpleNamespace(
        assert_single_attempt=lambda: None,
        assert_no_writes=lambda: None,
        outcome=outcome,
        physical=[{"action": "rollback", "status_after": 0, "closed_after": False}],
    )
    observer.assert_refusal_cleanup(watch)
    if failure == "commit":
        outcome.commit_attempted = True
    elif failure == "rollback":
        outcome.rollback_acknowledged = False
    elif failure == "cleanup":
        outcome.cleanup_failed = True
    else:
        watch.physical = []
    with pytest.raises(AssertionError):
        observer.assert_refusal_cleanup(watch)


class MutationConnection:
    def __init__(self, *, failure=None):
        self.calls, self.failure = [], failure
        self.dialect = PGDialect_psycopg(dbapi=psycopg)

    def exec_driver_sql(self, sql):
        self.calls.append(sql)
        return SimpleNamespace(one=lambda: ("owner", "target"))

    def execute(self, statement, parameters):
        self.calls.append((statement, parameters))
        assert statement._bindparams["cursor"].type.__class__.__name__ == "JSONB"
        compiled = statement.compile(dialect=self.dialect)
        assert "%(cursor)s::JSONB" in str(compiled)
        converted = compiled._bind_processors["cursor"](parameters["cursor"])
        assert type(converted) is Jsonb and converted.obj is parameters["cursor"]
        assert json.loads(JsonbDumper(Jsonb).dump(converted)) == parameters["cursor"]
        returned = json.dumps(parameters["cursor"])
        return SimpleNamespace(all=lambda: [(raw.REVISION, PHASE, returned)])


@pytest.mark.parametrize("kind", ["cursor", "acl"])
@pytest.mark.parametrize("fail_commit", [False, True])
def test_mutation_binding_and_commit_proof_are_separate_from_service(
    monkeypatch, kind, fail_commit
):
    connection = MutationConnection()
    failure = RuntimeError("commit failure")

    @contextmanager
    def begin():
        yield connection
        if fail_commit:
            raise failure

    fixture = SimpleNamespace(case=SimpleNamespace(engine=SimpleNamespace(begin=begin)))
    pg = {"owner_role": "owner", "owner": SimpleNamespace(url=SimpleNamespace(database="target"))}
    drained = []
    monkeypatch.setattr(raw, "drain", lambda actual: drained.append(actual))
    if fail_commit:
        with pytest.raises(RuntimeError) as caught:
            raw.mutate_target(fixture, pg, state(), kind, PHASE)
        assert caught.value is failure
    else:
        result = raw.mutate_target(fixture, pg, state(), kind, PHASE)
        assert result["committed"] and result["session_replication_role_changed"] is False
        assert result["kind"] == kind
    assert drained == [pg]
    assert not any("replication_role" in str(call) for call in connection.calls)


@pytest.mark.parametrize("terminal", [False, True])
def test_new_module_retains_actual_pg_fixture_ownership_teardown(monkeypatch, terminal):
    monkeypatch.setattr(ownership_controls, "native", native)
    ownership_controls.test_actual_pg_fixture_teardown_waits_for_confirmed_tool_exit(
        monkeypatch, terminal
    )


@pytest.mark.parametrize("terminal", [False, True])
def test_new_module_retains_actual_target_ownership_teardown(monkeypatch, tmp_path, terminal):
    monkeypatch.setattr(ownership_controls, "native", native)
    ownership_controls.test_actual_target_finalizer_never_drains_or_drops_for_live_tool(
        monkeypatch, tmp_path, terminal
    )


def test_new_module_autouse_guard_outlives_legacy_and_pg_teardown(monkeypatch, tmp_path, capsys):
    ownership_controls.test_autouse_guard_outlives_actual_pytest_pg_and_legacy_finalizers(
        monkeypatch, tmp_path, capsys, native.__name__
    )


@pytest.mark.parametrize("field", ["cursor", "updated_at", "source_digest", "rows_verified"])
def test_refusal_is_bound_to_independently_captured_m1_content(monkeypatch, field):
    stages, error, service = stage_path("cursor")
    monkeypatch.setattr(observer.ledger_service, "_inspect_ledger_reentry", service)
    with pytest.raises(MigrationRefused):
        stages.invoke(object())
    expected = {**PROGRESS, field: "changed" if field != "rows_verified" else 3}
    with pytest.raises(AssertionError, match="independently observed"):
        stages.verify("cursor", error, expected_progress=expected)


@pytest.mark.parametrize("mode", ["complete", "overflow", "changed_columns"])
def test_raw_capture_uses_source_columns_and_fails_closed_before_retaining_overflow(
    monkeypatch, tmp_path, mode
):
    metadata = witness()
    columns = raw.source_columns(metadata)
    metadata["rows_present"]["alembic_version"] = True
    if mode == "changed_columns":
        metadata["inventory"]["columns"][0]["name"] = "unexpected"
    calls, saves, drains = [], [], []
    dialect = PGDialect_psycopg(dbapi=psycopg)

    class Connection:
        def __init__(self):
            self.dialect = dialect

        def exec_driver_sql(self, sql):
            calls.append(sql)
            rows = []
            if 'FROM public."alembic_version"' in sql:
                rows = [{"id": "first"}]
                if mode == "overflow":
                    rows.append({"id": "overflow"})
            return SimpleNamespace(mappings=lambda: iter(rows))

    @contextmanager
    def begin():
        calls.append("begin")
        yield Connection()

    fixture = SimpleNamespace(case=SimpleNamespace(engine=SimpleNamespace(begin=begin)))
    monkeypatch.setattr(raw, "observe_schema_only", lambda *args: metadata)
    monkeypatch.setattr(raw, "save", lambda *args: saves.append(args))
    monkeypatch.setattr(raw, "drain", lambda actual: drains.append(actual))
    if mode == "overflow":
        monkeypatch.setattr(raw, "MAX_ROWS", 1)
    if mode == "complete":
        result = raw.capture_raw(fixture, {}, tmp_path, "raw", lambda *args: None, columns=columns)
        assert result["tables"]["alembic_version"]["rows"] == [{"id": "first"}]
        queries = [sql for sql in calls if sql.startswith("SELECT")]
        assert len(queries) == len(raw.TABLES) and all(
            sql.endswith(" LIMIT 1025") for sql in queries
        )
        assert len(saves) == 1 and drains == [{}]
    else:
        with pytest.raises(AssertionError):
            raw.capture_raw(fixture, {}, tmp_path, "raw", lambda *args: None, columns=columns)
        assert saves == []
        if mode == "changed_columns":
            assert calls == [] and drains == []
        else:
            assert len([sql for sql in calls if sql.startswith("SELECT")]) == 1 and drains == [{}]


def test_raw_source_finalizer_does_not_delegate_after_unreaped_dump(monkeypatch, tmp_path):
    from dataclasses import replace

    from sqlalchemy import create_engine

    monkeypatch.setattr(ownership_controls, "native", native)
    database, _, owner = ownership_controls.guarded_database(monkeypatch)
    engine = create_engine("postgresql+psycopg://postgres@/source")
    source = ownership_controls.source_fixture()
    source = replace(source, case=replace(source.case, engine=engine))
    pg = {
        "owner": engine,
        "control": create_engine("postgresql+psycopg://postgres@/postgres"),
        "owner_role": "owner",
        "app_role": "app",
        "group_role": "group",
    }
    owner.spawn(["dump"])
    original = TimeoutError("original dump failure")
    owner.remember(original)
    with pytest.raises(TimeoutError) as caught:
        raw.capture_raw(source, pg, tmp_path, "source", lambda *args: None)
    assert caught.value is original and database.calls == []


def history_state(observed):
    row = {
        **PROGRESS,
        "cursor": {"sequence": 0},
        raw.CURSOR_TEXT: '{ "sequence" : 0 }',
        "updated_at": observed,
    }
    return {"tables": {"migration_progress": {"rows": [row]}}}


@pytest.mark.parametrize(
    ("observed", "expected"),
    [
        (datetime(2026, 10, 23, 1, 2, 3, tzinfo=UTC), "2026-10-23T01:02:03.000000Z"),
        (
            datetime(
                2026, 10, 23, 1, 2, 3, 456789, tzinfo=timezone(timedelta(hours=5, minutes=30))
            ),
            "2026-10-22T19:32:03.456789Z",
        ),
        (
            datetime(2026, 10, 23, 23, 59, 59, 1, tzinfo=timezone(timedelta(hours=-7))),
            "2026-10-24T06:59:59.000001Z",
        ),
    ],
)
def test_expected_history_projection_preserves_raw_timestamp_and_cursor(observed, expected):
    before = history_state(observed)
    retained = deepcopy(before)
    result = raw.historical_row(before, PHASE)
    assert type(result["updated_at"]) is datetime
    assert result["updated_at"].isoformat(timespec="microseconds") == expected[:-1] + "+00:00"
    assert result["cursor"] == '{ "sequence" : 0 }'
    assert typed(before) == typed(retained)
    assert type(before["tables"]["migration_progress"]["rows"][0]["updated_at"]) is datetime


class TimestampSubclass(datetime):
    pass


@pytest.mark.parametrize(
    "observed",
    [
        datetime(2026, 10, 23),
        "2026-10-23T00:00:00.000000Z",
        TimestampSubclass(2026, 10, 23, tzinfo=UTC),
    ],
)
def test_expected_history_projection_rejects_non_native_timestamp(observed):
    with pytest.raises(AssertionError):
        raw.historical_row(history_state(observed), PHASE)


@pytest.mark.parametrize("change", ["cursor", "text", "missing", "duplicate", "field"])
def test_expected_history_projection_rejects_mismatched_cursor_and_row_shape(change):
    value = history_state(datetime(2026, 10, 23, tzinfo=UTC))
    rows = value["tables"]["migration_progress"]["rows"]
    if change == "cursor":
        rows[0]["cursor"]["sequence"] = 1
    elif change == "text":
        rows[0][raw.CURSOR_TEXT] = '{"sequence":1}'
    elif change == "missing":
        rows.clear()
    elif change == "duplicate":
        rows.append(deepcopy(rows[0]))
    else:
        rows[0]["unexpected"] = "value"
    with pytest.raises(AssertionError):
        raw.historical_row(value, PHASE)


def test_expected_history_timestamp_matches_frozen_actual_h60_projection():
    from agent_rewind.migrations.ledger_history_sql import SQL

    statement = SQL[("all", "postgresql", "H60_ledger_progress_body")]
    assert 'CAST(cursor AS TEXT) ELSE NULL END AS "cursor"' in statement
    assert (
        "to_char(updated_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"')"
        ' ELSE NULL END AS "updated_at"'
    ) in statement


@pytest.mark.parametrize(
    "observed",
    [
        datetime(2026, 10, 23, tzinfo=UTC),
        datetime(2026, 10, 23, 1, 2, 3, 456789, tzinfo=timezone(timedelta(hours=5, minutes=30))),
        datetime(2026, 10, 23, 23, 59, 59, 1, tzinfo=timezone(timedelta(hours=-7))),
    ],
)
def test_actual_read_converts_exact_h60_wire_time_before_progress_validator(monkeypatch, observed):
    from agent_rewind.migrations import ledger_reader_history

    expected = raw.historical_row(history_state(observed), PHASE)
    utc = observed.astimezone(UTC)
    wire = (
        f"{utc.year:04d}-{utc.month:02d}-{utc.day:02d}T"
        f"{utc.hour:02d}:{utc.minute:02d}:{utc.second:02d}.{utc.microsecond:06d}Z"
    )
    bodies = [
        {**expected, "updated_at": wire},
        {**expected, "phase": "ledger_opening", "updated_at": wire},
    ]
    byte_count = sum(len(str(value).encode()) for row in bodies for value in row.values())
    receipt = {
        "candidate_rows": 2,
        "invalid_rows": 0,
        "native_bytes": byte_count,
        "utf8_bytes": byte_count,
        "historical_timestamp_bytes": 0,
        "cursor_bytes": len(expected["cursor"].encode()) * 2,
        "metadata_bytes": 200,
        "opening_rows": 1,
        "manifest_rows": 1,
    }
    calls = []

    def query(connection, name, parameters):
        calls.append((name, parameters))
        if name == "H60_ledger_progress_gate":
            return [dict(receipt)]
        assert name == "H60_ledger_progress_body"
        return deepcopy(bodies)

    dialect = PGDialect_psycopg(dbapi=psycopg)
    dialect.server_version_info = (16, 15)
    monkeypatch.setattr(ledger_reader_history, "_query", query)
    rows, size = ledger_reader_history._read(
        SimpleNamespace(dialect=dialect),
        "H60_ledger_progress",
        SimpleNamespace(check=lambda: None),
    )
    assert typed(rows[0]) == typed(expected) and size == 0
    assert bodies[0]["updated_at"] is wire  # The retained wire input was not mutated.
    assert calls == [
        ("H60_ledger_progress_gate", {}),
        (
            "H60_ledger_progress_body",
            {
                "expected_rows": 2,
                "expected_native_bytes": byte_count,
                "expected_utf8_bytes": byte_count,
                "expected_cursor_bytes": receipt["cursor_bytes"],
            },
        ),
    ]
