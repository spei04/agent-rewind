"""Run with the isolated runtime interpreter from outside the source checkout."""

import importlib.metadata
import importlib.resources
import json
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

import agent_rewind
import agent_rewind.api
import agent_rewind.cli
import agent_rewind.scoped_artifacts
from agent_rewind.migrations.compatibility import runtime_schema_compatibility
from agent_rewind.migrations.ownership_service import initialize_ownership
from agent_rewind.migrations.service import install, schema_status
from agent_rewind.run_projection import utc_created
from agent_rewind.scoped_repositories import ProjectContext, ResourceNotFound, ScopedRepositories


def repository_smoke(engine: Engine) -> None:
    repository = ScopedRepositories(engine)
    # Synthetic trusted identity matches only the explicit smoke initialization.
    context = ProjectContext("8" * 32, "9" * 32, "oidc:" + "a" * 64)
    if repository.list_resources(context, "run") != []:
        raise RuntimeError("Installed scoped repository did not preserve the empty project")
    try:
        repository.list_resources(ProjectContext("8" * 32, "7" * 32, context.principal_id), "run")
    except ResourceNotFound as error:
        if str(error) != "Resource not found.":
            raise RuntimeError("Installed scoped denial changed its public message") from None
    else:
        raise RuntimeError("Installed scoped repository admitted a foreign project")


def artifact_smoke(engine: Engine, root: Path) -> None:
    import hashlib
    from datetime import UTC, datetime

    from cryptography.fernet import Fernet

    from agent_rewind.artifact_metadata import ArtifactObject
    from agent_rewind.artifact_storage import LocalArtifactStorage
    from agent_rewind.migrations.artifact_service import initialize_artifacts

    state = initialize_artifacts(engine)
    if state["revision"] != "ar_0004_artifacts" or state["customer_ready"]:
        raise RuntimeError("Installed artifact revision failed its explicit transition")
    content = b"synthetic-installed-object"
    digest = hashlib.sha256(content).hexdigest()
    value = ArtifactObject(
        id="a" * 32,
        project_id="9" * 32,
        digest=digest,
        locator=f"objects/{'9' * 32}/v1/{digest}",
        format_version=1,
        byte_count=len(content),
        created_at=datetime.now(UTC),
    )
    store = LocalArtifactStorage(root, Fernet(Fernet.generate_key()), plaintext_limit=4096)
    store.put_verified(value, content)
    if store.read_verified(value) != content:
        raise RuntimeError("Installed bounded artifact format did not round trip")


def projection_smoke(engine: Engine) -> None:
    from agent_rewind.migrations.projection_service import backfill_run_index, initialize_projection

    result = initialize_projection(engine)
    if result["revision"] != "ar_0005_run_index" or result["projection_status"] != "complete":
        raise RuntimeError("Installed empty projection transition failed")

    def forbidden(*args: object) -> bytes:
        raise RuntimeError("Empty installed projection attempted artifact I/O")

    if backfill_run_index(engine, forbidden) != result:
        raise RuntimeError("Installed empty projection retry changed progress")


def publication_smoke(engine: Engine, root: Path) -> None:
    from cryptography.fernet import Fernet

    from agent_rewind.artifact_graph import verify_run_graph
    from agent_rewind.artifact_metadata import ArtifactError
    from agent_rewind.artifact_publication import RunPublisher, UnavailableLiveWriter
    from agent_rewind.artifact_storage import LocalArtifactStorage
    from agent_rewind.projection_publication import ProjectionPublicationWriter
    from agent_rewind.publication_journal import PublicationJournal

    journal_root = root / "publication-journal"
    journal_root.mkdir(mode=0o700)
    journal = PublicationJournal(journal_root)
    # Synthetic packaging evidence only; a deployment provisions/fsyncs its root.
    with journal.open("b" * 32) as session:
        session.freeze({"synthetic_package": True})
    with journal.open("b" * 32) as session:
        if session.intent != {"synthetic_package": True}:
            raise RuntimeError("Installed publication journal did not round trip")
    publisher = RunPublisher(
        engine,
        LocalArtifactStorage(root, Fernet(Fernet.generate_key()), plaintext_limit=4096),
        journal,
        writer=ProjectionPublicationWriter(UnavailableLiveWriter()),
    )
    try:
        publisher.prepare(
            ProjectContext("8" * 32, "9" * 32, "oidc:" + "a" * 64),
            "c" * 32,
            worker_id="synthetic",
            generation=1,
            source=lambda ref, limit: b"",
        )
    except ArtifactError as error:
        if str(error) != "publication_live_fence_unavailable":
            raise RuntimeError("Installed live publisher refused with unexpected code") from None
    else:
        raise RuntimeError("Installed publisher incorrectly enabled a legacy live writer")
    try:
        verify_run_graph(b'{"schema":1}', lambda ref, limit: b"")
    except ArtifactError:
        pass
    else:
        raise RuntimeError("Installed publication parser accepted a legacy root")


