"""Fictional qualification inputs; no acquired rows or evaluator execution."""

import copy
import hashlib
import json
import socket
import subprocess
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agent_rewind import swe_rebench as normalizer
from agent_rewind.corpus import AdmissionPolicy, PrivateObject
from agent_rewind.public_corpus import PublicDeclarationError, PublicDeclarationPolicy
from agent_rewind.swe_rebench import (
    MAX_BATCH_BYTES,
    MAX_FILES,
    MAX_ROW_BYTES,
    NORMALIZER_PROFILE,
    SYNTHETIC_PROFILE,
    SYNTHETIC_SCHEMA_SHA256,
    NormalizationError,
    NormalizationPolicy,
    QualificationReceipt,
    SuppliedRow,
    normalize_swe_rebench,
)

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 30, 12, tzinfo=UTC)
IMPLEMENTATION = "b" * 64
CANARY = "PRIVATE-ANSWER-CANARY-48392"


def encode(value):
    # Independent fixture encoder: never call the production output/digest helpers.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def row_value():
    return {
        "profile": "swe-rebench-python-synthetic-v1",
        "language": "python",
        "synthetic_created_at": "2026-10-29T00:00:00Z",
        "state_kind": "file-tree",
        "base_revision": "1" * 40,
        "instruction": "Make the fictional addition function return a sum.",
        "base_files": {"src/add.py": "def add(a, b):\n    return a - b\n"},
        "evaluator": {
            "reference_patch": CANARY + "-patch",
            "test_files": {"private/test_add.py": CANARY + "-test"},
            "command": "python private/test_add.py",
            "image_digest": "2" * 64,
        },
        "private_metadata": {
            "repository": CANARY + "-repository",
            "instance": CANARY + "-instance",
            "pull_request_text": CANARY + "-pull-request",
            "labels": ["fictional"],
            "logs": CANARY + "-logs",
            "image_name": CANARY + "-image",
        },
    }


def make_case(value=None, *, raw=None, candidates=1):
    value = row_value() if value is None else copy.deepcopy(value)
    raw = encode(value) if raw is None else raw
    declaration = json.loads(
        (ROOT / "contracts/fixtures/public-corpus.synthetic.v2.json").read_text()
    )
    template = declaration["candidates"][0]
    declaration["created_at"] = "2026-10-29T00:00:00Z"
    declaration["candidates"] = []
    expected_inference = encode(
        {
            "profile": "answer-blind-inference-v1",
            "instruction": value["instruction"],
            "files": value["base_files"],
        }
    )
    expected_evaluator = encode(value["evaluator"])
    for index in range(candidates):
        candidate = copy.deepcopy(template)
        candidate["candidate_id"] = f"fictional-{index}"
        candidate["row"]["sha256"] = digest(raw if index == 0 else raw + b" " * index)
        candidate["source"]["revision"] = value["base_revision"]
        candidate["source"]["artifact"]["sha256"] = digest(encode({"files": value["base_files"]}))
        candidate["evaluator"]["artifact"]["sha256"] = digest(expected_evaluator)
        candidate["evaluator"]["command_sha256"] = digest(value["evaluator"]["command"].encode())
        candidate["evaluator"]["image_digest"] = value["evaluator"]["image_digest"]
        declaration["candidates"].append(candidate)
    declared = encode(declaration)
    receipts = []
    rows = []
    for index, candidate in enumerate(declaration["candidates"]):
        supplied = raw if index == 0 else raw + b" " * index
        rows.append(SuppliedRow(candidate["candidate_id"], supplied))
        # Bind independent expected bytes directly, never derive them from normalize().
        receipts.append(
            QualificationReceipt(
                receipt_profile="swe-rebench-qualification-synthetic-v1",
                candidate_id=candidate["candidate_id"],
                declaration_sha256=digest(declared),
                row_sha256=digest(supplied),
                dataset_revision=candidate["dataset"]["revision"],
                card_sha256=candidate["dataset"]["artifact"]["sha256"],
                source_revision=candidate["source"]["revision"],
                source_sha256=candidate["source"]["artifact"]["sha256"],
                field_policy_sha256=candidate["source_policy"]["sha256"],
                schema_sha256=SYNTHETIC_SCHEMA_SHA256,
                normalizer_profile=NORMALIZER_PROFILE,
                normalizer_sha256=IMPLEMENTATION,
                processor_id="synthetic-model-region-a-no-retention",
                purpose="independent-confirmation",
                inference_sha256=digest(expected_inference),
                evaluator_revision=candidate["evaluator"]["revision"],
                evaluator_sha256=digest(expected_evaluator),
                command_sha256=candidate["evaluator"]["command_sha256"],
                image_digest=candidate["evaluator"]["image_digest"],
                evidence=PrivateObject(
                    path=f"fictional/qualification-{index}.json", sha256="3" * 64
                ),
                issued_at=NOW - timedelta(days=1),
                expires_at=NOW + timedelta(days=1),
                original=("fail",) * 3,
                reference=("pass",) * 3,
                invalid=("fail", "rejected", "fail"),
                tamper=("rejected",) * 3,
                answer_blind_context=True,
                supported_state=True,
            )
        )
    admission = AdmissionPolicy(
        processor_id="synthetic-model-region-a-no-retention",
        approved_processors=frozenset({"synthetic-model-region-a-no-retention"}),
        approved_storage_profiles=frozenset({"synthetic-private-storage"}),
        purpose="independent-confirmation",
    )
    policy = NormalizationPolicy(
        declaration=PublicDeclarationPolicy(
            admission=admission,
            reviewed_manifest_sha256=digest(declared),
            approval_reference=PrivateObject(path="fictional/approval.json", sha256="4" * 64),
            rights_status="current",
            checked_at=NOW,
        ),
        normalizer_sha256=IMPLEMENTATION,
        reviewed_receipts=frozenset(digest(encode(r.model_dump(mode="json"))) for r in receipts),
        checked_at=NOW,
    )
    return declared, tuple(rows), policy, tuple(receipts), expected_inference, expected_evaluator


