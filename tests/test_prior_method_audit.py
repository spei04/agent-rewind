"""Record integrity tests; no third-party algorithm execution or scientific validation."""

import copy
import json

import pytest

from scripts.check_prior_methods import load_record, validate


@pytest.fixture
def record():
    return copy.deepcopy(load_record())


def test_checked_record_is_complete_and_does_not_claim_reproduction(record):
    validate(record)
    assert {row["id"] for row in record["methods"]} == {"dover", "car", "reflect", "daaf"}
    assert all(row["reproduction"] == "not_executed" for row in record["methods"])


@pytest.mark.parametrize("index", range(4))
def test_every_method_requires_every_comparison_dimension(record, index):
    del record["methods"][index]["dimensions"]["oracle_access"]
    with pytest.raises(ValueError, match="dimensions: fields"):
        validate(record)


@pytest.mark.parametrize("index", range(4))
def test_available_and_unlocated_methods_cannot_claim_reproduction(record, index):
    record["methods"][index]["reproduction"] = "reproduced"
    with pytest.raises(ValueError, match="no baseline reproduced"):
        validate(record)


def test_unknown_attribute_still_requires_traceable_evidence(record):
    record["methods"][2]["dimensions"]["unknowns"]["evidence"] = ["invented-source"]
    with pytest.raises(ValueError, match="unknown reference"):
        validate(record)


def test_public_source_requires_matching_commit_evidence(record):
    record["methods"][0]["availability"]["commit"] = "a" * 40
    with pytest.raises(ValueError, match="matching pinned code"):
        validate(record)


def test_paper_version_cannot_drift_silently(record):
    record["methods"][0]["paper_version"] = "2512.06749v2"
    with pytest.raises(ValueError, match="method paper version"):
        validate(record)


@pytest.mark.parametrize(
    ("identity", "replacement", "message"),
    [
        ("dover-paper", "https://arxiv.org/html/2512.06749", "pin version"),
        (
            "dover-readme",
            "https://github.com/microsoft/ACV/blob/main/misc/DoVer/README.md",
            "pin commit",
        ),
        ("dover-tree", "https://api.github.com/repos/microsoft/ACV/git/trees/main", "pin object"),
        ("dover-paper", "https://example.invalid/paper", "primary HTTPS"),
    ],
)
def test_versioned_primary_source_link_shape(record, identity, replacement, message):
    source = next(row for row in record["evidence"] if row["id"] == identity)
    source["url"] = replacement
    with pytest.raises(ValueError, match=message):
        validate(record)


def test_duplicate_evidence_identity_refused(record):
    record["evidence"].append(copy.deepcopy(record["evidence"][0]))
    with pytest.raises(ValueError, match="duplicate id"):
        validate(record)


def test_duplicate_method_identity_refused(record):
    record["methods"].append(copy.deepcopy(record["methods"][0]))
    with pytest.raises(ValueError, match="duplicate id"):
        validate(record)


def test_unlocated_code_cannot_invent_commit_or_inspection(record):
    record["methods"][2]["availability"]["commit"] = "a" * 40
    with pytest.raises(ValueError, match="cannot invent a pin"):
        validate(record)
    record["methods"][2]["availability"]["commit"] = None
    record["methods"][2]["dimensions"]["checkpoint_state"]["status"] = "source_inspected"
    with pytest.raises(ValueError, match="unlocated code inspection"):
        validate(record)


def test_planned_license_cannot_become_inspected_license(record):
    record["methods"][2]["availability"]["license_status"] = "root_text_inspected"
    with pytest.raises(ValueError, match="cannot claim inspected license"):
        validate(record)


def test_license_declaration_is_not_license_text(record):
    record["methods"][1]["availability"]["license_status"] = "root_text_inspected"
    with pytest.raises(ValueError, match="license-text evidence"):
        validate(record)


def test_code_inspection_needs_code_not_only_paper(record):
    record["methods"][0]["dimensions"]["oracle_access"]["evidence"] = ["dover-paper"]
    with pytest.raises(ValueError, match="source inspection requires matching source"):
        validate(record)


@pytest.mark.parametrize(
    "key", ["third_party_execution", "paid_calls", "customer_data", "algorithm_implemented"]
)
def test_design_audit_cannot_claim_execution(record, key):
    record["scope"][key] = True
    with pytest.raises(ValueError, match="cannot authorize or claim execution"):
        validate(record)


def test_unreviewed_hypothesis_cannot_become_novelty_result(record):
    record["candidate"]["status"] = "novel_algorithm_proven"
    with pytest.raises(ValueError, match="candidate evidence limit"):
        validate(record)


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("authorized", True, "adapter authority"),
        ("confidence", "high", "adapter authority"),
        ("low_days", 0, "adapter effort"),
        ("high_days", 1, "adapter effort"),
        ("low_days", True, "adapter effort"),
        ("prerequisites", [], "adapter prerequisites"),
    ],
)
def test_followup_estimate_cannot_hide_authority_or_missing_dependencies(
    record, key, value, message
):
    record["adapter_estimates"][0][key] = value
    with pytest.raises(ValueError, match=message):
        validate(record)


def test_unknown_fields_do_not_silently_change_contract(record):
    record["approval"] = "runtime implementation approved"
    with pytest.raises(ValueError, match="record: fields"):
        validate(record)


def test_duplicate_json_field_is_rejected_before_overwrite(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"scope": {}, "scope": {"paid_calls": true}}')
    with pytest.raises(ValueError, match="duplicate JSON field"):
        load_record(path)


def test_record_size_bound(tmp_path):
    path = tmp_path / "oversize.json"
    path.write_text(json.dumps("x" * 262144))
    with pytest.raises(ValueError, match="record too large"):
        load_record(path)


def test_another_method_source_cannot_substitute_for_inspection(record):
    record["methods"][0]["dimensions"]["oracle_access"]["evidence"] = ["car-contrast"]
    with pytest.raises(ValueError, match="matching source evidence"):
        validate(record)


def test_another_paper_cannot_substitute_for_method_report(record):
    record["methods"][0]["dimensions"]["allocation"]["evidence"] = ["car-paper"]
    with pytest.raises(ValueError, match="matching paper evidence"):
        validate(record)
