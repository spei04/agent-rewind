"""Offline differential controls for native money setup, observation and results."""

import json
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from ledger_eligibility_fixture import rows
from ledger_money_fixture import EXACT_AMOUNT, below_job_cap, money_manifest
from ledger_money_observer import assert_job_cap_refusal
from ledger_money_postgres_fixture import (
    assert_exact_result,
    assert_job_types,
    assert_setup_delta,
    exact_predecessor,
)
from ledger_money_postgres_observer import assert_native_preparation, observe_money
from ledger_provisioning_fixture import digest, expected_stage
from ledger_restore_authority import typed
from sqlalchemy import BigInteger
from sqlalchemy.dialects import postgresql
from test_ledger_eligibility_controls import replace_cell, table
from test_ledger_money_controls import context_for, legacy_example

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.ledger_state import LedgerProvisioning
from agent_rewind.migrations.schema import LEDGER, MigrationRefused


def native_example():
    fixture = legacy_example()
    before = fixture.before
    before["catalog"] = before.pop("schema")
    before["authority"] = {"schema": (("public", "fixture_owner", None),)}
    before["role"] = "fixture_owner"
    for index in range(3):
        replace_cell(before, "jobs", index, "cancel", False)
    before["tables"]["unrelated"] = table(
        [
            {
                "id": "protected",
                "data": {"integer": 0, "boolean": False},
                "created_at": datetime(2026, 1, 1, tzinfo=UTC),
            }
        ]
    )
    for value in before["tables"].values():
        value["rows"] = tuple(value["rows"])
    return fixture


def expected_setup(fixture):
    before = deepcopy(fixture.before)
    target = fixture.jobs[0]["id"]
    changed = []
    for row in rows(before, "jobs"):
        row["reserved"] = EXACT_AMOUNT if row["id"] == target else 0
        if row["id"] == target:
            row["budget"] = EXACT_AMOUNT
        changed.append(tuple(row[key] for key in before["tables"]["jobs"]["columns"]))
    fixture.before["tables"]["jobs"]["rows"] = tuple(sorted(changed, key=repr))
    for row in fixture.jobs:
        row["reserved"] = EXACT_AMOUNT if row["id"] == target else 0
        if row["id"] == target:
            row["budget"] = EXACT_AMOUNT
    return before, target


def replace_native_cell(state, name, index, field, value):
    data = state["tables"][name]
    changed = list(data["rows"])
    row = list(changed[index])
    row[data["columns"].index(field)] = value
    changed[index] = tuple(row)
    data["rows"] = tuple(changed)


def native_watch(fixture):
    watch, context = context_for(fixture)
    watch.trace = SimpleNamespace(handles=[watch.work._raw], events=[])
    return watch, context


def job_types(fixture):
    return [{**row, "budget_type": "bigint", "reserved_type": "bigint"} for row in fixture.jobs]


def refused(monkeypatch, *, earlier=False):
    fixture = native_example()
    _, manifest, target = below_job_cap(fixture)
    if earlier:
        manifest["accounts"][2]["limit_microusd"] = fixture.jobs[0]["budget"] + 1
    watch, context = native_watch(fixture)
    captured = []
    with (
        observe_money(watch, monkeypatch, lambda *args: captured.append(args)) as observed,
        pytest.raises(MigrationRefused) as failure,
    ):
        ledger_service._prepare_ledger(context, validate_ledger_manifest(manifest), watch.work)
    (entry,), stages = observed
    assert len(captured) == 1 and captured[0][0] == "money_preparation"
    return fixture, manifest, target, watch, entry, stages, failure.value


