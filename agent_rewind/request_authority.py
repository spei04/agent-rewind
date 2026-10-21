"""Fresh explicit project decisions; no HTTP, mutation or admission wiring."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import and_, case, select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from .ownership import allows_project_action
from .request_identity import IdentityInvalid, VerifiedPrincipal
from .scoped_lineage import ResourceNotFound, identifier
from .scoped_repositories import (
    ProjectContext,
    RepositoryUnavailable,
    ScopedRepositories,
    _byte_length,
    _Reads,
    members,
    organizations,
    projects,
)
from .sqlite_ownership import owned_connect


class ActionForbidden(PermissionError):
    """An accessible project/resource exists, but its current role denies action."""

    def __init__(self) -> None:
        super().__init__("This action is not permitted.")


@dataclass(frozen=True)
class ProjectDecision:
    """A result for one check, never a durable authorization capability."""

    context: ProjectContext
    role: str


class RequestAuthority:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.repositories = ScopedRepositories(engine)

    @staticmethod
    def _principal(principal: VerifiedPrincipal) -> str:
        if not isinstance(principal, VerifiedPrincipal):
            raise IdentityInvalid()
        principal.__post_init__()
        return principal.principal_id

    def _context(
        self, connection: Connection, principal: VerifiedPrincipal, project_id: str | None
    ) -> ProjectContext:
        principal_id = self._principal(principal)
        safe = and_(
            _byte_length(connection, projects.c.id) == 32,
            _byte_length(connection, organizations.c.id) == 32,
        )
        # CASE preserves an invalid/ambiguous default as a denial instead of
        # filtering it out and silently selecting a different membership. No
        # unbounded legacy SQLite identity cell crosses the driver boundary.
        query = (
            select(
                case((safe, projects.c.id), else_=None).label("project_id"),
                case((safe, organizations.c.id), else_=None).label("organization_id"),
            )
            .select_from(
                members.join(projects, members.c.project_id == projects.c.id).join(
                    organizations, organizations.c.id == projects.c.organization_id
                )
            )
            .where(members.c.principal_id == principal_id, members.c.revoked_at.is_(None))
        )
        if project_id is None:
            query = query.where(members.c.legacy_default.is_(True))
        else:
            query = query.where(projects.c.id == identifier(project_id))
        rows = connection.execute(query.limit(2)).mappings().all()
        if len(rows) != 1:
            raise ResourceNotFound()
        return ProjectContext(
            identifier(rows[0]["organization_id"]), identifier(rows[0]["project_id"]), principal_id
        )

    def check(
        self,
        connection: Connection,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        action: str = "read",
        *,
        resource_kind: str | None = None,
        resource_id: str | None = None,
    ) -> ProjectDecision:
        """Fresh same-Connection check; caller owns any required write exclusion.

        Recheck this SAME project after I/O, never resolve a changed legacy
        default. This method does not acquire locks or authorize a later commit.
        """
        principal_id = self._principal(principal)
        if not isinstance(context, ProjectContext) or context.principal_id != principal_id:
            raise ResourceNotFound()
        if (resource_kind is None) != (resource_id is None):
            raise ResourceNotFound()
        try:
            role = self.repositories.effective_role(connection, context)
            if resource_kind is not None and resource_id is not None:
                _Reads(connection, context).resource(resource_kind, resource_id)
            # Resource visibility precedes forbidden-action classification.
            if not isinstance(action, str) or not allows_project_action(role, action):
                raise ActionForbidden()
            return ProjectDecision(context, role)
        except SQLAlchemyError:
            raise RepositoryUnavailable() from None

    def _resolve(
        self,
        principal: VerifiedPrincipal,
        project_id: str | None,
        action: str,
        resource_kind: str | None,
        resource_id: str | None,
    ) -> ProjectDecision:
        self._principal(principal)
        try:
            with owned_connect(self.engine) as connection:
                context = self._context(connection, principal, project_id)
                return self.check(
                    connection,
                    principal,
                    context,
                    action,
                    resource_kind=resource_kind,
                    resource_id=resource_id,
                )
        except SQLAlchemyError:
            raise RepositoryUnavailable() from None

    def legacy(
        self,
        principal: VerifiedPrincipal,
        action: str = "read",
        *,
        resource_kind: str | None = None,
        resource_id: str | None = None,
    ) -> ProjectDecision:
        return self._resolve(principal, None, action, resource_kind, resource_id)

    def named(
        self,
        principal: VerifiedPrincipal,
        project_id: str,
        action: str = "read",
        *,
        resource_kind: str | None = None,
        resource_id: str | None = None,
    ) -> ProjectDecision:
        """Future server path dependency, never a new selector on legacy routes."""
        self._principal(principal)
        return self._resolve(principal, identifier(project_id), action, resource_kind, resource_id)

    def legacy_role(self, principal: VerifiedPrincipal) -> str | None:
        """Identity-only me hint; unavailable SQL is NOT an absent membership."""
        try:
            return self.legacy(principal).role
        except ResourceNotFound:
            return None
