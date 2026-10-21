"""Journal-free scoped complete-graph reads, without any publication authority."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Text, and_, case, column, select, table, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql.elements import ColumnElement

from .artifact_graph import (
    MAX_BYTES,
    MAX_JSON_BYTES,
    MAX_OBJECTS,
    GraphRef,
    VerifiedGraph,
    decode,
    verify_run_graph,
)
from .artifact_metadata import ArtifactError, ArtifactObject, _object, _owner, digest_value
from .artifact_storage import ArtifactStorage
from .models import canonical
from .scoped_lineage import ResourceNotFound, identifier
from .scoped_repositories import ProjectContext, ScopedRepositories, _byte_length, _Reads, scopes

MAX_COMPOUND_RUNS = 2
MAX_REF_INPUT_BYTES = 4 * 1024 * 1024
_FIELDS = ("id", "project_id", "digest", "locator", "format_version", "byte_count", "created_at")
_objects = table("artifact_objects", *(column(name) for name in _FIELDS))
_refs = table(
    "artifact_refs",
    *(column(name) for name in ("project_id", "owner_kind", "owner_id", "role", "artifact_id")),
)


def _bounded_columns(connection: Connection) -> tuple[ColumnElement[Any], ...]:
    """Bound all descriptor cells in the body SELECT, before driver transfer."""
    bounds = {
        "id": 32,
        "project_id": 32,
        "digest": 64,
        "locator": 160,
        "format_version": 8,
        "byte_count": 24,
        "created_at": 64,
    }
    safe = and_(
        *(_byte_length(connection, _objects.c[name]) <= limit for name, limit in bounds.items())
    )
    return tuple(case((safe, _objects.c[name]), else_=None).label(name) for name in _FIELDS)


def _resolve_bounded(
    connection: Connection,
    *,
    project_id: str,
    owner_kind: str,
    owner_id: str,
    role: str,
    digest: str,
) -> ArtifactObject | None:
    """Reader resolver; owner authorization still precedes this SQL-only join."""
    _owner(project_id, owner_kind, owner_id, role)
    digest_value(digest)
    query = (
        select(*_bounded_columns(connection))
        .select_from(
            _refs.join(
                _objects,
                and_(
                    _objects.c.project_id == _refs.c.project_id,
                    _objects.c.id == _refs.c.artifact_id,
                ),
            ).join(
                scopes,
                and_(
                    scopes.c.project_id == _refs.c.project_id,
                    scopes.c.resource_kind == _refs.c.owner_kind,
                    scopes.c.resource_id == _refs.c.owner_id,
                ),
            )
        )
        .where(
            _refs.c.project_id == project_id,
            _refs.c.owner_kind == owner_kind,
            _refs.c.owner_id == owner_id,
            _refs.c.role == role,
            _objects.c.digest == digest,
            _objects.c.format_version == 1,
        )
        .limit(2)
    )
    rows = connection.execute(query).mappings().all()
    if len(rows) > 1:
        raise ArtifactError("artifact_metadata_conflict")
    return _object(rows[0]) if rows else None


def _identity(value: Any) -> tuple[Any, ...]:
    return tuple(getattr(value, name) for name in _FIELDS)


@dataclass(frozen=True)
class RunRead:
    run_id: str
    root_digest: str | None = None

    def __post_init__(self) -> None:
        identifier(self.run_id)
        if self.root_digest is not None:
            digest_value(self.root_digest)


class PublishedRunReader:
    """Trusted ProjectContext input; every operation freshly checks its same project.

    No journal, SQL writer, migration, root publication or legacy hash fallback.
    Compound reads allow at most two graphs, 16,000 distinct scoped refs and
    64 MiB of loaded bytes across both graphs. Final metadata uses a <=4 MiB
    JSON rowset and constant bind count. Supported DBs are SQLite 3.35+ with its
    already-required JSON functions and PostgreSQL 16 with builtin JSONB.
    No extension or additional writer privilege is required.
    """

    def __init__(self, engine: Engine, storage: ArtifactStorage):
        self.engine = engine
        self.repositories = ScopedRepositories(
            engine, artifact_resolver=_resolve_bounded, artifact_loader=storage.read_verified
        )

    @contextmanager
    def _connection(self) -> Iterator[Connection]:
        try:
            with self.engine.connect() as connection:
                # Refuse unsupported CTE syntax during SQL-only preflight,
                # before a graph can trigger storage/decryption work.
                version = connection.dialect.server_version_info
                if connection.dialect.name == "sqlite" and (
                    version is None or version < (3, 35, 0)
                ):
                    raise ArtifactError("artifact_database_unsupported")
                yield connection
        except SQLAlchemyError:
            raise ArtifactError("publication_database_unavailable") from None

    def scoped_bytes(
        self, context: ProjectContext, ref: GraphRef, limit: int
    ) -> tuple[bytes, tuple[Any, ...]]:
        identities: list[tuple[Any, ...]] = []

        def bounded(value: Any) -> bytes:
            if type(value.byte_count) is not int or not 0 <= value.byte_count <= limit:
                raise ArtifactError("artifact_graph_limit")
            identities.append(_identity(value))
            if self.repositories.artifact_loader is None:
                raise ArtifactError("publication_loader_unavailable")
            return self.repositories.artifact_loader(value)

        scoped = ScopedRepositories(
            self.engine,
            artifact_resolver=self.repositories.artifact_resolver,
            artifact_loader=bounded,
        )
        value = scoped.read_artifact(context, "run", ref.owner_id, ref.role, ref.digest)
        return value, identities[0]

    def _unique_root(self, connection: Connection, context: ProjectContext, run_id: str) -> str:
        self.repositories._authorize(connection, context, "read")
        _Reads(connection, context).resource("run", run_id)
        # Only bounded digest values cross the driver, even with malformed
        # SQLite dynamic values. Invalid candidates still count toward ambiguity.
        rows: Sequence[Any] = (
            connection.execute(
                select(
                    case(
                        (_byte_length(connection, _objects.c.digest) == 64, _objects.c.digest),
                        else_=None,
                    )
                )
                .select_from(
                    _refs.join(
                        _objects,
                        and_(
                            _objects.c.project_id == _refs.c.project_id,
                            _objects.c.id == _refs.c.artifact_id,
                        ),
                    ).join(
                        scopes,
                        and_(
                            scopes.c.project_id == _refs.c.project_id,
                            scopes.c.resource_kind == _refs.c.owner_kind,
                            scopes.c.resource_id == _refs.c.owner_id,
                        ),
                    )
                )
                .where(
                    _refs.c.project_id == context.project_id,
                    _refs.c.owner_kind == "run",
                    _refs.c.owner_id == run_id,
                    _refs.c.role == "result",
                    _objects.c.format_version == 1,
                )
                .limit(2)
            )
            .scalars()
            .all()
        )
        if len(rows) != 1:
            raise ResourceNotFound()
        try:
            digest_value(rows[0])
        except ArtifactError:
            raise ResourceNotFound() from None
        return str(rows[0])

    def _final_refs(
        self,
        connection: Connection,
        context: ProjectContext,
        identities: dict[GraphRef, tuple[Any, ...]],
    ) -> None:
        """Re-read the entire bounded expected ref set in one statement snapshot.

        This prevents an earlier checked ref from escaping a later compound
        recheck. It needs SELECT privileges only, without holding writer locks.
        """
        if not 1 <= len(identities) <= MAX_OBJECTS:
            raise ArtifactError("artifact_graph_limit")
        expected = []
        for ref, identity in identities.items():
            if len(identity) != len(_FIELDS):
                raise ArtifactError("publication_reference_changed")
            try:
                identifier(identity[0])
            except ResourceNotFound:
                raise ArtifactError("publication_reference_changed") from None
            expected.append(
                {
                    "owner": ref.owner_id,
                    "role": ref.role,
                    "digest": ref.digest,
                    "artifact_id": identity[0],
                }
            )
        # One JSON bind carries all refs. SQLAlchemy's fixed predicates/limits
        # add a constant number of binds independent of graph size.
        encoded = canonical(expected)
        if len(encoded) > MAX_REF_INPUT_BYTES:
            raise ArtifactError("artifact_graph_limit")
        if connection.dialect.name == "sqlite":
            source = text(
                "SELECT json_extract(value,'$.artifact_id') AS artifact_id,"
                "json_extract(value,'$.owner') AS owner,"
                "json_extract(value,'$.role') AS role,json_extract(value,'$.digest') AS digest "
                "FROM json_each(:expected)"
            )
        elif connection.dialect.name == "postgresql":
            source = text(
                "SELECT owner,role,digest,artifact_id "
                "FROM jsonb_to_recordset(CAST(:expected AS jsonb)) "
                "AS w(owner TEXT,role TEXT,digest TEXT,artifact_id TEXT)"
            )
        else:
            raise ArtifactError("artifact_database_unsupported")
        # Without materialization SQLite can rescan json_each for every ref.
        # The expected ID also makes the reference join a full primary-key match
        # instead of pairing every same-owner/role ref before filtering digest.
        wanted = (
            source.columns(owner=Text, role=Text, digest=Text, artifact_id=Text)
            .cte("wanted")
            .prefix_with("MATERIALIZED")
        )
        query = (
            select(
                wanted.c.owner,
                wanted.c.role,
                wanted.c.digest.label("wanted_digest"),
                *_bounded_columns(connection),
            )
            .select_from(
                wanted.join(
                    _refs,
                    and_(
                        _refs.c.project_id == context.project_id,
                        _refs.c.owner_kind == "run",
                        _refs.c.owner_id == wanted.c.owner,
                        _refs.c.role == wanted.c.role,
                        _refs.c.artifact_id == wanted.c.artifact_id,
                    ),
                )
                .join(
                    _objects,
                    and_(
                        _objects.c.project_id == _refs.c.project_id,
                        _objects.c.id == _refs.c.artifact_id,
                        _objects.c.digest == wanted.c.digest,
                        _objects.c.format_version == 1,
                    ),
                )
                .join(
                    scopes,
                    and_(
                        scopes.c.project_id == context.project_id,
                        scopes.c.resource_kind == "run",
                        scopes.c.resource_id == wanted.c.owner,
                    ),
                )
            )
            .limit(len(identities) + 1)
        )
        rows = connection.execute(query, {"expected": encoded.decode()}).mappings().all()
        seen: set[GraphRef] = set()
        for row in rows:
            ref = GraphRef(row["owner"], row["role"], row["wanted_digest"])
            try:
                current = _object(row)
            except ArtifactError:
                raise ArtifactError("publication_reference_changed") from None
            if ref in seen or ref not in identities or _identity(current) != identities[ref]:
                raise ArtifactError("publication_reference_changed")
            seen.add(ref)
        if seen != identities.keys():
            raise ArtifactError("publication_reference_changed")

    def read_many(
        self, context: ProjectContext, requests: Sequence[RunRead]
    ) -> tuple[VerifiedGraph, ...]:
        if not 1 <= len(requests) <= MAX_COMPOUND_RUNS:
            raise ArtifactError("artifact_graph_limit")
        requests = tuple(requests)
        for request in requests:
            if not isinstance(request, RunRead):
                raise ResourceNotFound()
            request.__post_init__()
        identities: dict[GraphRef, tuple[Any, ...]] = {}
        retained = 0
        graphs: list[VerifiedGraph] = []
        discovered: dict[str, str] = {}

        def fetch(ref: GraphRef, limit: int) -> bytes:
            nonlocal retained
            if len(identities) >= MAX_OBJECTS and ref not in identities:
                raise ArtifactError("artifact_graph_limit")
            value, current = self.scoped_bytes(context, ref, min(limit, MAX_BYTES - retained))
            if ref in identities and identities[ref] != current:
                raise ArtifactError("publication_reference_changed")
            identities[ref] = current
            retained += len(value)
            if retained > MAX_BYTES:
                raise ArtifactError("artifact_graph_limit")
            return value

        # Resolve every requested run before any storage work. A compound read
        # with an inaccessible second input must not load the first input.
        resolved: list[tuple[RunRead, str]] = []
        with self._connection() as connection:
            self.repositories._authorize(connection, context, "read")
            reads = _Reads(connection, context)
            for request in requests:
                reads.resource("run", request.run_id)
                root_digest = request.root_digest
                if root_digest is None:
                    root_digest = self._unique_root(connection, context, request.run_id)
                    discovered[request.run_id] = root_digest
                # Explicit historical digests need the same scoped result-ref
                # preflight as discovered roots, before either graph is loaded.
                self.repositories._resolve(reads, "run", request.run_id, "result", root_digest)
                resolved.append((request, root_digest))
        for request, root_digest in resolved:
            envelope = fetch(GraphRef(request.run_id, "result", root_digest), MAX_JSON_BYTES)
            root = decode(envelope)
            if root.get("project_id") != context.project_id or root.get("run_id") != request.run_id:
                raise ArtifactError("artifact_graph_invalid")
            graphs.append(verify_run_graph(envelope, fetch))
        # SQL-only READ COMMITTED revalidation, not a repeatable snapshot or a
        # promise about network response linearizability. Recheck authority last
        # as well as first so revocation during this pass cannot be missed.
        with self._connection() as connection:
            self.repositories._authorize(connection, context, "read")
            reads = _Reads(connection, context)
            for owner in sorted({ref.owner_id for ref in identities}):
                reads.resource("run", owner)
            for run_id, root_digest in discovered.items():
                if self._unique_root(connection, context, run_id) != root_digest:
                    raise ArtifactError("publication_reference_changed")
            self._final_refs(connection, context, identities)
            self.repositories._authorize(connection, context, "read")
        return tuple(graphs)

    def read(self, context: ProjectContext, run_id: str, root_digest: str) -> VerifiedGraph:
        return self.read_many(context, (RunRead(run_id, root_digest),))[0]

    def read_current(self, context: ProjectContext, run_id: str) -> VerifiedGraph:
        return self.read_many(context, (RunRead(run_id),))[0]
