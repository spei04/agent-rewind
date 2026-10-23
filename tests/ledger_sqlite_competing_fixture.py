"""Fresh SQLite commands with a resumable physical boundary and scoped cleanup."""

import hashlib
import json
import os
import socket
import sys
from time import monotonic
from types import SimpleNamespace

import pytest
from ledger_competing_process import IDENTITY_KEYS, WORK_SECONDS, validate_control
from ledger_process_fixture import receive_frame, send_frame
from ledger_recovery_fixture import observe_command

from agent_rewind import sqlite_ownership
from agent_rewind.migrations import ledger_service, ledger_transaction
from agent_rewind.migrations.ledger_engine import create_ledger_engine
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused


def run(channel):
    request = receive_frame(channel, monotonic() + 15)
    assert set(request) == IDENTITY_KEYS | {"deadline", "configuration"}
    assert request["pid"] == os.getpid() and request["role"] in {"winner", "loser", "replay"}
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
    properties, stages, native_errors = {}, [], []
    receipt = refusal = None
    patch = pytest.MonkeyPatch()
    try:
        with observe_command(fixture, patch, properties.__setitem__, label="command") as watch:
            finalize_delegate = ledger_service._finalize
            classify_delegate = ledger_service._classify_manifest
            commit_delegate = sqlite_ownership._TrackedSQLite.commit
            error_delegate = ledger_transaction._ordinary_error
            final_context = final_receipt = None

            def ordinary_error(error):
                mapped = error_delegate(error)
                native_errors.append(
                    {
                        "type": type(error).__name__,
                        "sqlite_errorcode": getattr(error, "sqlite_errorcode", None),
                        "mapped_type": type(mapped).__name__,
                        "mapped_code": mapped.code,
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

            def response(sequence, phase, witness):
                return {
                    **identity,
                    "sequence": sequence,
                    "phase": phase,
                    "raw_id": id(watch.work._raw),
                    "engine_id": id(watch.engine),
                    "witness": witness,
                }

            def held(raw, sequence):
                assert raw.in_transaction and not raw._ownership.closed
                assert not watch.work._connection.closed and not watch.work._detached
                assert watch.outcome.commit_attempted and not watch.outcome.commit_acknowledged
                assert not watch.outcome.cleanup_failed and not watch.work.cleanup_observations
                watch.record(properties.__setitem__, "held")
                send_frame(
                    channel,
                    response(
                        sequence,
                        "held",
                        {
                            "observation": json.loads(properties["held"]),
                            "stages": stages,
                            "receipt": final_receipt,
                            "in_transaction": raw.in_transaction,
                            "ownership_closed": raw._ownership.closed,
                            "connection_closed": watch.work._connection.closed,
                            "work_detached": watch.work._detached,
                        },
                    ),
                    request["deadline"],
                )

            def commit(raw):
                if not watch.owns(raw):
                    return commit_delegate(raw)
                assert request["role"] == "winner"
                assert watch.trace.raws == [raw]
                assert final_receipt is not None
                assert [row[0] for row in stages] == ["finalize.return", "classify.return"]
                watch.mark("competition.before_physical_commit", raw)
                held(raw, 1)
                control = receive_frame(channel, request["deadline"])
                validate_control(
                    control,
                    identity,
                    raw_id=id(raw),
                    engine_id=id(watch.engine),
                    sequence=2,
                    action="probe",
                )
                held(raw, 3)
                control = receive_frame(channel, request["deadline"])
                validate_control(
                    control,
                    identity,
                    raw_id=id(raw),
                    engine_id=id(watch.engine),
                    sequence=4,
                    action="continue",
                )
                result = commit_delegate(raw)
                watch.mark("competition.physical_commit_ack", raw)
                return result

            def forbidden(*args, **kwargs):
                raise AssertionError("explicit replay attempted writer work")

            patch.setattr(ledger_transaction, "_ordinary_error", ordinary_error)
            if request["role"] == "winner":
                patch.setattr(ledger_service, "_finalize", finalize)
                patch.setattr(ledger_service, "_classify_manifest", classify)
                patch.setattr(sqlite_ownership._TrackedSQLite, "commit", commit)
            elif request["role"] == "replay":
                for name in ("_upgrade", "_prepare_ledger", "_provenance", "_write"):
                    patch.setattr(ledger_service, name, forbidden)
            try:
                receipt = ledger_service.initialize_ledger(watch.engine, manifest)
            except MigrationRefused as error:
                refusal = {"type": type(error).__name__, "code": error.code}
        # The accepted observer captures service return before disposing only
        # this process's owned engine. No file-wide drain or snapshot occurs.
        watch.assert_single_attempt()
        send_frame(
            channel,
            response(
                5 if request["role"] == "winner" else 1,
                "result",
                {
                    "observation": json.loads(properties["command"]),
                    "refusal": refusal,
                    "receipt": None if receipt is None else receipt.model_dump(mode="json"),
                    "native_errors": native_errors,
                },
            ),
            request["deadline"],
        )
    finally:
        patch.undo()


if __name__ == "__main__":
    with socket.socket(fileno=int(sys.argv[1])) as channel:
        run(channel)
