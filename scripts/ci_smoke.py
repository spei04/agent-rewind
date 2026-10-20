"""Run with the isolated runtime interpreter from outside the source checkout."""

import importlib.metadata
import importlib.resources
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine

import agent_rewind
import agent_rewind.api
import agent_rewind.cli
from agent_rewind.migrations.service import install, schema_status

package = Path(agent_rewind.__file__).resolve()
if not package.is_relative_to(Path(sys.prefix).resolve()):
    raise RuntimeError("Smoke imported a source checkout instead of the installed wheel")
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
    finally:
        engine.dispose()
print("Installed runtime, web assets, migration revisions and profile verified outside checkout.")
