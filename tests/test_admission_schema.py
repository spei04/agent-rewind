"""Admission DDL constraints, before catalog/initializer/repository acceptance."""

import json

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError
from test_artifact_metadata import OTHER, PROJECT, prepare

from agent_rewind.migrations import service
from agent_rewind.migrations.admission_schema import create_admission_schema
from agent_rewind.migrations.schema import COLUMNS, PROJECTION

JOB = "2" * 32
SECOND_JOB = "3" * 32
FOREIGN_JOB = "4" * 32
OPERATION = "a" * 32
PRINCIPAL = "oidc:" + "b" * 64
DIGEST = "c" * 64


def job(connection, identifier=JOB, *, project=PROJECT):
    connection.execute(
        text(
            "INSERT INTO jobs(id,kind,created,payload,status,cancel,budget,reserved,actor) "
            "VALUES(:id,'run',1700000000.125,:payload,'succeeded',false,500000,245000,:actor)"
        ),
        {"id": identifier, "payload": "f" * 64, "actor": PRINCIPAL},
    )
    connection.execute(
        text("INSERT INTO resource_scopes VALUES('job',:id,:project)"),
        {"id": identifier, "project": project},
    )


def operation(connection, **updates):
    values = {
        "id": OPERATION,
        "project_id": PROJECT,
        "principal_id": PRINCIPAL,
        "kind": "run",
        "client_operation_id": "d" * 32,
        "request_digest": "e" * 64,
        "job_id": JOB,
        "accepted_response": json.dumps(
            {"job_id": JOB, "operation_id": OPERATION}, sort_keys=True, separators=(",", ":")
        ),
        "created_at": "2026-01-01T00:00:00+00:00",
        "retain_until": "2026-04-01T00:00:00+00:00",
        "job_resource_kind": "job",
        "execution_config_digest": DIGEST,
        "payload_version": 2,
        "failure_correlation_id": "f" * 32,
    }
    values.update(updates)
    connection.execute(
        text(
            "INSERT INTO operations ("
            + ",".join(values)
            + ") VALUES ("
            + ",".join(":" + key for key in values)
            + ")"
        ),
        values,
    )


def alias(connection, **updates):
    values = {
        "project_id": PROJECT,
        "principal_id": PRINCIPAL,
        "kind": "run",
        "key_hash": "1" * 64,
        "operation_id": OPERATION,
        "request_digest": "e" * 64,
    }
    values.update(updates)
    connection.execute(
        text(
            "INSERT INTO operation_keys ("
            + ",".join(values)
            + ") VALUES ("
            + ",".join(":" + key for key in values)
            + ")"
        ),
        values,
    )


def predecessor(engine):
    prepare(engine)
    with service.migration_transaction(engine) as connection:
        service._alembic(connection, "upgrade", PROJECTION)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO projects(id,organization_id,name,created_at) "
                "SELECT :other,organization_id,'Other',created_at FROM projects WHERE id=:project"
            ),
            {"other": OTHER, "project": PROJECT},
        )
        job(connection)
        job(connection, SECOND_JOB)
        job(connection, FOREIGN_JOB, project=OTHER)


@pytest.fixture
def admission_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'admission.sqlite'}")

    @event.listens_for(engine, "connect")
    def foreign_keys(dbapi, _record):
        dbapi.execute("PRAGMA foreign_keys=ON")

    predecessor(engine)
    with service.migration_transaction(engine) as connection:
        create_admission_schema(connection)
    yield engine
    engine.dispose()


def test_exact_additions_and_historical_defaults(admission_engine):
    with admission_engine.connect() as connection:
        tables = inspect(connection).get_table_names()
        assert len(tables) == 17
        assert {"operations", "operation_keys"} <= set(tables)
        columns = inspect(connection).get_columns("jobs")
        assert [c["name"] for c in columns[:13]] == [c[0] for c in COLUMNS["jobs"]]
        assert [c["name"] for c in columns[13:]] == [
            "payload_version",
            "execution_config_ref",
            "execution_config_digest",
        ]
        assert (
            connection.exec_driver_sql(
                "SELECT payload_version,execution_config_ref,execution_config_digest FROM jobs"
            ).all()
            == [(1, None, None)] * 3
        )
        assert connection.exec_driver_sql("SELECT sum(reserved) FROM jobs").scalar_one() == 735000


