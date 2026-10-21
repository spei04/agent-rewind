"""Private filesystem evidence only; no authority, uploads or SQL publication."""

import json
import os
from dataclasses import replace
from types import SimpleNamespace

import pytest
import test_admission_envelope as fixture
from test_admission_request import at_task_size

from agent_rewind import publication_journal
from agent_rewind.admission_envelope import OriginCorrelation, PreparedAdmission, prepare_admission
from agent_rewind.admission_journal import AdmissionJournal
from agent_rewind.admission_journal_state import (
    MAX_ATTEMPT_RECORDS,
    MAX_CHILD_BYTES,
    MAX_POLICY_BYTES,
    JournalIdentity,
    MetadataCollision,
)
from agent_rewind.admission_request import MAX_TASK_BYTES, parse_submit
from agent_rewind.admission_transaction import TransactionOutcome
from agent_rewind.artifact_metadata import ArtifactError
from agent_rewind.artifact_storage import ObjectWriteResult
from agent_rewind.models import canonical


@pytest.fixture
def f(tmp_path):
    args = fixture.arguments()
    value = prepare_admission(**args)
    identity = JournalIdentity(
        "a" * 32,
        value.project_id,
        "oidc:" + "b" * 64,
        value.intent.client_operation_id,
        "c" * 64,
        value.intent.request_digest,
    )
    root = tmp_path / "journal"
    root.mkdir(mode=0o700)
    return SimpleNamespace(
        root=root,
        journal=AdmissionJournal(root),
        identity=identity,
        value=value,
        payload=fixture.descriptor(value.envelope_bytes, object_id="5" * 32),
    )


def policy(f, value=None):
    value = value or f.value
    return dict(
        schema=1,
        organization_id=f.identity.organization_id,
        project_id=f.identity.project_id,
        principal_id=f.identity.principal_id,
        request_digest=f.identity.request_digest,
        task_digest=value.intent.task_digest,
        configuration_digest=value.configuration.digest,
        permitted_processor_profile=value.configuration.processor_profile,
        version="fixture-v1",
        state={"generation": 1},
    )


def freeze(f, session, **kwargs):
    session.bind(f.value.origin)
    return session.freeze_attempt(
        f.value, operation_id="d" * 32, payload=f.payload, policy=policy(f), **kwargs
    )


def verify(session, f, role):
    objects = dict(
        task=f.value.task_binding.descriptor,
        admission_config=f.value.configuration_binding.descriptor,
        payload=f.payload,
    )
    value = objects[role]
    session.upload_started(role)
    session.upload_verified(role, ObjectWriteResult(value, 1, 1, 2, value.byte_count, 500, False))


def verified(f, session):
    for role in ("task", "admission_config", "payload"):
        verify(session, f, role)


def test_exact_restore_retains_first_origin_and_detaches_snapshots(f):
    with f.journal.open(f.identity) as session:
        assert session.route == "new"
        snapshot = freeze(f, session)
        snapshot.data()["job_id"] = "9" * 32
        assert session.restore(f.value.intent) == f.value
        session.upload_started("task")
    with f.journal.open(f.identity) as session:
        assert session.route == "resume"
        assert session.bind(OriginCorrelation("e" * 32)) == f.value.origin
        assert session.restore(f.value.intent) == f.value
        assert session.snapshot.data()["operation_id"] == "d" * 32
        assert session.states[0].unknown_work
        verified(f, session)
        assert session.states[0].unknown_work  # Interrupted work is never erased.
        assert session.states[0].write_requests == 3
        assert session.states[0].read_requests == 6
        session.commit("commit_pending")
        session.commit("commit_unknown")
    with f.journal.open(f.identity) as session:
        assert session.route == "reconcile"
        assert session.states[0].commit_pending
        with pytest.raises(ArtifactError):
            session.restore(f.value.intent)
        with pytest.raises(ArtifactError):
            session.upload_started("task")


