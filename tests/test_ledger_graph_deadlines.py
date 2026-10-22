"""Cooperative deadline checks inside valid, metadata-only study loops."""

import json
from types import SimpleNamespace

import pytest

from agent_rewind.migrations import ledger_work, ownership_lineage
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import MigrationRefused


def graph_rows(groups):
    run_job, study_job, run, study = [f"{number:032x}" for number in range(1, 5)]
    rows = {
        "SELECT id,kind FROM jobs ORDER BY id": [
            SimpleNamespace(id=run_job, kind="run"),
            SimpleNamespace(id=study_job, kind="study"),
        ],
        "SELECT id,revoked,expires FROM api_keys ORDER BY id": [],
        "SELECT id,kind,CAST(data AS TEXT) AS data FROM records ORDER BY id": [
            SimpleNamespace(
                id=run, kind="run", data=json.dumps({"job_id": run_job, "parent_id": None})
            ),
            SimpleNamespace(
                id=study,
                kind="study",
                data=json.dumps(
                    {
                        "job_id": study_job,
                        "source_run": run,
                        "request": {"run_id": run},
                        "candidates": groups,
                        "confirmation": None,
                    }
                ),
            ),
        ],
        "SELECT run_id,step FROM events ORDER BY run_id,step": [],
    }
    return lambda statement: iter(rows[statement])


@pytest.mark.parametrize("boundary", ["group", "pair"])
def test_expiry_during_empty_study_metadata_stops_before_remaining_items(monkeypatch, boundary):
    groups = (
        [{"pairs": []} for _ in range(2000)]
        if boundary == "group"
        else [{"pairs": [{} for _ in range(2000)]}]
    )
    rows = graph_rows(groups)
    baseline = ownership_lineage.reduce_relational_closure(rows)
    assert len(baseline.resources) == 4
    clock = [0.0]
    visits = [0]
    expire = [False]
    original = ownership_lineage._unique_object

    def visit():
        visits[0] += 1
        if expire[0]:
            clock[0] = 121.0

    class Group(dict):
        def get(self, key, default=None):
            if key == "pairs" and boundary == "group":
                visit()
            return super().get(key, default)

    class Pair(dict):
        def __contains__(self, key):
            if boundary == "pair":
                visit()
            return super().__contains__(key)

    def observed_object(items):
        value = original(items)
        if set(value) == {"pairs"}:
            return Group(value)
        return value if value else Pair(value)

    # Preserve the actual unique-key JSON parser and dict semantics. These
    # test-owned observations advance time only after the first loop item starts.
    monkeypatch.setattr(ownership_lineage, "_unique_object", observed_object)
    monkeypatch.setattr(ledger_work, "monotonic", lambda: clock[0])
    assert ownership_lineage.reduce_relational_closure(rows, check=LedgerWork().check) == baseline
    assert visits[0] >= 2000
    assert ownership_lineage.reduce_relational_closure(rows, check=None) == baseline

    visits[0] = 0
    expire[0] = True
    with pytest.raises(MigrationRefused, match="^migration_busy$"):
        ownership_lineage.reduce_relational_closure(rows, check=LedgerWork().check)
    # A pair has only two arm probes. Expiry must be checked before another
    # group/pair is consumed, even when it contributes no retained edge.
    assert 1 <= visits[0] <= 2
