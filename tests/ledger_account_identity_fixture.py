"""Finite first job accounts and unchanged-current-state second-account refusals."""

import ast
import inspect
from copy import deepcopy

from ledger_accounted_carry_fixture import replace_rows
from ledger_eligibility_fixture import file_hashes, rows
from ledger_provisioning_fixture import (
    END,
    ROLLOVER,
    START,
    canonical,
    digest,
    expected_stage,
    identity,
)
from ledger_restore_authority import typed

from agent_rewind.migrations import ledger_provisioning
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import LEDGER, MigrationRefused


def job_intents(fixture, first, job_id):
    """Use new identities and disjoint periods to exclude classifier/overlap refusals."""
    (job,) = [row for row in fixture.jobs if row["id"] == job_id]
    account = {
        "id": identity(8001),
        "organization_id": fixture.organization,
        "scope": "job",
        "scope_id": job_id,
        "project_id": fixture.project,
        "job_id": job_id,
        "period_start": START,
        "period_end": ROLLOVER,
        "limit_microusd": job["budget"],
    }
    one = {
        **deepcopy(first),
        "manifest_id": identity(8101),
        "operation": "provision",
        "parent_manifest_digest": digest(first),
        "source_digest": fixture.source,
        "opening_accounts": None,
        "accounts": [account],
    }
    two = {
        **deepcopy(one),
        "manifest_id": identity(8102),
        "parent_manifest_digest": digest(one),
        "accounts": [
            {**account, "id": identity(8002), "period_start": ROLLOVER, "period_end": END}
        ],
    }
    for manifest in (one, two):
        validate_ledger_manifest(manifest)
    return one, two


def assert_admission_delta(before, after, admission, project):
    """Only real publication additions may evolve the already-initialized state."""
    assert set(before) == set(after)
    for name in set(before) - {"tables"}:
        assert typed(before[name]) == typed(after[name]), name
    assert set(before["tables"]) == set(after["tables"])
    counts = {
        "jobs": 1,
        "operations": 1,
        "operation_keys": 1,
        "resource_scopes": 1,
        "artifact_objects": 3,
        "artifact_refs": 3,
        "audit": 1,
    }
    added = {}
    for name, old in before["tables"].items():
        new = after["tables"][name]
        assert typed(old["columns"]) == typed(new["columns"])
        remaining = list(new["rows"])
        for row in old["rows"]:
            matches = [i for i, value in enumerate(remaining) if typed(value) == typed(row)]
            assert len(matches) == 1, name
            remaining.pop(matches[0])
        assert len(remaining) == counts.get(name, 0), name
        added[name] = [dict(zip(new["columns"], row, strict=True)) for row in remaining]
    (job,) = added["jobs"]
    assert job["id"] == admission.accepted["job_id"]
    assert job["status"] == "queued" and job["owner"] is job["lease_until"] is None
    for key, value in {
        "payload_version": 2,
        "reserved": 0,
        "legacy_reserved_microusd": 0,
        "lease_generation": 0,
    }.items():
        assert typed(job[key]) == typed(value), key
    assert type(job["budget"]) is int and job["budget"] > 0
    (operation,) = added["operations"]
    assert operation["id"] == admission.accepted["operation_id"]
    assert operation["job_id"] == job["id"] and operation["project_id"] == project
    assert operation["principal_id"] == job["actor"]
    assert typed(admission.association["job"]) == typed(job)
    assert typed(admission.association["operation"]) == typed(operation)
    assert added["resource_scopes"] == [
        {"resource_kind": "job", "resource_id": job["id"], "project_id": project}
    ]
    references, objects = added["artifact_refs"], added["artifact_objects"]
    assert {row["role"] for row in references} == {"task", "payload", "admission_config"}
    assert {row["artifact_id"] for row in references} == {row["id"] for row in objects}
    assert len({row["id"] for row in objects}) == 3
    for reference in references:
        assert reference["owner_kind"] == "job" and reference["owner_id"] == job["id"]
        assert reference["project_id"] == project
    assert all(row["project_id"] == project for row in objects)
    (config,) = [row for row in references if row["role"] == "admission_config"]
    (descriptor,) = [row for row in objects if row["id"] == config["artifact_id"]]
    assert typed(admission.association["reference"]) == typed(config)
    assert typed(admission.association["descriptor"]) == typed(descriptor)
    assert descriptor["digest"] == job["execution_config_ref"] == job["execution_config_digest"]
    (alias,) = added["operation_keys"]
    assert alias["operation_id"] == operation["id"] and alias["project_id"] == project
    assert alias["principal_id"] == job["actor"] and alias["kind"] == "run"
    assert alias["key_hash"] == "7" * 64 and alias["request_digest"] == operation["request_digest"]
    (audit,) = added["audit"]
    assert (audit["action"], audit["target"], audit["actor"]) == (
        "job.create",
        job["id"],
        job["actor"],
    )
    assert not any(row["job_id"] == job["id"] for row in rows(after, "budget_accounts"))
    return added


def assert_stores(fixture, admission, legacy):
    assert legacy == fixture.encrypted == admission.original_legacy_ciphertexts
    assert file_hashes(admission.objects) == admission.ciphertexts
    assert file_hashes(admission.journal) == admission.journal_hashes