def successful(monkeypatch):
    fixture = native_example()
    expected_setup(fixture)
    manifest = money_manifest(fixture)
    watch, context = native_watch(fixture)
    original = ledger_service._prepare_ledger
    returned = []

    def delegate(*args):
        result = original(*args)
        returned.append(result)
        return result

    monkeypatch.setattr(ledger_service, "_prepare_ledger", delegate)
    with observe_money(watch, monkeypatch, lambda *args: None) as (entries, stages):
        result = ledger_service._prepare_ledger(
            context, validate_ledger_manifest(manifest), watch.work
        )
    assert result is returned[0]
    (entry,) = entries
    assert_native_preparation(entry, fixture, manifest, watch)
    assert stages == ["prepare.enter", "prepare.return"]
    receipt = LedgerProvisioning(
        installation_key=manifest["installation_key"],
        revision=LEDGER,
        manifest_id=manifest["manifest_id"],
        manifest_digest=digest(manifest),
        sequence=0,
        operation="initialize",
        source_digest=manifest["source_digest"],
        account_rows=5,
        imported_jobs=3,
        imported_opening_microusd=EXACT_AMOUNT,
        initialized_at="2026-01-01T00:00:00.123456Z",
        outcome="complete",
    )
    accounts, progress, inspection = expected_stage(
        fixture, [manifest], [receipt], database_role="fixture_owner"
    )
    for row in accounts:
        for field in ("period_start", "period_end"):
            row[field] = datetime.fromisoformat(row[field].replace("Z", "+00:00"))
    after = deepcopy(fixture.before)
    after["tables"]["budget_accounts"] = table(accounts)
    after["tables"]["migration_progress"] = table(
        [
            {
                "revision": LEDGER,
                "phase": phase,
                "cursor": cursor,
                "rows_verified": count,
                "source_digest": source,
                "status": "complete",
                "updated_at": datetime.fromisoformat(receipt.initialized_at.replace("Z", "+00:00")),
            }
            for phase, (cursor, count, source) in sorted(progress.items())
        ]
    )
    jobs = rows(after, "jobs")
    for row in jobs:
        row.update(legacy_reserved_microusd=row["reserved"], lease_generation=0)
    after["tables"]["jobs"] = table(jobs)
    account_types = [
        {
            "id": row["id"],
            "limit_type": "bigint",
            "opening_type": "bigint",
            "held_type": "bigint",
            "accounted_type": "bigint",
        }
        for row in accounts
    ]
    progress_text = [
        {"phase": phase, "cursor": json.dumps(cursor, sort_keys=True)}
        for phase, (cursor, _, _) in sorted(progress.items())
    ]
    return (
        fixture,
        manifest,
        entry["prepared"],
        receipt,
        after,
        inspection,
        account_types,
        progress_text,
        "fixture_owner",
    )


def test_native_four_cell_setup_and_bigint_transport_keep_other_budgets():
    fixture = native_example()
    before, target = expected_setup(fixture)
    assert_setup_delta(before, fixture.before, target)
    assert assert_job_types(fixture.before, job_types(fixture)) == fixture.jobs
    assert [row["budget"] for row in fixture.jobs] == [EXACT_AMOUNT, 10000000, 5000000]
    assert [row["reserved"] for row in fixture.jobs] == [EXACT_AMOUNT, 0, 0]


@pytest.mark.parametrize(
    "changed",
    [
        "float",
        "bool",
        "decimal",
        "string",
        "rounded",
        "other-budget",
        "catalog",
        "acl",
        "timestamp",
        "json-type",
        "missing-job",
        "extra-job",
    ],
)
def test_native_setup_rejects_type_coercion_or_collateral_changes(changed):
    fixture = native_example()
    before, target = expected_setup(fixture)
    after = fixture.before
    values = {"float": 0.0, "bool": False, "decimal": Decimal(0), "string": "0"}
    if changed in values:
        replace_native_cell(after, "jobs", 1, "reserved", values[changed])
    elif changed == "rounded":
        replace_native_cell(after, "jobs", 0, "reserved", 2**53)
    elif changed == "other-budget":
        replace_native_cell(after, "jobs", 1, "budget", EXACT_AMOUNT)
    elif changed == "catalog":
        after["catalog"] = ("different",)
    elif changed == "acl":
        after["authority"]["schema"] = (("public", "fixture_owner", "{PUBLIC=UC}"),)
    elif changed == "timestamp":
        replace_native_cell(after, "unrelated", 0, "created_at", datetime(2026, 1, 1))
    elif changed == "json-type":
        replace_native_cell(after, "unrelated", 0, "data", {"integer": False, "boolean": False})
    else:
        values = after["tables"]["jobs"]["rows"]
        after["tables"]["jobs"]["rows"] = (
            values[:-1] if changed == "missing-job" else values + values[:1]
        )
    with pytest.raises(AssertionError):
        assert_setup_delta(before, after, target)


@pytest.mark.parametrize(
    "change", ["float", "bool", "decimal", "string", "sql-type", "missing", "scope"]
)
def test_driver_and_server_job_type_receipts_cannot_substitute(change):
    fixture = native_example()
    observed = job_types(fixture)
    values = {"float": 125000.0, "bool": True, "decimal": Decimal(125000), "string": "125000"}
    if change in values:
        observed[0]["reserved"] = values[change]
    elif change == "sql-type":
        observed[0]["reserved_type"] = "numeric"
    elif change == "missing":
        observed.pop()
    else:
        observed[0]["project_id"] = "0" * 32
    with pytest.raises(AssertionError):
        assert_job_types(fixture.before, observed)


