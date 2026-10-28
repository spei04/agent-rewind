"""Actual PostgreSQL SQL-only run summaries; no customer-ready profile."""

from types import SimpleNamespace

import pytest
import test_migrations_postgres as migrations
import test_run_projection_postgres as projection_tests
from sqlalchemy import event, text
from test_run_projection_postgres import drain, preserved, source
from test_scoped_run_listing import NOW, PRINCIPAL, PROJECT, RUN1, RUN2, settings
from test_scoped_run_listing_bounds import add_runs

from agent_rewind import listing_session
from agent_rewind.errors import Fault
from agent_rewind.legacy_reads import ReadBudget
from agent_rewind.listing_projection import by_ids
from agent_rewind.listing_session import SQLWork, listing_connection
from agent_rewind.listing_sources import Sources
from agent_rewind.migrations.projection_service import backfill_run_index
from agent_rewind.scoped_lineage import ResourceNotFound
from agent_rewind.scoped_run_listing import ScopedRunReader

pg = projection_tests.pg
projection_profile = projection_tests.projection_profile
observed_reader = projection_tests.observed_reader
projected_legacy = projection_tests.projected_legacy
pytestmark = pytest.mark.skipif(not migrations.POSTGRES, reason="Opt-in synthetic PostgreSQL")


@pytest.fixture
def pg_listing(projected_legacy):
    pg = projected_legacy
    backfill_run_index(pg["owner"], source())
    drain(pg)
    with pg["owner"].begin() as connection:
        connection.exec_driver_sql(
            "GRANT SELECT ON organizations,projects,project_memberships,api_keys,"
            f"resource_scopes,records,jobs,run_index TO {pg['app_role']}"
        )
    return pg, ScopedRunReader(pg["app"], settings())


def test_postgres_list_detail_native_timestamps_ties_and_select_only(pg_listing):
    pg, reader = pg_listing
    with pg["app"].connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT has_table_privilege(current_user,'run_index','SELECT'),"
            "has_table_privilege(current_user,'run_index','UPDATE'),"
            "has_table_privilege(current_user,'records','UPDATE'),"
            "has_schema_privilege(current_user,'public','CREATE')"
        ).one() == (True, False, False, False)
    page = reader.list(PRINCIPAL, PROJECT, now=NOW, limit=1)
    assert [x["id"] for x in page.items] == [RUN2] and page.next_cursor
    tail = reader.list(PRINCIPAL, PROJECT, now=NOW, cursor=page.next_cursor)
    assert [x["id"] for x in tail.items] == [RUN1] and tail.next_cursor is None
    for item in (*page.items, *tail.items):
        assert item["created_at"] == "2023-11-14T22:13:20.125000+00:00"
        assert item["status"] == "complete"
        assert reader.detail(PRINCIPAL, PROJECT, item["id"]) == item
    preserved(pg["owner"])


