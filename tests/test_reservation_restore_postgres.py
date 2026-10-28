"""Same-cluster physical restore preserves actual P2 reservation history."""

import hashlib
import json
import os
import shutil
from dataclasses import asdict, replace

import pytest
import test_migrations_postgres as migrations
from ledger_eligibility_fixture import file_hashes
from ledger_provisioning_postgres_fixture import inspect
from ledger_restore_authority import assert_same_authority, typed
from ledger_restore_postgres_fixture import (
    TOOLS_ENV,
    assert_application_denials,
    capture,
    copy_ciphertexts,
    copy_hashes,
    empty_target,
    save,
    tool_configuration,
)
from ledger_restore_tool_ownership import restore_tool_ownership
from ledger_restore_tools import run_tool, tool_command, tool_environment
from legacy_fixture import FIXTURE_ROOT
from reservation_postgres_fixture import (
    build_postgres_reservation_case,
    offline_postgres_ledger,
)
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool
from test_ledger_recovery_restore_postgres import assert_migration_only, replay_original
from test_ledger_service_postgres import controlled_database_name
from test_run_projection_postgres import drain, observed_reader

from agent_rewind.artifact_storage import LocalArtifactStorage
from agent_rewind.migrations.compatibility import configure_runtime_engine
from agent_rewind.request_authority import RequestAuthority
from agent_rewind.reservation_service import ReservationCoordinator
from agent_rewind.reservation_types import (
    CallMatching,
    ClaimIntent,
    CreatedReservation,
    OriginalReservation,
    ReservationIntent,
)

pg = migrations.pg
__all__ = ["controlled_database_name", "observed_reader", "restore_tool_ownership"]
pytestmark = pytest.mark.skipif(
    not migrations.POSTGRES or not os.environ.get(TOOLS_ENV),
    reason="Opt-in same-cluster restore after actual P2 reservation",
)


