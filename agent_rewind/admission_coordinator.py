"""Preparatory admission recovery: SQL winners only, no successful new-work path.

The default release guard still refuses migration-only schemas. Tests may replace
only one instance's compatibility observation with a synthetic supported result;
this is not a packaged ready profile. No registry/policy/readiness/journal/storage
adapter is invoked here. Full new-work publication is a later P3 checkpoint.
"""

from __future__ import annotations

from sqlalchemy.engine import Connection, Engine

from .admission_envelope import OriginCorrelation
from .admission_records import AdmissionStorageError, StoredOperation, hexadecimal
from .admission_repository import AdmissionIdentityConflict, AdmissionRepository, IdentityResolution
from .admission_request import CanonicalIntent
from .admission_transaction import AdmissionError, TransactionOutcome, admission_transaction
from .migrations.compatibility import CompatibilityResult, runtime_schema_compatibility
from .request_authority import RequestAuthority
from .request_identity import VerifiedPrincipal
from .scoped_locks import lock_authority, lock_resource
from .scoped_repositories import ProjectContext


class AdmissionCoordinator:
    """Original context and creator-record recovery; never viewer status disclosure."""

    def __init__(self, engine: Engine, authority: RequestAuthority):
        self.engine, self.authority = engine, authority
        self.repository = AdmissionRepository(authority)

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
        return self._recover(
            principal,
            original_context,
            intent.client_operation_id,
            key_hash,
            intent.request_digest,
            reconcile=False,
        )

    def reconcile(
        self,
        principal: VerifiedPrincipal,
        original_context: ProjectContext,
        client_operation_id: str,
        key_hash: str,
        request_digest: str,
    ) -> dict[str, str]:
        return self._recover(
            principal,
            original_context,
            client_operation_id,
            key_hash,
            request_digest,
            reconcile=True,
        )

    def _recover(
        self,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        client_operation_id: str,
        key_hash: str,
        request_digest: str,
        *,
        reconcile: bool,
    ) -> dict[str, str]:
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
                # Both identities precede all new-work adapters and locking.
                first = self._resolve(
                    connection, principal, context, client_operation_id, key_hash, request_digest
                )
                lock_authority(self.authority, connection, principal, context, None, None)
                locked = self._resolve(
                    connection, principal, context, client_operation_id, key_hash, request_digest
                )
                original = locked.operation
                if original is None:
                    raise AdmissionError(
                        "outcome_uncertain" if reconcile else "dependency_unavailable"
                    )
                if first.operation is not None and first.operation != original:
                    raise AdmissionError("outcome_uncertain")
                lock_resource(connection, context, "job", original.job_id, shared=True)
                verified = self._resolve(
                    connection, principal, context, client_operation_id, key_hash, request_digest
                )
                if verified.operation != original:
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
            # SQL is released before fresh original-context disclosure. No lookup
            # through get_operation: its viewer status permission is insufficient.
            return self._disclose(
                principal, context, original, client_operation_id, key_hash, request_digest
            )
        except AdmissionError as error:
            if error.code == "dependency_unavailable" and (reconcile or outcome.commit_attempted):
                raise AdmissionError("outcome_uncertain") from None
            raise

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
