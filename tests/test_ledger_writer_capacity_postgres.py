"""Two opt-in native capacity cases and explicitly selectable pure adapter controls."""

import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
import test_migrations_postgres as migration_tests
from ledger_eligibility_fixture import rows
from ledger_eligibility_postgres_fixture import admitted_predecessor
from ledger_overflow_postgres_fixture import raw_progress
from ledger_provisioning_fixture import canonical, digest
from ledger_provisioning_postgres_fixture import native_snapshot, progress_diagnostic
from ledger_recovery_postgres_fixture import fresh_reentry, observe_command
from ledger_restore_authority import typed
from ledger_source_boundary_postgres import assert_physical_completion, observe_native_source
from ledger_writer_capacity_fixture import SHAPES, assert_transition, expected_transition
from ledger_writer_capacity_postgres_fixture import (
    SHAPE_IDS,
    WRITE_HASHES,
    assert_expansion,
    assert_native_metadata,
    assert_progress,
    assert_upgrade,
    assert_write_records,
    assert_writer,
    capacity_manifest,
    capture_fresh_context,
    expand_predecessor,
    expansion_rows,
    observe_writer,
    preservation,
)
from sqlalchemy import BigInteger, Integer, String, bindparam, text
from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg
from test_ledger_service_postgres import controlled_database_name
from test_ledger_writer_capacity_controls import OBSERVED, ROLE, set_rows, witness
from test_run_projection_postgres import observed_reader

from agent_rewind.migrations import ledger_service, ledger_writer_sql
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import LEDGER, installed_profile

__all__ = ["controlled_database_name", "observed_reader"]
pg = migration_tests.pg


@pytest.mark.skipif(not migration_tests.POSTGRES, reason="Opt-in native PostgreSQL writer capacity")
@pytest.mark.parametrize("shape", SHAPES, ids=SHAPE_IDS)
def test_postgres_writer_capacity_initialization(
    pg, observed_reader, tmp_path, monkeypatch, record_property, shape
):
    def record(name, value):
        record_property(name, json.dumps(value, default=progress_diagnostic, allow_nan=False))

    fixture, admission = admitted_predecessor(pg, tmp_path, monkeypatch, record)
    try:
        record("admission_association", typed(admission.association))
        record("original_legacy_jobs", typed(admission.original_legacy_jobs))
        record(
            "admission_adapter",
            {
                "scope": admission.adapter_scope,
                "compatibility": admission.compatibility,
            },
        )
        (admitted,) = [
            row for row in rows(fixture.before, "jobs") if row["id"] == admission.accepted["job_id"]
        ]
        fixture, prior_progress = expand_predecessor(fixture, pg, shape, record)
        record("predecessor", typed(fixture.before))
        record("source_rows", typed(fixture.original))
        record("source_fingerprint", fixture.source)
        record("predecessor_stores", preservation(fixture, admission, pg))
        manifest = capacity_manifest(fixture)
        checked = validate_ledger_manifest(manifest)
        assert (
            checked.canonical_bytes == canonical(manifest) and len(checked.canonical_bytes) <= 32768
        )
        record("manifest", manifest)
        with (
            observe_command(
                fixture, pg, monkeypatch, record_property, label="initialization_write"
            ) as writer,
            observe_writer(writer, monkeypatch, record) as observed,
            observe_native_source(writer, monkeypatch, record) as (source, calls),
        ):
            receipt = ledger_service.initialize_ledger(writer.engine, checked)
        assert_physical_completion(writer, "commit")
        _, role, uid = observed["provenance"][0]["value"]
        expected = expected_transition(
            fixture.before,
            manifest,
            admission.original_legacy_jobs,
            admitted,
            initialized_at=receipt.initialized_at,
            database_role=role,
            os_uid=uid,
            original_project=fixture.project,
            raw_manifest=checked.canonical_bytes,
        )
        assert_writer(observed, source, calls, writer, fixture, manifest, expected)
        after = native_snapshot(fixture.case, pg)
        assert_native_metadata(fixture.before, after)
        assert_transition(
            expected, after, receipt.model_dump(mode="json"), observed["finalization"][0]["state"]
        )
        record("expected_transition", typed(expected))
        record("initialization_receipt", receipt.model_dump(mode="json"))
        record("writer_after", typed(after))
        current_progress = raw_progress(fixture, pg)
        sizes = assert_progress(prior_progress, current_progress, after, expected)
        record("progress", {"before": prior_progress, "after": current_progress, "sizes": sizes})
        record(
            "writer_metrics",
            {
                **expected["facts"],
                "observed_ordinary": writer.work.observed_ordinary,
                "conditional_forecast_ordinary": 1711 if shape == (15, 48) else 1708,
                "observer_units": writer.observer_units,
                "original_source_hashes": len(source["hashes"]),
                "original_initializations": 1,
            },
        )
        with capture_fresh_context(monkeypatch) as states:
            fresh_receipt, fresh = fresh_reentry(
                fixture, pg, manifest, monkeypatch, record_property, previous=writer
            )
        assert_physical_completion(fresh, "commit")
        assert fresh.work is not writer.work and fresh.engine is not writer.engine
        assert typed(states) == typed([expected["inspection"]])
        assert typed(fresh_receipt.model_dump(mode="json")) == typed(expected["inspection"]["head"])
        final = native_snapshot(fixture.case, pg)
        assert typed(final) == typed(after)
        assert typed(raw_progress(fixture, pg)) == typed(current_progress)
        record("fresh_context", states[0])
        record("fresh_receipt", fresh_receipt.model_dump(mode="json"))
        record(
            "final_preservation",
            {
                **preservation(fixture, admission, pg),
                "snapshot": typed(final),
                "watched_commands": ["initialization_write", "fresh_reentry"],
                "fresh_receipt_replays": 0,
            },
        )
    finally:
        fixture.close()


