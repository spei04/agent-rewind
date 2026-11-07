"""Late valid evidence at each successor guard, using SQLite same-body faults.

These are controlled interference cases, not competing-writer proofs. PostgreSQL
marker creation requires owner authority and is not injected into its restricted
application connection. No catalog/profile acceptance is replaced.
"""

import json
from copy import deepcopy

import pytest
from operation_failure_paid_oracle import observe_paid
from operation_failure_service_oracle import one
from sqlalchemy import text
from sqlalchemy.engine import Connection
from test_failure_persistence_native_oracle import assert_same_state, whole_state
from test_operation_failure_paid_atomicity import _call, _claim, _rollback
from test_operation_failure_paid_oracle import case

from agent_rewind import reservation_successor
from agent_rewind.failure_evidence import FailureRefusal
from agent_rewind.reservation_service import ReservationCoordinator
from agent_rewind.reservation_types import ReservationRefusal

__all__ = ["case"]


def _prepare_marker_operation(case):
    """Only the owner prepares marker-compatible operation provenance."""
    assert case.engine.dialect.name == "sqlite" and not hasattr(case, "pg")
    operation_id = case.admission.accepted["operation_id"]
    before = whole_state(case)
    assert one(before, "operations", id=operation_id)["failure_correlation_id"] is not None
    with case.case.engine.begin() as connection:
        assert (
            connection.execute(
                text("UPDATE operations SET failure_correlation_id=NULL WHERE id=:operation"),
                {"operation": operation_id},
            ).rowcount
            == 1
        )
    expected = deepcopy(before)
    one(expected, "operations", id=operation_id)["failure_correlation_id"] = None
    assert_same_state(expected, whole_state(case))
    return operation_id


def _insert_current_marker(connection, case, operation_id, coordinator, execute):
    assert connection is coordinator._work._connection
    assert connection.info["operation_work"] is coordinator._work
    assert connection.engine is case.engine and connection.in_transaction()
    assert (
        execute(
            connection,
            text("SELECT failure_correlation_id FROM operations WHERE id=:operation"),
            {"operation": operation_id},
        ).scalar_one()
        is None
    )
    assert (
        execute(
            connection,
            text("SELECT count(*) FROM job_failure_evidence WHERE job_id=:job"),
            {"job": case.job_id},
        ).scalar_one()
        == 0
    )
    job = (
        execute(
            connection,
            text("SELECT status,lease_generation,payload_version FROM jobs WHERE id=:job"),
            {"job": case.job_id},
        )
        .mappings()
        .one()
    )
    assert job["payload_version"] == 2
    assert job["status"] in {"queued", "running"}
    assert type(job["lease_generation"]) is int and job["lease_generation"] in (0, 1)
    marker = {
        "schema_version": 1,
        "kind": "historical_marker",
        "project_id": case.project_id,
        "job_resource_kind": "job",
        "job_id": case.job_id,
        "operation_id": operation_id,
        "lease_generation": job["lease_generation"],
        "job_status": job["status"],
        "cause": None,
        "phase": None,
        "origin_kind": "migration_marker",
        "correlation_id": "e" * 32,
        "association_sha256": "c" * 64,
        "source_sha256": "d" * 64,
        "created_at_micros": 0,
    }
    columns = ",".join(marker)
    placeholders = ",".join(":" + name for name in marker)
    assert (
        execute(
            connection,
            text(f"INSERT INTO job_failure_evidence ({columns}) VALUES ({placeholders})"),
            marker,
        ).rowcount
        == 1
    )
    assert (
        execute(
            connection,
            text("SELECT count(*) FROM job_failure_evidence WHERE job_id=:job"),
            {"job": case.job_id},
        ).scalar_one()
        == 1
    )
    return {"status": job["status"], "generation": job["lease_generation"]}


