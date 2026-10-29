"""Adversarial SQL work and pagination fixtures; no storage or runtime admission."""

import json
from datetime import timedelta
from types import SimpleNamespace

import pytest
import test_scoped_run_listing as listing_tests
from sqlalchemy import insert, text
from test_scoped_run_listing import NOW, PRINCIPAL, PROJECT, RUN1, RUN2

from agent_rewind import listing_session, scoped_run_listing
from agent_rewind.database import jobs, records
from agent_rewind.errors import Fault
from agent_rewind.listing_session import SQLWork
from agent_rewind.run_projection import utc_created

listing = listing_tests.listing
legacy = listing_tests.legacy


def add_runs(connection, count, *, first=1000, created=1700000100.0, parent=None):
    """Synthetic SQL population from the actual fixture's supported manifest shape.

    This tests query work/ordering only, not new capture or publication integrity.
    """
    original = json.loads(
        connection.execute(
            text("SELECT CAST(data AS TEXT) FROM records WHERE id=:id"), {"id": RUN1}
        ).scalar_one()
    )
    original_job = dict(
        connection.execute(text("SELECT * FROM jobs WHERE id=:id"), {"id": original["job_id"]})
        .mappings()
        .one()
    )
    start = connection.execute(
        text("SELECT run_sequence FROM projects WHERE id=:id"), {"id": PROJECT}
    ).scalar_one()
    ids = []
    for i in range(count):
        run_id, job_id = f"{first + i:032x}", f"{first + i + 1000000:032x}"
        ids.append(run_id)
        job = {
            **original_job,
            "id": job_id,
            "kind": "run" if parent is None else "branch",
            "status": "succeeded",
            "cancel": False,
            "owner": None,
            "lease_until": None,
        }
        connection.execute(insert(jobs).values(**job))
        body = {**original, "job_id": job_id, "parent_id": parent, "status": "complete"}
        connection.execute(
            insert(records).values(id=run_id, kind="run", created=created, data=body)
        )
        for kind, identity in [("run", run_id), ("job", job_id)]:
            connection.execute(
                text("INSERT INTO resource_scopes VALUES(:kind,:id,:project)"),
                {"kind": kind, "id": identity, "project": PROJECT},
            )
        connection.execute(
            text(
                "INSERT INTO run_index VALUES(:id,:project,'run',:created,'complete',true,"
                ":parent,:head,:sequence,NULL)"
            ),
            {
                "id": run_id,
                "project": PROJECT,
                "created": utc_created(created).isoformat(),
                "parent": parent,
                "head": original["head"],
                "sequence": start + i + 1,
            },
        )
    connection.execute(
        text("UPDATE projects SET run_sequence=:seq WHERE id=:id"),
        {"seq": start + count, "id": PROJECT},
    )
    return ids


def test_max_page_shared_ancestor_is_set_oriented_under_native_budget(listing, monkeypatch):
    _, engine, reader = listing
    with engine.begin() as connection:
        ids = add_runs(connection, 201, parent=RUN1)
    works = []

    def tracked_work():
        work = SQLWork()
        works.append(work)
        return work

    monkeypatch.setattr(scoped_run_listing, "SQLWork", tracked_work)
    page = reader.list(PRINCIPAL, PROJECT, now=NOW, limit=200)
    assert [item["id"] for item in page.items] == sorted(ids, reverse=True)[:200]
    assert page.next_cursor and all(item["branchable"] for item in page.items)
    assert len(works) == 1
    assert works[0].statements < 40
    assert works[0].instructions <= 20_000_000
    assert works[0].seconds < 2.0
    assert engine.pool.checkedout() == 0