def adapter_case(shape):
    case = witness(shape)
    before = case["before"]
    fixture = SimpleNamespace(
        before=before,
        organization=rows(before, "organizations")[0]["id"],
        project=rows(before, "projects")[0]["id"],
        source=case["manifest"]["source_digest"],
        case=SimpleNamespace(adoption=rows(before, "installation_adoptions")[0]),
    )
    return case, fixture


@pytest.mark.parametrize("shape", SHAPES, ids=SHAPE_IDS)
def test_adapter_manifest_covers_every_original_and_admitted_job(shape):
    case, fixture = adapter_case(shape)
    result = capacity_manifest(fixture)
    assert len(result["accounts"]) == 64
    assert len(canonical(result)) <= 32768
    assert validate_ledger_manifest(result).canonical_bytes == canonical(result)
    accounts = result["accounts"]
    jobs = rows(case["before"], "jobs")
    scopes = {
        row["resource_id"]: row["project_id"] for row in rows(case["before"], "resource_scopes")
    }
    assert accounts[0]["limit_microusd"] == 245000
    projects = [row for row in accounts if row["scope"] == "project"]
    assert [row["limit_microusd"] for row in projects] == [245000] + [0] * (shape[0] - 1)
    actual = [
        (row["job_id"], row["project_id"], row["limit_microusd"])
        for row in accounts
        if row["scope"] == "job"
    ]
    assert typed(actual) == typed(
        [
            (row["id"], scopes[row["id"]], row["budget"])
            for row in sorted(jobs, key=lambda row: row["id"])
        ]
    )
    assert len({row["id"] for row in accounts}) == 64


