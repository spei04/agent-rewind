"""Independent evolved-state, immutable replay and bounded real-clock oracles."""

import math
import re
from copy import deepcopy
from datetime import UTC, datetime, timedelta

from ledger_accounted_carry_fixture import replace_rows
from ledger_eligibility_fixture import rows
from ledger_provisioning_fixture import canonical, initial_manifest, source_fingerprint
from ledger_restore_authority import typed

from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import LEDGER, installed_profile

CASES = ("evolved-original-and-whitespace", "expired-opening-original-replay")
CHILD_SECONDS = 360
CLOCK_SQL = "SELECT clock_timestamp(), current_user, current_database()"
CALL = "00000000000000000000000000910001"
LOGICAL_CALL = "00000000000000000000000000910002"
EVIDENCE = "00000000000000000000000000910003"
SETTLEMENT = b"R1 declared synthetic settlement; no provider execution"


def equal(actual, expected):
    assert typed(actual) == typed(expected)


def instant(value):
    assert type(value) is str
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert result.tzinfo is not None and result.utcoffset() == timedelta(0)
    assert result.isoformat(timespec="microseconds").replace("+00:00", "Z") == value
    return result


def timestamp(value):
    assert type(value) is datetime and value.utcoffset() == timedelta(0)
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def number(value):
    assert type(value) in (int, float) and math.isfinite(value) and value >= 0
    return value


def dispatch(value, entered):
    """Required controller-owned Popen timestamp; never reset the child deadline."""
    number(entered)
    assert type(value) is str and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value)
    started = float(value)
    assert math.isfinite(started) and 0 < started <= entered <= started + 15
    return {"started": started, "entered": entered, "deadline": started + CHILD_SECONDS}


def admit_service(schedule, now, *, expired=False):
    number(now)
    assert type(expired) is bool
    equal(schedule["deadline"], schedule["started"] + CHILD_SECONDS)
    assert schedule["entered"] <= now
    assert schedule["deadline"] - now >= (145 if expired else 150)


def assert_completion(schedule, timing):
    """Full final proof and local cleanup must leave the original shutdown reserve."""
    assert set(timing) == {"proof_finished", "cleanup_started", "cleanup_finished"}
    proof, start, finish = (
        number(timing[key]) for key in ("proof_finished", "cleanup_started", "cleanup_finished")
    )
    equal(schedule["deadline"], schedule["started"] + CHILD_SECONDS)
    assert schedule["entered"] <= proof <= start <= finish <= schedule["started"] + 340


def mixed_initial(fixture):
    first = initial_manifest(fixture)
    for account in first["accounts"]:
        if account["scope"] in {"organization", "project"}:
            equal(account["limit_microusd"], 245000)
            account["limit_microusd"] = 245001
    validate_ledger_manifest(first)
    return first


def expiry_initial(fixture, database_time):
    observed = instant(database_time)
    first = initial_manifest(fixture)
    for account in first["accounts"]:
        if account["scope"] in {"organization", "project"}:
            account["period_start"] = timestamp(observed - timedelta(seconds=60))
            account["period_end"] = timestamp(observed + timedelta(seconds=150))
    validate_ledger_manifest(first)
    return first


def _one(values):
    (value,) = values
    return value


def _state(before):
    assert set(before) == {"catalog", "tables", "authority", "role"}
    profile = installed_profile("postgresql", LEDGER)
    assert set(before["tables"]) == {name for name in profile if not name.startswith("$")}
    assert len(before["tables"]) == 20
    for table, value in before["tables"].items():
        equal(value["columns"], tuple(column[0] for column in profile[table]["columns"]))
        assert type(value["rows"]) is tuple


