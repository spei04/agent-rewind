"""One SQLite finite-account path; offline controls never execute this database node."""

import json
from copy import deepcopy
from types import SimpleNamespace

import ledger_eligibility_fixture as admission_helpers
import pytest
from ledger_account_identity_fixture import (
    assert_admission_delta,
    assert_second_refusal,
    assert_stores,
    expected_first,
    job_intents,
    same_job_site,
)
from ledger_accounted_carry_fixture import replace_rows
from ledger_accounted_carry_observer import assert_commit
from ledger_cohort_observer import observe_cohort
from ledger_eligibility_fixture import rows
from ledger_project_binding import observe_projects
from ledger_provisioning_fixture import (
    assert_no_writes,
    assert_stage,
    build_case,
    ciphertexts,
    expected_stage,
    initial_manifest,
    inspect,
    native_actions,
    snapshot,
    source_fingerprint,
    source_rows,
)
from ledger_recovery_fixture import observe_command
from ledger_restore_authority import typed
from test_ledger_accounted_carry_controls import receipt
from test_ledger_eligibility_controls import table

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.ledger_provisioning import _prepare_ledger
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import MigrationRefused


def test_first_finite_job_account_rejects_second_disjoint_account(
    tmp_path, monkeypatch, record_property
):
    def record(name, value):
        record_property(name, json.dumps(value, allow_nan=False))

    fixture = build_case(tmp_path / "identity.sqlite")
    try:
        record("original_predecessor", typed(fixture.before))
        first = initial_manifest(fixture)
        record("M0_manifest", first)
        with observe_command(fixture, monkeypatch, record_property, label="M0_service") as initial:
            first_receipt = ledger_service.initialize_ledger(
                initial.engine, validate_ledger_manifest(first)
            )
        assert_commit(initial)
        assert_stage(fixture, [first], [first_receipt])
        initialized = admission_helpers.refreshed(fixture)
        record("M0_receipt", first_receipt.model_dump(mode="json"))
        record("M0_state", typed(initialized.before))
        evolved, admission = admission_helpers.admit_existing_fixture(
            initialized, monkeypatch, lambda name, value: record("admission_" + name, value)
        )
        assert_admission_delta(initialized.before, evolved.before, admission, fixture.project)
        record("admission_association", typed(admission.association))
        record("admission_adapter", admission.adapter_scope)
        record("evolved_predecessor", typed(evolved.before))
        record("evolved_source", {"rows": typed(evolved.original), "fingerprint": evolved.source})
        record(
            "admission_stores",
            {
                "legacy": admission.original_legacy_ciphertexts,
                "objects": admission.ciphertexts,
                "journal": admission.journal_hashes,
            },
        )
        with native_actions(monkeypatch) as actions:
            prior = inspect(evolved).model_dump(mode="json")
        assert_no_writes(actions)
        _, _, first_state = expected_stage(fixture, [first], [first_receipt])
        assert typed(prior) == typed(first_state)
        assert typed(snapshot(fixture.case.path)) == typed(evolved.before)
        record("valid_evolved_inspection", prior)
        record("evolved_inspection_authorizer", actions)
        one, two = job_intents(evolved, first, admission.accepted["job_id"])
        record("M1_manifest", one)
        with (
            observe_command(evolved, monkeypatch, record_property, label="M1_service") as provision,
            observe_cohort(
                provision, monkeypatch, lambda name, value: record("M1_" + name, value)
            ) as (preparations, stages),
        ):
            written = ledger_service.initialize_ledger(
                provision.engine, validate_ledger_manifest(one)
            )
        assert_commit(provision)
        assert stages == ["prepare.enter", "prepare.return"] and len(preparations) == 1
        assert typed(preparations[0]["state"]) == typed(prior)
        expected, state = expected_first(
            fixture, first, first_receipt, evolved.before, one, written
        )
        after = snapshot(fixture.case.path)
        assert typed(after) == typed(expected)
        with native_actions(monkeypatch) as actions:
            observed = inspect(evolved).model_dump(mode="json")
        assert_no_writes(actions)
        assert typed(observed) == typed(state)
        assert typed(snapshot(fixture.case.path)) == typed(after)
        record("M1_receipt", written.model_dump(mode="json"))
        record("M1_expected", typed(expected))
        record("M1_state", typed(after))
        record("M1_whole_inspection", observed)
        record("M1_inspection_authorizer", actions)
        record("M2_manifest", two)
        with (
            observe_command(evolved, monkeypatch, record_property, label="M2_service") as refusal,
            observe_projects(refusal, monkeypatch, record) as gates,
            observe_cohort(refusal, monkeypatch, record) as (entries, stages),
            pytest.raises(MigrationRefused) as failure,
        ):
            ledger_service.initialize_ledger(refusal.engine, validate_ledger_manifest(two))
        assert_second_refusal(one, two, state, gates, entries, stages, failure.value, refusal)
        assert_no_writes(refusal.actions)
        refusal.assert_single_attempt()
        boundary = refusal.command_boundary
        assert boundary["raw_closed"] is False and boundary["in_transaction"] is False
        assert boundary["receipt_clean"] is True and boundary["checkedout"] == 0
        assert refusal.work._raw._ownership.closed is True  # Separate caller disposal.
        assert typed(snapshot(fixture.case.path)) == typed(after)
        original = source_rows(fixture.case.path)
        assert typed(original) == typed(evolved.original)
        assert source_fingerprint(original) == evolved.source
        assert_stores(evolved, admission, ciphertexts(fixture.case))
        assert len({id(watch.work) for watch in (initial, provision, refusal)}) == 3
        assert len({id(watch.work._raw) for watch in (initial, provision, refusal)}) == 3
        record(
            "final_preservation",
            {
                "state": typed(snapshot(fixture.case.path)),
                "source": typed(original),
                "source_fingerprint": evolved.source,
                "legacy": ciphertexts(fixture.case),
                "objects": admission.ciphertexts,
                "journal": admission.journal_hashes,
                "watched_services": 3,
                "receipt_replays": 0,
            },
        )
    finally:
        fixture.close()


