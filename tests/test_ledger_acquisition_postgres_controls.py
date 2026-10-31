"""Pure adversarial controls for C2; synthetic records are not native outcomes."""

import ast
import hashlib
import inspect
import re
from copy import deepcopy

import pytest
from ledger_acquisition_postgres_fixture import (
    BOOTSTRAP,
    EXCLUSION_QUERIES,
    MODES,
    OBSERVE_SQL,
    PRE_LOCK,
    AcquisitionObserver,
    assert_absent,
    assert_cancel_receipt,
    assert_held,
    assert_native_contract,
    assert_origins,
    assert_result,
    assert_waiting,
    lock_sql,
)
from sqlalchemy import text
from sqlalchemy.dialects.postgresql.base import PGDialect
from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg

from agent_rewind.migrations import ledger_transaction, service

TABLES = sorted(["api_keys", *[f"table_{index:02}" for index in range(16)]])


def source_text_calls(function):
    tree = ast.parse(inspect.getsource(function))
    nodes = sorted(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "text"
        ),
        key=lambda node: node.lineno,
    )
    return [ast.literal_eval(node.args[0]) for node in nodes]


def test_contracts_are_bound_to_original_queries_and_pinned_bootstrap_sources():
    assert_origins()
    assert source_text_calls(service._postgres_exclusion) == EXCLUSION_QUERIES
    beginning = [
        *source_text_calls(ledger_transaction._begin_native),
        *source_text_calls(ledger_transaction._begin),
    ]
    assert beginning == [
        "SELECT pg_try_advisory_xact_lock(:key)",
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename LIMIT 21",
    ]
    assert PRE_LOCK[2:4] == [
        str(text(sql).compile(dialect=PGDialect_psycopg())) for sql in beginning
    ]
    dialect = PGDialect_psycopg
    functions = [
        dialect._get_server_version_info,
        dialect._get_default_schema_name,
        PGDialect.get_isolation_level,
        dialect._set_backslash_escapes,
    ]
    for query, function in zip(BOOTSTRAP, functions, strict=True):
        constants = [
            node.value
            for node in ast.walk(ast.parse(inspect.getsource(function).lstrip()))
            if isinstance(node, ast.Constant) and type(node.value) is str
        ]
        assert query in constants


