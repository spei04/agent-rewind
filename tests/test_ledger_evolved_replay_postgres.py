"""Two opt-in PostgreSQL evolved old-receipt cases; never clock or ledger overrides."""

import hashlib
import json
import os
import sys
import time
from dataclasses import asdict
from types import SimpleNamespace

import ledger_eligibility_postgres_fixture as admission_helpers
import pytest
import test_migrations_postgres as migration_tests
from cryptography.fernet import Fernet
from ledger_account_identity_fixture import assert_admission_delta, assert_stores, job_intents
from ledger_account_identity_postgres_fixture import expected_native_first
from ledger_accounted_carry_postgres_fixture import assert_raw_progress
from ledger_accounted_carry_postgres_observer import financial_projection
from ledger_eligibility_fixture import file_hashes, rows
from ledger_evolved_replay_fixture import (
    CASES,
    CLOCK_SQL,
    EVIDENCE,
    SETTLEMENT,
    admit_service,
    assert_clock_sample,
    assert_completion,
    assert_evolution,
    assert_expiry_clock,
    assert_replay_preservation,
    cohort,
    dispatch,
    equal,
    expiry_initial,
    file_bytes,
    instant,
    mixed_initial,
    reservation_rows,
    source_rows_from_state,
    timestamp,
)
from ledger_evolved_replay_observer import anchor, assert_observation, observe_replay
from ledger_overflow_postgres_fixture import raw_progress
from ledger_provisioning_fixture import expected_stage, source_fingerprint
from ledger_provisioning_postgres_fixture import (
    assert_stage,
    build_postgres_case,
    encrypted_files,
    inspect,
    native_snapshot,
    progress_diagnostic,
)
from ledger_recovery_postgres_fixture import observe_command
from ledger_restore_authority import typed
from ledger_source_boundary_postgres import assert_physical_completion
from sqlalchemy import BigInteger, DateTime, bindparam, text
from test_admission_envelope import descriptor
from test_ledger_service_postgres import controlled_database_name
from test_run_projection_postgres import drain, observed_reader

from agent_rewind.artifact_metadata import record_verified, register_ref
from agent_rewind.artifact_storage import LocalArtifactStorage
from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import read_ledger_manifest, validate_ledger_manifest

__all__ = ["controlled_database_name", "observed_reader"]
pg = migration_tests.pg

PROPERTY_CONTRACT = {
    CASES[0]: (
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
        "reserved_service",
        "reserved_observation",
        "reserved_result",
        "settled_setup",
        "canonical_service",
        "canonical_observation",
        "canonical_result",
        "whitespace_service",
        "whitespace_observation",
        "whitespace_result",
        "final_preservation",
    ),
    CASES[1]: (
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
        "expired_service",
        "expired_observation",
        "expired_result",
        "final_preservation",
    ),
}


def recorder(record_property):
    def record(name, value):
        record_property(name, json.dumps(value, default=progress_diagnostic, allow_nan=False))

    return record


def entry(record, case):
    schedule = dispatch(os.environ.get("AR_R1_CHILD_STARTED_MONOTONIC"), time.monotonic())
    record("replay_case", case)
    record("schedule", schedule)
    return schedule


def finish_case(fixture, schedule, record, final, proof_finished, failure):
    """Always close; earlier failure remains primary even if cleanup also fails."""
    cleanup_started = time.monotonic()
    cleanup_error = None
    try:
        fixture.close()
    except BaseException as error:
        cleanup_error = error
    timing = {
        "proof_finished": proof_finished,
        "cleanup_started": cleanup_started,
        "cleanup_finished": time.monotonic(),
    }
    if failure is not None or cleanup_error is not None:
        record(
            "completion_diagnostic",
            {
                "timing": timing,
                "full_case_complete": False,
                "earlier_error": None if failure is None else type(failure).__name__,
                "cleanup_error": None if cleanup_error is None else type(cleanup_error).__name__,
            },
        )
        if failure is not None:
            if cleanup_error is not None:
                failure.add_note(
                    "Local fixture cleanup also failed: " + type(cleanup_error).__name__
                )
            return
        raise cleanup_error
    assert final is not None
    record("final_preservation", {**final, "completion": timing})
    assert_completion(schedule, timing)


