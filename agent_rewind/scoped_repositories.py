"""Preparatory project-scoped reads; routes and customer admission remain disabled."""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import LargeBinary, Text, and_, case, cast, column, func, literal, select, table
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql.elements import ColumnElement

from .database import events, jobs, keys, records
from .ownership import allows_project_action
from .scoped_artifacts import ArtifactLoader, ArtifactObject, ArtifactResolver
from .scoped_lineage import MAX_NODES, Lineage, encoded_size, identifier
from .scoped_lineage import ResourceNotFound as ResourceNotFound

MAX_RECORD_BYTES = 2 * 1024 * 1024
MAX_LIST_BYTES = 8 * 1024 * 1024
MAX_EVENT_REFS = 10000
ARTIFACT_ROLES = frozenset(
    {
        "payload",
        "admission_config",
        "task",
        "event",
        "checkpoint",
        "workspace",
        "file_blob",
        "evaluation",
        "result",
        "study_attachment",
        "budget_evidence",
    }
)
scopes = table(
    "resource_scopes", column("resource_kind"), column("resource_id"), column("project_id")
)
projects = table("projects", column("id"), column("organization_id"))
organizations = table("organizations", column("id"))
members = table(
    "project_memberships",
    column("project_id"),
    column("principal_id"),
    column("role"),
    column("revoked_at"),
    column("legacy_default"),
)


@dataclass(frozen=True)
class ProjectContext:
    """Identity already verified by a trusted authenticator, never request role claims.

    Construction is not authentication. AR-007-C must translate only verified
    issuer-bound OIDC identities or verified API-key identities into this context.
    """

    organization_id: str
    project_id: str
    principal_id: str