def synthetic_message(*, final=False, mode="lock-expiry"):
    raw = 11
    events, receipts, supplied = [], [], []

    def execute(phase, query, values=None, *, raises=False, begin=False, kind=None):
        kind = kind or ("NoneType" if values is None else "dict")
        events.append([phase, "sql-call", raw, query])
        if begin:
            events.append([phase, "command", raw, "BEGIN"])
        events.append([phase, "sql-raise" if raises else "sql-return", raw, query])
        receipts.append(
            {
                "phase": phase,
                "raw_id": raw,
                "sql_sha256": hashlib.sha256(query.encode()).hexdigest(),
                "parameter_type": kind,
                "parameter_count": len(values) if values is not None else 0,
                "outcome": "raise" if raises else "return",
            }
        )
        supplied.append({"sql": query, "raw_id": raw, "type": kind, "values": values})

    events.extend(
        [
            ["bootstrap", "connect-call", None, None],
            ["bootstrap", "internal-connect", None, None],
            ["bootstrap", "connect-return", raw, None],
        ]
    )
    for index, query in enumerate(BOOTSTRAP):
        execute("bootstrap", query, begin=index == 0)
    events.extend(
        [
            ["bootstrap", "rollback-call", raw, None],
            ["bootstrap", "command", raw, "ROLLBACK"],
            ["bootstrap", "rollback-return", raw, None],
        ]
    )
    targets = [*PRE_LOCK, *([lock_sql(TABLES)] if final else [])]
    for index, query in enumerate(targets):
        execute("ordinary", "SET LOCAL statement_timeout = '20000ms'", begin=index == 0)
        execute("ordinary", "SET LOCAL lock_timeout = '5000ms'")
        execute(
            "ordinary",
            query,
            {"key": service.MIGRATOR_LOCK} if query == PRE_LOCK[2] else None,
            raises=final and index == len(targets) - 1,
        )
    physical = []
    if final:
        events.extend(
            [
                ["cleanup", "rollback-call", raw, None],
                ["cleanup", "command", raw, "ROLLBACK"],
                ["cleanup", "rollback-return", raw, None],
            ]
        )
        physical.append(
            {
                "action": "rollback",
                "raw_id": raw,
                "closed_before": False,
                "closed_after": False,
                "status_before": 3,
                "status_after": 0,
                "trace_end": len(events),
            }
        )
        events.extend(
            [
                ["cleanup", "close-call", raw, None],
                ["cleanup", "close-return", raw, None],
            ]
        )
        physical.append(
            {
                "action": "close",
                "raw_id": raw,
                "closed_before": False,
                "closed_after": True,
                "status_before": 0,
                "status_after": None,
                "trace_end": len(events),
            }
        )
    observation = {
        "work_identity": {
            "raw_id": raw,
            "engine_id": 12,
            "connection_id": 13,
            "work_id": 14,
            "claim_id": 15,
        },
        "native_trace": events,
        "native_parameters": receipts,
        "work": [
            {
                "ordinary": 1 + 3 * len(targets),
                "timeout_seconds": 5,
                "cleanup": ["detach", "rollback", "close", "raw_close"] if final else [],
            }
        ],
        "xids": [],
        "observer_units": [],
        "tuple_deltas": [],
        "faults": [],
        "outcomes": [
            {
                "begun": True,
                "commit_attempted": False,
                "commit_acknowledged": False,
                "rollback_attempted": final,
                "rollback_acknowledged": final,
                "cleanup_failed": False,
                "begin_attempted": True,
                "_used": True,
            }
        ],
        "markers": [],
        "physical": physical,
        "command_boundary": {
            "raw_id": raw,
            "trace_end": len(events),
            "raw_closed": True,
            "connection_closed": True,
            "claim_released": True,
            "claim_absent": True,
            "engine_poisoned": False,
        }
        if final
        else None,
    }
    witness = {
        "sql": lock_sql(TABLES),
        "observation": observation,
        "parameters": supplied,
        "original_site": {
            "file": "agent_rewind/migrations/service.py",
            "function": "_postgres_exclusion",
            "line": 107,
        },
        "transaction_status": 2,
        "raw_closed": False,
        "claim_released": False,
        "connection_closed": False,
        "work_detached": False,
    }
    if final:
        witness.update(
            receipt=None,
            refusal={"code": "migration_busy", "error_id": 23},
            native_error={
                "error_id": 21,
                "sqlstate": MODES[mode],
                "status": 3,
                "raw_id": raw,
                "sql": lock_sql(TABLES),
                "trace_end": len(events) - 5,
            },
            mapped_error={
                "native_id": 21,
                "mapped_id": 23,
                "caught_id": 23,
                "original_mapping": True,
                "original_mapping_line": 286,
                "mapped_type": "MigrationRefused",
                "mapped_code": "migration_busy",
                "wrapper_type": "OperationalError",
                "wrapper_id": 22,
            },
            body_entries=0,
            lock_delegations=1,
        )
    return {"raw_id": raw, "engine_id": 12, "witness": witness}


@pytest.mark.parametrize("mode", list(MODES))
def test_synthetic_complete_profiles_accept(mode):
    held, final = synthetic_message(), synthetic_message(final=True, mode=mode)
    assert_held(held, TABLES)
    assert_result(final, held, mode)


