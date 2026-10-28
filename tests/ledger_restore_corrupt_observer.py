"""Attribute a corrupt-state refusal to the unchanged actual service call."""

import hashlib
from contextlib import contextmanager

from ledger_restore_interruption_raw import encoded

from agent_rewind.migrations import (
    ledger_catalog,
    ledger_inspection,
    ledger_reader_history,
    ledger_service,
)
from agent_rewind.migrations.schema import MigrationRefused

MAX_STAGES = 64


def progress_binding(row):
    assert set(row) == {
        "revision",
        "phase",
        "source_digest",
        "cursor",
        "rows_verified",
        "status",
        "updated_at",
    }
    assert type(row["cursor"]) is str
    cursor = row["cursor"].encode()
    return {
        "phase": row["phase"],
        "row_sha256": hashlib.sha256(encoded(dict(row))).hexdigest(),
        "cursor_sha256": hashlib.sha256(cursor).hexdigest(),
        "cursor_bytes": len(cursor),
    }


class CorruptionStages:
    def __init__(self, watch, phase):
        self.watch, self.phase = watch, phase
        self.events, self.refusals = [], []

    def record(self, stage, action, connection=None, **extra):
        assert len(self.events) < MAX_STAGES, "corruption stage bound"
        raw = None if connection is None else connection.connection.driver_connection
        if raw is not None:
            assert connection.engine is self.watch.engine and self.watch.owns(raw)
        self.events.append(
            {
                "stage": stage,
                "action": action,
                "raw_id": None if raw is None else id(raw),
                "trace_index": len(self.watch.trace.events),
                **extra,
            }
        )

    def wrap(self, delegate, stage):
        def observed(connection, *args, **kwargs):
            extra = progress_binding(args[0]) if stage == "progress" else {}
            self.record(stage, "enter", connection, **extra)
            try:
                result = delegate(connection, *args, **kwargs)
            except BaseException as error:
                self.refusals.append((stage, error, extra.get("phase")))
                self.record(
                    stage,
                    "raise",
                    connection,
                    error_type=type(error).__name__,
                    code=error.code if isinstance(error, MigrationRefused) else None,
                    **extra,
                )
                raise
            self.record(stage, "return", connection, **extra)
            return result

        return observed

    def invoke(self, manifest):
        self.record("service", "enter")
        try:
            result = ledger_service._inspect_ledger_reentry(self.watch.engine, manifest)
        except BaseException as error:
            self.refusals.append(("service", error, None))
            self.record(
                "service",
                "raise",
                error_type=type(error).__name__,
                code=error.code if isinstance(error, MigrationRefused) else None,
            )
            raise
        self.record("service", "return")
        return result

    def verify(self, kind, error, *, expected_progress=None):
        code = {"cursor": "ledger_progress_invalid", "acl": "schema_incompatible"}[kind]
        assert type(error) is MigrationRefused and error.code == code
        expected = (
            ["progress", "history", "inspection", "service"]
            if kind == "cursor"
            else ["executables", "catalog", "inspection", "service"]
        )
        assert [stage for stage, _, _ in self.refusals] == expected
        assert all(actual is error for _, actual, _ in self.refusals)
        if kind == "cursor":
            assert self.refusals[0][2] == self.phase
            expected = progress_binding(expected_progress)
            assert expected["phase"] == self.phase
            consumed = [
                row
                for row in self.events
                if row["stage"] == "progress" and row.get("phase") == self.phase
            ]
            assert [row["action"] for row in consumed] == ["enter", "raise"]
            assert all({key: row[key] for key in expected} == expected for row in consumed), (
                "historical refusal did not consume the independently observed M1 row"
            )
        entered = [row["stage"] for row in self.events if row["action"] == "enter"]
        if kind == "acl":
            assert entered == ["service", "inspection", "catalog", "executables"]
        else:
            assert entered[:5] == ["service", "inspection", "catalog", "executables", "history"]
            assert entered[5:] and set(entered[5:]) == {"progress"}
            assert any(
                row["stage"] == "catalog" and row["action"] == "return" for row in self.events
            )
        assert self.events[0]["stage"] == "service" and self.events[-1]["stage"] == "service"
        raw_id = id(self.watch.work._raw)
        assert all(row["raw_id"] == raw_id for row in self.events if row["stage"] != "service")
        boundary = self.watch.command_boundary["trace_end"]
        assert all(row["trace_index"] <= boundary for row in self.events)
        assert any(row["trace_index"] > 0 for row in self.events if row["stage"] != "service")
        assert all(
            a["trace_index"] <= b["trace_index"]
            for a, b in zip(self.events, self.events[1:], strict=False)
        )
        return {"kind": kind, "code": code, "same_exception": True, "events": self.events}


@contextmanager
def observe_corruption(patch, watch, phase):
    stages = CorruptionStages(watch, phase)
    for module, name, stage in (
        (ledger_service, "_inspect_ledger_context", "inspection"),
        (ledger_inspection, "inspect_catalog", "catalog"),
        (ledger_catalog, "ledger_executables", "executables"),
        (ledger_inspection, "read_history", "history"),
        (ledger_reader_history, "validate_progress_row", "progress"),
    ):
        patch.setattr(module, name, stages.wrap(getattr(module, name), stage))

    def forbidden(*args, **kwargs):
        raise AssertionError("corrupt restore inspection entered writer/source-refresh work")

    for name in (
        "initialize_ledger",
        "_upgrade",
        "_prepare_ledger",
        "_provenance",
        "_write",
        "source_digest",
    ):
        patch.setattr(ledger_service, name, forbidden)
    yield stages


def assert_refusal_cleanup(watch):
    watch.assert_single_attempt()
    watch.assert_no_writes()
    outcome = watch.outcome
    assert not outcome.commit_attempted and not outcome.commit_acknowledged
    assert outcome.rollback_attempted and outcome.rollback_acknowledged
    assert not outcome.cleanup_failed
    assert any(
        row["action"] == "rollback" and row["status_after"] == 0 and not row["closed_after"]
        for row in watch.physical
    ), "native service rollback acknowledgment missing"
