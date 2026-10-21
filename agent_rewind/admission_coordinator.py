"""Preparatory admission composition with unavailable defaults and a real schema guard.

SQL winners bypass new-work dependencies. Explicit internal adapters alone do not
make a migration-only release ready. Storage/journal/readiness run only after SQL
release; the caller receives IDs only after acknowledged publication and disclosure.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any, TypeVar

from sqlalchemy.engine import Connection, Engine

from .admission_adapters import (
    AdmissionPolicy,
    AdmissionReadiness,
    AdmissionReady,
    ProcessorPermission,
    UnavailableAdmissionPolicy,
    completed,
    synchronous,
)
from .admission_configuration import NativeConfiguration, NativeRegistry
from .admission_envelope import ArtifactBinding, OriginCorrelation, PreparedAdmission
from .admission_journal import AdmissionJournal
from .admission_journal_state import (
    MAX_POLICY_BYTES,
    JournalIdentity,
    encode,
    metadata,
    validate_policy,
)
from .admission_publication import (
    PublicationCollision,
    prove_replacement,
    publish_rows,
    select_descriptor,
    validate_receipts,
)
from .admission_records import AdmissionStorageError, StoredOperation, hexadecimal
from .admission_repository import AdmissionIdentityConflict, AdmissionRepository, IdentityResolution
from .admission_request import CanonicalIntent
from .admission_transaction import AdmissionError, TransactionOutcome, admission_transaction
from .artifact_metadata import ArtifactObject, object_locator
from .artifact_storage import ArtifactStorage, ObjectWriteResult
from .migrations.compatibility import CompatibilityResult, runtime_schema_compatibility
from .request_authority import ActionForbidden, RequestAuthority
from .request_identity import IdentityInvalid, VerifiedPrincipal
from .scoped_lineage import ResourceNotFound
from .scoped_locks import lock_authority, lock_resource
from .scoped_repositories import ProjectContext

T = TypeVar("T")


def _journal_call(call: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    try:
        return call(*args, **kwargs)
    except (IdentityInvalid, ResourceNotFound, ActionForbidden, AdmissionError):
        raise
    except Exception:
        raise AdmissionError("outcome_uncertain") from None


class AdmissionCoordinator:
    """Original context and creator-record recovery; never viewer status disclosure."""

    def __init__(
        self,
        engine: Engine,
        authority: RequestAuthority,
        *,
        policy: AdmissionPolicy | None = None,
        registry: NativeRegistry | None = None,
        readiness: AdmissionReadiness | None = None,
        journal: AdmissionJournal | None = None,
        storage: ArtifactStorage | None = None,
    ):
        self.engine, self.authority = engine, authority
        self.repository = AdmissionRepository(authority)
        self.policy = policy if policy is not None else UnavailableAdmissionPolicy()
        self.registry, self.readiness = registry, readiness
        self.journal, self.storage = journal, storage

    def schema_compatibility(self) -> CompatibilityResult:
        return runtime_schema_compatibility(self.engine)

    def _schema(self) -> None:
        observed = self.schema_compatibility()
        if observed.status != "ready":
            raise AdmissionError(
                "dependency_unavailable"
                if observed.status == "unavailable"
                else "schema_incompatible"
            )

    def _resolve(
        self,
        connection: Connection,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        client_operation_id: str,
        key_hash: str,
        request_digest: str,
    ) -> IdentityResolution:
        try:
            return self.repository.resolve_identities(
                connection,
                principal,
                context,
                client_operation_id=client_operation_id,
                key_hash=key_hash,
                request_digest=request_digest,
            )
        except AdmissionIdentityConflict:
            raise AdmissionError("idempotency_conflict") from None
        # All other storage/constraint failures remain dependencies, never 409.

    def submit(
        self,
        principal: VerifiedPrincipal,
        original_context: ProjectContext,
        intent: CanonicalIntent,
        key_hash: str,
        origin: OriginCorrelation,
    ) -> dict[str, str]:
        if type(intent) is not CanonicalIntent or type(origin) is not OriginCorrelation:
            raise AdmissionError("invalid_request")
        winner = self._recover(
            principal,
            original_context,
            intent.client_operation_id,
            key_hash,
            intent.request_digest,
            reconcile=False,
            allow_absent=True,
        )
        if winner is not None:
            return winner
        return self._new_work(principal, original_context, intent, key_hash, origin)

    def reconcile(
        self,
        principal: VerifiedPrincipal,
        original_context: ProjectContext,
        client_operation_id: str,
        key_hash: str,
        request_digest: str,
    ) -> dict[str, str]:
        result = self._recover(
            principal,
            original_context,
            client_operation_id,
            key_hash,
            request_digest,
            reconcile=True,
        )
        if result is None:
            raise AdmissionError("outcome_uncertain")
        return result

    def _recover(
        self,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        client_operation_id: str,
        key_hash: str,
        request_digest: str,
        *,
        reconcile: bool,
        allow_absent: bool = False,
    ) -> dict[str, str] | None:
        try:
            hexadecimal(client_operation_id, 32, input_value=True)
            hexadecimal(key_hash, 64, input_value=True)
            hexadecimal(request_digest, 64, input_value=True)
        except AdmissionStorageError:
            raise AdmissionError("invalid_request") from None
        original = None
        outcome = TransactionOutcome()
        try:
            self._schema()
            with admission_transaction(self.engine, outcome) as connection:
                resolved = self._locked_identities(
                    connection, principal, context, client_operation_id, key_hash, request_digest
                )
                original = resolved.operation
                if original is None:
                    if allow_absent:
                        return None
                    raise AdmissionError(
                        "outcome_uncertain" if reconcile else "dependency_unavailable"
                    )
                original = self._complete_winner(
                    connection,
                    principal,
                    context,
                    client_operation_id,
                    key_hash,
                    request_digest,
                    resolved,
                )
            # SQL is released before fresh original-context disclosure. No lookup
            # through get_operation: its viewer status permission is insufficient.
            return self._disclose(
                principal, context, original, client_operation_id, key_hash, request_digest
            )
        except AdmissionError as error:
            # Before a locked, verified winner or SQL absence, a prior commit
            # cannot be ruled out. Known alias rollback and dependencies reached
            # after proven absence retain their established precommit phase.
            if error.code == "dependency_unavailable" and (
                (allow_absent and original is None) or reconcile or outcome.commit_attempted
            ):
                raise AdmissionError("outcome_uncertain") from None
            raise

    def _locked_identities(
        self,
        connection: Connection,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        client_operation_id: str,
        key_hash: str,
        request_digest: str,
    ) -> IdentityResolution:
        first = self._resolve(
            connection, principal, context, client_operation_id, key_hash, request_digest
        )
        lock_authority(self.authority, connection, principal, context, None, None)
        locked = self._resolve(
            connection, principal, context, client_operation_id, key_hash, request_digest
        )
        original = locked.operation
        if original is None:
            return locked
        if first.operation is not None and first.operation != original:
            raise AdmissionError("outcome_uncertain")
        lock_resource(connection, context, "job", original.job_id, shared=True)
        verified = self._resolve(
            connection, principal, context, client_operation_id, key_hash, request_digest
        )
        if verified.operation != original:
            raise AdmissionError("outcome_uncertain")
        return verified

    def _complete_winner(
        self,
        connection: Connection,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        client_operation_id: str,
        key_hash: str,
        request_digest: str,
        verified: IdentityResolution,
    ) -> StoredOperation:
        original = verified.operation
        if original is None:
            raise AdmissionError("outcome_uncertain")
        if verified.needs_alias:
            self.repository.bind_alias(
                connection,
                principal,
                context,
                operation_id=original.id,
                key_hash=key_hash,
                request_digest=request_digest,
            )
        final = self._resolve(
            connection, principal, context, client_operation_id, key_hash, request_digest
        )
        if final.operation != original or final.needs_alias:
            raise AdmissionError("outcome_uncertain")
        return original

    def _locked_winner(
        self,
        connection: Connection,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        client_operation_id: str,
        key_hash: str,
        request_digest: str,
    ) -> StoredOperation | None:
        verified = self._locked_identities(
            connection, principal, context, client_operation_id, key_hash, request_digest
        )
        if verified.operation is None:
            return None
        return self._complete_winner(
            connection, principal, context, client_operation_id, key_hash, request_digest, verified
        )

    def _disclose(
        self,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        original: StoredOperation,
        client_operation_id: str,
        key_hash: str,
        request_digest: str,
    ) -> dict[str, str]:
        with admission_transaction(self.engine, TransactionOutcome()) as connection:
            result = self._resolve(
                connection, principal, context, client_operation_id, key_hash, request_digest
            )
            if result.operation != original or result.needs_alias:
                raise AdmissionError("outcome_uncertain")
            self.authority.check(
                connection,
                principal,
                context,
                "record",
                resource_kind="job",
                resource_id=original.job_id,
            )
        return original.accepted_response

    def _available(self) -> None:
        completed(self.policy.require_available)
        if self.storage is None or self.readiness is None:
            raise AdmissionError("dependency_unavailable")

    def _recheck(
        self,
        connection: Connection,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        prepared: PreparedAdmission,
        evidence: dict[str, Any],
    ) -> None:
        self.authority.check(connection, principal, context, "record")
        completed(
            self.policy.recheck,
            connection,
            principal,
            context,
            prepared.intent,
            prepared.configuration,
            json.loads(encode(evidence, MAX_POLICY_BYTES)),
        )
        self.authority.check(connection, principal, context, "record")

    def _prepare(
        self,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        intent: CanonicalIntent,
        configuration: NativeConfiguration,
        origin: OriginCorrelation,
        job_id: str,
    ) -> tuple[PreparedAdmission, ArtifactBinding]:
        def prospective(data: bytes, digest: str) -> ArtifactObject:
            return ArtifactObject(
                uuid.uuid4().hex,
                context.project_id,
                digest,
                object_locator(context.project_id, digest),
                1,
                len(data),
                datetime.now(UTC),
            )

        with admission_transaction(self.engine, TransactionOutcome()) as connection:
            self.authority.check(connection, principal, context, "record")
            task = select_descriptor(connection, prospective(intent.task_bytes, intent.task_digest))
            config = select_descriptor(
                connection, prospective(configuration.canonical_bytes, configuration.digest)
            )
            prepared = PreparedAdmission(
                intent,
                configuration,
                project_id=context.project_id,
                job_id=job_id,
                origin=origin,
                task_binding=ArtifactBinding(
                    project_id=context.project_id,
                    job_id=job_id,
                    role="task",
                    descriptor=task,
                    plaintext=intent.task_bytes,
                ),
                configuration_binding=ArtifactBinding(
                    project_id=context.project_id,
                    job_id=job_id,
                    role="admission_config",
                    descriptor=config,
                    plaintext=configuration.canonical_bytes,
                ),
            )
            payload = prepared.bind_payload(
                select_descriptor(
                    connection, prospective(prepared.envelope_bytes, prepared.envelope_digest)
                )
            )
            self.authority.check(connection, principal, context, "record")
        return prepared, payload

    def _new_work(
        self,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        intent: CanonicalIntent,
        key_hash: str,
        origin: OriginCorrelation,
    ) -> dict[str, str]:
        opened, pending, known_commit = False, False, False
        outcome = TransactionOutcome()
        try:
            if self.journal is None:
                self._available()
                raise AdmissionError("dependency_unavailable")
            identity = JournalIdentity(
                context.organization_id,
                context.project_id,
                principal.principal_id,
                intent.client_operation_id,
                key_hash,
                intent.request_digest,
            )
            with self.journal.open(identity) as session:
                opened = True
                # A journal can never override a freshly authorized SQL winner.
                winner = self._recover(
                    principal,
                    context,
                    intent.client_operation_id,
                    key_hash,
                    intent.request_digest,
                    reconcile=False,
                    allow_absent=True,
                )
                if winner is not None:
                    known_commit = True
                    return winner
                if session.route == "reconcile":
                    pending = True
                    return self.reconcile(
                        principal,
                        context,
                        intent.client_operation_id,
                        key_hash,
                        intent.request_digest,
                    )
                self._available()
                if session.route == "new":
                    registry = self.registry
                    if type(registry) is not NativeRegistry or registry.entry is None:
                        raise AdmissionError("dependency_unavailable")
                    # Availability precedes the first durable binding. Actual trusted
                    # permission precedes resolve_new and binds its exact candidate.
                    first_origin = _journal_call(session.bind, origin)
                    permission = synchronous(
                        self.policy.permission(principal, context, intent, registry.entry)
                    )
                    if (
                        type(permission) is not ProcessorPermission
                        or permission.configuration_digest != registry.entry.digest
                        or permission.processor_profile != registry.entry.processor_profile
                    ):
                        raise AdmissionError("dependency_unavailable")
                    configuration = registry.resolve_new(
                        intent.adapter_config_id,
                        json.loads(intent.task_bytes)["image"],
                        permitted_processor_profile=permission.processor_profile,
                    )
                    evidence = synchronous(
                        self.policy.prepare(principal, context, intent, configuration)
                    )
                    if type(evidence) is not dict:
                        raise AdmissionError("dependency_unavailable")
                    evidence = validate_policy(
                        evidence, identity, intent.task_digest, configuration
                    )
                    operation_id, job_id = uuid.uuid4().hex, uuid.uuid4().hex
                    prepared, payload = self._prepare(
                        principal, context, intent, configuration, first_origin, job_id
                    )
                    _journal_call(
                        session.freeze_attempt,
                        prepared,
                        operation_id=operation_id,
                        payload=payload.descriptor,
                        policy=evidence,
                    )
                else:
                    prepared = _journal_call(session.restore, intent)
                    snapshot = session.snapshot
                    if snapshot is None:
                        raise AdmissionError("outcome_uncertain")
                    frozen = snapshot.data()
                    operation_id, evidence = frozen["operation_id"], frozen["policy"]
                    payload = prepared.bind_payload(metadata(frozen["descriptors"]["payload"]))
                # All publication policy uses the detached, validated frozen evidence.
                snapshot = session.snapshot
                if snapshot is None:
                    raise AdmissionError("outcome_uncertain")
                evidence = snapshot.data()["policy"]
                with admission_transaction(self.engine, TransactionOutcome()) as connection:
                    lock_authority(self.authority, connection, principal, context, None, None)
                    self._recheck(connection, principal, context, prepared, evidence)
                readiness, storage = self.readiness, self.storage
                if readiness is None or storage is None:
                    raise AdmissionError("dependency_unavailable")
                ready = synchronous(
                    readiness.check(principal, context, intent, prepared.configuration)
                )
                if type(ready) is not AdmissionReady or ready.ready is not True:
                    raise AdmissionError("dependency_unavailable")
                # The only loop is the known attempt pair, never a third retry.
                for attempt in range(2):
                    receipts: list[ObjectWriteResult] = []
                    for binding in (prepared.task_binding, prepared.configuration_binding, payload):
                        winner = self._recover(
                            principal,
                            context,
                            intent.client_operation_id,
                            key_hash,
                            intent.request_digest,
                            reconcile=False,
                            allow_absent=True,
                        )
                        if winner is not None:
                            known_commit = True
                            return winner
                        with admission_transaction(self.engine, TransactionOutcome()) as connection:
                            lock_authority(
                                self.authority, connection, principal, context, None, None
                            )
                            self._recheck(connection, principal, context, prepared, evidence)
                        _journal_call(session.upload_started, binding.role)
                        try:
                            receipt = storage.put_verified(binding.descriptor, binding.plaintext)
                        except BaseException:
                            # Preserve the first failure, but retain UNKNOWN work if
                            # possible. An unfinished durable start is also UNKNOWN.
                            with suppress(Exception):
                                session.upload_unknown(binding.role)
                            raise
                        validate_receipts((binding,), (receipt,))
                        _journal_call(session.upload_verified, binding.role, receipt)
                        receipts.append(receipt)
                    _journal_call(session.commit, "commit_pending")
                    pending = True
                    outcome = TransactionOutcome()
                    try:
                        with admission_transaction(self.engine, outcome) as connection:
                            original = self._locked_winner(
                                connection,
                                principal,
                                context,
                                intent.client_operation_id,
                                key_hash,
                                intent.request_digest,
                            )
                            if original is None:
                                self._recheck(connection, principal, context, prepared, evidence)
                                original = publish_rows(
                                    connection,
                                    self.authority,
                                    self.repository,
                                    principal,
                                    context,
                                    operation_id=operation_id,
                                    key_hash=key_hash,
                                    prepared=prepared,
                                    payload=payload,
                                    receipts=tuple(receipts),
                                    created_at=datetime.now(UTC),
                                )
                                final = self._resolve(
                                    connection,
                                    principal,
                                    context,
                                    intent.client_operation_id,
                                    key_hash,
                                    intent.request_digest,
                                )
                                if final.operation != original or final.needs_alias:
                                    raise AdmissionError("outcome_uncertain")
                                self._recheck(connection, principal, context, prepared, evidence)
                    except PublicationCollision as collision:
                        if (
                            attempt
                            or not outcome.confirmed_precommit_rollback
                            or outcome.cleanup_failed
                        ):
                            raise AdmissionError("dependency_unavailable") from None
                        winner = self._recover(
                            principal,
                            context,
                            intent.client_operation_id,
                            key_hash,
                            intent.request_digest,
                            reconcile=False,
                            allow_absent=True,
                        )
                        if winner is not None:
                            known_commit = True
                            return winner
                        with admission_transaction(self.engine, TransactionOutcome()) as connection:
                            lock_authority(
                                self.authority, connection, principal, context, None, None
                            )
                            if (
                                self._resolve(
                                    connection,
                                    principal,
                                    context,
                                    intent.client_operation_id,
                                    key_hash,
                                    intent.request_digest,
                                ).operation
                                is not None
                            ):
                                raise AdmissionError("outcome_uncertain") from None
                            replacement, new_payload, proof = prove_replacement(
                                connection, prepared, payload, collision
                            )
                            self._recheck(connection, principal, context, replacement, evidence)
                        _journal_call(
                            session.freeze_attempt,
                            replacement,
                            operation_id=operation_id,
                            payload=new_payload.descriptor,
                            policy=evidence,
                            outcome=outcome,
                            collision=proof,
                        )
                        prepared, payload = replacement, new_payload
                        pending = False  # Observed clean rollback; restart still reconciles.
                        continue
                    except AdmissionError:
                        if outcome.commit_attempted or not outcome.rollback_acknowledged:
                            with suppress(Exception):
                                session.commit("commit_unknown")
                        raise
                    known_commit = True
                    if original.id == operation_id and original.job_id == prepared.job_id:
                        _journal_call(session.commit, "commit_confirmed")
                    # A late winner with different intended IDs stays separate from
                    # the abandoned pending journal; never falsely confirm its IDs.
                    return self._disclose(
                        principal,
                        context,
                        original,
                        intent.client_operation_id,
                        key_hash,
                        intent.request_digest,
                    )
                raise AdmissionError("dependency_unavailable")
        except (IdentityInvalid, ResourceNotFound, ActionForbidden):
            raise
        except AdmissionError as error:
            if error.code == "dependency_unavailable" and (
                known_commit
                or outcome.commit_attempted
                or (outcome.rollback_attempted and not outcome.rollback_acknowledged)
            ):
                raise AdmissionError("outcome_uncertain") from None
            # Fixed dependency/policy errors must not expose a caller's active
            # exception or an adapter's private cause outside the journal path.
            raise error from None
        except Exception:
            if not opened and self.journal is not None:
                # Busy, corrupt, partial and unreadable journals provide no absence
                # proof. A bounded SQL-only check may still recover an exact winner.
                return self.reconcile(
                    principal, context, intent.client_operation_id, key_hash, intent.request_digest
                )
            raise AdmissionError(
                "outcome_uncertain" if pending or known_commit else "dependency_unavailable"
            ) from None
