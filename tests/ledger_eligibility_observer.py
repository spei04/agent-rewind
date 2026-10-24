"""Delegated preparation-stage observations; earlier failures receive no eligibility credit."""

import ast
import inspect
from contextlib import contextmanager
from copy import deepcopy

from ledger_eligibility_fixture import rows

from agent_rewind.migrations import ledger_provisioning, ledger_service
from agent_rewind.migrations.schema import MigrationRefused


def eligibility_site():
    """Locate the real status/queue rejection without replacing its execution."""
    source, first = inspect.getsourcelines(ledger_provisioning._prepare_ledger)
    nodes = [
        node
        for node in ast.walk(ast.parse("".join(source)))
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.BoolOp)
        and isinstance(node.test.op, ast.Or)
        and ast.unparse(node.test.values[0])
        == "job['status'] not in {'succeeded', 'failed', 'cancelled', 'queued'}"
    ]
    (node,) = nodes
    (refusal,) = node.body
    assert isinstance(refusal, ast.Raise)
    assert ast.unparse(refusal.exc) == "MigrationRefused('ledger_history_unsupported')"
    function = ledger_provisioning._prepare_ledger
    return function.__code__, first + refusal.lineno - 1


def refusal_trace(error, code):
    frames, rejected = [], []
    cursor = error.__traceback__
    while cursor is not None:
        frame = cursor.tb_frame
        frames.append(
            {
                "file": frame.f_code.co_filename,
                "module": frame.f_globals.get("__name__"),
                "function": frame.f_code.co_name,
                "line": cursor.tb_lineno,
            }
        )
        if frame.f_code is code:
            values = frame.f_locals
            rejected.append(
                {
                    "line": cursor.tb_lineno,
                    "job_id": values.get("identity"),
                    "job": deepcopy(values.get("job")),
                    "assignments": {
                        key: value.model_dump(mode="json")
                        for key, value in values.get("assignments", {}).items()
                    },
                }
            )
        cursor = cursor.tb_next
    return {"frames": frames, "preparation_frames": rejected}


@contextmanager
def observe_preparation(watch, monkeypatch, record_property, *, raw_handle=None):
    records, stages = [], []
    code, refusal_line = eligibility_site()
    original = ledger_service._prepare_ledger
    upgrade, write = ledger_service._upgrade, ledger_service._write

    def prepare(context, manifest, work):
        assert work is watch.work and work._connection.engine is watch.engine
        assert work._raw is (watch.trace.raws[0] if raw_handle is None else raw_handle(watch))
        entry = {
            "raw_id": id(work._raw),
            "work_id": id(work),
            "engine_id": id(watch.engine),
            "trace_position": len(watch.trace.events),
            "state": context.state.model_dump(mode="json"),
            "manifest": manifest.model_dump(mode="json"),
            "financial": deepcopy(context.financial),
        }
        records.append(entry)
        stages.append("prepare.enter")
        try:
            result = original(context, manifest, work)
        except BaseException as error:
            stages.append("prepare.refused")
            entry["error"] = {
                "type": type(error).__name__,
                "code": getattr(error, "code", None),
                "identity": id(error),
            }
            entry["traceback"] = refusal_trace(error, code)
            entry["eligibility_line"] = refusal_line
            entry["refusal_trace_position"] = len(watch.trace.events)
            raise
        entry["prepared"] = {
            "jobs": [row.model_dump(mode="json") for row in result.jobs],
            "project_totals": [row.model_dump(mode="json") for row in result.project_totals],
            "organization_opening": result.organization_opening,
        }
        stages.append("prepare.return")
        return result

    def observed_upgrade(*args, **kwargs):
        stages.append("upgrade")
        return upgrade(*args, **kwargs)

    def observed_write(connection, name, values):
        stages.append("write:" + name)
        return write(connection, name, values)

    with monkeypatch.context() as patch:
        patch.setattr(ledger_service, "_prepare_ledger", prepare)
        patch.setattr(ledger_service, "_upgrade", observed_upgrade)
        patch.setattr(ledger_service, "_write", observed_write)
        try:
            yield records, stages
        finally:
            record_property("eligibility_preparation", {"records": records, "stages": stages})


def assert_preparation(entry, fixture, manifest, watch):
    assert entry["raw_id"] == id(watch.work._raw)
    assert entry["work_id"] == id(watch.work) and entry["engine_id"] == id(watch.engine)
    assert entry["manifest"] == manifest
    assert entry["manifest"]["source_digest"] == fixture.source
    assert entry["state"]["status"] == "absent" and entry["state"]["head"] is None
    assert entry["state"]["revision"] == "ar_0006_admission"
    expected = sorted(rows(fixture.before, "jobs"), key=lambda row: row["id"])
    assert sorted(entry["financial"]["job"], key=lambda row: row["id"]) == expected
    assert entry["financial"]["account"] == []
    expected_scopes = sorted(
        [row for row in rows(fixture.before, "resource_scopes") if row["resource_kind"] == "job"],
        key=lambda row: row["resource_id"],
    )
    assert (
        sorted(entry["financial"]["scope"], key=lambda row: row["resource_id"]) == expected_scopes
    )


def assert_eligibility_refusal(entry, stages, error, watch, *, target_job):
    assert type(error) is MigrationRefused and error.code == "ledger_history_unsupported"
    assert entry["error"] == {
        "type": "MigrationRefused",
        "code": "ledger_history_unsupported",
        "identity": id(error),
    }
    (rejected,) = entry["traceback"]["preparation_frames"]
    assert rejected["line"] == entry["eligibility_line"] == eligibility_site()[1]
    assert rejected["job_id"] == target_job
    (job,) = [row for row in entry["financial"]["job"] if row["id"] == target_job]
    assert rejected["job"] == job
    assert rejected["assignments"] == {
        row["job_id"]: row for row in entry["manifest"]["accounts"] if row["scope"] == "job"
    }
    assert "prepared" not in entry and stages == ["prepare.enter", "prepare.refused"]
    assert watch.outcome.confirmed_precommit_rollback
    assert not watch.outcome.commit_attempted and not watch.outcome.cleanup_failed
    selected = [
        row
        for row in watch.markers
        if row[0]
        in {
            "rollback.before_native",
            "rollback.native_ack",
            "connection.close.before",
            "connection.close.return",
            "command.exit",
        }
    ]
    assert len(selected) == 5 and all(row[1] == entry["raw_id"] for row in selected)
    assert entry["trace_position"] <= entry["refusal_trace_position"] <= selected[0][2]
    markers = [name for name, _, _ in watch.markers]
    assert markers.index("rollback.before_native") < markers.index("rollback.native_ack")
    assert markers.index("rollback.native_ack") < markers.index("connection.close.before")
    assert markers.index("connection.close.return") < markers.index("command.exit")
    assert "commit.before_native" not in markers
