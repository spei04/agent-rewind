"""Real PostgreSQL transactions with explicit synthetic future fence/root tables."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
import test_migrations_postgres as migrations
from publication_fixture import CONTEXT, make_capture
from sqlalchemy import text
from test_artifact_postgres import prepare_postgres

from agent_rewind.artifact_metadata import ArtifactError

pg = migrations.pg
pytestmark = pytest.mark.skipif(
    not migrations.POSTGRES, reason="Opt-in synthetic PostgreSQL publication"
)


@pytest.fixture
def capture_pg(pg, settings):
    prepare_postgres(pg)
    capture = make_capture(settings, prepared_engine=pg["owner"])
    yield capture
    capture.db.engine.dispose()


def test_postgres_complete_graph_and_exact_reentry(capture_pg, task):
    capture = capture_pg
    run = capture.run(task)
    intent = capture.intent(run)
    capture.publisher.publish(intent, capture.source)
    recovered = capture.publisher.load_intent(CONTEXT, intent.publication_id)
    assert recovered == intent
    assert (
        capture.publisher.publish(recovered, lambda *_: pytest.fail("repeat upload"))
        == intent.root_digest
    )
    assert (
        capture.publisher.read(CONTEXT, run, intent.root_digest).root_digest == intent.root_digest
    )


def test_postgres_partial_refs_rollback_and_orphans(capture_pg, task, monkeypatch):
    capture = capture_pg
    run = capture.run(task)
    intent = capture.intent(run)

    def fail(connection, value):
        raise ArtifactError("synthetic_root_failure")

    monkeypatch.setattr(capture.publisher.writer, "publish_root", fail)
    with pytest.raises(ArtifactError, match="synthetic_root_failure"):
        capture.publisher.publish(intent, capture.source)
    with capture.db.engine.connect() as c:
        for table in ("artifact_objects", "artifact_refs", "publication_roots"):
            assert c.exec_driver_sql("SELECT count(*) FROM " + table).scalar_one() == 0
    with capture.journal.open(intent.publication_id) as journal:
        assert len([r for r in journal.records if r["kind"] == "upload_verified"]) == len(
            intent.objects
        )


def test_postgres_reader_observes_only_complete_committed_roots(capture_pg, task, monkeypatch):
    capture = capture_pg
    run = capture.run(task)
    old = capture.intent(run)
    capture.publisher.publish(old, capture.source)
    new = capture.intent(run, expected_root=old.root_digest)
    entered, released = Event(), Event()
    publish = capture.publisher.writer.publish_root

    def held(connection, intent):
        entered.set()
        assert released.wait(10)
        publish(connection, intent)

    monkeypatch.setattr(capture.publisher.writer, "publish_root", held)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(capture.publisher.publish, new, capture.source)
        try:
            assert entered.wait(10)
            with capture.db.engine.connect() as c:
                assert (
                    c.exec_driver_sql("SELECT root_digest FROM publication_roots").scalar_one()
                    == old.root_digest
                )
                assert (
                    c.execute(
                        text(
                            "SELECT count(*) FROM artifact_refs r JOIN artifact_objects o "
                            "ON o.id=r.artifact_id WHERE o.digest=:digest"
                        ),
                        {"digest": new.root_digest},
                    ).scalar_one()
                    == 0
                )
            assert (
                capture.publisher.read(CONTEXT, run, old.root_digest).root_digest == old.root_digest
            )
        finally:
            released.set()
        assert future.result(10) == new.root_digest
    assert capture.publisher.read(CONTEXT, run, new.root_digest).root_digest == new.root_digest


def test_postgres_competing_frozen_identities_never_overwrite(capture_pg, task):
    capture = capture_pg
    run = capture.run(task)
    first = capture.intent(run)
    second = capture.intent(run)
    assert any(a.digest == b.digest and a.id != b.id for a in first.objects for b in second.objects)

    def execute(intent):
        try:
            return capture.publisher.publish(intent, capture.source)
        except ArtifactError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(execute, intent) for intent in (first, second)]
        outcomes = [future.result(20) for future in futures]
    assert sum(item in {first.root_digest, second.root_digest} for item in outcomes) == 1
    assert outcomes.count("publication_root_conflict") == 1
    with capture.db.engine.connect() as c:
        assert c.exec_driver_sql("SELECT count(*) FROM publication_roots").scalar_one() == 1


@pytest.mark.parametrize("mode", ["engine_option", "pooled_driver"])
def test_postgres_effective_autocommit_refuses_before_sql_mutation(
    capture_pg, task, monkeypatch, mode
):
    from sqlalchemy import create_engine

    capture = capture_pg
    run = capture.run(task)
    intent = capture.intent(run)
    pooled = None
    if mode == "engine_option":
        capture.publisher.engine = capture.db.engine.execution_options(isolation_level="AUTOCOMMIT")
    else:
        pooled = create_engine(capture.db.engine.url, pool_size=1, max_overflow=0)
        with pooled.connect() as connection:
            connection.connection.driver_connection.autocommit = True
        capture.publisher.engine = pooled
    try:
        monkeypatch.setattr(
            capture.publisher.writer,
            "lock_and_check",
            lambda *_: pytest.fail("autocommit reached writer"),
        )
        with pytest.raises(ArtifactError, match="publication_transaction_required"):
            capture.publisher.publish(intent, capture.source)
        with capture.db.engine.connect() as c:
            for table in ("artifact_objects", "artifact_refs", "publication_roots"):
                assert c.exec_driver_sql("SELECT count(*) FROM " + table).scalar_one() == 0
    finally:
        if pooled is not None:
            pooled.dispose()


@pytest.mark.parametrize(
    "dependency", ["ancestor_job", "ancestor_scope", "study_record", "by_job_membership"]
)
def test_postgres_validated_closure_is_locked_through_publication_commit(
    capture_pg, task, monkeypatch, dependency
):
    from sqlalchemy import insert, update
    from sqlalchemy.exc import DBAPIError

    from agent_rewind.database import jobs, records
    from agent_rewind.models import Action, Intervention

    capture = capture_pg
    parent = capture.run(task)
    parent_intent = capture.intent(parent)
    capture.publisher.publish(parent_intent, capture.source)
    child = capture.run(
        task,
        parent,
        Intervention(
            step=2,
            kind="action",
            action=Action(tool="write_file", path="source.py", content="correct"),
        ),
    )
    child_job = capture.db.get(child)["job_id"]
    study = "f" * 32
    if dependency == "study_record":
        with capture.db.engine.begin() as c:
            c.execute(update(jobs).where(jobs.c.id == child_job).values(kind="study"))
            c.execute(
                insert(records).values(
                    id=study,
                    kind="study",
                    created=1,
                    data={
                        "job_id": child_job,
                        "source_run": parent,
                        "request": {"run_id": parent},
                        "candidates": [],
                        "confirmation": None,
                    },
                )
            )
            c.execute(
                text("INSERT INTO resource_scopes VALUES('study',:study,:project)"),
                {"study": study, "project": CONTEXT.project_id},
            )
    intent = capture.intent(child)
    entered, released = Event(), Event()
    complete = capture.publisher._complete

    def held(connection, value):
        result = complete(connection, value)
        if result:
            entered.set()
            assert released.wait(10)
        return result

    monkeypatch.setattr(capture.publisher, "_complete", held)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(capture.publisher.publish, intent, capture.source)
        try:
            assert entered.wait(10)
            with pytest.raises(DBAPIError) as refused, capture.db.engine.begin() as c:
                c.exec_driver_sql("SET LOCAL lock_timeout='250ms'")
                if dependency == "ancestor_job":
                    c.execute(
                        text("UPDATE jobs SET kind='branch' WHERE id=:job"),
                        {"job": parent_intent.job_id},
                    )
                elif dependency == "ancestor_scope":
                    c.execute(
                        text(
                            "DELETE FROM resource_scopes WHERE resource_kind='job' "
                            "AND resource_id=:job"
                        ),
                        {"job": parent_intent.job_id},
                    )
                elif dependency == "study_record":
                    c.execute(
                        text("UPDATE records SET data='{}'::json WHERE id=:study"), {"study": study}
                    )
                else:
                    # Required producer discipline: serialize even a new member
                    # on its job before inserting/reassigning a by_job record.
                    c.execute(
                        text("SELECT id FROM jobs WHERE id=:job FOR UPDATE"),
                        {"job": parent_intent.job_id},
                    )
                    c.execute(
                        insert(records).values(
                            id="e" * 32,
                            kind="run",
                            created=1,
                            data={"job_id": parent_intent.job_id, "parent_id": None},
                        )
                    )
            assert refused.value.orig.sqlstate == "55P03"
        finally:
            released.set()
        assert pending.result(10) == intent.root_digest
    assert (
        capture.publisher.read(CONTEXT, child, intent.root_digest).root_digest == intent.root_digest
    )