class RepositoryUnavailable(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Resource service unavailable.")


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ResourceNotFound()
        value[key] = item
    return value


def _invalid_constant(value: str) -> None:
    raise ResourceNotFound()


class _ProjectScope(Protocol):
    @property
    def project_id(self) -> str: ...


def _scope(kind: str, resource_id: Any, context: _ProjectScope) -> Any:
    return and_(
        scopes.c.resource_kind == kind,
        scopes.c.resource_id == resource_id,
        scopes.c.project_id == context.project_id,
    )


def _byte_length(connection: Connection, value: Any) -> Any:
    return (
        func.octet_length(cast(value, Text))
        if connection.dialect.name == "postgresql"
        else func.length(cast(value, LargeBinary))
    )


def _bounded_row(connection: Connection, source: Any) -> Any:
    size: ColumnElement[int] = literal(0)
    for field in source.c:
        size = size + func.coalesce(_byte_length(connection, field), 0)
    return size <= MAX_RECORD_BYTES


def _json_row(value: dict[str, Any]) -> dict[str, Any]:
    # SQL-side byte checks precede fetch. This also bounds escaped JSON output
    # and rejects SQLite dynamic blobs or numeric overflow before retaining it.
    if encoded_size(value) > MAX_RECORD_BYTES:
        raise ResourceNotFound()
    return value


class _Reads:
    def __init__(self, connection: Connection, context: _ProjectScope):
        self.connection, self.context = connection, context

    def record(self, kind: str, resource_id: str) -> dict[str, Any]:
        row = (
            self.connection.execute(
                select(records.c.id, records.c.created, cast(records.c.data, Text).label("body"))
                .select_from(records.join(scopes, _scope(kind, records.c.id, self.context)))
                .where(
                    records.c.id == identifier(resource_id),
                    records.c.kind == kind,
                    _bounded_row(self.connection, records),
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise ResourceNotFound()
        try:
            data = json.loads(
                row["body"], object_pairs_hook=_object, parse_constant=_invalid_constant
            )
        except (ValueError, TypeError, RecursionError):
            raise ResourceNotFound() from None
        if not isinstance(data, dict):
            raise ResourceNotFound()
        # Historical JSON cannot override the authoritative SQL identity.
        return _json_row({**data, "id": row["id"], "created": row["created"]})

    def job(self, resource_id: str) -> dict[str, Any]:
        row = (
            self.connection.execute(
                select(jobs)
                .select_from(jobs.join(scopes, _scope("job", jobs.c.id, self.context)))
                .where(jobs.c.id == identifier(resource_id), _bounded_row(self.connection, jobs))
            )
            .mappings()
            .first()
        )
        if row is None:
            raise ResourceNotFound()
        return _json_row(dict(row))

    def key(self, resource_id: str, *, require_unrevoked: bool = False) -> dict[str, Any]:
        row = (
            self.connection.execute(
                select(keys.c.id, keys.c.role, keys.c.name, keys.c.expires, keys.c.revoked)
                .select_from(keys.join(scopes, _scope("key", keys.c.id, self.context)))
                .where(
                    keys.c.id == identifier(resource_id),
                    _bounded_row(self.connection, keys),
                    # SQLite Boolean decoding can coerce malformed empty cells
                    # to False. Authorization must check the SQL value first.
                    keys.c.revoked.is_(False) if require_unrevoked else literal(True),
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise ResourceNotFound()
        return _json_row(dict(row))

    def by_job(self, job_id: str) -> list[tuple[str, str]]:
        # Scope discovery before its count/limit. A foreign forged incoming
        # reference must neither leak nor deny access to this project's job.
        rows = self.connection.execute(
            select(records.c.kind, records.c.id)
            .select_from(
                records.join(
                    scopes,
                    and_(
                        scopes.c.resource_kind == records.c.kind,
                        scopes.c.resource_id == records.c.id,
                        scopes.c.project_id == self.context.project_id,
                    ),
                )
            )
            .where(records.c.data["job_id"].as_string() == job_id)
            .order_by(records.c.kind, records.c.id)
            .limit(MAX_NODES + 1)
        ).all()
        if len(rows) > MAX_NODES:
            raise ResourceNotFound()
        return [(row.kind, row.id) for row in rows]

    def resource(self, kind: str, resource_id: str) -> dict[str, Any]:
        if kind == "key":
            return self.key(resource_id)
        return Lineage(self.record, self.job, self.by_job).validate(kind, resource_id)


class ScopedRepositories:
    """SQL ownership and fresh authorization, with explicit scope on every call.

    This interface does not replace the release revision guard or authenticate
    callers. It is deliberately not wired into legacy or v1 routes in this slice.
    """

    def __init__(
        self,
        engine: Engine,
        *,
        artifact_resolver: ArtifactResolver | None = None,
        artifact_loader: ArtifactLoader | None = None,
    ):
        self.engine = engine
        self.artifact_resolver = artifact_resolver
        self.artifact_loader = artifact_loader

    def effective_role(self, connection: Connection, context: ProjectContext) -> str:
        """Fresh membership/token intersection; context construction is not authentication."""
        identifier(context.organization_id)
        identifier(context.project_id)
        if not isinstance(context.principal_id, str) or not re.fullmatch(
            r"(oidc:[0-9a-f]{64}|api-key:[0-9a-f]{32})", context.principal_id
        ):
            raise ResourceNotFound()
        role = connection.execute(
            select(
                case((_byte_length(connection, members.c.role) <= 16, members.c.role), else_=None)
            )
            .select_from(
                members.join(projects, members.c.project_id == projects.c.id).join(
                    organizations, organizations.c.id == projects.c.organization_id
                )
            )
            .where(
                projects.c.id == context.project_id,
                organizations.c.id == context.organization_id,
                members.c.principal_id == context.principal_id,
                members.c.revoked_at.is_(None),
            )
        ).scalar_one_or_none()
        if role not in {"viewer", "operator", "maintainer"}:
            raise ResourceNotFound()
        if context.principal_id.startswith("api-key:"):
            row = _Reads(connection, context).key(context.principal_id[8:], require_unrevoked=True)
            expires = row["expires"]
            if (
                row["revoked"] is not False
                or type(expires) not in {int, float}
                or not math.isfinite(expires)
                or expires <= time.time()
            ):
                raise ResourceNotFound()
            # An explicitly mapped historical administrator key has at most
            # operator authority. Membership can reduce, never expand, its scope.
            ceiling = "operator" if row["role"] == "administrator" else row["role"]
            if ceiling not in {"viewer", "operator"}:
                raise ResourceNotFound()
            if ceiling == "viewer" or role == "viewer":
                return "viewer"
            return "operator"
        return str(role)

    def _authorize(self, connection: Connection, context: ProjectContext, action: str) -> None:
        if not allows_project_action(self.effective_role(connection, context), action):
            raise ResourceNotFound()

    @contextmanager
    def _session(self, context: ProjectContext, action: str) -> Iterator[_Reads]:
        try:
            with self.engine.connect() as connection:
                self._authorize(connection, context, action)
                yield _Reads(connection, context)
        except SQLAlchemyError:
            raise RepositoryUnavailable() from None

    def require_action(
        self,
        context: ProjectContext,
        action: str,
        *,
        kind: str | None = None,
        resource_id: str | None = None,
    ) -> None:
        """A preparatory check, not permission to skip authorization at later use."""
        if (kind is None) != (resource_id is None):
            raise ResourceNotFound()
        with self._session(context, action) as reads:
            if kind is not None and resource_id is not None:
                reads.resource(kind, resource_id)

    def get_run(self, context: ProjectContext, run_id: str) -> dict[str, Any]:
        with self._session(context, "read") as reads:
            return reads.resource("run", run_id)

    def get_study(self, context: ProjectContext, study_id: str) -> dict[str, Any]:
        with self._session(context, "read") as reads:
            return reads.resource("study", study_id)

    def get_job(self, context: ProjectContext, job_id: str) -> dict[str, Any]:
        with self._session(context, "read") as reads:
            return reads.resource("job", job_id)

    def get_key(self, context: ProjectContext, key_id: str) -> dict[str, Any]:
        with self._session(context, "read") as reads:
            return reads.resource("key", key_id)

    def list_resources(
        self,
        context: ProjectContext,
        kind: str,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if (
            kind not in {"run", "study", "job", "key"}
            or type(limit) is not int
            or not 1 <= limit <= 100
        ):
            raise ResourceNotFound()
        source = jobs if kind == "job" else keys if kind == "key" else records
        with self._session(context, "list") as reads:
            query = select(source.c.id).select_from(
                source.join(scopes, _scope(kind, source.c.id, context))
            )
            if kind in {"run", "study"}:
                query = query.where(records.c.kind == kind)
            ids: list[str] = list(
                reads.connection.execute(query.order_by(source.c.id).limit(limit)).scalars().all()
            )
            result: list[dict[str, Any]] = []
            size = 0
            for resource_id in ids:
                item = reads.resource(kind, resource_id)
                size += encoded_size(item)
                if size > MAX_LIST_BYTES:
                    raise ResourceNotFound()
                result.append(item)
            return result

    def event_refs(self, context: ProjectContext, run_id: str) -> list[dict[str, Any]]:
        """Own event metadata only; inherited prefix traversal remains explicit."""
        with self._session(context, "read") as reads:
            reads.resource("run", run_id)
            event_source = events.join(scopes, _scope("run", events.c.run_id, context))
            byte_size = sum(
                (func.coalesce(_byte_length(reads.connection, field), 0) for field in events.c),
                literal(0),
            )
            if reads.connection.execute(
                select(literal(1))
                .select_from(event_source)
                .where(events.c.run_id == run_id, byte_size > 256)
                .limit(1)
            ).first():
                raise ResourceNotFound()
            rows = (
                reads.connection.execute(
                    select(events)
                    .select_from(events.join(scopes, _scope("run", events.c.run_id, context)))
                    .where(events.c.run_id == run_id)
                    .order_by(events.c.step)
                    .limit(MAX_EVENT_REFS + 1)
                )
                .mappings()
                .all()
            )
            if len(rows) > MAX_EVENT_REFS:
                raise ResourceNotFound()
            for row in rows:
                if (
                    type(row["step"]) is not int
                    or row["step"] < 1
                    or any(
                        not isinstance(row[key], str) or not re.fullmatch(r"[0-9a-f]{64}", row[key])
                        for key in ("artifact", "hash")
                    )
                ):
                    raise ResourceNotFound()
            return [dict(row) for row in rows]

    def _resolve(
        self,
        reads: _Reads,
        owner_kind: str,
        owner_id: str,
        role: str,
        digest: str,
    ) -> ArtifactObject:
        if (
            owner_kind not in {"run", "study", "job"}
            or role not in ARTIFACT_ROLES
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            raise ResourceNotFound()
        reads.resource(owner_kind, owner_id)
        if self.artifact_resolver is None:
            raise ResourceNotFound()
        value = self.artifact_resolver(
            reads.connection,
            project_id=reads.context.project_id,
            owner_kind=owner_kind,
            owner_id=owner_id,
            role=role,
            digest=digest,
        )
        if value is None or value.project_id != reads.context.project_id or value.digest != digest:
            raise ResourceNotFound()
        return value

    def resolve_artifact(
        self,
        context: ProjectContext,
        owner_kind: str,
        owner_id: str,
        role: str,
        digest: str,
    ) -> ArtifactObject:
        """Internal descriptor only; never serialize locators into a public response."""
        with self._session(context, "read") as reads:
            return self._resolve(reads, owner_kind, owner_id, role, digest)

    def read_artifact(
        self,
        context: ProjectContext,
        owner_kind: str,
        owner_id: str,
        role: str,
        digest: str,
    ) -> bytes:
        value = self.resolve_artifact(context, owner_kind, owner_id, role, digest)
        if self.artifact_loader is None:
            raise ResourceNotFound()
        # Storage/network/decryption must not consume a database pool slot.
        content = self.artifact_loader(value)
        current = self.resolve_artifact(context, owner_kind, owner_id, role, digest)
        if (
            current.id,
            current.project_id,
            current.digest,
            current.locator,
            current.format_version,
            current.byte_count,
            current.created_at,
        ) != (
            value.id,
            value.project_id,
            value.digest,
            value.locator,
            value.format_version,
            value.byte_count,
            value.created_at,
        ):
            raise ResourceNotFound()
        return content