def test_original_native_observer_refusal_has_exact_exception_and_amount(monkeypatch):
    fixture, manifest, target, watch, entry, stages, error = refused(monkeypatch)
    assert_native_preparation(entry, fixture, manifest, watch)
    assert_job_cap_refusal(fixture, manifest, target, entry, stages, error, watch)
    assert entry["amount_frames"][0]["amount"] == 125000
    assert entry["traceback"]["preparation_frames"][0]["line"] == 177


def test_native_observer_cannot_credit_same_code_earlier_refusal(monkeypatch):
    fixture, manifest, target, watch, entry, stages, error = refused(monkeypatch, earlier=True)
    assert error.code == "ledger_exposure_refused"
    assert entry["traceback"]["preparation_frames"][0]["line"] == 119
    with pytest.raises(AssertionError):
        assert_job_cap_refusal(fixture, manifest, target, entry, stages, error, watch)


@pytest.mark.parametrize(
    "change",
    [
        "financial-float",
        "manifest-float",
        "handle",
        "exception",
        "rollback",
        "commit",
        "close-order",
    ],
)
def test_native_observation_rejects_changed_identity_type_or_cleanup(change, monkeypatch):
    fixture, manifest, target, watch, entry, stages, error = refused(monkeypatch)
    if change == "financial-float":
        entry["financial"]["job"][0]["reserved"] = 125000.0
    elif change == "manifest-float":
        entry["manifest"]["accounts"][0]["limit_microusd"] = 245000.0
    elif change == "handle":
        entry["raw_id"] += 1
    elif change == "exception":
        error = MigrationRefused("ledger_exposure_refused")
    elif change == "rollback":
        watch.outcome.confirmed_precommit_rollback = False
    elif change == "commit":
        watch.outcome.commit_attempted = True
    else:
        watch.markers.reverse()
    with pytest.raises(AssertionError):
        assert_native_preparation(entry, fixture, manifest, watch)
        assert_job_cap_refusal(fixture, manifest, target, entry, stages, error, watch)


def test_native_delegate_baseexception_is_forwarded_without_receipt(monkeypatch):
    fixture = native_example()
    watch, context = native_watch(fixture)
    error = KeyboardInterrupt("native-money-control")
    calls = []

    def failed(*args):
        calls.append(args)
        raise error

    monkeypatch.setattr(ledger_service, "_prepare_ledger", failed)
    with (
        observe_money(watch, monkeypatch, lambda *args: None) as (entries, stages),
        pytest.raises(KeyboardInterrupt) as caught,
    ):
        ledger_service._prepare_ledger(
            context, validate_ledger_manifest(money_manifest(fixture)), watch.work
        )
    assert caught.value is error and len(calls) == 1
    assert entries[0]["amount_frames"] == [] and "prepared" not in entries[0]
    assert stages == ["prepare.enter", "prepare.refused"]


def test_exact_native_result_preserves_raw_types_and_one_economic_amount(monkeypatch):
    args = successful(monkeypatch)
    raw_before = typed(args[4])
    assert_exact_result(*args)
    assert typed(args[4]) == raw_before
    accounts = rows(args[4], "budget_accounts")
    assert sum(row["held_microusd"] for row in accounts if row["scope"] == "job") == EXACT_AMOUNT
    assert [row["held_microusd"] for row in accounts if row["scope"] == "project"] == [EXACT_AMOUNT]
    assert [row["held_microusd"] for row in accounts if row["scope"] == "organization"] == [
        EXACT_AMOUNT
    ]
    other = [row for row in accounts if row["scope"] == "job"][1:]
    assert [row["limit_microusd"] for row in other] == [10000000, 5000000]
    assert [row["held_microusd"] for row in other] == [0, 0]