def initialized(fixture, pg, first, schedule, monkeypatch, record_property, record):
    record("M0_manifest", first)
    started = time.monotonic()
    admit_service(schedule, started)
    with observe_command(fixture, pg, monkeypatch, record_property, label="M0_service") as watch:
        receipt = ledger_service.initialize_ledger(watch.engine, validate_ledger_manifest(first))
    assert_physical_completion(watch, "commit")
    equal(watch.work.timeout_seconds, 5)
    stages = []
    assert_stage(
        fixture,
        pg,
        [first],
        [receipt],
        record_property=lambda name, value: stages.append(
            {"name": name, "value": json.loads(value)}
        ),
        observation="M0",
    )
    result = admission_helpers.refreshed(fixture, pg)
    admission_helpers.assert_typed_initialization(fixture, pg, first, receipt, result.before)
    finished = time.monotonic()
    record("M0_stage", {"records": stages, "started": started, "finished": finished})
    record("M0_receipt", receipt.model_dump(mode="json"))
    record("M0_state", typed(result.before))
    return result, receipt, started, finished


def stored(fixture, admission=None, settlement=None):
    result = {"legacy": encrypted_files(fixture), "objects": {}, "journal": {}, "settlement": {}}
    if admission is not None:
        assert_stores(fixture, admission, result["legacy"])
        for value in admission.descriptors:
            assert (
                hashlib.sha256(admission.storage.read_verified(value)).hexdigest() == value.digest
            )
        result.update(
            objects=file_hashes(admission.objects), journal=file_hashes(admission.journal)
        )
    if settlement is not None:
        equal(settlement.storage.read_verified(settlement.descriptor), SETTLEMENT)
        result["settlement"] = file_hashes(settlement.root)
    return result


def typed_statement(sql, values):
    statement = text(sql)
    for key, value in values.items():
        if type(value).__name__ == "datetime":
            statement = statement.bindparams(bindparam(key, type_=DateTime(timezone=True)))
        elif type(value) is int:
            statement = statement.bindparams(bindparam(key, type_=BigInteger))
    return statement


def producer(fixture, pg, identity, base, *, settlement=None, legacy_job=None, membership=None):
    """Explicit owner-only synthetic SQL, outside every watched service slot."""
    before = native_snapshot(fixture.case, pg)
    updates = []
    started = time.monotonic()
    try:
        with fixture.case.engine.begin() as connection:
            connection.exec_driver_sql("SET LOCAL statement_timeout='2000ms'")
            connection.exec_driver_sql("SET LOCAL lock_timeout='1000ms'")
            owner = tuple(
                connection.exec_driver_sql("SELECT current_user,current_database()").one()
            )
            equal(owner, (pg["owner_role"], pg["owner"].url.database))

            def execute(sql, values, count=1):
                assert time.monotonic() - started < 30
                result = connection.execute(typed_statement(sql, values), values)
                updates.append(
                    {"sql": sql, "parameters": typed(values), "rowcount": result.rowcount}
                )
                equal(result.rowcount, count)
                result.close()

            def insert(table, value):
                assert table in {"provider_calls", "resource_scopes", "budget_entries"}
                execute(
                    f"INSERT INTO {table} ({','.join(value)}) VALUES "
                    f"({','.join(':' + key for key in value)})",
                    value,
                )

            if settlement is None:
                equal(before, base)
                for table, values in reservation_rows(identity).items():
                    for value in values:
                        insert(table, value)
                execute(
                    "UPDATE budget_accounts SET held_microusd=held_microusd+1 "
                    "WHERE id IN (:organization,:project,:job)",
                    dict(
                        zip(("organization", "project", "job"), identity["accounts"], strict=True)
                    ),
                    3,
                )
                execute(
                    "UPDATE jobs SET status='running',owner='synthetic-worker',"
                    "lease_until=:lease,lease_generation=2,reserved=1 WHERE id=:job",
                    {"lease": identity["lease_until"], "job": identity["job"]},
                )
            else:
                assert_evolution(base, before, identity)
                evidence = settlement.descriptor
                record_verified(connection, evidence)
                register_ref(
                    connection,
                    project_id=identity["project"],
                    owner_kind="provider_call",
                    owner_id=identity["call"],
                    role="budget_evidence",
                    artifact_id=evidence.id,
                )
                for value in reservation_rows(identity)["budget_entries"]:
                    insert(
                        "budget_entries",
                        {**value, "entry_kind": "settle", "evidence_ref": evidence.id},
                    )
                execute(
                    "UPDATE provider_calls SET state='reconciled' WHERE id=:id",
                    {"id": identity["call"]},
                )
                execute(
                    "UPDATE budget_accounts SET held_microusd=held_microusd-1,accounted_microusd=1 "
                    "WHERE id IN (:organization,:project,:job)",
                    dict(
                        zip(("organization", "project", "job"), identity["accounts"], strict=True)
                    ),
                    3,
                )
                execute("UPDATE jobs SET budget=budget+1 WHERE id=:id", {"id": legacy_job})
                execute(
                    "DELETE FROM project_memberships WHERE project_id=:project "
                    "AND principal_id=:principal",
                    {"project": membership[0], "principal": membership[1]},
                )
            connection.exec_driver_sql("SET CONSTRAINTS ALL IMMEDIATE")
        committed = True
    finally:
        drain(pg)
    assert time.monotonic() - started <= 30
    current = admission_helpers.refreshed(fixture, pg)
    evidence = None if settlement is None else asdict(settlement.descriptor)
    assert_evolution(
        base,
        current.before,
        identity,
        evidence=evidence,
        legacy_job=legacy_job,
        membership=membership,
    )
    return current, {
        "synthetic": True,
        "owner": owner,
        "commit_acknowledged": committed,
        "constraints_immediate": True,
        "updates": updates,
        "metadata_helpers": [] if settlement is None else ["record_verified", "register_ref"],
        "before": typed(before),
        "after": typed(current.before),
        "source": typed(current.original),
        "source_fingerprint": current.source,
        "seconds": time.monotonic() - started,
    }


