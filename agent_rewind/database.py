"""Transactional metadata, fenced worker leases, and append-only event references."""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    insert,
    select,
    true,
    update,
)
from sqlalchemy.engine import Connection

from .config import Settings

metadata = MetaData()
records = Table(
    "records",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("kind", String(20), nullable=False),
    Column("created", Float, nullable=False),
    Column("data", JSON, nullable=False),
)
events = Table(
    "events",
    metadata,
    Column("run_id", String(32), primary_key=True),
    Column("step", Integer, primary_key=True),
    Column("artifact", String(64), nullable=False),
    Column("hash", String(64), nullable=False),
)
jobs = Table(
    "jobs",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("kind", String(20), nullable=False),
    Column("created", Float, nullable=False),
    Column("payload", String(64), nullable=False),
    Column("status", String(20), nullable=False),
    Column("owner", String(64)),
    Column("lease_until", Float),
    Column("cancel", Boolean, nullable=False, default=False),
    Column("budget", BigInteger, nullable=False),
    Column("reserved", BigInteger, nullable=False),
    Column("result", String(64)),
    Column("error", String(300)),
    Column("actor", String(256)),
)
keys = Table(
    "api_keys",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("hash", String(64), unique=True),
    Column("role", String(20), nullable=False),
    Column("name", String(120), nullable=False),
    Column("expires", Float, nullable=False),
    Column("revoked", Boolean, default=False),
)
audit = Table(
    "audit",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("created", Float, nullable=False),
    Column("actor", String(256), nullable=False),
    Column("action", String(80), nullable=False),
    Column("target", String(64), nullable=False),
)


def identifier() -> str:
    return uuid.uuid4().hex


