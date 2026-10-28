"""One original initialize attempt, held immediately before its acquisition LOCK."""

import hashlib
import json
import os
import socket
import sys
from time import monotonic
from types import SimpleNamespace

import psycopg
import pytest
from ledger_acquisition_postgres_fixture import (
    MODES,
    assert_held,
    assert_origins,
    assert_result,
    lock_sql,
)
from ledger_competing_process import IDENTITY_KEYS, WORK_SECONDS, validate_control
from ledger_process_fixture import receive_frame, send_frame
from ledger_recovery_postgres_fixture import observe_command
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

from agent_rewind.migrations import ledger_service, ledger_transaction, service
from agent_rewind.migrations.ledger_engine import create_ledger_engine
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused


def run(channel):
    request = receive_frame(channel, monotonic() + 15)
    assert set(request) == IDENTITY_KEYS | {"deadline", "configuration"}
    assert request["pid"] == os.getpid() and request["role"] == "winner"
    assert (
        type(request["deadline"]) is float and 0 < request["deadline"] - monotonic() <= WORK_SECONDS
    )
    config = request["configuration"]
    assert set(config) == {"url", "control_url", "manifest", "tables", "mode"}
    assert config["mode"] in MODES
    manifest = validate_ledger_manifest(config["manifest"])
    assert hashlib.sha256(manifest.canonical_bytes).hexdigest() == request["intent_sha256"]
    assert_origins()
    target_sql = lock_sql(config["tables"])
    identity = {key: request[key] for key in IDENTITY_KEYS}
    fixture = SimpleNamespace(
        case=SimpleNamespace(operator_engine=lambda: create_ledger_engine(config["url"]))
    )
    control_engine = create_engine(config["control_url"], poolclass=NullPool)
    owner_engine = create_engine(config["url"], poolclass=NullPool)
    pg = {"control": control_engine, "owner": owner_engine}
    properties, parameters, native_errors, mappings, held_messages = {}, [], [], [], []
    patch = pytest.MonkeyPatch()
    previous_trace = sys.gettrace()
    assert previous_trace is None
    body_entries = lock_delegations = 0
    mapping_lines = []
    native_object = mapped_object = None
    refusal = receipt = None
    try:
        with observe_command(fixture, pg, patch, properties.__setitem__, label="command") as watch:
            driver_delegate = Connection.exec_driver_sql
            native_delegate = psycopg.Cursor.execute
            mapping_delegate = ledger_transaction._ordinary_error
            body_delegate = ledger_transaction._register_ledger_body
            original_code = service._postgres_exclusion.__code__

            def work_identity():
                raw = watch.work._raw
                assert watch.trace.handles == [raw] and watch.claims[0].raw is raw
                assert watch.work._connection.engine is watch.engine
                return {
                    "raw_id": id(raw),
                    "engine_id": id(watch.engine),
                    "connection_id": id(watch.work._connection),
                    "work_id": id(watch.work),
                    "claim_id": id(watch.claims[0]),
                }

            def observation(label):
                watch.record(properties.__setitem__, label)
                value = json.loads(properties[label])
                value["work_identity"] = work_identity()
                return value

            def response(sequence, phase, witness):
                return {
                    **identity,
                    "sequence": sequence,
                    "phase": phase,
                    "raw_id": id(watch.work._raw),
                    "engine_id": id(watch.engine),
                    "witness": witness,
                }

            def receive_control(sequence, action):
                validate_control(
                    receive_frame(channel, request["deadline"]),
                    identity,
                    raw_id=id(watch.work._raw),
                    engine_id=id(watch.engine),
                    sequence=sequence,
                    action=action,
                )

            def held(sequence, site):
                raw = watch.work._raw
                message = response(
                    sequence,
                    "held",
                    {
                        "sql": target_sql,
                        "original_site": site,
                        "observation": observation("held"),
                        "parameters": list(parameters),
                        "backend_pid": raw.info.backend_pid,
                        "database": raw.info.dbname,
                        "role": raw.info.user,
                        "transaction_status": int(raw.info.transaction_status),
                        "raw_closed": raw.closed,
                        "connection_closed": watch.work._connection.closed,
                        "claim_released": watch.claims[0].released,
                        "work_detached": watch.work._detached,
                    },
                )
                assert_held(message, config["tables"])
                held_messages.append(message)
                send_frame(channel, message, request["deadline"])

            def driver(connection, statement, *args, **kwargs):
                nonlocal lock_delegations
                if connection.engine is watch.engine and statement == target_sql:
                    frame = sys._getframe(1)
                    assert frame.f_code is original_code and frame.f_lineno == 107
                    assert frame.f_locals["connection"] is connection
                    assert frame.f_locals["tables"] == config["tables"]
                    assert connection is watch.work._connection and lock_delegations == 0
                    assert not args and not kwargs
                    site = {
                        "file": "agent_rewind/migrations/service.py",
                        "function": frame.f_code.co_name,
                        "line": frame.f_lineno,
                    }
                    held(1, site)
                    receive_control(2, "probe")
                    held(3, site)
                    receive_control(4, "continue")
                    lock_delegations += 1
                return driver_delegate(connection, statement, *args, **kwargs)

            def execute(cursor, query, *args, **kwargs):
                nonlocal native_object
                statement = query.decode() if isinstance(query, bytes) else str(query)
                values = args[0] if args else kwargs.get("params")
                parameters.append(
                    {
                        "sql": statement,
                        "raw_id": id(cursor.connection),
                        "type": type(values).__name__,
                        "values": dict(values)
                        if hasattr(values, "items")
                        else list(values)
                        if type(values) in (tuple, list)
                        else values,
                    }
                )
                try:
                    return native_delegate(cursor, query, *args, **kwargs)
                except psycopg.Error as error:
                    assert statement == target_sql and watch.owns(cursor.connection)
                    assert native_errors == []
                    native_object = error
                    native_errors.append(
                        {
                            "error_id": id(error),
                            "sqlstate": error.sqlstate,
                            "raw_id": id(cursor.connection),
                            "sql": statement,
                            "status": int(cursor.connection.info.transaction_status),
                            "trace_end": len(watch.trace.events),
                        }
                    )
                    raise

            def traced_mapping(frame, event, arg):
                if frame.f_code is mapping_delegate.__code__ and event == "line":
                    mapping_lines.append(frame.f_lineno)
                return traced_mapping

            def ordinary_error(error):
                nonlocal mapped_object
                assert isinstance(error, DBAPIError) and error.orig is native_object
                assert mappings == []
                mapped_object = mapping_delegate(error)
                mappings.append(
                    {
                        "wrapper_type": type(error).__name__,
                        "wrapper_id": id(error),
                        "native_id": id(error.orig),
                        "mapped_id": id(mapped_object),
                        "mapped_type": type(mapped_object).__name__,
                        "mapped_code": mapped_object.code,
                        "original_mapping": 280 in mapping_lines,
                        "original_mapping_line": 280,
                    }
                )
                return mapped_object

            def register_body(*args, **kwargs):
                nonlocal body_entries
                body_entries += 1
                return body_delegate(*args, **kwargs)

            patch.setattr(Connection, "exec_driver_sql", driver)
            patch.setattr(psycopg.Cursor, "execute", execute)
            patch.setattr(ledger_transaction, "_ordinary_error", ordinary_error)
            patch.setattr(ledger_transaction, "_register_ledger_body", register_body)
            sys.settrace(traced_mapping)
            try:
                receipt = ledger_service.initialize_ledger(watch.engine, manifest)
            except MigrationRefused as error:
                assert error is mapped_object and len(mappings) == 1
                mappings[0]["caught_id"] = id(error)
                refusal = {"code": error.code, "error_id": id(error)}
            finally:
                sys.settrace(previous_trace)
        # This point is reached only after the unchanged outer database drain.
        assert len(native_errors) == len(mappings) == 1 and len(held_messages) == 2
        result = response(
            5,
            "result",
            {
                "observation": observation("final"),
                "parameters": parameters,
                "native_error": native_errors[0],
                "mapped_error": mappings[0],
                "receipt": receipt,
                "refusal": refusal,
                "body_entries": body_entries,
                "lock_delegations": lock_delegations,
            },
        )
        assert_result(result, held_messages[0], config["mode"])
        send_frame(channel, result, request["deadline"])
    finally:
        sys.settrace(previous_trace)
        patch.undo()
        control_engine.dispose()
        owner_engine.dispose()


if __name__ == "__main__":
    with socket.socket(fileno=int(sys.argv[1])) as channel:
        run(channel)
