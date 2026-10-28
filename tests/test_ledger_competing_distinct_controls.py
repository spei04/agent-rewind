"""Offline adversarial controls for collision attribution, not service recovery evidence."""

import sqlite3
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

import ledger_sqlite_conflict_fixture as adapter
import pytest
from ledger_competing_distinct import (
    CASES,
    assert_conflict_context,
    assert_sqlite_conflict,
    changed_parent,
    intents,
    period_key,
    prove_collision,
)
from ledger_provisioning_fixture import ROLLOVER, START, identity

from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused


def table(values, columns=None):
    columns = tuple(values[0]) if values else tuple(columns or ())
    return {"columns": columns, "rows": [tuple(row[key] for key in columns) for row in values]}


def example(case="scope-start"):
    organization, project, other = (identity(number) for number in (1, 2, 3))
    account = {
        "id": identity(100),
        "organization_id": organization,
        "scope": "organization",
        "scope_id": organization,
        "project_id": None,
        "job_id": None,
        "period_start": START,
        "period_end": ROLLOVER,
        "limit_microusd": 245000,
    }
    first = {
        "schema_version": 1,
        "installation_key": "test-installation",
        "manifest_id": identity(1000),
        "operation": "initialize",
        "source_digest": "a" * 64,
        "parent_manifest_digest": None,
        "backup_evidence_digest": "b" * 64,
        "drain_evidence_digest": "d" * 64,
        "accounts": [account],
        "opening_accounts": {"organization_account_id": account["id"], "projects": []},
    }
    before = {
        "tables": {
            "migration_progress": table([{"phase": "ledger_manifest_" + first["manifest_id"]}]),
            "budget_accounts": table([account]),
            "organizations": table([{"id": organization}]),
            "projects": table(
                [{"id": item, "organization_id": organization} for item in (project, other)]
            ),
        }
    }
    winner, loser = intents(first, case, project=project, other_project=other)
    return before, first, winner, loser


@pytest.mark.parametrize("case", CASES)
def test_collision_proof_distinguishes_exact_identity_and_project_association(case):
    before, _, winner, loser = example(case)
    proof = prove_collision(before, winner, loser, case)
    if case == "account-id":
        assert proof["collisions"]["account_ids"] and not proof["collisions"]["scope_starts"]
        assert winner["accounts"][0]["period_end"] <= loser["accounts"][0]["period_start"]
    else:
        assert not proof["collisions"]["account_ids"]
        assert proof["collisions"]["scope_starts"] == [period_key(winner["accounts"][0])]
    assert len(proof["projects"]) == (2 if case == "shared-organization" else 0)


@pytest.mark.parametrize(
    "change",
    [
        "different-parent",
        "different-installation",
        "known-manifest",
        "existing-id",
        "existing-start",
        "no-collision",
        "accidental-id",
        "equal-projects",
        "wrong-project-organization",
        "absent-project",
        "project-key-collision",
    ],
)
def test_collision_proof_rejects_alternative_explanations(change):
    before, _, winner, loser = example("shared-organization")
    if change == "different-parent":
        loser["parent_manifest_digest"] = "c" * 64
    elif change == "different-installation":
        loser["installation_key"] = "other-installation"
    elif change == "known-manifest":
        before["tables"]["migration_progress"]["rows"].append(
            ("ledger_manifest_" + loser["manifest_id"],)
        )
    elif change in {"existing-id", "existing-start"}:
        account = deepcopy(loser["accounts"][0])
        if change == "existing-id":
            account.update(period_start=START, period_end=ROLLOVER)
        else:
            account["id"] = identity(999)
        before["tables"]["budget_accounts"] = table([account])
    elif change == "no-collision":
        loser["accounts"][0].update(
            period_start="2200-01-01T00:00:00.000000Z",
            period_end="2300-01-01T00:00:00.000000Z",
        )
    elif change == "accidental-id":
        loser["accounts"][0]["id"] = winner["accounts"][0]["id"]
    elif change in {"equal-projects", "project-key-collision"}:
        loser["accounts"][1].update(
            scope_id=winner["accounts"][1]["scope_id"],
            project_id=winner["accounts"][1]["project_id"],
        )
        if change == "equal-projects":
            loser["accounts"][1].update(
                period_start="2200-01-01T00:00:00.000000Z",
                period_end="2300-01-01T00:00:00.000000Z",
            )
    elif change == "wrong-project-organization":
        before["tables"]["projects"]["rows"][1] = (identity(3), identity(99))
    else:
        assert change == "absent-project"
        before["tables"]["projects"]["rows"].pop()
    with pytest.raises(AssertionError):
        prove_collision(before, winner, loser, "shared-organization")


def test_account_id_proof_rejects_additional_period_overlap():
    before, _, winner, loser = example("account-id")
    loser["accounts"][0]["period_start"] = "2150-01-01T00:00:00.000000Z"
    validate_ledger_manifest(loser)
    with pytest.raises(AssertionError):
        prove_collision(before, winner, loser, "account-id")


