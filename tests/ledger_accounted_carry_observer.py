"""Original held-only preparation, exact persisted delta and physical success oracles."""

import inspect
from contextlib import contextmanager
from copy import deepcopy

from ledger_accounted_carry_fixture import replace_rows
from ledger_eligibility_fixture import rows
from ledger_provisioning_fixture import canonical, digest, expected_stage

from agent_rewind.migrations import ledger_provisioning, ledger_service
from agent_rewind.migrations.schema import LEDGER


@contextmanager
def observe_carry(watch, monkeypatch, record, *, raw_handle=None):
    entries, sources = [], []
    original = ledger_service._prepare_ledger
    summation = ledger_provisioning._sum_money
    source_digest = ledger_service.source_digest
    prepare_code = original.__code__

    def bound(work):
        assert work is watch.work and work._connection.engine is watch.engine
        raw = watch.trace.raws[0] if raw_handle is None else raw_handle(watch)
        assert work._raw is raw
        return {"work_id": id(work), "raw_id": id(work._raw), "engine_id": id(watch.engine)}

    def total(values, work):
        frame = inspect.currentframe().f_back
        event = {
            **bound(work),
            "original_caller": frame.f_code is prepare_code,
            "line": frame.f_lineno,
            "values": deepcopy(values),
            "account": frame.f_locals["account"].model_dump(mode="json"),
            "position": len(watch.trace.events),
        }
        entries[-1]["sums"].append(event)
        result = summation(values, work)
        event.update(total=result, returned_at=len(watch.trace.events))
        return result

    def prepare(context, manifest, work):
        entry = {
            **bound(work),
            "manifest": manifest.model_dump(mode="json"),
            "state": context.state.model_dump(mode="json"),
            "financial": deepcopy(context.financial),
            "entered_at": len(watch.trace.events),
            "sums": [],
        }
        entries.append(entry)
        result = original(context, manifest, work)
        entry.update(
            returned_at=len(watch.trace.events),
            prepared={
                "jobs": [r.model_dump(mode="json") for r in result.jobs],
                "project_totals": [r.model_dump(mode="json") for r in result.project_totals],
                "exposure": dict(result.exposure),
                "organization_opening": result.organization_opening,
            },
        )
        return result

    def source(connection, work):
        receipt = bound(work)
        assert connection is work._connection
        result = source_digest(connection, work)
        sources.append({**receipt, "value": result, "position": len(watch.trace.events)})
        return result

    with monkeypatch.context() as patch:
        patch.setattr(ledger_service, "_prepare_ledger", prepare)
        patch.setattr(ledger_provisioning, "_sum_money", total)
        patch.setattr(ledger_service, "source_digest", source)
        try:
            yield entries, sources
        finally:
            record("carry_preparation", {"entries": entries, "source_receipts": sources})


def assert_carry(entry, sources, fixture, first, manifest, prior_state, watch):
    identity = {
        "work_id": id(watch.work),
        "raw_id": id(watch.work._raw),
        "engine_id": id(watch.engine),
    }
    assert {key: entry[key] for key in identity} == identity
    assert entry["manifest"] == manifest and entry["state"] == prior_state
    assert manifest["parent_manifest_digest"] == digest(first)
    assert manifest["source_digest"] == fixture.source
    assert manifest["operation"] == "provision" and manifest["opening_accounts"] is None
    old = rows(fixture.before, "budget_accounts")
    assert len(old) == 3 and all(
        a["held_microusd"] == 0 and a["accounted_microusd"] == 1 for a in old
    )
    assert sorted(entry["financial"]["account"], key=lambda a: a["id"]) == sorted(
        old, key=lambda a: a["id"]
    )
    for key, table in (
        ("job", "jobs"),
        ("call", "provider_calls"),
        ("entry", "budget_entries"),
        ("scope", "resource_scopes"),
        ("ref", "artifact_refs"),
    ):
        assert sorted(entry["financial"][key], key=repr) == sorted(
            rows(fixture.before, table), key=repr
        )
    assert entry["prepared"] == {
        "jobs": [],
        "project_totals": [],
        "exposure": {},
        "organization_opening": 0,
    }
    assert len(entry["sums"]) == len(manifest["accounts"]) == 2
    for event, account in zip(entry["sums"], manifest["accounts"], strict=True):
        assert account["scope"] in {"organization", "project"}
        assert type(account["limit_microusd"]) is int and account["limit_microusd"] == 0
        (previous,) = [
            a for a in old if (a["scope"], a["scope_id"]) == (account["scope"], account["scope_id"])
        ]
        assert previous["period_end"] <= account["period_start"]
        assert event["original_caller"] is True and event["line"] == 136
        assert {key: event[key] for key in identity} == identity
        assert event["account"] == account and event["values"] == [0]
        assert (
            type(event["values"][0]) is int and type(event["total"]) is int and event["total"] == 0
        )
        assert (
            entry["entered_at"] <= event["position"] <= event["returned_at"] <= entry["returned_at"]
        )
    assert len(sources) == 2
    assert all(
        {key: event[key] for key in identity} == identity and event["value"] == fixture.source
        for event in sources
    )
    assert entry["returned_at"] <= sources[0]["position"] <= sources[1]["position"]


