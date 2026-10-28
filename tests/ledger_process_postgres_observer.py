"""Separate-database observations of the exact held backend and its natural exit."""

from time import monotonic

from sqlalchemy import text

ACTIVITY = """
SELECT pid,datid,datname,usename,backend_type,state,backend_xid::text AS backend_xid,
       backend_start,xact_start
FROM pg_stat_activity WHERE pid=:pid
"""
LOCKS = """
SELECT pid,locktype,database,relation,virtualxid,transactionid::text AS transactionid,
       classid,objid,objsubid,mode,granted
FROM pg_locks WHERE pid=:pid
ORDER BY locktype,database,relation,virtualxid,transactionid,classid,objid,objsubid,mode
LIMIT 1025
"""


def observe(connection, pid):
    connection.exec_driver_sql("SELECT pg_stat_clear_snapshot()").close()
    activity = [dict(row) for row in connection.execute(text(ACTIVITY), {"pid": pid}).mappings()]
    locks = [dict(row) for row in connection.execute(text(LOCKS), {"pid": pid}).mappings()]
    assert len(activity) <= 1 and len(locks) <= 1024
    return {"activity": activity, "locks": locks}


def held_backend(pg, marker, table_ids, record):
    witness = marker["witness"]
    pid = witness["backend_pid"]
    assert type(pid) is int and pid > 0
    assert witness["database"] == pg["owner"].url.database
    assert witness["role"] == pg["owner_role"]
    assert pg["control"].url.database != witness["database"]
    with pg["control"].connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql("SET statement_timeout='1s'").close()
        result = observe(connection, pid)
    record("held_backend", result)
    assert len(result["activity"]) == 1
    backend = result["activity"][0]
    assert backend["pid"] == pid
    assert backend["datname"] == witness["database"] and backend["usename"] == witness["role"]
    assert backend["backend_type"] == "client backend"
    assert backend["backend_start"].utcoffset() is not None
    assert all(row["pid"] == pid and row["granted"] for row in result["locks"])
    if marker["phase"] == "before":
        assert backend["state"] == "idle in transaction" and backend["xact_start"] is not None
        xids = witness["observation"]["xids"]
        assert len({row[1] for row in xids}) == 1
        # pg_stat_activity exposes xid32; the writer observes PostgreSQL xid8.
        assert backend["backend_xid"] == str(int(xids[0][1]) % 2**32)
        advisory = [row for row in result["locks"] if row["locktype"] == "advisory"]
        assert len(advisory) == 1 and advisory[0]["mode"] == "ExclusiveLock"
        held_tables = {
            row["relation"]
            for row in result["locks"]
            if row["locktype"] == "relation"
            and row["database"] == backend["datid"]
            and row["mode"] == "AccessExclusiveLock"
        }
        assert set(table_ids.values()) <= held_tables
    else:
        assert backend["state"] == "idle"
        assert backend["backend_xid"] is None and backend["xact_start"] is None
        assert result["locks"] == []
    return result


def natural_backend_exit(pg, held, lifecycle, record):
    """Only observed disappearance passes; this function never terminates a backend."""
    assert lifecycle["reaped"] and lifecycle["events"][-1] == "pipe_eof"
    backend = held["activity"][0]
    identity = {
        key: backend[key] for key in ("pid", "datid", "datname", "usename", "backend_start")
    }
    started = monotonic()
    deadline = started + 5
    samples = []
    evidence = {"identity": identity, "samples": samples, "natural_exit": False}
    try:
        with pg["control"].connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql("SET statement_timeout='1s'").close()
            while len(samples) < 1024 and monotonic() < deadline:
                sample = observe(connection, backend["pid"])
                samples.append(sample)
                if not sample["activity"] and not sample["locks"]:
                    evidence["natural_exit"] = True
                    return
                for row in sample["activity"]:
                    assert {key: row[key] for key in identity} == identity, "backend PID reused"
        raise AssertionError(
            "owned backend or locks did not naturally drain within observation bounds"
        )
    finally:
        evidence["elapsed_seconds"] = monotonic() - started
        record("natural_backend_exit", evidence)
