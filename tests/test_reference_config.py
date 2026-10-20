"""C14 checks use fabricated inputs and never establish deployment approval."""

import copy
import importlib.util
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "reference_config", ROOT / "scripts/reference_config.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
SAMPLE = json.loads((ROOT / "contracts/fixtures/reference-config.synthetic.json").read_text())
NOW = datetime(2026, 10, 21, tzinfo=UTC)


def parse(value):
    return MODULE.ReferenceConfig.model_validate(value)


def sample():
    return copy.deepcopy(SAMPLE)


def declared_record():
    value = sample()
    value["synthetic"] = False
    for line in value["budget"]["lines"]:
        line["basis"] = "allowance"
    digest = MODULE.config_digest(parse(value))
    value["approval_record"] = {
        "gate": "ENV0",
        "evidence_id": "fabricated-test-evidence",
        "approved_by": "fabricated-test-owner",
        "approved_at": "2026-10-20T00:00:00Z",
        "expires_at": "2026-10-22T00:00:00Z",
        "config_sha256": digest,
    }
    return value


def test_synthetic_fixture_is_valid_but_cannot_enter_deployment_review():
    config = parse(sample())
    assert config.synthetic
    with pytest.raises(ValueError, match="Synthetic or unapproved"):
        MODULE.check_deployment_review(config, NOW)


def test_published_json_schema_matches_typed_wire_contract():
    schema = MODULE.ReferenceConfig.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = (
        "https://github.com/spei04/agent-rewind/contracts/reference-config.v1.schema.json"
    )
    assert schema == json.loads((ROOT / "contracts/reference-config.v1.schema.json").read_text())
    assert schema["additionalProperties"] is False
    for definition in schema["$defs"].values():
        if definition.get("type") == "object":
            assert definition["additionalProperties"] is False


@pytest.mark.parametrize(
    "field", ["region", "budget", "approval_record", "operator_id", "identities"]
)
def test_missing_required_input_is_rejected(field):
    value = sample()
    del value[field]
    with pytest.raises(ValidationError):
        parse(value)


@pytest.mark.parametrize(
    ("section", "field", "replacement"),
    [
        ("network", "ingress", "public-https"),
        ("network", "external_egress", "internet"),
        ("network", "worker_public_ip", True),
        ("network", "sandbox_network", "bridge"),
        ("network", "sandbox_metadata_access", True),
        ("network", "private_google_access", False),
        ("database", "public_ip", True),
        ("database", "iam_authentication", False),
        ("database", "backup_enabled", False),
        ("database", "connector_enforcement", "NOT_REQUIRED"),
        ("storage", "public_access_prevention", "inherited"),
        ("storage", "automatic_artifact_deletion", True),
        ("keys", "service_account_keys", "allowed"),
        ("keys", "secret_values", "accidental-secret"),
        ("capacity", "worker_max_hosts", True),
        ("budget", "monthly_limit_microusd", 1.5),
        ("database", "public_ip", 0),
    ],
)
def test_unsafe_or_wrongly_typed_policy_is_rejected(section, field, replacement):
    value = sample()
    value[section][field] = replacement
    with pytest.raises(ValidationError):
        parse(value)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("worker_subnet", "0.0.0.0/0"),
        ("worker_subnet", "127.0.0.0/24"),
        ("worker_subnet", "169.254.169.0/24"),
        ("worker_subnet", "192.0.2.0/24"),
        ("worker_subnet", "10.60.0.0/24"),
        ("worker_subnet", "10.60.1.2/24"),
        ("worker_subnet", "fc00::/64"),
        ("sql_service_range", "10.60.4.0/28"),
        ("operator_cidrs", ["10.60.1.0/24"]),
        ("operator_cidrs", []),
    ],
)
def test_network_rejects_public_metadata_overlapping_or_ambiguous_routes(field, replacement):
    value = sample()
    value["network"][field] = replacement
    with pytest.raises(ValidationError):
        parse(value)


@pytest.mark.parametrize(
    "variant", ["shared", "model-on-api", "ddl-on-worker", "missing", "duplicate"]
)
def test_identity_policy_cannot_gain_or_share_maintenance_authority(variant):
    value = sample()
    if variant == "shared":
        value["identities"]["api"]["account_id"] = value["identities"]["migrator"]["account_id"]
    elif variant == "model-on-api":
        value["identities"]["api"]["capabilities"].append("provider-secret-read")
    elif variant == "ddl-on-worker":
        value["identities"]["worker"]["capabilities"].append("database-ddl")
    elif variant == "missing":
        value["identities"]["provisioner"]["capabilities"].remove("state-read-write")
    else:
        value["identities"]["api"]["capabilities"].append("database-dml")
    with pytest.raises(ValidationError):
        parse(value)


