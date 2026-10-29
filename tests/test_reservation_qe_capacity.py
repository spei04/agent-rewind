"""One native financial-capacity integration oracle; existing reader matrices remain separate."""

import json
from dataclasses import asdict

import pytest
from ledger_eligibility_fixture import refreshed
from ledger_provisioning_fixture import inspect
from ledger_reader_fixture import _FINANCIAL_FIELDS, _financial_projection_receipt
from reservation_fixture import build_reservation_case
from reservation_qe_fixture import (
    assert_released,
    claim,
    coordinator,
    identity,
    intent,
    one,
    same,
    snapshot,
)
from sqlalchemy import event, text

from agent_rewind import reservation_rows
from agent_rewind.admission_transaction import TransactionOutcome, admission_transaction
from agent_rewind.migrations.schema import MigrationRefused
from agent_rewind.operation_work import OperationWork
from agent_rewind.reservation_types import ReservationRefusal
from agent_rewind.sqlite_ownership import owned_begin, owned_connect

CAP = 2 * 1024 * 1024


def calibrate_real_rows(case):
    """Reuse the reader's zero-import cohort, measuring native cells and full JSON."""

    def keys(count):
        return [identity(80_000_000 + index) for index in range(count)]

    def add(connection, values):
        for start in range(0, len(values), 64):
            batch = values[start : start + 64]
            connection.execute(
                text(
                    "INSERT INTO jobs(id,kind,created,payload,status,cancel,budget,reserved,"
                    "actor,payload_version,lease_generation,legacy_reserved_microusd) "
                    "VALUES(:id,'run',1700000000.125,'','succeeded',false,1,0,NULL,1,0,0)"
                ),
                [{"id": value} for value in batch],
            )
            connection.execute(
                text(
                    "INSERT INTO resource_scopes(resource_kind,resource_id,project_id) "
                    "VALUES('job',:id,:project)"
                ),
                [{"id": value, "project": case.project_id} for value in batch],
            )

    with owned_begin(case.engine) as connection:
        baseline = _financial_projection_receipt(connection)
        add(connection, keys(1))
        single = _financial_projection_receipt(connection)
    increments = {
        field: single[field] - baseline[field]
        for field in ("native_bytes", "canonical_bytes", "rows")
    }
    assert increments["rows"] == 2
    assert increments["native_bytes"] > 0 and increments["canonical_bytes"] > 0
    small = snapshot(case.engine)
    accepted = inspect(refreshed(case.provisioning))
    assert accepted.manifest_count == 1 and accepted.account_count == len(
        case.admission.manifest["accounts"]
    )
    same(small, snapshot(case.engine))

    # Legacy v1 retains scalar/native source gates, not the admitted v2 payload
    # limit. Eight bounded real cells separate financial size from the VM cap.
    # Only quote plus a one-byte ASCII tail is used: expansion is at most2x.
    target, count, maximum_payload_bytes = CAP - 1, 8, 131072
    assert baseline["rows"] + 2 * count < 65536
    values = keys(count)
    with owned_begin(case.engine) as connection:
        add(connection, values[1:])
        blank = _financial_projection_receipt(connection)
        for field, increment in increments.items():
            assert blank[field] == baseline[field] + count * increment
        remaining = target - blank["canonical_bytes"]
        assert 0 < remaining <= count * maximum_payload_bytes * 2
        updates = []
        for value in values:
            size = min(maximum_payload_bytes * 2, remaining)
            quotes, tail = divmod(size, 2)
            payload = '"' * quotes + "z" * tail
            assert len(payload.encode()) <= maximum_payload_bytes
            assert set(payload) <= {'"', "z"}
            updates.append({"id": value, "payload": payload})
            remaining -= size
        assert remaining == 0
        for start in range(0, len(updates), 64):
            connection.execute(
                text("UPDATE jobs SET payload=:payload WHERE id=:id"),
                updates[start : start + 64],
            )
        receipt = _financial_projection_receipt(connection)
    assert receipt["canonical_bytes"] == target
    assert 0 < receipt["native_bytes"] < CAP
    assert receipt["rows"] == baseline["rows"] + 2 * count < 65536
    assert receipt["domains"]["account"]["candidate_rows"] < 4096
    assert all(row["invalid_rows"] == 0 for row in receipt["domains"].values())
    receipt["cohort_jobs"] = count
    receipt["first_zero_job_full_reader_accepted"] = True
    return receipt


