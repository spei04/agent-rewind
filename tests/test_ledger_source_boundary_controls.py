"""Pure controls for the new witness; no database, provider or process execution."""

from copy import deepcopy

import pytest
from ledger_provisioning_fixture import digest, next_manifest
from ledger_source_boundary import assert_new_intent, assert_witness, source_site

from agent_rewind.migrations.schema import LEDGER


def witness():
    gate, refusal = source_site()
    identity = {"raw_id": 11, "work_id": 12, "engine_id": 13, "connection_id": 14}
    manifest = {"manifest_id": "new", "source_digest": "wrong", "parent_manifest_digest": "parent"}
    events = []
    for sql in ("PRAGMA busy_timeout=4000", "SELECT value FROM records"):
        events.extend(
            [
                ("c_call", "bootstrap", 11, "execute"),
                ("sql", "bootstrap", 11, sql),
                ("c_return", "bootstrap", 11, "execute"),
            ]
        )
    receipt = {
        "preparation": [
            {
                **identity,
                "original_caller": True,
                "line": gate - 1,
                "completed": True,
                "manifest": manifest,
                "entered_at": 0,
                "returned_at": 0,
                "state": {
                    "revision": LEDGER,
                    "manifest_count": 1,
                    "head": {"manifest_id": "old", "manifest_digest": "parent"},
                },
                "financial": {"account": [None] * 5},
            }
        ],
        "hashes": [
            {
                **identity,
                "original_caller": True,
                "line": gate,
                "entered_at": 0,
                "returned_at": 6,
                "work_before": 10,
                "work_after": 12,
                "result": "actual",
            }
        ],
        "refusals": [
            {
                **identity,
                "line": refusal,
                "exception_id": 15,
                "type": "MigrationRefused",
                "code": "source_digest_mismatch",
                "position": 6,
            }
        ],
    }
    return receipt, manifest, "actual", identity, 15, events


def test_complete_first_gate_witness_is_accepted():
    assert_witness(*witness())


@pytest.mark.parametrize(
    "target,key,value",
    [
        ("preparation", "completed", False),
        ("preparation", "original_caller", False),
        ("hashes", "original_caller", False),
        ("hashes", "line", 197),
        ("hashes", "raw_id", 99),
        ("hashes", "work_id", 99),
        ("hashes", "result", "wrong"),
        ("hashes", "work_after", 10),
        ("hashes", "entered_at", 6),
        ("refusals", "line", 198),
        ("refusals", "exception_id", 99),
        ("refusals", "position", 7),
    ],
)
def test_incomplete_or_wrong_boundary_is_rejected(target, key, value):
    args = list(deepcopy(witness()))
    args[0][target][0][key] = value
    with pytest.raises(AssertionError):
        assert_witness(*args)


@pytest.mark.parametrize(
    "fault",
    [
        "native-error",
        "missing-return",
        "write",
        "missing-prepare",
        "duplicate-hash",
        "stale-parent",
    ],
)
def test_missing_prerequisite_or_native_evidence_is_rejected(fault):
    args = list(deepcopy(witness()))
    if fault == "native-error":
        args[5][-1] = ("c_exception", "bootstrap", 11, "execute")
    elif fault == "missing-return":
        args[5].pop()
    elif fault == "write":
        args[5][4] = ("sql", "bootstrap", 11, "UPDATE records SET value=1")
    elif fault == "missing-prepare":
        args[0]["preparation"] = []
    elif fault == "duplicate-hash":
        args[0]["hashes"] *= 2
    else:
        args[0]["preparation"][0]["state"]["head"]["manifest_digest"] = "stale"
    with pytest.raises((AssertionError, ValueError)):
        assert_witness(*args)


def intents():
    first = {
        "manifest_id": "old",
        "source_digest": "a" * 64,
        "accounts": [
            {
                "id": "old-org",
                "scope": "organization",
                "period_start": "2000",
                "period_end": "2100",
                "limit_microusd": 245000,
            },
            {
                "id": "old-project",
                "scope": "project",
                "period_start": "2000",
                "period_end": "2100",
                "limit_microusd": 245000,
            },
        ],
    }
    valid = next_manifest(first)
    # Use the helper's actual rollover timestamp in both generations.
    for row in first["accounts"]:
        row["period_end"] = valid["accounts"][0]["period_start"]
    valid["parent_manifest_digest"] = digest(first)
    changed = {**deepcopy(valid), "source_digest": "e" * 64}
    return first, valid, changed


def test_only_requested_source_changes_in_new_intent():
    assert_new_intent(*intents())


@pytest.mark.parametrize("fault", ["extra-change", "stale-parent", "reused-id", "overlap", "cap"])
def test_competing_intent_defects_are_rejected(fault):
    first, valid, changed = intents()
    if fault == "extra-change":
        changed["manifest_id"] = "other"
    elif fault == "stale-parent":
        valid["parent_manifest_digest"] = changed["parent_manifest_digest"] = "stale"
    elif fault == "reused-id":
        valid["manifest_id"] = changed["manifest_id"] = first["manifest_id"]
    else:
        key, value = ("period_start", "2050") if fault == "overlap" else ("limit_microusd", 244999)
        valid["accounts"][0][key] = changed["accounts"][0][key] = value
    with pytest.raises(AssertionError):
        assert_new_intent(first, valid, changed)