def synthetic_identity():
    """Literal synthetic history; no database producer or service-success claim."""
    frozen = SimpleNamespace(
        case=SimpleNamespace(adoption={"installation_key": "synthetic-installation"}),
        organization="8" * 32,
        project="9" * 32,
        source="a" * 64,
        jobs=[{"id": "2" * 32, "budget": 1, "reserved": 0, "project_id": "9" * 32}],
    )
    first = initial_manifest(frozen)
    initial = receipt(first, 0)
    accounts, progress, prior = expected_stage(frozen, [first], [initial])
    before = {
        "schema": ("synthetic schema",),
        "tables": {
            "budget_accounts": table(accounts),
            "migration_progress": table(
                [
                    {
                        "revision": "ar_0007_ledger",
                        "phase": phase,
                        "source_digest": source,
                        "cursor": json.dumps(cursor, sort_keys=True, separators=(",", ":")),
                        "rows_verified": count,
                        "status": "complete",
                        "updated_at": initial.initialized_at,
                    }
                    for phase, (cursor, count, source) in progress.items()
                ]
            ),
            "jobs": table([{"id": "3" * 32, "budget": 1, "reserved": 0}]),
        },
    }
    evolved = SimpleNamespace(
        case=frozen.case,
        organization=frozen.organization,
        project=frozen.project,
        source="b" * 64,
        jobs=[
            *frozen.jobs,
            {"id": "3" * 32, "budget": 1, "reserved": 0, "project_id": frozen.project},
        ],
    )
    one, two = job_intents(evolved, first, "3" * 32)
    written = receipt(one, 1)
    return frozen, first, initial, before, one, two, written, prior


