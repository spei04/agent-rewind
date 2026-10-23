"""Offline controls for PostgreSQL setup types and original overflow attribution."""

import json
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from ledger_eligibility_fixture import rows
from ledger_money_postgres_fixture import assert_job_types
from ledger_money_postgres_observer import assert_native_preparation
from ledger_overflow_fixture import CASES, HALF, JOBS, overflow_manifest
from ledger_overflow_observer import assert_overflow_refusal, sum_sites
from ledger_overflow_postgres_fixture import (
    assert_move_candidate,
    assert_setup_delta,
    overflow_predecessor,
    raw_progress,
)
from ledger_overflow_postgres_observer import observe_overflow
from ledger_restore_authority import typed
from sqlalchemy import BigInteger
from sqlalchemy.dialects import postgresql
from test_ledger_eligibility_controls import table
from test_ledger_money_postgres_controls import job_types, native_watch, replace_native_cell
from test_ledger_overflow_controls import changed_example as sqlite_example

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused


def native_state(state):
    state = deepcopy(state)
    state["catalog"] = state.pop("schema")
    state["authority"] = {"schema": (("public", "fixture_owner", None),)}
    state["role"] = "fixture_owner"
    for name, field in (("records", "data"), ("projects", "created_at")):
        values = rows(state, name)
        for row in values:
            row[field] = (
                json.loads(row[field]) if name == "records" else datetime.fromisoformat(row[field])
            )
        state["tables"][name] = table(values)
    for i in range(3):
        # This standalone fixture explicitly models the PostgreSQL driver.
        from test_ledger_eligibility_controls import replace_cell

        replace_cell(state, "jobs", i, "cancel", False)
    state["tables"]["unrelated"] = table(
        [
            {
                "id": "protected",
                "data": {"integer": 0},
                "created_at": datetime(2026, 1, 1, tzinfo=UTC),
            }
        ]
    )
    for value in state["tables"].values():
        value["rows"] = tuple(value["rows"])
    return state


def example(case):
    fixture, before = sqlite_example(case)
    fixture.before, before = native_state(fixture.before), native_state(before)
    return fixture, before


def refused(monkeypatch, case, *, earlier=None, interrupt=None):
    fixture, _ = example(case)
    manifest = overflow_manifest(fixture, case)
    if earlier == "job-cap":
        manifest["accounts"][-3]["limit_microusd"] = HALF + 1
    elif earlier == "project-cap":
        manifest["accounts"][1]["limit_microusd"] = HALF - 1
    watch, context = native_watch(fixture)
    context.financial["scope"] = [
        row for row in context.financial["scope"] if row["resource_kind"] == "job"
    ]
    project_calls = []

    # Only the offline graph-query stand-in is synthetic; preparation and sums are original.
    def projects(connection, parsed, organization, work):
        project_calls.append((connection, parsed, organization, work))
        assert connection is watch.work._connection and work is watch.work

    monkeypatch.setattr(ledger_service, "_projects", projects)
    if interrupt is not None:

        def check():
            raise interrupt

        watch.work.check = check
    captured = []
    parsed = validate_ledger_manifest(manifest)
    with (
        observe_overflow(watch, monkeypatch, lambda *args: captured.append(args)) as observed,
        pytest.raises(type(interrupt) if interrupt else MigrationRefused) as failure,
    ):
        ledger_service._projects(watch.work._connection, parsed, fixture.organization, watch.work)
        ledger_service._prepare_ledger(context, parsed, watch.work)
    (entry,), stages = observed
    assert len(project_calls) == len(captured) == 1
    assert captured[0][0] == "overflow_preparation"
    return fixture, manifest, case, entry, stages, failure.value, watch


@pytest.mark.parametrize("case", CASES)
def test_native_valid_setup_has_only_declared_cells_and_exact_original_overflow(case, monkeypatch):
    fixture, before = example(case)
    assert_setup_delta(before, fixture.before, fixture.project, case)
    assert_job_types(fixture.before, job_types(fixture))
    args = refused(monkeypatch, case)
    assert_native_preparation(args[3], args[0], args[1], args[6])
    assert_overflow_refusal(*args)
    assert sum_sites() == {"total": 193, "organization_opening": 211, "refusal": 88}
    assert args[3]["error"]["identity"] == id(args[5])


