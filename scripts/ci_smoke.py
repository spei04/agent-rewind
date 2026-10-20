"""Run with the isolated runtime interpreter from outside the source checkout."""

import importlib.metadata
import importlib.resources
import sys
from pathlib import Path

import agent_rewind
import agent_rewind.api
import agent_rewind.cli

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
print("Installed runtime and packaged web assets verified outside the checkout.")