@pytest.mark.parametrize(
    "change",
    [
        "account-float",
        "account-bool",
        "account-decimal",
        "account-string",
        "rounded",
        "other-cap",
        "double",
        "receipt-float",
        "sql-type",
        "missing-account",
        "opening-json-float",
        "manifest-json-bool",
        "raw-json-float",
        "raw-json-duplicate",
        "raw-json-missing",
        "raw-json-extra",
        "inspection-type",
        "prepared-type",
        "naive-time",
        "wrong-time",
        "backfill-type",
    ],
)
def test_native_result_rejects_rounded_coerced_or_incomplete_evidence(change, monkeypatch):
    args = list(successful(monkeypatch))
    after, inspection, types, texts = args[4:8]
    invalid = {
        "account-float": 0.0,
        "account-bool": False,
        "account-decimal": Decimal(0),
        "account-string": "0",
    }
    if change in invalid:
        replace_native_cell(after, "budget_accounts", 0, "accounted_microusd", invalid[change])
    elif change == "rounded":
        replace_native_cell(after, "budget_accounts", 0, "held_microusd", 2**53)
    elif change == "other-cap":
        replace_native_cell(after, "budget_accounts", 3, "limit_microusd", EXACT_AMOUNT)
    elif change == "double":
        args[3] = args[3].model_copy(update={"imported_opening_microusd": EXACT_AMOUNT * 3})
    elif change == "receipt-float":
        args[3] = args[3].model_copy(update={"sequence": 0.0})
    elif change == "sql-type":
        types[0]["limit_type"] = "numeric"
    elif change == "missing-account":
        types.pop()
    elif change in ("opening-json-float", "manifest-json-bool"):
        index = next(
            i
            for i, row in enumerate(rows(after, "migration_progress"))
            if (row["phase"] == "ledger_opening") == (change == "opening-json-float")
        )
        cursor = rows(after, "migration_progress")[index]["cursor"]
        if change == "opening-json-float":
            cursor["jobs"][1]["legacy_reserved_microusd"] = 0.0
        else:
            cursor["sequence"] = False
    elif change == "raw-json-float":
        texts[0]["cursor"] = texts[0]["cursor"].replace('"sequence": 0', '"sequence": 0.0')
    elif change == "raw-json-duplicate":
        texts[0]["cursor"] = '{"sequence": 0,' + texts[0]["cursor"][1:]
    elif change == "raw-json-missing":
        texts.pop()
    elif change == "raw-json-extra":
        texts.append(deepcopy(texts[0]))
    elif change == "inspection-type":
        inspection["manifest_count"] = True
    elif change == "prepared-type":
        args[2]["jobs"][1]["legacy_reserved_microusd"] = 0.0
    elif change == "backfill-type":
        replace_native_cell(after, "jobs", 1, "legacy_reserved_microusd", False)
    else:
        row = rows(after, "migration_progress")[0]
        value = row["updated_at"]
        value = (
            value.replace(tzinfo=None)
            if change == "naive-time"
            else value + timedelta(microseconds=1)
        )
        replace_native_cell(after, "migration_progress", 0, "updated_at", value)
    with pytest.raises((AssertionError, ValueError)):
        assert_exact_result(*args)


def test_only_expected_comparison_timestamps_convert_to_utc(monkeypatch):
    args = successful(monkeypatch)
    after = args[4]
    zone = timezone(timedelta(hours=3))
    for name, fields in [
        ("budget_accounts", ("period_start", "period_end")),
        ("migration_progress", ("updated_at",)),
    ]:
        for index, row in enumerate(rows(after, name)):
            for field in fields:
                replace_native_cell(after, name, index, field, row[field].astimezone(zone))
    preserved = typed(after)
    assert_exact_result(*args)
    assert typed(after) == preserved


@pytest.mark.parametrize("fail_update", [None, 0, 1, 2])
def test_setup_bound_bigint_parameters_and_commit_receipt_follow_real_context_exit(
    monkeypatch, fail_update
):
    import ledger_money_postgres_fixture as target_module

    fixture = native_example()
    before = deepcopy(fixture.before)
    expected_setup(fixture)
    refreshed = fixture
    fixture = deepcopy(fixture)
    fixture.before = before
    fixture.encrypted = {str(i): "a" * 64 for i in range(18)}
    refreshed.encrypted = fixture.encrypted
    actions, recorded, statements = [], [], []
    failure = RuntimeError("controlled setup failure")

    class Connection:
        def exec_driver_sql(self, sql):
            actions.append(sql)
            return SimpleNamespace(one=lambda: ("fixture_owner", "fixture_database"))

        def execute(self, statement, values):
            compiled = statement.compile(dialect=postgresql.dialect())
            assert isinstance(compiled.binds["amount"].type, BigInteger)
            statements.append((str(statement), deepcopy(values)))
            if len(statements) - 1 == fail_update:
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
    monkeypatch.setattr(target_module, "native_snapshot", lambda *args: before)
    monkeypatch.setattr(target_module, "encrypted_files", lambda *args: fixture.encrypted)
    monkeypatch.setattr(target_module, "drain", lambda *args: actions.append("drain"))
    monkeypatch.setattr(target_module, "observe_inputs", lambda *args: refreshed)
    pg = {
        "owner_role": "fixture_owner",
        "owner": SimpleNamespace(url=SimpleNamespace(database="fixture_database")),
    }

    def record(name, value):
        recorded.append((name, value, list(actions)))

    if fail_update is not None:
        with pytest.raises(RuntimeError) as caught:
            exact_predecessor(fixture, pg, record)
        assert caught.value is failure
        assert actions[-2:] == ["rollback", "drain"] and not recorded
    else:
        result, selected = exact_predecessor(fixture, pg, record)
        assert result is refreshed and selected == fixture.jobs[0]["id"]
        assert [row[1]["amount"] for row in statements] == [EXACT_AMOUNT, 0, 0]
        assert recorded[0][0] == "setup_commit" and recorded[0][2][-1] == "commit"
        assert recorded[0][1]["acknowledged"] is True
        assert_setup_delta(before, result.before, selected)
    assert all(type(row[1]["amount"]) is int for row in statements)