@pytest.mark.parametrize(
    "mutation",
    [
        "write-cte",
        "side-effect-select",
        "changed-privilege-query",
        "wrong-key",
        "extra-parameter",
        "missed-prior-return",
        "raising-setter",
        "wrong-raw",
        "larger-timeout",
        "body-xid",
        "ordinary-undercount",
        "retry-begin",
        "commit",
        "extra-checkout",
    ],
)
def test_native_contract_rejects_unproved_or_write_capable_stream(mutation):
    message = synthetic_message(final=True)
    witness = message["witness"]
    observed, parameters = witness["observation"], witness["parameters"]
    ordinary = [
        row for row in observed["native_trace"] if row[0] == "ordinary" and row[1] == "sql-call"
    ]
    replacements = {
        "write-cte": "WITH changed AS (DELETE FROM jobs RETURNING *) SELECT * FROM changed",
        "side-effect-select": "SELECT pg_advisory_unlock_all()",
        "changed-privilege-query": PRE_LOCK[-1] + " /* changed */",
    }
    if mutation in replacements:
        ordinary[-4][3] = replacements[mutation]
    elif mutation == "wrong-key":
        next(row for row in parameters if row["sql"] == PRE_LOCK[2])["values"]["key"] += 1
    elif mutation == "extra-parameter":
        parameters[0]["values"] = {"unused": 1}
    elif mutation == "missed-prior-return":
        row = next(
            row
            for row in observed["native_trace"]
            if row[3] == PRE_LOCK[-1] and row[1] == "sql-return"
        )
        row[1] = "sql-raise"
    elif mutation == "raising-setter":
        observed["native_parameters"][-2]["outcome"] = "raise"
    elif mutation == "wrong-raw":
        ordinary[-1][2] += 1
    elif mutation == "larger-timeout":
        ordinary[-3][3] = "SET LOCAL statement_timeout = '20001ms'"
    elif mutation == "body-xid":
        observed["xids"].append([11, "123", 30])
    elif mutation == "ordinary-undercount":
        observed["work"][0]["ordinary"] -= 1
    elif mutation == "retry-begin":
        observed["native_trace"].append(["ordinary", "command", 11, "BEGIN"])
    elif mutation == "commit":
        observed["native_trace"].append(["cleanup", "commit-call", 11, None])
    else:
        observed["native_trace"].append(["ordinary", "connect-return", 11, None])
    with pytest.raises(AssertionError):
        assert_native_contract(observed, parameters, lock_sql(TABLES), final=True)


@pytest.mark.parametrize(
    "field,value",
    [
        ("original_mapping", False),
        ("original_mapping_line", 279),
        ("native_id", 999),
        ("caught_id", 999),
        ("mapped_code", "migration_database_failure"),
    ],
)
def test_original_exception_chain_required(field, value):
    held, final = synthetic_message(), synthetic_message(final=True)
    final["witness"]["mapped_error"][field] = value
    with pytest.raises(AssertionError):
        assert_result(final, held, "lock-expiry")


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong-sqlstate",
        "cleanup-only-error",
        "body-entered",
        "second-lock",
        "rollback-not-acknowledged",
        "intrans-rollback",
        "late-close",
        "missing-close",
        "poisoned",
    ],
)
def test_original_refusal_and_physical_cleanup_required(mutation):
    held, final = synthetic_message(), synthetic_message(final=True, mode="cancel-waiter")
    witness = final["witness"]
    observed = witness["observation"]
    if mutation == "wrong-sqlstate":
        witness["native_error"]["sqlstate"] = "55P03"
    elif mutation == "cleanup-only-error":
        witness["native_error"]["sql"] = "ROLLBACK"
    elif mutation == "body-entered":
        witness["body_entries"] = 1
    elif mutation == "second-lock":
        witness["lock_delegations"] = 2
    elif mutation == "rollback-not-acknowledged":
        observed["outcomes"][0]["rollback_acknowledged"] = False
    elif mutation == "intrans-rollback":
        observed["physical"][0]["status_before"] = 2
    elif mutation == "late-close":
        observed["physical"][-1]["trace_end"] += 1
    elif mutation == "missing-close":
        observed["physical"].pop()
    else:
        observed["command_boundary"]["engine_poisoned"] = True
    with pytest.raises(AssertionError):
        assert_result(final, held, "cancel-waiter")


def waiting_fixture():
    operator = {
        "pid": 31,
        "backend_start": "start-a",
        "datid": 41,
        "datname": "owned",
        "usename": "o",
    }
    blocker = {**operator, "pid": 32, "backend_start": "start-b", "usename": "admin"}
    row = {
        **operator,
        "state": "active",
        "wait_event_type": "Lock",
        "query": lock_sql(TABLES),
        "query_start": "query-start",
        "age": 0.2,
        "blockers": [32],
    }
    observation = {
        "activity": [row],
        "blocker_activity": [blocker.copy()],
        "target_pids": [31, 32],
        "locks": [
            {
                "pid": 31,
                "locktype": "relation",
                "database": 41,
                "relation": 51,
                "mode": "AccessExclusiveLock",
                "granted": False,
            }
        ],
        "blocker_locks": [
            {
                "pid": 32,
                "locktype": "relation",
                "database": 41,
                "relation": 51,
                "mode": "AccessShareLock",
                "granted": True,
            }
        ],
    }
    return observation, operator, blocker


