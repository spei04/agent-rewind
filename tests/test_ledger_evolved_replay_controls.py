"""Independent pure observations for R1; native nodes are collection-only here."""

import hashlib
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from ledger_account_identity_fixture import job_intents
from ledger_accounted_carry_fixture import replace_rows
from ledger_eligibility_fixture import rows
from ledger_evolved_replay_fixture import (
    CALL,
    CLOCK_SQL,
    EVIDENCE,
    LOGICAL_CALL,
    SETTLEMENT,
    admit_service,
    assert_completion,
    assert_evolution,
    assert_expiry_clock,
    assert_replay_preservation,
    cohort,
    dispatch,
    equal,
    expiry_initial,
    file_bytes,
    mixed_initial,
    source_rows_from_state,
    timestamp,
)
from ledger_evolved_replay_observer import (
    anchor,
    assert_observation,
    observe_replay,
    replay_financial,
    sites,
)
from ledger_provisioning_fixture import identity
from ledger_restore_authority import typed

from agent_rewind.migrations import ledger_provisioning, ledger_service
from agent_rewind.migrations.ledger_inputs import read_ledger_manifest, validate_ledger_manifest
from agent_rewind.migrations.schema import LEDGER, installed_profile

OBSERVED = datetime(2026, 10, 27, 12, tzinfo=UTC)