@pytest.mark.parametrize("change", ["key_hash", "client_operation_id", "request_digest"])
def test_reused_unresolved_locator_with_different_full_binding_refuses(f, change):
    with f.journal.open(f.identity) as session:
        freeze(f, session)
    changed = replace(f.identity, **{change: "e" * (32 if change == "client_operation_id" else 64)})
    with pytest.raises(ArtifactError), f.journal.open(changed):
        pytest.fail("mismatched locator authorized preparation")


def test_names_include_every_scope_identity_and_use_sorted_nonblocking_locks(f, monkeypatch):
    original = publication_journal.PublicationJournal.open
    observed = []

    def observe(self, name, **kwargs):
        observed.append(name)
        return original(self, name, **kwargs)

    monkeypatch.setattr(publication_journal.PublicationJournal, "open", observe)
    with f.journal.open(f.identity) as session:
        freeze(f, session)
        assert observed == [*sorted(f.identity.locators), *f.identity.children]
        with (
            pytest.raises(ArtifactError, match="publication_in_progress"),
            f.journal.open(f.identity),
        ):
            pytest.fail("concurrent writer entered")
    for field, value in (
        ("project_id", "e" * 32),
        ("organization_id", "f" * 32),
        ("principal_id", "api-key:" + "f" * 32),
    ):
        changed = replace(f.identity, **{field: value})
        assert set(changed.locators).isdisjoint(f.identity.locators)
    # No installation-directory enumeration; only four known directories.
    real = os.scandir

    def scan(fd):
        assert os.fstat(fd).st_ino != os.stat(f.root).st_ino
        return real(fd)

    monkeypatch.setattr(os, "scandir", scan)
    with f.journal.open(f.identity):
        pass


@pytest.mark.parametrize("which", ["first", "second", "child", "record"])
def test_torn_pair_child_or_history_never_becomes_absence(f, which):
    with f.journal.open(f.identity) as session:
        freeze(f, session)
        session.upload_started("task")
    if which in {"first", "second"}:
        name = sorted(f.identity.locators)[which == "second"]
        path = f.root / name / "intent.json"
    else:
        path = (
            f.root
            / f.identity.children[0]
            / ("intent.json" if which == "child" else "00000000000.json")
        )
    path.write_bytes(b'{"torn":')
    with pytest.raises(ArtifactError), f.journal.open(f.identity):
        pytest.fail("torn evidence accepted")


@pytest.mark.parametrize("stage", [1, 2])
def test_failed_pair_freeze_poisoned_and_reopen_refuses(f, monkeypatch, stage):
    original = publication_journal.JournalSession.freeze
    count = 0

    def fail(session, value):
        nonlocal count
        count += 1
        if count == stage:
            original(session, value)
            raise OSError("PRIVATE-FSYNC")
        return original(session, value)

    monkeypatch.setattr(publication_journal.JournalSession, "freeze", fail)
    with f.journal.open(f.identity) as session:
        with pytest.raises(OSError):
            session.bind(f.value.origin)
        with pytest.raises(ArtifactError):
            freeze(f, session)
    monkeypatch.setattr(publication_journal.JournalSession, "freeze", original)
    with pytest.raises(ArtifactError), f.journal.open(f.identity):
        pytest.fail("incomplete preparation was inferred absent")


@pytest.mark.parametrize(
    "change",
    [
        "origin",
        "scope",
        "unknown-child",
        "configuration",
        "policy",
        "descriptor",
        "job-kind",
        "extra",
    ],
)
def test_complete_but_invalid_snapshot_refuses(f, change):
    with f.journal.open(f.identity) as session:
        freeze(f, session)
    path = f.root / f.identity.children[0] / "intent.json"
    value = json.loads(path.read_bytes())
    if change == "origin":
        value["binding"]["origin"] = "e" * 32
    elif change == "scope":
        value["binding"]["client"]["scope"]["project_id"] = "e" * 32
    elif change == "unknown-child":
        value["binding"]["children"][1] = "e" * 32
    elif change == "configuration":
        value["configuration"]["model"] = "changed"
    elif change == "policy":
        value["policy"]["principal_id"] = "oidc:" + "e" * 64
    elif change == "descriptor":
        value["descriptors"]["task"]["format_version"] = True
    elif change == "job-kind":
        value["binding"]["key"]["scope"]["kind"] = "study"
    else:
        value["task_plaintext"] = "not permitted"
    path.write_bytes(canonical(value))
    with pytest.raises((ArtifactError, ValueError)), f.journal.open(f.identity):
        pytest.fail("invalid complete snapshot accepted")


