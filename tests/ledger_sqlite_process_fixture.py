"""Fresh SQLite operator child stopped at an observed physical COMMIT boundary."""

import json
import os
import socket
import sys
from time import monotonic
from types import SimpleNamespace

import pytest
from ledger_process_fixture import receive_frame, send_frame
from ledger_recovery_fixture import observe_command

from agent_rewind import sqlite_ownership
from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_engine import create_ledger_engine
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest


def run(channel):
    request = receive_frame(channel, monotonic() + 15)
    assert set(request) == {"nonce", "case", "phase", "deadline", "configuration"}
    assert request["phase"] in {"before", "after"}
    configuration = request["configuration"]
    assert set(configuration) == {"url", "manifest"}
    fixture = SimpleNamespace(
        case=SimpleNamespace(operator_engine=lambda: create_ledger_engine(configuration["url"]))
    )
    properties = {}
    patch = pytest.MonkeyPatch()
    try:
        with observe_command(fixture, patch, properties.__setitem__, label="held_command") as watch:
            finalize_delegate = ledger_service._finalize
            classify_delegate = ledger_service._classify_manifest
            commit_delegate = sqlite_ownership._TrackedSQLite.commit
            final_context = None
            final_receipt = None
            stages = []

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
                assert len(watch.works) == len(watch.outcomes) == len(watch.trace.raws) == 1
                assert raw is watch.trace.raws[0] and raw.in_transaction
                assert final_receipt is not None
                assert [row[0] for row in stages] == ["finalize.return", "classify.return"]
                watch.mark("death.before_physical_commit", raw)
                if request["phase"] == "after":
                    commit_delegate(raw)
                    assert raw.in_transaction is False
                    watch.mark("death.physical_commit_ack", raw)
                assert watch.outcome.commit_attempted and not watch.outcome.commit_acknowledged
                assert not watch.outcome.cleanup_failed and not watch.work.cleanup_observations
                watch.record(properties.__setitem__, "held_command")
                send_frame(
                    channel,
                    {
                        "nonce": request["nonce"],
                        "pid": os.getpid(),
                        "case": request["case"],
                        "phase": request["phase"],
                        "sequence": 1,
                        "raw_id": id(raw),
                        "witness": {
                            "observation": json.loads(properties["held_command"]),
                            "stages": stages,
                            "receipt": final_receipt,
                            "in_transaction": raw.in_transaction,
                            "ownership_closed": raw._ownership.closed,
                            "connection_closed": watch.work._connection.closed,
                            "work_detached": watch.work._detached,
                        },
                    },
                    request["deadline"],
                )
                # No return or continuation command exists: parent must kill this
                # exact blocked child. EOF/deadline is a failed attempt.
                receive_frame(channel, request["deadline"])
                raise AssertionError("held child unexpectedly received a continuation")

            patch.setattr(ledger_service, "_finalize", finalize)
            patch.setattr(ledger_service, "_classify_manifest", classify)
            patch.setattr(sqlite_ownership._TrackedSQLite, "commit", commit)
            ledger_service.initialize_ledger(
                watch.engine, validate_ledger_manifest(configuration["manifest"])
            )
            raise AssertionError("death-test child returned a successful service response")
    finally:
        patch.undo()


if __name__ == "__main__":
    with socket.socket(fileno=int(sys.argv[1])) as control:
        run(control)
