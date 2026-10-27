"""Delegating observation of the original complete-reader and old-receipt path."""

import ast
import inspect
import sys
from contextlib import contextmanager
from copy import deepcopy

from ledger_accounted_carry_postgres_observer import financial_projection, ordered
from ledger_evolved_replay_fixture import equal
from ledger_restore_authority import typed

from agent_rewind.migrations import ledger_service

NEW_INTENT = (
    "_prepare_ledger",
    "source_digest",
    "_provenance",
    "_write",
    "_upgrade",
    "_ledger_cursors",
    "_finalize",
)


def replay_financial(before):
    """Select the original ar7 reader scopes; retain the complete snapshot separately."""
    _, financial = financial_projection(before)
    financial["scope"] = [
        row for row in financial["scope"] if row["resource_kind"] in {"job", "provider_call"}
    ]
    return financial


def sites():
    lines, start = inspect.getsourcelines(ledger_service.initialize_ledger)
    tree = ast.parse("".join(lines))
    result = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"_inspect_ledger_context", "_classify_manifest"}
        ):
            result.setdefault(node.func.id, []).append(start + node.lineno - 1)
    return result


def anchor(watch):
    work = watch.work
    assert work._connection.engine is watch.engine
    return {
        "raw_id": id(work._raw),
        "work_id": id(work),
        "engine_id": id(watch.engine),
        "connection_id": id(work._connection),
    }


@contextmanager
def observe_replay(watch, monkeypatch, record):
    observations = {"inspection": [], "classification": [], "new_intent": []}
    originals = {
        name: getattr(ledger_service, name)
        for name in ("_inspect_ledger_context", "_classify_manifest", *NEW_INTENT)
    }
    original_code = ledger_service.initialize_ledger.__code__

    def entry(frame):
        return {
            **anchor(watch),
            "entered_at": len(watch.trace.events),
            "original_caller": frame.f_code is original_code,
            "line": frame.f_lineno,
        }

    def failed(value, error):
        value["error"] = {
            "type": type(error).__name__,
            "code": getattr(error, "code", None),
            "identity": id(error),
        }
        value["refused_at"] = len(watch.trace.events)

    def inspection(connection):
        assert connection is watch.work._connection
        value = entry(sys._getframe(1))
        observations["inspection"].append(value)
        try:
            context = originals["_inspect_ledger_context"](connection)
        except BaseException as error:
            failed(value, error)
            raise
        value.update(
            context_id=id(context),
            state=context.state.model_dump(mode="json"),
            financial={
                domain: typed(ordered(values)) for domain, values in context.financial.items()
            },
            returned_at=len(watch.trace.events),
        )
        return context

    def classify(context, manifest, work):
        assert work is watch.work
        value = {
            **entry(sys._getframe(1)),
            "context_id": id(context),
            "manifest": manifest.model_dump(mode="json"),
        }
        observations["classification"].append(value)
        try:
            result = originals["_classify_manifest"](context, manifest, work)
        except BaseException as error:
            failed(value, error)
            raise
        value.update(
            receipt=None if result is None else result.model_dump(mode="json"),
            returned_at=len(watch.trace.events),
        )
        return result

    def branch(name):
        def delegated(*args, **kwargs):
            value = {**entry(sys._getframe(1)), "name": name}
            observations["new_intent"].append(value)
            try:
                result = originals[name](*args, **kwargs)
            except BaseException as error:
                failed(value, error)
                raise
            value["returned_at"] = len(watch.trace.events)
            return result

        return delegated

    with monkeypatch.context() as patch:
        patch.setattr(ledger_service, "_inspect_ledger_context", inspection)
        patch.setattr(ledger_service, "_classify_manifest", classify)
        for name in NEW_INTENT:
            patch.setattr(ledger_service, name, branch(name))
        try:
            yield observations
        finally:
            record("observation", deepcopy(observations))


def assert_observation(
    observed, manifest, original_receipt, current_state, identity, trace_end, financial
):
    assert set(observed) == {"inspection", "classification", "new_intent"}
    equal(observed["new_intent"], [])
    (reader,) = observed["inspection"]
    (classification,) = observed["classification"]
    locations = sites()
    for row, name in ((reader, "_inspect_ledger_context"), (classification, "_classify_manifest")):
        assert "error" not in row
        equal(row["original_caller"], True)
        equal(row["line"], locations[name][0])
        for key, value in identity.items():
            assert type(value) is int and value > 0
            equal(row[key], value)
        for key in ("entered_at", "returned_at", "context_id"):
            assert type(row[key]) is int and row[key] >= 0
        assert row["entered_at"] <= row["returned_at"] <= trace_end
    assert reader["context_id"] > 0
    equal(classification["context_id"], reader["context_id"])
    assert reader["returned_at"] <= classification["entered_at"]
    equal(reader["state"], current_state)
    equal(
        reader["financial"],
        {domain: typed(ordered(values)) for domain, values in financial.items()},
    )
    equal(classification["manifest"], manifest)
    equal(classification["receipt"], {k: v for k, v in original_receipt.items() if k != "outcome"})