def test_exact_owned_wait_and_both_disappearance_states():
    observation, operator, blocker = waiting_fixture()
    assert_waiting(observation, operator, blocker, 51, lock_sql(TABLES))
    observation.update(activity=[], locks=[], target_pids=[32])
    assert_absent(observation, operator, blocker)
    observation.update(blocker_activity=[], blocker_locks=[], target_pids=[])
    assert_absent(observation, operator, blocker, released=True)


@pytest.mark.parametrize(
    "mutation",
    [
        "pid",
        "backend_start",
        "datid",
        "datname",
        "usename",
        "query",
        "wait_event_type",
        "state",
        "blockers",
        "relation",
        "granted",
        "blocker-granted",
        "blocker-start",
        "extra-client",
    ],
)
def test_owned_wait_rejects_wrong_identity_or_unproved_blocking(mutation):
    observation, operator, blocker = waiting_fixture()
    if mutation in {"pid", "datid"}:
        observation["activity"][0][mutation] += 1
    elif mutation in {"backend_start", "datname", "usename", "query", "wait_event_type", "state"}:
        observation["activity"][0][mutation] = "wrong"
    elif mutation == "blockers":
        observation["activity"][0]["blockers"] = [99]
    elif mutation == "relation":
        observation["locks"][0]["relation"] = 99
    elif mutation == "granted":
        observation["locks"][0]["granted"] = True
    elif mutation == "blocker-granted":
        observation["blocker_locks"][0]["granted"] = False
    elif mutation == "blocker-start":
        observation["blocker_activity"][0]["backend_start"] = "reused"
    else:
        observation["target_pids"].append(99)
    with pytest.raises(AssertionError):
        assert_waiting(observation, operator, blocker, 51, lock_sql(TABLES))


@pytest.mark.parametrize(
    "mutation", ["live", "reused", "residual-lock", "blocker-gone", "extra-client"]
)
def test_absence_needs_exact_session_and_all_locks_gone(mutation):
    observation, operator, blocker = waiting_fixture()
    observation.update(activity=[], locks=[], target_pids=[32])
    if mutation in {"live", "reused"}:
        observation["activity"] = [{**operator, "backend_start": mutation}]
    elif mutation == "residual-lock":
        observation["locks"] = [{"pid": 31}]
    elif mutation == "blocker-gone":
        observation["blocker_activity"] = []
    else:
        observation["target_pids"].append(99)
    with pytest.raises(AssertionError):
        assert_absent(observation, operator, blocker)


@pytest.mark.parametrize(
    "row,started,finished,deadline",
    [
        ((0, None), 10.1, 10.2, 19),
        ((1, False), 10.1, 10.2, 19),
        ((2, True), 10.1, 10.2, 19),
        ((True, True), 10.1, 10.2, 19),
        ((1, True), 13, 13.1, 19),
        ((1, True), 12.8, 13.01, 19),
        ((1, True), 10.1, 11.2, 19),
        ((1, True), 10.1, 10.3, 10.2),
    ],
)
def test_cancel_requires_one_true_ack_inside_both_original_bounds(row, started, finished, deadline):
    with pytest.raises(AssertionError):
        assert_cancel_receipt(
            row, started=started, finished=finished, continued=10, deadline=deadline
        )


def test_one_bounded_cancel_ack_is_accepted():
    assert_cancel_receipt((1, True), started=10.2, finished=10.4, continued=10, deadline=19)


def test_same_held_boundary_requires_original_site_and_no_new_native_work():
    held = synthetic_message()
    held["witness"]["original_site"]["line"] = 108
    with pytest.raises(AssertionError):
        assert_held(held, TABLES)


class FakeResult:
    def __init__(self, row):
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def one(self):
        return (deepcopy(self.row),)


