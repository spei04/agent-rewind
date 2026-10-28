"""Delegate native classification inside the accepted bounded command worker."""

import socket
import sys
from contextlib import contextmanager

import ledger_postgres_competing_fixture as worker
import psycopg
import pytest

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.schema import MigrationRefused


def run(channel):
    observations, classifications = [], []
    observe_delegate = worker.observe_owned
    classify_delegate = ledger_service._classify_manifest
    send_delegate = worker.send_frame

    @contextmanager
    def observe(*args, **kwargs):
        assert kwargs["observe_writes"] is True
        with observe_delegate(*args, **kwargs) as watch:
            observations.append(watch)
            yield watch

    def classify(context, manifest, work):
        (watch,) = observations
        assert work is watch.work
        raw = work._raw
        (claim,) = watch.claims
        assert watch.owns(raw) and claim.raw is raw
        assert work._connection.engine is watch.engine
        assert not raw.closed and not claim.released
        assert not work._connection.closed and not work._detached
        assert raw.info.transaction_status == psycopg.pq.TransactionStatus.INTRANS
        watch.mark("conflict.classify.enter", raw)
        entry = {
            "raw_id": id(raw),
            "engine_id": id(watch.engine),
            "state": context.state.model_dump(mode="json"),
            "manifest": manifest.model_dump(mode="json"),
            "manifest_digest": manifest.digest,
            "history": [
                {
                    "manifest": cursor.manifest.model_dump(mode="json"),
                    "receipt": cursor.receipt.model_dump(mode="json"),
                }
                for cursor in context.history.manifests
            ],
            "accounts": [dict(row) for row in context.financial["account"]],
            "backend": {
                "pid": raw.info.backend_pid,
                "database": raw.info.dbname,
                "role": raw.info.user,
                "transaction_status": int(raw.info.transaction_status),
                "raw_closed": raw.closed,
                "claim_released": claim.released,
                "connection_closed": work._connection.closed,
                "work_detached": work._detached,
            },
            "refusal": None,
        }
        classifications.append(entry)
        try:
            return classify_delegate(context, manifest, work)
        except MigrationRefused as error:
            entry["refusal"] = {"type": type(error).__name__, "code": error.code}
            watch.mark("conflict.classify.refused", raw)
            raise

    def send(target, message, deadline):
        assert message["role"] == "replay" and message["phase"] == "result"
        (entry,) = classifications
        assert (entry["raw_id"], entry["engine_id"]) == (message["raw_id"], message["engine_id"])
        message["witness"]["classifications"] = classifications
        return send_delegate(target, message, deadline)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(worker, "observe_owned", observe)
        patch.setattr(ledger_service, "_classify_manifest", classify)
        patch.setattr(worker, "send_frame", send)
        worker.run(channel)


if __name__ == "__main__":
    with socket.socket(fileno=int(sys.argv[1])) as channel:
        run(channel)
