"""Independent fictional declarations; no rights, data or execution authority."""

import copy
import hashlib
import importlib
import json
import socket
import subprocess
import sys
import traceback
import tracemalloc
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from agent_rewind import public_corpus
from agent_rewind.corpus import (
    MAX_MANIFEST_BYTES,
    AdmissionPolicy,
    CorpusManifestError,
    PrivateObject,
    validate_corpus_manifest,
)
from agent_rewind.public_corpus import (
    PublicCandidateManifest,
    PublicDeclarationError,
    PublicDeclarationPolicy,
    validate_public_candidate_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "contracts/fixtures/public-corpus.synthetic.v2.json"
NOW = datetime(2026, 10, 19, 12, tzinfo=UTC)
ADMISSION = AdmissionPolicy(
    processor_id="synthetic-model-region-a-no-retention",
    approved_processors=frozenset({"synthetic-model-region-a-no-retention"}),
    approved_storage_profiles=frozenset({"synthetic-private-storage"}),
    purpose="independent-confirmation",
)


@pytest.fixture
def declaration():
    return json.loads(EXAMPLE.read_text())


def encode(value):
    return json.dumps(value, separators=(",", ":")).encode()


def policy_for(raw, now=NOW):
    return PublicDeclarationPolicy(
        admission=ADMISSION,
        reviewed_manifest_sha256=hashlib.sha256(raw).hexdigest(),
        approval_reference=PrivateObject(
            path="fictional/independent-decision.json", sha256="a" * 64
        ),
        rights_status="current",
        checked_at=now,
    )


def validate(value, *, now=NOW, policy=None):
    raw = encode(value)
    return validate_public_candidate_manifest(
        raw, policy=policy_for(raw, now) if policy is None else policy, now=now
    )


def set_field(value, path, replacement):
    for key in path[:-1]:
        value = value[key]
    value[path[-1]] = replacement


def refuses(code, raw, policy=None, now=NOW):
    if policy is None:
        policy = policy_for(raw if type(raw) is bytes else b"fictional", now)
    with pytest.raises(PublicDeclarationError) as caught:
        validate_public_candidate_manifest(raw, policy=policy, now=now)
    assert caught.value.code == code
    assert str(caught.value) == code
    return caught.value


def test_fictional_candidates_preserve_identity_without_becoming_recordings(declaration):
    result = validate(declaration)
    assert result.schema_version == 2
    assert result.record_kind == "pre-recording-candidates"
    assert result.phase == "offline-preparation"
    assert [c.candidate_id for c in result.candidates] == [
        "synthetic-candidate-1",
        "synthetic-candidate-2",
    ]
    assert [c.workflow_id for c in result.candidates] == [
        "manual-action-recovery",
        "automatic-intervention-evaluation",
    ]
    for index, candidate in enumerate(result.candidates, 1):
        row = f"synthetic supplied row {index}; no real dataset content".encode()
        assert candidate.row.sha256 == hashlib.sha256(row).hexdigest()
        assert (
            candidate.dataset.artifact.sha256
            == hashlib.sha256(b"synthetic public card; no upstream schema claim").hexdigest()
        )
        assert not hasattr(candidate, "run_ids")
    assert result.publication.raw_content == "forbidden"
    assert result.publication.aggregates == "separate-review-required"
    assert result.model_dump(mode="json") == declaration


def test_public_derived_label_is_declaration_only_and_requires_same_policy(declaration):
    declaration["evidence_class"] = "public-derived-declaration"
    assert validate(declaration).evidence_class == "public-derived-declaration"
    raw = encode(declaration)
    refuses("rights-missing", raw, replace(policy_for(raw), rights_status="missing"))


def test_published_candidate_schema_matches_model():
    schema = json.loads((ROOT / "contracts/public-corpus.v2.schema.json").read_text())
    for annotation in ("$schema", "$id", "description"):
        schema.pop(annotation)
    assert schema == PublicCandidateManifest.model_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["PublicCandidate"]["additionalProperties"] is False


def test_v1_bytes_and_entry_point_remain_independent(declaration):
    expected = [
        (
            "agent_rewind/corpus.py",
            "c2f30b0e533000a955b151adca6cb15a1fbcf89b417f57abac8baf9a8756fa60",
        ),
        (
            "contracts/corpus-manifest.v1.schema.json",
            "c3ddda7d7cc5da6dea4e204b894ef53dcf71dea15d88cd22bfd5a9b4bb9950c2",
        ),
    ]
    for path, digest in expected:
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    original = (ROOT / "contracts/fixtures/corpus-manifest.synthetic.json").read_bytes()
    assert validate_corpus_manifest(original, policy=ADMISSION, now=NOW).schema_version == 1
    refuses("unsupported-version", original)
    with pytest.raises(CorpusManifestError, match="^invalid-manifest$"):
        validate_corpus_manifest(encode(declaration), policy=ADMISSION, now=NOW)


@pytest.mark.parametrize("value", [None, True, "2", 2.0, [], {}])
def test_malformed_version_is_not_an_unsupported_integer(declaration, value):
    declaration["schema_version"] = value
    refuses("invalid-manifest", encode(declaration))


@pytest.mark.parametrize("version", [0, 1, 3, -1])
def test_well_typed_unknown_version_refuses_before_kind(declaration, version):
    declaration["schema_version"] = version
    del declaration["record_kind"]
    refuses("unsupported-version", encode(declaration))


@pytest.mark.parametrize("field", ["schema_version", "record_kind"])
def test_missing_discriminator_is_malformed(declaration, field):
    del declaration[field]
    refuses("invalid-manifest", encode(declaration))


@pytest.mark.parametrize("value", [None, 2, True, [], {}])
def test_malformed_kind_is_not_an_unsupported_string(declaration, value):
    declaration["record_kind"] = value
    refuses("invalid-manifest", encode(declaration))


@pytest.mark.parametrize("kind", ["recorded-entries", "", "native-recording"])
def test_no_recorded_public_variant_or_implicit_promotion(declaration, kind):
    declaration["record_kind"] = kind
    refuses("unsupported-record-kind", encode(declaration))


@pytest.mark.parametrize(
    "field",
    ["run_ids", "checkpoint_id", "event_chain_id", "recording_receipt", "branchable", "metadata"],
)
def test_unknown_native_or_extension_fields_are_never_ignored(declaration, field):
    declaration["candidates"][0][field] = "PRIVATE-CANARY"
    refuses("invalid-manifest", encode(declaration))


@pytest.mark.parametrize("scope", ["root", "candidate", "permission", "object"])
def test_duplicate_json_members_at_every_boundary_refuse(declaration, scope):
    raw = encode(declaration)
    needle = {
        "root": b'"schema_version":2',
        "candidate": b'"candidate_id":"synthetic-candidate-1"',
        "permission": b'"status":"approved"',
        "object": b'"path":"synthetic/public-card.json"',
    }[scope]
    assert needle in raw
    raw = raw.replace(needle, needle + b"," + needle, 1)
    refuses("invalid-manifest", raw)


@pytest.mark.parametrize(
    "raw",
    [
        None,
        2,
        bytearray(b"{}"),
        {},
        b"\xff",
        b"{",
        b"[]",
        b"null",
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":-Infinity}',
        '{"x":"\ud800"}',
    ],
)
def test_invalid_raw_values_have_fixed_diagnostics(raw):
    refuses("invalid-manifest", raw)


def test_non_utf8_json_is_not_autodetected(declaration):
    refuses("invalid-manifest", json.dumps(declaration).encode("utf-16"))


def test_duplicate_candidate_identity_refuses_all_entries(declaration):
    declaration["candidates"][1]["candidate_id"] = declaration["candidates"][0]["candidate_id"]
    refuses("duplicate-candidate-id", encode(declaration))


def test_duplicate_row_identity_cannot_hide_behind_path_alias(declaration):
    first, second = declaration["candidates"]
    second["row"] = {**first["row"], "path": "fictional/different-key.json"}
    assert first["candidate_id"] != second["candidate_id"]
    refuses("duplicate-row-identity", encode(declaration))


@pytest.mark.parametrize(
    "path,value",
    [
        (("phase",), "native-capture"),
        (("permission",), {}),
        (("candidates", 0, "source"), None),
        (("candidates", 0, "dataset", "revision"), "main"),
        (("candidates", 0, "evaluator", "image_digest"), "A" * 64),
        (("candidates", 0, "row", "path"), "../secret"),
        (("candidates", 0, "source_policy", "path"), "a//b"),
        (("candidates", 0, "source_policy", "path"), "/absolute"),
        (("candidates", 0, "permission", "allowed_processors"), []),
        (("candidates", 0, "permission", "allowed_purposes"), ["debugging", "debugging"]),
        (("publication", "raw_content"), "allowed"),
        (("storage_owner_id",), "unicode-\u2603"),
        (("candidates",), []),
    ],
)
def test_closed_fields_and_reference_shapes(declaration, path, value):
    set_field(declaration, path, value)
    refuses("invalid-manifest", encode(declaration))


@pytest.mark.parametrize("length", [80, 81])
def test_candidate_identifier_boundary(declaration, length):
    declaration["candidates"][0]["candidate_id"] = "x" * length
    if length == 80:
        validate(declaration)
    else:
        refuses("invalid-manifest", encode(declaration))


@pytest.mark.parametrize("length", [512, 513])
def test_reference_path_boundary(declaration, length):
    declaration["candidates"][0]["row"]["path"] = "x" * length
    if length == 512:
        validate(declaration)
    else:
        refuses("invalid-manifest", encode(declaration))


def test_exact_raw_byte_limit_and_one_over(declaration):
    raw = encode(declaration)
    raw += b" " * (MAX_MANIFEST_BYTES - len(raw))
    assert len(raw) == MAX_MANIFEST_BYTES
    validate_public_candidate_manifest(raw, policy=policy_for(raw), now=NOW)
    refuses("manifest-too-large", raw + b" ")


def test_structural_candidate_count_and_transport_limit_are_distinct(declaration):
    candidate = declaration["candidates"][0]
    declaration["candidates"] = [
        {
            **copy.deepcopy(candidate),
            "candidate_id": f"candidate-{index}",
            "row": {"path": f"row-{index}", "sha256": f"{index:064x}"},
        }
        for index in range(1000)
    ]
    assert len(PublicCandidateManifest.model_validate(declaration).candidates) == 1000
    assert len(encode(declaration)) > MAX_MANIFEST_BYTES
    refuses("manifest-too-large", encode(declaration))
    declaration["candidates"].append(copy.deepcopy(candidate))
    with pytest.raises(ValidationError):
        PublicCandidateManifest.model_validate(declaration)


@pytest.mark.parametrize(
    "field,value",
    [
        ("admission", None),
        ("reviewed_manifest_sha256", "X" * 64),
        ("reviewed_manifest_sha256", None),
        ("approval_reference", {"path": "x", "sha256": "a" * 64}),
        ("rights_status", "approved"),
        ("rights_status", None),
        ("checked_at", NOW.replace(tzinfo=None)),
        ("checked_at", datetime.min.replace(tzinfo=timezone(timedelta(hours=1)))),
    ],
)
def test_policy_shape_is_revalidated_each_time(declaration, field, value):
    raw = encode(declaration)
    refuses("invalid-policy", raw, replace(policy_for(raw), **{field: value}))


@pytest.mark.parametrize(
    "field,value",
    [
        ("processor_id", "bad account"),
        ("approved_processors", {"synthetic-model-region-a-no-retention"}),
        ("approved_processors", frozenset()),
        ("approved_processors", frozenset({1})),
        ("approved_storage_profiles", "synthetic-private-storage"),
        ("approved_storage_profiles", frozenset({"a/b"})),
        ("purpose", "other"),
    ],
)
def test_nested_admission_policy_is_not_trusted_by_instance_type(declaration, field, value):
    raw = encode(declaration)
    policy = replace(policy_for(raw), admission=replace(ADMISSION, **{field: value}))
    refuses("invalid-policy", raw, policy)


@pytest.mark.parametrize("field", ["approved_processors", "approved_storage_profiles"])
@pytest.mark.parametrize("count", [32, 33])
def test_policy_allowlist_bounds(declaration, field, count):
    raw = encode(declaration)
    first = (
        ADMISSION.processor_id if field == "approved_processors" else "synthetic-private-storage"
    )
    values = frozenset([first, *(f"profile-{index}" for index in range(count - 1))])
    policy = replace(policy_for(raw), admission=replace(ADMISSION, **{field: values}))
    if count == 32:
        validate_public_candidate_manifest(raw, policy=policy, now=NOW)
    else:
        refuses("invalid-policy", raw, policy)


@pytest.mark.parametrize(
    "shape", ["mutated-path", "mutated-digest", "constructed", "missing", "extra"]
)
def test_current_approval_reference_fields_are_freshly_validated(declaration, shape):
    raw = encode(declaration)
    reference = PrivateObject(path="fictional/approval", sha256="a" * 64)
    if shape == "mutated-path":
        reference.path = "../PRIVATE-CANARY"
    elif shape == "mutated-digest":
        reference.sha256 = "PRIVATE-CANARY"
    elif shape == "constructed":
        reference = PrivateObject.model_construct(path=None, sha256="a" * 64)
    elif shape == "missing":
        reference = PrivateObject.model_construct(sha256="a" * 64)
    else:
        reference.__dict__["unexpected"] = "PRIVATE-CANARY"
    error = refuses("invalid-policy", raw, replace(policy_for(raw), approval_reference=reference))
    assert error.__suppress_context__ is True
    assert error.__cause__ is None
    assert "PRIVATE-CANARY" not in "".join(traceback.format_exception(error))


@pytest.mark.parametrize(
    "now",
    [
        None,
        "now",
        datetime(2026, 10, 19),
        datetime.min.replace(tzinfo=timezone(timedelta(hours=1))),
    ],
)
def test_invalid_now_precedes_malformed_policy_and_document(now):
    refuses("invalid-validation-time", None, policy=None, now=now)


@pytest.mark.parametrize("value", [None, {}, ADMISSION])
def test_policy_record_type_is_not_duck_typed(declaration, value):
    raw = encode(declaration)
    with pytest.raises(PublicDeclarationError, match="^invalid-policy$"):
        validate_public_candidate_manifest(raw, policy=value, now=NOW)


def test_equivalent_offsets_compare_as_instants(declaration):
    raw = encode(declaration)
    checked = NOW.astimezone(timezone(timedelta(hours=5, minutes=30)))
    validate_public_candidate_manifest(
        raw, policy=replace(policy_for(raw), checked_at=checked), now=NOW
    )


def test_same_timezone_fold_instants_are_not_equal_policy_snapshots(declaration):
    raw = encode(declaration)
    zone = ZoneInfo("America/New_York")
    earlier = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=0)
    later = earlier.replace(fold=1)
    assert earlier == later and earlier.astimezone(UTC) != later.astimezone(UTC)
    refuses("policy-not-current", raw, policy_for(raw, earlier), later)
    validate_public_candidate_manifest(raw, policy=policy_for(raw, later), now=later)


