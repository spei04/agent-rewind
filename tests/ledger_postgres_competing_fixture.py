"""One fresh native command; held boundaries precede any command response."""

import hashlib
import json
import os
import socket
import sys
from time import monotonic
from types import SimpleNamespace

import psycopg
import pytest
from ledger_competing_native import observe_owned
from ledger_competing_process import IDENTITY_KEYS, WORK_SECONDS, validate_control
from ledger_process_fixture import receive_frame, send_frame

from agent_rewind.migrations import ledger_service, ledger_transaction
from agent_rewind.migrations.ledger_engine import create_ledger_engine
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused
from agent_rewind.migrations.service import MIGRATOR_LOCK

TRY_LOCK_SQL = "SELECT pg_try_advisory_xact_lock(%(key)s)"


def run(channel):
    request = receive_frame(channel, monotonic() + 15)
    assert set(request) == IDENTITY_KEYS | {"deadline", "configuration"}
    assert type(request["pid"]) is int and request["pid"] == os.getpid()
    assert request["role"] in {"winner", "loser", "replay"}
    assert type(request["deadline"]) is float
    assert 0 < request["deadline"] - monotonic() <= WORK_SECONDS
    configuration = request["configuration"]
    assert set(configuration) == {"url", "manifest"}
    manifest = validate_ledger_manifest(configuration["manifest"])
    assert hashlib.sha256(manifest.canonical_bytes).hexdigest() == request["intent_sha256"]
    identity = {key: request[key] for key in IDENTITY_KEYS}
    fixture = SimpleNamespace(
        case=SimpleNamespace(operator_engine=lambda: create_ledger_engine(configuration["url"]))
    )
    properties, stages, native_errors, try_locks = {}, [], [], []
    receipt = refusal = None
    patch = pytest.MonkeyPatch()
    try:
        with observe_owned(
            fixture, patch, properties.__setitem__, observe_writes=request["role"] == "replay"
        ) as watch:
            finalize_delegate = ledger_service._finalize
            classify_delegate = ledger_service._classify_manifest
            commit_delegate = psycopg.Connection.commit
            execute_delegate = psycopg.Cursor.execute
            fetch_delegate = psycopg.Cursor.fetchone
            error_delegate = ledger_transaction._ordinary_error
            queries = {}
            final_context = final_receipt = None

            def response(sequence, phase, witness):
                return {
                    **identity,
                    "sequence": sequence,
                    "phase": phase,
                    "raw_id": id(watch.work._raw),
                    "engine_id": id(watch.engine),
                    "witness": witness,
                }

            def control(sequence, action):
                validate_control(
                    receive_frame(channel, request["deadline"]),
                    identity,
                    raw_id=id(watch.work._raw),
                    engine_id=id(watch.engine),
                    sequence=sequence,
                    action=action,
                )

            def held(raw, sequence, boundary):
                assert watch.trace.handles == [raw] and watch.claims[0].raw is raw
                assert not raw.closed
                assert raw.info.transaction_status == psycopg.pq.TransactionStatus.INTRANS
                assert not watch.work._connection.closed and not watch.work._detached
                assert not watch.claims[0].released
                assert not watch.outcome.cleanup_failed and not watch.work.cleanup_observations
                watch.record(properties.__setitem__, "held")
                send_frame(
                    channel,
                    response(
                        sequence,
                        "held",
                        {
                            "boundary": boundary,
                            "observation": json.loads(properties["held"]),
                            "stages": stages,
                            "receipt": final_receipt,
                            "try_locks": try_locks,
                            "backend_pid": raw.info.backend_pid,
                            "database": raw.info.dbname,
                            "role": raw.info.user,
                            "transaction_status": int(raw.info.transaction_status),
                            "raw_closed": raw.closed,
                            "claim_released": watch.claims[0].released,
                            "connection_closed": watch.work._connection.closed,
                            "work_detached": watch.work._detached,
                        },
                    ),
                    request["deadline"],
                )

            def execute(cursor, query, *args, **kwargs):
                statement = query.decode() if isinstance(query, bytes) else str(query)
                queries[id(cursor)] = None
                result = execute_delegate(cursor, query, *args, **kwargs)
                if watch.owns(cursor.connection) and statement == TRY_LOCK_SQL:
                    parameters = args[0] if args else kwargs.get("params")
                    assert dict(parameters) == {"key": MIGRATOR_LOCK}
                    assert type(parameters["key"]) is int
                    queries[id(cursor)] = {
                        "sql": statement,
                        "parameters": dict(parameters),
                        "cursor_id": id(cursor),
                        "raw_id": id(cursor.connection),
                        "execute_return_trace_index": len(watch.trace.events) - 1,
                    }
                return result

            def fetchone(cursor):
                row = fetch_delegate(cursor)
                query = queries.get(id(cursor))
                if query is not None and row is not None:
                    assert len(row) == 1 and type(row[0]) is bool
                    raw = cursor.connection
                    assert watch.owns(raw) and try_locks == []
                    fetched = {
                        **query,
                        "fetched": row[0],
                        "fetch_return_trace_index": len(watch.trace.events),
                        "backend_pid": raw.info.backend_pid,
                        "database": raw.info.dbname,
                        "role": raw.info.user,
                    }
                    try_locks.append(fetched)
                    watch.trace.events.append(
                        (watch.trace.phase, "try-lock-fetched", id(raw), row[0])
                    )
                    if row[0] is False:
                        assert request["role"] == "loser"
                        watch.mark("competition.false_try_lock", raw)
                        held(raw, 1, "fetched_false_try_lock_before_cleanup")
                        control(2, "continue")
                    else:
                        assert request["role"] in {"winner", "replay"}
                return row

            def ordinary_error(error):
                mapped = error_delegate(error)
                native_errors.append(
                    {
                        "type": type(error).__name__,
                        "code": getattr(error, "code", None),
                        "mapped_type": type(mapped).__name__,
                        "mapped_code": mapped.code,
                        "same_error": mapped is error,
                    }
                )
                return mapped

            def finalize(connection, *args):
                nonlocal final_context
                result = finalize_delegate(connection, *args)
                assert connection.engine is watch.engine
                final_context = result
                stages.append(("finalize.return", len(watch.trace.events)))
                return result

            def classify(context, *args):
                nonlocal final_receipt
                result = classify_delegate(context, *args)
                if context is final_context:
                    assert result is not None
                    final_receipt = result.model_dump(mode="json")
                    stages.append(("classify.return", len(watch.trace.events)))
                return result

            def commit(raw):
                if not watch.owns(raw):
                    return commit_delegate(raw)
                assert request["role"] == "winner"
                assert final_receipt is not None
                assert [row[0] for row in stages] == ["finalize.return", "classify.return"]
                assert watch.outcome.commit_attempted and not watch.outcome.commit_acknowledged
                watch.mark("competition.before_physical_commit", raw)
                held(raw, 1, "final_proof_before_physical_commit")
                control(2, "probe")
                held(raw, 3, "final_proof_before_physical_commit")
                control(4, "continue")
                result = commit_delegate(raw)
                assert raw.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
                watch.mark("competition.physical_commit_ack", raw)
                return result

            def forbidden(*args, **kwargs):
                raise AssertionError("explicit replay attempted writer work")

            patch.setattr(psycopg.Cursor, "execute", execute)
            patch.setattr(psycopg.Cursor, "fetchone", fetchone)
            patch.setattr(ledger_transaction, "_ordinary_error", ordinary_error)
            if request["role"] == "winner":
                patch.setattr(ledger_service, "_finalize", finalize)
                patch.setattr(ledger_service, "_classify_manifest", classify)
                patch.setattr(psycopg.Connection, "commit", commit)
            elif request["role"] == "replay":
                for name in ("_upgrade", "_prepare_ledger", "_provenance", "_write"):
                    patch.setattr(ledger_service, name, forbidden)
            try:
                receipt = ledger_service.initialize_ledger(watch.engine, manifest)
            except MigrationRefused as error:
                refusal = {"type": type(error).__name__, "code": error.code}
        # The early try-lock refusal never enters a registered body and has no
        # xid observations. Its separate oracle checks that exact native path.
        if request["role"] != "loser":
            watch.assert_single_attempt()
        if request["role"] == "replay":
            watch.assert_no_writes()
        sequence = {"winner": 5, "loser": 3, "replay": 1}[request["role"]]
        send_frame(
            channel,
            response(
                sequence,
                "result",
                {
                    "observation": json.loads(properties["command"]),
                    "refusal": refusal,
                    "receipt": None if receipt is None else receipt.model_dump(mode="json"),
                    "native_errors": native_errors,
                    "try_locks": try_locks,
                    "scoped_cleanup": properties["scoped_cleanup"],
                },
            ),
            request["deadline"],
        )
    finally:
        patch.undo()


if __name__ == "__main__":
    with socket.socket(fileno=int(sys.argv[1])) as channel:
        run(channel)