def witness():
    """Literal small mixed cohort; never calls an expected-evolution helper."""
    organization, project = identity(1), identity(2)
    job_ids = [identity(i) for i in (3, 4, 5, 6)]
    amounts = [35000, 85000, 125000]
    fixture = SimpleNamespace(
        case=SimpleNamespace(adoption={"installation_key": "synthetic-r1"}),
        organization=organization,
        project=project,
        source="a" * 64,
        jobs=[
            {"id": job, "project_id": project, "budget": 10_000_000, "reserved": amount}
            for job, amount in zip(job_ids, amounts, strict=False)
        ],
    )
    first = mixed_initial(fixture)
    evolved = SimpleNamespace(
        **{
            **fixture.__dict__,
            "jobs": fixture.jobs
            + [{"id": job_ids[3], "project_id": project, "budget": 1, "reserved": 0}],
        }
    )
    one, _ = job_intents(evolved, first, job_ids[3])
    profile = installed_profile("postgresql", LEDGER)
    before = {
        "catalog": deepcopy(profile),
        "authority": {"literal": ["owner", None]},
        "role": "synthetic-owner",
        "tables": {
            name: {"columns": tuple(c[0] for c in value["columns"]), "rows": ()}
            for name, value in profile.items()
            if not name.startswith("$")
        },
    }

    def complete(name, **values):
        return {column: values.get(column) for column in before["tables"][name]["columns"]}

    jobs = [
        complete(
            "jobs",
            id=job,
            kind="run",
            created=1700000000.125,
            payload="c" * 64,
            status="queued" if i == 3 else "succeeded",
            owner=None,
            lease_until=None,
            cancel=False,
            budget=1 if i == 3 else 10_000_000,
            reserved=0 if i == 3 else amounts[i],
            actor="literal-principal",
            payload_version=2 if i == 3 else 1,
            execution_config_ref="e" * 64 if i == 3 else None,
            execution_config_digest="e" * 64 if i == 3 else None,
            lease_generation=0,
            legacy_reserved_microusd=0 if i == 3 else amounts[i],
        )
        for i, job in enumerate(job_ids)
    ]
    replace_rows(before, "jobs", jobs)
    replace_rows(before, "organizations", [complete("organizations", id=organization)])
    replace_rows(
        before, "projects", [complete("projects", id=project, organization_id=organization)]
    )
    replace_rows(
        before,
        "resource_scopes",
        [{"resource_kind": "job", "resource_id": job, "project_id": project} for job in job_ids],
    )
    replace_rows(
        before,
        "project_memberships",
        [
            complete(
                "project_memberships",
                project_id=project,
                principal_id="literal-principal",
                role="maintainer",
                legacy_default=True,
            )
        ],
    )
    accounts = []
    for account in first["accounts"] + one["accounts"]:
        held = (
            245000
            if account["scope"] != "job"
            else (
                0 if account["job_id"] == job_ids[3] else amounts[job_ids.index(account["job_id"])]
            )
        )
        accounts.append(
            {
                **account,
                "period_start": datetime.fromisoformat(
                    account["period_start"].replace("Z", "+00:00")
                ),
                "period_end": datetime.fromisoformat(account["period_end"].replace("Z", "+00:00")),
                "opening_held_microusd": held,
                "held_microusd": held,
                "accounted_microusd": 0,
            }
        )
    replace_rows(before, "budget_accounts", accounts)
    replace_rows(
        before,
        "records",
        [complete("records", id=identity(90), kind="task", created=1.5, data='{"retain":1}')],
    )
    replace_rows(
        before,
        "migration_progress",
        [
            complete(
                "migration_progress",
                revision=LEDGER,
                phase="ledger_opening",
                cursor={"independent": [1, "unchanged native JSONB"]},
                rows_verified=3,
                source_digest="a" * 64,
                status="complete",
                updated_at=OBSERVED,
            )
        ],
    )
    ids = {
        "organization": organization,
        "project": project,
        "job": job_ids[3],
        "accounts": [identity(100), identity(200), identity(8001)],
        "call": CALL,
        "logical_call": LOGICAL_CALL,
        "price": "literal-price",
        "observed": timestamp(OBSERVED),
        "lease_until": float(OBSERVED.timestamp() + 3600),
    }
    observed = deepcopy(before)
    # This call/triple is independently written rather than produced by reservation_rows.
    call = {
        "id": CALL,
        "project_id": project,
        "job_id": job_ids[3],
        "logical_call_id": LOGICAL_CALL,
        "purpose": "continuation",
        "request_digest": "a" * 64,
        "price_version": "literal-price",
        "state": "reserved",
        "reserved_microusd": 1,
        "usage_estimate_microusd": None,
        "provider_request_id": None,
        "created_at": OBSERVED,
        "organization_id": organization,
        "job_resource_kind": "job",
        "lease_generation": 1,
        "organization_account_id": identity(100),
        "project_account_id": identity(200),
        "job_account_id": identity(8001),
    }
    replace_rows(observed, "provider_calls", [call])
    replace_rows(
        observed,
        "resource_scopes",
        rows(before, "resource_scopes")
        + [{"resource_kind": "provider_call", "resource_id": CALL, "project_id": project}],
    )
    entries = [
        {
            "call_id": CALL,
            "account_id": account,
            "entry_kind": "reserve",
            "amount_microusd": 1,
            "created_at": OBSERVED,
            "project_id": project,
            "evidence_ref": None,
            "evidence_owner_kind": "provider_call",
            "evidence_role": "budget_evidence",
        }
        for account in (identity(100), identity(200), identity(8001))
    ]
    replace_rows(observed, "budget_entries", entries)
    replace_rows(
        observed,
        "jobs",
        [
            {
                **row,
                "status": "running",
                "owner": "synthetic-worker",
                "lease_until": ids["lease_until"],
                "lease_generation": 2,
                "reserved": 1,
            }
            if row["id"] == job_ids[3]
            else row
            for row in jobs
        ],
    )
    literal_held = {identity(100): 245001, identity(200): 245001, identity(8001): 1}
    replace_rows(
        observed,
        "budget_accounts",
        [
            {**row, "held_microusd": literal_held[row["id"]]} if row["id"] in literal_held else row
            for row in accounts
        ],
    )
    evidence = complete(
        "artifact_objects",
        id=EVIDENCE,
        project_id=project,
        digest=hashlib.sha256(SETTLEMENT).hexdigest(),
        locator="literal/settlement",
        format_version=1,
        byte_count=len(SETTLEMENT),
        created_at=OBSERVED,
    )
    settled = deepcopy(observed)
    replace_rows(settled, "provider_calls", [{**call, "state": "reconciled"}])
    replace_rows(
        settled,
        "budget_entries",
        entries + [{**row, "entry_kind": "settle", "evidence_ref": EVIDENCE} for row in entries],
    )
    replace_rows(
        settled,
        "budget_accounts",
        [
            {
                **row,
                "held_microusd": 0 if row["id"] == identity(8001) else 245000,
                "accounted_microusd": 1,
            }
            if row["id"] in literal_held
            else row
            for row in rows(observed, "budget_accounts")
        ],
    )
    replace_rows(
        settled,
        "jobs",
        [
            {**row, "budget": 10_000_001} if row["id"] == job_ids[0] else row
            for row in rows(observed, "jobs")
        ],
    )
    replace_rows(settled, "project_memberships", [])
    replace_rows(settled, "artifact_objects", [evidence])
    replace_rows(
        settled,
        "artifact_refs",
        [
            {
                "project_id": project,
                "owner_kind": "provider_call",
                "owner_id": CALL,
                "role": "budget_evidence",
                "artifact_id": EVIDENCE,
            }
        ],
    )
    return SimpleNamespace(
        fixture=fixture,
        first=first,
        one=one,
        before=before,
        ids=ids,
        reserved=observed,
        settled=settled,
        evidence=evidence,
        legacy=job_ids[0],
        membership=(project, "literal-principal"),
    )


