"""Synthetic future fence/root contract, never installed by application migrations."""

import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from conftest import FixturePolicy, FixtureRunner
from cryptography.fernet import Fernet
from sqlalchemy import insert, select, text
from test_artifact_metadata import prepare
from test_ownership import FRESH

from agent_rewind.artifact_metadata import ArtifactError, configure_artifact_engine
from agent_rewind.artifact_publication import RunPublisher
from agent_rewind.artifact_storage import LocalArtifactStorage
from agent_rewind.artifacts import Artifacts
from agent_rewind.database import Database, jobs
from agent_rewind.engine import Engine
from agent_rewind.models import digest
from agent_rewind.publication_journal import PublicationJournal
from agent_rewind.scoped_repositories import ProjectContext
from agent_rewind.sqlite_ownership import owned_begin
from agent_rewind.workspace import File

CONTEXT = ProjectContext(
    FRESH["organization_id"], FRESH["project_id"], FRESH["principal_grants"][0]["principal_id"]
)
JOB = "a" * 32
WORKER = "synthetic-publication-worker"


class SQLFixtureWriter:
    def require_available(self):
        pass

    def inspect(self, connection, intent):
        row = (
            connection.execute(
                text("SELECT * FROM publication_roots WHERE project_id=:p AND run_id=:r"),
                {"p": intent.context.project_id, "r": intent.run_id},
            )
            .mappings()
            .first()
        )
        if row is None:
            return "absent" if intent.expected_root is None else "conflict"
        if row["publication_id"] != intent.publication_id:
            return "absent" if row["root_digest"] == intent.expected_root else "conflict"
        return (
            "matching"
            if (row["job_id"], row["generation"], row["root_digest"], row["intent_digest"])
            == (intent.job_id, intent.generation, intent.root_digest, digest(intent.record()))
            else "conflict"
        )

    def lock_and_check(self, connection, intent):
        if connection.dialect.name == "sqlite":
            connection.exec_driver_sql(
                "UPDATE publication_fences SET generation=generation WHERE 1=0"
            )
            now = "CAST(strftime('%s','now') AS REAL)"
        else:
            # Future producer hierarchy: project exclusion before job/run locks.
            # The ar4 fixture has no run counter, so lock the existing identity.
            connection.execute(
                text("SELECT id FROM projects WHERE id=:project FOR UPDATE"),
                {"project": intent.context.project_id},
            ).all()
            connection.execute(
                select(jobs.c.id).where(jobs.c.id == intent.job_id).with_for_update()
            ).all()
            connection.execute(
                text("SELECT job_id FROM publication_fences WHERE job_id=:job FOR UPDATE"),
                {"job": intent.job_id},
            ).all()
            now = "EXTRACT(EPOCH FROM clock_timestamp())"
        row = connection.execute(
            text(
                "SELECT j.id FROM jobs j JOIN publication_fences f ON f.job_id=j.id "
                "WHERE j.id=:job AND j.owner=:worker AND j.status='running' "
                f"AND j.cancel=false AND j.lease_until>{now} AND f.generation=:generation"
            ),
            {"job": intent.job_id, "worker": intent.worker_id, "generation": intent.generation},
        ).first()
        if row is None:
            raise ArtifactError("publication_fence_lost")

    def publish_root(self, connection, intent):
        self.lock_and_check(connection, intent)
        if self.inspect(connection, intent) != "absent":
            raise ArtifactError("publication_root_conflict")
        connection.execute(
            text(
                "INSERT INTO publication_roots "
                "VALUES(:project,:run,:publication,:job,:generation,:root,:intent) "
                "ON CONFLICT(project_id,run_id) DO UPDATE SET "
                "publication_id=excluded.publication_id,job_id=excluded.job_id,generation=excluded.generation,root_digest=excluded.root_digest,intent_digest=excluded.intent_digest"
            ),
            {
                "project": intent.context.project_id,
                "run": intent.run_id,
                "publication": intent.publication_id,
                "job": intent.job_id,
                "generation": intent.generation,
                "root": intent.root_digest,
                "intent": digest(intent.record()),
            },
        )


