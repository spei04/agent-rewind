"""Ordinary SQLite original-service replay after evolution and real opening expiry."""

import hashlib
import json
import os
import sqlite3
import sys
import time
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
from types import SimpleNamespace

from cryptography.fernet import Fernet
from ledger_account_identity_fixture import (
    assert_admission_delta,
    assert_stores,
    expected_first,
    job_intents,
)
from ledger_accounted_carry_fixture import replace_rows
from ledger_accounted_carry_observer import assert_commit
from ledger_accounted_carry_postgres_observer import FINANCIAL_TABLES, TIME_FIELDS
from ledger_eligibility_fixture import (
    admission_engine,
    admit_existing_fixture,
    file_hashes,
    refreshed,
    rows,
)
from ledger_evolved_replay_fixture import (
    CASES,
    EVIDENCE,
    SETTLEMENT,
    SQLITE_CLOCK_SQL,
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
)
from ledger_evolved_replay_observer import (
    anchor,
    assert_observation,
    observe_replay,
    replay_financial,
)
from ledger_provisioning_fixture import (
    assert_no_writes,
    assert_stage,
    build_case,
    ciphertexts,
    expected_stage,
    inspect,
    native_actions,
    reader,
    snapshot,
)
from ledger_recovery_fixture import observe_command
from ledger_restore_authority import typed
from sqlalchemy import text
from test_admission_configuration import configuration
from test_admission_envelope import descriptor

from agent_rewind.artifact_metadata import record_verified, register_ref
from agent_rewind.artifact_storage import LocalArtifactStorage
from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import read_ledger_manifest, validate_ledger_manifest


def begin(record_property, case):
    entered = time.monotonic()
    external = os.environ.get("AR_R1_CHILD_STARTED_MONOTONIC")
    schedule = dispatch(str(entered) if external is None else external, entered)

    def record(name, value):
        record_property(name, json.dumps(typed(value), allow_nan=False))

    record("replay_case", case)
    record("schedule", {**schedule, "origin": "function-entry" if external is None else "child"})
    return schedule, record


def finish(fixture, schedule, record, proof, failure):
    """Retain the original service/assertion error when local cleanup also fails."""
    started = time.monotonic()
    cleanup_error = None
    try:
        fixture.close()
    except BaseException as error:
        cleanup_error = error
    timing = {
        "proof_finished": proof,
        "cleanup_started": started,
        "cleanup_finished": time.monotonic(),
    }
    record(
        "completion",
        {
            "timing": timing,
            "original_error": None if failure is None else type(failure).__name__,
            "cleanup_error": None if cleanup_error is None else type(cleanup_error).__name__,
        },
    )
    if failure is not None:
        if cleanup_error is not None:
            failure.add_note("Local fixture cleanup also failed: " + type(cleanup_error).__name__)
        return
    if cleanup_error is not None:
        raise cleanup_error
    assert proof is not None
    assert_completion(schedule, timing)


def initialize(fixture, manifest, schedule, monkeypatch, record_property, record):
    admit_service(schedule, time.monotonic())
    started = time.monotonic()
    with observe_command(fixture, monkeypatch, record_property, label="M0_service") as watch:
        receipt = ledger_service.initialize_ledger(watch.engine, validate_ledger_manifest(manifest))
    assert_commit(watch)
    equal(watch.work.timeout_seconds, 5)
    assert_stage(fixture, [manifest], [receipt])
    _, _, state = expected_stage(fixture, [manifest], [receipt])
    initialized = refreshed(fixture)
    record(
        "M0",
        {
            "manifest": manifest,
            "receipt": receipt.model_dump(mode="json"),
            "state": initialized.before,
        },
    )
    return initialized, receipt, state, started, time.monotonic()


def stores(fixture, admission=None, settlement=None):
    value = {"legacy": ciphertexts(fixture.case), "objects": {}, "journal": {}, "settlement": {}}
    equal(value["legacy"], fixture.encrypted)
    if admission is not None:
        assert_stores(fixture, admission, value["legacy"])
        value.update(objects=file_hashes(admission.objects), journal=file_hashes(admission.journal))
    if settlement is not None:
        equal(settlement.storage.read_verified(settlement.descriptor), SETTLEMENT)
        value["settlement"] = file_hashes(settlement.root)
    return value


def sqlite_financial(before):
    # Only the financial reader's documented time projection is normalized.
    # Full snapshots, including raw SQLite time strings, remain byte/type exact.
    projected = deepcopy(before)
    for domain, fields in TIME_FIELDS.items():
        table = FINANCIAL_TABLES[domain]
        values = rows(projected, table)
        for value in values:
            for field in fields:
                assert type(value[field]) is str
                value[field] = datetime.fromisoformat(value[field].replace("Z", "+00:00"))
        replace_rows(projected, table, values)
    return replay_financial(projected)