@pytest.mark.parametrize(
    "status,code", [("missing", "rights-missing"), ("revoked", "rights-revoked")]
)
def test_current_authority_is_separate_from_declared_approval(declaration, status, code):
    raw = encode(declaration)
    refuses(code, raw, replace(policy_for(raw), rights_status=status))


def test_reuse_and_raw_byte_changes_need_fresh_independent_policy(declaration):
    raw = encode(declaration)
    trusted = policy_for(raw)
    validate_public_candidate_manifest(raw, policy=trusted, now=NOW)
    refuses("policy-not-current", raw, trusted, NOW + timedelta(microseconds=1))
    refuses("declaration-not-reviewed", raw + b" ", trusted)
    declaration["candidates"][0]["row"]["sha256"] = "b" * 64
    refuses("declaration-not-reviewed", encode(declaration), trusted)
    declaration["approved"] = True
    refuses("invalid-manifest", encode(declaration), trusted)


TIMESTAMPS = [
    ("created_at",),
    ("retention", "review_at"),
    ("retention", "delete_after"),
    *(
        ("candidates", index, "permission", field)
        for index in range(2)
        for field in ("approved_at", "valid_from", "valid_until")
    ),
]


@pytest.mark.parametrize("path", TIMESTAMPS)
@pytest.mark.parametrize("value", ["1792411200", "2026-02-30T00:00:00Z", "2026-10-19T00:00:00"])
def test_every_timestamp_position_preserves_wire_profile(declaration, path, value):
    set_field(declaration, path, value)
    refuses("invalid-manifest", encode(declaration))


