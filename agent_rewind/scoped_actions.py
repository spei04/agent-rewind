"""Atomic project mutations; trusted identity/context inputs, no admission authority.

Cooperating writers lock affected projects in sorted order before grants or
targets. Row locks also serialize ordinary updates/deletes of the existing
authority rows; they cannot constrain arbitrary administrative SQL or freeze
wall-clock expiry. Legacy worker writers remain outside the full project-first
protocol until AR-010/012 integration. No storage or network work occurs here.
"""

from __future__ import annotations

import hashlib
import secrets
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import insert, update
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from .artifact_metadata import ArtifactError
from .database import audit, jobs, keys
from .publication_source import _lock_closure
from .request_authority import RequestAuthority
from .request_identity import VerifiedPrincipal
from .scoped_lineage import ResourceNotFound, identifier
from .scoped_locks import lock_authority
from .scoped_repositories import (
    ProjectContext,
    RepositoryUnavailable,
    _Reads,
    members,
    scopes,
)

ActionCode = Literal["action_invalid_input", "action_unavailable", "outcome_uncertain"]
KeyRole = Literal["viewer", "operator"]


class ScopedActionError(RuntimeError):
    """Only a finite public code, never driver text or a token."""

    def __init__(self, code: ActionCode) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class IssuedKey:
    id: str
    token: str = field(repr=False)
    role: KeyRole