def run(case, *, rows=None, policy=None, receipts=None):
    declaration, original_rows, original_policy, original_receipts, _, _ = case
    return normalize_swe_rebench(
        declaration,
        original_rows if rows is None else rows,
        policy=original_policy if policy is None else policy,
        qualifications=original_receipts if receipts is None else receipts,
        now=NOW,
    )


def reviewed_policy(case, receipts):
    return replace(
        case[2],
        reviewed_receipts=frozenset(digest(encode(r.model_dump(mode="json"))) for r in receipts),
    )


def assert_refusal(decision, status, code):
    assert decision.status == status
    assert decision.code == code
    assert decision.inference is decision.evaluator is decision.lineage is None
    assert CANARY not in repr(decision)


def test_independent_golden_binding_separates_inference_evaluator_and_private_lineage():
    case = make_case()
    result = run(case)
    assert result.counts == {"declared": 1, "next-gate": 1, "quarantine": 0, "unsupported": 0}
    decision = result.decisions[0]
    assert decision.code == "qualified-synthetic"
    assert decision.inference.encoded() == case[4]
    assert decision.inference.cache_identity == digest(case[4])
    assert decision.evaluator.encoded() == case[5]
    assert CANARY.encode() not in decision.inference.encoded()
    assert CANARY.encode() in decision.evaluator.encoded()
    assert decision.lineage.candidate_id == "fictional-0"
    assert decision.lineage.row_sha256 == digest(case[1][0].raw)
    assert decision.lineage.declaration_sha256 == digest(case[0])
    assert decision.lineage.receipt_sha256 in case[2].reviewed_receipts
    assert not hasattr(decision, "run_id")
    assert not hasattr(decision.inference, "candidate_id")