def test_late_old_timestamp_and_rollback_do_not_enter_initial_watermark(listing):
    _, engine, reader = listing
    page = reader.list(PRINCIPAL, PROJECT, now=NOW, limit=1)
    assert page.items[0]["id"] == RUN2 and page.next_cursor
    with engine.begin() as connection:
        late = add_runs(connection, 1, created=1700000000.0)[0]
    with pytest.raises(RuntimeError, match="rollback fixture"), engine.begin() as connection:
        rolled_back = add_runs(connection, 1, first=2000, created=1699999999.0)[0]
        raise RuntimeError("rollback fixture")
    second = reader.list(
        PRINCIPAL, PROJECT, now=NOW + timedelta(seconds=899), cursor=page.next_cursor
    )
    assert [x["id"] for x in second.items] == [RUN1]
    assert second.next_cursor is None
    current = reader.list(PRINCIPAL, PROJECT, now=NOW)
    assert [x["id"] for x in current.items] == [RUN2, RUN1, late]
    assert rolled_back not in [x["id"] for x in current.items]
    with pytest.raises(Fault, match="invalid_cursor"):
        reader.list(PRINCIPAL, PROJECT, now=NOW + timedelta(seconds=900), cursor=page.next_cursor)


@pytest.mark.parametrize(
    "field,value",
    [
        ("created", b"1"),
        ("created", "1" + "\0" + "x" * 100000),
        ("data", '{"status":'),
        ("data", '{"status":1,"status":2}'),
    ],
)
def test_malformed_selected_source_refuses_without_partial_page(listing, field, value):
    _, engine, reader = listing
    with engine.begin() as connection:
        connection.execute(
            text(f"UPDATE records SET {field}=:value WHERE id=:id"), {"value": value, "id": RUN2}
        )
    with pytest.raises(Fault, match="dependency_unavailable"):
        reader.list(PRINCIPAL, PROJECT, now=NOW)


def test_malformed_job_boolean_is_not_truthy_and_partial_missing_parent_is_404(listing):
    from agent_rewind.scoped_lineage import ResourceNotFound

    _, engine, reader = listing
    with engine.begin() as connection:
        connection.execute(text("UPDATE jobs SET cancel=2"))
    with pytest.raises(Fault, match="dependency_unavailable"):
        reader.detail(PRINCIPAL, PROJECT, RUN2)
    with engine.begin() as connection:
        connection.execute(text("UPDATE jobs SET cancel=false"))
        # The current source points to an unmapped parent. It cannot gain access
        # by keeping its old projection's represented parent.
        data = json.loads(
            connection.execute(
                text("SELECT data FROM records WHERE id=:id"), {"id": RUN2}
            ).scalar_one()
        )
        data["parent_id"] = "f" * 32
        connection.execute(
            text("UPDATE records SET data=:data WHERE id=:id"),
            {"data": json.dumps(data), "id": RUN2},
        )
    with pytest.raises(ResourceNotFound):
        reader.detail(PRINCIPAL, PROJECT, RUN2)


def test_many_excluded_backfills_have_native_work_refusal_and_pool_reuse(listing, monkeypatch):
    from agent_rewind import listing_session

    _, engine, reader = listing
    page = reader.list(PRINCIPAL, PROJECT, now=NOW, limit=1)
    with engine.begin() as connection:
        # New rows lie between the two original tie tuples by created time;
        # they must be inspected/excluded, never included by old watermark.
        add_runs(connection, 300, created=1700000000.125, first=int("18" * 16, 16))
    # Deterministic native VM ceiling, not elapsed-time synchronization. An
    # exhausted operation must return no page and leave no callback/checkout.
    works, attempted = [], []

    def tracked():
        work = SQLWork()
        works.append(work)
        return work

    original = scoped_run_listing.candidates

    def limited(*args):
        attempted.append(True)
        monkeypatch.setattr(listing_session, "MAX_VM_INSTRUCTIONS", works[-1].instructions + 1000)
        return original(*args)

    with monkeypatch.context() as patch:
        patch.setattr(scoped_run_listing, "SQLWork", tracked)
        patch.setattr(scoped_run_listing, "candidates", limited)
        with pytest.raises(Fault, match="dependency_unavailable"):
            reader.list(PRINCIPAL, PROJECT, now=NOW, cursor=page.next_cursor)
    assert attempted == [True] and engine.pool.checkedout() == 0
    monkeypatch.setattr(listing_session, "MAX_VM_INSTRUCTIONS", 20_000_000)
    continuation = reader.list(PRINCIPAL, PROJECT, now=NOW, cursor=page.next_cursor)
    assert [item["id"] for item in continuation.items] == [RUN1]


