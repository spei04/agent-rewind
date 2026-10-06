import io
import tarfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.fernet import InvalidToken
from sqlalchemy import update

from agent_rewind.database import BudgetExceeded, JobStopped, jobs
from agent_rewind.workspace import File, pack, unpack


def test_encrypted_deduplicated_artifacts(storage, settings):
    _, artifacts = storage
    key = artifacts.put(b"private source code")
    assert artifacts.put(b"private source code") == key
    path = settings.data_dir / "objects" / key
    assert b"private source code" not in path.read_bytes()
    assert artifacts.get(key) == b"private source code"
    assert path.stat().st_mode & 0o077 == 0
    path.write_bytes(b"corrupted")
    with pytest.raises(InvalidToken):
        artifacts.get(key)


def test_workspace_preserves_binary_data_and_modes():
    files = {"bin/run": File(b"#!/bin/sh\n", 0o755), "data.bin": File(bytes(range(256)))}
    assert unpack(pack(files), 10000) == files


@pytest.mark.parametrize(
    "name,kind",
    [
        ("../outside", tarfile.REGTYPE),
        ("/absolute", tarfile.REGTYPE),
        ("link", tarfile.SYMTYPE),
        ("link", tarfile.LNKTYPE),
    ],
)
def test_unsafe_archive_is_rejected(name, kind):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        info = tarfile.TarInfo(name)
        info.type = kind
        info.linkname = "/etc/passwd"
        archive.addfile(info)
    with pytest.raises(ValueError):
        unpack(stream.getvalue(), 10000)


def test_budget_reservations_are_atomic(storage):
    db, artifacts = storage
    job = db.enqueue("run", artifacts.put_json({}), 0.0001, "test")
    db.claim("worker")

    def reserve(_):
        try:
            db.reserve(job, "worker", 30)
            return True
        except BudgetExceeded:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reserve, range(10)))
    assert sum(results) == 3
    assert db.job(job)["reserved"] == 90


def test_jobs_are_claimed_once_and_expired_owner_cannot_publish(storage):
    db, artifacts = storage
    job = db.enqueue("run", artifacts.put_json({}), 1, "test")
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(lambda i: db.claim(str(i)), range(4)))
    assert sum(c is not None for c in claims) == 1
    owner = db.job(job)["owner"]
    with db.engine.begin() as connection:
        connection.execute(update(jobs).where(jobs.c.id == job).values(lease_until=0))
    with pytest.raises(JobStopped):
        db.complete_job(job, owner, None, None)
    assert db.claim("new-worker") is None
    assert db.job(job)["status"] == "failed"


def test_cancellation_prevents_new_spend(storage):
    db, artifacts = storage
    job = db.enqueue("run", artifacts.put_json({}), 1, "test")
    db.claim("worker")
    db.cancel(job, "operator")
    with pytest.raises(JobStopped):
        db.reserve(job, "worker", 1)
    db.complete_job(job, "worker", None, "cancelled")
    assert db.job(job)["status"] == "cancelled"


def test_empty_directories_and_modified_times_round_trip():
    files = {
        "empty": File(b"", 0o755, "directory", 1730000000),
        "script": File(b"echo ok", 0o755, "file", 1740000000),
    }
    assert unpack(pack(files), 10000) == files


def test_content_addressing_shares_unchanged_files(storage):
    _, artifacts = storage
    first = artifacts.put_workspace({"a": File(b"a" * 10000), "b": File(b"first")})
    second = artifacts.put_workspace({"a": File(b"a" * 10000), "b": File(b"second")})
    assert (
        artifacts.json(first)["files"]["a"]["blob"] == artifacts.json(second)["files"]["a"]["blob"]
    )


def test_s3_artifacts_are_encrypted_and_verified(settings, monkeypatch):
    import io

    from agent_rewind.artifacts import Artifacts

    objects = {}

    class S3:
        def put_object(self, Bucket, Key, Body, ContentType):
            assert Bucket == "test-bucket"
            assert ContentType == "application/octet-stream"
            objects[Key] = Body

        def get_object(self, Bucket, Key):
            return {"Body": io.BytesIO(objects[Key])}

    monkeypatch.setattr("agent_rewind.artifacts.boto3.client", lambda *args, **kwargs: S3())
    settings.storage = "s3"
    settings.s3_bucket = "test-bucket"
    store = Artifacts(settings)
    key = store.put(b"private fixture")
    assert b"private fixture" not in objects["objects/" + key]
    assert store.get(key) == b"private fixture"