def replay(
    fixture,
    pg,
    manifest,
    path,
    original,
    state,
    schedule,
    monkeypatch,
    record_property,
    record,
    label,
    *,
    admission=None,
    settlement=None,
    expired=False,
    clock_gate=None,
):
    before = native_snapshot(fixture.case, pg)
    source = source_rows_from_state(before)
    _, financial = financial_projection(before)
    storage = stored(fixture, admission, settlement)
    checked = read_ledger_manifest(path)
    equal(checked.model_dump(mode="json"), manifest)
    if clock_gate is not None:
        clock_gate()
    entered = time.monotonic()
    admit_service(schedule, entered, expired=expired)
    with (
        observe_command(
            fixture, pg, monkeypatch, record_property, label=label + "_service", observe_writes=True
        ) as watch,
        observe_replay(
            watch, monkeypatch, lambda name, value: record(label + "_" + name, value)
        ) as observed,
    ):
        returned = ledger_service.initialize_ledger(watch.engine, checked)
    assert_physical_completion(watch, "commit")
    equal(watch.work.timeout_seconds, 5)
    watch.assert_no_writes()
    original_value = original.model_dump(mode="json")
    assert_observation(
        observed, manifest, original_value, state, anchor(watch), len(watch.trace.events), financial
    )
    after = native_snapshot(fixture.case, pg)
    current_storage = stored(fixture, admission, settlement)
    assert_replay_preservation(
        before,
        after,
        original_value,
        returned.model_dump(mode="json"),
        source,
        storage,
        current_storage,
    )
    assert time.monotonic() <= schedule["started"] + 340
    result = {
        "started": entered,
        "finished": time.monotonic(),
        "original": original_value,
        "returned": returned.model_dump(mode="json"),
        "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "input_bytes": len(path.read_bytes()),
        "canonical_sha256": checked.digest,
        "before": typed(before),
        "after": typed(after),
        "source": typed(source),
        "source_fingerprint": source_fingerprint(source),
        "stores_before": storage,
        "stores_after": current_storage,
        "current_state": state,
        "identity": anchor(watch),
    }
    record(label + "_result", result)
    return result