def test_postgres_restored_reservation_retains_original_identity_and_balances(
    pg, observed_reader, tmp_path, monkeypatch, record_property
):
    def record(name, value):
        record_property(name, json.dumps(typed(value), allow_nan=False))

    case = build_postgres_reservation_case(
        pg,
        tmp_path,
        monkeypatch,
        legacy=True,
        record=lambda name, value: record("setup_" + name, value),
    )
    try:
        claim = ReservationCoordinator(case.engine, case.authority)
        fence = claim.claim_generation(
            case.principal, case.context, ClaimIntent(case.job_id, "a" * 32, 0, 60)
        )
        intent = ReservationIntent(
            call_id="b" * 32,
            project_id=case.project_id,
            job_id=case.job_id,
            logical_call_id="c" * 32,
            request_digest="d" * 64,
            purpose="continuation",
            price_version=case.price_version,
            reserved_microusd=12345,
            lease_generation=fence.generation,
            organization_account_id=case.account_ids[0],
            project_account_id=case.account_ids[1],
            job_account_id=case.account_ids[2],
        )
        reserve = ReservationCoordinator(case.engine, case.authority)
        original = reserve.reserve(case.principal, case.context, fence, intent)
        assert isinstance(original, CreatedReservation) and original.record.identity == intent
        for owner in (claim, reserve):
            assert owner.outcome.commit_acknowledged and not owner.outcome.cleanup_failed
            assert owner._work.statements <= 512 and owner._work.seconds < 10
        record(
            "p2_source",
            {
                "identity": asdict(intent),
                "record": asdict(original.record),
                "claim_outcome": asdict(claim.outcome),
                "reserve_outcome": asdict(reserve.outcome),
                "claim_units": claim._work.statements,
                "reserve_units": reserve._work.statements,
            },
        )
        case.engine.dispose()
        fixture = case.provisioning
        with offline_postgres_ledger(case, record):
            source_inspection = inspect(fixture, pg)
        directory = tmp_path / "restore-evidence"
        binary, socket, port, token = tool_configuration(pg, directory, record_property)
        before = capture(fixture, pg, directory, "source-before", record_property)
        assert before["authority"]["database"][0]["acl"] is None
        legacy_backup = directory / "legacy-backup"
        legacy_hashes = copy_ciphertexts(FIXTURE_ROOT / "objects", legacy_backup)
        assert legacy_hashes == fixture.encrypted
        admission = case.admission
        object_hashes, journal_hashes = (
            file_hashes(admission.objects),
            file_hashes(admission.journal),
        )
        assert object_hashes == admission.ciphertexts and journal_hashes == admission.journal_hashes
        admitted_backup = directory / "admitted-backup"
        shutil.copytree(admission.objects, admitted_backup)
        assert file_hashes(admitted_backup) == object_hashes
        plaintext_hashes = {
            value.id: hashlib.sha256(admission.storage.read_verified(value)).hexdigest()
            for value in admission.descriptors
        }
        assert all(plaintext_hashes[value.id] == value.digest for value in admission.descriptors)
        save(
            directory,
            "p2-originals",
            {
                "identity": asdict(intent),
                "record": asdict(original.record),
                "manifest": admission.manifest,
                "receipt": admission.initialization_receipt.model_dump(mode="json"),
                "inspection": source_inspection.model_dump(mode="json"),
                "legacy_ciphertexts": legacy_hashes,
                "admission_ciphertexts": object_hashes,
                "admission_plaintext_digests": plaintext_hashes,
                "scope": (
                    "Same cluster and existing synthetic roles; no dispatch or readiness activation"
                ),
            },
            record_property,
        )
        drain(pg)
        try:
            archive = run_tool(
                tool_command(binary / "pg_dump", "pg_dump", pg["owner"].url.database, socket, port),
                directory,
                label="dump",
                env=tool_environment(socket, "ar_restore_" + token + "_dump"),
                archive=True,
            )
            with empty_target(fixture, pg, directory, record_property) as (target, target_pg):
                run_tool(
                    tool_command(
                        binary / "pg_restore",
                        "pg_restore",
                        target_pg["owner"].url.database,
                        socket,
                        port,
                        archive=archive,
                    ),
                    directory,
                    label="restore",
                    env=tool_environment(socket, "ar_restore_" + token + "_restore"),
                )
                drain(target_pg)
                restored_legacy = directory / "legacy-restored"
                assert copy_ciphertexts(legacy_backup, restored_legacy) == legacy_hashes
                restored_admitted = directory / "admitted-restored"
                shutil.copytree(admitted_backup, restored_admitted)
                assert file_hashes(restored_admitted) == object_hashes
                storage = LocalArtifactStorage(
                    restored_admitted,
                    admission.storage.cipher,
                    plaintext_limit=admission.storage.plaintext_limit,
                )
                assert {
                    value.id: hashlib.sha256(storage.read_verified(value)).hexdigest()
                    for value in admission.descriptors
                } == plaintext_hashes
                restored = capture(target, target_pg, directory, "target-restored", record_property)
                assert restored["snapshot"] == before["snapshot"]
                assert restored["progress"] == before["progress"]
                assert_same_authority(before["authority"], restored["authority"])
                app = create_engine(
                    target_pg["app"].url,
                    poolclass=QueuePool,
                    pool_timeout=1,
                    pool_size=8,
                    max_overflow=0,
                    pool_pre_ping=False,
                )
                try:
                    configure_runtime_engine(app, production=True)
                    authority = RequestAuthority(app)
                    context = authority.named(
                        case.principal, case.project_id, action="record"
                    ).context
                    restored_case = replace(
                        case,
                        engine=app,
                        authority=authority,
                        context=context,
                        case=target.case,
                        provisioning=target,
                        pg=target_pg,
                    )
                    with offline_postgres_ledger(restored_case, record):
                        assert inspect(target, target_pg) == source_inspection
                        replay_original(
                            target,
                            target_pg,
                            admission.manifest,
                            admission.initialization_receipt,
                            monkeypatch,
                            record_property,
                        )
                    replayed = capture(
                        target, target_pg, directory, "target-p1-replayed", record_property
                    )
                    assert replayed == restored
                    observer = ReservationCoordinator(app, authority)
                    observation = observer.inspect_original(
                        case.principal, context, case.job_id, intent
                    )
                    assert isinstance(observation.call, CallMatching)
                    assert observation.call.record == original.record
                    repeater = ReservationCoordinator(app, authority)
                    repeated = repeater.reserve(case.principal, context, fence, intent)
                    assert isinstance(repeated, OriginalReservation)
                    assert repeated.record == original.record
                    for owner in (observer, repeater):
                        assert (
                            owner.outcome.commit_acknowledged and not owner.outcome.cleanup_failed
                        )
                        assert owner._work.statements <= 512 and owner._work.seconds < 10
                    record(
                        "restored_p2_observation",
                        {
                            "inspection": asdict(observation),
                            "repeat": asdict(repeated),
                            "inspection_outcome": asdict(observer.outcome),
                            "repeat_outcome": asdict(repeater.outcome),
                            "inspection_units": observer._work.statements,
                            "repeat_units": repeater._work.statements,
                            "meaning": (
                                "Historical observation only; neither result is a dispatch permit"
                            ),
                        },
                    )
                    assert typed(restored_case.snapshot()) == before["snapshot"]
                finally:
                    app.dispose()
                    drain(target_pg)
                assert_application_denials(target, target_pg, directory, record_property)
                assert_migration_only(target, target_pg)
                final = capture(target, target_pg, directory, "target-final", record_property)
                assert final == restored
                assert copy_hashes(restored_legacy) == legacy_hashes
                assert file_hashes(restored_admitted) == object_hashes
        finally:
            after = capture(fixture, pg, directory, "source-after", record_property)
            assert after == before
            assert copy_hashes(FIXTURE_ROOT / "objects") == legacy_hashes
            assert file_hashes(admission.objects) == object_hashes
            assert file_hashes(admission.journal) == journal_hashes
            save(directory, "source-preservation", {"exact": True}, record_property)
    finally:
        case.close()
