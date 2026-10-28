"""Strict private P2 records and refusals; no dispatch or transaction authority."""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Literal

from .admission_transaction import AdmissionCode, AdmissionError, TransactionOutcome

MAX_MONEY = 2**63 - 1
RefusalReason = Literal[
    "invalid_intent",
    "invocation_reused",
    "unsupported_job",
    "job_not_live",
    "budget_exceeded",
    "identity_conflict",
    "schema_or_provenance_invalid",
    "ledger_state_invalid",
    "capacity_exceeded",
    "transaction_not_owned",
]
_REASONS: dict[str, AdmissionCode] = {
    "invalid_intent": "invalid_request",
    "invocation_reused": "invalid_request",
    "unsupported_job": "invalid_request",
    "job_not_live": "invalid_request",
    "budget_exceeded": "invalid_request",
    "identity_conflict": "idempotency_conflict",
    "schema_or_provenance_invalid": "schema_incompatible",
    "ledger_state_invalid": "dependency_unavailable",
    "capacity_exceeded": "dependency_unavailable",
    "transaction_not_owned": "dependency_unavailable",
}


class ReservationRefusal(AdmissionError):
    """A finite private reason; its code never proves transaction rollback."""

    def __init__(self, reason: RefusalReason):
        if type(reason) is not str or reason not in _REASONS:
            raise ValueError("invalid_refusal_reason")
        self.reason = reason
        super().__init__(_REASONS[reason])


def _identifier(value: str, width: int = 32) -> None:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{" + str(width) + "}", value) is None:
        raise ReservationRefusal("invalid_intent")


def _integer(value: int, minimum: int = 0, maximum: int = MAX_MONEY) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ReservationRefusal("invalid_intent")


def _choice(value: str, choices: set[str]) -> None:
    if type(value) is not str or value not in choices:
        raise ReservationRefusal("invalid_intent")


@dataclass(frozen=True)
class ClaimIntent:
    job_id: str
    owner_uuid: str
    expected_generation: int
    lease_seconds: int

    def __post_init__(self) -> None:
        _identifier(self.job_id)
        _identifier(self.owner_uuid)
        _integer(self.expected_generation, maximum=MAX_MONEY - 1)
        _integer(self.lease_seconds, 1, 60)


@dataclass(frozen=True)
class JobFence:
    job_id: str
    owner_uuid: str
    generation: int

    def __post_init__(self) -> None:
        _identifier(self.job_id)
        _identifier(self.owner_uuid)
        _integer(self.generation, 1)


@dataclass(frozen=True)
class ReservationIntent:
    call_id: str
    project_id: str
    job_id: str
    logical_call_id: str
    request_digest: str
    purpose: Literal["continuation", "discovery"]
    price_version: str
    reserved_microusd: int
    lease_generation: int
    organization_account_id: str
    project_account_id: str
    job_account_id: str

    def __post_init__(self) -> None:
        for value in (
            self.call_id,
            self.project_id,
            self.job_id,
            self.logical_call_id,
            self.organization_account_id,
            self.project_account_id,
            self.job_account_id,
        ):
            _identifier(value)
        _identifier(self.request_digest, 64)
        _choice(self.purpose, {"continuation", "discovery"})
        if type(self.price_version) is not str or not 1 <= len(self.price_version) <= 128:
            raise ReservationRefusal("invalid_intent")
        if any(unicodedata.category(char).startswith("C") for char in self.price_version):
            raise ReservationRefusal("invalid_intent")
        if len(self.price_version.encode("utf-8")) > 128:
            raise ReservationRefusal("invalid_intent")
        _integer(self.reserved_microusd)
        _integer(self.lease_generation, 1)
        if len({self.organization_account_id, self.project_account_id, self.job_account_id}) != 3:
            raise ReservationRefusal("invalid_intent")


CallState = Literal["reserved", "dispatching", "observed", "uncertain", "reconciled"]


