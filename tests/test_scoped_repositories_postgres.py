"""Actual PostgreSQL SELECT-only repository authority and project-boundary checks."""

import pytest
import test_migrations_postgres as migrations
from sqlalchemy import text
from test_scoped_repositories import (
    CA,
    CB,
    CONTENT,
    HASH,
    JOB_A,
    JOB_B,
    RUN_A,
    RUN_B,
    STUDY,
    TRIAL,
    A,
    Objects,
    add_study,
    edit,
    populate,
)

from agent_rewind.scoped_repositories import ResourceNotFound, ScopedRepositories

pg = migrations.pg
pytestmark = pytest.mark.skipif(not migrations.POSTGRES, reason="Opt-in synthetic PostgreSQL")


def prepare(pg):
    populate(pg["owner"])
    with pg["owner"].begin() as connection:
        connection.exec_driver_sql(
            f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {pg['app_role']}"
        )
    return ScopedRepositories(pg["app"])


def test_postgres_runtime_select_only_role_reads_only_its_explicit_scope(pg):
    repo = prepare(pg)
    assert repo.get_run(CA, RUN_A)["id"] == RUN_A
    assert repo.get_run(CB, RUN_B)["id"] == RUN_B
    assert [row["id"] for row in repo.list_resources(CA, "job")] == [JOB_A]
    with pytest.raises(ResourceNotFound):
        repo.get_job(CA, JOB_B)
    with pg["app"].connect() as connection:
        assert connection.execute(
            text(
                "SELECT has_table_privilege(current_user,'public.records','INSERT'),"
                "has_schema_privilege(current_user,'public','CREATE')"
            )
        ).one() == (False, False)


def test_postgres_forged_study_and_run_closure_denies_before_ref_lookup(pg):
    repo = prepare(pg)
    add_study(pg["owner"], claimed=False)
    assert repo.get_study(CA, STUDY)["source_run"] == RUN_A
    assert repo.get_run(CA, TRIAL)["status"] == "failed"
    edit(pg["owner"], TRIAL, parent_id=RUN_B)
    objects = Objects()
    scoped = ScopedRepositories(
        pg["app"], artifact_resolver=objects.resolve, artifact_loader=objects.load
    )
    with pytest.raises(ResourceNotFound):
        scoped.read_artifact(CA, "run", TRIAL, "task", HASH)
    assert objects.resolved == objects.loaded == []


def test_postgres_same_hash_project_refs_and_revocation_after_io(pg):
    prepare(pg)
    objects = Objects()
    repo = ScopedRepositories(
        pg["app"], artifact_resolver=objects.resolve, artifact_loader=objects.load
    )
    assert repo.read_artifact(CA, "run", RUN_A, "task", HASH) == CONTENT
    assert repo.read_artifact(CB, "run", RUN_B, "task", HASH) == CONTENT
    assert objects.loaded[0].project_id != objects.loaded[1].project_id

    def revoke(value):
        with pg["owner"].begin() as connection:
            connection.execute(
                text(
                    "UPDATE project_memberships SET revoked_at=CURRENT_TIMESTAMP "
                    "WHERE project_id=:p"
                ),
                {"p": A},
            )
        return CONTENT

    repo.artifact_loader = revoke
    with pytest.raises(ResourceNotFound):
        repo.read_artifact(CA, "run", RUN_A, "task", HASH)
