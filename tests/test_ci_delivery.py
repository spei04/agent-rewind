import io
import json
import runpy
import stat
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GATE = runpy.run_path(str(ROOT / "scripts" / "ci_gate.py"))
ARTIFACTS = runpy.run_path(str(ROOT / "scripts" / "ci_artifacts.py"))


def successful_results():
    return {name: {"result": "success"} for name in GATE["REQUIRED_JOBS"]}


def test_successful_gate():
    GATE["check_results"](successful_results())


@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped", "", None])
@pytest.mark.parametrize("job", sorted(GATE["REQUIRED_JOBS"]))
def test_each_required_job_must_succeed(job, result):
    results = successful_results()
    results[job] = {"result": result}
    with pytest.raises(ValueError, match="did not succeed"):
        GATE["check_results"](results)


@pytest.mark.parametrize("variant", ["missing", "unexpected", "not-object", "no-result"])
def test_gate_rejects_incomplete_job_evidence(variant):
    results = successful_results()
    if variant == "missing":
        del results["security"]
    elif variant == "unexpected":
        results["surprise"] = {"result": "success"}
    elif variant == "not-object":
        results = []
    else:
        results["security"] = {}
    with pytest.raises(ValueError):
        GATE["check_results"](results)


def make_distribution(tmp_path, wheel, extra=None, link=False, omit=None):
    name = "agent_rewind-0.1.0-py3-none-any.whl" if wheel else "agent_rewind-0.1.0.tar.gz"
    path = tmp_path / name
    members = sorted(ARTIFACTS["allowed_members"]("0.1.0", wheel) - {omit})
    if extra:
        members = [member for member in members if member != extra]
        members.append(extra)
    if wheel:
        with zipfile.ZipFile(path, "w") as archive:
            for member in members:
                info = zipfile.ZipInfo(member)
                if link and member == extra:
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, b"synthetic public package data")
    else:
        with tarfile.open(path, "w:gz") as archive:
            for member in members:
                info = tarfile.TarInfo(member)
                body = b"synthetic public package data"
                if link and member == extra:
                    info.type = tarfile.SYMTYPE
                    info.linkname = "/etc/passwd"
                    body = b""
                info.size = len(body)
                archive.addfile(info, io.BytesIO(body))
    return path


@pytest.mark.parametrize("wheel", [False, True])
def test_reviewed_distribution_files_pass(tmp_path, wheel):
    ARTIFACTS["validate_distribution"](make_distribution(tmp_path, wheel), "0.1.0")


@pytest.mark.parametrize("wheel", [False, True])
@pytest.mark.parametrize("forbidden", [".env", "evidence/result.json", "credentials.json", "../x"])
def test_distribution_rejects_private_and_unsafe_members(tmp_path, wheel, forbidden):
    path = make_distribution(tmp_path, wheel, forbidden)
    with pytest.raises(ValueError):
        ARTIFACTS["validate_distribution"](path, "0.1.0")


@pytest.mark.parametrize("wheel", [False, True])
@pytest.mark.parametrize(
    "asset",
    [
        "agent_rewind/web/app.js",
        "agent_rewind/migrations/profiles/sqlite.json",
        "agent_rewind/migrations/versions/0002_adoption.py",
    ],
)
def test_distribution_rejects_links_and_missing_runtime_resource(tmp_path, wheel, asset):
    path = make_distribution(tmp_path, wheel, "agent_rewind/cli.py", link=True)
    with pytest.raises(ValueError):
        ARTIFACTS["validate_distribution"](path, "0.1.0")
    if not wheel:
        asset = "agent_rewind-0.1.0/" + asset
    path = make_distribution(tmp_path, wheel, omit=asset)
    with pytest.raises(ValueError, match="missing required"):
        ARTIFACTS["validate_distribution"](path, "0.1.0")


def test_candidate_record_contains_only_package_and_source_identity(tmp_path):
    make_distribution(tmp_path, True)
    make_distribution(tmp_path, False)
    ARTIFACTS["record"](tmp_path, ROOT, "a" * 40)
    record = json.loads((tmp_path / "candidate.json").read_text())
    assert record["source_commit"] == "a" * 40
    assert len(record["uv_lock_sha256"]) == 64
    assert set(record["files"]) == {
        "agent_rewind-0.1.0-py3-none-any.whl",
        "agent_rewind-0.1.0.tar.gz",
    }
    assert set(p.name for p in tmp_path.iterdir()) == set(record["files"]) | {
        "candidate.json",
        "SHA256SUMS",
    }
    assert "candidate.json" in (tmp_path / "SHA256SUMS").read_text()


def test_candidate_rejects_unexpected_files_before_recording(tmp_path):
    make_distribution(tmp_path, True)
    make_distribution(tmp_path, False)
    (tmp_path / "private-evidence.json").write_text("{}")
    with pytest.raises(ValueError, match="exactly"):
        ARTIFACTS["record"](tmp_path, ROOT, "a" * 40)
    assert not (tmp_path / "candidate.json").exists()
