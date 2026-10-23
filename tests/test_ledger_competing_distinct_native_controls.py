"""Offline typed-state and native-outcome adversaries; no database or subprocess."""

import hashlib
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace

import ledger_postgres_conflict_fixture as adapter
import psycopg
import pytest
from ledger_competing_distinct import CASES
from ledger_competing_distinct_postgres import (
    assert_added_project,
    assert_native_conflict,
    prove_native_collision,
)
from ledger_postgres_competing_fixture import TRY_LOCK_SQL
from test_ledger_competing_distinct_controls import example, table

from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused
from agent_rewind.migrations.service import MIGRATOR_LOCK


def native_example(case="scope-start"):
    before, first, winner, loser = example(case)
    accounts = before["tables"]["budget_accounts"]
    native = []
    for values in accounts["rows"]:
        row = list(values)
        for name in ("period_start", "period_end"):
            index = accounts["columns"].index(name)
            row[index] = datetime.fromisoformat(row[index].replace("Z", "+00:00"))
        native.append(tuple(row))
    accounts["rows"] = tuple(native)
    return before, first, winner, loser


@pytest.mark.parametrize("case", CASES)
def test_native_collision_comparison_preserves_original_typed_snapshot(case):
    before, _, winner, loser = native_example(case)
    original = deepcopy(before)
    proof = prove_native_collision(before, winner, loser, case)
    assert before == original
    assert proof["native_absence"] and proof["collisions"]
    assert proof["projects"] == [] or len(proof["projects"]) == 2


@pytest.mark.parametrize("value", ["2000-01-01T00:00:00.000000Z", datetime(2000, 1, 1)])
def test_native_collision_comparison_rejects_untyped_or_naive_time(value):
    before, _, winner, loser = native_example()
    accounts = before["tables"]["budget_accounts"]
    row = list(accounts["rows"][0])
    row[accounts["columns"].index("period_start")] = value
    accounts["rows"] = (tuple(row),)
    with pytest.raises(AssertionError):
        prove_native_collision(before, winner, loser, "scope-start")


def test_native_absence_rejects_existing_key_with_distinct_id_and_aware_timestamp():
    before, _, winner, loser = native_example()
    account = deepcopy(winner["accounts"][0])
    account["id"] = "f" * 32
    for field in ("period_start", "period_end"):
        account[field] = datetime.fromisoformat(account[field].replace("Z", "+00:00"))
    before["tables"]["budget_accounts"] = table([account])
    with pytest.raises(AssertionError):
        prove_native_collision(before, winner, loser, "scope-start")


def project_snapshots():
    original = {
        "id": "1" * 32,
        "organization_id": "2" * 32,
        "name": "Original",
        "created_at": datetime(2020, 1, 1, tzinfo=UTC),
        "run_sequence": 9,
    }
    before = {
        "catalog": {"projects": "unchanged"},
        "authority": {"owner": "owner", "acl": None},
        "tables": {"projects": table([original]), "preserved": table([{"cipher": "unchanged"}])},
    }
    after = deepcopy(before)
    after["tables"]["projects"] = table(
        [
            original,
            {**original, "id": "3" * 32, "name": "Independent project", "run_sequence": 0},
        ]
    )
    return before, after


def test_added_project_keeps_typed_created_time_and_predecessor_authority():
    before, after = project_snapshots()
    added = assert_added_project(before, after, "1" * 32, "3" * 32)
    assert type(added["created_at"]) is datetime and added["created_at"].tzinfo is UTC


@pytest.mark.parametrize(
    "change", ["authority", "catalog", "other-table", "organization", "timestamp"]
)
def test_added_project_oracle_rejects_collateral_changes(change):
    before, after = project_snapshots()
    if change == "authority":
        after["authority"]["owner"] = "other"
    elif change == "catalog":
        after["catalog"]["projects"] = "changed"
    elif change == "other-table":
        after["tables"]["preserved"]["rows"][0] = ("changed",)
    else:
        projects = after["tables"]["projects"]
        row = list(projects["rows"][1])
        if change == "organization":
            row[projects["columns"].index("organization_id")] = "4" * 32
        else:
            row[projects["columns"].index("created_at")] = datetime(2020, 1, 1)
        projects["rows"][1] = tuple(row)
    with pytest.raises(AssertionError):
        assert_added_project(before, after, "1" * 32, "3" * 32)


