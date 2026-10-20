"""Actual coordinator composition against an explicit future PostgreSQL fence fixture.

These tests do not install or enable a production worker fence or customer route.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event
from uuid import uuid4

import pytest
import test_migrations_postgres as migrations
import test_run_projection_postgres as projection_tests
from conftest import FixturePolicy
from postgres_control import wait_for_database_drain
from publication_fixture import CONTEXT, WORKER, CaptureRunner, SQLFixtureWriter, make_capture
from sqlalchemy import insert, text
from test_artifact_postgres import prepare_postgres

from agent_rewind import projection_publication
from agent_rewind.artifact_metadata import ArtifactError
from agent_rewind.database import jobs
from agent_rewind.engine import Engine
from agent_rewind.migrations.projection_service import initialize_projection
from agent_rewind.projection_publication import ProjectionPublicationWriter
from agent_rewind.projection_rows import insert_projection, read_index
from agent_rewind.run_projection import RunProjection

pg = migrations.pg
projection_profile = projection_tests.projection_profile
pytestmark = pytest.mark.skipif(
    not migrations.POSTGRES, reason="Opt-in synthetic PostgreSQL projection publication"
)


@pytest.fixture
def projected_capture(pg, settings, projection_profile):
    prepare_postgres(pg)
    wait_for_database_drain(pg["control"], pg["owner"].url.database)
    initialize_projection(pg["owner"])
    capture = make_capture(settings, prepared_engine=pg["owner"])
    capture.publisher.writer = ProjectionPublicationWriter(SQLFixtureWriter())
    yield capture
    capture.db.engine.dispose()


def new_run(capture, task, *, created=None):
    """Separate running job for each fixture run; no shared-job serialization shortcut."""
    job = uuid4().hex
    with capture.db.engine.begin() as connection:
        connection.execute(
            insert(jobs).values(
                id=job,
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
        connection.execute(
            text("INSERT INTO resource_scopes VALUES('job',:job,:project)"),
            {"job": job, "project": CONTEXT.project_id},
        )
        connection.execute(text("INSERT INTO publication_fences VALUES(:job,1)"), {"job": job})
    capture.engine = Engine(
        capture.db, capture.artifacts, CaptureRunner(), FixturePolicy(), job, WORKER
    )
    run = capture.run(task)
    if created is not None:
        # A later imported run can legitimately have an older immutable source time.
        # Set the synthetic source before preparing any publication identity.
        with capture.db.engine.begin() as connection:
            connection.execute(
                text("UPDATE records SET created=:created WHERE id=:run"),
                {"created": created, "run": run},
            )
    return run


def outputs(capture):
    with capture.db.engine.connect() as connection:
        counts = {
            table: connection.exec_driver_sql("SELECT count(*) FROM " + table).scalar_one()
            for table in ("artifact_objects", "artifact_refs", "publication_roots", "run_index")
        }
        counter = connection.execute(
            text("SELECT run_sequence FROM projects WHERE id=:project"),
            {"project": CONTEXT.project_id},
        ).scalar_one()
        return counts, counter, read_index(connection, limit=100)


def wait_blocked(control, waiter, blocker):
    deadline = time.monotonic() + 10
    with control.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql("SET statement_timeout='1s'")
        while True:
            blocked = connection.execute(
                text("SELECT :blocker=ANY(pg_blocking_pids(:waiter))"),
                {"blocker": blocker, "waiter": waiter},
            ).scalar_one()
            if blocked:
                return
            remaining = deadline - time.monotonic()
            assert remaining > 0, "Expected synthetic publication lock was not observed"
            time.sleep(min(0.01, remaining))


def test_postgres_graph_root_index_counter_rollback_then_exact_retry(
    projected_capture, task, monkeypatch
):
    capture = projected_capture
    run = new_run(capture, task)
    intent = capture.intent(run)
    original = projection_publication.insert_projection

    def stop(connection, value):
        sequence = original(connection, value)
        assert sequence == 1
        assert (
            connection.exec_driver_sql("SELECT count(*) FROM publication_roots").scalar_one() == 1
        )
        assert connection.exec_driver_sql("SELECT count(*) FROM artifact_refs").scalar_one() > 0
        raise ArtifactError("synthetic_projection_after_insert")

    monkeypatch.setattr(projection_publication, "insert_projection", stop)
    with pytest.raises(ArtifactError, match="synthetic_projection_after_insert"):
        capture.publisher.publish(intent, capture.source)
    counts, counter, rows = outputs(capture)
    assert not any(counts.values()) and counter == 0 and rows == []
    with capture.journal.open(intent.publication_id) as journal:
        assert any(record["kind"] == "commit_unknown" for record in journal.records)
    monkeypatch.setattr(projection_publication, "insert_projection", original)
    assert capture.publisher.publish(intent, capture.source) == intent.root_digest
    before = outputs(capture)
    assert before[0]["run_index"] == before[0]["publication_roots"] == before[1] == 1
    assert (
        capture.publisher.publish(
            capture.publisher.load_intent(CONTEXT, intent.publication_id),
            lambda *_: pytest.fail("exact retry attempted artifact reads"),
        )
        == intent.root_digest
    )
    assert outputs(capture) == before


@pytest.mark.parametrize("rollback_first", [False, True], ids=["commit", "rollback"])
def test_postgres_competing_jobs_hold_project_sequence_until_commit(
    projected_capture, pg, task, monkeypatch, rollback_first
):
    capture = projected_capture
    # Register shared immutable task/workspace objects before preparing competitors;
    # their graph-specific objects remain distinct frozen identities.
    seed = new_run(capture, task)
    capture.publisher.publish(capture.intent(seed), capture.source)
    first_run, second_run = new_run(capture, task), new_run(capture, task)
    first, second = capture.intent(first_run), capture.intent(second_run)
    assert first.job_id != second.job_id
    entered, attempting, release = Event(), Event(), Event()
    pids = {}
    lock = capture.publisher.writer.lock_and_check
    publish = capture.publisher.writer.publish_root

    def held(connection, intent):
        if intent.publication_id == second.publication_id and not attempting.is_set():
            pids["second"] = connection.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
            attempting.set()
        lock(connection, intent)
        if intent.publication_id == first.publication_id and not entered.is_set():
            pids["first"] = connection.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
            entered.set()
            assert release.wait(15), "Synthetic competing publisher never released"

    def maybe_fail(connection, intent):
        publish(connection, intent)
        if rollback_first and intent.publication_id == first.publication_id:
            raise ArtifactError("synthetic_first_rollback")

    monkeypatch.setattr(capture.publisher.writer, "lock_and_check", held)
    monkeypatch.setattr(capture.publisher.writer, "publish_root", maybe_fail)
    with ThreadPoolExecutor(max_workers=2) as workers:
        first_work = workers.submit(capture.publisher.publish, first, capture.source)
        try:
            assert entered.wait(10)
            second_work = workers.submit(capture.publisher.publish, second, capture.source)
            assert attempting.wait(10)
            wait_blocked(pg["control"], pids["second"], pids["first"])
            counts, counter, rows = outputs(capture)
            assert counts["publication_roots"] == counts["run_index"] == counter == 1
            assert len(rows) == 1 and not second_work.done()
        finally:
            release.set()
        if rollback_first:
            with pytest.raises(ArtifactError, match="synthetic_first_rollback"):
                first_work.result(15)
        else:
            assert first_work.result(15) == first.root_digest
        assert second_work.result(15) == second.root_digest
    by_id = {row["run_id"]: row for row in outputs(capture)[2]}
    assert by_id[second_run]["published_seq"] == (2 if rollback_first else 3)
    if rollback_first:
        assert first_run not in by_id
    else:
        assert by_id[first_run]["published_seq"] == 2


def test_postgres_reversed_work_start_and_older_created_run_do_not_enter_old_watermark(
    projected_capture, task
):
    capture = projected_capture
    seed = new_run(capture, task, created=3000)
    capture.publisher.publish(capture.intent(seed), capture.source)
    early = new_run(capture, task, created=2000)
    late = new_run(capture, task, created=1000)
    early_intent, late_intent = capture.intent(early), capture.intent(late)
    start = Event()

    def delayed():
        assert start.wait(10)
        return capture.publisher.publish(early_intent, capture.source)

    with ThreadPoolExecutor(max_workers=1) as workers:
        submitted_first = workers.submit(delayed)
        try:
            assert capture.publisher.publish(late_intent, capture.source) == late_intent.root_digest
            with capture.db.engine.connect() as connection:
                watermark = connection.execute(
                    text("SELECT run_sequence FROM projects WHERE id=:project"),
                    {"project": CONTEXT.project_id},
                ).scalar_one()
        finally:
            start.set()
        assert submitted_first.result(15) == early_intent.root_digest
    with capture.db.engine.connect() as connection:
        frozen = connection.execute(
            text(
                "SELECT run_id,published_seq FROM run_index WHERE project_id=:project "
                "AND published_seq<=:watermark ORDER BY created_at DESC,run_id DESC"
            ),
            {"project": CONTEXT.project_id, "watermark": watermark},
        ).all()
        all_rows = read_index(connection, limit=10)
    assert [row[0] for row in frozen] == [seed, late]
    sequences = {row["run_id"]: row["published_seq"] for row in all_rows}
    assert sequences == {seed: 1, late: 2, early: 3}
    # AR-006-B owns cursor/API integration; this tests the SQL watermark invariant only.


def test_postgres_independent_project_can_commit_while_first_project_is_locked(
    projected_capture,
):
    capture = projected_capture
    first_project, other_project = CONTEXT.project_id, "7" * 32
    first_run, other_run = "5" * 32, "6" * 32
    with capture.db.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO projects(id,organization_id,name,created_at) "
                "VALUES(:id,:organization,'Independent',now())"
            ),
            {"id": other_project, "organization": CONTEXT.organization_id},
        )
        for run, project in ((first_run, first_project), (other_run, other_project)):
            connection.execute(text("INSERT INTO records VALUES(:id,'run',1,'{}')"), {"id": run})
            connection.execute(
                text("INSERT INTO resource_scopes VALUES('run',:id,:project)"),
                {"id": run, "project": project},
            )
    entered, release = Event(), Event()

    def value(run, project):
        return RunProjection(
            run, project, datetime(2026, 1, 1, tzinfo=UTC), "complete", True, None, None, None
        )

    def first():
        with capture.db.engine.begin() as connection:
            sequence = insert_projection(connection, value(first_run, first_project))
            entered.set()
            assert release.wait(10)
        return sequence

    with ThreadPoolExecutor(max_workers=1) as workers:
        pending = workers.submit(first)
        try:
            assert entered.wait(10)
            with capture.db.engine.begin() as connection:
                connection.exec_driver_sql("SET LOCAL lock_timeout='500ms'")
                assert insert_projection(connection, value(other_run, other_project)) == 1
            assert not pending.done()
        finally:
            release.set()
        assert pending.result(10) == 1
    with capture.db.engine.connect() as connection:
        assert sorted(row["published_seq"] for row in read_index(connection, limit=10)) == [1, 1]


def test_postgres_parent_republication_and_child_share_one_project_lock_order(
    projected_capture, pg, task, monkeypatch
):
    from agent_rewind.models import Action, Intervention

    capture = projected_capture
    parent = new_run(capture, task)
    original_parent = capture.intent(parent)
    capture.publisher.publish(original_parent, capture.source)
    child = capture.run(
        task,
        parent,
        Intervention(
            step=2,
            kind="action",
            action=Action(tool="write_file", path="source.py", content="correct"),
        ),
    )
    child_intent = capture.intent(child)
    replacement = capture.intent(parent, expected_root=original_parent.root_digest)
    assert child_intent.job_id != replacement.job_id
    assert replacement.publication_id != original_parent.publication_id
    entered, attempting, release = Event(), Event(), Event()
    pids = {}
    lock = capture.publisher.writer.lock_and_check

    def held(connection, intent):
        if intent.publication_id == replacement.publication_id and not attempting.is_set():
            pids["parent"] = connection.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
            attempting.set()
        lock(connection, intent)
        if intent.publication_id == child_intent.publication_id and not entered.is_set():
            pids["child"] = connection.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
            entered.set()
            assert release.wait(15)

    monkeypatch.setattr(capture.publisher.writer, "lock_and_check", held)
    with ThreadPoolExecutor(max_workers=2) as workers:
        child_work = workers.submit(capture.publisher.publish, child_intent, capture.source)
        try:
            assert entered.wait(10)
            parent_work = workers.submit(capture.publisher.publish, replacement, capture.source)
            assert attempting.wait(10)
            wait_blocked(pg["control"], pids["parent"], pids["child"])
            # A waiter must not hold its target job while waiting for the project.
            # Otherwise the child's upcoming ancestor SHARE lock forms a cycle.
            with capture.db.engine.begin() as connection:
                connection.execute(
                    text("SELECT id FROM jobs WHERE id=:job FOR UPDATE NOWAIT"),
                    {"job": replacement.job_id},
                ).scalar_one()
            assert not parent_work.done()
        finally:
            release.set()
        assert child_work.result(15) == child_intent.root_digest
        assert parent_work.result(15) == replacement.root_digest
    counts, counter, rows = outputs(capture)
    assert counts["publication_roots"] == counts["run_index"] == counter == 2
    sequences = {row["run_id"]: row["published_seq"] for row in rows}
    assert sequences == {parent: 1, child: 2}
    assert capture.publisher.read(CONTEXT, parent, replacement.root_digest).root_digest == (
        replacement.root_digest
    )


def test_postgres_exact_retry_refuses_allocator_below_published_sequence(projected_capture, task):
    capture = projected_capture
    run = new_run(capture, task)
    intent = capture.intent(run)
    capture.publisher.publish(intent, capture.source)
    with capture.db.engine.begin() as connection:
        connection.execute(
            text("UPDATE projects SET run_sequence=0 WHERE id=:id"),
            {"id": CONTEXT.project_id},
        )
    before = outputs(capture)
    with pytest.raises(ArtifactError, match="publication_root_conflict"):
        capture.publisher.publish(intent, lambda *_: pytest.fail("corruption read artifacts"))
    assert outputs(capture) == before  # No inferred allocator repair.
