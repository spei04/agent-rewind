"""Review metadata and cross-contract regressions, never runtime sign-off."""

import copy
import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECK = runpy.run_path(str(ROOT / "scripts/m1_contract_review.py"))["check_review"]
PATHS = [
    "contracts/proposals/m1.openapi.json",
    "contracts/proposals/m1.data-model.json",
    "contracts/proposals/m1.acceptance.json",
    "contracts/fixtures/m1-contract-links.json",
    "contracts/proposals/observability.contract.json",
    "contracts/proposals/m1.freeze.json",
]


@pytest.fixture
def documents():
    return [json.loads((ROOT / path).read_text()) for path in PATHS]


def reviewed_fixture(documents):
    """Synthetic shape test only: never persist these invented review examples."""
    documents[0]["x-approval-status"] = "reviewed"
    for index in (1, 3, 5):
        documents[index]["approval_status"] = "reviewed"
    documents[5]["reviewed_source_commit"] = "1" * 40
    for row in documents[5]["reviews"]:
        row.update(
            status="accepted",
            reviewed_source_commit="1" * 40,
            reviewer="Synthetic reviewer for validator test",
            date="2026-10-19T00:00:00Z",
            scope="Synthetic contract review only",
            evidence="tests/test_m1_contract_review.py:reviewed_fixture",
        )


def test_current_pending_record_and_future_reviewed_record_keep_behavior_planned(documents):
    assert CHECK(*documents) == "pending"
    reviewed_fixture(documents)
    assert CHECK(*documents) == "reviewed"
    assert documents[2]["status"] == documents[5]["behavior_status"] == "planned-not-executed"


@pytest.mark.parametrize("field", ["reviewer", "date", "scope", "evidence"])
def test_review_without_required_evidence_is_rejected(documents, field):
    reviewed_fixture(documents)
    documents[5]["reviews"][0][field] = None
    with pytest.raises(ValueError, match="review"):
        CHECK(*documents)


@pytest.mark.parametrize("status", ["pending", "changes-required"])
def test_unresolved_consumer_cannot_mark_freeze_reviewed(documents, status):
    reviewed_fixture(documents)
    documents[5]["reviews"][0]["status"] = status
    with pytest.raises(ValueError, match="consumer"):
        CHECK(*documents)


def test_missing_or_duplicate_review_role_is_rejected(documents):
    documents[5]["reviews"][0] = copy.deepcopy(documents[5]["reviews"][1])
    with pytest.raises(ValueError, match="review role"):
        CHECK(*documents)


@pytest.mark.parametrize("index", range(6))
def test_revision_drift_is_rejected(documents, index):
    field = "x-contract-revision" if index == 0 else "contract_revision"
    documents[index][field] = "unreviewed-revision"
    with pytest.raises(ValueError, match="revisions disagree"):
        CHECK(*documents)


def test_approval_drift_and_runtime_claims_are_rejected(documents):
    changed = copy.deepcopy(documents)
    changed[1]["approval_status"] = "reviewed"
    with pytest.raises(ValueError, match="review states"):
        CHECK(*changed)
    for field in ("runtime_implemented", "production_authorized"):
        changed = copy.deepcopy(documents)
        changed[5][field] = True
        with pytest.raises(ValueError, match="production or certify runtime"):
            CHECK(*changed)
    documents[5]["behavior_status"] = "passed"
    with pytest.raises(ValueError, match="runtime behavior"):
        CHECK(*documents)


def test_observability_vocabulary_and_cookie_header_cannot_drift(documents):
    changed = copy.deepcopy(documents)
    changed[0]["components"]["schemas"]["Error"]["properties"]["code"]["enum"].remove(
        "outcome_uncertain"
    )
    with pytest.raises(ValueError, match="error vocabulary"):
        CHECK(*changed)
    post = documents[0]["paths"]["/api/v1/projects/{project_id}/runs"]["post"]
    next(p for p in post["parameters"] if p["name"] == "X-Rewind-CSRF")["name"] = "X-CSRF-Token"
    with pytest.raises(ValueError, match="CSRF"):
        CHECK(*documents)


@pytest.mark.parametrize("member", ["500", "413", "X-Request-ID", "Cache-Control", "Retry-After"])
def test_all_responses_require_safe_faults_headers_and_bounded_retry(documents, member):
    responses = documents[0]["paths"]["/api/v1/projects/{project_id}/runs"]["get"]["responses"]
    if member in {"500", "413"}:
        del responses[member]
    elif member == "Retry-After":
        responses["429"]["headers"][member]["schema"]["maximum"] = 9999
    else:
        del responses["200"]["headers"][member]
    with pytest.raises(ValueError):
        CHECK(*documents)


def test_readiness_bounds_and_guard_are_not_expected_size_assumptions(documents):
    for field, value in (
        ("sentinel_maximum_ciphertext_bytes", 10000000),
        ("schema_guard_prerequisite", "AR-009-A"),
    ):
        changed = copy.deepcopy(documents)
        changed[4]["readiness_policy"][field] = value
        with pytest.raises(ValueError):
            CHECK(*changed)
    # Maximum Fernet token length for 4096 plaintext bytes, including PKCS7 padding.
    token_bytes = 57 + 16 * (4096 // 16 + 1)
    assert 4 * ((token_bytes + 2) // 3) == 5560


@pytest.mark.parametrize(
    "entity,field",
    [
        ("project_memberships", "legacy_default"),
        ("run_index", "published_seq"),
        ("operations", "execution_config_digest"),
        ("provider_calls", "lease_generation"),
        ("provider_calls", "project_account_id"),
        ("budget_accounts", "opening_held_microusd"),
        ("budget_entries", "evidence_owner_kind"),
    ],
)
def test_required_closure_and_compatibility_declarations_cannot_disappear(documents, entity, field):
    del documents[1]["entities"][entity]["fields"][field]
    with pytest.raises(ValueError, match="ownership/compatibility"):
        CHECK(*documents)


def test_first_slice_does_not_duplicate_ownership_backfill(documents):
    documents[5]["migration_owners"]["ownership-v1"] = "AR-005-B"
    with pytest.raises(ValueError, match="ownership overlaps"):
        CHECK(*documents)


def test_review_cannot_apply_to_a_different_source_commit(documents):
    reviewed_fixture(documents)
    documents[5]["reviews"][0]["reviewed_source_commit"] = "2" * 40
    with pytest.raises(ValueError, match="exact reviewed source commit"):
        CHECK(*documents)