def native_message():
    raw, engine, backend = 101, 202, 303
    events = [
        ["bootstrap", "connect-call", None, None],
        ["bootstrap", "internal-connect", None, None],
        ["bootstrap", "connect-return", raw, None],
        ["ordinary", "sql-call", raw, TRY_LOCK_SQL],
        ["ordinary", "sql-return", raw, TRY_LOCK_SQL],
        ["ordinary", "try-lock-fetched", raw, True],
        ["ordinary", "sql-call", raw, "SELECT id FROM budget_accounts"],
        ["ordinary", "sql-return", raw, "SELECT id FROM budget_accounts"],
        ["cleanup", "rollback-call", raw, None],
        ["cleanup", "command", raw, "ROLLBACK"],
        ["cleanup", "rollback-return", raw, None],
        ["cleanup", "close-call", raw, None],
        ["cleanup", "close-return", raw, None],
    ]
    observed = {
        "faults": [],
        "work": [{"ordinary": 50}],
        "outcomes": [
            {
                "begin_attempted": True,
                "begun": True,
                "commit_attempted": False,
                "commit_acknowledged": False,
                "rollback_attempted": True,
                "rollback_acknowledged": True,
                "cleanup_failed": False,
            }
        ],
        "native_trace": events,
        "native_parameters": [
            {
                "phase": phase,
                "raw_id": actual_raw,
                "sql_sha256": hashlib.sha256(sql.encode()).hexdigest(),
                "outcome": "return",
                "parameter_count": int(sql == TRY_LOCK_SQL),
            }
            for phase, kind, actual_raw, sql in events
            if kind == "sql-call"
        ],
        "markers": [
            ["conflict.classify.enter", raw, 8],
            ["conflict.classify.refused", raw, 8],
            ["connection.close.before", raw, 11],
            ["command.exit", raw, 13],
        ],
        "command_boundary": {
            "raw_id": raw,
            "raw_closed": True,
            "connection_closed": True,
            "claim_released": True,
            "claim_absent": True,
            "engine_poisoned": False,
            "trace_end": 13,
        },
        "physical": [
            {
                "action": "rollback",
                "raw_id": raw,
                "closed_before": False,
                "closed_after": False,
                "status_before": 2,
                "status_after": 0,
                "trace_end": 11,
            },
            {
                "action": "close",
                "raw_id": raw,
                "closed_before": False,
                "closed_after": True,
                "status_before": 0,
                "status_after": None,
                "trace_end": 13,
            },
        ],
        "xids": [[raw, "123", 7]],
        "observer_units": [6, 3],
        "tuple_deltas": [[]],
    }
    witness = {
        "observation": observed,
        "try_locks": [
            {
                "fetched": True,
                "raw_id": raw,
                "sql": TRY_LOCK_SQL,
                "parameters": {"key": MIGRATOR_LOCK},
                "backend_pid": backend,
                "database": "owned",
                "role": "owner",
                "execute_return_trace_index": 4,
                "fetch_return_trace_index": 5,
            }
        ],
        "classifications": [
            {
                "raw_id": raw,
                "engine_id": engine,
                "backend": {
                    "pid": backend,
                    "database": "owned",
                    "role": "owner",
                    "transaction_status": 2,
                    "raw_closed": False,
                    "claim_released": False,
                    "connection_closed": False,
                    "work_detached": False,
                },
            }
        ],
        "refusal": {"type": "MigrationRefused", "code": "ledger_manifest_conflict"},
        "receipt": None,
        "native_errors": [
            {
                "type": "MigrationRefused",
                "code": "ledger_manifest_conflict",
                "mapped_type": "MigrationRefused",
                "mapped_code": "ledger_manifest_conflict",
                "same_error": True,
            }
        ],
        "scoped_cleanup": {
            "raw_ids": [raw],
            "closed": [True],
            "rescued_raw_ids": [],
            "errors": [],
            "engine_id": engine,
        },
    }
    return {"phase": "result", "raw_id": raw, "engine_id": engine, "witness": witness}


def test_native_conflict_observer_accepts_owned_rollback_before_physical_close():
    assert_native_conflict(native_message())


