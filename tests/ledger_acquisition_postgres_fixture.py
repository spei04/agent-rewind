"""Exact original acquisition contracts and bounded, separately connected observations."""

import hashlib
import inspect
import re
from time import monotonic, sleep

from sqlalchemy import text
from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg

from agent_rewind.migrations import ledger_transaction, service

EXCLUSION_QUERIES = [
    """
        SELECT r.oid, r.rolsuper, d.datdba, n.nspowner
        FROM pg_roles r, pg_database d, pg_namespace n
        WHERE r.rolname=current_user AND d.datname=current_database() AND n.nspname='public'
    """,
    """
        SELECT 1 FROM pg_namespace WHERE nspname NOT IN ('public','information_schema')
        AND nspname NOT LIKE 'pg_%' LIMIT 1
    """,
    """
        SELECT 1 FROM pg_stat_activity a
        WHERE a.datname=current_database() AND a.pid<>pg_backend_pid()
        LIMIT 1
    """,
    """
        SELECT 1 FROM pg_roles actor JOIN pg_roles effective
        ON actor.oid=effective.oid OR pg_has_role(actor.oid,effective.oid,'MEMBER')
        WHERE actor.rolcanlogin AND NOT actor.rolsuper AND actor.rolname<>current_user
        AND (effective.rolname=current_user
          OR has_schema_privilege(effective.oid,'public','CREATE')
          OR EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relkind='r'
            AND has_table_privilege(effective.oid,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE')))
        LIMIT 1
    """,
]
ORIGIN_HASHES = {
    "_postgres_exclusion": "703b86006864491ed1ce29f71a6c1672707c26a1b3b0fe94ab8d2b2b34a2cbcf",
    "_begin": "a75cd93ef4c1d09b8f5bfe50762e70df0dd8613b14059b340d3209e4e1733fcb",
    "_ordinary_error": "a60af50376eaaa24f6dfe36fc94ef3e1a00029649110286b2980c27714cac9ba",
}
BOOTSTRAP = [
    "select pg_catalog.version()",
    "select current_schema()",
    "show transaction isolation level",
    "show standard_conforming_strings",
]
PRE_LOCK = [
    "SET LOCAL search_path TO public,pg_temp",
    "SET TRANSACTION ISOLATION LEVEL READ COMMITTED",
    "SELECT pg_try_advisory_xact_lock(%(key)s)",
    "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename LIMIT 21",
    *[str(text(sql).compile(dialect=PGDialect_psycopg())) for sql in EXCLUSION_QUERIES],
]
MODES = {"lock-expiry": "55P03", "cancel-waiter": "57014"}
# Retain an unresolved blocker until the outer owned-process controller stops this
# process. Never release it just to let an unproved child finish successfully.
UNRESOLVED_BLOCKERS = []


def assert_origins():
    for name, digest in ORIGIN_HASHES.items():
        function = getattr(ledger_transaction, name)
        assert function.__qualname__ == name
        assert function.__module__ == (
            service.__name__ if name == "_postgres_exclusion" else ledger_transaction.__name__
        )
        assert hashlib.sha256(inspect.getsource(function).encode()).hexdigest() == digest


def lock_sql(tables):
    assert len(tables) == 17 and tables == sorted(set(tables)) and "api_keys" in tables
    quote = PGDialect_psycopg().identifier_preparer.quote
    return (
        "LOCK TABLE "
        + ",".join("public." + quote(name) for name in tables)
        + (" IN ACCESS EXCLUSIVE MODE")
    )