def conflict_example():
    before, first, winner, loser = example()
    proof = prove_collision(before, winner, loser, "scope-start")
    head = {"manifest_digest": validate_ledger_manifest(winner).digest}
    target = changed_parent(loser, head)
    state = {
        "head": head,
        "installation_key": target["installation_key"],
        "revision": "ar_0007_ledger",
        "status": "complete",
    }
    accounts = deepcopy(first["accounts"] + winner["accounts"])
    history = [{"manifest": first}, {"manifest": winner}]
    classification = {
        "raw_id": 101,
        "engine_id": 202,
        "state": deepcopy(state),
        "manifest": deepcopy(target),
        "manifest_digest": validate_ledger_manifest(target).digest,
        "history": deepcopy(history),
        "accounts": deepcopy(accounts),
        "refusal": {"type": "MigrationRefused", "code": "ledger_manifest_conflict"},
    }
    message = {
        "raw_id": 101,
        "engine_id": 202,
        "witness": {
            "classifications": [classification],
            "refusal": deepcopy(classification["refusal"]),
            "receipt": None,
        },
    }
    return message, target, state, accounts, history, proof["collisions"], loser


def test_changed_parent_is_new_canonical_request_preserving_unsuccessful_content():
    message, target, state, accounts, history, expected, previous = conflict_example()
    assert validate_ledger_manifest(previous).digest != validate_ledger_manifest(target).digest
    assert target["accounts"] == previous["accounts"]
    assert target["manifest_id"] == previous["manifest_id"]
    assert_conflict_context(message, target, state, accounts, history, expected)


@pytest.mark.parametrize(
    "change",
    [
        "stale-parent",
        "wrong-installation",
        "known-id",
        "missing-collision",
        "extra-collision",
        "wrong-raw",
        "wrong-engine",
        "different-head",
        "duplicate-classification",
        "missing-classification",
        "different-request",
        "wrong-code",
        "unexpected-receipt",
        "altered-financial-state",
    ],
)
def test_current_context_oracle_rejects_false_attribution(change):
    message, target, state, accounts, history, expected, previous = conflict_example()
    classification = message["witness"]["classifications"][0]
    if change in {"stale-parent", "wrong-installation", "known-id"}:
        if change == "stale-parent":
            target["parent_manifest_digest"] = previous["parent_manifest_digest"]
        elif change == "wrong-installation":
            target["installation_key"] = "other-installation"
        else:
            target["manifest_id"] = history[0]["manifest"]["manifest_id"]
        classification["manifest"] = deepcopy(target)
        classification["manifest_digest"] = validate_ledger_manifest(target).digest
    elif change == "missing-collision":
        accounts.pop()
        classification["accounts"] = deepcopy(accounts)
    elif change == "extra-collision":
        accounts[0]["id"] = target["accounts"][0]["id"]
        classification["accounts"] = deepcopy(accounts)
    elif change == "wrong-raw":
        classification["raw_id"] += 1
    elif change == "wrong-engine":
        classification["engine_id"] += 1
    elif change == "different-head":
        classification["state"]["head"]["manifest_digest"] = "e" * 64
    elif change == "duplicate-classification":
        message["witness"]["classifications"].append(deepcopy(classification))
    elif change == "missing-classification":
        message["witness"]["classifications"].clear()
    elif change == "different-request":
        classification["manifest"]["accounts"][0]["limit_microusd"] -= 1
    elif change == "wrong-code":
        classification["refusal"]["code"] = "migration_busy"
    elif change == "unexpected-receipt":
        message["witness"]["receipt"] = {"outcome": "complete"}
    else:
        assert change == "altered-financial-state"
        classification["accounts"][0]["limit_microusd"] -= 1
    with pytest.raises((AssertionError, ValueError)):
        assert_conflict_context(message, target, state, accounts, history, expected)


def physical_message():
    raw = 101
    events = [
        ["connect_return", "bootstrap", raw],
        ["sql", "bootstrap", raw, "BEGIN EXCLUSIVE"],
        ["sql", "ordinary", raw, "SELECT id FROM budget_accounts"],
        ["c_call", "ordinary", raw, "rollback"],
        ["sql", "ordinary", raw, "ROLLBACK"],
        ["c_return", "ordinary", raw, "rollback"],
        ["c_call", "harness-dispose", raw, "close"],
        ["c_return", "harness-dispose", raw, "close"],
    ]
    return {
        "raw_id": raw,
        "witness": {
            "observation": {
                "work": [{}],
                "faults": [],
                "native_trace": events,
                "native_authorizer": [(sqlite3.SQLITE_READ, "budget_accounts", "id", "main", None)],
                "outcomes": [
                    {
                        "begin_attempted": True,
                        "begun": True,
                        "rollback_attempted": True,
                        "rollback_acknowledged": True,
                        "commit_attempted": False,
                        "commit_acknowledged": False,
                        "cleanup_failed": False,
                    }
                ],
                "command_boundary": {
                    "raw_id": raw,
                    "connection_closed": True,
                    "checkedout": 0,
                    "lease_present": False,
                    "receipt_completed": True,
                    "receipt_clean": True,
                    "in_transaction": False,
                    "tainted": False,
                    "borrowed": False,
                    "trace_end": 6,
                },
                "markers": [
                    ["conflict.classify.enter", raw, 3],
                    ["conflict.classify.refused", raw, 3],
                    ["rollback.before_native", raw, 3],
                    ["rollback.native_ack", raw, 6],
                    ["command.exit", raw, 6],
                ],
            },
            "native_errors": [
                {
                    "type": "MigrationRefused",
                    "sqlite_errorcode": None,
                    "mapped_type": "MigrationRefused",
                    "mapped_code": "ledger_manifest_conflict",
                }
            ],
        },
    }


