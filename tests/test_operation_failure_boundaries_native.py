"""Native selected-cell boundaries and opaque historical-marker consumer semantics.

The selected query's fixed per-cell maxima total at most 2431 raw bytes, not
4096. Canonical JSON escaping can expand those bytes; this is not a frame bound.
Exact serializer/frame controls are separate. Direct-query checks below prove
transfer guards only; complete service calls retain their own Work.
"""

import json
import time
from copy import deepcopy

import pytest
import test_migrations_postgres as migration_tests
from failure_postgres_fixture import pg
from ledger_restore_authority import typed
from operation_failure_service_oracle import (
    assert_cancel_delta,
    assert_service_released,
    expected_get,
    observe_service,
    one,
    service_case,
)
from sqlalchemy import text
from test_failure_persistence_native_oracle import assert_same_state, whole_state

from agent_rewind import operation_failure_reads
from agent_rewind.errors import Fault

__all__ = ["pg"]

# Literal contract fields, independent of the producer's dictionaries/size helper.
JOB_FIELDS = (
    "id", "kind", "created", "payload", "status", "owner", "lease_until", "cancel",
    "budget", "reserved", "result", "error", "actor", "payload_version",
    "execution_config_ref", "execution_config_digest",
)
EVIDENCE_FIELDS = (
    "schema_version", "kind", "project_id", "job_resource_kind", "job_id", "operation_id",
    "lease_generation", "job_status", "cause", "phase", "origin_kind", "correlation_id",
    "association_sha256", "source_sha256", "created_at_micros",
)
UPDATES = {
    "owner": "UPDATE jobs SET owner=:value WHERE id=:job",
    "error": "UPDATE jobs SET error=:value WHERE id=:job",
}
PG = pytest.param(
    "postgresql",
    marks=(
        pytest.mark.f4_owned_postgres,
        pytest.mark.skipif(
            not migration_tests.POSTGRES,
            reason="Opt-in synthetic PostgreSQL F4 native boundaries",
        ),
    ),
    id="postgresql",
)


@pytest.fixture(params=["sqlite", PG])
def dialect(request):
    return request.param


def _sort_rows(state):
    for table in state["tables"].values():
        table["rows"].sort(key=lambda row: repr(typed(row)))
    return state


def _read(fixture):
    return fixture.service._read_successor(
        fixture.principal, fixture.context, fixture.operation_id
    )


def _cancel(fixture):
    return fixture.service._cancel_successor(
        fixture.principal, fixture.context, fixture.operation_id
    )


def _dependency(call):
    with pytest.raises(Fault) as caught:
        call()
    assert caught.value.code == "dependency_unavailable"
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


def _selected(fixture, *, remaining, cancellation=False):
    """Execute the real bounded native query, without replacing its result."""
    with fixture.reader_engine.connect() as connection:
        query = operation_failure_reads._job_query(
            connection.dialect.name, _cancellation=cancellation
        )
        with connection.execute(
            text(query),
            {"project": fixture.context.project_id, "job": fixture.case.job_id,
             "remaining": remaining},
        ) as result:
            rows = result.mappings().all()
    assert len(rows) == 1
    row = dict(rows[0])
    assert set(row) == {
        *("j_" + field for field in JOB_FIELDS),
        *("f_" + field for field in EVIDENCE_FIELDS),
        "generation", "evidence_count", "any_provider_call", "safe",
    }
    assert type(row["safe"]) is int
    return row


def _assert_not_transferred(row, *, evidence_count):
    assert row["safe"] == 0
    assert type(row["evidence_count"]) is int
    assert row["evidence_count"] == evidence_count
    assert row["generation"] is None
    assert all(row["j_" + field] is None for field in JOB_FIELDS)
    assert all(row["f_" + field] is None for field in EVIDENCE_FIELDS)