def cohort(before, first, one, admitted_job, price, observed):
    """Freeze three explicit account IDs; never update an entire mixed table."""
    _state(before)
    job = _one([row for row in rows(before, "jobs") if row["id"] == admitted_job])
    equal(
        [
            job[key]
            for key in (
                "payload_version",
                "budget",
                "reserved",
                "lease_generation",
                "legacy_reserved_microusd",
                "status",
                "owner",
                "lease_until",
            )
        ],
        [2, 1, 0, 0, 0, "queued", None, None],
    )
    parents = [
        _one([row for row in first["accounts"] if row["scope"] == scope])
        for scope in ("organization", "project")
    ]
    (child,) = one["accounts"]
    assert child["scope"] == "job" and child["job_id"] == admitted_job
    assert child["organization_id"] == parents[0]["organization_id"]
    assert child["project_id"] == parents[1]["scope_id"]
    assert type(price) is str and price
    moment = instant(observed)
    for account in (*parents, child):
        assert instant(account["period_start"]) <= moment < instant(account["period_end"])
    return {
        "organization": parents[0]["organization_id"],
        "project": parents[1]["scope_id"],
        "job": admitted_job,
        "accounts": [parents[0]["id"], parents[1]["id"], child["id"]],
        "call": CALL,
        "logical_call": LOGICAL_CALL,
        "price": price,
        "observed": observed,
        "lease_until": float(moment.timestamp() + 3600),
    }


def reservation_rows(identity):
    """Declared producer inputs; independent control observations are literal."""
    observed = instant(identity["observed"])
    call = {
        "id": identity["call"],
        "project_id": identity["project"],
        "job_id": identity["job"],
        "logical_call_id": identity["logical_call"],
        "purpose": "continuation",
        "request_digest": "a" * 64,
        "price_version": identity["price"],
        "state": "reserved",
        "reserved_microusd": 1,
        "usage_estimate_microusd": None,
        "provider_request_id": None,
        "created_at": observed,
        "organization_id": identity["organization"],
        "job_resource_kind": "job",
        "lease_generation": 1,
        **dict(
            zip(
                (scope + "_account_id" for scope in ("organization", "project", "job")),
                identity["accounts"],
                strict=True,
            )
        ),
    }
    entries = [
        {
            "call_id": identity["call"],
            "account_id": account,
            "entry_kind": "reserve",
            "amount_microusd": 1,
            "created_at": observed,
            "project_id": identity["project"],
            "evidence_ref": None,
            "evidence_owner_kind": "provider_call",
            "evidence_role": "budget_evidence",
        }
        for account in identity["accounts"]
    ]
    return {
        "provider_calls": [call],
        "resource_scopes": [
            {
                "resource_kind": "provider_call",
                "resource_id": identity["call"],
                "project_id": identity["project"],
            }
        ],
        "budget_entries": entries,
    }