@pytest.mark.parametrize(
    "path,value,code",
    [
        (("created_at",), "2026-10-19T12:00:00.000001Z", "manifest-from-future"),
        (("retention", "review_at"), NOW.isoformat(), "retention-review-overdue"),
        (
            ("candidates", 0, "permission", "approved_at"),
            "2026-10-19T12:00:00.000001Z",
            "permission-not-active",
        ),
        (
            ("candidates", 0, "permission", "valid_from"),
            "2026-10-19T12:00:00.000001Z",
            "permission-not-active",
        ),
        (
            ("candidates", 0, "permission", "valid_until"),
            "2026-10-19T13:00:00+01:00",
            "permission-expired",
        ),
        (
            ("candidates", 0, "permission", "valid_until"),
            "2026-12-01T00:00:00Z",
            "retention-exceeds-permission",
        ),
        (("storage_profile_id",), "other-storage", "storage-not-approved"),
        (("purpose",), "debugging", "purpose-mismatch"),
        (
            ("candidates", 1, "permission", "allowed_processors"),
            ["other-account"],
            "processor-not-permitted",
        ),
        (
            ("candidates", 1, "permission", "allowed_purposes"),
            ["debugging"],
            "purpose-not-permitted",
        ),
    ],
)
def test_current_policy_and_permission_boundaries(declaration, path, value, code):
    set_field(declaration, path, value)
    refuses(code, encode(declaration))