@pytest.mark.parametrize("phase", ["reserved", "settled"])
def test_independent_mixed_full_state_is_accepted(phase):
    w = witness()
    original = deepcopy(w.before)
    extra = (
        {}
        if phase == "reserved"
        else {"evidence": w.evidence, "legacy_job": w.legacy, "membership": w.membership}
    )
    assert_evolution(w.before, getattr(w, phase), w.ids, **extra)
    equal(w.before, original)
    equal(
        cohort(w.before, w.first, w.one, w.ids["job"], "literal-price", timestamp(OBSERVED)), w.ids
    )


@pytest.mark.parametrize("phase", ["reserved", "settled"])
@pytest.mark.parametrize(
    "damage",
    [
        "legacy-held",
        "legacy-budget",
        "admitted-budget",
        "admitted-config",
        "generation",
        "call-generation",
        "missing-entry",
        "wrong-triple",
        "entry-bool",
        "account-float",
        "raw-progress",
        "unrelated-record",
        "authority",
        "catalog",
        "missing-table",
    ],
)
def test_complete_evolution_rejects_independent_corruption(phase, damage):
    w = witness()
    after = deepcopy(getattr(w, phase))
    if damage in {"authority", "catalog"}:
        after[damage]["unrelated"] = "changed"
    elif damage == "missing-table":
        del after["tables"]["operations"]
    else:
        table = {
            "legacy-held": "budget_accounts",
            "legacy-budget": "jobs",
            "admitted-budget": "jobs",
            "admitted-config": "jobs",
            "generation": "jobs",
            "call-generation": "provider_calls",
            "missing-entry": "budget_entries",
            "wrong-triple": "budget_entries",
            "entry-bool": "budget_entries",
            "account-float": "budget_accounts",
            "raw-progress": "migration_progress",
            "unrelated-record": "records",
        }[damage]
        values = rows(after, table)
        if damage == "missing-entry":
            values.pop()
        elif damage == "legacy-held":
            next(row for row in values if row["job_id"] == w.legacy)["held_microusd"] += 1
        elif damage == "legacy-budget":
            next(row for row in values if row["id"] == w.legacy)["budget"] += 1
        elif damage in {"admitted-budget", "admitted-config", "generation"}:
            row = next(row for row in values if row["id"] == w.ids["job"])
            key = {
                "admitted-budget": "budget",
                "admitted-config": "execution_config_digest",
                "generation": "lease_generation",
            }[damage]
            row[key] = "f" * 64 if damage == "admitted-config" else row[key] + 1
        elif damage == "call-generation":
            values[0]["lease_generation"] = 3
        elif damage == "wrong-triple":
            values[0]["account_id"] = identity(300)
        elif damage == "entry-bool":
            values[0]["amount_microusd"] = True
        elif damage == "account-float":
            values[0]["held_microusd"] = float(values[0]["held_microusd"])
        elif damage == "raw-progress":
            values[0]["cursor"]["independent"][0] = True
        else:
            values[0]["data"] = '{"retain":2}'
        replace_rows(after, table, values)
    extra = (
        {}
        if phase == "reserved"
        else {"evidence": w.evidence, "legacy_job": w.legacy, "membership": w.membership}
    )
    with pytest.raises(AssertionError):
        assert_evolution(w.before, after, w.ids, **extra)


@pytest.mark.parametrize(
    "damage",
    ["no-headroom", "wrong-job", "duplicate-account", "bad-call", "bad-lease", "wrong-price-type"],
)
def test_producer_identity_prerequisites_are_closed(damage):
    w = witness()
    if damage == "no-headroom":
        values = rows(w.before, "budget_accounts")
        next(row for row in values if row["scope"] == "organization")["limit_microusd"] = 245000
        replace_rows(w.before, "budget_accounts", values)
    elif damage == "wrong-job":
        w.ids["job"] = w.legacy
    elif damage == "duplicate-account":
        w.ids["accounts"][2] = w.ids["accounts"][1]
    elif damage == "bad-call":
        w.ids["call"] = identity(99)
    elif damage == "bad-lease":
        w.ids["lease_until"] = True
    else:
        w.ids["price"] = 7
    with pytest.raises((AssertionError, ValueError)):
        assert_evolution(w.before, w.reserved, w.ids)