def test_postgres_max_page_deep_keysets_and_late_backfills(pg_listing):
    pg, reader = pg_listing
    with pg["owner"].begin() as writer:
        ids = add_runs(writer, 201, parent=RUN1)
    first = reader.list(PRINCIPAL, PROJECT, now=NOW, limit=200)
    assert [x["id"] for x in first.items] == sorted(ids, reverse=True)[:200]
    assert first.next_cursor
    with pg["owner"].begin() as writer:
        late = add_runs(writer, 50, first=2000, created=1699999999.0)
    tail = reader.list(PRINCIPAL, PROJECT, now=NOW, cursor=first.next_cursor)
    assert [x["id"] for x in tail.items] == [min(ids), RUN2, RUN1]
    assert tail.next_cursor is None and not set(late) & {x["id"] for x in tail.items}
    cursor, seen = None, []
    while True:
        page = reader.list(PRINCIPAL, PROJECT, now=NOW, limit=7, cursor=cursor)
        seen.extend(x["id"] for x in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert len(seen) == len(set(seen)) == 253
    assert seen[:201] == sorted(ids, reverse=True)
    assert seen[-50:] == sorted(late, reverse=True)


@pytest.mark.parametrize("mutation", ["source", "projection", "job_scope", "phantom", "revoke"])
def test_postgres_original_receipts_and_final_fresh_authority(pg_listing, monkeypatch, mutation):
    pg, reader = pg_listing
    original = reader._finish

    def changed(principal, context, entries, sources, work):
        with pg["owner"].begin() as writer:
            if mutation == "source":
                writer.execute(
                    text("UPDATE records SET created=created+1 WHERE id=:id"), {"id": RUN1}
                )
            elif mutation == "projection":
                writer.execute(
                    text("UPDATE run_index SET branchable=false WHERE run_id=:id"), {"id": RUN1}
                )
            elif mutation == "job_scope":
                writer.execute(
                    text(
                        "DELETE FROM resource_scopes WHERE resource_kind='job' AND resource_id=:id"
                    ),
                    {"id": next(iter(sources.jobs))},
                )
            elif mutation == "phantom":
                writer.execute(
                    text(
                        "INSERT INTO records SELECT :id,kind,created,data "
                        "FROM records WHERE id=:old"
                    ),
                    {"id": "3" * 32, "old": RUN1},
                )
                writer.execute(
                    text("INSERT INTO resource_scopes VALUES('run',:id,:project)"),
                    {"id": "3" * 32, "project": PROJECT},
                )
            else:
                writer.execute(text("UPDATE project_memberships SET revoked_at=CURRENT_TIMESTAMP"))
        return original(principal, context, entries, sources, work)

    monkeypatch.setattr(reader, "_finish", changed)
    with pytest.raises(ResourceNotFound if mutation == "revoke" else Fault):
        reader.list(PRINCIPAL, PROJECT, now=NOW)


def test_postgres_revocation_committed_after_receipt_query_still_refuses(pg_listing):
    pg, reader = pg_listing
    changed = []

    def after(_connection, _cursor, statement, _parameters, _context, _many):
        if "matching_projections" in statement and not changed:
            with pg["owner"].begin() as writer:
                writer.execute(text("UPDATE project_memberships SET revoked_at=CURRENT_TIMESTAMP"))
            changed.append(True)

    event.listen(pg["app"], "after_cursor_execute", after)
    try:
        with pytest.raises(ResourceNotFound):
            reader.detail(PRINCIPAL, PROJECT, RUN1)
    finally:
        event.remove(pg["app"], "after_cursor_execute", after)
    assert changed == [True]


@pytest.mark.parametrize("change", [False, True])
def test_postgres_maximum_mixed_jsonb_source_projection_receipts(pg_listing, monkeypatch, change):
    pg, reader = pg_listing
    with pg["owner"].begin() as writer:
        ids = add_runs(writer, 682, parent=RUN1)
    # This maximum-size fixture proves receipt correctness, not wall latency.
    # Freeze only the adapter clock: native per-statement PostgreSQL timeouts
    # remain real. Separate session tests exercise 57014/55P03 cancellation,
    # cumulative remaining time, final-phase exhaustion and pool cleanup.
    monkeypatch.setattr(listing_session, "time", SimpleNamespace(monotonic=lambda: 0.0))
    work = SQLWork()
    with listing_connection(pg["app"], work) as connection:
        context = reader._context(connection, PRINCIPAL, PROJECT)
        entries = list(by_ids(connection, PROJECT, set(ids)).values())
        sources = Sources(context, ReadBudget(nodes=len(entries)))
        sources.load(connection, ids)
    assert len(sources.records) == len(sources.jobs) == 683 and sources.budget.nodes == 2048
    if change:
        with pg["owner"].begin() as writer:
            writer.execute(
                text("UPDATE jobs SET cancel=true WHERE id=:id"), {"id": next(iter(sources.jobs))}
            )
        with pytest.raises(Fault, match="dependency_unavailable"):
            reader._finish(PRINCIPAL, context, entries, sources, work)
    else:
        reader._finish(PRINCIPAL, context, entries, sources, work)
    assert work.statements < 40


def test_postgres_permission_failure_is_fixed_and_counter_regression_refuses(pg_listing):
    pg, reader = pg_listing
    with pg["owner"].begin() as writer:
        writer.exec_driver_sql(f"REVOKE SELECT ON records FROM {pg['app_role']}")
    with pytest.raises(Fault, match="dependency_unavailable"):
        reader.list(PRINCIPAL, PROJECT, now=NOW)
    with pg["owner"].begin() as writer:
        writer.exec_driver_sql(f"GRANT SELECT ON records TO {pg['app_role']}")
        writer.execute(text("UPDATE projects SET run_sequence=0"))
    with pytest.raises(Fault, match="dependency_unavailable"):
        reader.list(PRINCIPAL, PROJECT, now=NOW)


@pytest.mark.parametrize("created", ["infinity", "-infinity", "10000-01-01 00:00:00+00"])
def test_postgres_unrepresentable_order_cell_refuses_before_cursor_filter(
    pg_listing, monkeypatch, created
):
    pg, reader = pg_listing
    # Prove timestamp rejection and recovery independently of host scheduling.
    # Native PostgreSQL timeouts remain real; session tests retain native
    # timeout, cumulative deadline and cleanup coverage.
    monkeypatch.setattr(listing_session, "time", SimpleNamespace(monotonic=lambda: 0.0))
    first = reader.list(PRINCIPAL, PROJECT, now=NOW, limit=1)
    assert first.next_cursor and first.items[0]["id"] == RUN2
    with pg["owner"].begin() as writer:
        writer.execute(
            text("UPDATE run_index SET created_at=CAST(:created AS TIMESTAMPTZ) WHERE run_id=:id"),
            {"created": created, "id": RUN1},
        )
    with pytest.raises(Fault, match="dependency_unavailable"):
        reader.list(PRINCIPAL, PROJECT, now=NOW, cursor=first.next_cursor)
    with pg["owner"].begin() as writer:
        writer.execute(
            text("UPDATE run_index SET created_at=CAST(:created AS TIMESTAMPTZ) WHERE run_id=:id"),
            {"created": "2023-11-14T22:13:20.125000+00:00", "id": RUN1},
        )
    tail = reader.list(PRINCIPAL, PROJECT, now=NOW, cursor=first.next_cursor)
    assert [item["id"] for item in tail.items] == [RUN1] and tail.next_cursor is None