def expected_reserved(before, identity):
    _state(before)
    jobs = rows(before, "jobs")
    admitted = _one([row for row in jobs if row["id"] == identity["job"]])
    legacy = [row for row in jobs if row["id"] != identity["job"]]
    assert len(legacy) == 3
    equal(sorted(row["legacy_reserved_microusd"] for row in legacy), [35000, 85000, 125000])
    assert all(
        type(row["payload_version"]) is int and row["payload_version"] == 1 for row in legacy
    )
    equal(
        [
            admitted[key]
            for key in (
                "payload_version",
                "budget",
                "reserved",
                "lease_generation",
                "legacy_reserved_microusd",
                "status",
                "owner",
                "lease_until",
            )
        ],
        [2, 1, 0, 0, 0, "queued", None, None],
    )
    accounts = rows(before, "budget_accounts")
    assert len(accounts) == 6 and len(set(identity["accounts"])) == 3
    for scope, account_id, held in zip(
        ("organization", "project", "job"), identity["accounts"], (245000, 245000, 0), strict=True
    ):
        account = _one([row for row in accounts if row["id"] == account_id])
        equal(account["scope"], scope)
        equal(account["organization_id"], identity["organization"])
        equal(
            account["scope_id"],
            identity["organization"]
            if scope == "organization"
            else identity["project"]
            if scope == "project"
            else identity["job"],
        )
        equal(account["project_id"], None if scope == "organization" else identity["project"])
        equal(account["job_id"], identity["job"] if scope == "job" else None)
        equal(
            [
                account[key]
                for key in (
                    "limit_microusd",
                    "opening_held_microusd",
                    "held_microusd",
                    "accounted_microusd",
                )
            ],
            [1 if scope == "job" else 245001, held, held, 0],
        )
        assert account["period_start"] <= instant(identity["observed"]) < account["period_end"]
    equal(rows(before, "provider_calls"), [])
    equal(rows(before, "budget_entries"), [])
    equal(identity["call"], CALL)
    equal(identity["logical_call"], LOGICAL_CALL)
    assert type(identity["lease_until"]) is float and math.isfinite(identity["lease_until"])
    equal(identity["lease_until"], float(instant(identity["observed"]).timestamp() + 3600))
    result = deepcopy(before)
    for table, added in reservation_rows(identity).items():
        replace_rows(result, table, rows(before, table) + added)
    replace_rows(
        result,
        "jobs",
        [
            {
                **row,
                "status": "running",
                "owner": "synthetic-worker",
                "lease_until": identity["lease_until"],
                "lease_generation": 2,
                "reserved": 1,
            }
            if row["id"] == identity["job"]
            else row
            for row in jobs
        ],
    )
    replace_rows(
        result,
        "budget_accounts",
        [
            {**row, "held_microusd": row["held_microusd"] + 1}
            if row["id"] in identity["accounts"]
            else row
            for row in accounts
        ],
    )
    return result


def expected_settled(before, identity, evidence, legacy_job, membership):
    """Expected cumulative delta, independently bounded to the selected rows."""
    result = expected_reserved(before, identity)
    assert type(evidence) is dict and evidence["id"] == EVIDENCE
    equal(evidence["project_id"], identity["project"])
    assert type(evidence["created_at"]) is datetime
    assert type(evidence["byte_count"]) is int and evidence["byte_count"] == len(SETTLEMENT)
    import hashlib

    equal(evidence["digest"], hashlib.sha256(SETTLEMENT).hexdigest())
    assert legacy_job != identity["job"]
    old_job = _one([row for row in rows(before, "jobs") if row["id"] == legacy_job])
    equal(old_job["payload_version"], 1)
    assert type(old_job["budget"]) is int and old_job["budget"] >= old_job["reserved"]
    members = rows(before, "project_memberships")
    selected = _one(
        [row for row in members if (row["project_id"], row["principal_id"]) == tuple(membership)]
    )
    equal(selected["project_id"], identity["project"])
    replace_rows(result, "project_memberships", [row for row in members if row is not selected])
    replace_rows(
        result,
        "jobs",
        [
            {**row, "budget": row["budget"] + 1} if row["id"] == legacy_job else row
            for row in rows(result, "jobs")
        ],
    )
    replace_rows(
        result,
        "provider_calls",
        [{**row, "state": "reconciled"} for row in rows(result, "provider_calls")],
    )
    reserves = rows(result, "budget_entries")
    settlements = [
        {**row, "entry_kind": "settle", "evidence_ref": evidence["id"]} for row in reserves
    ]
    replace_rows(result, "budget_entries", reserves + settlements)
    replace_rows(
        result,
        "budget_accounts",
        [
            {**row, "held_microusd": row["held_microusd"] - 1, "accounted_microusd": 1}
            if row["id"] in identity["accounts"]
            else row
            for row in rows(result, "budget_accounts")
        ],
    )
    replace_rows(result, "artifact_objects", rows(before, "artifact_objects") + [evidence])
    replace_rows(
        result,
        "artifact_refs",
        rows(before, "artifact_refs")
        + [
            {
                "project_id": identity["project"],
                "owner_kind": "provider_call",
                "owner_id": identity["call"],
                "role": "budget_evidence",
                "artifact_id": evidence["id"],
            }
        ],
    )
    return result