def assert_native_contract(observed, parameters, sql, *, final):
    """An exact finite query stream, not a SELECT/WITH prefix allowlist."""
    events = observed["native_trace"]
    raw = observed["work_identity"]["raw_id"]
    calls = [event for event in events if event[1] == "sql-call"]
    receipts = observed["native_parameters"]
    assert len(calls) == len(receipts) == len(parameters)
    assert [event[3] for event in calls if event[0] == "bootstrap"] == BOOTSTRAP
    ordinary = [event for event in calls if event[0] == "ordinary"]
    targets = [*PRE_LOCK, *([sql] if final else [])]
    assert len(ordinary) == 3 * len(targets)
    for index, target in enumerate(targets):
        statement, lock, actual = [event[3] for event in ordinary[index * 3 : index * 3 + 3]]
        statement_match = re.fullmatch(r"SET LOCAL statement_timeout = '([0-9]+)ms'", statement)
        lock_match = re.fullmatch(r"SET LOCAL lock_timeout = '([0-9]+)ms'", lock)
        assert statement_match and 0 < int(statement_match[1]) <= 20000
        assert lock_match and 0 < int(lock_match[1]) <= 5000
        assert actual == target
    assert all(event[0] in {"bootstrap", "ordinary"} and event[2] == raw for event in calls)
    for index, (event, receipt, supplied) in enumerate(
        zip(calls, receipts, parameters, strict=True)
    ):
        phase, _, actual_raw, query = event
        outcome = "raise" if final and index == len(calls) - 1 else "return"
        assert receipt == {
            "phase": phase,
            "raw_id": actual_raw,
            "sql_sha256": hashlib.sha256(query.encode()).hexdigest(),
            "parameter_type": supplied["type"],
            "parameter_count": len(supplied["values"]) if supplied["values"] is not None else 0,
            "outcome": outcome,
        }
        assert supplied["sql"] == query and supplied["raw_id"] == raw
        expected = {"key": service.MIGRATOR_LOCK} if query == PRE_LOCK[2] else {}
        if expected:
            assert supplied["type"] == "dict" and supplied["values"] == expected
            assert type(supplied["values"]["key"]) is int
        else:
            assert supplied["values"] in (None, {}, [])
            assert supplied["type"] in {"NoneType", "dict", "immutabledict", "tuple"}
        position = next(i for i, row in enumerate(events) if row is event)
        tail = events[position + 1 :]
        terminal = next(row for row in tail if row[1] in {"sql-return", "sql-raise", "sql-call"})
        assert terminal == [phase, "sql-" + outcome, raw, query]
    assert observed["work"] == [
        {
            "ordinary": 1 + len(ordinary),
            "timeout_seconds": 5,
            "cleanup": ["detach", "rollback", "close", "raw_close"] if final else [],
        }
    ]
    assert observed["xids"] == observed["observer_units"] == observed["tuple_deltas"] == []
    assert observed["faults"] == []
    assert sorted(event[1] for event in events if event[2] is None) == [
        "connect-call",
        "internal-connect",
    ]
    assert sum(row[1] == "connect-return" for row in events) == 1
    assert all(row[2] in (None, raw) for row in events)
    commands = [(phase, value) for phase, kind, _, value in events if kind == "command"]
    assert commands == [
        ("bootstrap", "BEGIN"),
        ("bootstrap", "ROLLBACK"),
        ("ordinary", "BEGIN"),
        *([("cleanup", "ROLLBACK")] if final else []),
    ]
    assert not any(row[1].startswith("commit-") for row in events)


def assert_held(message, tables):
    witness = message["witness"]
    observed = witness["observation"]
    identity = observed["work_identity"]
    assert identity["raw_id"] == message["raw_id"] and identity["engine_id"] == message["engine_id"]
    assert all(type(identity[key]) is int and identity[key] > 0 for key in identity)
    assert witness["sql"] == lock_sql(tables)
    assert witness["original_site"] == {
        "file": "agent_rewind/migrations/service.py",
        "function": "_postgres_exclusion",
        "line": 107,
    }
    assert witness["transaction_status"] == 2
    assert witness["raw_closed"] is witness["claim_released"] is False
    assert witness["connection_closed"] is witness["work_detached"] is False
    assert observed["command_boundary"] is None
    assert observed["outcomes"] == [
        {
            "begun": True,
            "commit_attempted": False,
            "commit_acknowledged": False,
            "rollback_attempted": False,
            "rollback_acknowledged": False,
            "cleanup_failed": False,
            "begin_attempted": True,
            "_used": True,
        }
    ]
    assert observed["markers"] == [] and observed["physical"] == []
    assert_native_contract(observed, witness["parameters"], witness["sql"], final=False)