@pytest.mark.parametrize("principal", [PRINCIPAL, "api-key:" + "a" * 32])
def test_valid_operation_alias_and_retained_history_without_membership(admission_engine, principal):
    with admission_engine.begin() as connection:
        operation(connection, principal_id=principal)
        alias(connection, principal_id=principal)
        assert (
            connection.execute(
                text("SELECT count(*) FROM project_memberships WHERE principal_id=:principal"),
                {"principal": principal},
            ).scalar_one()
            == 0
        )
        assert connection.exec_driver_sql("SELECT count(*) FROM operations").scalar_one() == 1
        # Retain-until is not replay eligibility or an automatic deletion timer.
        connection.exec_driver_sql(
            "UPDATE operations SET created_at='2000-01-01T00:00:00+00:00',"
            "retain_until='2000-04-01T00:00:00+00:00'"
        )
        assert connection.exec_driver_sql("SELECT count(*) FROM operation_keys").scalar_one() == 1


@pytest.mark.parametrize(
    "updates",
    [
        {"id": "A" * 32},
        {"id": b"a" * 32},
        {"id": OPERATION + "\0suffix"},
        {"project_id": OTHER},
        {"project_id": PROJECT + "\0suffix"},
        {"principal_id": "unverified"},
        {"principal_id": PRINCIPAL + "\0suffix"},
        {"principal_id": b"oidc:" + b"b" * 64},
        {"principal_id": "oidc:" + "B" * 64},
        {"principal_id": "api-key:" + "a" * 31},
        {"kind": "study"},
        {"kind": b"run"},
        {"client_operation_id": "d" * 31},
        {"client_operation_id": "d" * 32 + "\0suffix"},
        {"request_digest": "E" * 64},
        {"request_digest": "e" * 64 + "\0suffix"},
        {"job_resource_kind": "run"},
        {"job_id": FOREIGN_JOB},
        {"job_id": "9" * 32},
        {"execution_config_digest": "c" * 64 + "\0suffix"},
        {"execution_config_digest": b"c" * 64},
        {"payload_version": 1},
        {"payload_version": 2.5},
        {"payload_version": None},
        {"failure_correlation_id": "f" * 32 + "\0suffix"},
        {"accepted_response": "{}"},
        {"accepted_response": '{"job_id":"' + JOB + '","operation_id":"' + "9" * 32 + '"}'},
        {"accepted_response": '{"operation_id":"' + OPERATION + '","job_id":"' + JOB + '"}'},
        {
            "accepted_response": '{"job_id":"'
            + JOB
            + '","operation_id":"'
            + OPERATION
            + '","extra":1}'
        },
        {"retain_until": "2025-01-01T00:00:00+00:00"},
    ],
)
def test_invalid_operation_refuses_without_partial_row(admission_engine, updates):
    with pytest.raises(IntegrityError), admission_engine.begin() as connection:
        operation(connection, **updates)
    with admission_engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM operations").scalar_one() == 0


@pytest.mark.parametrize(
    "changed",
    [
        {"principal_id": "oidc:" + "a" * 64},
        {"project_id": OTHER},
        {"kind": "study"},
        {"operation_id": "9" * 32},
        {"operation_id": OPERATION + "\0suffix"},
        {"key_hash": "1" * 64 + "\0suffix"},
        {"key_hash": b"1" * 64},
        {"request_digest": "e" * 64 + "\0suffix"},
        {"principal_id": PRINCIPAL + "\0suffix"},
    ],
)
def test_alias_requires_exact_scoped_owner(admission_engine, changed):
    with admission_engine.begin() as connection:
        operation(connection)
    with pytest.raises(IntegrityError), admission_engine.begin() as connection:
        alias(connection, **changed)


