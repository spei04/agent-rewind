"""Validate distributions without extracting them; record only reviewed candidate files."""

import argparse
import hashlib
import json
import re
import stat
import tarfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath

MAX_ENTRIES = 512
MAX_BYTES = 20 * 1024 * 1024
POLICY = json.loads(Path(__file__).with_name("distribution-files.json").read_text())


def allowed_members(version: str, wheel: bool) -> set[str]:
    runtime = set(POLICY["runtime"])
    if wheel:
        return runtime | {f"agent_rewind-{version}.dist-info/{p}" for p in POLICY["dist_info"]}
    files = runtime | set(POLICY["sdist"])
    files |= {f"agent_rewind.egg-info/{p}" for p in POLICY["egg_info"]}
    return {f"agent_rewind-{version}/{p}" for p in files}


def check_member(name: str, allowed: set[str], directory: bool) -> None:
    path = PurePosixPath(name)
    if "\\" in name or path.is_absolute() or ".." in path.parts:
        raise ValueError("Unsafe distribution member path")
    normalized = str(path)
    if name.rstrip("/") != normalized:
        raise ValueError("Noncanonical distribution member path")
    if directory:
        if not any(item.startswith(normalized + "/") for item in allowed):
            raise ValueError("Unexpected distribution directory")
    elif normalized not in allowed:
        raise ValueError(f"Unexpected distribution member: {normalized}")


def validate_distribution(path: Path, version: str) -> None:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError("Invalid distribution file")
    wheel = path.suffix == ".whl"
    allowed = allowed_members(version, wheel)
    seen: set[str] = set()
    size = 0
    count = 0
    if wheel:
        with zipfile.ZipFile(path) as archive:
            for item in archive.infolist():
                count += 1
                size += item.file_size
                if count > MAX_ENTRIES or size > MAX_BYTES:
                    raise ValueError("Distribution exceeds inspection bounds")
                if stat.S_ISLNK(item.external_attr >> 16):
                    raise ValueError("Distribution links are forbidden")
                check_member(item.filename, allowed, item.is_dir())
                if item.filename in seen:
                    raise ValueError("Duplicate distribution member")
                seen.add(item.filename)
    else:
        with tarfile.open(path, "r:gz") as archive:
            for item in archive:
                count += 1
                size += item.size
                if count > MAX_ENTRIES or size > MAX_BYTES:
                    raise ValueError("Distribution exceeds inspection bounds")
                if not (item.isfile() or item.isdir()):
                    raise ValueError("Distribution links and special files are forbidden")
                check_member(item.name, allowed, item.isdir())
                if item.name in seen:
                    raise ValueError("Duplicate distribution member")
                seen.add(item.name)
    required = set(POLICY["runtime"])
    if not wheel:
        required = {f"agent_rewind-{version}/{p}" for p in required}
    if not required <= seen:
        raise ValueError("Distribution is missing required runtime files")


def validate_directory(directory: Path, version: str) -> list[Path]:
    names = {f"agent_rewind-{version}-py3-none-any.whl", f"agent_rewind-{version}.tar.gz"}
    if {p.name for p in directory.iterdir()} != names:
        raise ValueError("Candidate directory must contain exactly the wheel and sdist")
    files = sorted(directory.iterdir())
    for path in files:
        validate_distribution(path, version)
    return files


def record(directory: Path, root: Path, commit: str) -> None:
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("Invalid source commit identity")
    project = tomllib.loads((root / "pyproject.toml").read_text())
    version = project["project"]["version"]
    files = validate_directory(directory, version)
    digests = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    provenance = {
        "schema": 1,
        "source_commit": commit,
        "uv_lock_sha256": hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest(),
        "pyproject_sha256": hashlib.sha256((root / "pyproject.toml").read_bytes()).hexdigest(),
        "uv_version": "0.11.21",
        "tested_python": ["3.11", "3.12"],
        "files": digests,
        "status": "candidate; no deployment or production certification",
    }
    metadata = directory / "candidate.json"
    metadata.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    digests[metadata.name] = hashlib.sha256(metadata.read_bytes()).hexdigest()
    (directory / "SHA256SUMS").write_text(
        "".join(f"{digest}  {name}\n" for name, digest in sorted(digests.items()))
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--commit")
    args = parser.parse_args()
    if args.commit:
        record(args.directory, args.root, args.commit)
    else:
        version = tomllib.loads((args.root / "pyproject.toml").read_text())["project"]["version"]
        validate_directory(args.directory, version)