def test_actual_financial_after_image_capacity_refusal_is_atomic(
    tmp_path, monkeypatch, record_property
):
    case = build_reservation_case(tmp_path, monkeypatch, legacy=True)
    try:
        fence = claim(case)
        initial_target = one(snapshot(case.engine), "jobs", id=case.job_id)
        receipt = calibrate_real_rows(case)
        before = snapshot(case.engine)
        assert one(before, "jobs", id=case.job_id) == initial_target
        # This separate fixture qualification observes unchanged native source
        # receipts and the real prospective+128 proof. Reserve repeats its own
        # mandatory checks under its own single unchanged OperationWork.
        source_work, source_outcome = OperationWork(), TransactionOutcome()
        with admission_transaction(case.engine, source_outcome, work=source_work) as connection:
            source_receipts = reservation_rows.source_headroom(
                connection, source_work, prospective=True
            )
        assert source_outcome.commit_acknowledged and not source_outcome.cleanup_failed
        receipt["source_receipts"] = {
            name: asdict(value) for name, value in source_receipts.items()
        }
        assert source_receipts["jobs"].max_native_bytes < 132000
        same(before, snapshot(case.engine))
        # The full scaled predecessor must remain a valid retained financial state.
        inspect(refreshed(case.provisioning))
        same(before, snapshot(case.engine))
        original = reservation_rows.ReservationRows.require_headroom
        observations, writes = [], []

        def observed_headroom(self, after):
            frames = [
                [domain, [row[field] for field in fields]]
                for domain, fields in _FINANCIAL_FIELDS.items()
                for row in after[domain]
            ]
            observed = {
                "before_native_bytes": self.projection.native_bytes,
                "before_canonical_bytes": self.projection.canonical_bytes,
                "before_rows": self.projection.row_count,
                "after_canonical_bytes": len(
                    json.dumps(
                        frames, sort_keys=True, separators=(",", ":"), allow_nan=False
                    ).encode()
                ),
            }
            observations.append(observed)
            try:
                return original(self, after)
            except MigrationRefused as error:
                observed["original_code"] = error.code
                raise

        def observe_sql(_connection, _cursor, statement, _parameters, _context, _many):
            command = statement.lstrip().split(None, 1)[0].upper()
            if command in {"INSERT", "UPDATE", "DELETE", "REPLACE"}:
                writes.append(command)

        monkeypatch.setattr(reservation_rows.ReservationRows, "require_headroom", observed_headroom)
        event.listen(case.engine, "before_cursor_execute", observe_sql)
        operation = coordinator(case)
        error = None
        try:
            operation.reserve(case.principal, case.context, fence, intent(case, fence))
        except BaseException as caught:
            error = caught
        finally:
            event.remove(case.engine, "before_cursor_execute", observe_sql)
            work = operation._work
            record_property(
                "capacity_observation",
                json.dumps(
                    {
                        "native_receipt": receipt,
                        "headroom": observations,
                        "error_type": type(error).__name__,
                        "reason": getattr(error, "reason", None),
                        "code": getattr(error, "code", None),
                        "work_statements": work.statements,
                        "work_seconds": work.seconds,
                        "work_vm_instructions": work.instructions,
                        "writes": writes,
                    },
                    sort_keys=True,
                ),
            )
        same(before, snapshot(case.engine))
        assert_released(case.engine)
        assert operation.outcome.confirmed_precommit_rollback
        assert not operation.outcome.commit_attempted
        assert not operation.outcome.cleanup_failed
        if not isinstance(error, ReservationRefusal):
            if error is not None:
                raise error
            pytest.fail("reservation unexpectedly succeeded")
        assert error.reason == "capacity_exceeded"
        # Earlier limits cannot masquerade as reaching this specific after-image gate.
        assert len(observations) == 1
        observed = observations[0]
        assert observed["before_canonical_bytes"] == receipt["canonical_bytes"] == CAP - 1
        assert observed["before_native_bytes"] == receipt["native_bytes"] < CAP
        assert observed["before_rows"] == receipt["rows"]
        assert observed["after_canonical_bytes"] > CAP
        assert observed["original_code"] == "ledger_limit_exceeded"
        assert writes == []
        assert work.statements <= 512 and work.seconds < 10.0
        with owned_connect(case.engine) as connection:
            assert _financial_projection_receipt(connection) == {
                key: value
                for key, value in receipt.items()
                if key
                not in {"cohort_jobs", "first_zero_job_full_reader_accepted", "source_receipts"}
            }
    finally:
        case.close()