@pytest.mark.parametrize("damage", ["table", "source", "storage", "receipt-type", "receipt-time"])
def test_replay_requires_full_preservation(damage):
    w = witness()
    before, after = w.settled, deepcopy(w.settled)
    source = source_rows_from_state(before)
    original = {"sequence": 0, "initialized_at": timestamp(OBSERVED)}
    returned = deepcopy(original)
    stores = {"legacy": {"x": "a" * 64}, "objects": {"y": "b" * 64}}
    current = deepcopy(stores)
    if damage == "table":
        after["tables"]["records"]["rows"] = ()
    elif damage == "source":
        source["jobs"] = []
    elif damage == "storage":
        current["legacy"]["x"] = "c" * 64
    elif damage == "receipt-type":
        returned["sequence"] = False
    else:
        returned["initialized_at"] = timestamp(OBSERVED + timedelta(seconds=1))
    with pytest.raises(AssertionError):
        assert_replay_preservation(before, after, original, returned, source, stores, current)


def test_real_manifest_file_whitespace_has_identical_model_and_digest(tmp_path):
    w = witness()
    plain, spaced = file_bytes(w.first)
    values = []
    for name, data in (("canonical", plain), ("whitespace", spaced)):
        path = tmp_path / name
        path.write_bytes(data)
        path.chmod(0o600)
        values.append(read_ledger_manifest(path))
    assert plain != spaced
    equal(values[0].canonical_bytes, values[1].canonical_bytes)
    equal(values[0].digest, values[1].digest)


@pytest.mark.parametrize(
    "value", [None, "", "nan", "inf", "-1", "0", "1e3", " 1000", True, "1000.0001", "984.999"]
)
def test_dispatch_rejects_missing_malformed_future_stale_values(value):
    with pytest.raises(AssertionError):
        dispatch(value, 1000)


@pytest.mark.parametrize("expired,remaining", [(False, 150), (True, 145)])
def test_service_admission_accepts_exact_reserve(expired, remaining):
    schedule = dispatch("1000", 1000)
    admit_service(schedule, 1360 - remaining, expired=expired)
    with pytest.raises(AssertionError):
        admit_service(schedule, 1360 - remaining + 0.001, expired=expired)


def clock_witness():
    w = witness()
    schedule = dispatch("1000", 1005)
    first = expiry_initial(w.fixture, timestamp(OBSERVED))
    samples = [
        {
            "before": before,
            "after": before + 0.1,
            "database": timestamp(OBSERVED + timedelta(seconds=offset)),
            "sql": CLOCK_SQL,
            "role": "owner",
            "database_name": "synthetic_db",
            "connection_closed": True,
            "drained": True,
        }
        for before, offset in ((1010.0, 0), (1160.1, 150.1), (1161.2, 151.2))
    ]
    return schedule, first, {"initialized_at": timestamp(OBSERVED + timedelta(seconds=4))}, samples


def test_real_clock_gate_accepts_independent_elapsed_expiry():
    schedule, first, receipt, samples = clock_witness()
    assert_expiry_clock(schedule, first, receipt, samples, 1011, 1020, 1161.4)


@pytest.mark.parametrize(
    "damage",
    [
        "setup-late",
        "m0-entry-late",
        "m0-proof-late",
        "expired-m0",
        "not-crossed",
        "jump",
        "regression",
        "unclosed",
        "undrained",
        "wrong-sql",
        "wrong-role",
        "slow-read",
        "cadence",
        "late-crossing",
        "stale-entry",
        "exhausted",
        "float-closed",
        "wrong-period",
    ],
)
def test_expiry_gate_rejects_invalid_preconditions(damage):
    schedule, first, receipt, samples = clock_witness()
    start, finish, entry = 1011, 1020, 1161.4
    if damage == "setup-late":
        schedule["entered"] = 980
    elif damage == "m0-entry-late":
        start = 1021
    elif damage == "m0-proof-late":
        finish = 1146
    elif damage == "expired-m0":
        receipt["initialized_at"] = timestamp(OBSERVED + timedelta(seconds=150))
    elif damage == "not-crossed":
        samples = samples[:1] + [
            {
                **samples[1],
                "before": 1100.0,
                "after": 1100.1,
                "database": timestamp(OBSERVED + timedelta(seconds=90)),
            }
        ]
        entry = 1100.2
    elif damage == "jump":
        samples[-1]["database"] = timestamp(OBSERVED + timedelta(seconds=200))
    elif damage == "regression":
        samples[-1]["database"] = timestamp(OBSERVED + timedelta(seconds=149))
    elif damage in {"unclosed", "undrained", "float-closed"}:
        samples[-1]["connection_closed" if damage != "undrained" else "drained"] = (
            1.0 if damage == "float-closed" else False
        )
    elif damage == "wrong-sql":
        samples[-1]["sql"] = "SELECT now()"
    elif damage == "wrong-role":
        samples[-1]["role"] = "other"
    elif damage == "slow-read":
        samples[-1]["after"] += 6
    elif damage == "cadence":
        samples[-1]["before"] = samples[-2]["after"]
    elif damage == "late-crossing":
        samples[-1].update(
            before=1175.0, after=1175.1, database=timestamp(OBSERVED + timedelta(seconds=165))
        )
        entry = 1175.2
    elif damage == "stale-entry":
        entry = 1163
    elif damage == "exhausted":
        samples = [samples[0]] * 167
    else:
        first["accounts"][0]["period_end"] = timestamp(OBSERVED + timedelta(seconds=149))
    with pytest.raises(AssertionError):
        assert_expiry_clock(schedule, first, receipt, samples, start, finish, entry)