class TestAccountIdentityControls:
    def test_original_prepare_accepts_first_and_refuses_disjoint_second(self):
        frozen, first, initial, before, one, two, written, prior = synthetic_identity()
        current = SimpleNamespace(
            state=SimpleNamespace(manifest_count=1, account_count=3),
            history=SimpleNamespace(
                ownership=SimpleNamespace(organization_id=frozen.organization),
                manifests=(),
                opening=None,
                adoption={"installed_schema_fingerprint": "a" * 64},
            ),
            financial={
                "job": [{"id": "3" * 32, "budget": 1}],
                "scope": [
                    {"resource_kind": "job", "resource_id": "3" * 32, "project_id": frozen.project}
                ],
                "account": rows(before, "budget_accounts"),
            },
        )
        prepared = _prepare_ledger(current, validate_ledger_manifest(one), LedgerWork())
        assert prepared.exposure == {} and prepared.jobs == ()
        current.financial["account"].append(
            {
                **one["accounts"][0],
                "opening_held_microusd": 0,
                "held_microusd": 0,
                "accounted_microusd": 0,
            }
        )
        with pytest.raises(MigrationRefused) as failure:
            _prepare_ledger(current, validate_ledger_manifest(two), LedgerWork())
        assert failure.value.code == "ledger_manifest_conflict"
        traceback = failure.value.__traceback__
        while traceback.tb_next is not None:
            traceback = traceback.tb_next
        assert traceback.tb_frame.f_code is _prepare_ledger.__code__
        assert traceback.tb_lineno == same_job_site()
        assert one["accounts"][0]["period_end"] == two["accounts"][0]["period_start"]

    def test_first_delta_has_zero_balances_and_immutable_opening(self):
        frozen, first, initial, before, one, _, written, _ = synthetic_identity()
        expected, state = expected_first(frozen, first, initial, before, one, written)
        (added,) = [row for row in rows(expected, "budget_accounts") if row["job_id"] == "3" * 32]
        assert added == {
            "id": f"{8001:032x}",
            "organization_id": "8" * 32,
            "scope": "job",
            "scope_id": "3" * 32,
            "project_id": "9" * 32,
            "job_id": "3" * 32,
            "period_start": "2000-01-01T00:00:00.000000Z",
            "period_end": "2100-01-01T00:00:00.000000Z",
            "limit_microusd": 1,
            "opening_held_microusd": 0,
            "held_microusd": 0,
            "accounted_microusd": 0,
        }
        assert state["account_count"] == 4 and state["manifest_count"] == 2
        assert typed(expected["tables"]["jobs"]) == typed(before["tables"]["jobs"])
        assert state["opening"]["jobs"][0]["job_id"] == "2" * 32

    @pytest.mark.parametrize(
        "field,value",
        [
            ("limit_microusd", True),
            ("held_microusd", 0.0),
            ("period_end", "2300-01-01T00:00:00.000000Z"),
            ("id", "f" * 32),
        ],
    )
    def test_first_delta_rejects_mutated_old_account(self, field, value):
        frozen, first, initial, before, one, _, written, _ = synthetic_identity()
        accounts = rows(before, "budget_accounts")
        accounts[0][field] = value
        replace_rows(before, "budget_accounts", accounts)
        with pytest.raises(AssertionError):
            expected_first(frozen, first, initial, before, one, written)

    def test_first_delta_rejects_changed_opening_cursor(self):
        frozen, first, initial, before, one, _, written, _ = synthetic_identity()
        progress = rows(before, "migration_progress")
        opening = next(row for row in progress if row["phase"] == "ledger_opening")
        cursor = json.loads(opening["cursor"])
        cursor["jobs"][0]["legacy_reserved_microusd"] = True
        opening["cursor"] = json.dumps(cursor, sort_keys=True, separators=(",", ":"))
        replace_rows(before, "migration_progress", progress)
        with pytest.raises(AssertionError):
            expected_first(frozen, first, initial, before, one, written)

    def test_existing_fixture_failure_does_not_close_caller(self, monkeypatch):
        closed = []
        fixture = SimpleNamespace(close=lambda: closed.append(True))
        failure = RuntimeError("synthetic admission engine failure")

        def unavailable(_fixture):
            raise failure

        monkeypatch.setattr(admission_helpers, "admission_engine", unavailable)
        with pytest.raises(RuntimeError) as observed:
            admission_helpers.admit_existing_fixture(fixture, monkeypatch, lambda *_: None)
        assert observed.value is failure and closed == []

    def test_builder_wrapper_preserves_failure_cleanup(self, monkeypatch):
        closed = []
        fixture = SimpleNamespace(close=lambda: closed.append(True))
        failure = RuntimeError("synthetic publication failure")
        monkeypatch.setattr(admission_helpers, "build_case", lambda _: fixture)

        def unavailable(*_args):
            raise failure

        monkeypatch.setattr(admission_helpers, "admit_existing_fixture", unavailable)
        with pytest.raises(RuntimeError) as observed:
            admission_helpers.admitted_predecessor(None, monkeypatch, lambda *_: None)
        assert observed.value is failure and closed == [True]


