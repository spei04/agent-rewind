"""Observe the original first source-digest gate for an otherwise valid new intent."""

import ast
import inspect
import re
import sys
from contextlib import contextmanager
from copy import deepcopy

from ledger_precommit_boundary_fixture import returned_sql
from ledger_precommit_boundary_observer import identity
from ledger_provisioning_fixture import assert_no_writes, digest

from agent_rewind.migrations import ledger_service, ledger_source
from agent_rewind.migrations.schema import LEDGER, MigrationRefused


def source_site():
    source, first = inspect.getsourcelines(ledger_service.initialize_ledger)
    (gate,) = [
        node
        for node in ast.walk(ast.parse("".join(source)))
        if isinstance(node, ast.If)
        and ast.unparse(node.test) == "source_digest(connection, work) != manifest.source_digest"
    ]
    (refusal,) = gate.body
    assert ast.unparse(refusal.exc) == "MigrationRefused('source_digest_mismatch')"
    return first + gate.lineno - 1, first + refusal.lineno - 1


def assert_new_intent(first, valid, changed):
    assert valid["operation"] == "provision"
    assert valid["manifest_id"] != first["manifest_id"]
    assert valid["parent_manifest_digest"] == digest(first)
    assert valid["source_digest"] == first["source_digest"]
    assert {key for key in valid if valid[key] != changed[key]} == {"source_digest"}
    assert set(valid) == set(changed)
    assert valid["opening_accounts"] is None
    assert len(valid["accounts"]) == 2
    assert [row["scope"] for row in valid["accounts"]] == ["organization", "project"]
    for old, new in zip(first["accounts"][:2], valid["accounts"], strict=True):
        assert new == {
            **old,
            "id": new["id"],
            "period_start": old["period_end"],
            "period_end": new["period_end"],
        }
        assert new["id"] not in {row["id"] for row in first["accounts"]}
        assert new["period_start"] < new["period_end"]


@contextmanager
def observe_source(watch, monkeypatch, record):
    prepare, source = ledger_service._prepare_ledger, ledger_service.source_digest
    assert source is ledger_source.source_digest
    caller = ledger_service.initialize_ledger.__code__
    gate_line, refusal_line = source_site()
    receipt = {"preparation": [], "hashes": [], "refusals": []}

    def bound(work):
        assert work is watch.work
        return identity(watch)

    def preparing(context, manifest, work):
        frame = inspect.currentframe().f_back
        entry = {
            **bound(work),
            "original_caller": frame.f_code is caller,
            "line": frame.f_lineno,
            "state": context.state.model_dump(mode="json"),
            "manifest": manifest.model_dump(mode="json"),
            "financial": deepcopy(context.financial),
            "entered_at": len(watch.trace.events),
        }
        receipt["preparation"].append(entry)
        result = prepare(context, manifest, work)
        entry.update(returned_at=len(watch.trace.events), completed=True)
        return result

    def hashing(connection, work):
        frame = inspect.currentframe().f_back
        assert connection is work._connection
        entry = {
            **bound(work),
            "original_caller": frame.f_code is caller,
            "line": frame.f_lineno,
            "entered_at": len(watch.trace.events),
            "work_before": work.observed_ordinary,
        }
        receipt["hashes"].append(entry)
        result = source(connection, work)
        entry.update(
            returned_at=len(watch.trace.events),
            work_after=work.observed_ordinary,
            result=result,
        )
        return result

    def tracing(frame, event, arg):
        if frame.f_code is not caller:
            return None
        if event == "exception":
            _, error, _ = arg
            receipt["refusals"].append(
                {
                    **bound(frame.f_locals["work"]),
                    "line": frame.f_lineno,
                    "exception_id": id(error),
                    "type": type(error).__name__,
                    "code": getattr(error, "code", None),
                    "position": len(watch.trace.events),
                }
            )
        return tracing

    previous = sys.gettrace()
    assert previous is None
    with monkeypatch.context() as patch:
        patch.setattr(ledger_service, "_prepare_ledger", preparing)
        patch.setattr(ledger_service, "source_digest", hashing)
        sys.settrace(tracing)
        try:
            yield receipt
        finally:
            sys.settrace(previous)
            record("source_boundary", receipt)
    assert gate_line < refusal_line


