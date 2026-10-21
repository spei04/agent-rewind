"""Required legacy work-admission contract; no supported production adapter yet.

AR-008-A/B and AR-010-B must supply reviewed scoped identity/configuration,
publication and dispatch semantics. There is deliberately no enqueue fallback.
"""

from typing import Any, Literal, Protocol

from .errors import Fault
from .request_identity import VerifiedPrincipal
from .scoped_repositories import ProjectContext

WorkKind = Literal["run", "branch", "study", "investigate"]


class WorkAdmission(Protocol):
    def require_available(self) -> None: ...
    def admit(
        self,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        kind: WorkKind,
        body: dict[str, Any],
    ) -> str: ...


class UnavailableAdmission:
    def require_available(self) -> None:
        raise Fault("dependency_unavailable")

    def admit(
        self,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        kind: WorkKind,
        body: dict[str, Any],
    ) -> str:
        self.require_available()
        raise Fault("dependency_unavailable")