@pytest.mark.parametrize(
    "field",
    [
        "repository",
        "instance",
        "pull_request_text",
        "labels",
        "logs",
        "image_name",
        "reference_patch",
        "test_files",
        "command",
        "image_digest",
    ],
)
def test_separately_qualified_hidden_variants_have_identical_inference_bytes_and_cache(field):
    first = make_case()
    value = row_value()
    if field in value["private_metadata"]:
        value["private_metadata"][field] = ["other"] if field == "labels" else CANARY + "-variant"
    else:
        value["evaluator"][field] = {
            "reference_patch": CANARY + "-other-patch",
            "test_files": {"private/different.py": CANARY + "-other-test"},
            "command": "python private/different.py",
            "image_digest": "f" * 64,
        }[field]
    second = make_case(value)
    a, b = run(first).decisions[0], run(second).decisions[0]
    assert a.status == b.status == "next-gate"
    assert a.lineage.row_sha256 != b.lineage.row_sha256
    assert a.lineage.declaration_sha256 != b.lineage.declaration_sha256
    assert a.inference.encoded() == b.inference.encoded() == first[4]
    assert a.inference.cache_identity == b.inference.cache_identity


def test_private_candidate_identity_is_never_an_inference_salt():
    case = make_case(candidates=2)
    result = run(case)
    first, second = result.decisions
    assert first.candidate_id != second.candidate_id
    assert first.lineage != second.lineage
    assert first.inference.encoded() == second.inference.encoded()
    assert first.inference.cache_identity == second.inference.cache_identity


def test_changed_allowed_context_changes_inference_identity():
    original = run(make_case()).decisions[0]
    value = row_value()
    value["base_files"]["src/add.py"] += "# additional admitted context\n"
    changed = run(make_case(value)).decisions[0]
    assert changed.status == "next-gate"
    assert changed.inference.cache_identity != original.inference.cache_identity


def test_hidden_mutation_with_stale_receipt_is_not_qualification():
    case = make_case()
    value = row_value()
    value["private_metadata"]["logs"] = CANARY + "-mutated"
    result = run(case, rows=(SuppliedRow("fictional-0", encode(value)),))
    assert_refusal(result.decisions[0], "quarantine", "binding-mismatch")


@pytest.mark.parametrize(
    "field",
    [
        "declaration_sha256",
        "row_sha256",
        "dataset_revision",
        "card_sha256",
        "source_revision",
        "source_sha256",
        "field_policy_sha256",
        "schema_sha256",
        "normalizer_sha256",
        "inference_sha256",
        "evaluator_revision",
        "evaluator_sha256",
        "command_sha256",
        "image_digest",
        "processor_id",
        "purpose",
    ],
)
def test_each_independent_binding_is_checked_even_when_receipt_is_reviewed(field):
    case = make_case()
    replacement = "f" * 64
    if field in {"dataset_revision", "source_revision", "evaluator_revision"}:
        replacement = "f" * 40
    elif field == "processor_id":
        replacement = "different-processor"
    elif field == "purpose":
        replacement = "debugging"
    changed = case[3][0].model_copy(update={field: replacement})
    receipts = (changed,)
    result = run(case, receipts=receipts, policy=reviewed_policy(case, receipts))
    assert_refusal(result.decisions[0], "quarantine", "binding-mismatch")


@pytest.mark.parametrize(
    "field,outcome",
    [
        ("original", "pass"),
        ("reference", "fail"),
        ("invalid", "pass"),
        ("tamper", "pass"),
        ("original", "unknown"),
        ("reference", "error"),
        ("invalid", "unknown"),
        ("tamper", "error"),
    ],
)
def test_failed_or_missing_control_evidence_quarantines_without_dropping_candidate(field, outcome):
    case = make_case()
    receipts = (case[3][0].model_copy(update={field: (outcome,) * 3}),)
    result = run(case, receipts=receipts, policy=reviewed_policy(case, receipts))
    assert result.counts["declared"] == result.counts["quarantine"] == 1
    assert_refusal(result.decisions[0], "quarantine", "qualification-controls-failed")


@pytest.mark.parametrize(
    "field,code",
    [
        ("answer_blind_context", "context-not-qualified"),
        ("supported_state", "state-not-qualified"),
    ],
)
def test_bound_receipt_is_not_a_substitute_for_independent_content_review(field, code):
    case = make_case()
    receipts = (case[3][0].model_copy(update={field: False}),)
    assert_refusal(
        run(case, receipts=receipts, policy=reviewed_policy(case, receipts)).decisions[0],
        "quarantine",
        code,
    )


