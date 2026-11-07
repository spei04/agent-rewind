"""Native complete GET at the aggregate receipt limit and one byte beyond it."""

import hashlib
import json

import pytest
import test_migrations_postgres as migration_tests
from failure_postgres_fixture import pg
from operation_failure_service_oracle import (
    add_roots,
    assert_service_released,
    canonical,
    expected_get,
    observe_service,
    service_case,
)
from sqlalchemy import text
from test_failure_persistence_native_oracle import (
    assert_same_state,
    native_digest_inputs,
    whole_state,
)

from agent_rewind.database import records
from agent_rewind.errors import Fault

__all__ = ["pg"]

# Literal adopted wire order, independent of production readers and constants.
OPERATION = (
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
)
JOB = (
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
)
CONFIGURATION = (
    "id",
    "project_id",
    "digest",
    "locator",
    "format_version",
    "byte_count",
    "created_at",
    "reference_id",
)
LIMIT = 4 * 1024 * 1024


@pytest.fixture(
    params=[
        "sqlite",
        pytest.param(
            "postgresql",
            marks=(
                pytest.mark.f4_owned_postgres,
                pytest.mark.skipif(
                    not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL F4 aggregate"
                ),
            ),
        ),
    ]
)
def dialect(request):
    return request.param


def native_wire(fixture, identifiers):
    """Independent owner SELECTs and a literal wire; no successor book is called."""
    operation, configuration = native_digest_inputs(fixture.case)
    with fixture.engine.connect() as connection:
        job = dict(
            connection.execute(
                text("SELECT " + ",".join(JOB) + ",lease_generation FROM jobs WHERE id=:job"),
                {"job": fixture.case.job_id},
            )
            .mappings()
            .one()
        )
        runs = [
            dict(
                connection.execute(
                    text(
                        "SELECT id,kind,created,CAST(data AS TEXT) AS body "
                        "FROM records WHERE id=:id AND kind='run'"
                    ),
                    {"id": identifier},
                )
                .mappings()
                .one()
            )
            for identifier in identifiers
        ]
        assert (
            connection.execute(
                text("SELECT count(*) FROM job_failure_evidence WHERE job_id=:job"),
                {"job": fixture.case.job_id},
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM provider_calls WHERE job_id=:job"),
                {"job": fixture.case.job_id},
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM artifact_refs WHERE owner_kind='job' "
                    "AND owner_id=:job AND role='result'"
                ),
                {"job": fixture.case.job_id},
            ).scalar_one()
            == 0
        )
    assert job["lease_generation"] == 0 and job["result"] is None
    assert [row["id"] for row in runs] == sorted(identifiers)
    wire = {
        "v": 1,
        "rows": [
            ["operation", fixture.operation_id, [operation[key] for key in OPERATION]],
            ["job", fixture.case.job_id, [job[key] for key in JOB], [0, 0, False, None]],
            [
                "admission_config",
                fixture.case.job_id,
                [configuration[key] for key in CONFIGURATION],
            ],
            *[
                ["run", row["id"], [row[key] for key in ("id", "kind", "created", "body")]]
                for row in runs
            ],
        ],
        "observations": [
            ["result_count", fixture.case.job_id, [0]],
            ["cohort", fixture.case.job_id, identifiers],
        ],
    }
    return canonical(wire), runs


@pytest.mark.parametrize("extra", [0, 1], ids=["exact-4MiB", "one-byte-over"])
def test_complete_get_enforces_native_aggregate_wire_without_refunding_or_mutating(
    request, tmp_path, monkeypatch, record_property, dialect, extra
):
    with service_case(request, tmp_path, monkeypatch, record_property, dialect) as fixture:
        identifiers = add_roots(fixture, 2, update={"padding": ""})
        initial, runs = native_wire(fixture, identifiers)
        required = LIMIT + extra - len(initial)
        assert required > 0
        padding = (required // 2, required - required // 2)
        with fixture.engine.begin() as connection:
            for row, size in zip(runs, padding, strict=True):
                body = json.loads(row["body"])
                assert body["padding"] == ""
                body["padding"] = "x" * size
                changed = connection.execute(
                    records.update()
                    .where(records.c.id == row["id"], records.c.kind == "run")
                    .values(data=body)
                )
                assert changed.rowcount == 1
        expected, populated = native_wire(fixture, identifiers)
        # Each candidate is legal by itself; the one-over case reaches aggregate
        # receipt retention, not a per-body, lineage, or source-count refusal.
        assert len(expected) == LIMIT + extra
        assert all(len(row["body"].encode("utf-8")) <= 2 * 1024 * 1024 for row in populated)
        assert all(json.loads(row["body"])["parent_id"] is None for row in populated)
        before = whole_state(fixture.case)
        with observe_service(fixture, monkeypatch, record_property) as observed:
            if extra:
                with pytest.raises(Fault) as caught:
                    fixture.service._read_successor(
                        fixture.principal, fixture.context, fixture.operation_id
                    )
                assert caught.value.code == "dependency_unavailable"
            else:
                response = fixture.service._read_successor(
                    fixture.principal, fixture.context, fixture.operation_id
                )
                assert response == expected_get(fixture, before)
                assert len(canonical(response)) <= 2048
        assert_service_released(observed)
        assert len(observed.books) == 1
        book = observed.books[0]
        assert book.source_visits == 3 and book.edges == 4
        assert len([key for key in book._receipts if key[0] == "run"]) == 2
        assert book.byte_count <= LIMIT
        if extra:
            # The two body receipts fit; the final cohort observation is the
            # independently measured last byte that cannot be retained.
            assert ("cohort", fixture.case.job_id) not in book.observations
            assert not observed.wires
        else:
            assert book.byte_count == LIMIT
            assert observed.wires and all(
                row["bytes"] == LIMIT
                and row["identities"] == 5
                and row["sha256"] == hashlib.sha256(expected).hexdigest()
                for row in observed.wires
            )
        assert_same_state(before, whole_state(fixture.case))
        record_property(
            "f4_native_aggregate_boundary",
            json.dumps(
                {
                    "expected_wire_bytes": len(expected),
                    "expected_wire_sha256": hashlib.sha256(expected).hexdigest(),
                    "native_body_bytes": [len(row["body"].encode("utf-8")) for row in populated],
                    "source_visits": book.source_visits,
                    "retained_bytes": book.byte_count,
                    "accepted": not bool(extra),
                },
                sort_keys=True,
            ),
        )