def assert_commit(watch):
    watch.assert_single_attempt()
    assert watch.outcome.commit_attempted and watch.outcome.commit_acknowledged
    assert not watch.outcome.rollback_attempted and not watch.outcome.cleanup_failed
    names = [
        "commit.before_native",
        "commit.native_ack",
        "connection.close.before",
        "connection.close.return",
        "command.exit",
    ]
    selected = [r for r in watch.markers if r[0] in names]
    assert [r[0] for r in selected] == names
    assert all(r[1] == id(watch.work._raw) for r in selected)
    assert [r[2] for r in selected] == sorted(r[2] for r in selected)
    boundary = watch.command_boundary
    assert not boundary["raw_closed"] and boundary["checkedout"] == 0
    assert boundary["receipt_clean"] and boundary["in_transaction"] is False


def expected_final(frozen, first, first_receipt, settled, second, second_receipt):
    """Opening always derives from frozen queued0, never the evolved reserved1 job."""
    assert len(frozen.jobs) == 1 and frozen.jobs[0]["reserved"] == 0
    assert all(a["limit_microusd"] == 1 for a in first["accounts"])
    assert first_receipt.imported_jobs == 1 and first_receipt.imported_opening_microusd == 0
    accounts, progress, state = expected_stage(
        frozen, [first, second], [first_receipt, second_receipt]
    )
    old_ids = {a["id"] for a in first["accounts"]}
    accounts = [{**a, "accounted_microusd": 1} if a["id"] in old_ids else a for a in accounts]
    previous = rows(settled, "budget_accounts")
    assert sorted(previous, key=lambda a: a["id"]) == sorted(
        [a for a in accounts if a["id"] in old_ids], key=lambda a: a["id"]
    )
    expected = deepcopy(settled)
    replace_rows(expected, "budget_accounts", accounts)
    old_progress = rows(settled, "migration_progress")
    phase = "ledger_manifest_" + second["manifest_id"]
    cursor, count, source = progress[phase]
    added = {
        "revision": LEDGER,
        "phase": phase,
        "source_digest": source,
        "cursor": canonical(cursor).decode(),
        "rows_verified": count,
        "status": "complete",
        "updated_at": cursor["initialized_at"],
    }
    assert not any(r["revision"] == LEDGER and r["phase"] == phase for r in old_progress)
    replace_rows(expected, "migration_progress", old_progress + [added])
    for row in old_progress:
        if row["revision"] == LEDGER:
            cursor, count, source = progress[row["phase"]]
            assert row == {
                "revision": LEDGER,
                "phase": row["phase"],
                "source_digest": source,
                "cursor": canonical(cursor).decode(),
                "rows_verified": count,
                "status": "complete",
                "updated_at": cursor["initialized_at"],
            }
    return expected, state


def assert_receipt_reentry(actual, written):
    expected = written.model_dump(mode="json")
    assert expected.pop("outcome") == "complete"
    assert actual is not None and actual.model_dump(mode="json") == expected
