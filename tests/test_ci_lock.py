"""Exercise real lock drift rejection without resolving or downloading dependencies."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_lock_check_rejects_manifest_drift_without_mutation(tmp_path):
    uv = shutil.which("uv")
    if uv is None:
        pytest.fail("Pinned uv must be available to validate the CI lock guard")
    manifest = (ROOT / "pyproject.toml").read_text()
    lock = (ROOT / "uv.lock").read_bytes()
    (tmp_path / "pyproject.toml").write_text(manifest)
    (tmp_path / "uv.lock").write_bytes(lock)
    command = [uv, "lock", "--check", "--offline", "--no-cache", "--no-python-downloads"]
    environment = {**os.environ, "UV_PYTHON_DOWNLOADS": "never"}
    valid = subprocess.run(
        command, cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30
    )
    assert valid.returncode == 0, valid.stderr
    (tmp_path / "pyproject.toml").write_text(
        manifest.replace("fastapi>=0.115,<1", "fastapi==0.1.0")
    )
    drift = subprocess.run(
        command, cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30
    )
    assert drift.returncode != 0
    assert (tmp_path / "uv.lock").read_bytes() == lock
