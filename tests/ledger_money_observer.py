"""Observe the original amount-versus-job-limit branch without replacing it."""

import ast
import inspect
from contextlib import contextmanager
from copy import deepcopy

from ledger_eligibility_observer import assert_preparation, refusal_trace

from agent_rewind.migrations import ledger_provisioning, ledger_service
from agent_rewind.migrations.schema import MigrationRefused


def amount_site():
    source, first = inspect.getsourcelines(ledger_provisioning._prepare_ledger)
    condition = (
        "type(amount) is not int or not 0 <= amount <= job['budget'] "
        "or amount > assignments[identity].limit_microusd"
    )
    (node,) = [
        node
        for node in ast.walk(ast.parse("".join(source)))
        if isinstance(node, ast.If) and ast.unparse(node.test) == condition
    ]
    (refusal,) = node.body
    assert isinstance(refusal, ast.Raise)
    assert ast.unparse(refusal.exc) == "MigrationRefused('ledger_exposure_refused')"
    return ledger_provisioning._prepare_ledger.__code__, first + refusal.lineno - 1


@contextmanager
def observe_money(watch, monkeypatch, record):
    records, stages = [], []
    original = ledger_service._prepare_ledger
    code, line = amount_site()

    def prepare(context, manifest, work):
        assert work is watch.work and work._connection.engine is watch.engine
        assert work._raw is watch.trace.raws[0]
        entry = {
            "raw_id": id(work._raw),
            "work_id": id(work),
            "engine_id": id(watch.engine),
            "trace_position": len(watch.trace.events),
            "state": context.state.model_dump(mode="json"),
            "manifest": manifest.model_dump(mode="json"),
            "financial": deepcopy(context.financial),
            "amount_line": line,
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
            cursor = error.__traceback__
            amounts = []
            while cursor is not None:
                if cursor.tb_frame.f_code is code:
                    values = cursor.tb_frame.f_locals
                    amounts.append(
                        {
                            "amount": values.get("amount"),
                            "jobs": deepcopy(values.get("jobs")),
                            "scopes": deepcopy(values.get("scopes")),
                            "current": deepcopy(values.get("current")),
                        }
                    )
                cursor = cursor.tb_next
            entry["amount_frames"] = amounts
            entry["refusal_trace_position"] = len(watch.trace.events)
            raise
        entry["prepared"] = {
            "jobs": [row.model_dump(mode="json") for row in result.jobs],
            "project_totals": [row.model_dump(mode="json") for row in result.project_totals],
            "organization_opening": result.organization_opening,
        }
        stages.append("prepare.return")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(ledger_service, "_prepare_ledger", prepare)
        try:
            yield records, stages
        finally:
            record("money_preparation", {"records": records, "stages": stages})


def assert_job_cap_refusal(fixture, manifest, target, entry, stages, error, watch):
    assert_preparation(entry, fixture, manifest, watch)
    assert type(error) is MigrationRefused and error.code == "ledger_exposure_refused"
    assert entry["error"] == {
        "type": "MigrationRefused",
        "code": "ledger_exposure_refused",
        "identity": id(error),
    }
    assert stages == ["prepare.enter", "prepare.refused"] and "prepared" not in entry
    (frame,) = entry["traceback"]["preparation_frames"]
    (amount,) = entry["amount_frames"]
    assert frame["line"] == entry["amount_line"] == amount_site()[1]
    jobs = {row["id"]: row for row in entry["financial"]["job"]}
    scopes = {
        row["resource_id"]: row["project_id"]
        for row in entry["financial"]["scope"]
        if row["resource_kind"] == "job"
    }
    assignments = {row["job_id"]: row for row in manifest["accounts"] if row["scope"] == "job"}
    assert frame["assignments"] == assignments and set(assignments) == set(jobs)
    assert frame["job_id"] == target and frame["job"] == jobs[target]
    assert amount["jobs"] == jobs and amount["scopes"] == scopes
    assert amount["current"] == entry["financial"]["account"] == []
    assert type(amount["amount"]) is int and amount["amount"] == jobs[target]["reserved"]
    assert jobs[target]["budget"] >= amount["amount"] > assignments[target]["limit_microusd"] >= 0
    for identity, assignment in assignments.items():
        assert assignment["project_id"] == scopes[identity] == fixture.project
        assert assignment["limit_microusd"] <= jobs[identity]["budget"]
    assert watch.outcome.confirmed_precommit_rollback
    assert not watch.outcome.commit_attempted and not watch.outcome.cleanup_failed
    names = [
        "rollback.before_native",
        "rollback.native_ack",
        "connection.close.before",
        "connection.close.return",
        "command.exit",
    ]
    markers = [row for row in watch.markers if row[0] in names]
    assert [row[0] for row in markers] == names
    assert all(row[1] == entry["raw_id"] for row in markers)
    assert entry["trace_position"] <= entry["refusal_trace_position"] <= markers[0][2]
    assert "commit.before_native" not in [row[0] for row in watch.markers]
