"""Atomic complete-graph publication with an explicitly required future SQL fence.

No live legacy adapter is available: ar0004 has neither generation fencing nor
run projection. This coordinator is exercised through contract-conforming SQL
fixtures until those producer revisions are implemented and reviewed.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from .artifact_graph import MAX_OBJECTS, GraphRef, VerifiedGraph, decode, exact, verify_run_graph
from .artifact_metadata import (
    ArtifactError,
    ArtifactObject,
    _object,
    digest_value,
    identifier,
    object_locator,
    record_verified,
    register_ref,
    resolve_ref,
)
from .artifact_storage import ArtifactStorage, LocalArtifactStorage
from .models import canonical, digest
from .publication_journal import PublicationJournal
from .publication_source import lock_ancestor_ref, snapshot
from .published_reader import PublishedRunReader
from .scoped_repositories import ProjectContext, _Reads


@dataclass(frozen=True)
class PublicationIntent:
    publication_id: str
    context: ProjectContext
    run_id: str
    job_id: str
    worker_id: str
    generation: int
    expected_root: str | None
    envelope: bytes
    source_digest: str
    objects: tuple[ArtifactObject, ...]
    refs: tuple[GraphRef, ...]

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> PublicationIntent:
        try:
            exact(
                record,
                "journal_schema publication_id context run_id job_id worker_id "
                "generation expected_root envelope source_digest objects refs",
            )
            if type(record["journal_schema"]) is not int or record["journal_schema"] != 1:
                raise ValueError
            exact(record["context"], "organization_id project_id principal_id")
            context = ProjectContext(**record["context"])
            for field in ("publication_id", "run_id", "job_id"):
                identifier(record[field])
            digest_value(record["source_digest"])
            if record["expected_root"] is not None:
                digest_value(record["expected_root"])
            if (
                not isinstance(record["objects"], list)
                or not 1 <= len(record["objects"]) <= MAX_OBJECTS
            ):
                raise ValueError
            if not isinstance(record["refs"], list) or not 1 <= len(record["refs"]) <= MAX_OBJECTS:
                raise ValueError
            objects = tuple(_object(row) for row in record["objects"])
            refs = tuple(GraphRef(**row) for row in record["refs"])
            if (
                len({obj.id for obj in objects}) != len(objects)
                or len({obj.digest for obj in objects}) != len(objects)
                or tuple(sorted(set(refs))) != refs
                or any(obj.project_id != context.project_id for obj in objects)
                or {ref.digest for ref in refs} != {obj.digest for obj in objects}
            ):
                raise ValueError
            envelope = canonical(record["envelope"])
            root = decode(envelope)
            for name in ("publication_id", "run_id", "job_id", "worker_id", "generation"):
                if root[name] != record[name]:
                    raise ValueError
            if root["project_id"] != context.project_id:
                raise ValueError
            value = cls(
                record["publication_id"],
                context,
                record["run_id"],
                record["job_id"],
                record["worker_id"],
                record["generation"],
                record["expected_root"],
                envelope,
                record["source_digest"],
                objects,
                refs,
            )
            if value.record() != record:
                raise ValueError
            return value
        except (TypeError, ValueError, KeyError, RecursionError):
            raise ArtifactError("publication_intent_invalid") from None

    @property
    def root_digest(self) -> str:
        return hashlib.sha256(self.envelope).hexdigest()

    def record(self) -> dict[str, Any]:
        return {
            "journal_schema": 1,
            "publication_id": self.publication_id,
            "context": asdict(self.context),
            "run_id": self.run_id,
            "job_id": self.job_id,
            "worker_id": self.worker_id,
            "generation": self.generation,
            "expected_root": self.expected_root,
            "envelope": decode(self.envelope),
            "source_digest": self.source_digest,
            "objects": [
                {**asdict(obj), "created_at": obj.created_at.astimezone(UTC).isoformat()}
                for obj in self.objects
            ],
            "refs": [asdict(ref) for ref in self.refs],
        }


class PublicationWriter(Protocol):
    """Trusted adapter; all methods SQL-only, never commit/open another connection.

    inspect must bind publication ID, scoped job/generation and complete root
    identity; exact success may be inspected after lease expiry. lock_and_check
    must lock and validate current generation/owner/running/cancel/DB-time lease.
    publish_root must compare expected root and write on this same connection.
    All future graph-source producers needing project and job/run exclusion must
    lock all affected projects in sorted order before any affected owning job/run
    rows (also in consistent order), then revalidate before mutation. This includes
    event insert/reassignment/deletion, run/ancestry/source identity changes and
    by_job membership; reassignment covers both old and new owners. Existing-row
    locks cannot protect absent-row phantoms. Complete source graphs are immutable.
    Current legacy producers do not establish this contract; live use is disabled.
    """

    def require_available(self) -> None: ...
    def inspect(
        self, connection: Connection, intent: PublicationIntent
    ) -> Literal["absent", "matching", "conflict"]: ...
    def lock_and_check(self, connection: Connection, intent: PublicationIntent) -> None: ...
    def publish_root(self, connection: Connection, intent: PublicationIntent) -> None: ...


class UnavailableLiveWriter:
    def require_available(self) -> None:
        raise ArtifactError("publication_live_fence_unavailable")

    def inspect(
        self, connection: Connection, intent: PublicationIntent
    ) -> Literal["absent", "matching", "conflict"]:
        self.require_available()
        return "absent"

    def lock_and_check(self, connection: Connection, intent: PublicationIntent) -> None:
        self.require_available()

    def publish_root(self, connection: Connection, intent: PublicationIntent) -> None:
        self.require_available()


class RunPublisher:
    def __init__(
        self,
        engine: Engine,
        storage: ArtifactStorage,
        journal: PublicationJournal,
        *,
        writer: PublicationWriter,
    ):
        if isinstance(storage, LocalArtifactStorage) and journal.root.resolve().is_relative_to(
            (storage.root / "objects").resolve()
        ):
            raise ArtifactError("publication_journal_unsafe")
        self.engine, self.storage, self.journal, self.writer = engine, storage, journal, writer
        self.reader = PublishedRunReader(engine, storage)
        self.repositories = self.reader.repositories

    @contextmanager
    def _connection(self, *, write: bool = False) -> Iterator[Connection]:
        try:
            with self.engine.begin() if write else self.engine.connect() as connection:
                if write:
                    raw = connection.connection.driver_connection
                    dialect = connection.dialect.name
                    transactional = (
                        dialect == "postgresql" and getattr(raw, "autocommit", None) is False
                    ) or (
                        dialect == "sqlite"
                        and getattr(raw, "isolation_level", None) is not None
                        and getattr(raw, "autocommit", False) is not True
                    )
                    if not transactional:
                        raise ArtifactError("publication_transaction_required")
                yield connection
        except SQLAlchemyError:
            raise ArtifactError("publication_database_unavailable") from None

    def _scoped_bytes(
        self, context: ProjectContext, ref: GraphRef, limit: int
    ) -> tuple[bytes, tuple[Any, ...]]:
        return self.reader.scoped_bytes(context, ref, limit)

    def _graph(
        self, intent: PublicationIntent, source: Callable[[GraphRef, int], bytes]
    ) -> VerifiedGraph:
        def fetch(ref: GraphRef, limit: int) -> bytes:
            self.repositories.require_action(
                intent.context, "record", kind="run", resource_id=ref.owner_id
            )
            if ref.owner_id != intent.run_id:
                # An inherited prefix must already be published under its real
                # ancestor owner. Never fall back to the child's source/cache.
                return self._scoped_bytes(intent.context, ref, limit)[0]
            try:
                return source(ref, limit)
            except OSError:
                raise ArtifactError("publication_source_unavailable") from None

        return verify_run_graph(intent.envelope, fetch)

    def prepare(
        self,
        context: ProjectContext,
        run_id: str,
        *,
        worker_id: str,
        generation: int,
        source: Callable[[GraphRef, int], bytes],
        expected_root: str | None = None,
        publication_id: str | None = None,
    ) -> PublicationIntent:
        self.writer.require_available()
        publication_id = publication_id or uuid4().hex
        identifier(publication_id)
        if expected_root is not None:
            digest_value(expected_root)
        with self._connection() as connection:
            captured = snapshot(self.repositories, connection, context, run_id)
        envelope = canonical(
            {
                "publication_schema": 1,
                "publication_id": publication_id,
                "project_id": context.project_id,
                "run_id": run_id,
                "job_id": captured["manifest"]["job_id"],
                "worker_id": worker_id,
                "generation": generation,
                **captured,
            }
        )
        partial = PublicationIntent(
            publication_id,
            context,
            run_id,
            captured["manifest"]["job_id"],
            worker_id,
            generation,
            expected_root,
            envelope,
            digest(captured),
            (),
            (),
        )
        graph = self._graph(partial, source)
        objects: list[ArtifactObject] = []
        with self._connection() as connection:
            if (
                digest(snapshot(self.repositories, connection, context, run_id))
                != partial.source_digest
            ):
                raise ArtifactError("publication_source_changed")
            for key, content in sorted(graph.objects.items()):
                row = (
                    connection.execute(
                        text(
                            "SELECT "
                            "id,project_id,digest,locator,format_version,byte_count,created_at "
                            "FROM artifact_objects WHERE project_id=:project AND "
                            "digest=:digest AND format_version=1 LIMIT 2"
                        ),
                        {"project": context.project_id, "digest": key},
                    )
                    .mappings()
                    .all()
                )
                if len(row) > 1:
                    raise ArtifactError("artifact_metadata_conflict")
                value = (
                    _object(row[0])
                    if row
                    else ArtifactObject(
                        uuid4().hex,
                        context.project_id,
                        key,
                        object_locator(context.project_id, key),
                        1,
                        len(content),
                        datetime.now(UTC),
                    )
                )
                if value.byte_count != len(content):
                    raise ArtifactError("artifact_metadata_conflict")
                objects.append(value)
        intent = PublicationIntent(
            **{**partial.__dict__, "objects": tuple(objects), "refs": graph.refs}
        )
        with self.journal.open(publication_id) as journal:
            journal.freeze(intent.record())
        return intent

    def load_intent(self, context: ProjectContext, publication_id: str) -> PublicationIntent:
        self.repositories.require_action(context, "read")
        with self.journal.open(publication_id) as journal:
            if journal.intent is None:
                raise ArtifactError("publication_intent_missing")
            intent = PublicationIntent.from_record(journal.intent)
        if intent.context != context or intent.publication_id != publication_id:
            raise ArtifactError("publication_intent_conflict")
        self.repositories.require_action(context, "read", kind="run", resource_id=intent.run_id)
        return intent

    def _complete(self, connection: Connection, intent: PublicationIntent) -> bool:
        self.repositories._authorize(connection, intent.context, "read")
        state = self.writer.inspect(connection, intent)
        if state == "absent":
            return False
        if state != "matching":
            raise ArtifactError("publication_root_conflict")
        reads = _Reads(connection, intent.context)
        for owner in {ref.owner_id for ref in intent.refs}:
            reads.resource("run", owner)
        by_digest = {obj.digest: obj for obj in intent.objects}
        for ref in intent.refs:
            self.repositories._authorize(connection, intent.context, "read")
            value = resolve_ref(
                connection,
                project_id=intent.context.project_id,
                owner_kind="run",
                owner_id=ref.owner_id,
                role=ref.role,
                digest=ref.digest,
            )
            if value != by_digest[ref.digest]:
                raise ArtifactError("publication_incomplete")
        return True

    def publish(self, intent: PublicationIntent, source: Callable[[GraphRef, int], bytes]) -> str:
        self.writer.require_available()
        with self.journal.open(intent.publication_id) as journal:
            if journal.intent is None:
                raise ArtifactError("publication_intent_missing")
            journal.freeze(intent.record())
            # Resolve an uncertain prior response before requiring a still-live
            # lease or performing another backend request. Read access is fresh.
            with self._connection() as connection:
                complete = self._complete(connection, intent)
            if complete:
                journal.append("commit_confirmed", {"root": intent.root_digest})
                return intent.root_digest
            graph = self._graph(intent, source)
            if graph.refs != intent.refs or set(graph.objects) != {
                obj.digest for obj in intent.objects
            }:
                raise ArtifactError("publication_intent_conflict")
            for obj in intent.objects:
                content = graph.objects[obj.digest]
                if len(content) != obj.byte_count:
                    raise ArtifactError("publication_intent_conflict")
                journal.append(
                    "upload_started",
                    {"object_id": obj.id, "digest": obj.digest, "backend_work": "UNKNOWN"},
                )
                try:
                    receipt = self.storage.put_verified(obj, content)
                except Exception:
                    journal.append(
                        "upload_unknown", {"object_id": obj.id, "backend_work": "UNKNOWN"}
                    )
                    raise ArtifactError("publication_upload_failed") from None
                if receipt.object != obj:
                    raise ArtifactError("publication_receipt_invalid")
                journal.append(
                    "upload_verified",
                    {
                        "object_id": obj.id,
                        "logical_writes": receipt.logical_writes,
                        "write_requests": receipt.write_requests,
                        "read_requests": receipt.read_requests,
                        "plaintext_bytes": receipt.plaintext_bytes,
                        "ciphertext_bytes": receipt.ciphertext_bytes,
                        "cache_hit": receipt.cache_hit,
                    },
                )
            journal.append("commit_pending", {"root": intent.root_digest, "sql_commit": "UNKNOWN"})
            try:
                with self._connection(write=True) as connection:
                    self.writer.lock_and_check(connection, intent)
                    if (
                        digest(
                            snapshot(
                                self.repositories,
                                connection,
                                intent.context,
                                intent.run_id,
                                lock=True,
                            )
                        )
                        != intent.source_digest
                    ):
                        raise ArtifactError("publication_source_changed")
                    if self._complete(connection, intent):
                        pass
                    else:
                        by_digest = {obj.digest: obj for obj in intent.objects}
                        for ref in intent.refs:
                            if ref.owner_id != intent.run_id:
                                obj = by_digest[ref.digest]
                                lock_ancestor_ref(
                                    connection,
                                    intent.context.project_id,
                                    ref.owner_id,
                                    ref.role,
                                    obj.id,
                                )
                                if (
                                    resolve_ref(
                                        connection,
                                        project_id=intent.context.project_id,
                                        owner_kind="run",
                                        owner_id=ref.owner_id,
                                        role=ref.role,
                                        digest=ref.digest,
                                    )
                                    != obj
                                ):
                                    raise ArtifactError("publication_ancestor_changed")
                        for obj in intent.objects:
                            record_verified(connection, obj)
                        for ref in intent.refs:
                            register_ref(
                                connection,
                                project_id=intent.context.project_id,
                                owner_kind="run",
                                owner_id=ref.owner_id,
                                role=ref.role,
                                artifact_id=by_digest[ref.digest].id,
                            )
                        self.repositories._authorize(connection, intent.context, "record")
                        self.writer.publish_root(connection, intent)
                        if not self._complete(connection, intent):
                            raise ArtifactError("publication_incomplete")
            except Exception as exc:
                journal.append(
                    "commit_unknown", {"root": intent.root_digest, "sql_commit": "UNKNOWN"}
                )
                if isinstance(exc, ArtifactError):
                    raise
                if isinstance(exc, SQLAlchemyError):
                    raise ArtifactError("publication_database_unavailable") from None
                raise
            journal.append("commit_confirmed", {"root": intent.root_digest})
            return intent.root_digest

    def read(self, context: ProjectContext, run_id: str, root_digest: str) -> VerifiedGraph:
        """Compatibility entry point; reading needs no journal or available writer."""
        return self.reader.read(context, run_id, root_digest)
