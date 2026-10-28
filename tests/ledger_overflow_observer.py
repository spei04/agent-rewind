"""Original sum delegates, caller attribution and physical refusal boundaries."""

import ast
import inspect
from contextlib import contextmanager
from copy import deepcopy

from ledger_eligibility_observer import assert_preparation, refusal_trace
from ledger_overflow_fixture import HALF, OVERFLOW, overflow_manifest

from agent_rewind.migrations import ledger_provisioning, ledger_service
from agent_rewind.migrations.schema import MigrationRefused


def sum_sites():
    source, first = inspect.getsourcelines(ledger_provisioning._prepare_ledger)
    result = {}
    for node in ast.walk(ast.parse("".join(source))):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and ast.unparse(node.value.func) == "_sum_money"
        ):
            (target,) = node.targets
            result[ast.unparse(target)] = first + node.lineno - 1
    assert set(result) == {"total", "organization_opening"}
    source, first = inspect.getsourcelines(ledger_provisioning._sum_money)
    (node,) = [node for node in ast.walk(ast.parse("".join(source))) if isinstance(node, ast.Raise)]
    assert ast.unparse(node.exc) == "MigrationRefused('ledger_exposure_refused')"
    result["refusal"] = first + node.lineno - 1
    return result


def model_rows(values):
    return [value.model_dump(mode="json") for value in values]


@contextmanager
def observe_overflow(watch, monkeypatch, record):
    entries, stages = [], []
    sites = sum_sites()
    projects_original = ledger_service._projects
    prepare_original = ledger_service._prepare_ledger
    sum_original = ledger_provisioning._sum_money
    prepare_code, sum_code = prepare_original.__code__, sum_original.__code__
    sums, gate = [], {}

    def bound(work):
        assert work is watch.work and work._connection.engine is watch.engine
        assert work._raw is watch.trace.raws[0]
        return {"raw_id": id(work._raw), "work_id": id(work), "engine_id": id(watch.engine)}

    def projects(connection, manifest, organization, work):
        gate.update(bound(work))
        assert connection is work._connection
        gate.update(
            manifest=manifest.model_dump(mode="json"),
            organization=organization,
            entry=len(watch.trace.events),
        )
        stages.append("projects.enter")
        result = projects_original(connection, manifest, organization, work)
        gate["return"] = len(watch.trace.events)
        stages.append("projects.return")
        return result

    def summation(values, work):
        caller = inspect.currentframe().f_back
        event = {
            **bound(work),
            "caller_line": caller.f_lineno,
            "original_prepare_caller": caller.f_code is prepare_code,
            "values": deepcopy(values),
            "value_types": [type(value).__name__ for value in values],
            "trace_position": len(watch.trace.events),
        }
        sums.append(event)
        try:
            total = sum_original(values, work)
        except BaseException as error:
            event["error_identity"] = id(error)
            frames = []
            cursor = error.__traceback__
            while cursor is not None:
                if cursor.tb_frame.f_code is sum_code:
                    local = cursor.tb_frame.f_locals
                    frames.append(
                        {
                            "line": cursor.tb_lineno,
                            "values": deepcopy(local.get("values")),
                            "value": local.get("value"),
                            "total": local.get("total"),
                            "work_id": id(local.get("work")),
                        }
                    )
                cursor = cursor.tb_next
            event["sum_frames"] = frames
            raise
        event["total"], event["total_type"] = total, type(total).__name__
        return total

    def prepare(context, manifest, work):
        entry = {
            **bound(work),
            "trace_position": len(watch.trace.events),
            "state": context.state.model_dump(mode="json"),
            "manifest": manifest.model_dump(mode="json"),
            "financial": deepcopy(context.financial),
            "project_gate": gate,
            "sums": sums,
            "sites": sites,
        }
        entries.append(entry)
        stages.append("prepare.enter")
        try:
            result = prepare_original(context, manifest, work)
        except BaseException as error:
            stages.append("prepare.refused")
            entry["error"] = {
                "type": type(error).__name__,
                "code": getattr(error, "code", None),
                "identity": id(error),
            }
            entry["traceback"] = refusal_trace(error, prepare_code)
            frames = []
            cursor = error.__traceback__
            while cursor is not None:
                if cursor.tb_frame.f_code is prepare_code:
                    local = cursor.tb_frame.f_locals
                    frames.append(
                        {
                            "line": cursor.tb_lineno,
                            "imported": model_rows(local.get("imported", [])),
                            "projects": model_rows(local.get("projects", [])),
                            "exposure": deepcopy(local.get("exposure")),
                        }
                    )
                cursor = cursor.tb_next
            entry["reduction_frames"] = frames
            entry["refusal_trace_position"] = len(watch.trace.events)
            raise
        stages.append("prepare.return")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(ledger_service, "_projects", projects)
        patch.setattr(ledger_service, "_prepare_ledger", prepare)
        patch.setattr(ledger_provisioning, "_sum_money", summation)
        try:
            yield entries, stages
        finally:
            record("overflow_preparation", {"records": entries, "stages": stages})


