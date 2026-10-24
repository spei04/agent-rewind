"""Observe the actual two cohort refusals without changing preparation behavior."""

import ast
import inspect
from contextlib import contextmanager
from copy import deepcopy

from agent_rewind.migrations import ledger_provisioning, ledger_service
from agent_rewind.migrations.schema import MigrationRefused


def cohort_sites():
    source, first = inspect.getsourcelines(ledger_provisioning._prepare_ledger)
    tree = ast.parse("".join(source))
    sites = {}
    for name, condition in {
        "cohort": "set(assignments) != set(jobs)",
        "missing-job": "job is None or scopes.get(account.job_id) != account.project_id",
    }.items():
        (node,) = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.If) and ast.unparse(node.test) == condition
        ]
        (refusal,) = node.body
        assert isinstance(refusal, ast.Raise)
        assert ast.unparse(refusal.exc) == "MigrationRefused('ledger_history_unsupported')"
        sites[name] = first + refusal.lineno - 1
    return ledger_provisioning._prepare_ledger.__code__, sites


def cohort_trace(error, code):
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
            account = values.get("account")
            assignments = values.get("assignments")
            rejected.append(
                {
                    "line": cursor.tb_lineno,
                    "jobs": deepcopy(values.get("jobs")),
                    "scopes": deepcopy(values.get("scopes")),
                    "current": deepcopy(values.get("current")),
                    "account": account.model_dump(mode="json") if account is not None else None,
                    "job": deepcopy(values.get("job")),
                    "assignments": {
                        key: row.model_dump(mode="json") for key, row in assignments.items()
                    }
                    if assignments is not None
                    else None,
                }
            )
        cursor = cursor.tb_next
    return {"frames": frames, "preparation_frames": rejected}


@contextmanager
def observe_cohort(watch, monkeypatch, record, *, raw_handle=None):
    records, stages = [], []
    code, sites = cohort_sites()
    original = ledger_service._prepare_ledger

    def prepare(context, manifest, work):
        assert work is watch.work and work._connection.engine is watch.engine
        assert work._raw is (watch.trace.raws[0] if raw_handle is None else raw_handle(watch))
        entry = {
            "raw_id": id(work._raw),
            "work_id": id(work),
            "engine_id": id(watch.engine),
            "trace_position": len(watch.trace.events),
            "state": context.state.model_dump(mode="json"),
            "organization": context.history.ownership.organization_id,
            "manifest": manifest.model_dump(mode="json"),
            "financial": deepcopy(context.financial),
            "sites": sites,
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
            entry["traceback"] = cohort_trace(error, code)
            entry["refusal_trace_position"] = len(watch.trace.events)
            raise
        entry["returned"] = True
        stages.append("prepare.return")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(ledger_service, "_prepare_ledger", prepare)
        try:
            yield records, stages
        finally:
            record("cohort_preparation", {"records": records, "stages": stages})


def assert_cohort_refusal(entry, stages, error, watch, *, case, target_job):
    assert type(error) is MigrationRefused and error.code == "ledger_history_unsupported"
    assert entry["error"] == {
        "type": "MigrationRefused",
        "code": "ledger_history_unsupported",
        "identity": id(error),
    }
    assert "returned" not in entry and stages == ["prepare.enter", "prepare.refused"]
    assert entry["sites"] == cohort_sites()[1]
    (rejected,) = entry["traceback"]["preparation_frames"]
    jobs = {row["id"]: row for row in entry["financial"]["job"]}
    scopes = {
        row["resource_id"]: row["project_id"]
        for row in entry["financial"]["scope"]
        if row["resource_kind"] == "job"
    }
    assert rejected["jobs"] == jobs and rejected["scopes"] == scopes
    assert rejected["current"] == entry["financial"]["account"] == []
    accounts = entry["manifest"]["accounts"]
    assignments = {row["job_id"]: row for row in accounts if row["scope"] == "job"}
    assert all(row["organization_id"] == entry["organization"] for row in accounts)
    for job_id, account in assignments.items():
        if job_id in jobs:
            assert account["project_id"] == scopes[job_id]
            assert account["limit_microusd"] <= jobs[job_id]["budget"]
    if case in {"omit-admitted-zero", "omit-reserved-legacy"}:
        assert rejected["line"] == entry["sites"]["cohort"]
        assert rejected["assignments"] == assignments
        assert set(jobs) - set(assignments) == {target_job}
        assert not set(assignments) - set(jobs)
        assert rejected["account"] == accounts[-1]
    else:
        assert case == "nonexistent-job"
        assert rejected["line"] == entry["sites"]["missing-job"]
        assert set(assignments) - set(jobs) == {target_job}
        assert not set(jobs) - set(assignments)
        assert rejected["account"] == assignments[target_job]
        assert rejected["job"] is None and target_job not in scopes
        assert rejected["assignments"] is None
    assert watch.outcome.confirmed_precommit_rollback
    assert not watch.outcome.commit_attempted and not watch.outcome.cleanup_failed
    names = [
        "rollback.before_native",
        "rollback.native_ack",
        "connection.close.before",
        "connection.close.return",
        "command.exit",
    ]
    selected = [row for row in watch.markers if row[0] in names]
    assert [row[0] for row in selected] == names
    assert all(row[1] == entry["raw_id"] for row in selected)
    assert entry["trace_position"] <= entry["refusal_trace_position"] <= selected[0][2]
    assert "commit.before_native" not in [row[0] for row in watch.markers]
