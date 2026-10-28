"""Fresh PostgreSQL child held at the actual service COMMIT boundary."""

import json
import os
import socket
import sys
from time import monotonic
from types import SimpleNamespace

import psycopg
import pytest
from ledger_process_fixture import receive_frame, send_frame
from ledger_recovery_postgres_fixture import observe_command
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_engine import create_ledger_engine


def run(channel):
    request = receive_frame(channel, monotonic() + 15)
    assert set(request) == {"nonce", "case", "phase", "deadline", "configuration"}
    assert request["phase"] in {"before", "after"}
    configuration = request["configuration"]
    assert set(configuration) == {"url", "control_url", "manifest"}
    url = make_url(configuration["url"])
    control = create_engine(configuration["control_url"], poolclass=NullPool)
    assert control.url.database != url.database
    fixture = SimpleNamespace(
        case=SimpleNamespace(operator_engine=lambda: create_ledger_engine(configuration["url"]))
    )
    # This lazy, separate-database engine is used only by the existing observer's
    # failure cleanup. A child held successfully at the gate never connects it.
    pg = {"control": control, "owner": SimpleNamespace(url=url)}
    properties = {}
    patch = pytest.MonkeyPatch()
    try:
        with observe_command(
            fixture, pg, patch, properties.__setitem__, label="held_command"
        ) as watch:
            finalize_delegate = ledger_service._finalize
            classify_delegate = ledger_service._classify_manifest
            commit_delegate = psycopg.Connection.commit
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
                assert len(watch.works) == len(watch.outcomes) == len(watch.claims) == 1
                assert watch.trace.handles == [raw]
                assert not raw.closed
                assert raw.info.transaction_status == psycopg.pq.TransactionStatus.INTRANS
                assert final_receipt is not None
                assert [row[0] for row in stages] == ["finalize.return", "classify.return"]
                watch.mark("death.before_physical_commit", raw)
                if request["phase"] == "after":
                    commit_delegate(raw)
                    assert raw.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
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
                            "backend_pid": raw.info.backend_pid,
                            "database": raw.info.dbname,
                            "role": raw.info.user,
                            "transaction_status": int(raw.info.transaction_status),
                            "raw_closed": raw.closed,
                            "connection_closed": watch.work._connection.closed,
                            "work_detached": watch.work._detached,
                            "claim_released": watch.claims[0].released,
                        },
                    },
                    request["deadline"],
                )
                receive_frame(channel, request["deadline"])
                raise AssertionError("held child unexpectedly received a continuation")

            patch.setattr(ledger_service, "_finalize", finalize)
            patch.setattr(ledger_service, "_classify_manifest", classify)
            patch.setattr(psycopg.Connection, "commit", commit)
            manifest = ledger_service.validate_ledger_manifest(configuration["manifest"])
            ledger_service.initialize_ledger(watch.engine, manifest)
            raise AssertionError("death-test child returned a successful service response")
    finally:
        patch.undo()
        control.dispose()


if __name__ == "__main__":
    with socket.socket(fileno=int(sys.argv[1])) as channel:
        run(channel)