def native_metadata_witness():
    # Literal expected authority additions: independent of the adapter's set.
    old = {
        "role": ROLE,
        "authority": {
            "schema": (("public", ROLE, None),),
            "relations": (("jobs", ROLE, None),),
            "functions": (("existing_function", "", ROLE, None),),
        },
    }
    new = deepcopy(old)
    new["catalog"] = installed_profile("postgresql", LEDGER)
    names = (
        "ar7_accounts_job_window",
        "ar7_accounts_pk",
        "ar7_accounts_scope_period",
        "ar7_calls_job_account_id",
        "ar7_calls_job_id",
        "ar7_calls_logical_unique",
        "ar7_calls_organization_account_id",
        "ar7_calls_pk",
        "ar7_calls_project_account_id",
        "ar7_calls_project_unique",
        "ar7_entries_account_id",
        "ar7_entries_pk",
        "budget_accounts",
        "budget_entries",
        "provider_calls",
    )
    new["authority"]["relations"] = tuple(
        sorted((*old["authority"]["relations"], *((name, ROLE, None) for name in names)))
    )
    new["authority"]["functions"] = (
        ("ar7_ledger_constraint", "", ROLE, "{" + ROLE + "=X/" + ROLE + "}"),
        *old["authority"]["functions"],
    )
    return old, new


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "owner",
        "old-acl",
        "new-acl",
        "missing-index",
        "extra-index",
        "public-execute",
        "extra-function",
        "old-function",
        "schema",
        "catalog",
    ],
)
def test_adapter_native_metadata_is_exact(fault):
    before, after = native_metadata_witness()
    relations = list(after["authority"]["relations"])
    functions = list(after["authority"]["functions"])
    if fault == "owner":
        after["role"] = "another"
    elif fault == "old-acl":
        relations = [
            (name, owner, "changed" if name == "jobs" else acl) for name, owner, acl in relations
        ]
    elif fault == "new-acl":
        relations[0] = (*relations[0][:2], "{public=r}")
    elif fault == "missing-index":
        relations.pop(0)
    elif fault == "extra-index":
        relations.append(("unexpected", ROLE, None))
    elif fault == "public-execute":
        functions[0] = (*functions[0][:3], "{=X/" + ROLE + "}")
    elif fault == "extra-function":
        functions.append(("extra", "", ROLE, None))
    elif fault == "old-function":
        functions[-1] = (*functions[-1][:2], "changed", None)
    elif fault == "schema":
        after["authority"]["schema"] = ()
    elif fault == "catalog":
        del after["catalog"]["jobs"]
    after["authority"]["relations"] = tuple(relations)
    after["authority"]["functions"] = tuple(functions)
    if fault is None:
        assert_native_metadata(before, after)
    else:
        with pytest.raises(AssertionError):
            assert_native_metadata(before, after)