def install_future_contract(engine):
    with owned_begin(engine) as c:
        c.exec_driver_sql(
            "CREATE TABLE publication_fences(job_id VARCHAR(32) PRIMARY KEY "
            "REFERENCES jobs(id),generation INTEGER NOT NULL)"
        )
        c.exec_driver_sql(
            "CREATE TABLE publication_roots(project_id VARCHAR(32),run_id "
            "VARCHAR(32),publication_id VARCHAR(32),job_id "
            "VARCHAR(32),generation INTEGER,root_digest "
            "VARCHAR(64),intent_digest VARCHAR(64),PRIMARY "
            "KEY(project_id,run_id))"
        )
        c.execute(
            insert(jobs).values(
                id=JOB,
                kind="run",
                created=1,
                payload="0" * 64,
                status="running",
                owner=WORKER,
                lease_until=4102444800,
                cancel=False,
                budget=100,
                reserved=7,
            )
        )
        c.execute(
            text("INSERT INTO resource_scopes VALUES('job',:job,:project)"),
            {"job": JOB, "project": CONTEXT.project_id},
        )
        c.execute(text("INSERT INTO publication_fences VALUES(:job,1)"), {"job": JOB})


class CaptureRunner(FixtureRunner):
    def execute(self, image, files, action, timeout, guard):
        if action.tool == "read_file":
            files = {
                **files,
                "script": File(b"#!/bin/sh\n", 0o755, "file", -7),
                "folder": File(b"", 0o700, "directory", 12),
                "empty": File(b""),
                "binary": File(b"\x00\xff"),
            }
        return super().execute(image, files, action, timeout, guard)


@dataclass
class Capture:
    db: Database
    artifacts: Artifacts
    engine: Engine
    publisher: RunPublisher
    journal: PublicationJournal

    def run(self, task, *args, **kwargs):
        if args:
            job_id = uuid4().hex
            with owned_begin(self.db.engine) as c:
                c.execute(
                    insert(jobs).values(
                        id=job_id,
                        kind="branch",
                        created=1,
                        payload="0" * 64,
                        status="running",
                        owner=WORKER,
                        lease_until=4102444800,
                        cancel=False,
                        budget=100,
                        reserved=7,
                    )
                )
                c.execute(
                    text("INSERT INTO resource_scopes VALUES('job',:job,:project)"),
                    {"job": job_id, "project": CONTEXT.project_id},
                )
                c.execute(text("INSERT INTO publication_fences VALUES(:job,1)"), {"job": job_id})
            self.engine = Engine(
                self.db, self.artifacts, CaptureRunner(), FixturePolicy(), job_id, WORKER
            )
        run = self.engine.run(task, *args, **kwargs)
        with owned_begin(self.db.engine) as c:
            c.execute(
                text("INSERT INTO resource_scopes VALUES('run',:run,:project)"),
                {"run": run, "project": CONTEXT.project_id},
            )
        return run

    def source(self, ref, limit):
        # Explicit test-only capture bridge. No production legacy adoption API.
        value = self.artifacts.get(ref.digest)
        if len(value) > limit:
            raise ArtifactError("artifact_graph_limit")
        return value

    def intent(self, run, **kwargs):
        return self.publisher.prepare(
            CONTEXT, run, worker_id=WORKER, generation=1, source=self.source, **kwargs
        )


def make_capture(settings, *, prepared_engine=None):
    db = Database(settings)
    if prepared_engine is not None:
        db.engine.dispose()
        db.engine = prepared_engine
    configure_artifact_engine(db.engine)
    if prepared_engine is None:
        prepare(db.engine)
    install_future_contract(db.engine)
    artifacts = Artifacts(settings)
    engine = Engine(db, artifacts, CaptureRunner(), FixturePolicy(), JOB, WORKER)
    journal_root = Path(settings.data_dir) / "publication-journal"
    journal_root.mkdir(mode=0o700)
    fd = os.open(journal_root.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    journal = PublicationJournal(journal_root)
    storage = LocalArtifactStorage(
        settings.data_dir,
        Fernet(settings.encryption_key.get_secret_value().encode()),
        plaintext_limit=64 * 1024 * 1024,
    )
    return Capture(
        db,
        artifacts,
        engine,
        RunPublisher(db.engine, storage, journal, writer=SQLFixtureWriter()),
        journal,
    )