@pytest.mark.parametrize("handles", [[], [object()], [object(), object()]])
def test_native_observer_refuses_unproved_handle_before_delegate(monkeypatch, handles):
    fixture = native_example()
    watch, context = native_watch(fixture)
    watch.trace.handles = handles
    calls = []

    def unreachable(*args):
        calls.append(args)
        raise AssertionError("unproved handle delegated")

    monkeypatch.setattr(ledger_service, "_prepare_ledger", unreachable)
    with (
        observe_money(watch, monkeypatch, lambda *args: None) as (entries, stages),
        pytest.raises(AssertionError),
    ):
        ledger_service._prepare_ledger(
            context, validate_ledger_manifest(money_manifest(fixture)), watch.work
        )
    assert calls == entries == stages == []


@pytest.mark.parametrize("change", ["original-job-type", "unrelated-json-type", "unrelated-time"])
def test_positive_preservation_is_typed_for_every_unrelated_predecessor_cell(change, monkeypatch):
    args = successful(monkeypatch)
    after = args[4]
    if change == "original-job-type":
        replace_native_cell(after, "jobs", 1, "cancel", 0)
    elif change == "unrelated-json-type":
        replace_native_cell(after, "unrelated", 0, "data", {"integer": False, "boolean": False})
    else:
        replace_native_cell(after, "unrelated", 0, "created_at", datetime(2026, 1, 1))
    with pytest.raises(AssertionError):
        assert_exact_result(*args)


@pytest.mark.parametrize("corrupt", [False, True])
def test_actual_refresh_uses_native_source_facts_and_keeps_case_identity(monkeypatch, corrupt):
    import ledger_money_postgres_fixture as module
    from ledger_provisioning_fixture import SOURCE_FIELDS, ProvisioningFixture, source_fingerprint

    source = {name: [] for name in SOURCE_FIELDS}
    source["jobs"] = [
        (
            "a" * 32,
            "run",
            1.0,
            "b" * 64,
            "failed",
            None,
            None,
            False,
            EXACT_AMOUNT,
            EXACT_AMOUNT,
            None,
            None,
            None,
        )
    ]
    example = native_example()
    expected_setup(example)
    before = deepcopy(example.before)
    observed = job_types(example)
    protected = {str(i): "a" * 64 for i in range(18)}
    closes = []

    class Connection:
        def exec_driver_sql(self, sql):
            assert sql == module.JOB_TYPES_SQL
            return SimpleNamespace(mappings=lambda: observed)

    class Engine:
        @contextmanager
        def connect(self):
            try:
                yield Connection()
            finally:
                closes.append("connection.closed")

    case = SimpleNamespace(engine=Engine(), adoption={"unchanged": True})
    fixture = ProvisioningFixture(
        case, {}, {}, "old", protected, [], example.organization, example.project
    )
    monkeypatch.setattr(module, "native_snapshot", lambda *args: before)
    monkeypatch.setattr(module, "source_rows", lambda *args: source)
    monkeypatch.setattr(module, "drain", lambda *args: closes.append("drain"))
    monkeypatch.setattr(
        module,
        "encrypted_files",
        lambda *args: {**protected, "0": "b" * 64} if corrupt else protected,
    )
    if corrupt:
        with pytest.raises(AssertionError):
            module.observe_inputs(fixture, {}, lambda *args: None)
    else:
        result = module.observe_inputs(fixture, {}, lambda *args: None)
        assert result is not fixture and result.case is case
        assert result.before is before and result.original is source
        assert result.source == source_fingerprint(source) and result.jobs == example.jobs
        assert (
            fixture.before == {}
            and fixture.source == "old"
            and case.adoption == {"unchanged": True}
        )
    assert closes == ["connection.closed", "drain"]