def test_expired_retention_and_unapproved_requested_processor(declaration):
    later = datetime(2027, 1, 19, tzinfo=UTC)
    refuses("retention-expired", encode(declaration), now=later)
    raw = encode(declaration)
    policy = replace(policy_for(raw), admission=replace(ADMISSION, processor_id="unapproved"))
    refuses("processor-not-approved", raw, policy)


def test_unrepresentable_declared_utc_instant_is_sanitized(declaration):
    declaration["created_at"] = "0001-01-01T00:00:00+01:00"
    refuses("invalid-manifest", encode(declaration))


def test_private_model_diagnostics_do_not_escape(declaration):
    declaration["candidates"][0]["row"]["path"] = "../PRIVATE-CANARY"
    error = refuses("invalid-manifest", encode(declaration))
    assert error.__suppress_context__ is True and error.__cause__ is None
    assert "PRIVATE-CANARY" not in str(error) + repr(error)
    assert "PRIVATE-CANARY" not in "".join(traceback.format_exception(error))


@pytest.mark.parametrize(
    "error", [KeyboardInterrupt("PRIVATE-CANARY"), SystemExit("PRIVATE-CANARY")]
)
def test_parser_interrupt_keeps_original_identity(declaration, monkeypatch, error):
    raw = encode(declaration)
    policy = policy_for(raw)

    def interrupted(*args, **kwargs):
        raise error

    monkeypatch.setattr(public_corpus.json, "loads", interrupted)
    with pytest.raises(type(error)) as caught:
        validate_public_candidate_manifest(raw, policy=policy, now=NOW)
    assert caught.value is error