def synthetic_admission():
    """Independent publication rows, including both nonfinancial admission objects."""
    from test_ledger_eligibility_controls import association, example

    fixture, accepted, principal, config, _ = example()
    after = fixture.before
    jobs = rows(after, "jobs")
    for job in jobs:
        job.update(legacy_reserved_microusd=job["reserved"], lease_generation=0)
    after["tables"]["jobs"] = table(jobs)
    operations = rows(after, "operations")
    operations[0]["request_digest"] = "d" * 64
    after["tables"]["operations"] = table(operations)
    references = rows(after, "artifact_refs")
    objects = rows(after, "artifact_objects")
    for i, role in enumerate(("task", "payload"), 41):
        references.append({**references[0], "role": role, "artifact_id": f"{i:032x}"})
        objects.append({**objects[0], "id": f"{i:032x}", "digest": str(i % 10) * 64})
    after["tables"]["artifact_refs"] = table(references)
    after["tables"]["artifact_objects"] = table(objects)
    after["tables"]["operation_keys"] = table(
        [
            {
                "project_id": fixture.project,
                "principal_id": principal,
                "kind": "run",
                "key_hash": "7" * 64,
                "operation_id": accepted["operation_id"],
                "request_digest": "d" * 64,
            }
        ]
    )
    after["tables"]["audit"] = table(
        [
            {
                "id": "a" * 32,
                "created": 1700000001.0,
                "actor": principal,
                "action": "job.create",
                "target": accepted["job_id"],
            }
        ]
    )
    after["tables"]["budget_accounts"] = table(
        [
            {
                "id": "b" * 32,
                "job_id": jobs[0]["id"],
                "held_microusd": 13,
            }
        ]
    )
    after["tables"]["migration_progress"] = table(
        [{"phase": "immutable M0 opening", "cursor": "x"}]
    )
    before = deepcopy(after)
    for name in ("operations", "operation_keys", "artifact_refs", "artifact_objects", "audit"):
        before["tables"][name]["rows"] = []
    replace_rows(before, "jobs", jobs[:1])
    replace_rows(before, "resource_scopes", rows(before, "resource_scopes")[:1])
    admission = SimpleNamespace(
        accepted=accepted,
        association=deepcopy(association(fixture, accepted, principal, config)),
    )
    return before, after, admission, fixture.project


