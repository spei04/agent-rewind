"""Three SQLite window refusals; source validation collects these database nodes only."""

import json
from contextlib import nullcontext

import ledger_eligibility_fixture as admission_helpers
import pytest
from ledger_account_identity_fixture import assert_admission_delta, assert_stores
from ledger_account_window_fixture import (
    CASES,
    assert_expiry_source,
    assert_intent,
    assert_preservation,
    assert_refusal,
    equal,
    initial_window,
    window_intent,
)
from ledger_account_window_observer import identity, observe_window, observe_window_source
from ledger_account_window_sqlite import assert_pooled_rollback, assert_target_actions
from ledger_accounted_carry_observer import assert_commit
from ledger_cohort_observer import observe_cohort
from ledger_eligibility_fixture import file_hashes, rows
from ledger_project_binding import observe_projects
from ledger_provisioning_fixture import (
    assert_no_writes,
    assert_stage,
    build_case,
    ciphertexts,
    expected_stage,
    inspect,
    native_actions,
    snapshot,
    source_fingerprint,
    source_rows,
)
from ledger_recovery_fixture import observe_command
from ledger_restore_authority import typed

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused


@pytest.mark.parametrize("case", CASES)
def test_sqlite_account_window_refusal(tmp_path, monkeypatch, record_property, case):
    def record(name, value):
        record_property(name, json.dumps(value, allow_nan=False))

    record("window_case", case)
    fixture = build_case(tmp_path / "window.sqlite")
    try:
        record("original_predecessor", typed(fixture.before))
        first, legacy = initial_window(fixture, case)
        record("M0_manifest", first)
        with observe_command(fixture, monkeypatch, record_property, label="M0_service") as initial:
            receipt = ledger_service.initialize_ledger(
                initial.engine, validate_ledger_manifest(first)
            )
        assert_commit(initial)
        equal(initial.work.timeout_seconds, 5)
        assert_stage(fixture, [first], [receipt])
        initialized = admission_helpers.refreshed(fixture)
        accounts, progress, expected = expected_stage(fixture, [first], [receipt])
        record(
            "M0_stage",
            {
                "expected_accounts": accounts,
                "expected_progress": progress,
                "observed_progress": typed(rows(initialized.before, "migration_progress")),
                "expected_inspection": expected,
            },
        )
        record("M0_receipt", receipt.model_dump(mode="json"))
        record("M0_state", typed(initialized.before))
        setup = []
        evolved, admission = admission_helpers.admit_existing_fixture(
            initialized,
            monkeypatch,
            lambda name, value: setup.append({"name": name, "value": value}),
        )
        assert_admission_delta(initialized.before, evolved.before, admission, fixture.project)
        assert len(evolved.before["tables"]) == 20
        assert len(admission.original_legacy_ciphertexts) == 18
        assert len(admission.ciphertexts) == 3 and len(admission.journal_hashes) == 15
        record("admission_setup", setup)
        record("admission_association", typed(admission.association))
        record("admission_adapter_scope", admission.adapter_scope)
        record("evolved_predecessor", typed(evolved.before))
        record("evolved_source", {"rows": typed(evolved.original), "fingerprint": evolved.source})
        stores = {
            "legacy": admission.original_legacy_ciphertexts,
            "objects": admission.ciphertexts,
            "journal": admission.journal_hashes,
        }
        record("admission_stores", stores)
        with native_actions(monkeypatch) as actions:
            prior = inspect(evolved).model_dump(mode="json")
        assert_no_writes(actions)
        equal(prior, expected)
        equal(snapshot(fixture.case.path), evolved.before)
        record("valid_evolved_inspection", {"state": prior, "authorizer": actions})
        requested = window_intent(evolved, first, case, admission.accepted["job_id"], legacy)
        target = (
            None
            if case == CASES[0]
            else legacy
            if case == CASES[1]
            else admission.accepted["job_id"]
        )
        assert_intent(first, requested, evolved.before, case, target, receipt.initialized_at)
        record("target_manifest", requested)
        before_progress = evolved.before["tables"]["migration_progress"]
        with (
            observe_command(evolved, monkeypatch, record_property, label="target_service") as watch,
            observe_projects(watch, monkeypatch, record) as projects,
            observe_cohort(watch, monkeypatch, record) as (entries, phases),
            observe_window(watch, monkeypatch, record, backend="sqlite") as observations,
            (
                observe_window_source(watch, monkeypatch, observations, backend="sqlite")
                if case == CASES[2]
                else nullcontext()
            ),
            pytest.raises(MigrationRefused) as refusal,
        ):
            ledger_service.initialize_ledger(watch.engine, validate_ledger_manifest(requested))
        assert_refusal(
            first,
            requested,
            prior,
            observations,
            projects,
            entries,
            phases,
            refusal.value,
            watch,
            case,
            backend="sqlite",
        )
        assert_pooled_rollback(watch)
        assert_target_actions(watch.actions, inserted=case == CASES[2])
        if case == CASES[2]:
            equal(observations["source_hashes"][0]["preparation"][0]["state"], prior)
            assert_expiry_source(
                observations,
                evolved.original,
                requested,
                watch.trace.events,
                None,
                identity(watch),
                backend="sqlite",
            )
        assert initial.work is not watch.work and initial.work._raw is not watch.work._raw
        after = snapshot(fixture.case.path)
        source = source_rows(fixture.case.path)
        after_progress = after["tables"]["migration_progress"]
        equal(before_progress, after_progress)
        assert_stores(evolved, admission, ciphertexts(fixture.case))
        after_stores = {
            "legacy": ciphertexts(fixture.case),
            "objects": file_hashes(admission.objects),
            "journal": file_hashes(admission.journal),
        }
        assert_preservation(evolved.before, after, evolved.original, source, stores, after_stores)
        assert source_fingerprint(source) == requested["source_digest"] == evolved.source
        record(
            "raw_progress_preservation",
            {"before": typed(before_progress), "after": typed(after_progress)},
        )
        record(
            "target_refusal",
            {
                "case": case,
                "code": refusal.value.code,
                "post_insert_rollback": case == CASES[2],
                "watched_services": 2,
                "receipt_replays": 0,
            },
        )
        record(
            "final_preservation",
            {
                "state": typed(after),
                "source": typed(source),
                "source_fingerprint": evolved.source,
                **after_stores,
            },
        )
    finally:
        fixture.close()
