"""Disconnected normalization of an explicit fictional Python-row profile.

Only consistency of independently supplied qualification is checked here. No
source acquisition, evaluator execution, rights issuance or runtime dispatch.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import ConfigDict, Field, ValidationError, field_validator

from .corpus import Identifier, ManifestTimestamp, PrivateObject, Purpose, Revision, Sha256
from .models import StrictModel, canonical, valid_path
from .public_corpus import (
    PublicCandidate,
    PublicDeclarationPolicy,
    validate_public_candidate_manifest,
)

SYNTHETIC_PROFILE = "swe-rebench-python-synthetic-v1"
NORMALIZER_PROFILE = "swe-rebench-disconnected-v1"
MAX_ROW_BYTES = 8 * 1024 * 1024
MAX_BATCH_BYTES = 8 * 1024 * 1024
MAX_CANDIDATES = 1000
MAX_FILES = 2000
_DIGEST = re.compile(r"[0-9a-f]{64}")

Outcome = Literal["pass", "fail", "rejected", "error", "unknown"]
DecisionStatus = Literal["next-gate", "quarantine", "unsupported"]
DecisionCode = Literal[
    "qualified-synthetic",
    "missing-row",
    "invalid-row",
    "row-too-large",
    "batch-too-large",
    "unsupported-profile",
    "unsupported-language",
    "unsupported-state",
    "state-too-large",
    "future-row",
    "missing-qualification",
    "invalid-qualification",
    "qualification-not-reviewed",
    "qualification-not-current",
    "binding-mismatch",
    "qualification-controls-failed",
    "context-not-qualified",
    "state-not-qualified",
]
BatchCode = Literal["invalid-policy", "invalid-rows", "invalid-qualifications", "synthetic-only"]


class NormalizationError(ValueError):
    """A fixed public code, never supplied row content or validation details."""

    def __init__(self, code: BatchCode):
        self.code = code
        super().__init__(code)


class _Contract(StrictModel):
    model_config = ConfigDict(frozen=True, revalidate_instances="always")


class _Evaluator(_Contract):
    reference_patch: str
    test_files: dict[str, str]
    command: str = Field(min_length=1, max_length=4000)
    image_digest: Sha256


class _PrivateMetadata(_Contract):
    repository: str = Field(min_length=1, max_length=512)
    instance: str = Field(min_length=1, max_length=512)
    pull_request_text: str
    labels: list[str] = Field(max_length=32)
    logs: str
    image_name: str = Field(min_length=1, max_length=512)

    @field_validator("labels")
    @classmethod
    def unique_labels(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value) or any(not 1 <= len(v) <= 80 for v in value):
            raise ValueError("Invalid fictional labels.")
        return value


class _SyntheticRow(_Contract):
    profile: Literal["swe-rebench-python-synthetic-v1"]
    language: str = Field(min_length=1, max_length=32)
    synthetic_created_at: ManifestTimestamp
    state_kind: str = Field(min_length=1, max_length=32)
    base_revision: Revision
    instruction: str = Field(min_length=1, max_length=20000)
    base_files: dict[str, str]
    evaluator: _Evaluator
    private_metadata: _PrivateMetadata


SYNTHETIC_SCHEMA_SHA256 = hashlib.sha256(canonical(_SyntheticRow.model_json_schema())).hexdigest()


class QualificationReceipt(_Contract):
    """Caller-reviewed supplied statements, not observations made by this module."""

    receipt_profile: Literal["swe-rebench-qualification-synthetic-v1"]
    candidate_id: Identifier
    declaration_sha256: Sha256
    row_sha256: Sha256
    dataset_revision: Revision
    card_sha256: Sha256
    source_revision: Revision
    source_sha256: Sha256
    field_policy_sha256: Sha256
    schema_sha256: Sha256
    normalizer_profile: Literal["swe-rebench-disconnected-v1"]
    normalizer_sha256: Sha256
    processor_id: Identifier
    purpose: Purpose
    inference_sha256: Sha256
    evaluator_revision: Revision
    evaluator_sha256: Sha256
    command_sha256: Sha256
    image_digest: Sha256
    evidence: PrivateObject
    issued_at: ManifestTimestamp
    expires_at: ManifestTimestamp
    original: tuple[Outcome, ...] = Field(min_length=3, max_length=32)
    reference: tuple[Outcome, ...] = Field(min_length=3, max_length=32)
    invalid: tuple[Outcome, ...] = Field(min_length=3, max_length=32)
    tamper: tuple[Outcome, ...] = Field(min_length=3, max_length=32)
    answer_blind_context: bool
    supported_state: bool

    @field_validator("evidence", mode="before")
    @classmethod
    def current_evidence(cls, value: Any) -> Any:
        # Existing C02 references are mutable; do not trust instance validation.
        return dict(value) if type(value) is PrivateObject else value


@dataclass(frozen=True)
class SuppliedRow:
    candidate_id: str
    raw: bytes | str


@dataclass(frozen=True)
class NormalizationPolicy:
    """Trusted configuration supplied outside row/receipt JSON.

    The caller verifies actual implementation identity and accepted receipt
    provenance. A digest does not authenticate an issuer by itself.
    """

    declaration: PublicDeclarationPolicy
    normalizer_sha256: str
    reviewed_receipts: frozenset[str]
    checked_at: datetime


@dataclass(frozen=True)
class InferenceManifest:
    instruction: str
    files: tuple[tuple[str, str], ...]

    def encoded(self) -> bytes:
        return canonical(
            {
                "profile": "answer-blind-inference-v1",
                "instruction": self.instruction,
                "files": dict(self.files),
            }
        )

    @property
    def cache_identity(self) -> str:
        return hashlib.sha256(self.encoded()).hexdigest()


@dataclass(frozen=True)
class EvaluatorManifest:
    reference_patch: str
    test_files: tuple[tuple[str, str], ...]
    command: str
    image_digest: str

    def encoded(self) -> bytes:
        return canonical(
            {
                "reference_patch": self.reference_patch,
                "test_files": dict(self.test_files),
                "command": self.command,
                "image_digest": self.image_digest,
            }
        )


@dataclass(frozen=True)
class PrivateLineage:
    candidate_id: str
    declaration_sha256: str
    row_sha256: str
    receipt_sha256: str


@dataclass(frozen=True)
class CandidateDecision:
    candidate_id: str
    status: DecisionStatus
    code: DecisionCode
    inference: InferenceManifest | None = None
    evaluator: EvaluatorManifest | None = None
    lineage: PrivateLineage | None = None


@dataclass(frozen=True)
class NormalizationBatch:
    decisions: tuple[CandidateDecision, ...]

    @property
    def counts(self) -> dict[str, int]:
        return {
            "declared": len(self.decisions),
            **{
                status: sum(d.status == status for d in self.decisions)
                for status in ("next-gate", "quarantine", "unsupported")
            },
        }


def _utc(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("An aware instant is required.")
    return value.astimezone(UTC)


def _policy(policy: NormalizationPolicy, now: datetime) -> datetime:
    try:
        current = _utc(now)
        if (
            type(policy) is not NormalizationPolicy
            or type(policy.normalizer_sha256) is not str
            or _DIGEST.fullmatch(policy.normalizer_sha256) is None
            or type(policy.reviewed_receipts) is not frozenset
            or len(policy.reviewed_receipts) > MAX_CANDIDATES
            or any(
                type(v) is not str or _DIGEST.fullmatch(v) is None for v in policy.reviewed_receipts
            )
            or _utc(policy.checked_at) != current
        ):
            raise ValueError("Invalid current policy.")
        return current
    except (ValueError, TypeError, AttributeError, OverflowError, RecursionError):
        raise NormalizationError("invalid-policy") from None


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON member.")
        result[key] = value
    return result


def _nonfinite(value: str) -> Any:
    raise ValueError("Nonfinite JSON value.")


def _encoded(raw: bytes | str) -> bytes:
    if type(raw) not in (bytes, str):
        raise ValueError("Invalid raw value.")
    return raw.encode("utf-8") if isinstance(raw, str) else raw


def _inputs(
    rows: tuple[SuppliedRow, ...],
    qualifications: tuple[QualificationReceipt, ...],
    candidate_ids: set[str],
) -> tuple[dict[str, SuppliedRow], dict[str, QualificationReceipt]]:
    if type(rows) is not tuple or len(rows) > MAX_CANDIDATES:
        raise NormalizationError("invalid-rows")
    supplied: dict[str, SuppliedRow] = {}
    for row in rows:
        if (
            type(row) is not SuppliedRow
            or type(row.candidate_id) is not str
            or row.candidate_id not in candidate_ids
            or row.candidate_id in supplied
        ):
            raise NormalizationError("invalid-rows")
        supplied[row.candidate_id] = row
    if type(qualifications) is not tuple or len(qualifications) > MAX_CANDIDATES:
        raise NormalizationError("invalid-qualifications")
    receipts: dict[str, QualificationReceipt] = {}
    for receipt in qualifications:
        if type(receipt) is not QualificationReceipt:
            raise NormalizationError("invalid-qualifications")
        identifier = getattr(receipt, "candidate_id", None)
        if type(identifier) is not str or identifier not in candidate_ids or identifier in receipts:
            raise NormalizationError("invalid-qualifications")
        receipts[identifier] = receipt
    return supplied, receipts


def _row(raw: bytes | str, now: datetime) -> tuple[_SyntheticRow | None, DecisionCode]:
    try:
        if type(raw) in (bytes, str) and len(raw) > MAX_ROW_BYTES:
            return None, "row-too-large"
        encoded = _encoded(raw)
        if len(encoded) > MAX_ROW_BYTES:
            return None, "row-too-large"
        value = json.loads(
            encoded.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_nonfinite
        )
        if (
            type(value) is dict
            and type(value.get("profile")) is str
            and value["profile"] != SYNTHETIC_PROFILE
        ):
            return None, "unsupported-profile"
        # Escaped unpaired surrogates are not valid UTF-8 source text.
        json.dumps(value, ensure_ascii=False).encode("utf-8")
        row = _SyntheticRow.model_validate(value)
        if _utc(row.synthetic_created_at) > now:
            return None, "future-row"
        for files in (row.base_files, row.evaluator.test_files):
            for path in files:
                valid_path(path)
                if re.search(r"[\x00-\x1f\x7f]", path):
                    raise ValueError("Control character in path.")
        if set(row.base_files) & set(row.evaluator.test_files):
            raise ValueError("Overlapping private evaluator path.")
        if row.language != "python":
            return None, "unsupported-language"
        if row.state_kind != "file-tree":
            return None, "unsupported-state"
        if (
            len(row.base_files) + len(row.evaluator.test_files) > MAX_FILES
            or len(canonical(row.model_dump(mode="json"))) > MAX_ROW_BYTES
        ):
            return None, "state-too-large"
        return row, "qualified-synthetic"
    except (ValidationError, ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        return None, "invalid-row"


def _receipt(
    supplied: QualificationReceipt,
    policy: NormalizationPolicy,
    now: datetime,
) -> tuple[QualificationReceipt | None, str, DecisionCode]:
    try:
        receipt = QualificationReceipt.model_validate(dict(supplied))
        json.dumps(receipt.model_dump(mode="json"), ensure_ascii=False).encode("utf-8")
        raw = canonical(receipt.model_dump(mode="json"))
        if len(raw) > MAX_ROW_BYTES:
            raise ValueError("Oversize receipt.")
        digest = hashlib.sha256(raw).hexdigest()
        if digest not in policy.reviewed_receipts:
            return None, digest, "qualification-not-reviewed"
        issued, expires = _utc(receipt.issued_at), _utc(receipt.expires_at)
        if not issued <= now < expires:
            return None, digest, "qualification-not-current"
        return receipt, digest, "qualified-synthetic"
    except (ValidationError, ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        return None, "", "invalid-qualification"


def _decision(
    candidate: PublicCandidate,
    raw: bytes | str,
    supplied_receipt: QualificationReceipt | None,
    policy: NormalizationPolicy,
    declaration_sha256: str,
    now: datetime,
) -> CandidateDecision:
    identifier = candidate.candidate_id
    row, code = _row(raw, now)
    if row is None:
        status: DecisionStatus = (
            "unsupported"
            if code
            in {
                "row-too-large",
                "state-too-large",
                "unsupported-profile",
                "unsupported-language",
                "unsupported-state",
            }
            else "quarantine"
        )
        return CandidateDecision(identifier, status, code)
    if supplied_receipt is None:
        return CandidateDecision(identifier, "quarantine", "missing-qualification")
    receipt, receipt_digest, code = _receipt(supplied_receipt, policy, now)
    if receipt is None:
        return CandidateDecision(identifier, "quarantine", code)
    inference = InferenceManifest(row.instruction, tuple(sorted(row.base_files.items())))
    evaluator = EvaluatorManifest(
        row.evaluator.reference_patch,
        tuple(sorted(row.evaluator.test_files.items())),
        row.evaluator.command,
        row.evaluator.image_digest,
    )
    row_digest = hashlib.sha256(_encoded(raw)).hexdigest()
    source_digest = hashlib.sha256(canonical({"files": row.base_files})).hexdigest()
    evaluator_digest = hashlib.sha256(evaluator.encoded()).hexdigest()
    command_digest = hashlib.sha256(row.evaluator.command.encode("utf-8")).hexdigest()
    actual = (
        identifier,
        declaration_sha256,
        row_digest,
        candidate.dataset.revision,
        candidate.dataset.artifact.sha256,
        candidate.source.revision,
        source_digest,
        candidate.source_policy.sha256,
        SYNTHETIC_SCHEMA_SHA256,
        NORMALIZER_PROFILE,
        policy.normalizer_sha256,
        policy.declaration.admission.processor_id,
        policy.declaration.admission.purpose,
        inference.cache_identity,
        candidate.evaluator.revision,
        evaluator_digest,
        command_digest,
        row.evaluator.image_digest,
    )
    bound = (
        receipt.candidate_id,
        receipt.declaration_sha256,
        receipt.row_sha256,
        receipt.dataset_revision,
        receipt.card_sha256,
        receipt.source_revision,
        receipt.source_sha256,
        receipt.field_policy_sha256,
        receipt.schema_sha256,
        receipt.normalizer_profile,
        receipt.normalizer_sha256,
        receipt.processor_id,
        receipt.purpose,
        receipt.inference_sha256,
        receipt.evaluator_revision,
        receipt.evaluator_sha256,
        receipt.command_sha256,
        receipt.image_digest,
    )
    if (
        actual != bound
        or candidate.row.sha256 != row_digest
        or candidate.source.artifact.sha256 != source_digest
        or row.base_revision != candidate.source.revision
        or candidate.evaluator.artifact.sha256 != evaluator_digest
        or candidate.evaluator.command_sha256 != command_digest
        or candidate.evaluator.image_digest != row.evaluator.image_digest
    ):
        return CandidateDecision(identifier, "quarantine", "binding-mismatch")
    if not (
        all(v == "fail" for v in receipt.original)
        and all(v == "pass" for v in receipt.reference)
        and all(v in ("fail", "rejected") for v in receipt.invalid)
        and all(v in ("fail", "rejected") for v in receipt.tamper)
    ):
        return CandidateDecision(identifier, "quarantine", "qualification-controls-failed")
    if not receipt.answer_blind_context:
        return CandidateDecision(identifier, "quarantine", "context-not-qualified")
    if not receipt.supported_state:
        return CandidateDecision(identifier, "quarantine", "state-not-qualified")
    return CandidateDecision(
        identifier,
        "next-gate",
        "qualified-synthetic",
        inference,
        evaluator,
        PrivateLineage(identifier, declaration_sha256, row_digest, receipt_digest),
    )


def normalize_swe_rebench(
    declaration: bytes | str,
    rows: tuple[SuppliedRow, ...],
    *,
    policy: NormalizationPolicy,
    qualifications: tuple[QualificationReceipt, ...],
    now: datetime,
) -> NormalizationBatch:
    """Normalize supplied fictional inputs without resolving any reference.

    Every declared candidate has one ordered outcome. Batch-level ambiguity
    refuses completely; no partial results or execution permission are issued.
    """
    current = _policy(policy, now)
    manifest = validate_public_candidate_manifest(
        declaration, policy=policy.declaration, now=current
    )
    if manifest.evidence_class != "synthetic":
        raise NormalizationError("synthetic-only")
    supplied, receipts = _inputs(
        rows, qualifications, {c.candidate_id for c in manifest.candidates}
    )
    total = 0
    for row in rows:
        if type(row.raw) not in (bytes, str):
            continue
        if len(row.raw) > MAX_BATCH_BYTES:
            total = MAX_BATCH_BYTES + 1
            break
        try:
            total += len(_encoded(row.raw))
        except UnicodeError:
            continue
        if total > MAX_BATCH_BYTES:
            break
    if total > MAX_BATCH_BYTES:
        return NormalizationBatch(
            tuple(
                CandidateDecision(c.candidate_id, "unsupported", "batch-too-large")
                for c in manifest.candidates
            )
        )
    declaration_digest = hashlib.sha256(_encoded(declaration)).hexdigest()
    decisions = []
    for candidate in manifest.candidates:
        supplied_row = supplied.get(candidate.candidate_id)
        if supplied_row is None:
            decisions.append(CandidateDecision(candidate.candidate_id, "quarantine", "missing-row"))
        else:
            decisions.append(
                _decision(
                    candidate,
                    supplied_row.raw,
                    receipts.get(candidate.candidate_id),
                    policy,
                    declaration_digest,
                    current,
                )
            )
    return NormalizationBatch(tuple(decisions))