def _native_raw_size(fixture):
    """Independent metadata-only byte total, including native numeric/boolean text."""
    with fixture.reader_engine.connect() as connection:
        postgres = connection.dialect.name == "postgresql"
        prefix = "public." if postgres else "main."

        def width(column):
            return (
                f"octet_length(CAST({column} AS text))"
                if postgres else f"length(CAST({column} AS BLOB))"
            )

        job = "+".join(f"coalesce({width('j.' + field)},0)" for field in JOB_FIELDS)
        evidence = "+".join(
            f"coalesce({width('f.' + field)},0)" for field in EVIDENCE_FIELDS
        )
        query = (
            f"SELECT {job}+coalesce({width('j.lease_generation')},0)+"
            f"(SELECT coalesce(sum({evidence}),0) FROM {prefix}job_failure_evidence f "
            "WHERE f.job_id=j.id) FROM "
            f"{prefix}jobs j WHERE j.id=:job"
        )
        value = connection.execute(text(query), {"job": fixture.case.job_id}).scalar_one()
    assert type(value) is int and 0 < value <= 2431
    return value


def _install_marker(fixture):
    """Owner-issued stored marker, without claiming execution of a migration."""
    before = whole_state(fixture.case)
    job = one(before, "jobs", id=fixture.case.job_id)
    operation = one(before, "operations", id=fixture.operation_id)
    assert job["status"] == "queued" and job["lease_generation"] == 0
    assert job["payload_version"] == 2 and operation["failure_correlation_id"] is not None
    assert before["tables"]["job_failure_evidence"]["rows"] == []
    marker = {
        "schema_version": 1, "kind": "historical_marker",
        "project_id": fixture.context.project_id, "job_resource_kind": "job",
        "job_id": fixture.case.job_id, "operation_id": fixture.operation_id,
        "lease_generation": 0, "job_status": "queued", "cause": None, "phase": None,
        "origin_kind": "migration_marker", "correlation_id": "e" * 32,
        "association_sha256": "c" * 64, "source_sha256": "d" * 64,
        "created_at_micros": 0,
    }
    with fixture.engine.begin() as connection:
        if fixture.pg is not None:
            owner = connection.exec_driver_sql(
                "SELECT current_user=session_user AND NOT EXISTS("
                "SELECT 1 FROM pg_catalog.pg_class "
                "WHERE relnamespace='public'::regnamespace AND relkind='r' "
                "AND relowner<>current_user::regrole)"
            ).scalar_one()
            assert owner is True
        changed = connection.execute(
            text("UPDATE operations SET failure_correlation_id=NULL WHERE id=:operation"),
            {"operation": fixture.operation_id},
        )
        assert changed.rowcount == 1
        connection.execute(text(
            "INSERT INTO job_failure_evidence (schema_version,kind,project_id,"
            "job_resource_kind,job_id,operation_id,lease_generation,job_status,cause,phase,"
            "origin_kind,correlation_id,association_sha256,source_sha256,created_at_micros) "
            "VALUES (:schema_version,:kind,:project_id,:job_resource_kind,:job_id,"
            ":operation_id,:lease_generation,:job_status,:cause,:phase,:origin_kind,"
            ":correlation_id,:association_sha256,:source_sha256,:created_at_micros)"
        ), marker)
    expected = deepcopy(before)
    one(expected, "operations", id=fixture.operation_id)["failure_correlation_id"] = None
    expected["tables"]["job_failure_evidence"]["rows"].append(marker)
    after = whole_state(fixture.case)
    assert_same_state(_sort_rows(expected), after)
    assert typed(after["tables"]["job_failure_evidence"]["rows"][0]) == typed(marker)
    return marker