@pytest.mark.parametrize(
    "change",
    [
        "backend-pid",
        "database",
        "role",
        "idle-at-classifier",
        "released-claim",
        "wrong-raw",
        "wrong-engine",
        "tuple-write",
        "write-sql",
        "hidden-write-cte",
        "missing-rollback-ack",
        "wrong-rollback-state",
        "physical-commit",
        "late-close",
        "rescued-raw",
        "early-harness",
        "classifier-before-lock",
        "duplicate-classification",
        "replaced-error",
    ],
)
def test_native_conflict_observer_rejects_wrong_backend_write_or_uncertain_cleanup(change):
    message = native_message()
    witness = message["witness"]
    observed = witness["observation"]
    entry = witness["classifications"][0]
    if change == "backend-pid":
        entry["backend"]["pid"] += 1
    elif change in {"database", "role"}:
        entry["backend"][change] = "other"
    elif change == "idle-at-classifier":
        entry["backend"]["transaction_status"] = 0
    elif change == "released-claim":
        entry["backend"]["claim_released"] = True
    elif change == "wrong-raw":
        entry["raw_id"] += 1
    elif change == "wrong-engine":
        entry["engine_id"] += 1
    elif change == "tuple-write":
        observed["tuple_deltas"] = [
            [{"relation": ["public", "budget_accounts"], "delta": [0, 1, 0]}]
        ]
    elif change in {"write-sql", "hidden-write-cte"}:
        sql = "UPDATE budget_accounts SET held_microusd=held_microusd"
        if change == "hidden-write-cte":
            sql = "WITH written AS (" + sql + " RETURNING id) SELECT id FROM written"
        observed["native_trace"][6][3] = observed["native_trace"][7][3] = sql
        observed["native_parameters"][1]["sql_sha256"] = hashlib.sha256(sql.encode()).hexdigest()
    elif change == "missing-rollback-ack":
        observed["outcomes"][0]["rollback_acknowledged"] = False
    elif change == "wrong-rollback-state":
        observed["physical"][0]["status_after"] = 2
    elif change == "physical-commit":
        observed["physical"].append({**observed["physical"][0], "action": "commit"})
    elif change == "late-close":
        observed["physical"][1]["trace_end"] = 14
    elif change == "rescued-raw":
        witness["scoped_cleanup"]["rescued_raw_ids"] = [101]
    elif change == "early-harness":
        observed["native_trace"][12][0] = "harness-dispose"
    elif change == "classifier-before-lock":
        observed["markers"][0][2] = 4
    elif change == "duplicate-classification":
        observed["markers"].insert(0, observed["markers"][0])
    else:
        assert change == "replaced-error"
        witness["native_errors"][0]["same_error"] = False
    with pytest.raises((AssertionError, ValueError)):
        assert_native_conflict(message)


@pytest.mark.parametrize("invalid", [None, "foreign-claim", "closed", "idle", "detached"])
def test_native_classifier_adapter_keeps_owned_delegate_identity_and_restores_patches(
    monkeypatch, invalid
):
    raw = SimpleNamespace(
        closed=False,
        info=SimpleNamespace(
            transaction_status=psycopg.pq.TransactionStatus.INTRANS,
            backend_pid=303,
            dbname="owned",
            user="owner",
        ),
    )
    engine = object()
    work = SimpleNamespace(
        _raw=raw,
        _connection=SimpleNamespace(engine=engine, closed=False),
        _detached=False,
    )
    claim = SimpleNamespace(raw=raw, released=False)
    if invalid == "foreign-claim":
        claim.raw = object()
    elif invalid == "closed":
        raw.closed = True
    elif invalid == "idle":
        raw.info.transaction_status = psycopg.pq.TransactionStatus.IDLE
    elif invalid == "detached":
        work._detached = True
    marks, delegated, sent, caught, finalized = [], [], [], [], []
    watch = SimpleNamespace(
        work=work,
        engine=engine,
        claims=[claim],
        owns=lambda candidate: candidate is raw,
        mark=lambda label, candidate: marks.append((label, candidate)),
    )
    _, _, _, target = example()
    manifest = validate_ledger_manifest(target)
    context = SimpleNamespace(
        state=SimpleNamespace(model_dump=lambda **kwargs: {"status": "complete"}),
        history=SimpleNamespace(manifests=[]),
        financial={"account": []},
    )
    original = MigrationRefused("ledger_manifest_conflict")

    @contextmanager
    def observe(*args, **kwargs):
        assert kwargs == {"observe_writes": True}
        try:
            yield watch
        finally:
            finalized.append(True)

    def classify(*args):
        delegated.append(args)
        raise original

    def fake_worker(channel):
        with adapter.worker.observe_owned(observe_writes=True):
            try:
                adapter.ledger_service._classify_manifest(context, manifest, work)
            except MigrationRefused as error:
                caught.append(error)
        adapter.worker.send_frame(
            channel,
            {
                "role": "replay",
                "phase": "result",
                "raw_id": id(raw),
                "engine_id": id(engine),
                "witness": {},
            },
            42.0,
        )

    monkeypatch.setattr(adapter.worker, "observe_owned", observe)
    monkeypatch.setattr(adapter.ledger_service, "_classify_manifest", classify)
    monkeypatch.setattr(adapter.worker, "run", fake_worker)
    monkeypatch.setattr(adapter.worker, "send_frame", lambda *args: sent.append(args))
    if invalid is not None:
        with pytest.raises(AssertionError):
            adapter.run("owned-channel")
        assert delegated == [] and sent == []
    else:
        adapter.run("owned-channel")
        assert delegated == [(context, manifest, work)] and caught == [original]
        assert caught[0] is original
        assert marks == [("conflict.classify.enter", raw), ("conflict.classify.refused", raw)]
        (entry,) = sent[0][1]["witness"]["classifications"]
        assert entry["backend"]["pid"] == 303
        assert entry["manifest_digest"] == manifest.digest
        assert entry["refusal"] == {"type": "MigrationRefused", "code": "ledger_manifest_conflict"}
    assert finalized == [True]
    assert adapter.worker.observe_owned is observe
    assert adapter.ledger_service._classify_manifest is classify