@pytest.mark.skipif(
    "AR_R1_CHILD_STARTED_MONOTONIC" not in os.environ,
    reason="Requires reviewed R1 bounded runner; ordinary CI gives no native coverage",
)
@pytest.mark.skipif(not migration_tests.POSTGRES, reason="Opt-in evolved PostgreSQL receipt replay")
def test_postgres_evolved_original_and_whitespace_replay(
    pg, observed_reader, tmp_path, monkeypatch, record_property
):
    record = recorder(record_property)
    schedule = entry(record, CASES[0])
    fixture = build_postgres_case(pg)
    final = proof_finished = None
    try:
        record("original_predecessor", typed(fixture.before))
        first = mixed_initial(fixture)
        initial, receipt, _, _ = initialized(
            fixture, pg, first, schedule, monkeypatch, record_property, record
        )
        setup = []
        evolved, admission = admission_helpers.admit_existing_fixture(
            initial,
            pg,
            tmp_path,
            monkeypatch,
            lambda name, value: setup.append({"name": name, "value": value}),
        )
        assert_admission_delta(initial.before, evolved.before, admission, fixture.project)
        record(
            "admission_setup",
            {
                "records": setup,
                "association": typed(admission.association),
                "before": typed(initial.before),
                "after": typed(evolved.before),
                "stores": stored(evolved, admission),
            },
        )
        one, _ = job_intents(evolved, first, admission.accepted["job_id"])
        record("M1_manifest", one)
        previous_progress = raw_progress(evolved, pg)
        admit_service(schedule, time.monotonic())
        with observe_command(
            evolved, pg, monkeypatch, record_property, label="M1_service"
        ) as watch:
            written = ledger_service.initialize_ledger(watch.engine, validate_ledger_manifest(one))
        assert_physical_completion(watch, "commit")
        equal(watch.work.timeout_seconds, 5)
        expected, state = expected_native_first(
            fixture, first, receipt, evolved.before, one, written, pg["owner_role"]
        )
        base = native_snapshot(fixture.case, pg)
        equal(base, expected)
        equal(inspect(evolved, pg).model_dump(mode="json"), state)
        current_progress = raw_progress(evolved, pg)
        assert_raw_progress(
            previous_progress, current_progress, "ledger_manifest_" + one["manifest_id"]
        )
        record(
            "M1_stage",
            {
                "progress_before": previous_progress,
                "progress_after": current_progress,
                "whole_inspection": state,
                "expected": typed(expected),
            },
        )
        record("M1_receipt", written.model_dump(mode="json"))
        record("M1_state", typed(base))
        identity = cohort(
            base,
            first,
            one,
            admission.accepted["job_id"],
            json.loads(admission.config.canonical_bytes)["price_version"],
            written.initialized_at,
        )
        record("cohort", identity)
        plain, whitespace = file_bytes(first)
        original_file, whitespace_file = tmp_path / "M0.json", tmp_path / "M0-whitespace.json"
        for path, payload in ((original_file, plain), (whitespace_file, whitespace)):
            path.write_bytes(payload)
            path.chmod(0o600)
        admit_service(schedule, time.monotonic())
        reserved, setup = producer(evolved, pg, identity, base)
        equal(inspect(reserved, pg).model_dump(mode="json"), state)
        equal(native_snapshot(fixture.case, pg), reserved.before)
        record("reserved_setup", setup)
        replay(
            reserved,
            pg,
            first,
            original_file,
            receipt,
            state,
            schedule,
            monkeypatch,
            record_property,
            record,
            "reserved",
            admission=admission,
        )
        admit_service(schedule, time.monotonic())
        root = tmp_path / "settlement"
        root.mkdir(mode=0o700)
        storage = LocalArtifactStorage(root, Fernet(Fernet.generate_key()), plaintext_limit=4096)
        evidence = descriptor(SETTLEMENT, object_id=EVIDENCE, project=fixture.project)
        assert storage.put_verified(evidence, SETTLEMENT).object == evidence
        settlement = SimpleNamespace(root=root, storage=storage, descriptor=evidence)
        legacy_job = sorted(row["id"] for row in rows(base, "jobs") if row["payload_version"] == 1)[
            0
        ]
        member = rows(base, "project_memberships")[0]
        membership = (member["project_id"], member["principal_id"])
        settled, setup = producer(
            evolved,
            pg,
            identity,
            base,
            settlement=settlement,
            legacy_job=legacy_job,
            membership=membership,
        )
        setup.update(
            evidence=typed(asdict(evidence)),
            legacy_job=legacy_job,
            membership=list(membership),
            settlement_hashes=file_hashes(root),
        )
        equal(inspect(settled, pg).model_dump(mode="json"), state)
        equal(native_snapshot(fixture.case, pg), settled.before)
        record("settled_setup", setup)
        canonical_result = replay(
            settled,
            pg,
            first,
            original_file,
            receipt,
            state,
            schedule,
            monkeypatch,
            record_property,
            record,
            "canonical",
            admission=admission,
            settlement=settlement,
        )
        whitespace_result = replay(
            settled,
            pg,
            first,
            whitespace_file,
            receipt,
            state,
            schedule,
            monkeypatch,
            record_property,
            record,
            "whitespace",
            admission=admission,
            settlement=settlement,
        )
        assert canonical_result["input_sha256"] != whitespace_result["input_sha256"]
        equal(canonical_result["canonical_sha256"], whitespace_result["canonical_sha256"])
        equal(canonical_result["after"], whitespace_result["after"])
        final = {
            "state": typed(native_snapshot(fixture.case, pg)),
            "source": typed(settled.original),
            "source_fingerprint": settled.source,
            "stores": stored(settled, admission, settlement),
            "watched_services": 5,
            "receipt_replays": 3,
            "synthetic_producer_commits": 2,
        }
        proof_finished = time.monotonic()
    finally:
        finish_case(fixture, schedule, record, final, proof_finished, sys.exception())