@pytest.mark.parametrize(
    "kind,data",
    [
        ("commit_pending", {}),
        ("upload_verified", {}),
        ("upload_unknown", {"role": "task", "object_id": "3" * 32, "backend_work": "UNKNOWN"}),
        ("upload_started", {"role": "task", "object_id": "9" * 32, "backend_work": "UNKNOWN"}),
        (
            "commit_confirmed",
            {"operation_id": "d" * 32, "job_id": "2" * 32, "sql_commit": "CONFIRMED"},
        ),
    ],
)
def test_generic_journal_valid_but_semantically_invalid_records_refuse(f, kind, data):
    with f.journal.open(f.identity) as session:
        freeze(f, session)
    with publication_journal.PublicationJournal(f.root).open(f.identity.children[0]) as raw:
        raw.append(kind, data)
    with pytest.raises(ArtifactError), f.journal.open(f.identity):
        pytest.fail("invalid phase accepted")


def test_verified_receipt_requires_exact_metadata_and_counters(f):
    with f.journal.open(f.identity) as session:
        freeze(f, session)
        session.upload_started("task")
        obj = f.value.task_binding.descriptor
        for receipt in (
            ObjectWriteResult(replace(obj, id="e" * 32), 1, 1, 2, obj.byte_count, 500, False),
            ObjectWriteResult(obj, True, 1, 2, obj.byte_count, 500, False),
            ObjectWriteResult(obj, 1, -1, 2, obj.byte_count, 500, False),
        ):
            with pytest.raises(ArtifactError):
                session.upload_verified("task", receipt)
        assert session.states[0].unknown_work
        with pytest.raises(ArtifactError):
            session.commit("commit_pending")


def test_record_exhaustion_is_bounded_and_refuses_without_overwrite(f):
    with f.journal.open(f.identity) as session:
        freeze(f, session)
        for _ in range(MAX_ATTEMPT_RECORDS):
            session.upload_started("task")
        with pytest.raises(ArtifactError):
            session.upload_started("task")
        assert session.states[0].unknown_work
    with f.journal.open(f.identity) as session:
        assert session.states[0].unknown_work
        with pytest.raises(ArtifactError):
            verify(session, f, "task")
    assert len(list((f.root / f.identity.children[0]).glob("0*.json"))) == MAX_ATTEMPT_RECORDS