class JobStopped(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


class Database:
    def __init__(self, settings: Settings):
        settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        kwargs: dict[str, Any] = {"pool_pre_ping": True}
        if settings.database_url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        self.engine = create_engine(settings.database_url, **kwargs)

    def migrate(self) -> None:
        # Initial schema. Later schema changes require an explicit migration revision.
        metadata.create_all(self.engine)

    def add(self, kind: str, data: dict[str, Any], record_id: str | None = None) -> str:
        record_id = record_id or identifier()
        with self.engine.begin() as db:
            db.execute(
                insert(records).values(id=record_id, kind=kind, created=time.time(), data=data)
            )
        return record_id

    def get(self, record_id: str, kind: str | None = None) -> dict[str, Any]:
        with self.engine.connect() as db:
            query = select(records).where(records.c.id == record_id)
            if kind:
                query = query.where(records.c.kind == kind)
            row = db.execute(query).mappings().first()
        if row is None:
            raise KeyError("Record not found.")
        return {"id": row["id"], "created": row["created"], **row["data"]}

    def list_records(self, kind: str, limit: int = 100) -> list[dict[str, Any]]:
        with self.engine.connect() as db:
            rows = db.execute(
                select(records)
                .where(records.c.kind == kind)
                .order_by(records.c.created.desc())
                .limit(limit)
            ).mappings()
            return [{"id": r["id"], "created": r["created"], **r["data"]} for r in rows]

    def _fence(
        self, db: Connection, job_id: str, owner: str, allow_cancelled: bool = False
    ) -> None:
        result = db.execute(
            update(jobs)
            .where(
                jobs.c.id == job_id,
                jobs.c.owner == owner,
                jobs.c.status == "running",
                jobs.c.lease_until > time.time(),
                true() if allow_cancelled else jobs.c.cancel.is_(False),
            )
            .values(lease_until=time.time() + 60)
        )
        if result.rowcount != 1:
            raise JobStopped("Job cancelled or worker lease lost.")

    def save_event(
        self, job_id: str, owner: str, run_id: str, step: int, artifact: str, event_hash: str
    ) -> None:
        with self.engine.begin() as db:
            self._fence(db, job_id, owner)
            db.execute(
                insert(events).values(run_id=run_id, step=step, artifact=artifact, hash=event_hash)
            )

    def event_refs(self, run_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as db:
            rows = db.execute(
                select(events).where(events.c.run_id == run_id).order_by(events.c.step)
            ).mappings()
            return [dict(row) for row in rows]

    def finish_run(self, job_id: str, owner: str, run_id: str, data: dict[str, Any]) -> None:
        with self.engine.begin() as db:
            self._fence(
                db, job_id, owner, allow_cancelled=data.get("status") in {"failed", "incomplete"}
            )
            db.execute(update(records).where(records.c.id == run_id).values(data=data))

    def enqueue(self, kind: str, payload: str, budget_usd: float, actor: str) -> str:
        job_id = identifier()
        with self.engine.begin() as db:
            db.execute(
                insert(jobs).values(
                    id=job_id,
                    kind=kind,
                    created=time.time(),
                    payload=payload,
                    status="queued",
                    cancel=False,
                    budget=round(budget_usd * 1_000_000),
                    reserved=0,
                    actor=actor,
                )
            )
            self._audit(db, actor, "job.create", job_id)
        return job_id

    def claim(self, owner: str) -> dict[str, Any] | None:
        now = time.time()
        with self.engine.begin() as db:
            # A lost job is not silently retried: model calls may already have been billed.
            db.execute(
                update(jobs)
                .where(jobs.c.status == "running", jobs.c.lease_until < now)
                .values(status="failed", error="Worker lease expired; inspect partial runs.")
            )
            row = (
                db.execute(
                    select(jobs)
                    .where(jobs.c.status == "queued", jobs.c.cancel.is_(False))
                    .order_by(jobs.c.created)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            result = db.execute(
                update(jobs)
                .where(jobs.c.id == row["id"], jobs.c.status == "queued")
                .values(status="running", owner=owner, lease_until=now + 60)
            )
            return dict(row) if result.rowcount == 1 else None

    def heartbeat(self, job_id: str, owner: str) -> None:
        with self.engine.begin() as db:
            self._fence(db, job_id, owner)

    def reserve(self, job_id: str, owner: str, amount: int) -> None:
        if amount < 0:
            raise ValueError("Budget reservations cannot be negative.")
        with self.engine.begin() as db:
            self._fence(db, job_id, owner)
            result = db.execute(
                update(jobs)
                .where(jobs.c.id == job_id, jobs.c.reserved + amount <= jobs.c.budget)
                .values(reserved=jobs.c.reserved + amount)
            )
            if result.rowcount != 1:
                raise BudgetExceeded("Insufficient remaining budget for the next model call.")

    def complete_job(self, job_id: str, owner: str, result: str | None, error: str | None) -> None:
        with self.engine.begin() as db:
            row = (
                db.execute(select(jobs).where(jobs.c.id == job_id).with_for_update())
                .mappings()
                .one()
            )
            if (
                row["owner"] != owner
                or row["status"] != "running"
                or row["lease_until"] < time.time()
            ):
                raise JobStopped("Cannot publish under an expired lease.")
            status = "cancelled" if row["cancel"] else ("failed" if error else "succeeded")
            db.execute(
                update(jobs)
                .where(jobs.c.id == job_id)
                .values(status=status, result=result, error=error)
            )

    def job(self, job_id: str) -> dict[str, Any]:
        with self.engine.connect() as db:
            row = db.execute(select(jobs).where(jobs.c.id == job_id)).mappings().first()
        if row is None:
            raise KeyError("Job not found.")
        return dict(row)

    def list_jobs(self) -> list[dict[str, Any]]:
        with self.engine.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    select(jobs).order_by(jobs.c.created.desc()).limit(100)
                ).mappings()
            ]

    def cancel(self, job_id: str, actor: str) -> None:
        with self.engine.begin() as db:
            db.execute(update(jobs).where(jobs.c.id == job_id).values(cancel=True))
            db.execute(
                update(jobs)
                .where(jobs.c.id == job_id, jobs.c.status == "queued")
                .values(status="cancelled")
            )
            self._audit(db, actor, "job.cancel", job_id)

    def _audit(self, db: Connection, actor: str, action: str, target: str) -> None:
        db.execute(
            insert(audit).values(
                id=identifier(), created=time.time(), actor=actor, action=action, target=target
            )
        )

    def audit(self, actor: str, action: str, target: str) -> None:
        with self.engine.begin() as db:
            self._audit(db, actor, action, target)

    def issue_key(self, token: str, role: str, name: str, expires: float, actor: str) -> str:
        key_id = identifier()
        with self.engine.begin() as db:
            db.execute(
                insert(keys).values(
                    id=key_id,
                    hash=hashlib.sha256(token.encode()).hexdigest(),
                    role=role,
                    name=name,
                    expires=expires,
                    revoked=False,
                )
            )
            self._audit(db, actor, "key.create", key_id)
        return key_id

    def lookup_key(self, token: str) -> dict[str, Any] | None:
        with self.engine.connect() as db:
            row = (
                db.execute(
                    select(keys).where(
                        keys.c.hash == hashlib.sha256(token.encode()).hexdigest(),
                        keys.c.expires > time.time(),
                        keys.c.revoked.is_(False),
                    )
                )
                .mappings()
                .first()
            )
            return dict(row) if row else None

    def revoke_key(self, key_id: str, actor: str) -> None:
        with self.engine.begin() as db:
            db.execute(update(keys).where(keys.c.id == key_id).values(revoked=True))
            self._audit(db, actor, "key.revoke", key_id)
