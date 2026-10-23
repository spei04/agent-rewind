"""Bounded, separate-database identity observations while another writer is held."""

from time import monotonic

from ledger_process_fixture import remaining
from ledger_process_postgres_observer import ACTIVITY, LOCKS
from sqlalchemy import event, text

IDENTITY_FIELDS = ("pid", "datid", "datname", "usename", "backend_start")
CLEAR = "SELECT pg_stat_clear_snapshot()"
TIMEOUT = "SET statement_timeout='1s'"


def install_cleanup_guard(engine, group, record):
    allowed = {
        CLEAR,
        TIMEOUT,
        str(text(ACTIVITY).compile(dialect=engine.dialect)),
        str(text(LOCKS).compile(dialect=engine.dialect)),
    }

    def guard(connection, cursor, statement, parameters, context, executemany):
        active = [
            child.process.pid
            for child in group.children
            if child.process is not None and child.process.returncode is None
        ]
        if active and statement not in allowed:
            record("blocked_finalizer", {"owned_pids": active, "statement": statement})
            raise AssertionError("target cleanup forbidden before owned children are reaped")

    event.listen(engine, "before_cursor_execute", guard)
    # Deliberately retain this guard on a failed cleanup. The fixture's driver
    # SQL finalizer must not race the outer controller's exact-subtree reaper.
    return guard


def observe(connection, pid, deadline):
    # The connection was opened, and its one-second server timeout installed,
    # before the shared work clock starts. Each query reserves that full bound.
    assert remaining(deadline) > 1
    connection.exec_driver_sql(CLEAR).close()
    assert remaining(deadline) > 1
    activity = [dict(row) for row in connection.execute(text(ACTIVITY), {"pid": pid}).mappings()]
    assert remaining(deadline) > 1
    locks = [dict(row) for row in connection.execute(text(LOCKS), {"pid": pid}).mappings()]
    remaining(deadline)
    assert len(activity) <= 1 and len(locks) <= 1024
    return {"activity": activity, "locks": locks}


def attest_backend(connection, marker, pg, deadline, *, winner, table_ids=()):
    witness = marker["witness"]
    pid = witness["backend_pid"]
    assert type(pid) is int and pid > 0
    assert witness["database"] == pg["owner"].url.database
    assert witness["role"] == pg["owner_role"]
    assert connection.engine.url.database != witness["database"]
    result = observe(connection, pid, deadline)
    assert len(result["activity"]) == 1
    backend = result["activity"][0]
    assert backend["datname"] == witness["database"] and backend["usename"] == witness["role"]
    assert backend["backend_type"] == "client backend"
    assert backend["backend_start"].utcoffset() is not None
    assert backend["state"] == "idle in transaction" and backend["xact_start"] is not None
    assert all(row["pid"] == pid and row["granted"] for row in result["locks"])
    advisory = [row for row in result["locks"] if row["locktype"] == "advisory"]
    if winner:
        assert len(advisory) == 1 and advisory[0]["mode"] == "ExclusiveLock"
        xids = witness["observation"]["xids"]
        assert xids and len({row[1] for row in xids}) == 1
        assert backend["backend_xid"] == str(int(xids[0][1]) % 2**32)
        held = {
            row["relation"]
            for row in result["locks"]
            if row["locktype"] == "relation"
            and row["database"] == backend["datid"]
            and row["mode"] == "AccessExclusiveLock"
        }
        assert set(table_ids.values()) <= held
    else:
        assert advisory == [] and backend["backend_xid"] is None
        assert not any(row["locktype"] == "relation" for row in result["locks"])
    return result


def assert_same_backend(original, current):
    assert len(original["activity"]) == len(current["activity"]) == 1
    for key in (*IDENTITY_FIELDS, "backend_xid", "xact_start", "state"):
        assert original["activity"][0][key] == current["activity"][0][key], key
    assert original["locks"] == current["locks"]


def natural_exit(connection, held, lifecycle, deadline, record):
    assert lifecycle["reaped"] and lifecycle["events"][-1] == "pipe_eof"
    identity = {key: held["activity"][0][key] for key in IDENTITY_FIELDS}
    stop = min(deadline, monotonic() + 5)
    samples = []
    evidence = {"identity": identity, "samples": samples, "natural_exit": False}
    started = monotonic()
    try:
        while len(samples) < 1024 and monotonic() < stop:
            sample = observe(connection, identity["pid"], stop)
            samples.append(sample)
            if not sample["activity"] and not sample["locks"]:
                evidence["natural_exit"] = True
                return
            for row in sample["activity"]:
                assert {key: row[key] for key in identity} == identity, "backend PID reused"
        raise AssertionError("owned backend or locks did not naturally disappear")
    finally:
        evidence["elapsed_seconds"] = monotonic() - started
        record("loser_natural_exit", evidence)