def test_absent_receipt_or_unreviewed_receipt_cannot_approve_itself():
    case = make_case()
    assert_refusal(run(case, receipts=()).decisions[0], "quarantine", "missing-qualification")
    policy = replace(case[2], reviewed_receipts=frozenset())
    assert_refusal(
        run(case, policy=policy).decisions[0], "quarantine", "qualification-not-reviewed"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("issued_at", NOW + timedelta(microseconds=1)),
        ("expires_at", NOW),
        ("expires_at", NOW - timedelta(seconds=1)),
    ],
)
def test_qualification_time_is_current_and_expiry_is_exclusive(field, value):
    case = make_case()
    receipts = (case[3][0].model_copy(update={field: value}),)
    assert_refusal(
        run(case, receipts=receipts, policy=reviewed_policy(case, receipts)).decisions[0],
        "quarantine",
        "qualification-not-current",
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("issued_at", None),
        ("issued_at", NOW.replace(tzinfo=None)),
        ("original", ("fail",) * 2),
        ("reference", ("pass",) * 33),
        ("answer_blind_context", 1),
        ("normalizer_profile", "self-declared"),
        ("schema_sha256", None),
    ],
)
def test_constructed_or_mutated_receipt_values_are_revalidated(field, value):
    case = make_case()
    receipt = case[3][0].model_copy(update={field: value})
    assert_refusal(
        run(case, receipts=(receipt,)).decisions[0], "quarantine", "invalid-qualification"
    )


def test_mutated_nested_private_evidence_is_revalidated():
    case = make_case()
    case[3][0].evidence.path = "../escape"
    assert_refusal(run(case).decisions[0], "quarantine", "invalid-qualification")


@pytest.mark.parametrize("status", ["revoked", "missing"])
def test_current_pca1_rights_are_required_on_every_call(status):
    case = make_case()
    policy = replace(case[2], declaration=replace(case[2].declaration, rights_status=status))
    with pytest.raises(PublicDeclarationError, match="^rights-" + status + "$"):
        run(case, policy=policy)


@pytest.mark.parametrize(
    "field,value",
    [
        ("normalizer_sha256", "bad"),
        ("normalizer_sha256", None),
        ("reviewed_receipts", {"a" * 64}),
        ("reviewed_receipts", frozenset({"bad"})),
        ("checked_at", NOW - timedelta(microseconds=1)),
        ("checked_at", NOW.replace(tzinfo=None)),
    ],
)
def test_caller_policy_cannot_be_supplied_or_stale_untrusted_data(field, value):
    case = make_case()
    with pytest.raises(NormalizationError, match="^invalid-policy$"):
        run(case, policy=replace(case[2], **{field: value}))


@pytest.mark.parametrize(
    "raw",
    [
        None,
        {},
        bytearray(b"{}"),
        True,
        b"\xff",
        b"[]",
        b"null",
        b"{",
        b'{"profile":NaN}',
        b'{"profile":Infinity}',
        b'{"profile":-Infinity}',
        '{"profile":"\ud800"}',
    ],
)
def test_untrusted_raw_types_and_json_have_safe_denominator_outcomes(raw):
    case = make_case()
    decision = run(case, rows=(SuppliedRow("fictional-0", raw),)).decisions[0]
    assert_refusal(decision, "quarantine", "invalid-row")


@pytest.mark.parametrize("where", ["root", "evaluator", "metadata", "files"])
def test_duplicate_json_members_are_rejected_at_every_depth(where):
    case = make_case()
    needle = {
        "root": b'"language":"python"',
        "evaluator": b'"image_digest":"' + b"2" * 64 + b'"',
        "metadata": b'"labels":["fictional"]',
        "files": b'"src/add.py":"def add(a, b):\\n    return a - b\\n"',
    }[where]
    raw = case[1][0].raw
    assert raw.count(needle) == 1
    raw = raw.replace(needle, needle + b"," + needle)
    assert_refusal(
        run(case, rows=(SuppliedRow("fictional-0", raw),)).decisions[0], "quarantine", "invalid-row"
    )