@pytest.mark.parametrize("duplicate", ["job", "client", "key"])
def test_independent_identity_uniqueness(admission_engine, duplicate):
    with admission_engine.begin() as connection:
        operation(connection)
        alias(connection)
    with pytest.raises(IntegrityError), admission_engine.begin() as connection:
        if duplicate == "key":
            alias(connection)
        else:
            new_id = "9" * 32
            target_job = JOB if duplicate == "job" else SECOND_JOB
            operation(
                connection,
                id=new_id,
                job_id=target_job,
                client_operation_id="8" * 32 if duplicate == "job" else "d" * 32,
                accepted_response=json.dumps(
                    {"job_id": target_job, "operation_id": new_id},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )


@pytest.mark.parametrize(
    "version,ref,digest,valid",
    [
        (1, None, None, True),
        (1, DIGEST, DIGEST, True),
        (2, DIGEST, DIGEST, True),
        (2, None, None, False),
        (1, DIGEST, None, False),
        (1, None, DIGEST, False),
        (2, DIGEST, None, False),
        (2, None, DIGEST, False),
        (1, DIGEST, "d" * 64, False),
        (2, DIGEST, "d" * 64, False),
        (2, DIGEST + "\0suffix", DIGEST + "\0suffix", False),
        (2, b"c" * 64, b"c" * 64, False),
        (2, "C" * 64, "C" * 64, False),
        (3, DIGEST, DIGEST, False),
        (1.5, DIGEST, DIGEST, False),
    ],
)
def test_job_config_pair_constraint(admission_engine, version, ref, digest, valid):
    def update(connection):
        connection.execute(
            text(
                "UPDATE jobs SET payload_version=:version,execution_config_ref=:ref,"
                "execution_config_digest=:digest WHERE id=:id"
            ),
            {"version": version, "ref": ref, "digest": digest, "id": JOB},
        )

    if valid:
        with admission_engine.begin() as connection:
            update(connection)
    else:
        with pytest.raises(IntegrityError), admission_engine.begin() as connection:
            update(connection)


def test_config_association_and_alias_digest_remain_repository_obligations(admission_engine):
    # SQL enforces scoped identity, not a fictitious digest-to-artifact-ID FK.
    # P2 repositories must reject these otherwise structurally legal rows.
    with admission_engine.begin() as connection:
        operation(connection)
        alias(connection, request_digest="9" * 64)
        assert connection.exec_driver_sql("SELECT count(*) FROM artifact_refs").scalar_one() == 0
        assert (
            connection.exec_driver_sql(
                "SELECT execution_config_ref FROM jobs WHERE id='" + JOB + "'"
            ).scalar_one()
            is None
        )


def test_ddl_rollback_keeps_original_thirteen_job_fields(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'rollback.sqlite'}")
    try:
        predecessor(engine)
        with engine.connect() as connection:
            before = connection.exec_driver_sql("SELECT * FROM jobs ORDER BY id").all()
            tables = inspect(connection).get_table_names()
        with (
            pytest.raises(RuntimeError, match="before commit"),
            service.migration_transaction(engine) as connection,
        ):
            create_admission_schema(connection)
            operation(connection)
            alias(connection)
            raise RuntimeError("synthetic failure before commit")
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT * FROM jobs ORDER BY id").all() == before
            assert inspect(connection).get_table_names() == tables
            assert len(inspect(connection).get_columns("jobs")) == 13
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "project,principal,target",
    [
        (PROJECT, "oidc:" + "a" * 64, SECOND_JOB),
        (OTHER, PRINCIPAL, FOREIGN_JOB),
    ],
)
def test_identity_namespace_is_project_and_principal_scoped(
    admission_engine, project, principal, target
):
    with admission_engine.begin() as connection:
        operation(connection)
        alias(connection)
        new_id = "9" * 32
        operation(
            connection,
            id=new_id,
            project_id=project,
            principal_id=principal,
            job_id=target,
            accepted_response=json.dumps(
                {"job_id": target, "operation_id": new_id},
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        alias(connection, project_id=project, principal_id=principal, operation_id=new_id)
        assert connection.exec_driver_sql("SELECT count(*) FROM operations").scalar_one() == 2
        assert connection.exec_driver_sql("SELECT count(*) FROM operation_keys").scalar_one() == 2