@pytest.mark.parametrize("value", ["bad", b"bad", -1, 0])
def test_invalid_sequence_cannot_disappear_behind_watermark(listing, value):
    _, engine, reader = listing
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA ignore_check_constraints=ON")
        connection.execute(
            text("UPDATE run_index SET published_seq=:v WHERE run_id=:id"), {"v": value, "id": RUN2}
        )
    with pytest.raises(Fault, match="dependency_unavailable"):
        reader.list(PRINCIPAL, PROJECT, now=NOW, limit=1)


def test_counter_behind_existing_rows_never_returns_an_empty_page(listing):
    _, engine, reader = listing
    with engine.begin() as connection:
        connection.execute(text("UPDATE projects SET run_sequence=0"))
    with pytest.raises(Fault, match="dependency_unavailable"):
        reader.list(PRINCIPAL, PROJECT, now=NOW)


@pytest.mark.parametrize("foreign", [False, True])
@pytest.mark.parametrize("malformed", [False, True])
def test_incoming_cohort_bounds_and_foreign_scope_behavior(
    listing, foreign, malformed, monkeypatch
):
    # Cohort bounds and foreign-scope semantics are independent of elapsed scheduling.
    # Native SQL and statement/VM guards remain active; separate controls cover
    # elapsed deadlines and the real native-work budget.
    monkeypatch.setattr(listing_session, "time", SimpleNamespace(monotonic=lambda: 0.0))
    from agent_rewind.scoped_repositories import MAX_RECORD_BYTES

    _, engine, reader = listing
    with engine.begin() as writer:
        original = json.loads(
            writer.execute(text("SELECT data FROM records WHERE id=:id"), {"id": RUN1}).scalar_one()
        )
        body = (
            "{" if malformed else json.dumps({**original, "padding": "x" * (MAX_RECORD_BYTES + 1)})
        )
        project = "7" * 32 if foreign else PROJECT
        if foreign:
            writer.execute(
                text(
                    "INSERT INTO projects(id,organization_id,name,created_at,run_sequence) "
                    "SELECT :id,organization_id,'Foreign',created_at,0 FROM projects WHERE id=:old"
                ),
                {"id": project, "old": PROJECT},
            )
        writer.execute(
            text("INSERT INTO records VALUES(:id,'run',1,:body)"), {"id": "3" * 32, "body": body}
        )
        writer.execute(
            text("INSERT INTO resource_scopes VALUES('run',:id,:project)"),
            {"id": "3" * 32, "project": project},
        )
    if foreign and not malformed:
        # Valid foreign content stays outside the requested cohort. Malformed
        # foreign SQLite JSON may still be evaluated by the final anti-join;
        # that unsupported database state produces a bounded fixed refusal,
        # not a portable promise about optimizer expression order.
        page = reader.list(PRINCIPAL, PROJECT, now=NOW)
        assert [row["id"] for row in page.items] == [RUN2, RUN1]
    else:
        with pytest.raises(Fault, match="dependency_unavailable"):
            reader.list(PRINCIPAL, PROJECT, now=NOW)