@dataclass(frozen=True)
class ReservationRecord:
    identity: ReservationIntent
    state: CallState
    settled_microusd: int
    released_microusd: int

    def __post_init__(self) -> None:
        if type(self.identity) is not ReservationIntent:
            raise ReservationRefusal("invalid_intent")
        self.identity.__post_init__()
        _choice(self.state, {"reserved", "dispatching", "observed", "uncertain", "reconciled"})
        _integer(self.settled_microusd)
        _integer(self.released_microusd)
        amount = self.identity.reserved_microusd
        if (
            self.settled_microusd > amount
            or self.released_microusd > amount - self.settled_microusd
        ):
            raise ReservationRefusal("invalid_intent")


@dataclass(frozen=True)
class JobObservation:
    job_id: str
    owner_uuid: str | None
    generation: int
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    lease_until: int | float | None

    def __post_init__(self) -> None:
        _identifier(self.job_id)
        if self.owner_uuid is not None:
            _identifier(self.owner_uuid)
        _integer(self.generation)
        _choice(self.status, {"queued", "running", "succeeded", "failed", "cancelled"})
        if self.lease_until is not None:
            if type(self.lease_until) is int:
                if not -MAX_MONEY - 1 <= self.lease_until <= MAX_MONEY:
                    raise ReservationRefusal("invalid_intent")
            elif type(self.lease_until) is not float or not math.isfinite(self.lease_until):
                raise ReservationRefusal("invalid_intent")


def _record(value: ReservationRecord) -> None:
    if type(value) is not ReservationRecord:
        raise ReservationRefusal("invalid_intent")
    value.__post_init__()


@dataclass(frozen=True)
class CreatedReservation:
    record: ReservationRecord
    kind: Literal["created"] = field(default="created", init=False)

    def __post_init__(self) -> None:
        _record(self.record)


@dataclass(frozen=True)
class OriginalReservation:
    record: ReservationRecord
    kind: Literal["original"] = field(default="original", init=False)

    def __post_init__(self) -> None:
        _record(self.record)


ReservationDecision = CreatedReservation | OriginalReservation


@dataclass(frozen=True)
class CallNotRequested:
    kind: Literal["not_requested"] = field(default="not_requested", init=False)


@dataclass(frozen=True)
class CallAbsent:
    kind: Literal["absent"] = field(default="absent", init=False)


@dataclass(frozen=True)
class CallConflict:
    kind: Literal["conflict"] = field(default="conflict", init=False)


@dataclass(frozen=True)
class CallMatching:
    record: ReservationRecord
    kind: Literal["matching"] = field(default="matching", init=False)

    def __post_init__(self) -> None:
        _record(self.record)


CallObservation = CallNotRequested | CallAbsent | CallConflict | CallMatching


@dataclass(frozen=True)
class InspectionResult:
    job: JobObservation
    call: CallObservation

    def __post_init__(self) -> None:
        if type(self.job) is not JobObservation or type(self.call) not in {
            CallNotRequested,
            CallAbsent,
            CallConflict,
            CallMatching,
        }:
            raise ReservationRefusal("invalid_intent")
        self.job.__post_init__()
        if isinstance(self.call, CallMatching):
            self.call.__post_init__()


@dataclass(frozen=True)
class TransactionFacts:
    """Detached facts remain available after an exception; callers cannot reset them."""

    begun: bool
    commit_attempted: bool
    commit_acknowledged: bool
    rollback_attempted: bool
    rollback_acknowledged: bool
    cleanup_failed: bool

    def __post_init__(self) -> None:
        if any(
            type(value) is not bool
            for value in (
                self.begun,
                self.commit_attempted,
                self.commit_acknowledged,
                self.rollback_attempted,
                self.rollback_acknowledged,
                self.cleanup_failed,
            )
        ):
            raise ReservationRefusal("invalid_intent")

    @classmethod
    def observe(cls, outcome: TransactionOutcome) -> TransactionFacts:
        return cls(
            outcome.begun,
            outcome.commit_attempted,
            outcome.commit_acknowledged,
            outcome.rollback_attempted,
            outcome.rollback_acknowledged,
            outcome.cleanup_failed,
        )

    @property
    def confirmed_precommit_rollback(self) -> bool:
        return self.begun and not self.commit_attempted and self.rollback_acknowledged
