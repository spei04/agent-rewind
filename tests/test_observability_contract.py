"""Design-time checks; these do not exercise runtime handlers or telemetry sinks."""

import copy
import json
import math
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "contracts/proposals/observability.contract.json").read_text())
M1 = json.loads((ROOT / "contracts/proposals/m1.openapi.json").read_text())
ID = re.compile(r"[0-9a-f]{32}")


def validate_error(row):
    body = row["body"]
    if set(body) != {"code", "message", "request_id", "retryable"}:
        raise ValueError("Unknown or missing error fields")
    rule = CONTRACT["error_rules"].get(body["code"])
    if rule is None or row["http_status"] not in rule["statuses"]:
        raise ValueError("Invalid error code/status")
    if body["message"] not in rule["messages"] or len(body["message"]) > 300:
        raise ValueError("Unsafe public message")
    if body["retryable"] is not rule["retryable"]:
        raise ValueError("Unsafe retry classification")
    if not isinstance(body["request_id"], str) or not ID.fullmatch(body["request_id"]):
        raise ValueError("Invalid request ID")
    headers = row["headers"]
    if headers.get("X-Request-ID") != body["request_id"]:
        raise ValueError("Uncorrelated request ID")
    if headers.get("Cache-Control") != "no-store":
        raise ValueError("Sensitive response can be cached")
    if row["http_status"] == 429:
        delay = headers.get("Retry-After", "")
        if not delay.isdecimal() or not 1 <= int(delay) <= 60:
            raise ValueError("Invalid retry delay")


def readiness(row):
    required = CONTRACT["readiness_policy"]["required_checks"]
    if row["checks"].get("schema") == "not_ready":
        return 200, 503, "schema_incompatible"
    if row["draining"] or any(row["checks"].get(key) != "ready" for key in required):
        return 200, 503, "dependency_unavailable"
    return 200, 200, None


def validate_metric(row):
    rule = CONTRACT["metrics"].get(row["metric"])
    if rule is None or set(row["labels"]) != set(rule["labels"]):
        raise ValueError("Unknown metric or label names")
    for key, value in row["labels"].items():
        if value not in CONTRACT["label_vocabulary"][key]:
            raise ValueError("Unbounded or unsafe label value")


@pytest.mark.parametrize("row", CONTRACT["errors"], ids=lambda row: row["id"])
def test_error_examples_use_safe_fixed_envelope(row):
    validate_error(row)


@pytest.mark.parametrize("row", CONTRACT["successes"], ids=lambda row: row["id"])
def test_success_examples_keep_response_shapes_and_request_id(row):
    schema = M1["components"]["schemas"][row["schema"]]
    assert set(row["body"]) == set(schema["required"]) == set(schema["properties"])
    assert row["http_status"] in {200, 202}
    assert ID.fullmatch(row["headers"]["X-Request-ID"])
    assert row["headers"]["Cache-Control"] == "no-store"
    for key, value in row["body"].items():
        if key == "id" or key.endswith("_id"):
            assert value is None or ID.fullmatch(value)
    if row["schema"] == "Cancellation":
        assert row["body"]["cancel_requested"] is True
        assert row["body"]["status"] == "running"
    if row["schema"] == "Operation":
        assert row["http_status"] == 200
        assert row["body"]["status"] == "failed"
        assert row["body"]["error"]["code"] == "outcome_uncertain"
        assert row["body"]["reserved_microusd"] > 0


def test_central_contract_differences_are_explicit():
    current = set(M1["components"]["schemas"]["Error"]["properties"]["code"]["enum"])
    proposed = set(CONTRACT["error_rules"])
    assert current <= proposed
    assert proposed - current == set(CONTRACT["reconciliation"]["add_error_codes"])
    assert CONTRACT["runtime_implemented"] is False


def test_absent_and_inaccessible_resource_do_not_reveal_existence():
    rows = {row["id"]: row for row in CONTRACT["errors"]}
    absent = rows["absent_resource"]
    inaccessible = rows["inaccessible_resource"]
    assert absent["body"] == inaccessible["body"]
    assert absent["http_status"] == inaccessible["http_status"] == 404


@pytest.mark.parametrize(
    "field,value",
    [
        ("message", "synthetic-secret-token: customer source"),
        ("request_id", "caller\r\nInjected: value"),
        ("retryable", True),
        ("debug", {"provider_body": "synthetic-secret-token"}),
    ],
)
def test_secret_and_unsafe_error_fields_are_rejected(field, value):
    row = copy.deepcopy(CONTRACT["errors"][-1])
    row["body"][field] = value
    with pytest.raises(ValueError):
        validate_error(row)


def test_request_id_mismatch_and_unbounded_retry_after_are_rejected():
    row = copy.deepcopy(CONTRACT["errors"][0])
    row["headers"]["X-Request-ID"] = "f" * 32
    with pytest.raises(ValueError, match="Uncorrelated"):
        validate_error(row)
    quota = copy.deepcopy(next(row for row in CONTRACT["errors"] if row["id"] == "quota"))
    quota["headers"]["Retry-After"] = "999999999"
    with pytest.raises(ValueError, match="retry delay"):
        validate_error(quota)


@pytest.mark.parametrize("row", CONTRACT["readiness_cases"], ids=lambda row: row["id"])
def test_dependency_faults_affect_readiness_without_restart_loop(row):
    assert readiness(row) == (
        row["expected_liveness"],
        row["expected_readiness"],
        row["expected_code"],
    )


def test_missing_probe_is_not_assumed_healthy():
    row = copy.deepcopy(CONTRACT["readiness_cases"][0])
    del row["checks"]["artifacts"]
    assert readiness(row) == (200, 503, "dependency_unavailable")


@pytest.mark.parametrize("row", CONTRACT["valid_metric_examples"])
def test_approved_metric_label_values(row):
    validate_metric(row)


@pytest.mark.parametrize("row", CONTRACT["rejected_metric_examples"])
def test_secret_or_high_cardinality_labels_are_rejected(row):
    with pytest.raises(ValueError):
        validate_metric(row)


def test_label_combination_bounds_do_not_grow_with_request_count():
    for rule in CONTRACT["metrics"].values():
        count = math.prod(len(CONTRACT["label_vocabulary"][label]) for label in rule["labels"])
        assert count == rule["maximum_label_combinations"]
    for value in range(1000):
        row = {
            "metric": "http_requests_total",
            "labels": {
                "route": f"/api/runs/{value:032x}",
                "method": "GET",
                "status_class": "2xx",
            },
        }
        with pytest.raises(ValueError, match="label value"):
            validate_metric(row)