def _other_predicates(connection, case, boundary, parameters, execute):
    """Witness genuine zero rows are due to the evidence predicate."""
    job = (
        execute(
            connection,
            text(
                "SELECT status,owner,lease_until,cancel,lease_generation,reserved "
                "FROM jobs WHERE id=:job"
            ),
            {"job": case.job_id},
        )
        .mappings()
        .one()
    )
    if boundary == "claim-update":
        assert job["status"] == "queued" and job["owner"] is None
        assert job["lease_until"] is None and job["cancel"] in (False, 0)
        assert job["lease_generation"] == parameters["expected"]
    elif boundary == "gross-update":
        assert job["status"] == "running" and job["cancel"] in (False, 0)
        assert job["owner"] == parameters["owner"]
        assert job["lease_generation"] == parameters["generation"]
        assert job["reserved"] == parameters["old"]
    else:
        assert boundary == "call-insert"
        assert job["status"] == "running"
        assert (
            execute(
                connection,
                text("SELECT count(*) FROM provider_calls WHERE id=:call"),
                {"call": parameters["id"]},
            ).scalar_one()
            == 0
        )


@pytest.mark.parametrize("case", ["sqlite"], indirect=True)
@pytest.mark.parametrize(
    "boundary",
    [
        "claim-update",
        "call-insert",
        "gross-update",
        "claim-final",
        "reserve-final",
    ],
)
def test_successor_late_evidence_uses_each_actual_paid_guard_and_rolls_back(
    case, monkeypatch, record_property, boundary
):
    entry = "claim" if boundary.startswith("claim-") else "reserve"
    fence = None if entry == "claim" else _claim(case, monkeypatch, record_property)
    operation_id = _prepare_marker_operation(case)
    before = whole_state(case)
    coordinator = ReservationCoordinator(case.engine, case.authority)
    original_execute, original_final = Connection.execute, reservation_successor.final_fence
    inserted, rowcounts, final_refusals, returned = [], [], [], []

    def execute(connection, statement, *args, **kwargs):
        sql = " ".join(str(statement).split()).lower()
        selected = {
            "claim-update": sql.startswith("update jobs set status="),
            "call-insert": sql.startswith("insert into provider_calls"),
            "gross-update": sql.startswith("update jobs set reserved="),
        }.get(boundary, False)
        if connection.engine is case.engine and selected:
            assert not inserted and "not exists" in sql and "job_failure_evidence" in sql
            assert args and isinstance(args[0], dict)
            parameters = args[0]
            _other_predicates(connection, case, boundary, parameters, original_execute)
            inserted.append(
                _insert_current_marker(
                    connection, case, operation_id, coordinator, original_execute
                )
            )
            # No replacement result or rowcount: forward the exact original SQL.
            result = original_execute(connection, statement, *args, **kwargs)
            rowcounts.append(result.rowcount)
            return result
        return original_execute(connection, statement, *args, **kwargs)

    def final(connection, scope, actual_fence, identity):
        assert boundary in {"claim-final", "reserve-final"} and not inserted
        assert scope.job_id == case.job_id
        assert (identity is None) is (boundary == "claim-final")
        inserted.append(
            _insert_current_marker(connection, case, operation_id, coordinator, original_execute)
        )
        try:
            return original_final(connection, scope, actual_fence, identity)
        except FailureRefusal as error:
            final_refusals.append(error)
            raise

    expected = FailureRefusal if boundary.endswith("-final") else ReservationRefusal
    with monkeypatch.context() as patch:
        patch.setattr(Connection, "execute", execute)
        if boundary.endswith("-final"):
            patch.setattr(reservation_successor, "final_fence", final)
        with (
            observe_paid(case, patch, record_property, coordinator),
            pytest.raises(expected) as caught,
        ):
            returned.append(_call(coordinator, case, entry, fence))
    assert len(inserted) == 1 and returned == []
    if boundary.endswith("-final"):
        assert rowcounts == [] and final_refusals == [caught.value]
        assert caught.value.reason == "not_eligible"
    else:
        assert rowcounts == [0] and final_refusals == []
        assert caught.value.reason == "job_not_live"
    _rollback(coordinator)
    assert_same_state(before, whole_state(case))
    record_property(
        "f4_paid_late_evidence_guard",
        json.dumps(
            {
                "boundary": boundary,
                "native_marker": inserted[0],
                "actual_rowcounts": rowcounts,
                "final_refusals": len(final_refusals),
                "same_owned_connection": True,
                "returned_receipts": len(returned),
                "qualification": "SQLite same-body interference; no PG or competing-writer credit.",
            },
            sort_keys=True,
        ),
    )
