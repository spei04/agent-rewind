"""Actual frozen history, scoped keysets and original SQL receipt invariants."""

import base64
import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr
from sqlalchemy import event, text
from test_run_projection_backfill import preserved

from agent_rewind.config import Settings
from agent_rewind.errors import Fault
from agent_rewind.migrations.compatibility import runtime_schema_compatibility
from agent_rewind.migrations.projection_service import backfill_run_index, initialize_projection
from agent_rewind.request_identity import IdentityInvalid, VerifiedPrincipal
from agent_rewind.scoped_lineage import ResourceNotFound
from agent_rewind.scoped_run_listing import ScopedRunReader

pytest_plugins = ["test_run_projection_backfill"]

NOW = datetime(2026, 1, 1, tzinfo=UTC)
PROJECT = "9" * 32
PRINCIPAL = VerifiedPrincipal("oidc:" + "a" * 64)
RUN1, RUN2 = "1" * 32, "2" * 32


def settings(key=True):
    return Settings(
        encryption_key=SecretStr(base64.urlsafe_b64encode(b"e" * 32).decode()),
        bootstrap_key=SecretStr("synthetic-bootstrap-value-long-enough"),
        cursor_signing_key=(
            SecretStr(base64.urlsafe_b64encode(b"k" * 32).decode().rstrip("=")) if key else None
        ),
    )


@pytest.fixture
def listing(legacy):
    path, engine, source = legacy
    initialize_projection(engine)
    backfill_run_index(engine, source)
    yield path, engine, ScopedRunReader(engine, settings())


def test_literal_complete_false_success_ties_and_preservation(listing):
    path, engine, reader = listing
    before = path.read_bytes()
    page = reader.list(PRINCIPAL, PROJECT, now=NOW, limit=1)
    assert [x["id"] for x in page.items] == [RUN2]
    assert page.next_cursor
    second = reader.list(
        PRINCIPAL, PROJECT, now=NOW + timedelta(seconds=10), cursor=page.next_cursor
    )
    assert [x["id"] for x in second.items] == [RUN1]
    assert second.next_cursor is None
    for item in (*page.items, *second.items):
        assert set(item) == {
            "id",
            "project_id",
            "created_at",
            "status",
            "branchable",
            "parent_id",
            "event_head",
        }
        assert item["status"] == "complete"
        assert item["created_at"] == "2023-11-14T22:13:20.125000+00:00"
        assert reader.detail(PRINCIPAL, PROJECT, item["id"]) == item
    with engine.connect() as connection:
        outcomes = [
            json.loads(row)["success"]
            for row in connection.execute(
                text("SELECT data FROM records WHERE kind='run'")
            ).scalars()
        ]
    assert set(outcomes) == {False, True}
    preserved(path)
    assert path.read_bytes() == before
    assert runtime_schema_compatibility(engine).code == "migration_only"


def test_detail_does_not_need_cursor_key_and_authority_precedes_key(listing):
    _, engine, _ = listing
    reader = ScopedRunReader(engine, settings(False))
    assert reader.detail(PRINCIPAL, PROJECT, RUN1)["id"] == RUN1
    with pytest.raises(Fault, match="dependency_unavailable"):
        reader.list(PRINCIPAL, PROJECT, now=NOW)
    with pytest.raises(ResourceNotFound):
        reader.list(PRINCIPAL, "7" * 32, now=NOW, cursor="invalid")
    with pytest.raises(IdentityInvalid):
        reader.list("unverified", PROJECT, now=NOW)


def test_empty_page_retains_counter_and_no_token(listing):
    _, engine, reader = listing
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM run_index"))
    page = reader.list(PRINCIPAL, PROJECT, now=NOW)
    assert page.items == () and page.next_cursor is None


@pytest.mark.parametrize("field", ["event_head", "created_at", "projection_reason"])
def test_oversized_selected_projection_never_hides_as_empty(listing, field):
    _, engine, reader = listing
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA ignore_check_constraints=ON")
        connection.execute(
            text(f"UPDATE run_index SET {field}=:value WHERE run_id=:id"),
            {"value": "x" * (1024 * 1024), "id": RUN2},
        )
    with pytest.raises(Fault, match="dependency_unavailable"):
        reader.list(PRINCIPAL, PROJECT, now=NOW, limit=1)


@pytest.mark.parametrize("mutation", ["source", "projection", "job", "scope", "member", "phantom"])
def test_original_receipts_or_final_authority_refuse_change(listing, monkeypatch, mutation):
    _, engine, reader = listing
    original = reader._finish

    def changed(principal, context, entries, sources, work):
        with engine.begin() as connection:
            if mutation == "source":
                connection.execute(
                    text("UPDATE records SET created=created+1 WHERE id=:id"), {"id": RUN1}
                )
            elif mutation == "projection":
                connection.execute(
                    text("UPDATE run_index SET branchable=false WHERE run_id=:id"), {"id": RUN1}
                )
            elif mutation == "job":
                connection.execute(text("UPDATE jobs SET cancel=true"))
            elif mutation == "scope":
                connection.execute(
                    text(
                        "DELETE FROM resource_scopes WHERE resource_kind='job' AND resource_id=:id"
                    ),
                    {"id": next(iter(sources.jobs))},
                )
            elif mutation == "member":
                connection.execute(text("UPDATE project_memberships SET revoked_at='2026-01-01'"))
            else:
                connection.execute(
                    text(
                        "INSERT INTO records SELECT :new,kind,created,data "
                        "FROM records WHERE id=:old"
                    ),
                    {"new": "3" * 32, "old": RUN1},
                )
                connection.execute(
                    text("INSERT INTO resource_scopes VALUES('run',:id,:project)"),
                    {"id": "3" * 32, "project": PROJECT},
                )
        return original(principal, context, entries, sources, work)

    monkeypatch.setattr(reader, "_finish", changed)
    failure = ResourceNotFound if mutation == "member" else Fault
    with pytest.raises(failure):
        reader.list(PRINCIPAL, PROJECT, now=NOW)


def test_reads_are_bounded_selects_and_one_final_composed_receipt_statement(listing):
    _, engine, reader = listing
    sql = []

    def observe(_c, _cursor, statement, parameters, _context, _many):
        sql.append(statement)

    event.listen(engine, "before_cursor_execute", observe)
    try:
        reader.list(PRINCIPAL, PROJECT, now=NOW)
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert len(sql) < 40
    assert all(s.lstrip().upper().startswith(("SELECT", "WITH")) for s in sql)
    final = [s for s in sql if "matching_projections" in s]
    assert len(final) == 1
    assert all(
        name in final[0] for name in ("source_receipts", "projection_receipts", "unexpected_jobs")
    )
