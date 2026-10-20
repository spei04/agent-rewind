"""Offline frozen-byte verification; no scoped registration or customer hash reader."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from .artifact_graph import GraphRef, decode, verify_run_capture_bytes
from .artifact_metadata import ArtifactError, digest_value, identifier
from .bounded_bytes import (
    BoundedReadError,
    ciphertext_limit,
    decrypt_checked,
    directory,
    read_ciphertext,
    regular_reader,
)
from .models import canonical, digest
from .projection_source import CohortIdentity, SQLCohort
from .run_projection import MAX_CAPTURE_BYTES, MAX_COHORT_BYTES, RunProjection, classify_capture

OperatorReader = Callable[[str, str, str, str, int], bytes]


class FrozenLegacySource:
    """Explicit operator-only reader for a separately frozen legacy object tree.

    The operator must keep this byte view immutable throughout the operation.
    Verification binds bytes actually observed, not future filesystem availability.
    It creates no artifact metadata/ref and cannot authorize customer access.
    """

    def __init__(self, root: Path, cipher: Fernet):
        self.root, self.cipher = root, cipher

    def __call__(self, project: str, owner: str, role: str, address: str, limit: int) -> bytes:
        identifier(project)
        GraphRef(owner, role, address)
        digest_value(address)
        try:
            bound = ciphertext_limit(limit)
            with (
                directory(self.root, ("objects",)) as parent,
                regular_reader(address, dir_fd=parent, limit=bound) as stream,
            ):
                ciphertext = read_ciphertext(stream, limit=bound)
            return decrypt_checked(ciphertext, self.cipher, address, plaintext_limit=limit)
        except FileNotFoundError:
            raise ArtifactError("projection_evidence_missing") from None
        except (OSError, BoundedReadError, InvalidToken):
            raise ArtifactError("projection_evidence_invalid") from None


@dataclass(frozen=True)
class PreparedCohort:
    identity: CohortIdentity
    rows: tuple[RunProjection, ...]
    evidence_digest: str
    retained_bytes: int
    bytes_read: int


def projection_identity(row: RunProjection) -> dict[str, object]:
    return {**asdict(row), "created_at": row.created_at.isoformat()}


def prepare_evidence(cohort: SQLCohort, reader: OperatorReader) -> PreparedCohort:
    """Verify sequentially, dropping each graph's bytes before the next capture."""
    total_bytes = 0
    retained = 0
    rows: list[RunProjection] = []
    evidence: list[str] = []
    for run_id in cohort.order:
        project, encoded = cohort.captures[run_id]
        # Count the currently decoded capture in addition to retained immutable
        # cohort bytes and already prepared row metadata (canonical byte units).
        if retained + len(encoded) + cohort.retained_bytes > MAX_COHORT_BYTES:
            raise ArtifactError("projection_cohort_limit")

        def fetch(ref: GraphRef, limit: int, project: str = project) -> bytes:
            nonlocal total_bytes
            remaining = min(limit, MAX_CAPTURE_BYTES - total_bytes)
            value = reader(project, ref.owner_id, ref.role, ref.digest, remaining)
            if not isinstance(value, bytes) or len(value) > remaining:
                raise ArtifactError("projection_evidence_limit")
            total_bytes += len(value)
            return value

        verified = verify_run_capture_bytes(encoded, fetch)
        row = classify_capture(project, decode(encoded), verified)
        size = len(canonical([projection_identity(row), verified.evidence_digest]))
        if retained + size + cohort.retained_bytes > MAX_COHORT_BYTES:
            raise ArtifactError("projection_cohort_limit")
        retained += size
        rows.append(row)
        evidence.append(verified.evidence_digest)
    return PreparedCohort(cohort.identity, tuple(rows), digest(evidence), retained, total_bytes)