def test_one_linked_retry_requires_observed_rollback_clean_release_and_exact_collision(f):
    with f.journal.open(f.identity) as session:
        freeze(f, session)
        session.upload_started("task")
        session.upload_unknown("task")
        verified(f, session)
        session.commit("commit_pending")
        old = f.value.task_binding.descriptor
        winner = replace(old, id="e" * 32)
        binding = fixture.ArtifactBinding(
            project_id=f.value.project_id,
            job_id=f.value.job_id,
            role="task",
            descriptor=winner,
            plaintext=f.value.intent.task_bytes,
        )
        replacement = PreparedAdmission(
            f.value.intent,
            f.value.configuration,
            project_id=f.value.project_id,
            job_id=f.value.job_id,
            origin=f.value.origin,
            task_binding=binding,
            configuration_binding=f.value.configuration_binding,
        )
        collision = MetadataCollision(old, winner)
        failed_release = TransactionOutcome(
            begun=True, rollback_attempted=True, rollback_acknowledged=True, cleanup_failed=True
        )
        assert failed_release.confirmed_precommit_rollback
        before_snapshot, before_states = session.snapshot, session.states

        def files():
            return {
                path.relative_to(f.root): path.read_bytes()
                for path in f.root.rglob("*")
                if path.is_file()
            }

        before_files = files()
        for outcome in (
            failed_release,
            True,
            TransactionOutcome(),
            TransactionOutcome(
                begun=True,
                commit_attempted=True,
                rollback_attempted=True,
                rollback_acknowledged=True,
            ),
        ):
            with pytest.raises(ArtifactError):
                session.freeze_attempt(
                    replacement,
                    operation_id="d" * 32,
                    payload=f.payload,
                    policy=policy(f),
                    outcome=outcome,
                    collision=collision,
                )
            assert session.snapshot == before_snapshot and session.states == before_states
            assert len(session.states) == 1 and files() == before_files
        outcome = TransactionOutcome(
            begun=True, rollback_attempted=True, rollback_acknowledged=True
        )
        session.freeze_attempt(
            replacement,
            operation_id="d" * 32,
            payload=f.payload,
            policy=policy(f),
            outcome=outcome,
            collision=collision,
        )
        assert session.restore(f.value.intent) == replacement
        assert len(session.states) == 2 and session.states[0].unknown_work
        assert sum(item.write_requests for item in session.states) == 3
        with pytest.raises(ArtifactError):
            session.freeze_attempt(
                replacement,
                operation_id="d" * 32,
                payload=f.payload,
                policy=policy(f),
                outcome=outcome,
                collision=collision,
            )
    with f.journal.open(f.identity) as session:
        assert session.route == "reconcile"  # Old pending survives a linked child.
        with pytest.raises(ArtifactError):
            session.restore(f.value.intent)


def test_full_task_and_policy_boundary_do_not_enter_journal_as_task_plaintext(f):
    intent = parse_submit(canonical(at_task_size(MAX_TASK_BYTES)))
    value = PreparedAdmission(
        intent,
        f.value.configuration,
        project_id=f.value.project_id,
        job_id=f.value.job_id,
        origin=f.value.origin,
        task_binding=fixture.binding(intent.task_bytes),
        configuration_binding=f.value.configuration_binding,
    )
    f.value = value
    f.identity = replace(
        f.identity,
        client_operation_id=intent.client_operation_id,
        request_digest=intent.request_digest,
    )
    f.payload = fixture.descriptor(value.envelope_bytes, object_id="5" * 32)
    evidence = policy(f)
    evidence["state"] = {"padding": ""}
    evidence["state"]["padding"] = "p" * (MAX_POLICY_BYTES - len(canonical(evidence)))
    assert len(canonical(evidence)) == MAX_POLICY_BYTES
    with f.journal.open(f.identity) as session:
        session.bind(value.origin)
        snapshot = session.freeze_attempt(
            value, operation_id="d" * 32, payload=f.payload, policy=evidence
        )
        assert len(snapshot.encoded) < MAX_CHILD_BYTES
        assert "task_plaintext" not in snapshot.data()
        assert session.restore(intent) == value
    with f.journal.open(f.identity) as session:
        assert session.restore(intent) == value
    evidence["state"]["padding"] += "p"
    fresh = f.root.parent / "overflow"
    fresh.mkdir(mode=0o700)
    with AdmissionJournal(fresh).open(f.identity) as session:
        session.bind(value.origin)
        with pytest.raises(ArtifactError):
            session.freeze_attempt(value, operation_id="d" * 32, payload=f.payload, policy=evidence)
        assert not (fresh / f.identity.children[0] / "intent.json").exists()


@pytest.mark.parametrize("where", ["root", "child"])
def test_oversize_files_refuse_before_byte_materialization(f, monkeypatch, where):
    with f.journal.open(f.identity) as session:
        freeze(f, session)
    folder = f.identity.children[0] if where == "child" else sorted(f.identity.locators)[0]
    limit = MAX_CHILD_BYTES if where == "child" else 4096
    path = f.root / folder / "intent.json"
    path.write_bytes(b"x" * (limit + 1))
    real = publication_journal.read_ciphertext

    def bounded(stream, **kwargs):
        assert os.fstat(stream.fileno()).st_size <= kwargs["limit"]
        return real(stream, **kwargs)

    monkeypatch.setattr(publication_journal, "read_ciphertext", bounded)
    with pytest.raises(ArtifactError), f.journal.open(f.identity):
        pytest.fail("oversized file was materialized")