def test_study_links_stop_at_remaining_edge_allowance(monkeypatch):
    from agent_rewind import listing_sources
    from agent_rewind.listing_sources import Sources

    calls = []
    original = listing_sources.identifier

    def counted(value):
        calls.append(value)
        return original(value)

    monkeypatch.setattr(listing_sources, "identifier", counted)
    body = {
        "job_id": "1" * 32,
        "source_run": "2" * 32,
        "candidates": [{"pairs": [{"control_run": "3" * 32}] * 10000}],
        "confirmation": None,
    }
    with pytest.raises(Fault, match="dependency_unavailable"):
        Sources._links("study", body, 7)
    assert len(calls) == 7  # No 10,000-link transient list is materialized.


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(b"2023-11-14T22:13:20.125000+00:00", id="blob"),
        pytest.param("z" * 100000, id="oversized"),
        pytest.param("9999-02-30T00:00:00+00:00", id="february-30"),
        pytest.param("2025-02-29T00:00:00+00:00", id="non-leap-day"),
        pytest.param("2024-01-01T24:00:00+00:00", id="hour-24"),
        pytest.param("9999-01-01T00:00:00.000000+00:00", id="zero-fraction"),
        pytest.param("9999-01-01T00:00:00+01:00", id="offset"),
        pytest.param("9999-01-01T00:00:00+00:00\0", id="nul-suffix"),
    ],
)
def test_invalid_order_cell_cannot_vanish_before_continuation(listing, monkeypatch, value):
    # This tests malformed-order detection and recovery, independently of host
    # scheduling. Native SQL and the statement/instruction limits stay active;
    # the paired continuation test below covers the unchanged elapsed-time cap.
    monkeypatch.setattr(listing_session, "time", SimpleNamespace(monotonic=lambda: 0.0))
    _, engine, reader = listing
    first = reader.list(PRINCIPAL, PROJECT, now=NOW, limit=1)
    assert [row["id"] for row in first.items] == [RUN2] and first.next_cursor
    with engine.begin() as connection:
        original = connection.execute(
            text("SELECT created_at FROM run_index WHERE run_id=:id"), {"id": RUN1}
        ).scalar_one()
        # DATETIME has no SQLite type/CHECK constraint. This mutation does not
        # disable enforcement or alter schema, but can sort above the cursor.
        connection.execute(
            text("UPDATE run_index SET created_at=:value WHERE run_id=:id"),
            {"value": value, "id": RUN1},
        )
    with pytest.raises(Fault, match="dependency_unavailable"):
        reader.list(PRINCIPAL, PROJECT, now=NOW, cursor=first.next_cursor)
    assert engine.pool.checkedout() == 0
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE run_index SET created_at=:value WHERE run_id=:id"),
            {"value": original, "id": RUN1},
        )
    tail = reader.list(PRINCIPAL, PROJECT, now=NOW, cursor=first.next_cursor)
    assert [row["id"] for row in tail.items] == [RUN1] and tail.next_cursor is None


@pytest.mark.parametrize(
    ("elapsed", "refused"),
    [pytest.param(1.0, False, id="below-deadline"), pytest.param(2.0, True, id="at-deadline")],
)
def test_continuation_clock_refusal_and_pool_reuse(listing, monkeypatch, elapsed, refused):
    _, engine, reader = listing
    clock = [0.0]
    monkeypatch.setattr(listing_session, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    first = reader.list(PRINCIPAL, PROJECT, now=NOW, limit=1)
    assert [row["id"] for row in first.items] == [RUN2] and first.next_cursor
    work = SQLWork()
    observed = []
    original = scoped_run_listing.candidates

    def candidates(*args, **kwargs):
        result = original(*args, **kwargs)
        observed.append([entry.value.run_id for entry in result[1]])
        # Advance only after the actual continuation query. The next native
        # target must honor cumulative elapsed time before returning any page.
        clock[0] = elapsed
        return result

    with monkeypatch.context() as patch:
        patch.setattr(scoped_run_listing, "candidates", candidates)
        patch.setattr(scoped_run_listing, "SQLWork", lambda: work)
        if refused:
            with pytest.raises(Fault, match="dependency_unavailable"):
                reader.list(PRINCIPAL, PROJECT, now=NOW, cursor=first.next_cursor)
        else:
            tail = reader.list(PRINCIPAL, PROJECT, now=NOW, cursor=first.next_cursor)
            assert [row["id"] for row in tail.items] == [RUN1] and tail.next_cursor is None
    assert observed == [[RUN1]]
    assert work.seconds == elapsed and work.started is None
    assert engine.pool.checkedout() == 0
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA query_only").scalar_one() == 0
        assert not connection.connection.driver_connection.in_transaction
    # A new request owns a new budget after either the refusal or valid page.
    clock[0] = 0.0
    tail = reader.list(PRINCIPAL, PROJECT, now=NOW, cursor=first.next_cursor)
    assert [row["id"] for row in tail.items] == [RUN1] and tail.next_cursor is None
    assert engine.pool.checkedout() == 0