def produce(fixture, identity, base, record, *, settlement=None, legacy_job=None, membership=None):
    """Declared fixture writes outside the observer; never a provider execution."""
    before = snapshot(fixture.case.path)
    updates = []
    engine = admission_engine(fixture)
    started = time.monotonic()
    try:
        with engine.begin() as connection:
            equal(connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one(), 1)

            def execute(sql, values, count=1):
                assert time.monotonic() - started < 30
                result = connection.execute(text(sql), values)
                try:
                    equal(result.rowcount, count)
                    updates.append({"sql": sql, "parameters": values, "rowcount": result.rowcount})
                finally:
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
                for table, values in reservation_rows(identity, backend="sqlite").items():
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
                assert_evolution(base, before, identity, backend="sqlite")
                evidence = settlement.descriptor
                assert record_verified(connection, evidence)
                assert register_ref(
                    connection,
                    project_id=identity["project"],
                    owner_kind="provider_call",
                    owner_id=identity["call"],
                    role="budget_evidence",
                    artifact_id=evidence.id,
                )
                for value in reservation_rows(identity, backend="sqlite")["budget_entries"]:
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
            equal(connection.exec_driver_sql("PRAGMA foreign_key_check").all(), [])
        assert engine.pool.checkedout() == 0
    finally:
        engine.dispose()
    assert time.monotonic() - started < 30
    current = refreshed(fixture)
    evidence = None if settlement is None else asdict(settlement.descriptor)
    assert_evolution(
        base,
        current.before,
        identity,
        evidence=evidence,
        legacy_job=legacy_job,
        membership=membership,
        backend="sqlite",
    )
    record(
        "reserved_setup" if settlement is None else "settled_setup",
        {"synthetic": True, "updates": updates, "before": before, "after": current.before},
    )
    return current


def replay(
    fixture,
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
    clock_gate=None,
):
    before = snapshot(fixture.case.path)
    financial = sqlite_financial(before)
    saved = stores(fixture, admission, settlement)
    checked = read_ledger_manifest(path)
    equal(checked.model_dump(mode="json"), manifest)
    with native_actions(monkeypatch) as actions:
        equal(inspect(fixture).model_dump(mode="json"), state)
    assert_no_writes(actions)
    equal(snapshot(fixture.case.path), before)
    if clock_gate is not None:
        clock_gate()
    admit_service(schedule, time.monotonic(), expired=clock_gate is not None)
    with (
        observe_command(fixture, monkeypatch, record_property, label=label + "_service") as watch,
        observe_replay(
            watch, monkeypatch, lambda name, value: record(label + "_" + name, value)
        ) as observed,
    ):
        returned = ledger_service.initialize_ledger(watch.engine, checked)
    assert_commit(watch)
    equal(watch.work.timeout_seconds, 5)
    assert_no_writes(watch.actions)
    original_value = original.model_dump(mode="json")
    assert_observation(
        observed, manifest, original_value, state, anchor(watch), len(watch.trace.events), financial
    )
    after = snapshot(fixture.case.path)
    assert_replay_preservation(
        before,
        after,
        original_value,
        returned.model_dump(mode="json"),
        source_rows_from_state(before),
        saved,
        stores(fixture, admission, settlement),
    )
    result = {
        "before": before,
        "after": after,
        "original": original_value,
        "returned": returned.model_dump(mode="json"),
        "stores": saved,
        "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "canonical_sha256": checked.digest,
    }
    record(label + "_result", result)
    return result