class FakeControl:
    def __init__(self, clock, durations, row):
        self.clock, self.durations, self.row = clock, iter(durations), row

    def execute(self, statement, parameters):
        self.clock[0] += next(self.durations)
        return FakeResult(self.row)


@pytest.mark.parametrize("duration", [0.101, 0.9])
def test_observation_may_take_over_100ms_without_reclassifying_latency(monkeypatch, duration):
    import ledger_acquisition_postgres_fixture as module

    clock = [10.0]
    monkeypatch.setattr(module, "monotonic", lambda: clock[0])
    row, _, _ = waiting_fixture()
    observer = AcquisitionObserver(FakeControl(clock, [duration], row), "owned", 19, [])
    assert observer.observe(31, 32) == row


@pytest.mark.parametrize("case", ["query-over-one-second", "fixed-deadline", "poll-idle-gap"])
def test_observer_preserves_failed_bounds_and_never_renews_deadline(monkeypatch, case):
    import ledger_acquisition_postgres_fixture as module

    clock, journal = [10.0], []
    monkeypatch.setattr(module, "monotonic", lambda: clock[0])
    row, _, _ = waiting_fixture()
    durations = [1.01] if case == "query-over-one-second" else [0.2]
    deadline = 10.1 if case == "fixed-deadline" else 19
    observer = AcquisitionObserver(FakeControl(clock, durations, row), "owned", deadline, journal)
    if case == "poll-idle-gap":

        def overslept(_seconds):
            clock[0] += 0.101

        monkeypatch.setattr(module, "sleep", overslept)
    with pytest.raises(AssertionError):
        if case == "poll-idle-gap":
            observer.poll(lambda _: False, 31, 32, deadline)
        else:
            observer.observe(31, 32)
    assert journal and "finished" in journal[0]
    assert observer.deadline == deadline and observer.calls == 1


def test_positive_observation_cannot_cross_narrower_poll_deadline(monkeypatch):
    import ledger_acquisition_postgres_fixture as module

    clock, journal = [10.0], []
    monkeypatch.setattr(module, "monotonic", lambda: clock[0])
    row, _, _ = waiting_fixture()
    observer = AcquisitionObserver(FakeControl(clock, [0.2], row), "owned", 19, journal)
    with pytest.raises(AssertionError, match="poll deadline"):
        observer.poll(lambda _: True, 31, 32, 10.1)
    assert journal[0]["finished"] == 10.2 and observer.deadline == 19


def test_phase_transition_cannot_reset_observation_idle_clock(monkeypatch):
    import ledger_acquisition_postgres_fixture as module

    clock = [10.0]
    monkeypatch.setattr(module, "monotonic", lambda: clock[0])
    row, _, _ = waiting_fixture()
    observer = AcquisitionObserver(FakeControl(clock, [0.2], row), "owned", 19, [])
    observer.poll(lambda _: True, 31, 32, 12)
    clock[0] += 0.101
    with pytest.raises(AssertionError, match="idle gap"):
        observer.poll(lambda _: True, 31, 32, 19)
    assert observer.calls == 1 and observer.last_completion == 10.2


@pytest.mark.parametrize(
    "absent,closed,now,deadline",
    [
        (10.3, 12.1, 12.1, 19),
        (10.2, 12.21, 12.21, 19),
        (10.2, 11.1, 11.21, 19),
        (10.2, 11.1, 11.1, 11),
    ],
)
def test_release_accounting_rejects_new_anchor_or_late_action(
    monkeypatch, absent, closed, now, deadline
):
    import ledger_acquisition_postgres_fixture as module

    monkeypatch.setattr(module, "monotonic", lambda: now)
    observer = AcquisitionObserver(None, "owned", deadline, [])
    observer.last_completion = 10.2
    with pytest.raises(AssertionError):
        observer.account_release(absent, closed)
    assert observer.last_completion == 10.2 and observer.deadline == deadline


def test_bounded_release_allows_only_its_explicit_interval(monkeypatch):
    import ledger_acquisition_postgres_fixture as module

    clock = [12.1]
    monkeypatch.setattr(module, "monotonic", lambda: clock[0])
    row, _, _ = waiting_fixture()
    observer = AcquisitionObserver(FakeControl(clock, [0.05], row), "owned", 19, [])
    observer.last_completion = 10.2
    observer.account_release(10.2, 12.1)
    assert observer.poll(lambda _: True, 31, 32, 12.2) == row
    assert observer.deadline == 19