def assert_result(message, held, mode):
    witness, raw = message["witness"], message["raw_id"]
    observed = witness["observation"]
    assert observed["work_identity"] == held["witness"]["observation"]["work_identity"]
    prefix = held["witness"]["observation"]["native_trace"]
    assert observed["native_trace"][: len(prefix)] == prefix
    prior_parameters = held["witness"]["parameters"]
    assert witness["parameters"][: len(prior_parameters)] == prior_parameters
    assert_native_contract(observed, witness["parameters"], held["witness"]["sql"], final=True)
    assert witness["receipt"] is None and witness["refusal"]["code"] == "migration_busy"
    native, mapped = witness["native_error"], witness["mapped_error"]
    assert native["sqlstate"] == MODES[mode] and native["status"] == 3
    assert native["raw_id"] == raw and native["sql"] == held["witness"]["sql"]
    assert type(native["error_id"]) is int and native["error_id"] > 0
    assert mapped["native_id"] == native["error_id"]
    assert observed["native_trace"][native["trace_end"] - 1] == [
        "ordinary",
        "sql-raise",
        raw,
        held["witness"]["sql"],
    ]
    assert len({native["error_id"], mapped["wrapper_id"], mapped["mapped_id"]}) == 3
    assert mapped["caught_id"] == mapped["mapped_id"] == witness["refusal"]["error_id"]
    assert mapped["original_mapping"] and mapped["original_mapping_line"] == 280
    assert mapped["mapped_type"] == "MigrationRefused" and mapped["mapped_code"] == "migration_busy"
    assert mapped["wrapper_type"] == "OperationalError" and mapped["wrapper_id"] > 0
    assert observed["outcomes"] == [
        {
            "begun": True,
            "commit_attempted": False,
            "commit_acknowledged": False,
            "rollback_attempted": True,
            "rollback_acknowledged": True,
            "cleanup_failed": False,
            "begin_attempted": True,
            "_used": True,
        }
    ]
    boundary = observed["command_boundary"]
    assert boundary["raw_id"] == raw and not boundary["engine_poisoned"]
    assert all(
        boundary[key]
        for key in ("raw_closed", "connection_closed", "claim_released", "claim_absent")
    )
    assert not any(
        row[0] == "harness-dispose" for row in (observed["native_trace"][: boundary["trace_end"]])
    )
    physical = observed["physical"]
    rollbacks = [row for row in physical if row["action"] == "rollback"]
    assert len(rollbacks) == 1
    assert (rollbacks[0]["status_before"], rollbacks[0]["status_after"]) == (3, 0)
    assert not rollbacks[0]["closed_before"] and not rollbacks[0]["closed_after"]
    closes = [row for row in physical if row["action"] == "close" and not row["closed_before"]]
    assert len(closes) == 1 and closes[0]["closed_after"]
    assert rollbacks[0]["trace_end"] < closes[0]["trace_end"] <= boundary["trace_end"]
    assert all(row["raw_id"] == raw for row in physical)
    assert all(row["action"] in {"rollback", "close"} for row in physical)
    assert witness["body_entries"] == 0 and witness["lock_delegations"] == 1


