"""Private recovery evidence refuses torn history, concurrency and unknown work."""

import os

import pytest

from agent_rewind.artifact_metadata import ArtifactError
from agent_rewind.publication_journal import PublicationJournal

ID = "a" * 32


@pytest.fixture
def journal(tmp_path):
    root = tmp_path / "journal"
    root.mkdir(mode=0o700)
    return PublicationJournal(root)


def test_roundtrip_preserves_unknown_attempt(journal):
    with journal.open(ID) as session:
        session.freeze({"synthetic": 1})
        session.append("upload_started", {"object_id": "b" * 32, "backend_work": "UNKNOWN"})
    with journal.open(ID) as session:
        assert session.intent == {"synthetic": 1}
        assert session.records[0]["data"]["backend_work"] == "UNKNOWN"
        session.freeze({"synthetic": 1})
        with pytest.raises(ArtifactError, match="intent_conflict"):
            session.freeze({"synthetic": 2})


def test_requires_preprovisioned_private_root(tmp_path):
    with (
        pytest.raises(ArtifactError, match="journal_unavailable"),
        PublicationJournal(tmp_path / "absent").open(ID),
    ):
        pytest.fail("missing root accepted")
    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    with pytest.raises(ArtifactError, match="journal_unsafe"), PublicationJournal(public).open(ID):
        pytest.fail("public root accepted")


def test_exclusive_writer(journal):
    with (
        journal.open(ID),
        pytest.raises(ArtifactError, match="publication_in_progress"),
        journal.open(ID),
    ):
        pytest.fail("second writer accepted")


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"{",
        b'{"sequence":0,"sequence":1}',
        b'{"sequence":0,"kind":[],"data":{}}',
        b'{"sequence":false,"kind":"upload_started","data":{}}',
    ],
)
def test_torn_or_malformed_records_refuse(journal, content):
    with journal.open(ID) as session:
        session.freeze({"synthetic": 1})
        session.append("upload_started", {})
    (journal.root / ID / "00000000000.json").write_bytes(content)
    with pytest.raises(ArtifactError), journal.open(ID):
        pytest.fail("corrupt history accepted")


def test_noncontiguous_sequence_refuses(journal):
    with journal.open(ID) as session:
        session.freeze({"synthetic": 1})
        session.append("upload_started", {})
    (journal.root / ID / "00000000000.json").rename(journal.root / ID / "00000000001.json")
    with pytest.raises(ArtifactError, match="journal_invalid"), journal.open(ID):
        pytest.fail("gap accepted")


def test_retry_flushes_complete_file_after_failed_fsync(journal, monkeypatch):
    real = os.fsync
    with journal.open(ID) as session:
        monkeypatch.setattr(
            os, "fsync", lambda _: (_ for _ in ()).throw(OSError("synthetic fsync"))
        )
        with pytest.raises(OSError):
            session.freeze({"synthetic": 1})
    calls = []

    def observe(fd):
        calls.append(os.fstat(fd).st_size)
        real(fd)

    monkeypatch.setattr(os, "fsync", observe)
    with journal.open(ID) as session:
        session.freeze({"synthetic": 1})
    assert len(b'{"synthetic":1}') in calls


def test_caps_include_intent_and_records(journal, monkeypatch):
    import agent_rewind.publication_journal as module

    monkeypatch.setattr(module, "MAX_JOURNAL_BYTES", 40)
    with journal.open(ID) as session:
        session.freeze({"synthetic": 1})
        with pytest.raises(ArtifactError, match="journal_limit"):
            session.append("upload_started", {})
    assert list((journal.root / ID).glob("0*.json")) == []


def test_symlink_evidence_refuses(journal, tmp_path):
    with journal.open(ID) as session:
        session.freeze({"synthetic": 1})
    (journal.root / ID / "intent.json").unlink()
    (journal.root / ID / "intent.json").symlink_to(tmp_path / "other")
    with pytest.raises(ArtifactError), journal.open(ID):
        pytest.fail("symlink accepted")