@pytest.mark.parametrize(
    ("field", "exact", "limit"),
    [("owner", "\u2603" * 21 + "x", 64), ("error", "\u2603" * 400, 1200)],
    ids=["owner-utf8-64", "error-utf8-1200"],
)
@pytest.mark.parametrize("extra", [0, 1], ids=["exact-bytes", "one-byte-over"])
def test_utf8_cell_guard_is_native_and_reached_by_complete_cancellation(
    request, tmp_path, monkeypatch, record_property, dialect, field, exact, limit, extra
):
    with service_case(
        request, tmp_path, monkeypatch, record_property, dialect, cancel=True
    ) as fixture:
        value = exact + "x" * extra
        assert len(exact.encode("utf-8")) == limit
        assert len(value.encode("utf-8")) == limit + extra
        assert len(value) < limit  # A character-count guard would miss this refusal.
        with fixture.engine.begin() as connection:
            changed = connection.execute(
                text(UPDATES[field]), {"value": value, "job": fixture.case.job_id}
            )
            assert changed.rowcount == 1
        before = whole_state(fixture.case)
        assert one(before, "jobs", id=fixture.case.job_id)[field] == value
        row = _selected(fixture, remaining=4096, cancellation=True)
        if extra:
            _assert_not_transferred(row, evidence_count=0)
        else:
            assert row["safe"] == 1 and row["j_" + field] == value
        assert_same_state(before, whole_state(fixture.case))

        original = operation_failure_reads._read_successor_job
        visits = []

        def forwarded(*args, **kwargs):
            visits.append(kwargs["_cancellation"])
            return original(*args, **kwargs)

        monkeypatch.setattr(operation_failure_reads, "_read_successor_job", forwarded)
        first = time.time()
        with observe_service(fixture, monkeypatch, record_property) as observed:
            if extra:
                _dependency(lambda: _cancel(fixture))
            else:
                response = _cancel(fixture)
        last = time.time()
        assert_service_released(observed)
        assert visits == ([True] if extra else [True, True, True])
        if extra:
            assert not any(kind == "commit" for _, kind, _, _ in observed.controls)
            assert not any(sql.lstrip().startswith(("UPDATE jobs", "INSERT INTO audit"))
                           for sql in observed.sql)
            assert_same_state(before, whole_state(fixture.case))
        else:
            assert response == {
                "operation_id": fixture.operation_id, "cancel_requested": True,
                "status": "cancelled",
            }
            assert_cancel_delta(fixture, before, whole_state(fixture.case), (first, last))


@pytest.mark.parametrize("kind", ["absent", "verified_failure", "historical_marker"])
def test_native_remaining_transfer_budget_is_exact_and_one_short(
    request, tmp_path, monkeypatch, record_property, dialect, kind
):
    """Native raw-byte query component; no whole-service or serialized-frame claim."""
    with service_case(
        request, tmp_path, monkeypatch, record_property, dialect,
        failed=kind == "verified_failure",
    ) as fixture:
        if kind == "historical_marker":
            _install_marker(fixture)
        before = whole_state(fixture.case)
        count = 0 if kind == "absent" else 1
        assert len(before["tables"]["job_failure_evidence"]["rows"]) == count
        size = _native_raw_size(fixture)
        enough = _selected(fixture, remaining=size)
        assert enough["safe"] == 1 and enough["j_id"] == fixture.case.job_id
        assert enough["evidence_count"] == count
        if count:
            assert enough["f_kind"] == kind
        else:
            assert all(enough["f_" + field] is None for field in EVIDENCE_FIELDS)
        short = _selected(fixture, remaining=size - 1)
        _assert_not_transferred(short, evidence_count=count)
        assert_same_state(before, whole_state(fixture.case))
        record_property("f4_native_transfer_component", json.dumps({
            "kind": kind, "raw_bytes": size, "exact_safe": enough["safe"],
            "one_short_safe": short["safe"], "raw_cell_upper_bound": 2431,
            "whole_service_claim": False, "serialized_frame_bound_claim": False,
        }, sort_keys=True))