def test_failed_record_persistence_poisoned_until_validated_reload(f, monkeypatch):
    with f.journal.open(f.identity) as session:
        freeze(f, session)
        original = publication_journal.JournalSession.append

        def fail(raw, kind, data):
            original(raw, kind, data)
            raise OSError("PRIVATE-RECEIPT")

        monkeypatch.setattr(publication_journal.JournalSession, "append", fail)
        with pytest.raises(OSError):
            session.upload_started("task")
        with pytest.raises(ArtifactError):
            session.upload_started("task")
    with f.journal.open(f.identity) as session:
        assert session.states[0].unknown_work


def test_bad_record_object_type_cannot_equal_integer_metadata(f):
    with f.journal.open(f.identity) as session:
        freeze(f, session)
        verify(session, f, "task")
    path = f.root / f.identity.children[0] / "00000000001.json"
    record = json.loads(path.read_bytes())
    record["data"]["object"]["format_version"] = True
    path.write_bytes(canonical(record))
    with pytest.raises(ArtifactError), f.journal.open(f.identity):
        pytest.fail("boolean descriptor version accepted")


def _contender(root, identity, sender):
    try:
        with AdmissionJournal(root).open(identity):
            sender.send("entered")
    except ArtifactError as error:
        sender.send(str(error))
    finally:
        sender.close()


def test_independent_process_cannot_enter_held_locator_pair(f):
    import multiprocessing

    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_contender, args=(f.root, f.identity, sender))
    try:
        with f.journal.open(f.identity) as session:
            freeze(f, session)
            process.start()
            sender.close()
            assert receiver.poll(10), "journal contender did not report within bound"
            assert receiver.recv() == "publication_in_progress"
            process.join(10)
            assert process.exitcode == 0
    finally:
        if process.is_alive():
            process.kill()
            process.join(10)
        receiver.close()
        sender.close()


def test_full_scope_comparison_refuses_truncated_name_collision(f, monkeypatch):
    with f.journal.open(f.identity) as session:
        freeze(f, session)
    # Capture names before replacing the derivation itself.
    client, key = f.identity.locators
    children = f.identity.children

    def names(value):
        if value["purpose"] == "admission-client":
            return client
        if value["purpose"] == "admission-key":
            return key
        return children[value["attempt"]]

    monkeypatch.setattr(JournalIdentity, "_name", staticmethod(names))
    changed = replace(f.identity, principal_id="oidc:" + "f" * 64)
    with pytest.raises(ArtifactError), f.journal.open(changed):
        pytest.fail("locator-name collision replaced full identity")


def test_actual_fsync_failure_preserves_unknown_record_and_poisoned_session(f, monkeypatch):
    real = os.fsync
    with f.journal.open(f.identity) as session:
        freeze(f, session)

        def fail(_fd):
            raise OSError("PRIVATE-FSYNC")

        monkeypatch.setattr(os, "fsync", fail)
        with pytest.raises(OSError):
            session.upload_started("task")
        with pytest.raises(ArtifactError):
            session.upload_started("task")
        monkeypatch.setattr(os, "fsync", real)
    with f.journal.open(f.identity) as session:
        assert session.states[0].unknown_work
        assert session.states[0].write_requests == 0


def test_unknown_commit_cannot_be_reinterpreted_as_safe_child_retry(f):
    with f.journal.open(f.identity) as session:
        freeze(f, session)
        verified(f, session)
        session.commit("commit_pending")
        assert session.route == "reconcile"
        session.commit("commit_unknown")
        with pytest.raises(ArtifactError):
            session.commit("commit_unknown")
        with pytest.raises(ArtifactError):
            session.freeze_attempt(
                f.value,
                operation_id="d" * 32,
                payload=f.payload,
                policy=policy(f),
                outcome=TransactionOutcome(
                    begun=True, rollback_attempted=True, rollback_acknowledged=True
                ),
                collision=MetadataCollision(
                    f.value.task_binding.descriptor,
                    replace(f.value.task_binding.descriptor, id="e" * 32),
                ),
            )
        session.commit("commit_confirmed")
    with f.journal.open(f.identity) as session:
        assert session.route == "reconcile" and session.states[0].commit_status == "CONFIRMED"


