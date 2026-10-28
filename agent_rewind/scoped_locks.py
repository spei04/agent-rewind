"""Shared same-Connection project/grant/resource exclusion, without commit authority.

Participating writers acquire projects before organization, caller membership,
caller key scope/key and target scope/row. These helpers retain visibility-first
decisions; callers must freshly check the actual action after lock waits.
No connection, transaction, audit or external I/O is owned here.
"""

from sqlalchemy import select
from sqlalchemy.engine import Connection
from sqlalchemy.sql import Select

from .database import jobs, keys
from .request_authority import RequestAuthority
from .request_identity import VerifiedPrincipal
from .scoped_lineage import ResourceNotFound
from .scoped_repositories import ProjectContext, members, organizations, projects, scopes


def _lock_row(connection: Connection, statement: Select[tuple[str]], *, shared: bool) -> None:
    row = connection.execute(statement.with_for_update(read=shared)).first()
    if row is None:
        raise ResourceNotFound()


def lock_authority(
    authority: RequestAuthority,
    connection: Connection,
    principal: VerifiedPrincipal,
    context: ProjectContext,
    kind: str | None,
    resource_id: str | None,
    *,
    exclusive_organization: bool = False,
) -> None:
    # No cached role or changed default is substituted for the original
    # context. Visibility comes before action classification, including for
    # a viewer addressing a foreign/missing target.
    authority.check(connection, principal, context, resource_kind=kind, resource_id=resource_id)
    _lock_row(
        connection,
        select(projects.c.id).where(
            projects.c.id == context.project_id,
            projects.c.organization_id == context.organization_id,
        ),
        shared=False,
    )
    _lock_row(
        connection,
        select(organizations.c.id).where(organizations.c.id == context.organization_id),
        # P2 selects its strongest organization mode on the first acquisition.
        shared=not exclusive_organization,
    )
    _lock_row(
        connection,
        select(members.c.principal_id).where(
            members.c.project_id == context.project_id,
            members.c.principal_id == principal.principal_id,
        ),
        shared=True,
    )
    if principal.principal_id.startswith("api-key:"):
        lock_resource(connection, context, "key", principal.principal_id[8:], shared=True)
    if kind is not None and resource_id is not None:
        lock_resource(connection, context, kind, resource_id, shared=False)
        if kind == "key":
            # Revoked/expired keys stay visible for revocation. A missing
            # key membership is not repaired or synthesized.
            connection.execute(
                select(members.c.principal_id)
                .where(
                    members.c.project_id == context.project_id,
                    members.c.principal_id == "api-key:" + resource_id,
                )
                .with_for_update()
            ).first()


def lock_resource(
    connection: Connection,
    context: ProjectContext,
    kind: str,
    resource_id: str,
    *,
    shared: bool,
) -> None:
    # Freeze ownership before locking the target, so a changed foreign
    # scope cannot make this transaction lock another project's resource.
    _lock_row(
        connection,
        select(scopes.c.resource_id).where(
            scopes.c.resource_kind == kind,
            scopes.c.resource_id == resource_id,
            scopes.c.project_id == context.project_id,
        ),
        shared=True,
    )
    source = keys if kind == "key" else jobs
    _lock_row(
        connection,
        select(source.c.id).where(source.c.id == resource_id),
        shared=shared,
    )
