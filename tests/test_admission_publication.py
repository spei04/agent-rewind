"""Bounded prospective metadata selection, not an upload or retry capability."""

from dataclasses import replace

import pytest
import test_admission_repository as fixtures
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from test_artifact_metadata import OTHER

from agent_rewind import admission_publication, artifact_metadata
from agent_rewind.admission_publication import PublicationCollision, select_descriptor
from agent_rewind.admission_transaction import AdmissionError
from agent_rewind.artifact_metadata import ArtifactError, object_locator, record_verified

admission_engine = fixtures.admission_engine
repository = fixtures.repository


def test_scoped_existing_descriptor_preserves_all_seven_original_fields(repository):
    f = repository
    expected = f.value.task_binding.descriptor
    prospective = replace(expected, id="9" * 32)
    with f.engine.connect() as connection:
        assert select_descriptor(connection, prospective) == expected
    with fixtures.transaction(f.engine) as connection:
        with pytest.raises(PublicationCollision) as caught:
            admission_publication._record(connection, prospective)
        assert caught.value.expected == prospective and caught.value.winner == expected


@pytest.mark.parametrize("both", [False, True])
def test_foreign_id_or_two_candidate_rows_cannot_prove_retry(repository, both):
    f = repository
    expected = f.value.task_binding.descriptor
    foreign = replace(
        expected, id="9" * 32, project_id=OTHER, locator=object_locator(OTHER, expected.digest)
    )
    with fixtures.transaction(f.engine) as connection:
        record_verified(connection, foreign)
    prospective = replace(expected, id=foreign.id)
    if not both:
        prospective = replace(
            prospective, digest="a" * 64, locator=object_locator(expected.project_id, "a" * 64)
        )
    with f.engine.connect() as connection, pytest.raises(ArtifactError if both else AdmissionError):
        select_descriptor(connection, prospective)
    with fixtures.transaction(f.engine) as connection:
        with pytest.raises((ArtifactError, AdmissionError)) as caught:
            admission_publication._record(connection, prospective)
        assert not isinstance(caught.value, PublicationCollision)


@pytest.mark.parametrize("field", ["created_at", "byte_count", "locator"])
def test_descriptor_candidate_bytes_are_bounded_before_parser(repository, monkeypatch, field):
    f = repository
    expected = f.value.task_binding.descriptor
    with f.engine.begin() as connection:
        # The existing SQLite catalog permits malformed timestamp/typed cells;
        # disable CHECKs only for the corruption fixture's constrained locator.
        connection.exec_driver_sql("PRAGMA ignore_check_constraints=ON")
        connection.execute(
            text(f"UPDATE artifact_objects SET {field}=:bad WHERE id=:id"),
            {"bad": "x" * 131072, "id": expected.id},
        )
        connection.exec_driver_sql("PRAGMA ignore_check_constraints=OFF")
    seen = []
    original = artifact_metadata._object

    def observe(row):
        seen.append(dict(row))
        assert all(value is None or len(str(value)) < 200 for value in row.values())
        return original(row)

    monkeypatch.setattr(artifact_metadata, "_object", observe)
    with f.engine.connect() as connection, pytest.raises(ArtifactError):
        select_descriptor(connection, expected)
    assert seen and all(value is None for value in seen[0].values())


def test_generic_metadata_integrity_failure_never_mints_retry_proof(repository, monkeypatch):
    def failure(*args):
        raise IntegrityError("PRIVATE", {}, RuntimeError("PRIVATE"))

    monkeypatch.setattr(admission_publication, "record_verified", failure)
    with fixtures.transaction(repository.engine) as connection, pytest.raises(IntegrityError):
        admission_publication._record(connection, repository.value.task_binding.descriptor)
