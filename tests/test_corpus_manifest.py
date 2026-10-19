"""Synthetic admission tests; no approval, content transfer or model execution."""

import copy
import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from agent_rewind.corpus import (
    MAX_MANIFEST_BYTES,
    AdmissionPolicy,
    CorpusManifest,
    CorpusManifestError,
    validate_corpus_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "contracts" / "fixtures" / "corpus-manifest.synthetic.json"
NOW = datetime(2026, 10, 19, 12, tzinfo=UTC)
POLICY = AdmissionPolicy(
    processor_id="synthetic-model-region-a-no-retention",
    approved_processors=frozenset({"synthetic-model-region-a-no-retention"}),
    approved_storage_profiles=frozenset({"synthetic-private-storage"}),
    purpose="independent-confirmation",
)


@pytest.fixture
def manifest():
    return json.loads(EXAMPLE.read_text())


def validate(value, *, policy=POLICY, now=NOW):
    return validate_corpus_manifest(json.dumps(value), policy=policy, now=now)


def set_field(value, path, replacement):
    current = value
    for name in path[:-1]:
        current = current[name]
    current[path[-1]] = replacement


def test_synthetic_example_preserves_source_and_evaluator_provenance(manifest):
    result = validate(manifest)
    assert result.evidence_class == "synthetic"
    workflows = json.loads((ROOT / "contracts/fixtures/workflows.json").read_text())["workflows"]
    by_id = {workflow["id"]: workflow["task"] for workflow in workflows}
    for task in result.tasks:
        original = by_id[task.workflow_id]
        source = json.dumps(original["files"], sort_keys=True, separators=(",", ":")).encode()
        assert task.source.artifact.sha256 == hashlib.sha256(source).hexdigest()
        evaluator = {
            "files": original["evaluator_files"],
            "command": original["evaluator_command"],
            "image": original["image"],
        }
        content = json.dumps(evaluator, sort_keys=True, separators=(",", ":")).encode()
        assert task.evaluator.artifact.sha256 == hashlib.sha256(content).hexdigest()
        assert (
            task.evaluator.command_sha256
            == hashlib.sha256(original["evaluator_command"].encode()).hexdigest()
        )
        assert task.evaluator.image_digest == original["image"].split("@sha256:")[1]
        assert task.permission.rights_owner_id == "synthetic-rights-owner"
    assert result.retention.owner_id == "synthetic-retention-owner"
    assert result.storage_owner_id == "synthetic-storage-owner"
    assert result.publication.raw_content == "forbidden"


def test_published_json_schema_matches_parser():
    schema = json.loads((ROOT / "contracts/corpus-manifest.v1.schema.json").read_text())
    for annotation in ("$schema", "$id", "description"):
        schema.pop(annotation)
    assert schema == CorpusManifest.model_json_schema()


@pytest.mark.parametrize("field", ["permission", "source", "evaluator", "run_ids"])
def test_missing_permission_or_provenance_is_rejected(manifest, field):
    del manifest["tasks"][0][field]
    with pytest.raises(CorpusManifestError, match="^invalid-manifest$"):
        validate(manifest)


@pytest.mark.parametrize(
    "path,value",
    [
        (("tasks", 0, "permission", "status"), "pending"),
        (("tasks", 0, "permission", "rights_owner_id"), ""),
        (("tasks", 0, "permission", "evidence", "sha256"), "not-a-hash"),
        (("tasks", 0, "source", "revision"), "main"),
        (("tasks", 0, "evaluator", "command_sha256"), "A" * 64),
        (("tasks", 0, "run_ids"), ["invalid-run"]),
        (("publication", "raw_content"), "allowed"),
        (("publication", "aggregates"), "automatic"),
        (("retention", "review_at"), "2026-11-19T00:00:00"),
        (("schema_version",), True),
        (("tasks", 0, "permission", "allowed_processors"), []),
    ],
)
def test_malformed_or_unsafe_contract_fields_are_rejected(manifest, path, value):
    set_field(manifest, path, value)
    with pytest.raises(CorpusManifestError, match="^invalid-manifest$"):
        validate(manifest)


@pytest.mark.parametrize(
    "path",
    ["../private", "/absolute", "a/../b", "a//b", "a\\b", "a/./b", "a\nsecret", "a\x00b", ".", ""],
)
def test_invalid_private_object_paths_are_rejected(manifest, path):
    manifest["tasks"][0]["source"]["artifact"]["path"] = path
    with pytest.raises(CorpusManifestError, match="^invalid-manifest$"):
        validate(manifest)


def test_duplicate_task_ids_are_rejected_before_admission(manifest):
    manifest["tasks"].append(copy.deepcopy(manifest["tasks"][0]))
    with pytest.raises(CorpusManifestError, match="^duplicate-task-id$"):
        validate(manifest)


@pytest.mark.parametrize("same_task", [True, False])
def test_duplicate_run_ids_are_rejected_within_and_across_tasks(manifest, same_task):
    run_id = manifest["tasks"][0]["run_ids"][0]
    manifest["tasks"][0 if same_task else 1]["run_ids"].append(run_id)
    with pytest.raises(CorpusManifestError, match="^duplicate-run-id$"):
        validate(manifest)


def test_expired_permission_rejects_new_use_at_exact_expiry(manifest):
    manifest["tasks"][0]["permission"]["valid_until"] = NOW.isoformat()
    with pytest.raises(CorpusManifestError, match="^permission-expired$"):
        validate(manifest)


def test_future_permission_rejects_early_use(manifest):
    manifest["tasks"][0]["permission"]["valid_from"] = (NOW + timedelta(seconds=1)).isoformat()
    with pytest.raises(CorpusManifestError, match="^permission-not-active$"):
        validate(manifest)


def test_retention_cannot_exceed_permission(manifest):
    manifest["tasks"][0]["permission"]["valid_until"] = "2026-12-01T00:00:00Z"
    with pytest.raises(CorpusManifestError, match="^retention-exceeds-permission$"):
        validate(manifest)


@pytest.mark.parametrize(
    "time,code",
    [
        (datetime(2026, 11, 19, tzinfo=UTC), "retention-review-overdue"),
        (datetime(2027, 1, 19, tzinfo=UTC), "retention-expired"),
    ],
)
def test_admission_rechecks_retention_at_reuse(manifest, time, code):
    validate(manifest)
    with pytest.raises(CorpusManifestError, match=f"^{code}$"):
        validate(manifest, now=time)


def test_manifest_cannot_approve_a_new_processor_or_storage_location(manifest):
    manifest["tasks"][0]["permission"]["allowed_processors"].append("unapproved-vendor")
    with pytest.raises(CorpusManifestError, match="^processor-not-approved$"):
        validate(manifest, policy=replace(POLICY, processor_id="unapproved-vendor"))
    manifest["storage_profile_id"] = "unapproved-storage"
    with pytest.raises(CorpusManifestError, match="^storage-not-approved$"):
        validate(manifest)


def test_approved_processor_still_needs_each_rights_holders_permission(manifest):
    manifest["tasks"][1]["permission"]["allowed_processors"] = ["different-account-region"]
    with pytest.raises(CorpusManifestError, match="^processor-not-permitted$"):
        validate(manifest)


def test_permission_purpose_cannot_be_silently_widened(manifest):
    with pytest.raises(CorpusManifestError, match="^purpose-mismatch$"):
        validate(manifest, policy=replace(POLICY, purpose="debugging"))
    manifest["tasks"][0]["permission"]["allowed_purposes"] = ["debugging"]
    with pytest.raises(CorpusManifestError, match="^purpose-not-permitted$"):
        validate(manifest)


def test_duplicate_json_members_are_rejected():
    raw = EXAMPLE.read_text().replace(
        '"schema_version": 1', '"schema_version": 2, "schema_version": 1'
    )
    with pytest.raises(CorpusManifestError, match="^invalid-manifest$"):
        validate_corpus_manifest(raw, policy=POLICY, now=NOW)


def test_bounds_and_safe_errors_do_not_echo_private_values(manifest):
    with pytest.raises(CorpusManifestError, match="^manifest-too-large$"):
        validate_corpus_manifest(b" " * (MAX_MANIFEST_BYTES + 1), policy=POLICY, now=NOW)
    manifest["tasks"][0]["task_id"] = "private customer content, must not be logged"
    with pytest.raises(CorpusManifestError) as error:
        validate(manifest)
    assert str(error.value) == "invalid-manifest"
    assert error.value.__suppress_context__ is True
    with pytest.raises(CorpusManifestError, match="^invalid-validation-time$"):
        validate(manifest, now=NOW.replace(tzinfo=None))


TIMESTAMP_PATHS = [
    ("created_at",),
    ("retention", "review_at"),
    ("retention", "delete_after"),
    *[
        ("tasks", index, "permission", field)
        for index in range(2)
        for field in ("approved_at", "valid_from", "valid_until")
    ],
]


def field_value(value, path):
    for part in path:
        value = value[part]
    return value


@pytest.mark.parametrize("path", TIMESTAMP_PATHS)
@pytest.mark.parametrize("multiplier", [1, 1000])
def test_epoch_strings_rejected_at_every_timestamp(manifest, path, multiplier):
    instant = datetime.fromisoformat(field_value(manifest, path).replace("Z", "+00:00"))
    set_field(manifest, path, str(int(instant.timestamp()) * multiplier))
    with pytest.raises(CorpusManifestError, match="^invalid-manifest$"):
        validate(manifest)


@pytest.mark.parametrize("path", TIMESTAMP_PATHS)
@pytest.mark.parametrize("offset", [timedelta(hours=5, minutes=45), timedelta(hours=-4)])
def test_numeric_offsets_preserve_every_timestamp_instant(manifest, path, offset):
    original = validate(manifest).model_dump(mode="json")
    instant = datetime.fromisoformat(field_value(manifest, path).replace("Z", "+00:00"))
    set_field(manifest, path, instant.astimezone(timezone(offset)).isoformat())
    parsed = validate(manifest).model_dump(mode="json")
    actual = datetime.fromisoformat(field_value(parsed, path).replace("Z", "+00:00"))
    expected = datetime.fromisoformat(field_value(original, path).replace("Z", "+00:00"))
    assert actual == expected


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-10-19 00:00:00Z",
        "2026-10-19T00:00Z",
        "2026-10-19T00:00:00+0000",
        "2026-10-19T00:00:00Z\n",
        "2026-10-19T00:00:00.1234567Z",
        "2026-10-19T00:00:60Z",
        "2026-10-19T24:00:00Z",
        "2026-02-30T00:00:00Z",
        "2026-10-19T00:00:00+24:00",
    ],
)
def test_timestamp_profile_rejects_ambiguous_or_unrepresentable_values(manifest, timestamp):
    manifest["created_at"] = timestamp
    with pytest.raises(CorpusManifestError, match="^invalid-manifest$"):
        validate(manifest)


@pytest.mark.parametrize("suffix", ["Z", "z", "+00:00", "-00:00"])
def test_fractional_seconds_and_case_variants_are_preserved(manifest, suffix):
    manifest["created_at"] = "2026-10-19t00:00:00.123456" + suffix
    assert validate(manifest).created_at == datetime(2026, 10, 19, microsecond=123456, tzinfo=UTC)


def test_native_datetime_model_round_trip_remains_supported(manifest):
    result = validate(manifest)
    assert CorpusManifest.model_validate(result.model_dump()) == result


def test_permission_expiry_with_offset_uses_exact_instant(manifest):
    manifest["tasks"][0]["permission"]["valid_until"] = "2026-10-19T17:45:00+05:45"
    with pytest.raises(CorpusManifestError, match="^permission-expired$"):
        validate(manifest)