def independent_write_records(case):
    """Observations from the independent S1 witness, not expected_writes()."""
    result = []
    jobs = sorted(rows(case["before"], "jobs"), key=lambda row: row["id"])
    for row in jobs:
        result.append(
            {
                "name": "jobs.backfill",
                "values": {"id": row["id"], "opening": row["reserved"]},
                "rowcount": 1,
            }
        )
    # Witness accounts already contain independently assigned literal balances.
    accounts = {row["id"]: row for row in rows(case["after"], "budget_accounts")}
    for declaration in case["manifest"]["accounts"]:
        stored = accounts[declaration["id"]]
        result.append(
            {
                "name": "accounts.insert",
                "values": {
                    **declaration,
                    "opening_held_microusd": stored["opening_held_microusd"],
                    "held_microusd": stored["held_microusd"],
                    "accounted_microusd": stored["accounted_microusd"],
                },
                "rowcount": 1,
            }
        )
    progress = {
        row["phase"]: row
        for row in rows(case["after"], "migration_progress")
        if row["revision"] == LEDGER
    }
    for key in ("ledger_manifest_" + case["manifest"]["manifest_id"], "ledger_opening"):
        row = deepcopy(progress[key])
        row["cursor"] = json.dumps(
            row["cursor"], sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        row["updated_at"] = OBSERVED
        result.append({"name": "progress.insert", "values": row, "rowcount": 1})
    result.append(
        {
            "name": "adoption.publish_fingerprint",
            "values": {
                "fingerprint": digest(installed_profile("postgresql", LEDGER)),
                "installation_key": case["manifest"]["installation_key"],
                "previous_fingerprint": rows(case["before"], "installation_adoptions")[0][
                    "installed_schema_fingerprint"
                ],
            },
            "rowcount": 1,
        }
    )
    return result


@pytest.mark.parametrize("shape", SHAPES, ids=SHAPE_IDS)
@pytest.mark.parametrize(
    "fault",
    [
        None,
        "missing",
        "duplicate",
        "bool-rowcount",
        "zero-rowcount",
        "float-money",
        "admitted-opening",
        "project-inflation",
        "cursor",
        "previous-fingerprint",
    ],
)
def test_adapter_write_values_bind_every_returned_target(shape, fault):
    case = witness(shape)
    expected = {
        "tables": case["after"]["tables"],
        "inspection": case["inspection"],
        "receipt": case["receipt"],
    }
    records = independent_write_records(case)
    if fault == "missing":
        records.pop(3)
    elif fault == "duplicate":
        records[3] = deepcopy(records[2])
    elif fault == "bool-rowcount":
        records[0]["rowcount"] = True
    elif fault == "zero-rowcount":
        records[-1]["rowcount"] = 0
    elif fault == "float-money":
        records[0]["values"]["opening"] = float(records[0]["values"]["opening"])
    elif fault == "admitted-opening":
        records[3]["values"]["opening"] = 1
    elif fault == "project-inflation":
        records[shape[1] + 2]["values"]["held_microusd"] = 245000
    elif fault == "cursor":
        records[-2]["values"]["cursor"] += " "
    elif fault == "previous-fingerprint":
        records[-1]["values"]["previous_fingerprint"] = "0" * 64
    if fault is None:
        assert_write_records(records, case["before"], case["manifest"], expected)
    else:
        with pytest.raises(AssertionError):
            assert_write_records(records, case["before"], case["manifest"], expected)


@pytest.mark.parametrize("name", tuple(WRITE_HASHES))
def test_adapter_historical_query_hash_matches_original_compiler(name):
    types = {"String": String, "BigInteger": BigInteger, "Integer": Integer}
    statement = text(ledger_writer_sql.SQL[("postgresql", name)]).bindparams(
        *(
            bindparam(key, type_=types[value])
            for key, value in ledger_writer_sql.PARAMETER_TYPES[("postgresql", name)].items()
        )
    )
    query = str(statement.compile(dialect=PGDialect_psycopg()))
    assert hashlib.sha256(query.encode()).hexdigest() == WRITE_HASHES[name]
    assert hashlib.sha256(query.rstrip().encode()).hexdigest() != WRITE_HASHES[name]


@pytest.mark.parametrize("shape", SHAPES, ids=SHAPE_IDS)
@pytest.mark.parametrize(
    "fault", [None, "old-progress", "duplicate", "missing", "float-count", "extra", "oversize"]
)
def test_adapter_raw_progress_preserves_old_rows_and_typed_cursors(shape, fault):
    case = witness(shape)
    before = [
        {
            "revision": row["revision"],
            "phase": row["phase"],
            "raw_cursor": json.dumps(row["cursor"]),
        }
        for row in rows(case["before"], "migration_progress")
    ]
    after = before + [
        {
            "revision": row["revision"],
            "phase": row["phase"],
            "raw_cursor": json.dumps(row["cursor"]),
        }
        for row in rows(case["after"], "migration_progress")
        if row["revision"] == LEDGER
    ]
    if fault == "old-progress":
        after[0] = {**after[0], "raw_cursor": "{}"}
    elif fault == "duplicate":
        after.append(deepcopy(after[-1]))
    elif fault == "missing":
        after.pop()
    elif fault == "float-count":
        value = json.loads(after[-1]["raw_cursor"])
        value["job_count"] = float(value["job_count"])
        after[-1]["raw_cursor"] = json.dumps(value)
    elif fault == "extra":
        after.append({"revision": LEDGER, "phase": "unexpected", "raw_cursor": "{}"})
    elif fault == "oversize":
        after[-1]["raw_cursor"] += " " * 65536
    if fault is None:
        sizes = assert_progress(before, after, case["after"], {"receipt": case["receipt"]})
        assert len(sizes) == 2
    else:
        with pytest.raises(AssertionError):
            assert_progress(before, after, case["after"], {"receipt": case["receipt"]})


def test_adapter_fresh_context_is_passive(monkeypatch):
    expected = {"status": "complete", "account_count": 64}
    calls = []
    context = SimpleNamespace(state=SimpleNamespace(model_dump=lambda **kwargs: deepcopy(expected)))

    def original(connection):
        calls.append(connection)
        return context

    monkeypatch.setattr(ledger_service, "_inspect_ledger_context", original)
    connection = object()
    with capture_fresh_context(monkeypatch) as states:
        assert ledger_service._inspect_ledger_context(connection) is context
    assert calls == [connection] and states == [expected]
    assert ledger_service._inspect_ledger_context is original


@pytest.mark.parametrize("shape", SHAPES, ids=SHAPE_IDS)
@pytest.mark.parametrize("fault", [None, "old-cell", "admitted", "missing-scope", "extra-cell"])
def test_adapter_expansion_preserves_entire_predecessor(shape, fault):
    case = witness(shape)
    before = deepcopy(case["before"])
    # Reduce the independent witness to the actual producer's four-job starting shape.
    original = rows(before, "projects")[0]
    set_rows(before, "projects", [original])
    jobs = rows(before, "jobs")[:4]
    set_rows(before, "jobs", jobs)
    set_rows(
        before,
        "resource_scopes",
        [
            {"resource_kind": "job", "resource_id": row["id"], "project_id": original["id"]}
            for row in jobs
        ],
    )
    additions = expansion_rows(before, original["id"], shape)
    after = deepcopy(before)
    # Independent observation packing deliberately does not call table_value.
    for name, values in additions.items():
        columns = after["tables"][name]["columns"]
        after["tables"][name]["rows"] = tuple(
            sorted(
                [
                    *after["tables"][name]["rows"],
                    *(tuple(deepcopy(row[c]) for c in columns) for row in values),
                ],
                key=repr,
            )
        )
    if fault == "old-cell":
        after["tables"]["records"]["rows"] = ()
    elif fault == "admitted":
        changed = rows(after, "jobs")
        next(row for row in changed if row["id"] == jobs[3]["id"])["reserved"] = 1
        set_rows(after, "jobs", changed)
    elif fault == "missing-scope":
        after["tables"]["resource_scopes"]["rows"] = after["tables"]["resource_scopes"]["rows"][:-1]
    elif fault == "extra-cell":
        after["tables"]["projects"]["columns"] += ("extra",)
    if fault is None:
        assert_expansion(before, after, additions)
        assert len(rows(after, "projects")) == shape[0] and len(rows(after, "jobs")) == shape[1]
    else:
        with pytest.raises(AssertionError):
            assert_expansion(before, after, additions)


@pytest.mark.parametrize("misplaced", [False, True])
def test_adapter_upgrade_reflection_bind_is_first(misplaced):
    # Retained SQL strings are independent of the adapter's expected bind list.
    from test_ledger_precommit_boundary_postgres_controls import UPGRADE_SQL

    reflection = {
        "table_names_1": "alembic_version",
        "param_1": "r",
        "param_2": "p",
        "param_3": "f",
        "param_4": "v",
        "param_5": "m",
        "nspname_1": "pg_catalog",
    }
    events, calls = [], []
    for index, query in enumerate(UPGRADE_SQL):
        parameters = reflection if index == (1 if misplaced else 0) else {}
        for sql, values in (
            ("SET LOCAL statement_timeout = '20000ms'", None),
            ("SET LOCAL lock_timeout = '5000ms'", None),
            (query, parameters),
        ):
            position = len(events)
            events += [("ordinary", "sql-call", 101, sql), ("ordinary", "sql-return", 101, sql)]
            calls.append(
                {
                    "entered_at": position,
                    "returned_at": position + 2,
                    "raw_id": 101,
                    "phase": "ordinary",
                    "sql": sql,
                    "parameters": values,
                    "outcome": "return",
                }
            )
    entry = {"entered_at": 0, "returned_at": len(events), "work_before": 50, "work_after": 89}
    if misplaced:
        with pytest.raises(AssertionError):
            assert_upgrade(entry, events, calls, 101, 5)
    else:
        assert_upgrade(entry, events, calls, 101, 5)