def test_opaque_marker_get_keeps_stored_w_across_allowed_current_state_drift(
    request, tmp_path, monkeypatch, record_property, dialect
):
    with service_case(request, tmp_path, monkeypatch, record_property, dialect) as fixture:
        marker = _install_marker(fixture)
        before = whole_state(fixture.case)
        original = operation_failure_reads._marker
        visits = []

        def forwarded(*args, **kwargs):
            visits.append(True)
            return original(*args, **kwargs)

        def must_not_recompute(*_args, **_kwargs):
            pytest.fail("A historical marker cannot be reinterpreted as verified provenance")

        monkeypatch.setattr(operation_failure_reads, "_marker", forwarded)
        monkeypatch.setattr(operation_failure_reads, "association_digest", must_not_recompute)
        monkeypatch.setattr(operation_failure_reads, "source_digest", must_not_recompute)
        with observe_service(fixture, monkeypatch, record_property) as initial:
            response = _read(fixture)
        assert response == expected_get(fixture, before) and response["error"] is None
        assert_service_released(initial)
        assert not initial.frames
        assert_same_state(before, whole_state(fixture.case))

        with fixture.engine.begin() as connection:
            changed = connection.execute(text(
                "UPDATE jobs SET cancel=:cancel,owner=:owner,lease_until=:lease WHERE id=:job"
            ), {"cancel": True, "owner": "later-worker", "lease": 1900000000.0,
                "job": fixture.case.job_id})
            assert changed.rowcount == 1
        expected = deepcopy(before)
        one(expected, "jobs", id=fixture.case.job_id).update(
            cancel=True if fixture.pg is not None else 1,
            owner="later-worker", lease_until=1900000000.0,
        )
        current = whole_state(fixture.case)
        assert_same_state(_sort_rows(expected), current)
        with observe_service(fixture, monkeypatch, record_property) as fresh:
            response = _read(fixture)
        assert response == expected_get(fixture, current) and response["error"] is None
        assert response["cancel_requested"] is True
        assert_service_released(fresh)
        assert not fresh.frames and visits == [True, True]
        after = whole_state(fixture.case)
        assert_same_state(current, after)
        assert typed(after["tables"]["job_failure_evidence"]["rows"][0]) == typed(marker)


@pytest.mark.parametrize("change", ["generation", "status"])
def test_marker_current_generation_and_status_are_required_despite_opaque_w(
    request, tmp_path, monkeypatch, record_property, dialect, change
):
    with service_case(request, tmp_path, monkeypatch, record_property, dialect) as fixture:
        marker = _install_marker(fixture)
        before = whole_state(fixture.case)
        sql = {
            "generation": "UPDATE jobs SET lease_generation=lease_generation+1 WHERE id=:job",
            "status": "UPDATE jobs SET status='running' WHERE id=:job",
        }[change]
        with fixture.engine.begin() as connection:
            changed = connection.execute(text(sql), {"job": fixture.case.job_id})
            assert changed.rowcount == 1
        expected = deepcopy(before)
        job = one(expected, "jobs", id=fixture.case.job_id)
        job["lease_generation" if change == "generation" else "status"] = (
            1 if change == "generation" else "running"
        )
        current = whole_state(fixture.case)
        assert_same_state(_sort_rows(expected), current)
        row = _selected(fixture, remaining=4096)
        assert row["safe"] == 1 and row["evidence_count"] == 1
        assert row["f_kind"] == "historical_marker"
        original = operation_failure_reads._marker
        visits = []

        def forwarded(*args, **kwargs):
            visits.append(True)
            return original(*args, **kwargs)

        monkeypatch.setattr(operation_failure_reads, "_marker", forwarded)
        with observe_service(fixture, monkeypatch, record_property) as observed:
            _dependency(lambda: _read(fixture))
        assert visits == [True]
        assert_service_released(observed)
        assert not observed.frames
        assert not any(kind == "commit" for _, kind, _, _ in observed.controls)
        after = whole_state(fixture.case)
        assert_same_state(current, after)
        assert typed(after["tables"]["job_failure_evidence"]["rows"][0]) == typed(marker)