def test_parent_fixture_wrapper_does_not_replace_operator_source_binding(monkeypatch):
    def fixture_wrapper(*args, **kwargs):
        raise AssertionError("fixture delegate must not be invoked")

    monkeypatch.setattr(service, "_postgres_exclusion", fixture_wrapper)
    assert_origins()


def test_changed_original_operator_alias_fails_source_binding(monkeypatch):
    for name in ("_postgres_exclusion", "_begin", "_begin_native", "_ordinary_error"):
        with monkeypatch.context() as patch:

            def replacement(*args, **kwargs):
                raise AssertionError("replacement must not be invoked")

            # Preserve identity metadata so rejection proves the source hash guard.
            replacement.__name__ = replacement.__qualname__ = name
            replacement.__module__ = (
                service.__name__ if name == "_postgres_exclusion" else ledger_transaction.__name__
            )
            patch.setattr(ledger_transaction, name, replacement)
            with pytest.raises(AssertionError):
                assert_origins()


def test_final_native_prefix_must_be_the_exact_held_observation():
    held, final = synthetic_message(), synthetic_message(final=True)
    # A valid shorter timeout in both call/return and receipts could satisfy an
    # independent final shape, but cannot change an already observed held prefix.
    original = "SET LOCAL lock_timeout = '5000ms'"
    replacement = "SET LOCAL lock_timeout = '4000ms'"
    observed = final["witness"]["observation"]
    for row in observed["native_trace"]:
        if row[3] == original:
            row[3] = replacement
    for receipt, supplied in zip(
        observed["native_parameters"], final["witness"]["parameters"], strict=True
    ):
        if supplied["sql"] == original:
            supplied["sql"] = replacement
            receipt["sql_sha256"] = hashlib.sha256(replacement.encode()).hexdigest()
    assert_native_contract(observed, final["witness"]["parameters"], lock_sql(TABLES), final=True)
    with pytest.raises(AssertionError):
        assert_result(final, held, "lock-expiry")


def test_observer_projects_all_oid_fields_as_numbers_without_changing_query_scope():
    # The original query produced JSON strings for oid fields. Pin every
    # projection and alias without changing predicates, limits or selected rows.
    projected = re.findall(r"\b(datid|database|relation)::bigint AS (\w+)", OBSERVE_SQL)
    assert projected == [
        ("datid", "datid"),
        ("database", "database"),
        ("relation", "relation"),
        ("datid", "datid"),
        ("database", "database"),
        ("relation", "relation"),
    ]
    original = re.sub(r"\b(datid|database|relation)::bigint AS \1\b", r"\1", OBSERVE_SQL)
    assert hashlib.sha256(" ".join(original.split()).encode()).hexdigest() == (
        "032bf808628950705b4062ccd181a543b22e1acdccf8b1242bb30d8318a4016c"
    )
    compiled = text(OBSERVE_SQL).compile(dialect=PGDialect_psycopg())
    assert set(compiled.params) == {"pid", "blocker", "database"}


@pytest.mark.parametrize(
    "collection,field",
    [
        ("activity", "datid"),
        ("blocker_activity", "datid"),
        ("locks", "database"),
        ("locks", "relation"),
        ("blocker_locks", "database"),
        ("blocker_locks", "relation"),
    ],
)
def test_observer_does_not_normalize_string_oids_or_credit_them_as_owned_waits(
    monkeypatch, collection, field
):
    import ledger_acquisition_postgres_fixture as module

    clock, journal = [10.0], []
    monkeypatch.setattr(module, "monotonic", lambda: clock[0])
    row, operator, blocker = waiting_fixture()
    row[collection][0][field] = str(row[collection][0][field])
    observer = AcquisitionObserver(FakeControl(clock, [0.05], row), "owned", 19, journal)
    captured = observer.observe(31, 32)
    assert type(captured[collection][0][field]) is str
    assert journal[0]["row"] == [captured]
    with pytest.raises(AssertionError):
        assert_waiting(captured, operator, blocker, 51, lock_sql(TABLES))
