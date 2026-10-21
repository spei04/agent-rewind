"""Private dual-locator admission evidence for the internal coordinator.

Only the two scoped locators and two derived children are opened. Locks are local,
nonblocking and ordered; journal possession never authorizes work or proves SQL.
Callers must resolve both SQL identities and reauthorize before using this API.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any

from .admission_envelope import OriginCorrelation, PreparedAdmission
from .admission_journal_state import (
    MAX_ATTEMPT_RECORDS,
    MAX_BINDING_BYTES,
    MAX_CHILD_BYTES,
    MAX_POLICY_BYTES,
    ROLES,
    AttemptSnapshot,
    JournalIdentity,
    MetadataCollision,
    WorkState,
    descriptor,
    encode,
    invalid,
    work_state,
)
from .admission_request import CanonicalIntent
from .admission_transaction import TransactionOutcome
from .artifact_metadata import ArtifactError, ArtifactObject, identifier
from .artifact_storage import ObjectWriteResult
from .publication_journal import JournalLimits, JournalSession, PublicationJournal

LOCATOR_LIMITS = JournalLimits(MAX_BINDING_BYTES, 0, MAX_BINDING_BYTES)
CHILD_LIMITS = JournalLimits(
    MAX_CHILD_BYTES, MAX_ATTEMPT_RECORDS, MAX_CHILD_BYTES + MAX_ATTEMPT_RECORDS * 16384
)


class AdmissionJournalSession:
    def __init__(
        self, identity: JournalIdentity, roots: list[JournalSession], children: list[JournalSession]
    ):
        self.identity = identity
        self._roots, self._children = roots, children
        self._usable = True
        self._snapshots: list[AttemptSnapshot | None] = [None, None]
        bindings = [root.intent for root in roots]
        if all(value is None for value in bindings):
            if any(child.intent is not None or child.records for child in children):
                invalid()
            self._binding: bytes | None = None
        elif all(value is not None for value in bindings):
            encoded = [identity.validate_binding(value) for value in bindings if value is not None]
            if encoded[0] != encoded[1]:
                invalid()
            self._binding = encoded[0]
            for index, child in enumerate(children):
                if child.intent is not None:
                    self._snapshots[index] = AttemptSnapshot.validate(
                        child.intent, identity, self._binding, index
                    )
            if self._snapshots[0] is None:
                # A complete pair is not proof that a missing frozen child never
                # existed. Only this invocation's genuinely fresh pair may freeze it.
                invalid()
            self._validate_link()
        else:
            invalid()
        self._opened_pending = any(state.commit_pending for state in self.states)
        self._resumed_upload = bool(self.states and self.states[-1].pending_role is not None)

    def _check(self) -> None:
        if not self._usable:
            invalid()

    @property
    def snapshot(self) -> AttemptSnapshot | None:
        """Detached frozen input for later policy/SQL composition, never a grant."""
        self._check()
        return self._snapshots[1] or self._snapshots[0]

    @property
    def states(self) -> tuple[WorkState, ...]:
        return tuple(
            work_state(snapshot, child.records)
            for snapshot, child in zip(self._snapshots, self._children, strict=True)
            if snapshot is not None
        )

    @property
    def route(self) -> str:
        self._check()
        if self._opened_pending or (self.states and self.states[-1].commit_pending):
            return "reconcile"
        return "new" if self._snapshots[0] is None else "resume"

    @property
    def origin(self) -> OriginCorrelation:
        self._check()
        if self._binding is None:
            invalid()
        return OriginCorrelation(json.loads(self._binding)["origin"])

    def bind(self, origin: OriginCorrelation) -> OriginCorrelation:
        self._check()
        if self._binding is not None:
            return self.origin  # A retry's fresh request ID never replaces first origin.
        binding = encode(self.identity.binding(origin), MAX_BINDING_BYTES)
        try:
            for root in self._roots:
                root.freeze(json.loads(binding))
        except BaseException:
            self._usable = False
            raise
        self._binding = binding
        return self.origin

    def _validate_link(self) -> None:
        old, new = self._snapshots
        if new is None:
            return
        if old is None:
            invalid()
        before, after = old.data(), new.data()
        if work_state(old, self._children[0].records).commit_status != "PENDING":
            invalid()
        for key in before.keys() - {"index", "predecessor", "descriptors"}:
            if before[key] != after[key]:
                invalid()
        collision = after["predecessor"]["collision"]
        if (
            collision["expected"] not in before["descriptors"].values()
            or collision["winner"] not in after["descriptors"].values()
        ):
            invalid()

    def freeze_attempt(
        self,
        prepared: PreparedAdmission,
        *,
        operation_id: str,
        payload: ArtifactObject,
        policy: dict[str, Any],
        outcome: TransactionOutcome | None = None,
        collision: MetadataCollision | None = None,
    ) -> AttemptSnapshot:
        self._check()
        if self._binding is None or self._opened_pending or type(prepared) is not PreparedAdmission:
            invalid()
        identifier(operation_id)
        identity = self.identity
        if (
            prepared.project_id != identity.project_id
            or prepared.origin != self.origin
            or prepared.intent.client_operation_id != identity.client_operation_id
            or prepared.intent.request_digest != identity.request_digest
        ):
            invalid()
        prepared.bind_payload(payload)
        encode(policy, MAX_POLICY_BYTES)
        index = 0
        predecessor = None
        if outcome is not None or collision is not None:
            if (
                type(outcome) is not TransactionOutcome
                or not outcome.confirmed_precommit_rollback
                or outcome.cleanup_failed
                or type(collision) is not MetadataCollision
                or self._snapshots[0] is None
                or self._snapshots[1] is not None
                or not self.states[0].commit_pending
                or self.states[0].commit_status != "PENDING"
            ):
                invalid()
            collision.__post_init__()
            index = 1
            predecessor = dict(
                attempt_id=identity.children[0],
                rollback_acknowledged=True,
                collision=collision.record(),
            )
        elif self._snapshots[0] is not None:
            invalid()  # Resume uses restore(), never refreezes changed preparation.
        value = dict(
            schema=1,
            purpose="admission-attempt",
            binding=json.loads(self._binding),
            index=index,
            predecessor=predecessor,
            operation_id=operation_id,
            job_id=prepared.job_id,
            task_digest=prepared.intent.task_digest,
            configuration_digest=prepared.configuration.digest,
            envelope_digest=prepared.envelope_digest,
            configuration=json.loads(prepared.configuration.canonical_bytes),
            policy=policy,
            descriptors={
                "task": descriptor(prepared.task_binding.descriptor),
                "admission_config": descriptor(prepared.configuration_binding.descriptor),
                "payload": descriptor(payload),
            },
        )
        snapshot = AttemptSnapshot.validate(value, identity, self._binding, index)
        # Validate linked content before writing the immutable child.
        self._snapshots[index] = snapshot
        try:
            self._validate_link()
            self._children[index].freeze(snapshot.data())
        except BaseException:
            self._usable = False
            raise
        return snapshot

    def restore(self, intent: CanonicalIntent) -> PreparedAdmission:
        self._check()
        if self._opened_pending:
            invalid()
        snapshot = self._snapshots[1] or self._snapshots[0]
        if snapshot is None:
            invalid()
        return snapshot.restore(self.identity, intent)

    def _append(self, kind: str, data: dict[str, Any]) -> None:
        self._check()
        index = 1 if self._snapshots[1] is not None else 0
        snapshot = self._snapshots[index]
        if snapshot is None or self._opened_pending:
            invalid()
        if kind == "upload_verified" and self._resumed_upload:
            # An old unfinished call is UNKNOWN. Reverification must first append
            # its own durable start, preserving that earlier unknown work.
            invalid()
        child = self._children[index]
        candidate = dict(sequence=len(child.records), kind=kind, data=data)
        work_state(snapshot, [*child.records, candidate])
        try:
            child.append(kind, data)
            if kind in {"upload_started", "upload_unknown"}:
                self._resumed_upload = False
        except BaseException:
            self._usable = False
            raise

    def upload_started(self, role: str) -> None:
        self._upload_unknown("upload_started", role)

    def upload_unknown(self, role: str) -> None:
        self._upload_unknown("upload_unknown", role)

    def _upload_unknown(self, kind: str, role: str) -> None:
        if role not in ROLES:
            invalid()
        snapshot = self._snapshots[1] or self._snapshots[0]
        if snapshot is None:
            invalid()
        self._append(
            kind,
            dict(
                role=role,
                object_id=snapshot.data()["descriptors"][role]["id"],
                backend_work="UNKNOWN",
            ),
        )

    def upload_verified(self, role: str, receipt: ObjectWriteResult) -> None:
        if type(receipt) is not ObjectWriteResult:
            invalid()
        self._append(
            "upload_verified",
            dict(
                role=role,
                object=descriptor(receipt.object),
                logical_writes=receipt.logical_writes,
                write_requests=receipt.write_requests,
                read_requests=receipt.read_requests,
                plaintext_bytes=receipt.plaintext_bytes,
                ciphertext_bytes=receipt.ciphertext_bytes,
                cache_hit=receipt.cache_hit,
            ),
        )

    def commit(self, kind: str) -> None:
        if kind not in {"commit_pending", "commit_unknown", "commit_confirmed"}:
            invalid()
        snapshot = self._snapshots[1] or self._snapshots[0]
        if snapshot is None:
            invalid()
        value = snapshot.data()
        self._append(
            kind,
            dict(
                operation_id=value["operation_id"],
                job_id=value["job_id"],
                sql_commit="CONFIRMED" if kind == "commit_confirmed" else "UNKNOWN",
            ),
        )


class AdmissionJournal:
    def __init__(self, root: Path):
        self._journal = PublicationJournal(root)

    @contextmanager
    def open(self, identity: JournalIdentity) -> Iterator[AdmissionJournalSession]:
        if type(identity) is not JournalIdentity:
            invalid()
        identity.__post_init__()
        stack = ExitStack()
        primary: BaseException | None = None
        session = None
        try:
            roots = [
                stack.enter_context(self._journal.open(name, limits=LOCATOR_LIMITS))
                for name in sorted(identity.locators)
            ]
            # Refuse partial/mismatched locators before touching any child.
            if any(root.intent is not None for root in roots):
                if any(root.intent is None for root in roots):
                    invalid()
                bindings = [
                    identity.validate_binding(root.intent)
                    for root in roots
                    if root.intent is not None
                ]
                if bindings[0] != bindings[1]:
                    invalid()
            children = [
                stack.enter_context(self._journal.open(name, limits=CHILD_LIMITS))
                for name in identity.children
            ]
            session = AdmissionJournalSession(identity, roots, children)
            yield session
        except BaseException as error:
            primary = error
        finally:
            if session is not None:
                session._usable = False
            try:
                stack.close()
            except Exception:
                if primary is None:
                    primary = ArtifactError("admission_journal_unavailable")
        if primary is not None:
            if isinstance(primary, OSError):
                raise ArtifactError("admission_journal_unavailable") from None
            raise primary from None
