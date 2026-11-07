"""Complete private F4 consumer paths on real ar8 state and restricted PG readers."""

import time
from copy import deepcopy

import pytest
import test_migrations_postgres as migration_tests
from failure_postgres_fixture import pg
from operation_failure_service_oracle import (
    add_roots,
    assert_cancel_delta,
    assert_service_released,
    canonical,
    expected_get,
    observe_service,
    one,
    publish_result,
    service_case,
)
from sqlalchemy import text
from test_failure_persistence_native_oracle import assert_same_state, whole_state

from agent_rewind import operation_failure_cancellation, operation_failure_service
from agent_rewind.errors import Fault

__all__ = ["pg"]
PG = pytest.param(
    "postgresql",
    marks=(
        pytest.mark.f4_owned_postgres,
        pytest.mark.skipif(
            not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL F4 service"
        ),
    ),
    id="postgresql",
)


@pytest.fixture(params=["sqlite", PG])
def dialect(request):
    return request.param


def read(fixture):
    return fixture.service._read_successor(fixture.principal, fixture.context, fixture.operation_id)


def cancel(fixture):
    return fixture.service._cancel_successor(
        fixture.principal, fixture.context, fixture.operation_id
    )


def dependency(call):
    with pytest.raises(Fault) as caught:
        call()
    assert caught.value.code == "dependency_unavailable"
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


@pytest.mark.parametrize("key", [False, True], ids=["principal", "service-key"])
def test_complete_empty_get_uses_one_work_and_preserves_every_native_row(
    request, tmp_path, monkeypatch, record_property, dialect, key
):
    with service_case(request, tmp_path, monkeypatch, record_property, dialect, key=key) as fixture:
        before = whole_state(fixture.case)
        with observe_service(fixture, monkeypatch, record_property) as observed:
            response = read(fixture)
        assert response == expected_get(fixture, before)
        assert len(canonical(response)) <= 2048
        assert_service_released(observed)
        assert observed.wires and max(row["identities"] for row in observed.wires) == 3
        assert_same_state(before, whole_state(fixture.case))


@pytest.mark.parametrize("key", [False, True], ids=["principal", "service-key"])
@pytest.mark.parametrize("failed", [False, True], ids=["healthy-259", "verified-failure-258"])
def test_supported_full_get_shapes_have_exact_identity_count_and_native_work(
    request, tmp_path, monkeypatch, record_property, dialect, key, failed
):
    with service_case(
        request, tmp_path, monkeypatch, record_property, dialect, failed=failed, key=key
    ) as fixture:
        identifiers = add_roots(fixture, 255)
        if not failed:
            publish_result(fixture, identifiers[-1])
        before = whole_state(fixture.case)
        if failed:
            assert one(before, "jobs", id=fixture.case.job_id)["result"] is None
            assert not [
                row
                for row in before["tables"]["artifact_refs"]["rows"]
                if row["owner_kind"] == "job"
                and row["owner_id"] == fixture.case.job_id
                and row["role"] == "result"
            ]
        with observe_service(fixture, monkeypatch, record_property) as observed:
            response = read(fixture)
        assert response == expected_get(
            fixture, before, result_run_id=None if failed else identifiers[-1]
        )
        assert len(canonical(response)) <= 2048
        assert_service_released(observed)
        assert observed.wires and max(row["identities"] for row in observed.wires) == (
            258 if failed else 259
        )
        assert max(book.source_visits for book in observed.books) == 256
        assert max(book.edges for book in observed.books) == 510
        assert bool(observed.frames) is failed
        assert_same_state(before, whole_state(fixture.case))


def test_get_one_over_source_capacity_refuses_without_disclosure_or_mutation(
    request, tmp_path, monkeypatch, record_property, dialect
):
    with service_case(request, tmp_path, monkeypatch, record_property, dialect) as fixture:
        add_roots(fixture, 256)
        before = whole_state(fixture.case)
        with observe_service(fixture, monkeypatch, record_property) as observed:
            dependency(lambda: read(fixture))
        assert_service_released(observed)
        assert all(not any(key[0] == "run" for key in book._receipts) for book in observed.books)
        assert_same_state(before, whole_state(fixture.case))