def financial_witness():
    # Literal reader cohort; not produced by financial_projection or the validator.
    return {
        "account": [{"id": "selected", "held_microusd": 245001, "accounted_microusd": 0}],
        "job": [],
        "call": [],
        "entry": [],
        "scope": [],
        "ref": [],
        "object": [],
        "operation": [],
        "project": [],
        "organization": [],
    }


def observation_witness():
    w = witness()
    identity_values = {"raw_id": 11, "work_id": 12, "engine_id": 13, "connection_id": 14}
    original = {"sequence": 0, "initialized_at": timestamp(OBSERVED), "outcome": "complete"}
    state = {"head": {"sequence": 1}, "opening": {"organization_opening_microusd": 245000}}
    positions = sites()
    reader = {
        **identity_values,
        "entered_at": 1,
        "returned_at": 100,
        "context_id": 15,
        "original_caller": True,
        "line": positions["_inspect_ledger_context"][0],
        "state": state,
        "financial": {
            "account": typed(
                [{"id": "selected", "held_microusd": 245001, "accounted_microusd": 0}]
            ),
            **{
                name: typed([])
                for name in (
                    "job",
                    "call",
                    "entry",
                    "scope",
                    "ref",
                    "object",
                    "operation",
                    "project",
                    "organization",
                )
            },
        },
    }
    classifier = {
        **identity_values,
        "entered_at": 100,
        "returned_at": 100,
        "context_id": 15,
        "original_caller": True,
        "line": positions["_classify_manifest"][0],
        "manifest": w.first,
        "receipt": {k: v for k, v in original.items() if k != "outcome"},
    }
    return (
        w.first,
        original,
        state,
        identity_values,
        {"inspection": [reader], "classification": [classifier], "new_intent": []},
    )


def test_complete_original_reader_classifier_join():
    manifest, receipt, state, identity_values, observed = observation_witness()
    assert_observation(
        observed, manifest, receipt, state, identity_values, 110, financial_witness()
    )


@pytest.mark.parametrize(
    "damage",
    [
        "reader-missing",
        "wrong-context",
        "foreign-raw",
        "float-work",
        "wrong-caller",
        "wrong-line",
        "new-write",
        "receipt",
        "state",
        "order",
        "original-error",
        "financial-balance",
        "financial-extra-domain",
    ],
)
def test_replay_join_rejects_wrong_branch_or_identity(damage):
    manifest, receipt, state, identity_values, observed = observation_witness()
    observed = deepcopy(observed)
    row = observed["classification"][0]
    if damage == "reader-missing":
        observed["inspection"] = []
    elif damage == "wrong-context":
        row["context_id"] += 1
    elif damage == "foreign-raw":
        row["raw_id"] += 1
    elif damage == "float-work":
        row["work_id"] = float(row["work_id"])
    elif damage == "wrong-caller":
        row["original_caller"] = False
    elif damage == "wrong-line":
        row["line"] += 1
    elif damage == "new-write":
        observed["new_intent"] = [{"name": "_write"}]
    elif damage == "receipt":
        row["receipt"]["sequence"] = False
    elif damage == "state":
        observed["inspection"][0]["state"]["head"]["sequence"] = 0
    elif damage == "order":
        row["entered_at"] = 99
    elif damage == "financial-balance":
        observed["inspection"][0]["financial"]["account"] = typed(
            [{"id": "selected", "held_microusd": 245000, "accounted_microusd": 0}]
        )
    elif damage == "financial-extra-domain":
        observed["inspection"][0]["financial"]["unreviewed"] = typed([])
    else:
        row["error"] = {"type": "MigrationRefused"}
    with pytest.raises((AssertionError, ValueError)):
        assert_observation(
            observed, manifest, receipt, state, identity_values, 110, financial_witness()
        )


