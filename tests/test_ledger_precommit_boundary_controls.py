"""Offline discrimination controls; synthetic receipts never establish native execution."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from ledger_precommit_boundary_fixture import (
    ALTERS,
    INDEXES,
    PROBES,
    QUICK_CHECK,
    STAGES,
    TABLES,
    assert_preserved,
    assert_target,
    native_statements,
    returned_sql,
)
from ledger_precommit_boundary_observer import assert_boundary

from agent_rewind.migrations.schema import ADMISSION, LEDGER, MigrationRefused


def example(stage):
    import sqlite3

    raw, engine = object(), object()
    connection = SimpleNamespace(engine=engine)
    work = SimpleNamespace(
        _raw=raw, _connection=connection, timeout_seconds=5, previous_timeout=5000
    )
    identity = {
        "raw_id": id(raw),
        "work_id": id(work),
        "engine_id": id(engine),
        "connection_id": id(connection),
    }
    fixture = SimpleNamespace(
        jobs=[
            {"id": token * 32, "reserved": reserved}
            for token, reserved in (("a", 125000), ("b", 85000), ("c", 35000))
        ]
    )
    manifest = {"manifest_id": "d" * 32, "operation": "initialize"}
    first = MigrationRefused("migration_busy")
    events, actions = [], []

    def emit(sql, method="execute"):
        events.extend(
            [
                ("c_call", "bootstrap", id(raw), method),
                ("sql", "bootstrap", id(raw), sql),
                *([("sql", "bootstrap", id(raw), QUICK_CHECK)] if sql in ALTERS else []),
                ("c_return", "bootstrap", id(raw), method),
            ]
        )

    emit("BEGIN EXCLUSIVE")
    upgrade = {
        **identity,
        "original_caller": True,
        "line": 251,
        "manifest": manifest,
        "entered_at": len(events),
        "authorizer_start": len(actions),
    }
    for sql in (
        *ALTERS,
        *["CREATE TABLE " + table + " (synthetic_columns)" for table in TABLES],
        *[
            f"CREATE INDEX {name} ON {table}({name.removeprefix('ar7_calls_')})"
            if table == "provider_calls"
            else "CREATE INDEX ar7_entries_account_id ON budget_entries(account_id)"
            for name, table in INDEXES
        ],
        f"UPDATE alembic_version SET version_num='{LEDGER}' "
        f"WHERE alembic_version.version_num = '{ADMISSION}'",
    ):
        emit(sql)
    actions.extend([(sqlite3.SQLITE_ALTER_TABLE, "main", "jobs", None, None)] * 2)
    actions.extend((sqlite3.SQLITE_CREATE_TABLE, name, None, "main", None) for name in TABLES)
    actions.extend(
        (sqlite3.SQLITE_CREATE_INDEX, name, table, "main", None) for name, table in INDEXES
    )
    upgrade.update(returned_at=len(events), authorizer_end=len(actions))
    receipt = {
        "stage": stage,
        "identity": identity,
        "upgrades": [upgrade],
        "writes": [],
        "backfill_executions": [],
        "probes": [],
        "injections": [],
    }
    if stage == "first-backfill":
        write = {
            **identity,
            "original_caller": True,
            "line": 254,
            "name": "jobs.backfill",
            "values": {"id": "a" * 32, "opening": 125000},
            "entered_at": len(events),
            "authorizer_start": len(actions),
        }
        execution = {
            key: value
            for key, value in write.items()
            if key not in {"original_caller", "line", "authorizer_start"}
        }
        emit("PRAGMA busy_timeout=5000")
        emit(
            "UPDATE jobs SET legacy_reserved_microusd=125000, lease_generation=0 "
            "WHERE id='" + "a" * 32 + "'"
        )
        actions.extend(
            (sqlite3.SQLITE_UPDATE, "jobs", name, "main", None)
            for name in ("legacy_reserved_microusd", "lease_generation")
        )
        write.update(returned_at=len(events), authorizer_end=len(actions))
        execution.update(returned_at=len(events), rowcount=1)
        receipt["writes"].append(write)
        receipt["backfill_executions"].append(execution)
    receipt["probe_start"] = len(events)
    rows = (
        [(LEDGER,)],
        [
            (job["id"], 0, job["reserved"] if stage == "first-backfill" and i == 0 else 0)
            for i, job in enumerate(fixture.jobs)
        ],
        [(0, 0, 0)],
    )
    for (name, sql), actual in zip(PROBES, rows, strict=True):
        probe = {**identity, "name": name, "sql": sql, "entered_at": len(events)}
        emit("PRAGMA busy_timeout=5000")
        emit(sql)
        probe.update(returned_at=len(events), rows=actual)
        receipt["probes"].append(probe)
    receipt.update(probe_end=len(events), probe_work=6)
    receipt["injections"].append(
        {
            **identity,
            "position": len(events),
            "type": "MigrationRefused",
            "code": "migration_busy",
            "exception_id": id(first),
        }
    )
    markers = [
        ("boundary.inject", id(raw), len(events)),
        ("rollback.before_native", id(raw), len(events)),
    ]
    emit("ROLLBACK", method="rollback")
    markers.append(("rollback.native_ack", id(raw), len(events)))
    emit("PRAGMA busy_timeout=5000")
    markers.extend(
        (name, id(raw), len(events))
        for name in (
            "connection.close.before",
            "connection.close.return",
            "command.exit",
        )
    )
    watch = SimpleNamespace(
        work=work,
        engine=engine,
        trace=SimpleNamespace(
            raws=[raw],
            events=events,
            sql=lambda: [row[3] for row in events if row[0] == "sql"],
        ),
        actions=actions,
        markers=markers,
        faults=[],
        command_boundary={
            "trace_end": len(events),
            "raw_closed": False,
            "in_transaction": False,
            "receipt_clean": True,
            "receipt_completed": True,
            "checkedout": 0,
        },
        outcome=SimpleNamespace(
            confirmed_precommit_rollback=True,
            rollback_attempted=True,
            rollback_acknowledged=True,
            commit_attempted=False,
            commit_acknowledged=False,
            cleanup_failed=False,
        ),
        assert_single_attempt=lambda: None,
    )
    return receipt, fixture, manifest, first, watch


def check(items, *, raised=None):
    receipt, fixture, manifest, first, watch = items
    assert_boundary(receipt, fixture, manifest, first, raised or first, watch)


@pytest.mark.parametrize("stage", STAGES)
def test_complete_synthetic_stage_receipt_is_accepted(stage):
    check(example(stage))


@pytest.mark.parametrize(
    "mutation",
    [
        "no-return",
        "native-error",
        "wrong-raw",
        "wrong-method",
        "extra-sql",
        "bad-version",
        "missing-ddl",
        "wrong-index",
        "wrong-authorizer-table",
        "trigger",
        "wrong-caller",
        "wrong-line",
        "wrong-manifest",
        "wrong-work",
        "duplicate-upgrade",
    ],
)
def test_upgrade_oracle_rejects_incomplete_or_misattributed_stage(mutation):
    items = example("after-ddl")
    receipt, _, _, _, watch = items
    upgrade = receipt["upgrades"][0]
    start = upgrade["entered_at"]
    event = list(watch.trace.events[start + 3])
    if mutation == "no-return":
        event[0] = "missing"
    elif mutation == "native-error":
        event[0] = "c_exception"
    elif mutation == "wrong-raw":
        event[2] += 1
    elif mutation == "wrong-method":
        event[3] = "executemany"
    elif mutation == "extra-sql":
        event[0], event[3] = "sql", "SELECT 1"
    elif mutation in {"bad-version", "missing-ddl", "wrong-index"}:
        offset = {"bad-version": 33, "missing-ddl": 1, "wrong-index": 18}[mutation]
        current = list(watch.trace.events[start + offset])
        current[3] = {
            "bad-version": "UPDATE alembic_version SET version_num='wrong'",
            "missing-ddl": "SELECT 1",
            "wrong-index": "CREATE INDEX unexpected ON jobs(id)",
        }[mutation]
        watch.trace.events[start + offset] = tuple(current)
    elif mutation == "wrong-authorizer-table":
        action = list(watch.actions[0])
        action[2] = "other"
        watch.actions[0] = tuple(action)
    elif mutation == "trigger":
        action = list(watch.actions[0])
        action[4] = "unexpected_trigger"
        watch.actions[0] = tuple(action)
    elif mutation == "wrong-caller":
        upgrade["original_caller"] = False
    elif mutation == "wrong-line":
        upgrade["line"] += 1
    elif mutation == "wrong-manifest":
        upgrade["manifest"] = {**upgrade["manifest"], "manifest_id": "e" * 32}
    elif mutation == "wrong-work":
        upgrade["work_id"] += 1
    elif mutation == "duplicate-upgrade":
        receipt["upgrades"].append(deepcopy(upgrade))
    watch.trace.events[start + 3] = tuple(event)
    with pytest.raises((AssertionError, ValueError)):
        check(items)


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong-job",
        "wrong-amount",
        "float-rowcount",
        "zero-rowcount",
        "second-write",
        "missing-execution",
        "earlier-execution",
        "native-error",
        "wrong-sql",
        "wrong-column",
        "wrong-line",
        "wrong-execution-raw",
    ],
)
def test_backfill_oracle_requires_the_exact_first_native_row_update(mutation):
    items = example("first-backfill")
    receipt, _, _, _, watch = items
    write, execution = receipt["writes"][0], receipt["backfill_executions"][0]
    if mutation == "wrong-job":
        write["values"] = {**write["values"], "id": "b" * 32}
    elif mutation == "wrong-amount":
        write["values"] = {**write["values"], "opening": 0}
    elif mutation == "float-rowcount":
        execution["rowcount"] = 1.0
    elif mutation == "zero-rowcount":
        execution["rowcount"] = 0
    elif mutation == "second-write":
        receipt["writes"].append(deepcopy(write))
    elif mutation == "missing-execution":
        receipt["backfill_executions"].clear()
    elif mutation == "earlier-execution":
        execution["entered_at"] = 0
    elif mutation in {"native-error", "wrong-sql"}:
        offset = 2 if mutation == "native-error" else 1
        event = list(watch.trace.events[write["entered_at"] + offset])
        if mutation == "native-error":
            event[0] = "c_exception"
        else:
            event[3] = "UPDATE jobs SET reserved=0"
        watch.trace.events[write["entered_at"] + offset] = tuple(event)
    elif mutation == "wrong-column":
        offset = write["authorizer_start"]
        action = list(watch.actions[offset])
        action[2] = "reserved"
        watch.actions[offset] = tuple(action)
    elif mutation == "wrong-line":
        write["line"] += 1
    elif mutation == "wrong-execution-raw":
        execution["raw_id"] += 1
    with pytest.raises((AssertionError, ValueError)):
        check(items)


@pytest.mark.parametrize(
    "mutation",
    [
        "version",
        "job-amount",
        "generation",
        "collateral-job",
        "native-type",
        "nonempty-table",
        "native-count-type",
        "probe-query",
        "probe-return",
        "probe-work",
        "probe-identity",
        "injection-count",
        "exception-id",
        "wrong-exception",
        "late-write",
        "commit",
        "no-rollback",
        "cleanup",
        "dirty-pool",
        "raw-closed",
        "wrong-marker-raw",
        "wrong-marker-order",
    ],
)
def test_probe_and_cleanup_oracle_rejects_false_boundary_claims(mutation):
    items = example("first-backfill")
    receipt, _, _, _, watch = items
    probes = receipt["probes"]
    raised = None
    if mutation == "version":
        probes[0]["rows"] = [(ADMISSION,)]
    elif mutation in {"job-amount", "generation", "collateral-job", "native-type"}:
        row = list(probes[1]["rows"][0 if mutation != "collateral-job" else 1])
        field = 1 if mutation == "generation" else 2
        row[field] = 125000.0 if mutation == "native-type" else 17
        probes[1]["rows"][0 if mutation != "collateral-job" else 1] = tuple(row)
    elif mutation == "nonempty-table":
        probes[2]["rows"] = [(0, 1, 0)]
    elif mutation == "native-count-type":
        probes[2]["rows"] = [(False, 0, 0)]
    elif mutation == "probe-query":
        probes[0]["sql"] = "SELECT 1"
    elif mutation == "probe-return":
        offset = probes[0]["returned_at"] - 1
        event = list(watch.trace.events[offset])
        event[0] = "c_exception"
        watch.trace.events[offset] = tuple(event)
    elif mutation == "probe-work":
        receipt["probe_work"] = 0
    elif mutation == "probe-identity":
        probes[0]["raw_id"] += 1
    elif mutation == "injection-count":
        receipt["injections"].append(deepcopy(receipt["injections"][0]))
    elif mutation == "exception-id":
        receipt["injections"][0]["exception_id"] += 1
    elif mutation == "wrong-exception":
        raised = MigrationRefused("migration_busy")
    elif mutation == "late-write":
        offset = receipt["injections"][0]["position"] + 1
        event = list(watch.trace.events[offset])
        event[3] = "UPDATE jobs SET reserved=0"
        watch.trace.events[offset] = tuple(event)
    elif mutation == "commit":
        watch.outcome.commit_attempted = True
    elif mutation == "no-rollback":
        watch.outcome.rollback_acknowledged = False
    elif mutation == "cleanup":
        watch.outcome.cleanup_failed = True
    elif mutation == "dirty-pool":
        watch.command_boundary["checkedout"] = 1
    elif mutation == "raw-closed":
        watch.command_boundary["raw_closed"] = True
    elif mutation == "wrong-marker-raw":
        marker = list(watch.markers[2])
        marker[1] += 1
        watch.markers[2] = tuple(marker)
    elif mutation == "wrong-marker-order":
        watch.markers[1], watch.markers[2] = watch.markers[2], watch.markers[1]
    with pytest.raises((AssertionError, ValueError)):
        check(items, raised=raised)


@pytest.mark.parametrize("kind", ["sql-without-call", "nested-call", "unfinished-call"])
def test_native_pairing_requires_one_complete_driver_operation(kind):
    events = {
        "sql-without-call": [("sql", "body", 1, "SELECT 1")],
        "nested-call": [
            ("c_call", "body", 1, "execute"),
            ("c_call", "body", 1, "execute"),
        ],
        "unfinished-call": [("c_call", "body", 1, "execute")],
    }[kind]
    with pytest.raises(AssertionError):
        native_statements(events, 1)


@pytest.mark.parametrize(
    "mutation",
    ["none", "schema", "column", "cell", "source", "digest", "ciphertext", "missing-object"],
)
def test_full_predecessor_preservation_is_not_a_table_count_check(monkeypatch, mutation):
    import ledger_precommit_boundary_fixture as target

    before = {
        "schema": [("table", "jobs", "jobs", "original SQL")],
        "tables": {"jobs": {"columns": ("id", "reserved"), "rows": (("a" * 32, 125000),)}},
    }
    original = {"jobs": [("a" * 32, 125000)]}
    hashes = {str(i): "a" * 64 for i in range(18)}
    fixture = SimpleNamespace(
        case=SimpleNamespace(path="no-database"),
        before=before,
        original=original,
        source="b" * 64,
        encrypted=hashes,
    )
    after, rows, encrypted = deepcopy(before), deepcopy(original), dict(hashes)
    if mutation == "schema":
        after["schema"][0] = ("table", "jobs", "jobs", "changed SQL")
    elif mutation == "column":
        after["tables"]["jobs"]["columns"] = ("id", "budget")
    elif mutation == "cell":
        after["tables"]["jobs"]["rows"] = (("a" * 32, 125001),)
    elif mutation == "source":
        rows["jobs"][0] = ("a" * 32, 0)
    elif mutation == "ciphertext":
        encrypted["0"] = "c" * 64
    elif mutation == "missing-object":
        encrypted.pop("0")
    monkeypatch.setattr(target, "snapshot", lambda _: after)
    monkeypatch.setattr(target, "source_rows", lambda _: rows)
    monkeypatch.setattr(target, "ciphertexts", lambda _: encrypted)
    monkeypatch.setattr(
        target, "source_fingerprint", lambda _: "c" * 64 if mutation == "digest" else "b" * 64
    )
    if mutation == "none":
        assert assert_preserved(fixture)["snapshot"] == before
    else:
        with pytest.raises(AssertionError):
            assert_preserved(fixture)


@pytest.mark.parametrize(
    "mutation",
    [
        "none",
        "second-alter",
        "missing",
        "extra",
        "wrong-table",
        "wrong-callback",
        "wrong-alter",
        "wrong-primary",
        "no-permission",
    ],
)
def test_only_exact_selected_alter_internal_callback_is_accepted(mutation):
    primary = ALTERS[1] if mutation == "second-alter" else ALTERS[0]
    sql = [primary, QUICK_CHECK]
    if mutation == "missing":
        sql.pop()
    elif mutation == "extra":
        sql.append(QUICK_CHECK)
    elif mutation == "wrong-table":
        sql[1] = "-- PRAGMA 'main'.quick_check='other'"
    elif mutation == "wrong-callback":
        sql[1] = "SELECT 1"
    elif mutation == "wrong-alter":
        sql[0] = primary.replace("DEFAULT 0", "DEFAULT 1")
    elif mutation == "wrong-primary":
        sql[0] = "SELECT 1"
    events = [
        ("c_call", "body", 1, "execute"),
        *[("sql", "body", 1, value) for value in sql],
        ("c_return", "body", 1, "execute"),
    ]
    if mutation in {"none", "second-alter"}:
        assert returned_sql(events, 1, allow_alter_internal=True) == [primary]
    else:
        with pytest.raises(AssertionError):
            returned_sql(events, 1, allow_alter_internal=mutation != "no-permission")


@pytest.mark.parametrize(
    "setter",
    [
        "PRAGMA busy_timeout=1",
        "PRAGMA busy_timeout=5000",
        "PRAGMA busy_timeout=0",
        "PRAGMA busy_timeout=5001",
        "PRAGMA busy_timeout=-1",
        "PRAGMA busy_timeout=1.0",
        "SELECT 1",
    ],
)
def test_every_probe_and_backfill_requires_bounded_timeout_setter(setter):
    events = [
        event
        for sql in (setter, "SELECT 2")
        for event in (
            ("c_call", "body", 1, "execute"),
            ("sql", "body", 1, sql),
            ("c_return", "body", 1, "execute"),
        )
    ]
    if setter in {"PRAGMA busy_timeout=1", "PRAGMA busy_timeout=5000"}:
        assert_target(events, 1, "SELECT 2", 5)
    else:
        with pytest.raises(AssertionError):
            assert_target(events, 1, "SELECT 2", 5)
