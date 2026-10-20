"""Installed worker probe against the existing synthetic PostgreSQL16 fixture."""

import asyncio

import pytest
import test_migrations_postgres as migration_cases
from pydantic import SecretStr
from sqlalchemy import text

from agent_rewind.migrations import service
from agent_rewind.readiness import Readiness
from agent_rewind.sentinel import SentinelSettings, provision

pg = migration_cases.pg
pytestmark = pytest.mark.skipif(
    not migration_cases.POSTGRES, reason="Opt-in synthetic PostgreSQL integration"
)


def test_real_postgres_readiness_refuses_migration_only_and_owns_one_connection(pg, settings):
    service.install(pg["owner"], "synthetic-readiness-postgres")
    with pg["owner"].begin() as connection:
        connection.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {pg['app_role']}")
        connection.exec_driver_sql(
            f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {pg['app_role']}"
        )
    settings.database_url = pg["app"].url.render_as_string(hide_password=False)
    provision(
        SentinelSettings(
            _env_file=None,
            data_dir=settings.data_dir,
            encryption_key=settings.encryption_key,
            installation_key=SecretStr("synthetic-readiness-postgres"),
        )
    )

    def connections():
        with pg["admin"].connect() as connection:
            return connection.execute(
                text("SELECT count(*) FROM pg_stat_activity WHERE usename=:role"),
                {"role": pg["app_role"]},
            ).scalar_one()

    async def exercise():
        manager = Readiness(settings)
        manager.start()
        try:
            async with asyncio.timeout(5):
                while not manager._warm:
                    await asyncio.sleep(0.01)
            assert await manager.check() == "schema_incompatible"
            assert connections() == 1
            with pg["owner"].begin() as blocker:
                blocker.exec_driver_sql("LOCK TABLE alembic_version IN ACCESS EXCLUSIVE MODE")
                assert await manager.check() == "dependency_unavailable"
            assert await manager.check() == "schema_incompatible"
            assert connections() == 1
        finally:
            await manager.close()
        assert connections() == 0

    asyncio.run(exercise())
