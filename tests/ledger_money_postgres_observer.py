"""Observe the unchanged preparation delegate on its native PostgreSQL handle."""

from contextlib import contextmanager
from copy import deepcopy

from ledger_eligibility_fixture import rows
from ledger_eligibility_observer import assert_preparation, refusal_trace
from ledger_money_observer import amount_site
from ledger_restore_authority import typed

from agent_rewind.migrations import ledger_service


@contextmanager
def observe_money(watch, monkeypatch, record):
    records, stages = [], []
    original = ledger_service._prepare_ledger
    code, line = amount_site()

    def prepare(context, manifest, work):
        assert work is watch.work and work._connection.engine is watch.engine
        assert watch.trace.handles == [work._raw]
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
            cursor, amounts = error.__traceback__, []
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


def assert_native_preparation(entry, fixture, manifest, watch):
    assert_preparation(entry, fixture, manifest, watch)
    assert typed(entry["manifest"]) == typed(manifest)
    expected = sorted(rows(fixture.before, "jobs"), key=lambda row: row["id"])
    assert typed(sorted(entry["financial"]["job"], key=lambda row: row["id"])) == typed(expected)
    scopes = sorted(
        [row for row in rows(fixture.before, "resource_scopes") if row["resource_kind"] == "job"],
        key=lambda row: row["resource_id"],
    )
    assert typed(sorted(entry["financial"]["scope"], key=lambda row: row["resource_id"])) == typed(
        scopes
    )
