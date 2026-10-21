"""Required internal new-admission dependencies; all defaults refuse work.

A policy adapter must implement actual caller/corpus permission and coordinate its
same-Connection recheck with project-first writers (or immutable version evidence).
These protocols do not deploy such a policy or grant a processor permission.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.engine import Connection

from .admission_configuration import NativeConfiguration
from .admission_request import CanonicalIntent
from .admission_transaction import AdmissionError
from .request_identity import VerifiedPrincipal
from .scoped_repositories import ProjectContext


@dataclass(frozen=True)
class ProcessorPermission:
    """Trusted adapter decision for this exact candidate, not a registry grant."""

    configuration_digest: str
    processor_profile: str


@dataclass(frozen=True)
class AdmissionReady:
    ready: bool


def synchronous(value: Any) -> Any:
    """Never bridge an event loop or interpret an awaitable as readiness/grant."""
    if inspect.isawaitable(value):
        if inspect.iscoroutine(value):
            value.close()
        raise AdmissionError("dependency_unavailable")
    return value


def completed(call: Callable[..., object], *args: Any) -> None:
    """Validate a no-value policy hook without accepting async completion."""
    if synchronous(call(*args)) is not None:
        raise AdmissionError("dependency_unavailable")


class AdmissionPolicy(Protocol):
    def require_available(self) -> None:
        """Pure availability preflight, before new intent/config/readiness/I/O."""
        ...

    def permission(
        self,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        intent: CanonicalIntent,
        candidate: NativeConfiguration,
    ) -> ProcessorPermission:
        """Establish actual permission before NativeRegistry.resolve_new."""
        ...

    def prepare(
        self,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        intent: CanonicalIntent,
        configuration: NativeConfiguration,
    ) -> dict[str, Any]:
        """Bounded credential-free evidence in the exact admission policy schema."""
        ...

    def recheck(
        self,
        connection: Connection,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        intent: CanonicalIntent,
        configuration: NativeConfiguration,
        evidence: dict[str, Any],
    ) -> None:
        """SQL/pure only on this Connection; no external I/O or new connection."""
        ...


class AdmissionReadiness(Protocol):
    def check(
        self,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        intent: CanonicalIntent,
        configuration: NativeConfiguration,
    ) -> AdmissionReady:
        """Bounded synchronous check outside SQL; not the async HTTP Readiness API."""
        ...


class UnavailableAdmissionPolicy:
    def require_available(self) -> None:
        raise AdmissionError("dependency_unavailable")

    def permission(
        self,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        intent: CanonicalIntent,
        candidate: NativeConfiguration,
    ) -> ProcessorPermission:
        raise AdmissionError("dependency_unavailable")

    def prepare(
        self,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        intent: CanonicalIntent,
        configuration: NativeConfiguration,
    ) -> dict[str, Any]:
        raise AdmissionError("dependency_unavailable")

    def recheck(
        self,
        connection: Connection,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        intent: CanonicalIntent,
        configuration: NativeConfiguration,
        evidence: dict[str, Any],
    ) -> None:
        raise AdmissionError("dependency_unavailable")