@pytest.mark.parametrize(
    "variant",
    ["region", "label", "bucket", "secret", "over-budget", "bootstrap", "cost-line", "alert"],
)
def test_cross_resource_and_funding_invariants(variant):
    value = sample()
    if variant == "region":
        value["keys"]["location"] = "europe-west1"
    elif variant == "label":
        value["labels"]["installation"] = "different-installation"
    elif variant == "bucket":
        value["storage"]["state_bucket"] = value["storage"]["artifact_bucket"]
    elif variant == "secret":
        value["keys"]["provider_secret"] = value["keys"]["oidc_client_secret"]
    elif variant == "over-budget":
        value["budget"]["monthly_limit_microusd"] = 999_999_999
    elif variant == "bootstrap":
        value["budget"]["bootstrap_limit_microusd"] = 49_999_999
    elif variant == "cost-line":
        value["budget"]["lines"][-1] = copy.deepcopy(value["budget"]["lines"][0])
    else:
        value["budget"]["alert_percentages"] = [50, 80]
    with pytest.raises(ValidationError):
        parse(value)


def test_connection_envelope_uses_all_processes_and_seventy_percent_boundary():
    value = sample()
    # 2*5 API + 2*4*2 worker + 10 operator = 36; 52 allows36, 51 allows35.
    value["database"]["connection_capacity"] = 52
    parse(value)
    value["database"]["connection_capacity"] = 51
    with pytest.raises(ValidationError, match="70 percent"):
        parse(value)


def test_record_consistency_does_not_verify_the_external_evidence():
    config = parse(declared_record())
    MODULE.check_deployment_review(config, NOW)
    assert config.approval_record.evidence_id == "fabricated-test-evidence"
    # No deployment or approval grant is returned; this check cannot establish authenticity.


@pytest.mark.parametrize(
    "variant", ["missing", "expired", "future", "changed", "epoch", "naive", "stop-before-expiry"]
)
def test_record_preflight_rejects_missing_stale_or_unbound_authority(variant):
    value = declared_record()
    if variant == "missing":
        value["approval_record"] = None
    elif variant == "expired":
        value["approval_record"]["expires_at"] = "2026-10-21T00:00:00Z"
    elif variant == "future":
        value["approval_record"]["approved_at"] = "2026-10-21T00:00:01Z"
    elif variant == "changed":
        value["budget"]["monthly_limit_microusd"] += 1
    elif variant == "stop-before-expiry":
        value["staging_stop_at"] = "2026-10-21T12:00:00Z"
        value["approval_record"]["config_sha256"] = MODULE.config_digest(parse(value))
    elif variant == "epoch":
        value["approval_record"]["approved_at"] = "1792454400"
    else:
        value["approval_record"]["approved_at"] = "2026-10-20T00:00:00"
    with pytest.raises((ValueError, ValidationError)):
        MODULE.check_deployment_review(parse(value), NOW)


def test_synthetic_prices_cannot_be_relabelled_as_a_real_request():
    value = sample()
    value["synthetic"] = False
    with pytest.raises(ValidationError, match="actual quote/allowance"):
        parse(value)


@pytest.mark.parametrize("body", ['{"region":"one","region":"two"}', " " * 65537])
def test_loader_rejects_duplicate_fields_and_large_input(tmp_path, body):
    path = tmp_path / "config.json"
    path.write_text(body)
    with pytest.raises(ValueError):
        MODULE.load_config(path)


def test_cli_is_offline_non_authorizing_and_does_not_echo_invalid_secrets(tmp_path):
    command = [sys.executable, str(ROOT / "scripts/reference_config.py")]
    good = subprocess.run(
        [*command, str(ROOT / "contracts/fixtures/reference-config.synthetic.json")],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert good.returncode == 0, good.stderr
    assert json.loads(good.stdout)["deployable"] is False
    blocked = subprocess.run(
        [
            *command,
            str(ROOT / "contracts/fixtures/reference-config.synthetic.json"),
            "--deployment-review",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert blocked.returncode == 2
    value = sample()
    value["credential"] = "do-not-echo-this-secret"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(value))
    bad = subprocess.run([*command, str(path)], capture_output=True, text=True, timeout=10)
    assert bad.returncode == 2
    assert "do-not-echo-this-secret" not in bad.stdout + bad.stderr
    assert json.loads(bad.stdout)["issues"] == [
        {"path": ["<unknown-field>"], "code": "extra_forbidden"}
    ]
    missing = sample()
    del missing["region"]
    path.write_text(json.dumps(missing))
    result = subprocess.run([*command, str(path)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert json.loads(result.stdout)["issues"] == [{"path": ["region"], "code": "missing"}]
