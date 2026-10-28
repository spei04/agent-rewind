"""Contracts for the client row observer without opening a database connection."""

import hashlib
from types import SimpleNamespace

import pytest
from ledger_reader_fixture import RowTransferWatch
from sqlalchemy.engine.cursor import CursorFetchStrategy

METHODS = ("fetchone", "fetchmany", "fetchall")
STATEMENT = "SELECT synthetic_projection"


def result_value(method, row):
    return row if method == "fetchone" else [row]


def fetch_arguments(method):
    result = SimpleNamespace(context=SimpleNamespace(statement=" \n" + STATEMENT + "\n "))
    arguments = (object(), result, object())
    keywords = {}
    if method == "fetchmany":
        arguments += (2,)
    elif method == "fetchone":
        keywords["hard_close"] = True
    return arguments, keywords


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("statements", ["tracked", "unmatched", "none"])
def test_empty_targets_preserve_values_arguments_and_repeated_eof(monkeypatch, method, statements):
    class UnvisitedRow:
        def __iter__(self):
            raise AssertionError("no cell targets were requested")

    row = UnvisitedRow()
    first = row if method == "fetchone" else [row, UnvisitedRow()]
    values = [first, None, None] if method == "fetchone" else [first, [], []]
    calls = []

    def delegate(*args, **kwargs):
        calls.append((args, kwargs))
        return values[len(calls) - 1]

    monkeypatch.setattr(CursorFetchStrategy, method, delegate)
    names = (
        {STATEMENT: "projection"}
        if statements == "tracked"
        else {"SELECT unrelated": "unrelated"}
        if statements == "unmatched"
        else None
    )
    watch = RowTransferWatch(monkeypatch, {}, statements=names)
    fetch = getattr(CursorFetchStrategy, method)
    arguments, keywords = fetch_arguments(method)
    for value in values:
        assert fetch(*arguments, **keywords) is value
    assert calls == [(arguments, keywords)] * 3
    assert watch.hits == []
    expected_counts = [1 if method == "fetchone" else 2, 0, 0]
    assert watch.statement_hits == (
        [{"name": "projection", "method": method, "rows": count} for count in expected_counts]
        if statements == "tracked"
        else []
    )


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("error_type", [RuntimeError, KeyboardInterrupt])
def test_empty_targets_forward_original_exception_once(monkeypatch, method, error_type):
    error = error_type("original-fetch")
    calls = []

    def delegate(*args, **kwargs):
        calls.append((args, kwargs))
        raise error

    monkeypatch.setattr(CursorFetchStrategy, method, delegate)
    watch = RowTransferWatch(monkeypatch, {}, statements={STATEMENT: "projection"})
    arguments, keywords = fetch_arguments(method)
    with pytest.raises(error_type) as seen:
        getattr(CursorFetchStrategy, method)(*arguments, **keywords)
    assert seen.value is error and calls == [(arguments, keywords)]
    assert watch.hits == watch.statement_hits == []


@pytest.mark.parametrize("method", METHODS)
def test_target_map_is_checked_again_after_each_fetch(monkeypatch, method):
    text = "sentinel-雪"
    value = result_value(method, (text, b"unchanged"))
    targets = {}
    calls = []

    def delegate(*args, **kwargs):
        calls.append((args, kwargs))
        return value

    monkeypatch.setattr(CursorFetchStrategy, method, delegate)
    watch = RowTransferWatch(monkeypatch, targets, statements={STATEMENT: "projection"})
    assert watch.targets is targets
    fetch = getattr(CursorFetchStrategy, method)
    arguments, keywords = fetch_arguments(method)
    assert fetch(*arguments, **keywords) is value
    targets["text"] = text
    assert fetch(*arguments, **keywords) is value
    targets.clear()
    assert fetch(*arguments, **keywords) is value
    assert calls == [(arguments, keywords)] * 3
    assert watch.hits == [
        {
            "label": "text",
            "method": method,
            "bytes": len(text.encode()),
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
        }
    ]
    assert watch.statement_hits == [{"name": "projection", "method": method, "rows": 1}] * 3


@pytest.mark.parametrize("method", METHODS)
def test_replacements_resume_when_live_targets_become_nonempty(monkeypatch, method):
    text, replacement = "sentinel-雪", "replacement-雪"
    value = result_value(method, (text, b"unchanged"))
    targets = {"text": text}
    calls = []

    def delegate(*args, **kwargs):
        calls.append((args, kwargs))
        return value

    monkeypatch.setattr(CursorFetchStrategy, method, delegate)
    watch = RowTransferWatch(
        monkeypatch,
        targets,
        replacements={"text": replacement},
        statements={STATEMENT: "projection"},
    )
    fetch = getattr(CursorFetchStrategy, method)
    arguments, keywords = fetch_arguments(method)
    targets.clear()
    assert fetch(*arguments, **keywords) is value
    targets["text"] = text
    changed = fetch(*arguments, **keywords)
    assert changed == result_value(method, (replacement, b"unchanged"))
    assert changed is not value
    targets.clear()
    assert fetch(*arguments, **keywords) is value
    assert calls == [(arguments, keywords)] * 3
    assert [hit["label"] for hit in watch.hits] == ["text"]
    assert watch.statement_hits == [{"name": "projection", "method": method, "rows": 1}] * 3


@pytest.mark.parametrize("method", METHODS)
def test_targets_added_by_delegate_are_observed_on_same_call(monkeypatch, method):
    text = "delegate-target"
    value = result_value(method, (text,))
    targets = {}
    calls = []

    def delegate(*args, **kwargs):
        calls.append((args, kwargs))
        targets["text"] = text
        return value

    monkeypatch.setattr(CursorFetchStrategy, method, delegate)
    watch = RowTransferWatch(monkeypatch, targets)
    arguments, keywords = fetch_arguments(method)
    assert getattr(CursorFetchStrategy, method)(*arguments, **keywords) is value
    assert calls == [(arguments, keywords)]
    assert [hit["label"] for hit in watch.hits] == ["text"]


@pytest.mark.parametrize("mode", ["iterate", "many", "all"])
def test_empty_targets_retain_real_sqlite_statement_receipts(monkeypatch, mode):
    from sqlalchemy import create_engine, text

    statement = "SELECT 1 AS value UNION ALL SELECT 2 AS value"
    engine = create_engine("sqlite://")
    watch = RowTransferWatch(monkeypatch, {}, statements={statement: "projection"})
    try:
        with engine.connect() as connection:
            result = connection.execute(text(statement))
            if mode == "iterate":
                rows = list(result)
                assert list(result) == []
                expected = [("fetchone", 1), ("fetchone", 1), ("fetchone", 0)]
            elif mode == "many":
                rows = result.fetchmany(2)
                assert result.fetchmany(2) == result.fetchmany(2) == []
                expected = [("fetchmany", 2), ("fetchmany", 0)]
            else:
                rows = result.fetchall()
                assert result.fetchall() == []
                expected = [("fetchall", 2)]
        assert [tuple(row) for row in rows] == [(1,), (2,)]
        assert watch.hits == []
        assert watch.statement_hits == [
            {"name": "projection", "method": method, "rows": count} for method, count in expected
        ]
    finally:
        engine.dispose()