def test_clock_interrupt_is_not_a_validation_refusal(declaration):
    error = KeyboardInterrupt("PRIVATE-CANARY")

    class InterruptedZone(tzinfo):
        def utcoffset(self, value):
            raise error

    with pytest.raises(KeyboardInterrupt) as caught:
        validate_public_candidate_manifest(
            encode(declaration),
            policy=policy_for(encode(declaration)),
            now=datetime(2026, 10, 19, tzinfo=InterruptedZone()),
        )
    assert caught.value is error


def test_validation_has_no_io_or_dispatch_path(declaration, monkeypatch):
    raw = encode(declaration)
    trusted = policy_for(raw)

    def denied(*args, **kwargs):
        pytest.fail("Unexpected I/O or dispatch")

    with monkeypatch.context() as blocked:
        blocked.setattr("builtins.open", denied)
        blocked.setattr(Path, "open", denied)
        blocked.setattr(socket, "socket", denied)
        blocked.setattr(subprocess, "Popen", denied)
        blocked.setattr(importlib, "import_module", denied)
        result = validate_public_candidate_manifest(raw, policy=trusted, now=NOW)
    assert result.phase == "offline-preparation"


def test_already_oversized_text_refuses_before_a_second_large_allocation(tmp_path, record_property):
    # Keep allocation measurement out of the pytest process and any caller tracing session.
    tracing = (tracemalloc.is_tracing(), tracemalloc.get_traceback_limit())
    script = """
import json
import sys
import tracemalloc
from datetime import UTC, datetime
sys.path.insert(0, sys.argv[1])
from agent_rewind.corpus import MAX_MANIFEST_BYTES, AdmissionPolicy, PrivateObject
from agent_rewind.public_corpus import (
    PublicDeclarationError, PublicDeclarationPolicy, validate_public_candidate_manifest,
)
now = datetime(2026, 10, 19, 12, tzinfo=UTC)
policy = PublicDeclarationPolicy(
    AdmissionPolicy("p", frozenset({"p"}), frozenset({"s"}), "debugging"),
    "0" * 64, PrivateObject(path="approval", sha256="0" * 64), "current", now,
)
raw = "x" * (8 * MAX_MANIFEST_BYTES)
tracemalloc.start()
tracemalloc.reset_peak()
before = tracemalloc.get_traced_memory()[0]
try:
    try:
        validate_public_candidate_manifest(raw, policy=policy, now=now)
    except PublicDeclarationError as error:
        code = error.code
    else:
        raise AssertionError("Oversized declaration accepted")
    additional_peak = tracemalloc.get_traced_memory()[1] - before
finally:
    tracemalloc.stop()
print(json.dumps({
    "code": code, "input_characters": len(raw), "additional_peak": additional_peak,
}))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", script, str(ROOT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    assert (tracemalloc.is_tracing(), tracemalloc.get_traceback_limit()) == tracing
    receipt = json.loads(result.stdout)
    assert receipt["code"] == "manifest-too-large"
    assert receipt["input_characters"] == 8 * MAX_MANIFEST_BYTES
    # A full UTF-8 copy of the already oversized input would exceed this generous cap.
    assert 0 <= receipt["additional_peak"] < MAX_MANIFEST_BYTES
    record_property("oversized_text_allocation", json.dumps(receipt, sort_keys=True))


def test_character_precheck_keeps_the_exact_utf8_byte_limit():
    raw = '"' + "é" * (MAX_MANIFEST_BYTES // 2) + '"'
    assert len(raw) < MAX_MANIFEST_BYTES < len(raw.encode("utf-8"))
    refuses("manifest-too-large", raw)


@pytest.mark.parametrize("boundary", ["now", "checked_at"])
def test_recursive_timezone_is_a_safe_boundary_refusal(declaration, boundary):
    class RecursiveZone(tzinfo):
        def utcoffset(self, value):
            return value.utcoffset()

    raw = encode(declaration)
    recursive = NOW.replace(tzinfo=RecursiveZone())
    trusted = policy_for(raw)
    if boundary == "now":
        error = refuses("invalid-validation-time", raw, trusted, recursive)
    else:
        error = refuses("invalid-policy", raw, replace(trusted, checked_at=recursive))
    assert error.__cause__ is None and error.__suppress_context__ is True
    assert "RecursionError" not in "".join(traceback.format_exception(error))
