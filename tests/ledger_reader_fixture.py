"""Complete independent SQL fixtures for the dormant ledger inspector.

Setup uses accepted predecessor services. Ar7 rows are explicit fixture seeding,
not proof of an initialize/provision implementation.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
from ledger_fixture import (
    END,
    OBSERVED,
    START,
    canonical_bytes,
    cursor_for,
    digest,
    identifier,
    opening_for,
    progress_row,
)
from legacy_fixture import assert_preserved_rows, materialize_legacy, read_manifest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from test_migrations import mapping_for
from test_ownership import FRESH

from agent_rewind.migrations import service
from agent_rewind.migrations.admission_service import initialize_admission
from agent_rewind.migrations.artifact_service import initialize_artifacts
from agent_rewind.migrations.inputs import SOURCE_QUERIES, source_digest
from agent_rewind.migrations.ledger_engine import create_ledger_engine
from agent_rewind.migrations.ledger_schema import create_ledger_constraints, create_ledger_schema
from agent_rewind.migrations.ownership_service import initialize_ownership
from agent_rewind.migrations.projection_service import backfill_run_index, initialize_projection
from agent_rewind.migrations.schema import ADMISSION, LEDGER, catalog, checksum, installed_profile
from agent_rewind.projection_evidence import FrozenLegacySource


@dataclass
class ReaderFixture:
    path: Path | None
    engine: Engine
    legacy: bool
    revision: str
    original_digest: str
    original_rows: dict[str, list[tuple[Any, ...]]]
    adoption: dict[str, Any]
    previous_progress: list[tuple[Any, ...]]
    expected: dict[str, Any]
    manifest: dict[str, Any] | None = None
    cursor: dict[str, Any] | None = None
    opening: dict[str, Any] | None = None

    def operator_engine(self) -> Engine:
        """A separate attested engine; no setup event handlers are inherited."""
        return create_ledger_engine(self.engine.url.render_as_string(hide_password=False))

    def dispose(self) -> None:
        self.engine.dispose()


def original_rows(engine: Engine) -> dict[str, list[tuple[Any, ...]]]:
    with engine.connect() as connection:
        return {
            table: [tuple(row) for row in connection.exec_driver_sql(query)]
            for table, query in SOURCE_QUERIES.items()
        }


def sqlite_snapshot(path: Path) -> tuple[str, ...]:
    """Independent logical data/schema witness outside the command engine."""
    with closing(sqlite3.connect(path)) as raw:
        raw.execute("PRAGMA query_only=ON")
        return tuple(raw.iterdump())


def _insert(connection, table: str, values: dict[str, Any]) -> None:
    # All identifiers are fixed fixture literals, never values from the database.
    connection.execute(
        text(
            f"INSERT INTO {table} ({','.join(values)}) "
            f"VALUES ({','.join(':' + key for key in values)})"
        ),
        values,
    )


def complete_ar6(path: Path, *, legacy: bool = False) -> ReaderFixture:
    if legacy:
        path = materialize_legacy(path.parent / "legacy")
    engine = create_engine(f"sqlite:///{path}")
    try:
        if legacy:
            service.adopt(engine, mapping_for(engine), "b" * 64, "d" * 64)
            initialize_ownership(engine)
        else:
            service.install(engine, FRESH["installation_key"])
            initialize_ownership(engine, FRESH)
        initialize_artifacts(engine)
        initialize_projection(engine)
        if legacy:
            source = FrozenLegacySource(
                path.parent, Fernet(read_manifest()["synthetic_fernet_key"].encode())
            )
            backfill_run_index(engine, source)
        initialize_admission(engine)
        if legacy:
            assert_preserved_rows(path)
        return capture_ar6(path, engine, legacy=legacy)
    except BaseException:
        engine.dispose()
        raise


def capture_ar6(path: Path | None, engine: Engine, *, legacy: bool) -> ReaderFixture:
    with engine.connect() as connection:
        shape = catalog(connection)
        assert shape == installed_profile(engine.dialect.name, ADMISSION)
        original = source_digest(connection)
        adoption = dict(
            connection.exec_driver_sql("SELECT * FROM installation_adoptions").mappings().one()
        )
        progress = [
            tuple(row)
            for row in connection.exec_driver_sql(
                "SELECT * FROM migration_progress ORDER BY revision,phase"
            )
        ]
    return ReaderFixture(
        path=path,
        engine=engine,
        legacy=legacy,
        revision=ADMISSION,
        original_digest=original,
        original_rows=original_rows(engine),
        adoption=adoption,
        previous_progress=progress,
        expected={
            "status": "absent",
            "installation_key": adoption["installation_key"],
            "revision": ADMISSION,
            "head": None,
            "manifest_count": 0,
            "account_count": 0,
            "opening": None,
        },
    )


def _account(number, organization, scope, scope_id, *, project=None, job=None, limit=1_000_000):
    return {
        "id": identifier(number),
        "organization_id": organization,
        "scope": scope,
        "scope_id": scope_id,
        "project_id": project,
        "job_id": job,
        "period_start": START,
        "period_end": END,
        "limit_microusd": limit,
    }


def seed_ar7(case: ReaderFixture, *, empty_accounts: bool = False) -> ReaderFixture:
    with case.engine.begin() as connection:
        jobs = [
            dict(row)
            for row in connection.exec_driver_sql(
                "SELECT j.id,j.budget,j.reserved,s.project_id FROM jobs j "
                "JOIN resource_scopes s ON s.resource_kind='job' AND s.resource_id=j.id "
                "ORDER BY j.id"
            ).mappings()
        ]
        organization = connection.exec_driver_sql("SELECT id FROM organizations").scalar_one()
        assert not (empty_accounts and jobs), "opening jobs cannot be silently omitted"
        projects = sorted({row["project_id"] for row in jobs})
        accounts = (
            [] if empty_accounts else [_account(10_000, organization, "organization", organization)]
        )
        project_accounts = {
            project: _account(20_000 + index, organization, "project", project, project=project)
            for index, project in enumerate(projects)
        }
        accounts.extend(project_accounts.values())
        accounts.extend(
            _account(
                30_000 + index,
                organization,
                "job",
                row["id"],
                project=row["project_id"],
                job=row["id"],
                limit=row["budget"],
            )
            for index, row in enumerate(jobs)
        )
        raw = {
            "schema_version": 1,
            "installation_key": case.adoption["installation_key"],
            "manifest_id": identifier(1_000_000),
            "operation": "initialize",
            "source_digest": case.original_digest,
            "parent_manifest_digest": None,
            "backup_evidence_digest": "2" * 64,
            "drain_evidence_digest": "3" * 64,
            "accounts": accounts,
            "opening_accounts": {
                "organization_account_id": None if empty_accounts else identifier(10_000),
                "projects": [
                    {"project_id": project, "account_id": project_accounts[project]["id"]}
                    for project in projects
                ],
            },
        }
        opening = opening_for(raw, amounts=[row["reserved"] for row in jobs])
        role = (
            connection.exec_driver_sql("SELECT current_user").scalar_one()
            if connection.dialect.name == "postgresql"
            else None
        )
        cursor = cursor_for(raw, opening=opening, role=role)
        exposure = {
            row["account_id"]: row["opening_held_microusd"] for row in opening["project_totals"]
        }
        exposure.update(
            (row["id"], job["reserved"])
            for row, job in zip(
                [value for value in accounts if value["scope"] == "job"], jobs, strict=True
            )
        )
        if not empty_accounts:
            exposure[identifier(10_000)] = opening["organization_opening_microusd"]
        create_ledger_schema(connection)
        connection.exec_driver_sql("UPDATE jobs SET legacy_reserved_microusd=reserved")
        for row in accounts:
            _insert(
                connection,
                "budget_accounts",
                {
                    **row,
                    "held_microusd": exposure.get(row["id"], 0),
                    "accounted_microusd": 0,
                    "opening_held_microusd": exposure.get(row["id"], 0),
                },
            )
        for value, is_opening in ((cursor, False), (opening, True)):
            _insert(
                connection,
                "migration_progress",
                progress_row(
                    value, opening=is_opening, postgres=connection.dialect.name == "postgresql"
                ),
            )
        create_ledger_constraints(connection)
        connection.execute(
            text("UPDATE alembic_version SET version_num=:revision"), {"revision": LEDGER}
        )
        shape = catalog(connection)
        assert shape == installed_profile(connection.dialect.name, LEDGER)
        connection.execute(
            text("UPDATE installation_adoptions SET installed_schema_fingerprint=:fingerprint"),
            {"fingerprint": checksum(shape)},
        )
    case.revision = LEDGER
    case.manifest, case.cursor, case.opening = raw, cursor, opening
    case.expected = {
        "status": "complete",
        "installation_key": raw["installation_key"],
        "revision": LEDGER,
        "head": {
            "installation_key": raw["installation_key"],
            "revision": LEDGER,
            "manifest_id": raw["manifest_id"],
            "manifest_digest": digest(raw),
            "sequence": 0,
            "operation": "initialize",
            "source_digest": raw["source_digest"],
            "account_rows": len(accounts),
            "imported_jobs": len(jobs),
            "imported_opening_microusd": sum(row["reserved"] for row in jobs),
            "initialized_at": OBSERVED,
        },
        "manifest_count": 1,
        "account_count": len(accounts),
        "opening": opening,
    }
    return case


def replace_progress(case: ReaderFixture, phase: str, value: dict[str, Any]) -> None:
    with case.engine.begin() as connection:
        result = connection.execute(
            text(
                "UPDATE migration_progress SET cursor=:cursor "
                "WHERE revision=:revision AND phase=:phase"
            ),
            {"cursor": canonical_bytes(value).decode(), "revision": LEDGER, "phase": phase},
        )
        assert result.rowcount == 1


def postgres_snapshot(engine: Engine) -> dict[str, Any]:
    """Small-fixture rows and catalog metadata, outside the operator engine."""
    with engine.connect() as connection:
        shape = catalog(connection)
        return {
            "catalog": shape,
            "rows": {
                table: sorted(
                    [tuple(row) for row in connection.exec_driver_sql(f'SELECT * FROM "{table}"')],
                    key=repr,
                )
                for table in sorted(shape)
                if table != "$postgres"
            },
        }


def complete_postgres_ar6(pg, *, legacy: bool) -> ReaderFixture:
    """Reuse actual PostgreSQL predecessor preparation and its drain observations."""
    from test_run_projection_postgres import drain, prepare_legacy, source

    engine = pg["owner"]
    if legacy:
        prepare_legacy(pg)
    else:
        service.install(engine, FRESH["installation_key"])
        drain(pg)
        initialize_ownership(engine, FRESH)
        drain(pg)
        initialize_artifacts(engine)
        drain(pg)
    initialize_projection(engine)
    drain(pg)
    if legacy:
        backfill_run_index(engine, source())
        drain(pg)
    initialize_admission(engine)
    drain(pg)
    case = capture_ar6(None, engine, legacy=legacy)
    drain(pg)
    return case