def test_observer_registration_never_reads_uncreated_work(monkeypatch):
    class EmptyWatch:
        @property
        def work(self):
            raise AssertionError("work is not constructed until service entry")

    saved = []
    with observe_replay(EmptyWatch(), monkeypatch, lambda *value: saved.append(value)) as observed:
        equal(observed, {"inspection": [], "classification": [], "new_intent": []})
    assert len(saved) == 1


def test_observer_delegates_original_classifier_and_preserves_receipt_identity(monkeypatch):
    w = witness()
    manifest = validate_ledger_manifest(w.first)
    receipt = SimpleNamespace(model_dump=lambda **_: {"sequence": 0})
    context = SimpleNamespace(
        state=SimpleNamespace(installation_key=manifest.installation_key),
        history=SimpleNamespace(manifests=[SimpleNamespace(manifest=manifest, receipt=receipt)]),
    )
    engine = object()
    work = SimpleNamespace(
        _raw=object(), _connection=SimpleNamespace(engine=engine), check=lambda: None
    )
    watch = SimpleNamespace(work=work, engine=engine, trace=SimpleNamespace(events=[]))
    with observe_replay(watch, monkeypatch, lambda *_: None) as observed:
        result = ledger_service._classify_manifest(context, manifest, work)
    assert result is receipt
    equal(observed["classification"][0]["receipt"], {"sequence": 0})
    equal(observed["classification"][0]["work_id"], id(work))
    assert ledger_service._classify_manifest is ledger_provisioning._classify_manifest
    equal(anchor(watch)["raw_id"], id(work._raw))


def test_completion_accepts_exact_original_shutdown_boundary():
    assert_completion(
        dispatch("1000", 1001),
        {"proof_finished": 1339, "cleanup_started": 1339.5, "cleanup_finished": 1340},
    )


@pytest.mark.parametrize(
    "timing",
    [
        {"proof_finished": 1339, "cleanup_started": 1339.5, "cleanup_finished": 1340.001},
        {"proof_finished": 1339, "cleanup_started": 1338, "cleanup_finished": 1340},
        {"proof_finished": 1339, "cleanup_started": 1340, "cleanup_finished": 1339.5},
        {"proof_finished": 999, "cleanup_started": 1339.5, "cleanup_finished": 1340},
        {"proof_finished": True, "cleanup_started": 1339.5, "cleanup_finished": 1340},
        {"proof_finished": 1339, "cleanup_started": 1339.5, "cleanup_finished": float("inf")},
    ],
)
def test_completion_rejects_late_unordered_or_untyped_proof(timing):
    with pytest.raises(AssertionError):
        assert_completion(dispatch("1000", 1001), timing)


def test_original_failure_survives_local_cleanup_failure():
    from test_ledger_evolved_replay_postgres import finish_case

    earlier = RuntimeError("original service failure")
    cleanup = OSError("cleanup failed")

    def close():
        raise cleanup

    saved = []
    finish_case(
        SimpleNamespace(close=close),
        dispatch("1000", 1001),
        lambda *record: saved.append(record),
        None,
        None,
        earlier,
    )
    assert saved[0][0] == "completion_diagnostic"
    assert saved[0][1]["earlier_error"] == "RuntimeError"
    assert saved[0][1]["cleanup_error"] == "OSError"
    assert earlier.__notes__ == ["Local fixture cleanup also failed: OSError"]