class ScopedActions:
    """Own one transaction per call; never retry an uncertain mutation.

    The caller authenticates the principal, resolves the original context and
    applies the release/HTTP guards. This module freshly checks that same
    authority on its owned connection and supplies no release-ready bypass.
    """

    def __init__(self, engine: Engine, authority: RequestAuthority):
        self.engine, self.authority = engine, authority

    @staticmethod
    def _identity(principal: VerifiedPrincipal, context: ProjectContext) -> None:
        principal_id = RequestAuthority._principal(principal)
        if not isinstance(context, ProjectContext) or context.principal_id != principal_id:
            raise ResourceNotFound()
        identifier(context.organization_id)
        identifier(context.project_id)

    @contextmanager
    def _transaction(self) -> Iterator[Connection]:
        commit_attempted = False
        try:
            with self.engine.connect() as connection:
                raw = connection.connection.driver_connection
                dialect = connection.dialect.name
                if not (
                    (dialect == "postgresql" and getattr(raw, "autocommit", None) is False)
                    or (
                        dialect == "sqlite"
                        and getattr(raw, "isolation_level", None) is not None
                        and getattr(raw, "autocommit", -1) == -1
                    )
                ):
                    # A mutated pooled DBAPI mode must not reach another caller.
                    connection.invalidate()
                    raise ScopedActionError("action_unavailable")
                try:
                    if dialect == "sqlite":
                        if connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 1:
                            connection.invalidate()
                            raise ScopedActionError("action_unavailable")
                        connection.exec_driver_sql("BEGIN IMMEDIATE")
                    else:
                        connection.begin()
                        connection.exec_driver_sql("SET LOCAL search_path TO public,pg_temp")
                        connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                        connection.exec_driver_sql("SET LOCAL lock_timeout = '3s'")
                        connection.exec_driver_sql("SET LOCAL statement_timeout = '5s'")
                    yield connection
                    commit_attempted = True
                    connection.commit()
                except BaseException:
                    try:
                        connection.rollback()
                    except SQLAlchemyError:
                        connection.invalidate()
                    raise
        except (SQLAlchemyError, RepositoryUnavailable):
            raise ScopedActionError(
                "outcome_uncertain" if commit_attempted else "action_unavailable"
            ) from None

    def _locks(
        self,
        connection: Connection,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        kind: str | None,
        resource_id: str | None,
    ) -> None:
        lock_authority(self.authority, connection, principal, context, kind, resource_id)

    @staticmethod
    def _audit(
        connection: Connection,
        audit_id: str,
        principal: VerifiedPrincipal,
        action: str,
        target: str,
    ) -> None:
        connection.execute(
            insert(audit).values(
                id=audit_id,
                created=time.time(),
                actor=principal.principal_id,
                action=action,
                target=target,
            )
        )

    def cancel(self, principal: VerifiedPrincipal, context: ProjectContext, job_id: str) -> None:
        self._identity(principal, context)
        identifier(job_id)
        audit_id = uuid.uuid4().hex
        with self._transaction() as connection:
            self._locks(connection, principal, context, "job", job_id)
            current = _Reads(connection, context).job(job_id)
            if current["status"] not in {"queued", "running", "succeeded", "failed", "cancelled"}:
                raise ResourceNotFound()
            self.authority.check(
                connection, principal, context, "cancel", resource_kind="job", resource_id=job_id
            )
            values: dict[str, str | bool] = {"cancel": True}
            if current["status"] == "queued":
                values["status"] = "cancelled"
            connection.execute(update(jobs).where(jobs.c.id == job_id).values(**values))
            self._audit(connection, audit_id, principal, "job.cancel", job_id)

    def issue_key(
        self,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        role: KeyRole,
        name: str,
        days: int,
    ) -> IssuedKey:
        self._identity(principal, context)
        try:
            valid = (
                role in {"viewer", "operator"}
                and isinstance(name, str)
                and 1 <= len(name) <= 120
                and "\x00" not in name
                and len(name.encode("utf-8")) <= 480
                and type(days) is int
                and 1 <= days <= 90
            )
        except (TypeError, UnicodeError):
            valid = False
        if not valid:
            raise ScopedActionError("action_invalid_input")
        # Entropy and hashing precede locks. The secret is never persisted or
        # exposed by repr/audit, and is returned only after confirmed commit.
        key_id, audit_id = uuid.uuid4().hex, uuid.uuid4().hex
        token = "rw_" + secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self._transaction() as connection:
            self._locks(connection, principal, context, None, None)
            self.authority.check(connection, principal, context, "create_key")
            connection.execute(
                insert(keys).values(
                    id=key_id,
                    hash=digest,
                    role=role,
                    name=name,
                    expires=time.time() + days * 86400,
                    revoked=False,
                )
            )
            connection.execute(
                insert(scopes).values(
                    resource_kind="key", resource_id=key_id, project_id=context.project_id
                )
            )
            connection.execute(
                insert(members).values(
                    project_id=context.project_id,
                    principal_id="api-key:" + key_id,
                    role=role,
                    revoked_at=None,
                    legacy_default=True,
                )
            )
            self._audit(connection, audit_id, principal, "key.create", key_id)
        return IssuedKey(key_id, token, role)

    def revoke_key(
        self, principal: VerifiedPrincipal, context: ProjectContext, key_id: str
    ) -> None:
        self._identity(principal, context)
        identifier(key_id)
        audit_id = uuid.uuid4().hex
        with self._transaction() as connection:
            self._locks(connection, principal, context, "key", key_id)
            self.authority.check(
                connection,
                principal,
                context,
                "revoke_key",
                resource_kind="key",
                resource_id=key_id,
            )
            connection.execute(update(keys).where(keys.c.id == key_id).values(revoked=True))
            connection.execute(
                update(members)
                .where(
                    members.c.project_id == context.project_id,
                    members.c.principal_id == "api-key:" + key_id,
                    members.c.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(UTC).isoformat())
            )
            self._audit(connection, audit_id, principal, "key.revoke", key_id)

    def record_run_read(
        self, principal: VerifiedPrincipal, context: ProjectContext, run_id: str
    ) -> None:
        """Record only an already successfully verified/rendered run response.

        Caller rendering finishes before this SQL-only transaction. Reuse the
        bounded publication lineage lock/revalidation protocol; existing source
        rows/scopes remain stable through audit commit, while future source
        writers must still follow its project/owning-job phantom discipline.
        This does not verify artifact bytes or promise response linearizability.
        """
        self._identity(principal, context)
        identifier(run_id)
        audit_id = uuid.uuid4().hex
        with self._transaction() as connection:
            self.authority.check(
                connection, principal, context, resource_kind="run", resource_id=run_id
            )
            self._locks(connection, principal, context, None, None)
            try:
                _lock_closure(_Reads(connection, context), run_id)
            except ArtifactError:
                raise ResourceNotFound() from None
            self.authority.check(
                connection, principal, context, resource_kind="run", resource_id=run_id
            )
            self._audit(connection, audit_id, principal, "run.read", run_id)