@pytest.mark.parametrize(
    "path",
    [
        ("unexpected",),
        ("created_at",),
        ("evaluator", "metadata"),
        ("private_metadata", "unknown"),
        ("base_files", "bad"),
    ],
)
def test_unknown_keys_and_wrong_file_shapes_refuse(path):
    case = make_case()
    value = row_value()
    if len(path) == 1:
        value[path[0]] = CANARY
    else:
        value[path[0]][path[1]] = None
    assert_refusal(
        run(case, rows=(SuppliedRow("fictional-0", encode(value)),)).decisions[0],
        "quarantine",
        "invalid-row",
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("instruction", None),
        ("instruction", 1),
        ("base_files", []),
        ("synthetic_created_at", "2026-10-29"),
        ("synthetic_created_at", 1793232000),
        ("synthetic_created_at", "2026-02-30T00:00:00Z"),
        ("synthetic_created_at", "0001-01-01T00:00:00+01:00"),
        ("instruction", "x" * 20001),
    ],
)
def test_null_type_and_timestamp_ambiguity_is_not_normalized(field, value):
    case = make_case()
    row = row_value()
    row[field] = value
    assert_refusal(
        run(case, rows=(SuppliedRow("fictional-0", encode(row)),)).decisions[0],
        "quarantine",
        "invalid-row",
    )


@pytest.mark.parametrize("path", ["../x", "/x", "a//b", "a/./b", ".", "a\\b", "a\x00b", "a\nb"])
def test_paths_are_not_resolved_normalized_or_aliased(path):
    case = make_case()
    value = row_value()
    value["base_files"] = {path: "fictional"}
    assert_refusal(
        run(case, rows=(SuppliedRow("fictional-0", encode(value)),)).decisions[0],
        "quarantine",
        "invalid-row",
    )


def test_private_evaluator_cannot_overlap_base_context():
    value = row_value()
    value["evaluator"]["test_files"] = {"src/add.py": CANARY}
    case = make_case(value)
    assert_refusal(run(case).decisions[0], "quarantine", "invalid-row")


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("profile", "upstream-unqualified", "unsupported-profile"),
        ("language", "javascript", "unsupported-language"),
        ("state_kind", "live-process", "unsupported-state"),
    ],
)
def test_unsupported_inputs_are_retained_without_truncation(field, value, code):
    case = make_case()
    row = row_value()
    row[field] = value
    assert_refusal(
        run(case, rows=(SuppliedRow("fictional-0", encode(row)),)).decisions[0], "unsupported", code
    )


def test_future_fictional_timestamp_is_not_interpreted_as_other_time():
    value = row_value()
    value["synthetic_created_at"] = "2026-10-30T12:00:00.000001Z"
    assert_refusal(run(make_case(value)).decisions[0], "quarantine", "future-row")


@pytest.mark.parametrize("count", [MAX_FILES, MAX_FILES + 1])
def test_combined_file_limit_keeps_all_paths_or_refuses(count):
    value = row_value()
    value["base_files"] = {f"src/{n}.py": "" for n in range(count - 1)}
    result = run(make_case(value)).decisions[0]
    if count == MAX_FILES:
        assert result.status == "next-gate"
        assert len(result.inference.files) == MAX_FILES - 1
        assert len(result.evaluator.test_files) == 1
    else:
        assert_refusal(result, "unsupported", "state-too-large")


def test_exact_raw_byte_bound_and_one_over_preserve_the_denominator():
    value = row_value()
    raw = encode(value)
    raw += b" " * (MAX_ROW_BYTES - len(raw))
    assert run(make_case(value, raw=raw)).decisions[0].status == "next-gate"
    case = make_case()
    result = run(case, rows=(SuppliedRow("fictional-0", raw + b" "),))
    assert result.counts == {"declared": 1, "next-gate": 0, "quarantine": 0, "unsupported": 1}
    assert_refusal(result.decisions[0], "unsupported", "batch-too-large")


