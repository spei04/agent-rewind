"""Original overflow delegates bound to the actual native PostgreSQL handle."""

import inspect
from contextlib import contextmanager
from copy import deepcopy

from ledger_eligibility_observer import refusal_trace
from ledger_overflow_observer import model_rows, sum_sites

from agent_rewind.migrations import ledger_provisioning, ledger_service


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
        assert watch.trace.handles == [work._raw]
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