@pytest.mark.parametrize("key", [False, True], ids=["principal", "service-key"])
@pytest.mark.parametrize("count", [0, 84])
def test_complete_cancellation_has_exact_effect_and_cumulative_capacity(
    request, tmp_path, monkeypatch, record_property, dialect, key, count
):
    with service_case(
        request, tmp_path, monkeypatch, record_property, dialect, key=key, cancel=True
    ) as fixture:
        add_roots(fixture, count)
        before = whole_state(fixture.case)
        first = time.time()
        with observe_service(fixture, monkeypatch, record_property) as observed:
            response = cancel(fixture)
        last = time.time()
        assert response == {
            "operation_id": fixture.operation_id,
            "cancel_requested": True,
            "status": "cancelled",
        }
        assert len(canonical(response)) <= 2048
        assert_service_released(observed)
        assert len(observed.owners) == 1
        owner = observed.owners[0]
        assert owner.source_visits == 3 * (1 + count)
        assert owner.edges == 6 * count and owner._generation == 3
        assert not owner._failed and owner._active is None
        assert len(observed.wires) == 3
        assert all(row["identities"] == count + 3 for row in observed.wires)
        assert_cancel_delta(fixture, before, whole_state(fixture.case), (first, last))


@pytest.mark.parametrize("key", [False, True], ids=["principal", "service-key"])
def test_cancellation_85_roots_refuses_before_effect_and_commit(
    request, tmp_path, monkeypatch, record_property, dialect, key
):
    with service_case(
        request, tmp_path, monkeypatch, record_property, dialect, key=key, cancel=True
    ) as fixture:
        add_roots(fixture, 85)
        before = whole_state(fixture.case)
        with observe_service(fixture, monkeypatch, record_property) as observed:
            dependency(lambda: cancel(fixture))
        assert_service_released(observed)
        assert len(observed.owners) == 1
        assert observed.owners[0].source_visits == 172
        assert observed.owners[0].edges == 340 and observed.owners[0]._failed
        assert not any(kind == "commit" for _, kind, _, _ in observed.controls)
        assert not any(
            sql.lstrip().startswith(("UPDATE jobs", "INSERT INTO audit")) for sql in observed.sql
        )
        assert_same_state(before, whole_state(fixture.case))


@pytest.mark.parametrize("entry", ["get", "cancel"])
def test_verified_failure_with_null_result_and_actual_result_ref_refuses_at_native_proof(
    request, tmp_path, monkeypatch, record_property, dialect, entry
):
    with service_case(
        request, tmp_path, monkeypatch, record_property, dialect, failed=True, cancel=True
    ) as fixture:
        identifier = add_roots(fixture, 1)[0]
        publish_result(fixture, identifier, publish=False)
        fixture.service.artifact_loader = lambda _value: pytest.fail(
            "refused evidence loaded bytes"
        )
        before = whole_state(fixture.case)
        assert one(before, "jobs", id=fixture.case.job_id)["result"] is None
        assert (
            len(
                [
                    row
                    for row in before["tables"]["artifact_refs"]["rows"]
                    if row["owner_kind"] == "job"
                    and row["owner_id"] == fixture.case.job_id
                    and row["role"] == "result"
                ]
            )
            == 1
        )
        target = operation_failure_service if entry == "get" else operation_failure_cancellation
        original = target.observe_failure_result_absence
        proof_visits = []

        def proof(*args, **kwargs):
            proof_visits.append(True)
            return original(*args, **kwargs)

        monkeypatch.setattr(target, "observe_failure_result_absence", proof)
        with observe_service(fixture, monkeypatch, record_property) as observed:
            dependency(lambda: read(fixture) if entry == "get" else cancel(fixture))
        assert proof_visits == [True]
        assert_service_released(observed)
        assert not any(kind == "commit" for _, kind, _, _ in observed.controls)
        assert_same_state(before, whole_state(fixture.case))


def test_cancel_of_verified_failure_retains_original_evidence_and_get_error(
    request, tmp_path, monkeypatch, record_property, dialect
):
    with service_case(
        request, tmp_path, monkeypatch, record_property, dialect, failed=True, cancel=True
    ) as fixture:
        before = whole_state(fixture.case)
        first = time.time()
        with observe_service(fixture, monkeypatch, record_property) as observed:
            response = cancel(fixture)
        last = time.time()
        assert response == {
            "operation_id": fixture.operation_id,
            "cancel_requested": True,
            "status": "failed",
        }
        assert_service_released(observed)
        after = whole_state(fixture.case)
        assert_cancel_delta(fixture, before, after, (first, last))
        assert after["tables"]["job_failure_evidence"] == before["tables"]["job_failure_evidence"]
        with observe_service(fixture, monkeypatch, record_property) as read_observed:
            recovered = read(fixture)
        assert recovered == expected_get(fixture, after)
        assert_service_released(read_observed)
        assert_same_state(after, whole_state(fixture.case))