@pytest.mark.parametrize(
    "change",
    [
        "float",
        "boolean",
        "decimal",
        "string",
        "other-budget",
        "job-state",
        "scope",
        "run-scope",
        "json-type",
        "json-text",
        "naive-time",
        "changed-time",
        "catalog",
        "authority",
        "role",
        "extra-job",
        "missing-job",
        "project-owner",
    ],
)
def test_typed_native_setup_rejects_any_other_change(change):
    fixture, before = example("organization")
    state = fixture.before
    invalid = {"float": 0.0, "boolean": False, "decimal": Decimal(0), "string": "0"}
    if change in invalid:
        replace_native_cell(state, "jobs", 1, "reserved", invalid[change])
    elif change == "other-budget":
        replace_native_cell(state, "jobs", 1, "budget", HALF)
    elif change == "job-state":
        replace_native_cell(state, "jobs", 2, "status", "cancelled")
    elif change == "scope":
        replace_native_cell(state, "resource_scopes", 2, "project_id", fixture.project)
    elif change == "run-scope":
        replace_native_cell(state, "run_index", 0, "project_id", "7" * 32)
    elif change in {"json-type", "json-text"}:
        value = {"integer": False} if change == "json-type" else '{"integer": 0}'
        replace_native_cell(state, "unrelated", 0, "data", value)
    elif change in {"naive-time", "changed-time"}:
        value = datetime(2026, 1, 1) if change == "naive-time" else datetime(2026, 1, 2, tzinfo=UTC)
        replace_native_cell(state, "unrelated", 0, "created_at", value)
    elif change in {"catalog", "authority", "role"}:
        state[change] = "changed"
    elif change == "extra-job":
        state["tables"]["jobs"]["rows"] += state["tables"]["jobs"]["rows"][:1]
    elif change == "missing-job":
        state["tables"]["jobs"]["rows"] = state["tables"]["jobs"]["rows"][:-1]
    else:
        replace_native_cell(state, "projects", 0, "organization_id", "7" * 32)
    with pytest.raises(AssertionError):
        assert_setup_delta(before, state, fixture.project, "organization")


@pytest.mark.parametrize("change", ["record-edge", "record-text", "operation", "result", "scope"])
def test_native_move_candidate_requires_the_original_edge_free_job(change):
    fixture, before = example("organization")
    if change == "record-edge":
        replace_native_cell(before, "records", 1, "data", {"job_id": JOBS[2], "parent_id": None})
    elif change == "record-text":
        replace_native_cell(before, "records", 0, "data", '{"job_id": "untyped"}')
    elif change == "operation":
        before["tables"]["operations"]["rows"] += (("new-operation",),)
    elif change == "result":
        replace_native_cell(before, "jobs", 2, "result", "e" * 64)
    else:
        replace_native_cell(before, "resource_scopes", 2, "project_id", "7" * 32)
    with pytest.raises(AssertionError):
        assert_move_candidate(before, fixture.project)


@pytest.mark.parametrize("earlier", ["job-cap", "project-cap"])
def test_native_same_code_earlier_refusals_never_receive_sum_credit(earlier, monkeypatch):
    args = refused(monkeypatch, "organization", earlier=earlier)
    assert args[5].code == "ledger_exposure_refused"
    assert args[3]["reduction_frames"][0]["line"] == (119 if earlier == "job-cap" else 202)
    with pytest.raises(AssertionError):
        assert_overflow_refusal(*args)


@pytest.mark.parametrize(
    "change",
    [
        "work",
        "raw",
        "exception",
        "project-sum",
        "organization-caller",
        "sum-delegate",
        "rollback",
        "commit",
        "closure-order",
        "native-financial-type",
    ],
)
def test_native_observation_requires_original_identity_reductions_and_cleanup(change, monkeypatch):
    args = list(refused(monkeypatch, "organization"))
    entry, watch = args[3], args[6]
    if change == "work":
        entry["sums"][-1]["work_id"] += 1
    elif change == "raw":
        entry["raw_id"] += 1
    elif change == "exception":
        args[5] = MigrationRefused("ledger_exposure_refused")
    elif change == "project-sum":
        entry["sums"][-2]["total"] -= 1
    elif change == "organization-caller":
        entry["reduction_frames"][0]["line"] = sum_sites()["total"]
    elif change == "sum-delegate":
        entry["sums"][-1]["original_prepare_caller"] = False
    elif change == "rollback":
        watch.outcome.confirmed_precommit_rollback = False
    elif change == "commit":
        watch.outcome.commit_attempted = True
    elif change == "closure-order":
        watch.markers.reverse()
    else:
        entry["financial"]["job"][1]["reserved"] = 0.0
    with pytest.raises(AssertionError):
        assert_native_preparation(entry, args[0], args[1], watch)
        assert_overflow_refusal(*args)


@pytest.mark.parametrize("handles", [[], [object()], [object(), object()]])
def test_native_observer_rejects_unproved_handle_before_any_delegate(monkeypatch, handles):
    fixture, _ = example("project")
    watch, context = native_watch(fixture)
    watch.trace.handles = handles
    called = []

    def unreachable(*args):
        called.append(args)
        raise AssertionError("unproved native handle")

    monkeypatch.setattr(ledger_service, "_prepare_ledger", unreachable)
    with (
        observe_overflow(watch, monkeypatch, lambda *args: None) as (entries, stages),
        pytest.raises(AssertionError),
    ):
        ledger_service._prepare_ledger(
            context, validate_ledger_manifest(overflow_manifest(fixture, "project")), watch.work
        )
    assert called == entries == stages == []