# One autocommit statement observes PID identity and all its locks together.
# A different live identity at a reused PID is deliberately not filtered away.
OBSERVE_SQL = """
SELECT json_build_object(
 'activity', (SELECT coalesce(json_agg(a), '[]'::json) FROM (
   SELECT pid, backend_start::text, datid, datname, usename, state, wait_event_type,
          query, query_start::text,
          extract(epoch FROM clock_timestamp()-query_start)::float8 AS age,
          pg_blocking_pids(pid) AS blockers
   FROM pg_stat_activity WHERE pid=:pid LIMIT 2) a),
 'locks', (SELECT coalesce(json_agg(l), '[]'::json) FROM (
   SELECT pid, locktype, database, relation, mode, granted
   FROM pg_locks WHERE pid=:pid ORDER BY locktype, relation, mode LIMIT 129) l),
 'blocker_activity', (SELECT coalesce(json_agg(a), '[]'::json) FROM (
   SELECT pid, backend_start::text, datid, datname, usename
   FROM pg_stat_activity WHERE pid=:blocker LIMIT 2) a),
 'blocker_locks', (SELECT coalesce(json_agg(l), '[]'::json) FROM (
   SELECT pid, locktype, database, relation, mode, granted
   FROM pg_locks WHERE pid=:blocker ORDER BY locktype, relation, mode LIMIT 129) l),
 'target_pids', (SELECT coalesce(json_agg(pid ORDER BY pid), '[]'::json) FROM (
   SELECT pid FROM pg_stat_activity WHERE datname=:database LIMIT 4) a))
"""
CANCEL_SQL = """
WITH eligible AS MATERIALIZED (
 SELECT a.pid FROM pg_stat_activity a
 WHERE a.pid=:pid AND a.backend_start=CAST(:backend_start AS timestamptz)
 AND a.datid=:datid AND a.datname=:database AND a.usename=:role
 AND a.query_start=CAST(:query_start AS timestamptz) AND a.query=:query
 AND a.state='active' AND a.wait_event_type='Lock'
 AND clock_timestamp()-a.query_start < interval '2 seconds'
 AND clock_timestamp()>=a.query_start
 AND pg_blocking_pids(a.pid)=ARRAY[CAST(:blocker AS integer)]
 AND EXISTS (SELECT 1 FROM pg_locks l WHERE l.pid=a.pid AND l.locktype='relation'
   AND l.database=:datid AND l.relation=:relation
   AND l.mode='AccessExclusiveLock' AND NOT l.granted)
 AND EXISTS (SELECT 1 FROM pg_stat_activity b
   WHERE b.pid=:blocker AND b.backend_start=CAST(:blocker_start AS timestamptz)
   AND b.datid=:datid AND b.datname=:database AND b.usename=:blocker_role)
 AND EXISTS (SELECT 1 FROM pg_locks l WHERE l.pid=:blocker
   AND l.locktype='relation' AND l.database=:datid AND l.relation=:relation
   AND l.mode='AccessShareLock' AND l.granted)
 AND (SELECT array_agg(pid ORDER BY pid) FROM pg_stat_activity WHERE datname=:database)
     = ARRAY[LEAST(CAST(:pid AS integer),CAST(:blocker AS integer)),
             GREATEST(CAST(:pid AS integer),CAST(:blocker AS integer))]
 LIMIT 2
), tally AS (SELECT count(*) AS n, min(pid) AS pid FROM eligible)
SELECT n, CASE WHEN n=1 THEN pg_cancel_backend(pid) ELSE NULL END AS acknowledged FROM tally
"""


def assert_identity(row, expected):
    for key in ("pid", "backend_start", "datid", "datname", "usename"):
        assert type(row[key]) is type(expected[key]) and row[key] == expected[key], key