def test_sqlite_evolved_original_and_whitespace_replay(tmp_path, monkeypatch, record_property):
    schedule, record = begin(record_property, CASES[0])
    fixture = build_case(tmp_path / "mixed.sqlite")
    proof = None
    try:
        first = mixed_initial(fixture)
        initial, receipt, _, _, _ = initialize(
            fixture,
            first,
            schedule,
            monkeypatch,
            record_property,
            record,
        )
        evolved, admission = admit_existing_fixture(initial, monkeypatch, record)
        assert_admission_delta(initial.before, evolved.before, admission, fixture.project)
        one, _ = job_intents(evolved, first, admission.accepted["job_id"])
        admit_service(schedule, time.monotonic())
        with observe_command(evolved, monkeypatch, record_property, label="M1_service") as watch:
            written = ledger_service.initialize_ledger(watch.engine, validate_ledger_manifest(one))
        assert_commit(watch)
        equal(watch.work.timeout_seconds, 5)
        expected, state = expected_first(fixture, first, receipt, evolved.before, one, written)
        base = snapshot(fixture.case.path)
        equal(base, expected)
        equal(inspect(evolved).model_dump(mode="json"), state)
        record("M1", {"manifest": one, "receipt": written.model_dump(mode="json"), "state": base})
        config = configuration()
        equal(admission.association["job"]["execution_config_digest"], config.digest)
        identity = cohort(
            base,
            first,
            one,
            admission.accepted["job_id"],
            json.loads(config.canonical_bytes)["price_version"],
            written.initialized_at,
            backend="sqlite",
        )
        record("cohort", identity)
        original, whitespace = tmp_path / "M0.json", tmp_path / "M0-whitespace.json"
        for path, payload in zip((original, whitespace), file_bytes(first), strict=True):
            path.write_bytes(payload)
            path.chmod(0o600)
        reserved = produce(evolved, identity, base, record)
        replay(
            reserved,
            first,
            original,
            receipt,
            state,
            schedule,
            monkeypatch,
            record_property,
            record,
            "reserved",
            admission=admission,
        )
        root = tmp_path / "settlement"
        root.mkdir(mode=0o700)
        storage = LocalArtifactStorage(root, Fernet(Fernet.generate_key()), plaintext_limit=4096)
        evidence = descriptor(SETTLEMENT, object_id=EVIDENCE, project=fixture.project)
        assert storage.put_verified(evidence, SETTLEMENT).object == evidence
        settlement = SimpleNamespace(root=root, storage=storage, descriptor=evidence)
        legacy_job = sorted(row["id"] for row in rows(base, "jobs") if row["payload_version"] == 1)[
            0
        ]
        (member,) = rows(base, "project_memberships")
        settled = produce(
            evolved,
            identity,
            base,
            record,
            settlement=settlement,
            legacy_job=legacy_job,
            membership=(member["project_id"], member["principal_id"]),
        )
        results = [
            replay(
                settled,
                first,
                path,
                receipt,
                state,
                schedule,
                monkeypatch,
                record_property,
                record,
                label,
                admission=admission,
                settlement=settlement,
            )
            for label, path in (("canonical", original), ("whitespace", whitespace))
        ]
        assert results[0]["input_sha256"] != results[1]["input_sha256"]
        equal(results[0]["canonical_sha256"], results[1]["canonical_sha256"])
        equal(results[0]["after"], results[1]["after"])
        record(
            "final_preservation",
            {
                "state": results[-1]["after"],
                "stores": stores(settled, admission, settlement),
                "watched_services": 5,
                "receipt_replays": 3,
            },
        )
        proof = time.monotonic()
    finally:
        finish(fixture, schedule, record, proof, sys.exception())


def clock_sample(fixture):
    before = time.monotonic()
    with reader(fixture.case.path) as connection:
        query_only = connection.execute("PRAGMA query_only").fetchone()[0]
        value = connection.execute(SQLITE_CLOCK_SQL).fetchone()[0]
    try:
        connection.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        closed = True
    else:
        raise AssertionError("clock connection remained open")
    result = {
        "before": before,
        "after": time.monotonic(),
        "database": value,
        "sql": SQLITE_CLOCK_SQL,
        "connection_closed": closed,
        "query_only": query_only,
    }
    assert_clock_sample(result, backend="sqlite")
    return result


def test_sqlite_expired_opening_original_replay(tmp_path, monkeypatch, record_property):
    schedule, record = begin(record_property, CASES[1])
    fixture = build_case(tmp_path / "expiry.sqlite")
    proof = None
    try:
        anchor_sample = clock_sample(fixture)
        samples = [anchor_sample]
        a = anchor_sample["before"]
        assert a <= schedule["entered"] + 20 and a <= schedule["started"] + 35
        first = expiry_initial(fixture, anchor_sample["database"])
        initial, receipt, state, m0_start, m0_end = initialize(
            fixture,
            first,
            schedule,
            monkeypatch,
            record_property,
            record,
        )
        assert m0_start <= a + 10 and m0_end <= a + 135
        original = tmp_path / "M0.json"
        original.write_bytes(file_bytes(first)[0])
        original.chmod(0o600)
        end = max(
            instant(row["period_end"])
            for row in first["accounts"]
            if row["scope"] in {"organization", "project"}
        )

        def sample():
            assert len(samples) < 166 and time.monotonic() < a + 165
            delay = max(0.0, samples[-1]["after"] + 1 - time.monotonic())
            if delay:
                time.sleep(delay)
            current = clock_sample(fixture)
            assert_clock_sample(current, anchor=anchor_sample, backend="sqlite")
            assert instant(current["database"]) >= instant(samples[-1]["database"])
            samples.append(current)

        while instant(samples[-1]["database"]) < end:
            sample()

        def final_clock_gate():
            sample()
            assert_expiry_clock(
                schedule,
                first,
                receipt.model_dump(mode="json"),
                samples,
                m0_start,
                m0_end,
                time.monotonic(),
                backend="sqlite",
            )
            record(
                "expiry_clock",
                {
                    "samples": samples,
                    "M0_start": m0_start,
                    "M0_end": m0_end,
                    "wait_transaction_open": False,
                },
            )

        result = replay(
            initial,
            first,
            original,
            receipt,
            state,
            schedule,
            monkeypatch,
            record_property,
            record,
            "expired",
            clock_gate=final_clock_gate,
        )
        record(
            "final_preservation",
            {
                "state": result["after"],
                "stores": stores(initial),
                "watched_services": 2,
                "receipt_replays": 1,
            },
        )
        proof = time.monotonic()
    finally:
        finish(fixture, schedule, record, proof, sys.exception())