def test_conflict_cleanup_oracle_accepts_realistic_owned_rollback_and_separate_harness():
    assert_sqlite_conflict(physical_message())


@pytest.mark.parametrize(
    "change",
    [
        "write",
        "second-attempt",
        "wrong-raw",
        "commit",
        "rollback-error",
        "rollback-ack-missing",
        "cleanup-failed",
        "unreturned-checkout",
        "harness-before-service-exit",
        "wrong-marker-order",
        "duplicate-marker",
    ],
)
def test_conflict_cleanup_oracle_rejects_writes_retry_and_fabricated_outcome(change):
    message = physical_message()
    observed = message["witness"]["observation"]
    events = observed["native_trace"]
    if change == "write":
        observed["native_authorizer"].append(
            (sqlite3.SQLITE_INSERT, "budget_accounts", None, "main", None)
        )
    elif change == "second-attempt":
        events.append(["sql", "ordinary", 101, "BEGIN EXCLUSIVE"])
    elif change == "wrong-raw":
        events[3][2] += 1
    elif change == "commit":
        events.append(["c_call", "ordinary", 101, "commit"])
    elif change == "rollback-error":
        events[5][0] = "c_exception"
    elif change == "rollback-ack-missing":
        observed["outcomes"][0]["rollback_acknowledged"] = False
    elif change == "cleanup-failed":
        observed["outcomes"][0]["cleanup_failed"] = True
    elif change == "unreturned-checkout":
        observed["command_boundary"]["checkedout"] = 1
    elif change == "harness-before-service-exit":
        events[5][1] = "harness-dispose"
    elif change == "wrong-marker-order":
        observed["markers"][0], observed["markers"][1] = (
            observed["markers"][1],
            observed["markers"][0],
        )
    else:
        assert change == "duplicate-marker"
        observed["markers"].insert(0, observed["markers"][0])
    with pytest.raises(AssertionError):
        assert_sqlite_conflict(message)


def test_classifier_adapter_delegates_once_and_preserves_original_refusal(monkeypatch):
    raw, engine = object(), object()
    work = SimpleNamespace(_raw=raw, _connection=SimpleNamespace(engine=engine))
    marks, delegated, sent, caught = [], [], [], []
    watch = SimpleNamespace(
        work=work,
        engine=engine,
        owns=lambda candidate: candidate is raw,
        mark=lambda label, candidate: marks.append((label, candidate)),
    )
    _, _, _, target = example()
    manifest = validate_ledger_manifest(target)
    context = SimpleNamespace(
        state=SimpleNamespace(model_dump=lambda **kwargs: {"status": "complete"}),
        history=SimpleNamespace(manifests=[]),
        financial={"account": []},
    )
    original = MigrationRefused("ledger_manifest_conflict")

    @contextmanager
    def observe(*args, **kwargs):
        yield watch

    def classify(*args):
        delegated.append(args)
        raise original

    def fake_worker(channel):
        with adapter.worker.observe_command():
            try:
                adapter.ledger_service._classify_manifest(context, manifest, work)
            except MigrationRefused as error:
                caught.append(error)
        adapter.worker.send_frame(
            channel,
            {
                "role": "replay",
                "phase": "result",
                "raw_id": id(raw),
                "engine_id": id(engine),
                "witness": {},
            },
            42.0,
        )

    monkeypatch.setattr(adapter.worker, "observe_command", observe)
    monkeypatch.setattr(adapter.ledger_service, "_classify_manifest", classify)
    monkeypatch.setattr(adapter.worker, "run", fake_worker)
    monkeypatch.setattr(adapter.worker, "send_frame", lambda *args: sent.append(args))
    adapter.run("owned-channel")
    assert delegated == [(context, manifest, work)] and caught == [original]
    assert caught[0] is original
    assert marks == [("conflict.classify.enter", raw), ("conflict.classify.refused", raw)]
    assert len(sent) == 1 and sent[0][0] == "owned-channel" and sent[0][2] == 42.0
    (entry,) = sent[0][1]["witness"]["classifications"]
    assert entry["manifest_digest"] == manifest.digest
    assert entry["refusal"] == {"type": "MigrationRefused", "code": "ledger_manifest_conflict"}
    assert adapter.worker.observe_command is observe
    assert adapter.ledger_service._classify_manifest is classify