def test_utf8_bytes_not_character_count_bound_batch_and_rows():
    case = make_case()
    raw = "é" * (MAX_BATCH_BYTES // 2 + 1)
    assert len(raw) < MAX_BATCH_BYTES < len(raw.encode())
    assert_refusal(
        run(case, rows=(SuppliedRow("fictional-0", raw),)).decisions[0],
        "unsupported",
        "batch-too-large",
    )


def test_batch_size_refuses_every_declared_candidate_without_partial_output():
    case = make_case(candidates=2)
    rows = tuple(SuppliedRow(r.candidate_id, b" " * (MAX_BATCH_BYTES // 2 + 1)) for r in case[1])
    result = run(case, rows=rows)
    assert result.counts == {"declared": 2, "next-gate": 0, "quarantine": 0, "unsupported": 2}
    assert all(d.code == "batch-too-large" for d in result.decisions)


def test_all_decisions_remain_in_declaration_order_despite_supplied_order():
    case = make_case(candidates=3)
    unsupported = row_value()
    unsupported["state_kind"] = "socket"
    rows = (SuppliedRow("fictional-2", encode(unsupported)), case[1][0])
    result = run(case, rows=rows)
    assert [d.candidate_id for d in result.decisions] == [
        "fictional-0",
        "fictional-1",
        "fictional-2",
    ]
    assert [d.status for d in result.decisions] == ["next-gate", "quarantine", "unsupported"]
    assert result.decisions[1].code == "missing-row"
    assert result.counts == {"declared": 3, "next-gate": 1, "quarantine": 1, "unsupported": 1}


@pytest.mark.parametrize("rows", ["duplicate", "extra", "list", "wrong"])
def test_batch_association_ambiguity_never_disappears_by_dict_overwrite(rows):
    case = make_case()
    supplied = {
        "duplicate": (case[1][0], case[1][0]),
        "extra": (case[1][0], SuppliedRow("undeclared", b"{}")),
        "list": list(case[1]),
        "wrong": ({},),
    }[rows]
    with pytest.raises(NormalizationError, match="^invalid-rows$"):
        run(case, rows=supplied)


@pytest.mark.parametrize("kind", ["duplicate", "extra", "list", "wrong"])
def test_receipt_association_ambiguity_refuses_the_entire_batch(kind):
    case = make_case()
    supplied = {
        "duplicate": (case[3][0], case[3][0]),
        "extra": (case[3][0].model_copy(update={"candidate_id": "undeclared"}),),
        "list": list(case[3]),
        "wrong": ({},),
    }[kind]
    with pytest.raises(NormalizationError, match="^invalid-qualifications$"):
        run(case, receipts=supplied)


def test_public_derived_declaration_is_not_actual_supported_source():
    case = make_case()
    declaration = json.loads(case[0])
    declaration["evidence_class"] = "public-derived-declaration"
    raw = encode(declaration)
    policy = replace(
        case[2], declaration=replace(case[2].declaration, reviewed_manifest_sha256=digest(raw))
    )
    with pytest.raises(NormalizationError, match="^synthetic-only$"):
        normalize_swe_rebench(raw, case[1], policy=policy, qualifications=case[3], now=NOW)


def test_normalization_performs_no_file_network_or_process_action(monkeypatch):
    case = make_case()

    def forbidden(*args, **kwargs):
        pytest.fail("Disconnected normalizer attempted external I/O or execution.")

    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    assert run(case).decisions[0].status == "next-gate"


def test_new_module_is_explicitly_packaged_without_changing_public_interfaces():
    policy = json.loads((ROOT / "scripts/distribution-files.json").read_text())
    assert policy["runtime"].count("agent_rewind/swe_rebench.py") == 1
    assert SYNTHETIC_PROFILE == "swe-rebench-python-synthetic-v1"
    assert not hasattr(normalizer, "qualify")
    assert not hasattr(normalizer, "Engine")
    assert digest((ROOT / "agent_rewind/corpus.py").read_bytes()) == (
        "c2f30b0e533000a955b151adca6cb15a1fbcf89b417f57abac8baf9a8756fa60"
    )


def test_wrong_receipt_object_is_rejected_without_accessing_its_properties():
    case = make_case()
    accesses = []

    class Untrusted:
        @property
        def candidate_id(self):
            accesses.append("candidate_id")
            raise RuntimeError(CANARY)

    with pytest.raises(NormalizationError, match="^invalid-qualifications$") as caught:
        run(case, receipts=(Untrusted(),))
    assert accesses == []
    assert CANARY not in str(caught.value)
    assert caught.value.__cause__ is None