def assert_overflow_refusal(fixture, manifest, case, entry, stages, error, watch):
    assert manifest == overflow_manifest(fixture, case)
    assert_preparation(entry, fixture, manifest, watch)
    assert type(error) is MigrationRefused and error.code == "ledger_exposure_refused"
    assert entry["error"] == {"type": "MigrationRefused", "code": error.code, "identity": id(error)}
    assert stages == ["projects.enter", "projects.return", "prepare.enter", "prepare.refused"]
    sites = sum_sites()
    assert entry["sites"] == sites
    identity = {key: entry[key] for key in ("raw_id", "work_id", "engine_id")}
    gate = entry["project_gate"]
    assert {key: gate[key] for key in identity} == identity
    assert gate["manifest"] == manifest and gate["organization"] == fixture.organization
    assert gate["entry"] <= gate["return"] <= entry["trace_position"]
    (frame,) = entry["reduction_frames"]
    (trace,) = entry["traceback"]["preparation_frames"]
    target = sites["total"] if case == "project" else sites["organization_opening"]
    assert frame["line"] == trace["line"] == target
    imported = [
        {
            "job_id": row["id"],
            "project_id": row["project_id"],
            "budget_microusd": row["budget"],
            "legacy_reserved_microusd": row["reserved"],
        }
        for row in fixture.jobs
    ]
    assert frame["imported"] == imported
    assert trace["assignments"] == {
        row["job_id"]: row for row in manifest["accounts"] if row["scope"] == "job"
    }
    sums = entry["sums"]
    assert all(
        row["original_prepare_caller"] and {key: row[key] for key in identity} == identity
        for row in sums
    )
    assert all(
        row["value_types"] == ["int"] * len(row["values"])
        and all(type(value) is int for value in row["values"])
        for row in sums
    )
    prior = sums[: len(manifest["accounts"])]
    assert len(prior) == len(manifest["accounts"])
    assert all(
        row["values"] == []
        and row["total"] == 0
        and row["total_type"] == "int"
        and "error_identity" not in row
        for row in prior
    )
    reductions = sums[len(prior) :]
    if case == "project":
        assert len(reductions) == 1 and frame["projects"] == []
        assert reductions[0]["caller_line"] == sites["total"]
    else:
        assert len(reductions) == 3
        expected_projects = []
        for row, destination in zip(
            reductions[:2], manifest["opening_accounts"]["projects"], strict=True
        ):
            expected_values = [
                job["reserved"]
                for job in fixture.jobs
                if job["project_id"] == destination["project_id"]
            ]
            assert row["caller_line"] == sites["total"] and row["values"] == expected_values
            assert row["total"] == HALF and type(row["total"]) is int and row["total_type"] == "int"
            assert "error_identity" not in row
            expected_projects.append({**destination, "opening_held_microusd": HALF})
        assert frame["projects"] == expected_projects
    failed = reductions[-1]
    assert failed["caller_line"] == target and failed["values"] == [HALF, 0, HALF]
    assert sum(failed["values"]) == OVERFLOW
    assert failed["error_identity"] == id(error) and "total" not in failed
    (rejected,) = failed["sum_frames"]
    assert rejected == {
        "line": sites["refusal"],
        "values": [HALF, 0, HALF],
        "value": HALF,
        "total": HALF,
        "work_id": id(watch.work),
    }
    assert type(rejected["value"]) is type(rejected["total"]) is int
    expected_exposure = {
        row["id"]: next(job["reserved"] for job in fixture.jobs if job["id"] == row["job_id"])
        for row in manifest["accounts"]
        if row["scope"] == "job"
    }
    if case == "organization":
        expected_exposure.update({row["account_id"]: HALF for row in frame["projects"]})
    assert frame["exposure"] == expected_exposure
    assert (
        watch.outcome.confirmed_precommit_rollback
        and not watch.outcome.commit_attempted
        and not watch.outcome.cleanup_failed
    )
    names = [
        "rollback.before_native",
        "rollback.native_ack",
        "connection.close.before",
        "connection.close.return",
        "command.exit",
    ]
    markers = [row for row in watch.markers if row[0] in names]
    assert [row[0] for row in markers] == names and all(
        row[1] == entry["raw_id"] for row in markers
    )
    assert entry["trace_position"] <= entry["refusal_trace_position"] <= markers[0][2]
    assert "commit.before_native" not in [row[0] for row in watch.markers]
