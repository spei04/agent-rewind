"""Database-free controls for exact cohort deltas and delegated refusal attribution."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from ledger_cohort_fixture import CASES, assert_cohort_change, cohort_change
from ledger_cohort_observer import assert_cohort_refusal, cohort_sites, observe_cohort
from ledger_eligibility_fixture import rows
from ledger_eligibility_observer import assert_preparation
from ledger_provisioning_fixture import identity
from test_ledger_eligibility_controls import example

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused


def scenario(case):
    fixture, accepted, _, _, _ = example()
    baseline, manifest, target = cohort_change(fixture, accepted["job_id"], case)
    raw, engine = object(), object()
    work = SimpleNamespace(_raw=raw, _connection=SimpleNamespace(engine=engine), check=lambda: None)
    watch = SimpleNamespace(
        work=work,
        engine=engine,
        trace=SimpleNamespace(raws=[raw], events=[]),
        outcome=SimpleNamespace(
            confirmed_precommit_rollback=True, commit_attempted=False, cleanup_failed=False
        ),
        markers=[
            (name, id(raw), 0)
            for name in (
                "rollback.before_native",
                "rollback.native_ack",
                "connection.close.before",
                "connection.close.return",
                "command.exit",
            )
        ],
    )
    context = SimpleNamespace(
        state=SimpleNamespace(
            manifest_count=0,
            account_count=0,
            model_dump=lambda **kwargs: {
                "status": "absent",
                "head": None,
                "revision": "ar_0006_admission",
            },
        ),
        history=SimpleNamespace(ownership=SimpleNamespace(organization_id=fixture.organization)),
        financial={
            "job": rows(fixture.before, "jobs"),
            "scope": rows(fixture.before, "resource_scopes"),
            "account": [],
        },
    )
    return fixture, accepted, baseline, manifest, target, watch, context


def delegated(case, monkeypatch, *, earlier=None):
    fixture, accepted, baseline, manifest, target, watch, context = scenario(case)
    if earlier == "organization":
        context.history.ownership.organization_id = identity(99)
    elif earlier == "limit":
        context.state.account_count = 4096
    recorded = []
    with (
        observe_cohort(watch, monkeypatch, lambda *value: recorded.append(value)) as observed,
        pytest.raises(MigrationRefused) as failure,
    ):
        ledger_service._prepare_ledger(context, validate_ledger_manifest(manifest), watch.work)
    (entry,), stages = observed
    assert len(recorded) == 1
    return fixture, accepted, baseline, manifest, target, watch, entry, stages, failure.value


@pytest.mark.parametrize("case", CASES)
def test_manifest_changes_only_one_account_and_preserves_openings_and_valid_source(case):
    fixture, accepted, baseline, manifest, target, _, _ = scenario(case)
    before = deepcopy(fixture.before)
    complete = {row["job_id"] for row in baseline["accounts"] if row["scope"] == "job"}
    changed = {row["job_id"] for row in manifest["accounts"] if row["scope"] == "job"}
    assert before == fixture.before
    assert baseline["opening_accounts"] == manifest["opening_accounts"]
    assert baseline["source_digest"] == manifest["source_digest"] == fixture.source
    assert [row for row in baseline["accounts"] if row["scope"] != "job"] == [
        row for row in manifest["accounts"] if row["scope"] != "job"
    ]
    if case == "nonexistent-job":
        assert changed == complete | {target} and target not in complete
    else:
        assert changed == complete - {target}
    if case == "omit-admitted-zero":
        assert target == accepted["job_id"]
        # The omitted zero job changes membership without changing money totals.
        assert sum(row["reserved"] for row in fixture.jobs) == sum(
            row["reserved"] for row in fixture.jobs if row["id"] != target
        )


@pytest.mark.parametrize(
    "change",
    [
        "cap",
        "fingerprint",
        "opening",
        "other-job",
        "second-omission",
        "wrong-project",
        "duplicate-id",
        "scope-id",
        "wrong-target",
    ],
)
def test_manifest_delta_oracle_rejects_collateral_changes(change):
    case = (
        "nonexistent-job"
        if change in {"wrong-project", "duplicate-id", "scope-id"}
        else "omit-admitted-zero"
    )
    fixture, accepted, baseline, manifest, target, _, _ = scenario(case)
    if change == "cap":
        manifest["accounts"][0]["limit_microusd"] += 1
    elif change == "fingerprint":
        manifest["source_digest"] = "0" * 64
    elif change == "opening":
        manifest["opening_accounts"]["organization_account_id"] = identity(99)
    elif change == "other-job":
        manifest["accounts"][-1]["limit_microusd"] -= 1
    elif change == "second-omission":
        manifest["accounts"] = [row for row in manifest["accounts"] if row["scope"] != "job"]
    elif change == "wrong-project":
        manifest["accounts"][-1]["project_id"] = identity(99)
    elif change == "duplicate-id":
        manifest["accounts"][-1]["id"] = manifest["accounts"][-2]["id"]
    elif change == "scope-id":
        manifest["accounts"][-1]["scope_id"] = identity(99)
    else:
        target = identity(99)
    with pytest.raises((AssertionError, MigrationRefused)):
        assert_cohort_change(fixture, baseline, manifest, case, target, accepted["job_id"])


@pytest.mark.parametrize("case", CASES)
def test_real_pure_preparation_refuses_exact_branch_and_original_exception(case, monkeypatch):
    fixture, _, _, manifest, target, watch, entry, stages, error = delegated(case, monkeypatch)
    assert_preparation(entry, fixture, manifest, watch)
    assert_cohort_refusal(entry, stages, error, watch, case=case, target_job=target)
    assert (
        entry["traceback"]["frames"][-1]["line"]
        == (cohort_sites()[1]["missing-job" if case == "nonexistent-job" else "cohort"])
    )


@pytest.mark.parametrize("earlier", ["organization", "limit"])
def test_actual_earlier_preparation_refusal_cannot_count_as_cohort(earlier, monkeypatch):
    *_, target, watch, entry, stages, error = delegated(
        "omit-admitted-zero", monkeypatch, earlier=earlier
    )
    with pytest.raises(AssertionError):
        assert_cohort_refusal(
            entry, stages, error, watch, case="omit-admitted-zero", target_job=target
        )


@pytest.mark.parametrize(
    "change",
    [
        "line",
        "jobs",
        "scopes",
        "assignments",
        "current",
        "account",
        "exception",
        "returned",
        "commit",
        "rollback",
        "order",
        "position",
        "duplicate-frame",
        "wrong-target",
    ],
)
def test_cohort_oracle_rejects_wrong_stage_identity_state_and_cleanup(change, monkeypatch):
    *_, target, watch, entry, stages, error = delegated("omit-admitted-zero", monkeypatch)
    rejected = entry["traceback"]["preparation_frames"][0]
    if change == "line":
        rejected["line"] = 161
    elif change in {"jobs", "scopes", "assignments"}:
        rejected[change] = {}
    elif change == "current":
        rejected["current"] = [{"id": identity(99)}]
    elif change == "account":
        rejected["account"] = entry["manifest"]["accounts"][0]
    elif change == "exception":
        error = MigrationRefused("ledger_history_unsupported")
    elif change == "returned":
        entry["returned"] = True
    elif change == "commit":
        watch.outcome.commit_attempted = True
    elif change == "rollback":
        watch.outcome.confirmed_precommit_rollback = False
    elif change == "order":
        watch.markers[1], watch.markers[2] = watch.markers[2], watch.markers[1]
    elif change == "position":
        entry["refusal_trace_position"] = 1
    elif change == "duplicate-frame":
        entry["traceback"]["preparation_frames"].append(deepcopy(rejected))
    else:
        target = identity(99)
    with pytest.raises((AssertionError, ValueError)):
        assert_cohort_refusal(
            entry, stages, error, watch, case="omit-admitted-zero", target_job=target
        )


@pytest.mark.parametrize("change", ["present-job", "scope-present", "account", "assignments"])
def test_absent_job_oracle_requires_missing_job_at_requested_account(change, monkeypatch):
    *_, target, watch, entry, stages, error = delegated("nonexistent-job", monkeypatch)
    rejected = entry["traceback"]["preparation_frames"][0]
    if change == "present-job":
        rejected["job"] = next(iter(rejected["jobs"].values()))
    elif change == "scope-present":
        rejected["scopes"][target] = identity(2)
    elif change == "account":
        rejected["account"] = entry["manifest"]["accounts"][-2]
    else:
        rejected["assignments"] = {}
    with pytest.raises(AssertionError):
        assert_cohort_refusal(
            entry, stages, error, watch, case="nonexistent-job", target_job=target
        )


def test_preparation_baseexception_remains_original_and_is_recorded(monkeypatch):
    _, _, _, manifest, _, watch, context = scenario("omit-admitted-zero")
    original = KeyboardInterrupt("cohort-control")

    def fail():
        raise original

    watch.work.check = fail
    recorded = []
    with (
        observe_cohort(watch, monkeypatch, lambda *value: recorded.append(value)) as observed,
        pytest.raises(KeyboardInterrupt) as failure,
    ):
        ledger_service._prepare_ledger(context, validate_ledger_manifest(manifest), watch.work)
    (entry,), stages = observed
    assert failure.value is original
    assert entry["error"]["identity"] == id(original)
    assert entry["error"]["type"] == "KeyboardInterrupt"
    assert stages == ["prepare.enter", "prepare.refused"]
    assert len(recorded) == 1