def assert_witness(receipt, manifest, expected_source, expected_identity, exception_id, events):
    (prepared,) = receipt["preparation"]
    (hashed,) = receipt["hashes"]
    (refused,) = receipt["refusals"]
    gate_line, refusal_line = source_site()
    for entry in (prepared, hashed, refused):
        assert {key: entry[key] for key in expected_identity} == expected_identity
    assert prepared["original_caller"] and prepared["line"] == gate_line - 1
    assert prepared["completed"] is True and prepared["manifest"] == manifest
    state = prepared["state"]
    assert state["revision"] == LEDGER and state["manifest_count"] == 1
    assert state["head"]["manifest_digest"] == manifest["parent_manifest_digest"]
    assert state["head"]["manifest_id"] != manifest["manifest_id"]
    assert len(prepared["financial"]["account"]) == 5
    assert hashed["original_caller"] and hashed["line"] == gate_line
    assert hashed["result"] == expected_source != manifest["source_digest"]
    assert (
        prepared["entered_at"]
        <= prepared["returned_at"]
        <= hashed["entered_at"]
        < hashed["returned_at"]
        == refused["position"]
    )
    assert refused == {
        **expected_identity,
        "line": refusal_line,
        "exception_id": exception_id,
        "type": "MigrationRefused",
        "code": "source_digest_mismatch",
        "position": hashed["returned_at"],
    }
    sql = returned_sql(
        events[hashed["entered_at"] : hashed["returned_at"]], expected_identity["raw_id"]
    )
    assert len(sql) > 0 and len(sql) % 2 == 0
    assert hashed["work_after"] - hashed["work_before"] == len(sql)
    for setter, query in zip(sql[::2], sql[1::2], strict=True):
        assert re.fullmatch(r"PRAGMA busy_timeout=[1-9][0-9]*", setter)
        assert query.startswith(("SELECT ", "WITH "))


def assert_refusal(receipt, manifest, expected_source, error, watch):
    assert type(error) is MigrationRefused and error.code == "source_digest_mismatch"
    assert_witness(
        receipt, manifest, expected_source, identity(watch), id(error), watch.trace.events
    )
    assert_no_writes(watch.actions)
    watch.assert_single_attempt()
    assert watch.outcome.confirmed_precommit_rollback
    assert watch.outcome.rollback_acknowledged and not watch.outcome.commit_attempted
    assert not watch.outcome.cleanup_failed and watch.faults == []
    names = [
        "rollback.before_native",
        "rollback.native_ack",
        "connection.close.before",
        "connection.close.return",
        "command.exit",
    ]
    selected = [row for row in watch.markers if row[0] in names]
    assert [row[0] for row in selected] == names
    assert all(row[1] == id(watch.work._raw) for row in selected)
    assert [row[2] for row in selected] == sorted(row[2] for row in selected)
    start = receipt["refusals"][0]["position"]
    assert start <= selected[0][2]
    assert returned_sql(
        watch.trace.events[selected[0][2] : selected[1][2]], id(watch.work._raw)
    ) == ["ROLLBACK"]
    tail = [
        row[3]
        for row in watch.trace.events[start : watch.command_boundary["trace_end"]]
        if row[0] == "sql"
    ]
    assert tail == ["ROLLBACK", f"PRAGMA busy_timeout={watch.work.previous_timeout}"]
    boundary = watch.command_boundary
    assert not boundary["raw_closed"] and boundary["in_transaction"] is False
    assert boundary["receipt_clean"] and boundary["receipt_completed"]
    assert boundary["checkedout"] == 0