def synthetic_refusal(monkeypatch):
    from agent_rewind.migrations.ledger_state import LedgerState

    frozen, first, initial, before, one, two, written, _ = synthetic_identity()
    _, prior = expected_first(frozen, first, initial, before, one, written)
    raw, engine = object(), object()
    work = LedgerWork()
    work._raw, work._connection = raw, SimpleNamespace(engine=engine)
    watch = SimpleNamespace(
        work=work,
        engine=engine,
        trace=SimpleNamespace(raws=[raw], events=["start", "projects"]),
        markers=[("rollback.before_native", id(raw), 3)],
        outcome=SimpleNamespace(
            confirmed_precommit_rollback=True,
            rollback_acknowledged=True,
            commit_attempted=False,
            cleanup_failed=False,
        ),
    )
    context = SimpleNamespace(
        state=LedgerState.model_validate(prior),
        history=SimpleNamespace(ownership=SimpleNamespace(organization_id=frozen.organization)),
        financial={
            "job": [{"id": "3" * 32, "budget": 1}],
            "scope": [
                {"resource_kind": "job", "resource_id": "3" * 32, "project_id": frozen.project}
            ],
            "account": rows(before, "budget_accounts")
            + [
                {
                    **one["accounts"][0],
                    "opening_held_microusd": 0,
                    "held_microusd": 0,
                    "accounted_microusd": 0,
                }
            ],
        },
    )
    with (
        observe_cohort(watch, monkeypatch, lambda *_: None) as (entries, stages),
        pytest.raises(MigrationRefused) as failure,
    ):
        ledger_service._prepare_ledger(context, validate_ledger_manifest(two), work)
    gates = [
        {
            "raw_id": id(raw),
            "work_id": id(work),
            "engine_id": id(engine),
            "connection_id": id(work._connection),
            "organization": frozen.organization,
            "manifest": deepcopy(two),
            "trace_position": 0,
            "return_trace_position": 1,
            "returned": True,
        }
    ]
    return one, two, prior, gates, entries, stages, failure.value, watch


class TestAccountIdentityWitnessControls:
    def test_complete_admission_append_only_and_default_zero_fields(self):
        before, after, admission, project = synthetic_admission()
        result = assert_admission_delta(before, after, admission, project)
        assert len(result["artifact_objects"]) == len(result["artifact_refs"]) == 3
        assert result["budget_accounts"] == result["migration_progress"] == []

    @pytest.mark.parametrize(
        "change",
        [
            "generation-float",
            "legacy-bool",
            "old-money",
            "old-opening",
            "extra-job",
            "wrong-project",
            "missing-payload",
            "changed-alias",
            "changed-audit",
        ],
    )
    def test_admission_rejects_invalid_producer_or_changed_history(self, change):
        before, after, admission, project = synthetic_admission()
        table_name, field, value = {
            "generation-float": ("jobs", "lease_generation", 0.0),
            "legacy-bool": ("jobs", "legacy_reserved_microusd", False),
            "old-money": ("budget_accounts", "held_microusd", 12),
            "old-opening": ("migration_progress", "cursor", "changed"),
            "wrong-project": ("resource_scopes", "project_id", "f" * 32),
            "changed-alias": ("operation_keys", "operation_id", "f" * 32),
            "changed-audit": ("audit", "target", "f" * 32),
        }.get(change, (None, None, None))
        if table_name:
            values = rows(after, table_name)
            values[-1][field] = value
            replace_rows(after, table_name, values)
        elif change == "extra-job":
            values = rows(after, "jobs")
            values.append({**values[-1], "id": "f" * 32})
            replace_rows(after, "jobs", values)
        else:
            replace_rows(
                after,
                "artifact_refs",
                [row for row in rows(after, "artifact_refs") if row["role"] != "payload"],
            )
        with pytest.raises(AssertionError):
            assert_admission_delta(before, after, admission, project)

    def test_original_conflict_witness_and_live_exception(self, monkeypatch):
        assert_second_refusal(*synthetic_refusal(monkeypatch))

    @pytest.mark.parametrize(
        "change",
        [
            "raw",
            "line-type",
            "project-return",
            "previous-held",
            "wrong-parent",
            "exception",
        ],
    )
    def test_conflict_oracle_rejects_misattribution(self, monkeypatch, change):
        values = list(synthetic_refusal(monkeypatch))
        if change == "raw":
            values[4][0]["raw_id"] += 1
        elif change == "line-type":
            values[4][0]["traceback"]["preparation_frames"][0]["line"] = float(same_job_site())
        elif change == "project-return":
            values[3][0]["returned"] = False
        elif change == "previous-held":
            values[4][0]["traceback"]["preparation_frames"][0]["current"][-1]["held_microusd"] = 1
        elif change == "wrong-parent":
            values[1] = deepcopy(values[1])
            values[1]["parent_manifest_digest"] = "f" * 64
        else:
            values[6] = MigrationRefused("ledger_manifest_conflict")
        with pytest.raises((AssertionError, ValueError)):
            assert_second_refusal(*values)