def test_original_baseexception_is_preserved_without_overflow_credit(monkeypatch):
    error = KeyboardInterrupt("native-overflow-control")
    args = refused(monkeypatch, "organization", interrupt=error)
    assert args[5] is error and args[3]["sums"] == []
    with pytest.raises(AssertionError):
        assert_overflow_refusal(*args)


@pytest.mark.parametrize(
    ("case", "failure_step"),
    [(case, step) for case in CASES for step in [None, *range(3 if case == "project" else 5)]],
)
def test_setup_context_acknowledges_only_successful_bound_bigint_transaction(
    monkeypatch, case, failure_step
):
    import ledger_overflow_postgres_fixture as module

    refreshed, before = example(case)
    refreshed.encrypted = {str(i): "a" * 64 for i in range(18)}
    fixture = deepcopy(refreshed)
    fixture.before = before
    actions, statements, recorded = [], [], []
    failure = RuntimeError("controlled setup failure")
    progress = [{"revision": "ar_0006_admission", "phase": "example", "raw_cursor": '{"n":0}'}]

    class Connection:
        def exec_driver_sql(self, sql):
            actions.append(sql)
            return SimpleNamespace(one=lambda: ("fixture_owner", "fixture_database"))

        def execute(self, statement, values):
            if "amount" in values:
                compiled = statement.compile(dialect=postgresql.dialect())
                assert isinstance(compiled.binds["amount"].type, BigInteger)
            statements.append((str(statement), deepcopy(values)))
            if len(statements) - 1 == failure_step:
                raise failure
            return SimpleNamespace(rowcount=1)

    class Engine:
        @contextmanager
        def begin(self):
            actions.append("begin")
            try:
                yield Connection()
            except BaseException:
                actions.append("rollback")
                raise
            else:
                actions.append("commit")

    fixture.case = SimpleNamespace(engine=Engine())
    monkeypatch.setattr(module, "native_snapshot", lambda *args: before)
    monkeypatch.setattr(module, "encrypted_files", lambda *args: fixture.encrypted)
    monkeypatch.setattr(module, "drain", lambda *args: actions.append("drain"))
    monkeypatch.setattr(module, "observe_inputs", lambda *args: refreshed)
    monkeypatch.setattr(module, "raw_progress", lambda *args: deepcopy(progress))
    pg = {
        "owner_role": "fixture_owner",
        "owner": SimpleNamespace(url=SimpleNamespace(database="fixture_database")),
    }

    def record(name, value):
        recorded.append((name, value, list(actions)))

    if failure_step is not None:
        with pytest.raises(RuntimeError) as caught:
            overflow_predecessor(fixture, pg, case, record)
        assert caught.value is failure
        assert actions[-2:] == ["rollback", "drain"] and not recorded
    else:
        result, observed_progress = overflow_predecessor(fixture, pg, case, record)
        assert result is refreshed and typed(observed_progress) == typed(progress)
        assert recorded[0][0] == "setup_commit" and recorded[0][2][-1] == "commit"
        assert recorded[0][1]["acknowledged"] is True
        money = [values["amount"] for _, values in statements if "amount" in values]
        assert money == [HALF, 0, HALF] and all(type(value) is int for value in money)
        assert actions[-3:] == ["SET CONSTRAINTS ALL IMMEDIATE", "commit", "drain"]
        assert_setup_delta(before, result.before, fixture.project, case)


@pytest.mark.parametrize("fail", [False, True])
def test_raw_json_witness_is_returned_without_normalization_and_always_drained(monkeypatch, fail):
    import ledger_overflow_postgres_fixture as module

    value = [{"revision": "a", "phase": "b", "raw_cursor": '{"n":0, "t":false}'}]
    events = []
    error = RuntimeError("controlled raw witness query failure")

    class Connection:
        def exec_driver_sql(self, sql):
            assert sql == module.RAW_PROGRESS_SQL
            if fail:
                raise error
            return SimpleNamespace(mappings=lambda: value)

    class Engine:
        @contextmanager
        def connect(self):
            try:
                yield Connection()
            finally:
                events.append("closed")

    fixture = SimpleNamespace(case=SimpleNamespace(engine=Engine()))
    monkeypatch.setattr(module, "drain", lambda *args: events.append("drain"))
    if fail:
        with pytest.raises(RuntimeError) as caught:
            raw_progress(fixture, {})
        assert caught.value is error
    else:
        assert typed(raw_progress(fixture, {})) == typed(value)
    assert events == ["closed", "drain"]