def assert_evolution(before, after, identity, *, evidence=None, legacy_job=None, membership=None):
    expected = (
        expected_reserved(before, identity)
        if evidence is None
        else expected_settled(before, identity, evidence, legacy_job, membership)
    )
    equal(after, expected)


def source_rows_from_state(state):
    from ledger_provisioning_fixture import SOURCE_FIELDS

    return {
        table: [
            tuple(row[field] for field in fields)
            for row in sorted(
                rows(state, table),
                key=lambda row: (row["run_id"], row["step"]) if table == "events" else row["id"],
            )
        ]
        for table, fields in SOURCE_FIELDS.items()
    }


def assert_replay_preservation(before, after, original, returned, source, storage, current_storage):
    equal(after, before)
    equal(returned, original)
    equal(source, source_rows_from_state(before))
    equal(source_fingerprint(source), source_fingerprint(source_rows_from_state(after)))
    equal(current_storage, storage)


def file_bytes(manifest):
    checked = validate_ledger_manifest(manifest)
    plain = canonical(manifest)
    spaced = b" \t\r\n" + plain + b"\n\t "
    assert plain != spaced and len(spaced) <= 32768
    equal(checked.canonical_bytes, plain)
    return plain, spaced


def assert_clock_sample(sample, *, anchor=None):
    assert set(sample) == {
        "before",
        "after",
        "database",
        "sql",
        "role",
        "database_name",
        "connection_closed",
        "drained",
    }
    before, after = number(sample["before"]), number(sample["after"])
    assert before <= after <= before + 5
    instant(sample["database"])
    equal(sample["sql"], CLOCK_SQL)
    assert type(sample["role"]) is type(sample["database_name"]) is str
    assert sample["role"] and sample["database_name"]
    equal(sample["connection_closed"], True)
    equal(sample["drained"], True)
    if anchor is not None:
        delta = (instant(sample["database"]) - instant(anchor["database"])).total_seconds()
        assert max(0, before - anchor["after"] - 2) <= delta <= after - anchor["before"] + 2
        equal(sample["role"], anchor["role"])
        equal(sample["database_name"], anchor["database_name"])


def assert_expiry_clock(schedule, manifest, receipt, samples, m0_start, m0_end, replay_entry):
    assert 2 <= len(samples) <= 166
    anchor = samples[0]
    assert_clock_sample(anchor)
    a = anchor["before"]
    assert schedule["entered"] <= a <= schedule["entered"] + 20
    assert a <= schedule["started"] + 35
    assert anchor["after"] <= number(m0_start) <= a + 10
    assert number(m0_start) <= number(m0_end) <= a + 135
    start = instant(anchor["database"]) - timedelta(seconds=60)
    end = instant(anchor["database"]) + timedelta(seconds=150)
    selected = {
        manifest["opening_accounts"]["organization_account_id"],
        *(row["account_id"] for row in manifest["opening_accounts"]["projects"]),
    }
    periods = [row for row in manifest["accounts"] if row["id"] in selected]
    assert len(periods) == len(selected) == 2
    assert {row["scope"] for row in periods} == {"organization", "project"}
    for account in periods:
        equal(account["period_start"], timestamp(start))
        equal(account["period_end"], timestamp(end))
    assert start <= instant(receipt["initialized_at"]) < end
    previous = anchor
    for sample in samples[1:]:
        assert_clock_sample(sample, anchor=anchor)
        assert sample["before"] >= previous["after"] + 1
        assert instant(sample["database"]) >= instant(previous["database"])
        assert sample["after"] <= a + 165
        previous = sample
    assert samples[1]["before"] >= m0_end
    assert instant(samples[-1]["database"]) >= end
    assert samples[-1]["after"] <= number(replay_entry) <= a + 165
    assert replay_entry - samples[-1]["after"] <= 1
    admit_service(schedule, replay_entry, expired=True)