def readiness_smoke(root: Path, database_url: str) -> None:
    import asyncio
    import time

    from cryptography.fernet import Fernet
    from pydantic import SecretStr

    from agent_rewind.config import Settings
    from agent_rewind.readiness import Readiness
    from agent_rewind.sentinel import SentinelSettings, provision, read_system_sentinel

    key = SecretStr(Fernet.generate_key().decode())
    sentinel = SentinelSettings(
        _env_file=None,
        data_dir=root,
        encryption_key=key,
        installation_key=SecretStr("synthetic-package-smoke"),
    )
    provision(sentinel)
    read_system_sentinel(sentinel, time.monotonic() + 1, installation_key="synthetic-package-smoke")
    settings = Settings(
        _env_file=None, data_dir=root, database_url=database_url, encryption_key=key
    )

    async def check() -> None:
        manager = Readiness(settings)
        manager.start()
        try:
            async with asyncio.timeout(5):
                while not manager._warm:
                    await asyncio.sleep(0.01)
            if await manager.check() != "schema_incompatible":
                raise RuntimeError("Installed readiness process admitted migration-only metadata")
        finally:
            await manager.close()

    asyncio.run(check())


package = Path(agent_rewind.__file__).resolve()
if not package.is_relative_to(Path(sys.prefix).resolve()):
    raise RuntimeError("Smoke imported a source checkout instead of the installed wheel")
if utc_created(1 / 128).microsecond != 7812:
    raise RuntimeError("Installed projection timestamp rule changed")
for development_tool in ("pytest", "ruff", "mypy", "pip-audit", "setuptools"):
    try:
        importlib.metadata.version(development_tool)
    except importlib.metadata.PackageNotFoundError:
        continue
    raise RuntimeError("Runtime smoke environment contains development dependencies")
for asset in ("index.html", "style.css", "app.js"):
    content = importlib.resources.files("agent_rewind").joinpath("web", asset).read_bytes()
    if not content:
        raise RuntimeError("Packaged web asset is empty")
for profile in (
    "sqlite",
    "postgresql16",
    "sqlite_ownership",
    "postgresql16_ownership",
    "sqlite_artifacts",
    "postgresql16_artifacts",
    "sqlite_projection",
):
    shape = json.loads(
        importlib.resources.files("agent_rewind.migrations")
        .joinpath("profiles", profile + ".json")
        .read_text()
    )
    if not isinstance(shape, dict) or "installation_adoptions" not in shape:
        raise RuntimeError("Packaged frozen migration profile is missing or invalid")
if importlib.metadata.version("agent-rewind") != "0.1.0":
    raise RuntimeError("Unexpected installed package identity")
with tempfile.TemporaryDirectory(prefix="rewind-package-migration-") as temporary:
    database = Path(temporary) / "metadata.sqlite"
    engine = create_engine(f"sqlite:///{database}")
    try:
        if schema_status(engine)["state"] != "empty" or database.exists():
            raise RuntimeError("Installed schema inspection modified an empty database")
        prepared = install(engine, "synthetic-package-smoke")
        if (
            prepared["state"] != "prepared"
            or prepared["customer_ready"] is not False
            or schema_status(engine) != prepared
            or install(engine, "synthetic-package-smoke") != prepared
        ):
            raise RuntimeError("Installed Alembic revisions/profile failed the migration smoke")
        compatibility = runtime_schema_compatibility(engine)
        if compatibility.status != "incompatible" or compatibility.code != "migration_only":
            raise RuntimeError("Installed release manifest incorrectly permits customer admission")
        ownership = initialize_ownership(
            engine,
            {
                "schema_version": 1,
                "installation_key": "synthetic-package-smoke",
                "organization_id": "8" * 32,
                "project_id": "9" * 32,
                "project_name": "Synthetic installed package",
                "principal_grants": [
                    {
                        "principal_id": "oidc:" + "a" * 64,
                        "role": "maintainer",
                        "legacy_default": False,
                    }
                ],
            },
        )
        if ownership["state"] != "ownership_complete" or ownership["customer_ready"]:
            raise RuntimeError("Installed ownership revision failed the explicit transition")
        repository_smoke(engine)
        artifact_smoke(engine, Path(temporary))
        projection_smoke(engine)
        publication_smoke(engine, Path(temporary))
        compatibility = runtime_schema_compatibility(engine)
        if compatibility.status != "incompatible" or compatibility.code != "migration_only":
            raise RuntimeError(
                "Installed ownership/artifact revision incorrectly permits admission"
            )
    finally:
        engine.dispose()
    readiness_smoke(Path(temporary), f"sqlite:///{database}")
print("Installed runtime, web assets, migration revisions and profile verified outside checkout.")