@pytest.mark.parametrize("boundary", ["before_mutation", "before_disclosure"])
def test_cancellation_preserves_allowed_worker_progress_without_evidence(
    request, tmp_path, monkeypatch, record_property, dialect, boundary
):
    with service_case(
        request, tmp_path, monkeypatch, record_property, dialect, cancel=True
    ) as fixture:
        name = "_cancel_mutate" if boundary == "before_mutation" else "_cancel_disclose"
        original = getattr(operation_failure_service._SuccessorService, name)
        visits = []

        def progress(service, *args, **kwargs):
            assert service.engine is fixture.reader_engine
            visits.append(True)
            with fixture.engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE jobs SET status='succeeded',result=:result,error=:error,"
                        "owner=:owner,lease_until=:lease WHERE id=:job"
                    ),
                    {
                        "result": "d" * 64,
                        "error": "bounded legacy progress",
                        "owner": "worker",
                        "lease": 1900000000.0,
                        "job": fixture.case.job_id,
                    },
                )
            return original(service, *args, **kwargs)

        monkeypatch.setattr(operation_failure_service._SuccessorService, name, progress)
        before = whole_state(fixture.case)
        first = time.time()
        with observe_service(fixture, monkeypatch, record_property) as observed:
            response = cancel(fixture)
        last = time.time()
        assert visits == [True]
        assert response["status"] == ("succeeded" if boundary == "before_mutation" else "cancelled")
        assert_service_released(observed)
        expected_before = before
        job = one(expected_before, "jobs", id=fixture.case.job_id)
        job.update(
            status="succeeded",
            result="d" * 64,
            error="bounded legacy progress",
            owner="worker",
            lease_until=1900000000.0,
        )
        assert_cancel_delta(fixture, expected_before, whole_state(fixture.case), (first, last))


def test_get_final_match_retains_raw_cancel_even_when_verified_digest_excludes_it(
    request, tmp_path, monkeypatch, record_property, dialect
):
    with service_case(
        request, tmp_path, monkeypatch, record_property, dialect, failed=True
    ) as fixture:
        before = whole_state(fixture.case)
        original = fixture.service._load_result
        visits = []

        def after_release(*args, **kwargs):
            value = original(*args, **kwargs)
            with fixture.engine.begin() as connection:
                connection.execute(
                    text("UPDATE jobs SET cancel=:cancel WHERE id=:job"),
                    {"cancel": True, "job": fixture.case.job_id},
                )
            visits.append(True)
            return value

        monkeypatch.setattr(fixture.service, "_load_result", after_release)
        with observe_service(fixture, monkeypatch, record_property) as observed:
            dependency(lambda: read(fixture))
        assert visits == [True]
        assert_service_released(observed)
        expected = deepcopy(before)
        one(expected, "jobs", id=fixture.case.job_id)["cancel"] = (
            True if fixture.pg is not None else 1
        )
        assert_same_state(expected, whole_state(fixture.case))
        # A fresh attempt can verify the same durable error against the new raw
        # row; the refused attempt was never permission to return its old view.
        monkeypatch.setattr(fixture.service, "_load_result", original)
        with observe_service(fixture, monkeypatch, record_property) as fresh:
            response = read(fixture)
        assert response == expected_get(fixture, expected)
        assert_service_released(fresh)


def test_public_operation_boundaries_remain_dormant_on_real_successor_schema(
    request, tmp_path, monkeypatch, record_property, dialect
):
    with service_case(request, tmp_path, monkeypatch, record_property, dialect) as fixture:
        before = whole_state(fixture.case)
        for entry in (fixture.service.read_operation, fixture.service.cancel_operation):
            with pytest.raises(Fault) as caught:
                entry(fixture.principal, fixture.context, fixture.operation_id)
            assert caught.value.code == "schema_incompatible"
        assert_same_state(before, whole_state(fixture.case))
