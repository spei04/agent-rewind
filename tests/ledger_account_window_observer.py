"""Observe original window gates without replacing their result or exception."""

from contextlib import contextmanager
from copy import deepcopy

import psycopg

from agent_rewind.migrations import ledger_provisioning, ledger_service


def identity(watch):
    work = watch.work
    assert work._connection.engine is watch.engine
    return {
        "raw_id": id(work._raw),
        "work_id": id(work),
        "engine_id": id(watch.engine),
        "connection_id": id(work._connection),
    }


def cursor_frames(error):
    frames = []
    trace = error.__traceback__
    while trace is not None:
        if trace.tb_frame.f_code is ledger_provisioning._ledger_cursors.__code__:
            values = trace.tb_frame.f_locals
            frames.append(
                {
                    "line": trace.tb_lineno,
                    "account": values["account"].model_dump(mode="json")
                    if values.get("account") is not None
                    else None,
                    "initialized_at": values["initialized_at"],
                    "work_id": id(values["work"]),
                    "connection_id": id(values["connection"]),
                }
            )
        trace = trace.tb_next
    return frames


@contextmanager
def observe_window(watch, monkeypatch, record):
    observations = {
        "classification": [],
        "writes": [],
        "executions": [],
        "provenance": [],
        "cursors": [],
        "native_calls": [],
    }
    delegates = {
        name: getattr(ledger_service, name)
        for name in ("_classify_manifest", "_write", "_execute", "_provenance", "_ledger_cursors")
    }
    native_execute = psycopg.Cursor.execute
    active = []

    def entry():
        return {**identity(watch), "entered_at": len(watch.trace.events)}

    def finish(value):
        value["returned_at"] = len(watch.trace.events)

    def failed(value, error):
        value["error"] = {
            "type": type(error).__name__,
            "code": getattr(error, "code", None),
            "identity": id(error),
        }
        value["refused_at"] = len(watch.trace.events)

    def classify(context, manifest, work):
        assert work is watch.work
        value = {**entry(), "manifest": manifest.model_dump(mode="json")}
        observations["classification"].append(value)
        try:
            result = delegates["_classify_manifest"](context, manifest, work)
        except BaseException as error:
            failed(value, error)
            raise
        value["receipt"] = None if result is None else result.model_dump(mode="json")
        finish(value)
        return result

    def write(connection, name, values):
        assert connection is watch.work._connection
        value = {**entry(), "name": name, "values": deepcopy(values)}
        observations["writes"].append(value)
        try:
            result = delegates["_write"](connection, name, values)
        except BaseException as error:
            failed(value, error)
            raise
        finish(value)
        return result

    def execute(connection, name, values=None):
        if connection is not watch.work._connection:
            return delegates["_execute"](connection, name, values)
        value = {**entry(), "name": name, "values": deepcopy(values)}
        observations["executions"].append(value)
        active.append(name)
        try:
            result = delegates["_execute"](connection, name, values)
        except BaseException as error:
            failed(value, error)
            raise
        finally:
            assert active.pop() == name
        value["rowcount"] = result.rowcount
        finish(value)
        return result

    def provenance(connection):
        assert connection is watch.work._connection
        value = entry()
        observations["provenance"].append(value)
        try:
            result = delegates["_provenance"](connection)
        except BaseException as error:
            failed(value, error)
            raise
        value["observed"], value["database_role"], value["os_uid"] = result
        finish(value)
        return result

    def cursors(connection, manifest, prepared, observed, role, uid, work):
        assert connection is watch.work._connection and work is watch.work
        value = {
            **entry(),
            "manifest": manifest.model_dump(mode="json"),
            "observed": observed,
            "database_role": role,
            "os_uid": uid,
        }
        observations["cursors"].append(value)
        try:
            result = delegates["_ledger_cursors"](
                connection, manifest, prepared, observed, role, uid, work
            )
        except BaseException as error:
            failed(value, error)
            value["original_frames"] = cursor_frames(error)
            raise
        finish(value)
        return result

    def native(cursor, query, *args, **kwargs):
        if (
            not active
            or active[-1] not in {"accounts.insert", "provenance.observe"}
            or cursor.connection is not watch.work._raw
        ):
            return native_execute(cursor, query, *args, **kwargs)
        value = {
            **entry(),
            "name": active[-1],
            "sql": query.decode() if isinstance(query, bytes) else str(query),
            "parameters": deepcopy(args[0] if args else kwargs.get("params")),
        }
        observations["native_calls"].append(value)
        try:
            result = native_execute(cursor, query, *args, **kwargs)
        except BaseException as error:
            failed(value, error)
            raise
        value["rowcount"] = cursor.rowcount
        finish(value)
        return result

    with monkeypatch.context() as patch:
        for name, function in (
            ("_classify_manifest", classify),
            ("_write", write),
            ("_execute", execute),
            ("_provenance", provenance),
            ("_ledger_cursors", cursors),
        ):
            patch.setattr(ledger_service, name, function)
        patch.setattr(psycopg.Cursor, "execute", native)
        try:
            yield observations
        finally:
            record("window_observation", observations)
