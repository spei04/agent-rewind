"""Complete independent SQL fixtures for the dormant ledger inspector.

Setup uses accepted predecessor services. Ar7 rows are explicit fixture seeding,
not proof of an initialize/provision implementation.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
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


def append_provision(case: ReaderFixture, accounts: list[dict[str, Any]]) -> None:
    """Seed a later immutable receipt, without pretending a provisioner exists."""
    assert case.manifest is not None and case.opening is not None
    raw = deepcopy(case.manifest)
    sequence = case.expected["manifest_count"]
    raw.update(
        manifest_id=identifier(1_000_000 + sequence),
        operation="provision",
        parent_manifest_digest=digest(case.manifest),
        accounts=sorted(accounts, key=lambda row: row["id"]),
        opening_accounts=None,
    )
    with case.engine.begin() as connection:
        raw["source_digest"] = source_digest(connection)
        role = (
            connection.exec_driver_sql("SELECT current_user").scalar_one()
            if connection.dialect.name == "postgresql"
            else None
        )
        cursor = cursor_for(raw, sequence=sequence, role=role)
        for row in raw["accounts"]:
            _insert(
                connection,
                "budget_accounts",
                {
                    **row,
                    "held_microusd": 0,
                    "accounted_microusd": 0,
                    "opening_held_microusd": 0,
                },
            )
        _insert(
            connection,
            "migration_progress",
            progress_row(cursor, postgres=connection.dialect.name == "postgresql"),
        )
    case.manifest, case.cursor = raw, cursor
    case.expected = {
        **case.expected,
        "head": {
            "installation_key": raw["installation_key"],
            "revision": LEDGER,
            "manifest_id": raw["manifest_id"],
            "manifest_digest": digest(raw),
            "sequence": sequence,
            "operation": "provision",
            "source_digest": raw["source_digest"],
            "account_rows": len(accounts),
            "imported_jobs": 0,
            "imported_opening_microusd": 0,
            "initialized_at": OBSERVED,
        },
        "manifest_count": sequence + 1,
        "account_count": case.expected["account_count"] + len(accounts),
    }


def later_admitted_call(
    case: ReaderFixture, *, effect: str = "reserved", future_zero_period: bool = False
) -> dict[str, Any]:
    """A complete synthetic post-opening admission and financial closure.

    Artifact helpers establish SQL metadata associations only. No provider,
    upload, authenticated invoice or production reservation method is invoked.
    """
    from test_admission_envelope import descriptor
    from test_admission_repository import config_refs, prepared
    from test_admission_schema import PRINCIPAL, operation

    from agent_rewind.artifact_metadata import record_verified, register_ref

    assert case.revision == LEDGER and not case.legacy
    assert case.expected["account_count"] == 1
    assert effect in {"reserved", "settled", "released"}
    project, organization = FRESH["project_id"], FRESH["organization_id"]
    job, call, operation_id = identifier(2_000_000), identifier(3_000_000), identifier(4_000_000)
    value, payload = prepared(job=job, ids=tuple(identifier(5_000_000 + i) for i in range(3)))
    assert value.intent.budget_microusd == 1
    with case.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO jobs(id,kind,created,payload,status,cancel,budget,reserved,actor) "
                "VALUES(:id,'run',1700000000.125,:payload,'queued',false,1,0,:actor)"
            ),
            {"id": job, "payload": value.envelope_digest, "actor": PRINCIPAL},
        )
        _insert(
            connection,
            "resource_scopes",
            {"resource_kind": "job", "resource_id": job, "project_id": project},
        )
        config_refs(connection, value, payload)
        operation(
            connection,
            id=operation_id,
            job_id=job,
            client_operation_id=value.intent.client_operation_id,
            request_digest=value.intent.request_digest,
            execution_config_digest=value.configuration.digest,
            accepted_response=canonical_bytes(
                {"job_id": job, "operation_id": operation_id}
            ).decode(),
        )
    rows = [
        _account(20_000, organization, "project", project, project=project),
        _account(30_000, organization, "job", job, project=project, job=job, limit=1),
    ]
    append_provision(case, rows)
    triple = [identifier(10_000), identifier(20_000), identifier(30_000)]
    future_ids = []
    if future_zero_period:
        # Provision while carried exposure is zero, before the later January
        # reservation. A future admission may refuse; persisted state is valid.
        future_rows = [
            _account(40_000, organization, "organization", organization, limit=0),
            _account(50_000, organization, "project", project, project=project, limit=0),
        ]
        for row in future_rows:
            row.update(period_start=END, period_end="2026-03-01T00:00:00.000000Z")
        with case.engine.connect() as connection:
            assert (
                connection.exec_driver_sql(
                    "SELECT sum(held_microusd) FROM budget_accounts"
                ).scalar_one()
                == 0
            )
        append_provision(case, future_rows)
        future_ids = [row["id"] for row in future_rows]
    with case.engine.begin() as connection:
        _insert(
            connection,
            "provider_calls",
            {
                "id": call,
                "project_id": project,
                "job_id": job,
                "logical_call_id": identifier(6_000_000),
                "purpose": "continuation",
                "request_digest": "a" * 64,
                "price_version": json.loads(value.configuration.canonical_bytes)["price_version"],
                "state": "reserved" if effect == "reserved" else "reconciled",
                "reserved_microusd": 1,
                "created_at": OBSERVED,
                "organization_id": organization,
                "job_resource_kind": "job",
                "lease_generation": 1,
                "organization_account_id": triple[0],
                "project_account_id": triple[1],
                "job_account_id": triple[2],
            },
        )
        _insert(
            connection,
            "resource_scopes",
            {"resource_kind": "provider_call", "resource_id": call, "project_id": project},
        )
        for account_id in triple:
            _insert(
                connection,
                "budget_entries",
                {
                    "call_id": call,
                    "account_id": account_id,
                    "entry_kind": "reserve",
                    "amount_microusd": 1,
                    "created_at": OBSERVED,
                    "project_id": project,
                },
            )
        evidence_id = None
        if effect != "reserved":
            evidence = descriptor(
                b"synthetic-accounting-observation",
                object_id=identifier(7_000_000),
                project=project,
            )
            record_verified(connection, evidence)
            register_ref(
                connection,
                project_id=project,
                owner_kind="provider_call",
                owner_id=call,
                role="budget_evidence",
                artifact_id=evidence.id,
            )
            evidence_id = evidence.id
            for account_id in triple:
                _insert(
                    connection,
                    "budget_entries",
                    {
                        "call_id": call,
                        "account_id": account_id,
                        "entry_kind": "settle" if effect == "settled" else "release",
                        "amount_microusd": 1,
                        "created_at": OBSERVED,
                        "project_id": project,
                        "evidence_ref": evidence.id,
                        "evidence_owner_kind": "provider_call",
                        "evidence_role": "budget_evidence",
                    },
                )
        connection.execute(
            text(
                "UPDATE budget_accounts SET held_microusd=:held,accounted_microusd=:accounted "
                "WHERE id IN (:organization,:project,:job)"
            ),
            {
                "held": 1 if effect == "reserved" else 0,
                "accounted": 1 if effect == "settled" else 0,
                "organization": triple[0],
                "project": triple[1],
                "job": triple[2],
            },
        )
        connection.execute(
            text(
                "UPDATE jobs SET status='running',owner='synthetic-worker',lease_until=1900000000,"
                "lease_generation=2,reserved=1 WHERE id=:job"
            ),
            {"job": job},
        )
    return {
        "job_id": job,
        "call_id": call,
        "operation_id": operation_id,
        "accounts": triple,
        "evidence_id": evidence_id,
        "configuration": value.configuration,
        "future_accounts": future_ids,
    }


class RowTransferWatch:
    """Observe actual client-buffered DBAPI cells at the pinned fetch boundary.

    This observes row transfer, not server disk reads. It neither accepts SQL
    prefixes as a read-only proof nor changes the operator engine's listeners.
    """

    def __init__(
        self,
        monkeypatch,
        targets: dict[str, str | bytes],
        *,
        replacements: dict[str, str | bytes] | None = None,
        statements: dict[str, str] | None = None,
    ):
        from sqlalchemy.engine.cursor import CursorFetchStrategy

        self.hits: list[dict[str, Any]] = []
        self.targets = targets
        self.statement_hits: list[dict[str, Any]] = []
        statements = statements or {}
        replacements = replacements or {}
        assert set(replacements) <= set(targets)
        for method in ("fetchone", "fetchmany", "fetchall"):
            original = getattr(CursorFetchStrategy, method)

            def observed(
                strategy, result, cursor, *args, _original=original, _method=method, **kwargs
            ):
                value = _original(strategy, result, cursor, *args, **kwargs)
                rows = [value] if _method == "fetchone" else value
                if statements:
                    statement = result.context.statement.strip()
                    if statement in statements:
                        self.statement_hits.append(
                            {
                                "name": statements[statement],
                                "method": _method,
                                "rows": sum(row is not None for row in rows or []),
                            }
                        )
                changed, substituted = False, []
                for row in rows or []:
                    if row is None:
                        continue
                    cells = list(row)
                    for position, cell in enumerate(row):
                        for label, target in self.targets.items():
                            if type(cell) is type(target) and cell == target:
                                wire = cell.encode("utf-8") if isinstance(cell, str) else cell
                                self.hits.append(
                                    {
                                        "label": label,
                                        "method": _method,
                                        "bytes": len(wire),
                                        "sha256": hashlib.sha256(wire).hexdigest(),
                                    }
                                )
                                if label in replacements:
                                    assert type(replacements[label]) is type(cell)
                                    cells[position] = replacements[label]
                                    changed = True
                    substituted.append(tuple(cells))
                if changed:
                    return substituted[0] if _method == "fetchone" else substituted
                return value

            monkeypatch.setattr(CursorFetchStrategy, method, observed)


# Frozen financial projection contract, intentionally independent of consumer _FIELDS.
_FINANCIAL_FIELDS = {
    "account": [
        "id",
        "organization_id",
        "scope",
        "scope_id",
        "period_start",
        "period_end",
        "limit_microusd",
        "held_microusd",
        "accounted_microusd",
        "project_id",
        "job_id",
        "opening_held_microusd",
    ],
    "call": [
        "id",
        "project_id",
        "job_id",
        "logical_call_id",
        "purpose",
        "request_digest",
        "price_version",
        "state",
        "reserved_microusd",
        "usage_estimate_microusd",
        "provider_request_id",
        "created_at",
        "organization_id",
        "job_resource_kind",
        "lease_generation",
        "organization_account_id",
        "project_account_id",
        "job_account_id",
    ],
    "entry": [
        "call_id",
        "account_id",
        "entry_kind",
        "amount_microusd",
        "evidence_ref",
        "created_at",
        "project_id",
        "evidence_owner_kind",
        "evidence_role",
    ],
    "job": [
        "id",
        "kind",
        "created",
        "payload",
        "status",
        "owner",
        "lease_until",
        "cancel",
        "budget",
        "reserved",
        "result",
        "error",
        "actor",
        "payload_version",
        "execution_config_ref",
        "execution_config_digest",
        "lease_generation",
        "legacy_reserved_microusd",
    ],
    "operation": [
        "id",
        "project_id",
        "principal_id",
        "kind",
        "client_operation_id",
        "request_digest",
        "job_id",
        "accepted_response",
        "created_at",
        "retain_until",
        "job_resource_kind",
        "execution_config_digest",
        "payload_version",
        "failure_correlation_id",
    ],
    "scope": ["resource_kind", "resource_id", "project_id"],
    "ref": ["project_id", "owner_kind", "owner_id", "artifact_id", "role"],
    "object": [
        "id",
        "project_id",
        "digest",
        "locator",
        "format_version",
        "byte_count",
        "created_at",
    ],
    "project": ["id", "organization_id"],
    "organization": ["id", "installation_key"],
}
_FINANCIAL_TIMES = {
    "account": ("period_start", "period_end"),
    "call": ("created_at",),
    "entry": ("created_at",),
    "object": ("created_at",),
    "operation": ("created_at", "retain_until"),
}
_FINANCIAL_BASE = {"account", "call", "entry", "job", "operation", "scope", "organization"}
FINANCIAL_BOUNDARIES = (
    "native-cap",
    "native-one-over",
    "canonical-expansion",
    "canonical-cap",
    "canonical-one-over",
)


def financial_statements(dialect_name: str) -> dict[str, str]:
    from agent_rewind.migrations.ledger_financial_sql import SQL

    return {
        query.strip(): name
        for (revision, dialect, name), query in SQL.items()
        if revision == "ar7" and dialect == dialect_name
    }


def _financial_projection_receipt(connection) -> dict[str, Any]:
    from agent_rewind.migrations.ledger_financial_sql import SQL

    receipts, frames = {}, []
    dialect = connection.dialect.name
    for domain, fields in _FINANCIAL_FIELDS.items():
        prefix = "financial_base_" if domain in _FINANCIAL_BASE else "financial_"
        name = prefix + domain
        receipts[domain] = dict(
            connection.execute(text(SQL[("ar7", dialect, name + "_gate")])).mappings().one()
        )
        rows = connection.execute(text(SQL[("ar7", dialect, name + "_body")])).mappings().all()
        assert len(rows) == receipts[domain]["candidate_rows"]
        for raw in rows:
            row = dict(raw)
            assert set(row) == {*fields, "invalid"} and row.pop("invalid") == 0
            for field in _FINANCIAL_TIMES.get(domain, ()):
                value = row[field]
                instant = datetime.fromisoformat(value) if isinstance(value, str) else value
                assert isinstance(instant, datetime) and instant.utcoffset() is not None
                row[field] = (
                    instant.astimezone(UTC)
                    .isoformat(timespec="microseconds")
                    .replace("+00:00", "Z")
                )
                assert len(row[field]) == 27
            frames.append([domain, [row[field] for field in fields]])
    encoded = json.dumps(frames, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    # Full flat-array serialization independently agrees with the row-frame contract.
    row_sizes = [
        len(json.dumps(frame, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
        for frame in frames
    ]
    assert len(encoded) == 2 + sum(row_sizes) + max(0, len(frames) - 1)
    return {
        "domains": receipts,
        "native_bytes": sum(row["native_bytes"] for row in receipts.values()),
        "canonical_bytes": len(encoded),
        "canonical_sha256": hashlib.sha256(encoded).hexdigest(),
        "rows": len(frames),
    }


def calibrate_financial_boundary(case: ReaderFixture, mode: str) -> tuple[str, dict[str, Any]]:
    """Build actual bounded state; no product counter, cap or result is replaced."""
    assert mode in FINANCIAL_BOUNDARIES and case.legacy and case.revision == LEDGER
    cap = 2 * 1024 * 1024
    with case.engine.begin() as connection:
        job, version = connection.exec_driver_sql(
            "SELECT id,payload_version FROM jobs ORDER BY id LIMIT 1"
        ).one()
        assert version == 1

        def replace(payload):
            connection.execute(
                text("UPDATE jobs SET payload=:payload WHERE id=:job"),
                {"payload": payload, "job": job},
            )

        replace("")
        baseline = _financial_projection_receipt(connection)
        if mode.startswith("native"):
            payload = "z" * (cap + (mode == "native-one-over") - baseline["native_bytes"])
        elif mode == "canonical-expansion":
            payload = '"' * (cap // 2 + 1)
        else:
            target = cap + (mode == "canonical-one-over")
            quotes, tail = divmod(target - baseline["canonical_bytes"], 2)
            assert quotes > 0
            payload = '"' * quotes + "z" * tail
        replace(payload)
        receipt = _financial_projection_receipt(connection)
    assert len(receipt["domains"]) == 10 and 0 < receipt["rows"] < 65536
    assert all(
        row["invalid_rows"] == 0 and row["native_bytes"] < cap
        for row in receipt["domains"].values()
    )
    if mode.startswith("native"):
        assert receipt["native_bytes"] == cap + (mode == "native-one-over")
        assert receipt["canonical_bytes"] > cap
    else:
        assert receipt["native_bytes"] < cap
        if mode == "canonical-expansion":
            assert receipt["canonical_bytes"] > cap
        else:
            assert receipt["canonical_bytes"] == cap + (mode == "canonical-one-over")
    return payload, receipt


def assert_financial_transfer_boundary(watch: RowTransferWatch, mode: str) -> None:
    bodies = [value for value in watch.statement_hits if value["name"].endswith("_body")]
    if mode == "native-one-over":
        assert not bodies and not watch.hits
    else:
        assert bodies and watch.hits
        first_body = next(
            index
            for index, value in enumerate(watch.statement_hits)
            if value["name"].endswith("_body")
        )
        gates = {
            value["name"]
            for value in watch.statement_hits[:first_body]
            if value["name"].endswith("_gate") and value["name"] != "financial_owner_gate"
        }
        assert len(gates) == 10