def assert_waiting(observation, operator, blocker, relation, query):
    assert len(observation["activity"]) == len(observation["blocker_activity"]) == 1
    row = observation["activity"][0]
    assert_identity(row, operator)
    assert_identity(observation["blocker_activity"][0], blocker)
    assert observation["target_pids"] == sorted([operator["pid"], blocker["pid"]])
    assert (row["state"], row["wait_event_type"], row["query"]) == ("active", "Lock", query)
    assert row["blockers"] == [blocker["pid"]]
    assert type(row["query_start"]) is str and row["query_start"]
    assert row["age"] >= 0
    for key, pid, mode, granted in (
        ("locks", operator["pid"], "AccessExclusiveLock", False),
        ("blocker_locks", blocker["pid"], "AccessShareLock", True),
    ):
        assert len(observation[key]) < 129
        matches = [
            lock
            for lock in observation[key]
            if (
                lock["pid"] == pid
                and lock["locktype"] == "relation"
                and lock["database"] == operator["datid"]
                and lock["relation"] == relation
                and lock["mode"] == mode
                and lock["granted"] is granted
            )
        ]
        assert len(matches) == 1
    return row


def assert_absent(observation, operator, blocker, *, released=False):
    assert observation["activity"] == [] and observation["locks"] == []
    if released:
        assert observation["blocker_activity"] == observation["blocker_locks"] == []
        assert observation["target_pids"] == []
    else:
        assert len(observation["blocker_activity"]) == 1
        assert_identity(observation["blocker_activity"][0], blocker)
        assert observation["target_pids"] == [blocker["pid"]]
    assert operator["pid"] != blocker["pid"]


def assert_cancel_receipt(row, *, started, finished, continued, deadline):
    assert 0 <= started - continued < 3
    assert started <= finished <= min(continued + 3, deadline)
    assert finished - started <= 1
    assert tuple(row) == (1, True) and type(row[0]) is int and type(row[1]) is bool


class AcquisitionObserver:
    """Fixed query/poll bounds; clocks are observations, never renewed budgets."""

    def __init__(self, control, database, deadline, journal):
        self.control, self.database = control, database
        self.deadline, self.journal = deadline, journal
        self.calls, self.last_completion = 0, None

    def execute(self, statement, parameters):
        started = monotonic()
        assert started < self.deadline and self.calls < 256
        if self.last_completion is not None:
            assert 0 <= started - self.last_completion <= 0.1, "observation idle gap"
        self.calls += 1
        receipt = {"started": started, "sql": statement, "parameters": parameters}
        self.journal.append(receipt)
        try:
            result = self.control.execute(text(statement), parameters)
            with result:
                row = result.one()
            receipt["row"] = list(row)
            return row
        except BaseException as error:
            receipt["error"] = {"type": type(error).__name__, "message": str(error)}
            raise
        finally:
            finished = monotonic()
            receipt["finished"] = finished
            assert finished - started <= 1 and finished <= self.deadline
            self.last_completion = finished

    def observe(self, pid, blocker):
        row = self.execute(
            OBSERVE_SQL,
            {
                "pid": pid,
                "blocker": blocker,
                "database": self.database,
            },
        )[0]
        assert type(row) is dict
        assert set(row) == {"activity", "locks", "blocker_activity", "blocker_locks", "target_pids"}
        assert len(row["activity"]) < 2 and len(row["blocker_activity"]) < 2
        assert len(row["locks"]) < 129 and len(row["blocker_locks"]) < 129
        assert len(row["target_pids"]) < 4
        return row

    def account_release(self, absent_at, closed_at):
        # Only the separately bounded native blocker rollback/close may span
        # more than the polling idle allowance. It cannot renew either cap.
        assert self.last_completion == absent_at
        assert absent_at <= closed_at <= min(absent_at + 2, self.deadline)
        assert 0 <= monotonic() - closed_at <= 0.1
        self.last_completion = closed_at

    def poll(self, predicate, pid, blocker, deadline):
        assert deadline <= self.deadline
        for _ in range(256):
            assert monotonic() < deadline
            observation = self.observe(pid, blocker)
            assert self.last_completion <= deadline, "complete observation missed poll deadline"
            if predicate(observation):
                return observation
            sleep(min(0.05, max(0, deadline - monotonic())))
        raise AssertionError("acquisition observation budget exhausted")