@pytest.mark.parametrize(
    "native_name",
    [
        "test_postgres_evolved_original_and_whitespace_replay",
        "test_postgres_expired_opening_original_replay",
    ],
)
@pytest.mark.parametrize(
    ("postgres_enabled", "supplied", "skipped", "invalid"),
    [
        (True, None, True, False),
        (True, "", False, True),
        (True, "malformed", False, True),
        (True, "1002", False, True),
        (True, "900", False, True),
        (True, "1000", False, False),
        (False, "1000", True, False),
    ],
    ids=["absent", "empty", "malformed", "future", "stale", "valid", "postgres-absent"],
)
def test_actual_native_collection_requires_bounded_runner_key(
    monkeypatch, request, native_name, postgres_enabled, supplied, skipped, invalid
):
    """Use pinned pytest's real marker decision; no fixture or native body is entered."""
    import importlib.util
    from pathlib import Path

    import test_migrations_postgres as migration_tests
    from _pytest.skipping import evaluate_skip_marks

    with monkeypatch.context() as patch:
        # These values qualify only an isolated module's collection metadata.
        patch.setattr(migration_tests, "POSTGRES", postgres_enabled)
        if supplied is None:
            patch.delenv("AR_R1_CHILD_STARTED_MONOTONIC", raising=False)
        else:
            patch.setenv("AR_R1_CHILD_STARTED_MONOTONIC", supplied)
        spec = importlib.util.spec_from_file_location(
            "_r1_collection_probe",
            Path(__file__).with_name("test_ledger_evolved_replay_postgres.py"),
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        target = getattr(module, native_name)
        item = pytest.Function.from_parent(
            request.node.parent, name="bounded-runner-collection-probe", callobj=target
        )
        assert item.function is target
        decision = evaluate_skip_marks(item)
        assert (decision is not None) is skipped
        if supplied is None:
            assert "reviewed R1 bounded runner" in decision.reason
        elif not postgres_enabled:
            assert "Opt-in" in decision.reason
        elif invalid:
            with pytest.raises(AssertionError):
                dispatch(supplied, 1001)
        else:
            equal(
                dispatch(supplied, 1001), {"started": 1000.0, "entered": 1001, "deadline": 1360.0}
            )


def mixed_scope_reader_witness(*, reserved=True):
    """Literal selected identities plus unrelated persisted run/key scopes."""
    value = witness()
    full = deepcopy(value.reserved if reserved else value.before)
    project = identity(2)
    jobs = [
        {"resource_kind": "job", "resource_id": identity(i), "project_id": project}
        for i in (3, 4, 5, 6)
    ]
    selected = jobs + (
        [{"resource_kind": "provider_call", "resource_id": CALL, "project_id": project}]
        if reserved
        else []
    )
    unrelated = [
        {"resource_kind": "key", "resource_id": identity(31), "project_id": project},
        {"resource_kind": "key", "resource_id": identity(32), "project_id": project},
        {"resource_kind": "run", "resource_id": identity(41), "project_id": project},
        {"resource_kind": "run", "resource_id": identity(42), "project_id": project},
    ]
    replace_rows(full, "resource_scopes", selected + unrelated)
    return full, selected, unrelated


@pytest.mark.parametrize("reserved", [False, True])
def test_replay_reader_scope_subset_preserves_complete_native_state(reserved):
    full, selected, unrelated = mixed_scope_reader_witness(reserved=reserved)
    before = deepcopy(full)
    actual = replay_financial(full)
    equal(actual["scope"], selected)
    equal(full, before)
    assert len(rows(full, "resource_scopes")) == len(selected) + 4
    equal(
        [row for row in rows(full, "resource_scopes") if row["resource_kind"] in {"key", "run"}],
        unrelated,
    )


def test_complete_reader_accepts_independently_selected_scope_observation():
    full, selected, _ = mixed_scope_reader_witness()
    manifest, receipt, state, identity_values, observed = observation_witness()
    observed["inspection"][0]["financial"]["scope"] = typed(selected)
    expected = {**financial_witness(), "scope": replay_financial(full)["scope"]}
    assert_observation(observed, manifest, receipt, state, identity_values, 110, expected)


@pytest.mark.parametrize("damage", ["unfiltered", "key", "missing-job", "missing-call"])
def test_complete_reader_rejects_wrong_scope_domain(damage):
    full, selected, unrelated = mixed_scope_reader_witness()
    manifest, receipt, state, identity_values, observed = observation_witness()
    wrong = deepcopy(selected)
    if damage == "unfiltered":
        wrong += unrelated
    elif damage == "key":
        wrong += unrelated[:1]
    elif damage == "missing-job":
        wrong.pop(0)
    else:
        wrong.pop()
    observed["inspection"][0]["financial"]["scope"] = typed(wrong)
    expected = {**financial_witness(), "scope": replay_financial(full)["scope"]}
    with pytest.raises(AssertionError):
        assert_observation(observed, manifest, receipt, state, identity_values, 110, expected)


def test_reader_scope_subset_does_not_permit_full_state_deletion():
    full, selected, _ = mixed_scope_reader_witness()
    damaged = deepcopy(full)
    replace_rows(damaged, "resource_scopes", selected)
    receipt = {"sequence": 0, "outcome": "complete"}
    with pytest.raises(AssertionError):
        assert_replay_preservation(
            full, damaged, receipt, receipt, source_rows_from_state(full), {}, {}
        )


@pytest.mark.parametrize(
    ("case_name", "expected"),
    [
        (
            "evolved-original-and-whitespace",
            (
                "replay_case",
                "schedule",
                "original_predecessor",
                "M0_manifest",
                "M0_service",
                "M0_stage",
                "M0_receipt",
                "M0_state",
                "admission_setup",
                "M1_manifest",
                "M1_service",
                "M1_stage",
                "M1_receipt",
                "M1_state",
                "cohort",
                "reserved_setup",
                "reserved_observation",
                "reserved_service",
                "reserved_result",
                "settled_setup",
                "canonical_observation",
                "canonical_service",
                "canonical_result",
                "whitespace_observation",
                "whitespace_service",
                "whitespace_result",
                "final_preservation",
            ),
        ),
        (
            "expired-opening-original-replay",
            (
                "replay_case",
                "schedule",
                "original_predecessor",
                "clock_anchor",
                "M0_manifest",
                "M0_service",
                "M0_stage",
                "M0_receipt",
                "M0_state",
                "expiry_clock",
                "expired_observation",
                "expired_service",
                "expired_result",
                "final_preservation",
            ),
        ),
    ],
)
def test_property_contract_matches_independent_emission_order(case_name, expected):
    # Mixed order is literal from the retained native XML b3cd104e; expiry uses
    # the same replay emitter, whose context-exit behavior is checked below.
    from test_ledger_evolved_replay_postgres import PROPERTY_CONTRACT

    assert len(expected) == len(set(expected))
    equal(PROPERTY_CONTRACT[case_name], expected)


@pytest.mark.parametrize("label", ["reserved", "canonical", "whitespace", "expired"])
def test_original_replay_emits_observation_before_service(monkeypatch, tmp_path, label):
    """Exercise original replay/observer context exits, with no native service."""
    import json
    import time
    from contextlib import contextmanager

    import test_ledger_evolved_replay_postgres as native

    value = witness()
    path = tmp_path / "manifest.json"
    path.write_bytes(file_bytes(value.first)[0])
    path.chmod(0o600)
    fixture = SimpleNamespace(case=object())
    watch = SimpleNamespace(engine=object())
    properties = []
    service_calls = []
    completed = RuntimeError("stop after both original replay contexts have finalized")

    def record_property(name, encoded):
        properties.append((name, json.loads(encoded)))

    @contextmanager
    def inert_command(actual_fixture, pg, patch, save, *, label, observe_writes):
        assert actual_fixture is fixture and pg is None and patch is monkeypatch
        assert observe_writes is True
        try:
            yield watch
        finally:
            save(label, '{"synthetic_command": true}')

    def inert_service(engine, manifest):
        assert engine is watch.engine
        equal(manifest.model_dump(mode="json"), value.first)
        service_calls.append(manifest)
        return object()

    def stop_after_contexts(actual_watch, action):
        assert actual_watch is watch and action == "commit"
        raise completed

    monkeypatch.setattr(native, "native_snapshot", lambda *_: deepcopy(value.before))
    monkeypatch.setattr(native, "stored", lambda *_: {})
    monkeypatch.setattr(native, "observe_command", inert_command)
    monkeypatch.setattr(native.ledger_service, "initialize_ledger", inert_service)
    monkeypatch.setattr(native, "assert_physical_completion", stop_after_contexts)
    started = time.monotonic()
    with pytest.raises(RuntimeError) as caught:
        native.replay(
            fixture,
            None,
            value.first,
            path,
            object(),
            {},
            dispatch(str(started), started),
            monkeypatch,
            record_property,
            native.recorder(record_property),
            label,
            expired=label == "expired",
        )
    assert caught.value is completed
    assert len(service_calls) == 1
    names = tuple(name for name, _ in properties)
    equal(names, (label + "_observation", label + "_service"))
    equal(properties[0][1], {"inspection": [], "classification": [], "new_intent": []})
    case_name = (
        "expired-opening-original-replay"
        if label == "expired"
        else "evolved-original-and-whitespace"
    )
    contract = native.PROPERTY_CONTRACT[case_name]
    position = contract.index(label + "_observation")
    equal(contract[position : position + 2], names)