def clock_sample(fixture, pg):
    """One separately attributed read-only setup connection; no open wait transaction."""
    before = time.monotonic()
    try:
        with fixture.case.engine.connect() as connection:
            connection.exec_driver_sql("SET LOCAL statement_timeout='2000ms'")
            connection.exec_driver_sql("SET LOCAL lock_timeout='1000ms'")
            value, role, database = connection.exec_driver_sql(CLOCK_SQL).one()
            equal((role, database), (pg["owner_role"], pg["owner"].url.database))
        closed = connection.closed
    finally:
        drain(pg)
    sample = {
        "before": before,
        "after": time.monotonic(),
        "database": timestamp(value),
        "sql": CLOCK_SQL,
        "role": role,
        "database_name": database,
        "connection_closed": closed,
        "drained": True,
    }
    assert_clock_sample(sample)
    return sample


@pytest.mark.skipif(
    "AR_R1_CHILD_STARTED_MONOTONIC" not in os.environ,
    reason="Requires reviewed R1 bounded runner; ordinary CI gives no native coverage",
)
@pytest.mark.skipif(not migration_tests.POSTGRES, reason="Opt-in real PostgreSQL opening expiry")
def test_postgres_expired_opening_original_replay(
    pg, observed_reader, tmp_path, monkeypatch, record_property
):
    record = recorder(record_property)
    schedule = entry(record, CASES[1])
    fixture = build_postgres_case(pg)
    samples = []
    complete = False
    final = proof_finished = None
    try:
        record("original_predecessor", typed(fixture.before))
        assert time.monotonic() <= schedule["entered"] + 20
        samples.append(clock_sample(fixture, pg))
        a = samples[0]["before"]
        assert a <= schedule["started"] + 35
        record("clock_anchor", samples[0])
        first = expiry_initial(fixture, samples[0]["database"])
        assert time.monotonic() <= a + 10
        initialized_fixture, receipt, m0_start, m0_end = initialized(
            fixture, pg, first, schedule, monkeypatch, record_property, record
        )
        assert m0_end <= a + 135
        _, _, state = expected_stage(fixture, [first], [receipt], database_role=pg["owner_role"])
        plain, _ = file_bytes(first)
        original = tmp_path / "M0.json"
        original.write_bytes(plain)
        original.chmod(0o600)
        end = max(
            instant(row["period_end"])
            for row in first["accounts"]
            if row["scope"] in {"organization", "project"}
        )
        while len(samples) < 165:
            assert time.monotonic() < a + 165
            delay = max(0.0, samples[-1]["after"] + 1 - time.monotonic())
            if delay:
                time.sleep(delay)
            sample = clock_sample(fixture, pg)
            assert_clock_sample(sample, anchor=samples[0])
            assert instant(sample["database"]) >= instant(samples[-1]["database"])
            samples.append(sample)
            if instant(sample["database"]) >= end:
                break

        def final_clock_gate():
            # Snapshot/file preflight cannot make the final clock observation stale.
            delay = max(0.0, samples[-1]["after"] + 1 - time.monotonic())
            if delay:
                time.sleep(delay)
            assert len(samples) < 166 and time.monotonic() < a + 165
            samples.append(clock_sample(fixture, pg))
            entered = time.monotonic()
            assert_expiry_clock(
                schedule, first, receipt.model_dump(mode="json"), samples, m0_start, m0_end, entered
            )
            record(
                "expiry_clock",
                {
                    "samples": samples,
                    "M0_start": m0_start,
                    "M0_end": m0_end,
                    "replay_admitted": entered,
                    "wait_transaction_open": False,
                },
            )

        result = replay(
            initialized_fixture,
            pg,
            first,
            original,
            receipt,
            state,
            schedule,
            monkeypatch,
            record_property,
            record,
            "expired",
            expired=True,
            clock_gate=final_clock_gate,
        )
        assert result["started"] <= a + 165
        assert result["started"] - samples[-1]["after"] <= 1
        final = {
            "state": typed(native_snapshot(fixture.case, pg)),
            "source": typed(fixture.original),
            "source_fingerprint": fixture.source,
            "stores": stored(fixture),
            "watched_services": 2,
            "receipt_replays": 1,
            "synthetic_producer_commits": 0,
        }
        proof_finished = time.monotonic()
        complete = True
    finally:
        # Partial samples survive without authorizing replay or retry.
        if samples and not complete:
            record("clock_diagnostic", {"samples": samples, "complete": len(samples) >= 2})
        finish_case(fixture, schedule, record, final, proof_finished, sys.exception())