def test_context_release_and_cleanup_failure_cannot_replace_primary_denial(f, monkeypatch):
    from contextlib import ExitStack

    from agent_rewind.scoped_lineage import ResourceNotFound

    original = ExitStack.close

    def fail(stack):
        original(stack)
        raise OSError("PRIVATE-CLOSE")

    with f.journal.open(f.identity) as session:
        freeze(f, session)
    with pytest.raises(ArtifactError):
        session.restore(f.value.intent)
    monkeypatch.setattr(ExitStack, "close", fail)
    denial = ResourceNotFound()
    with pytest.raises(ResourceNotFound) as caught, f.journal.open(f.identity):
        raise denial
    assert caught.value is denial
    with (
        pytest.raises(ArtifactError, match="^admission_journal_unavailable$"),
        f.journal.open(f.identity),
    ):
        pass


def test_limits_reject_invalid_values_and_prefetch_record_count(f, monkeypatch):
    from agent_rewind.publication_journal import JournalLimits

    for values in ((True, 1, 1), (1, -1, 1), (1, 100001, 1), (1, 1, 0)):
        with pytest.raises(ArtifactError):
            JournalLimits(*values)
    with f.journal.open(f.identity) as session:
        freeze(f, session)
    child = f.root / f.identity.children[0]
    for index in range(MAX_ATTEMPT_RECORDS + 1):
        path = child / f"{index:011d}.json"
        path.write_bytes(b"{}")
        path.chmod(0o600)
    original = publication_journal.JournalSession._read

    def read(raw, name, limit):
        assert os.fstat(raw.fd).st_ino != child.stat().st_ino
        return original(raw, name, limit)

    monkeypatch.setattr(publication_journal.JournalSession, "_read", read)
    with (
        pytest.raises(ArtifactError, match="publication_journal_limit"),
        f.journal.open(f.identity),
    ):
        pytest.fail("over-count history reached materialization")


def test_frozen_configuration_limit_precedes_configuration_parser(f, monkeypatch):
    from agent_rewind import admission_journal_state
    from agent_rewind.admission_request import MAX_CONFIG_BYTES

    with f.journal.open(f.identity) as session:
        freeze(f, session)
    path = f.root / f.identity.children[0] / "intent.json"
    value = json.loads(path.read_bytes())
    value["configuration"]["oversized"] = "x" * (MAX_CONFIG_BYTES + 1)
    raw = canonical(value)
    assert len(raw) < MAX_CHILD_BYTES
    path.write_bytes(raw)

    def forbidden(*args, **kwargs):
        pytest.fail("oversized frozen configuration reached parser")

    monkeypatch.setattr(admission_journal_state, "NativeConfiguration", forbidden)
    with pytest.raises(ArtifactError), f.journal.open(f.identity):
        pytest.fail("oversized frozen configuration accepted")


def test_reopened_unfinished_call_requires_new_start_before_receipt(f):
    with f.journal.open(f.identity) as session:
        freeze(f, session)
        session.upload_started("task")
    obj = f.value.task_binding.descriptor
    receipt = ObjectWriteResult(obj, 1, 1, 2, obj.byte_count, 500, False)
    with f.journal.open(f.identity) as session:
        with pytest.raises(ArtifactError):
            session.upload_verified("task", receipt)
        assert session.states[0].unknown_work
        session.upload_started("task")
        session.upload_verified("task", receipt)
        assert session.states[0].unknown_work
        assert session.states[0].write_requests == 1
    with f.journal.open(f.identity) as session:
        assert session.states[0].unknown_work and session.states[0].write_requests == 1