def expected_first(frozen, first, initial, predecessor, one, written, *, role=None):
    """Original M0 input alone supplies the immutable opening, never the new job."""
    accounts, progress, state = expected_stage(
        frozen, [first, one], [initial, written], database_role=role
    )
    old_ids = {row["id"] for row in first["accounts"]}
    for value in (initial, written):
        for key in ("sequence", "account_rows", "imported_jobs", "imported_opening_microusd"):
            assert type(getattr(value, key)) is int
    assert typed(sorted(rows(predecessor, "budget_accounts"), key=lambda row: row["id"])) == typed(
        sorted([row for row in accounts if row["id"] in old_ids], key=lambda row: row["id"])
    )
    expected = deepcopy(predecessor)
    replace_rows(expected, "budget_accounts", accounts)
    previous = rows(predecessor, "migration_progress")
    phase = "ledger_manifest_" + one["manifest_id"]
    assert not any(row["phase"] == phase for row in previous)
    cursor, count, source = progress[phase]
    for row in previous:
        if row["revision"] == LEDGER:
            old_cursor, old_count, old_source = progress[row["phase"]]
            assert typed(row) == typed(
                progress_row(row["phase"], old_cursor, old_count, old_source)
            )
    replace_rows(
        expected, "migration_progress", previous + [progress_row(phase, cursor, count, source)]
    )
    (account,) = one["accounts"]
    assert written.initialized_at < account["period_end"]
    return expected, state


def progress_row(phase, cursor, count, source):
    return {
        "revision": LEDGER,
        "phase": phase,
        "source_digest": source,
        "cursor": canonical(cursor).decode(),
        "rows_verified": count,
        "status": "complete",
        "updated_at": cursor["initialized_at"],
    }


def same_job_site():
    source, first = inspect.getsourcelines(ledger_provisioning._prepare_ledger)
    (condition,) = [
        node
        for node in ast.walk(ast.parse("".join(source)))
        if isinstance(node, ast.If)
        and ast.unparse(node.test)
        == "account.job_id is not None and row['job_id'] == account.job_id"
    ]
    (raise_node,) = condition.body
    assert ast.unparse(raise_node.exc) == "MigrationRefused('ledger_manifest_conflict')"
    return first + raise_node.lineno - 1


def assert_second_refusal(one, two, prior_state, gates, entries, stages, error, watch):
    """The original prepare traceback distinguishes this from other conflict gates."""
    assert type(error) is MigrationRefused and error.code == "ledger_manifest_conflict"
    (entry,), (gate,) = entries, gates
    assert stages == ["prepare.enter", "prepare.refused"] and "returned" not in entry
    assert typed(entry["error"]) == typed(
        {"type": "MigrationRefused", "code": "ledger_manifest_conflict", "identity": id(error)}
    )
    assert typed(entry["state"]) == typed(prior_state)
    assert typed(entry["manifest"]) == typed(two)
    assert gate["returned"] is True and "error" not in gate
    assert typed(gate["manifest"]) == typed(two)
    for key, value in {
        "raw_id": id(watch.work._raw),
        "work_id": id(watch.work),
        "engine_id": id(watch.engine),
    }.items():
        assert typed(entry[key]) == typed(value) == typed(gate[key])
    assert typed(gate["connection_id"]) == typed(id(watch.work._connection))
    assert gate["trace_position"] < gate["return_trace_position"] <= entry["trace_position"]
    assert gate["organization"] == entry["organization"] == two["accounts"][0]["organization_id"]
    (requested,), (original,) = two["accounts"], one["accounts"]
    assert two["parent_manifest_digest"] == digest(one)
    assert two["source_digest"] == one["source_digest"]
    assert two["manifest_id"] != one["manifest_id"]
    assert requested == {
        **original,
        "id": requested["id"],
        "period_start": original["period_end"],
        "period_end": END,
    }
    assert requested["id"] != original["id"] and requested["period_start"] < END
    (rejected,) = entry["traceback"]["preparation_frames"]
    assert type(rejected["line"]) is int and rejected["line"] == same_job_site()
    # Check the live exception's original frame too, not just a serialized numeric identity.
    frames = []
    traceback = error.__traceback__
    while traceback is not None:
        if traceback.tb_frame.f_code is ledger_provisioning._prepare_ledger.__code__:
            frames.append(traceback)
        traceback = traceback.tb_next
    (frame,) = frames
    assert frame.tb_lineno == same_job_site() and frame.tb_frame.f_locals["work"] is watch.work
    assert typed(rejected["account"]) == typed(requested)
    assert typed(rejected["current"]) == typed(entry["financial"]["account"])
    (old,) = [row for row in rejected["current"] if row["job_id"] == requested["job_id"]]
    assert typed(old) == typed(
        {**original, "opening_held_microusd": 0, "held_microusd": 0, "accounted_microusd": 0}
    )
    assert requested["id"] not in {row["id"] for row in rejected["current"]}
    assert rejected["job"]["id"] == requested["job_id"]
    assert rejected["scopes"][requested["job_id"]] == requested["project_id"]
    assert typed(rejected["job"]) == typed(rejected["jobs"][requested["job_id"]])
    assert rejected["assignments"] is None
    assert entry["refusal_trace_position"] <= watch.markers[0][2]
    assert watch.outcome.confirmed_precommit_rollback and watch.outcome.rollback_acknowledged
    assert not watch.outcome.commit_attempted and not watch.outcome.cleanup_failed
