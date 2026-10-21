"""Offline C15 proposal/vector checks, not admin authorization or live IdP proof."""

import copy
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi.openapi.models import OpenAPI

from agent_rewind.models import canonical
from agent_rewind.ownership import oidc_principal_id

ROOT = Path(__file__).resolve().parents[1]
API_PATH = ROOT / "contracts/proposals/administrative-identity.openapi.json"
FIXTURE_PATH = ROOT / "contracts/fixtures/administrative-identity.json"
API = json.loads(API_PATH.read_text())
FIXTURE = json.loads(FIXTURE_PATH.read_text())
SCHEMAS = API["components"]["schemas"]
LIMITS = API["x-limits"]
METHODS = {"get", "post", "put", "patch", "delete"}
KEYWORDS = {
    "$ref",
    "type",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "minItems",
    "maxItems",
    "minLength",
    "maxLength",
    "pattern",
    "minimum",
    "maximum",
    "enum",
    "const",
    "anyOf",
    "default",
    "description",
    "x-max-utf8-bytes",
    "x-max-canonical-bytes",
    "x-max-raw-bytes",
    "x-transport",
}


def require(ok, message="Invalid synthetic C15 vector"):
    if not ok:
        raise ValueError(message)


def sample(name):
    return copy.deepcopy(next(row["value"] for row in FIXTURE["examples"] if row["schema"] == name))


def validate(schema, value):
    """Closed subset used by this proposal only; unsupported keywords fail."""
    require(set(schema) <= KEYWORDS, "Unsupported proposal schema keyword")
    if "$ref" in schema:
        require(set(schema) == {"$ref"})
        prefix = "#/components/schemas/"
        require(schema["$ref"].startswith(prefix))
        return validate(SCHEMAS[schema["$ref"][len(prefix) :]], value)
    if "anyOf" in schema:
        for branch in schema["anyOf"]:
            try:
                validate(branch, value)
                return
            except ValueError:
                pass
        raise ValueError("No matching proposal branch")
    kind = schema.get("type")
    types = {
        "object": dict,
        "array": list,
        "string": str,
        "boolean": bool,
        "integer": int,
        "null": type(None),
    }
    require(kind in types and type(value) is types[kind], "Strict type mismatch")
    if "enum" in schema:
        require(value in schema["enum"])
    if "const" in schema:
        require(type(value) is type(schema["const"]) and value == schema["const"])
    if kind == "object":
        require(schema["additionalProperties"] is False)
        props = schema["properties"]
        require(set(schema["required"]) <= value.keys() <= props.keys())
        for name, item in value.items():
            validate(props[name], item)
    elif kind == "array":
        require(schema.get("minItems", 0) <= len(value) <= schema["maxItems"])
        for item in value:
            validate(schema["items"], item)
    elif kind == "string":
        try:
            encoded = value.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            raise ValueError("Invalid UTF-8") from None
        require("\0" not in value)
        require(schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 10_000))
        if "pattern" in schema:
            # JSON Schema searches; fullmatch here would hide bad exported anchors.
            require(re.search(schema["pattern"], value) is not None)
        if "x-max-utf8-bytes" in schema:
            require(len(encoded) <= schema["x-max-utf8-bytes"])
        if schema.get("minLength") == schema.get("maxLength") == 20 and "pattern" in schema:
            try:
                datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                raise ValueError("Invalid finite UTC date") from None
    elif kind == "integer":
        require(schema.get("minimum", value) <= value <= schema.get("maximum", value))
    if "x-max-canonical-bytes" in schema:
        require(len(canonical(value)) <= schema["x-max-canonical-bytes"])


def mapping_check(value):
    """Synthetic mapping consistency, never authentication of its producer."""
    validate(SCHEMAS["InstallationMapping"], value)
    issuer = urlsplit(value["issuer"])
    require(issuer.scheme == "https" and bool(issuer.hostname))
    require(issuer.username is None and issuer.password is None)
    require(not issuer.query and not issuer.fragment)
    require("?" not in value["issuer"] and "#" not in value["issuer"])
    require(all(ord(char) >= 33 and ord(char) != 127 for char in value["issuer"]))
    principals = []
    for binding in value["administrators"]:
        require(binding["principal_id"] == oidc_principal_id(value["issuer"], binding["subject"]))
        principals.append(binding["principal_id"])
    require(len(principals) == len(set(principals)))
    rules = [(rule["group"], rule["project_id"]) for rule in value["group_rules"]]
    require(len(rules) == len(set(rules)))


def snapshot_check(mapping, snapshot):
    """Expected mapping proposals only; output is not a project grant."""
    mapping_check(mapping)
    validate(SCHEMAS["VerifiedGroupSnapshot"], snapshot)
    require(snapshot["issuer"] == mapping["issuer"])
    require(snapshot["mapping_digest"] == hashlib.sha256(canonical(mapping)).hexdigest())
    groups = snapshot["groups"]
    require(len(groups) == len(set(groups)))
    proposals = {}
    for rule in mapping["group_rules"]:
        if rule["group"] not in groups:
            continue
        project = rule["project_id"]
        require(project not in proposals or proposals[project] == rule["role"])
        proposals[project] = rule["role"]
    return proposals


def decode_body(raw):
    """Test-only raw-body oracle; never installed as an HTTP parser."""
    require(type(raw) is bytes and len(raw) <= LIMITS["raw_body_bytes"])

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result

    def nonfinite(_):
        raise ValueError("Nonfinite JSON")

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=nonfinite)
    except (UnicodeDecodeError, RecursionError):
        raise ValueError("Invalid encoded body") from None
    count = 0

    def visit(item, depth=0):
        nonlocal count
        count += 1
        require(depth <= 8 and count <= 512)
        if isinstance(item, str):
            require("\0" not in item)
            try:
                item.encode("utf-8", errors="strict")
            except UnicodeEncodeError:
                raise ValueError("Invalid string") from None
        elif isinstance(item, dict):
            for key, child in item.items():
                visit(key, depth + 1)
                visit(child, depth + 1)
        elif isinstance(item, list):
            for child in item:
                visit(child, depth + 1)

    visit(value)
    return value


def test_proposal_model_and_exact_surface_are_not_runtime_or_approval():
    OpenAPI.model_validate(API)
    assert API["x-contract"] == FIXTURE["contract"] == "C15"
    assert API["x-approval-status"] == "pending-peer-review"
    assert not API["x-runtime-implemented"] and not API["x-production-authorized"]
    assert FIXTURE["synthetic"] and FIXTURE["behavior_status"] == "planned-not-executed"
    assert API["x-source-baseline"] == FIXTURE["source_baseline"]
    expected = {
        "/api/v1/admin/projects": {"get", "post"},
        "/api/v1/admin/projects/{project_id}": {"patch"},
        "/api/v1/admin/projects/{project_id}/memberships": {"get"},
        "/api/v1/admin/projects/{project_id}/memberships/{principal_id}": {"put", "delete"},
        "/api/v1/admin/projects/{project_id}/keys": {"get", "post"},
        "/api/v1/admin/projects/{project_id}/keys/{key_id}": {"delete"},
    }
    assert {path: set(item) & METHODS for path, item in API["paths"].items()} == expected
    ids = [
        op["operationId"]
        for item in API["paths"].values()
        for method, op in item.items()
        if method in METHODS
    ]
    assert len(ids) == len(set(ids)) == 9
    assert not any(
        "recovery" in path or "session" in path or "mapping" in path for path in expected
    )


def test_frozen_error_vocabulary_and_credentials_are_preserved():
    m1 = json.loads((ROOT / "contracts/proposals/m1.openapi.json").read_text())
    assert SCHEMAS["Error"] == m1["components"]["schemas"]["Error"]
    assert API["components"]["securitySchemes"] == {
        "sessionCookie": {"type": "apiKey", "in": "cookie", "name": "rewind_session"}
    }
    for item in API["paths"].values():
        for method, op in item.items():
            if method not in METHODS:
                continue
            assert op["security"] == [{"sessionCookie": []}]
            assert op["x-reject-authorization-header"]
            assert op["x-producer"] == "AR-034-B" and not op["x-runtime-implemented"]
            headers = {p["name"]: p for p in op["parameters"] if p["in"] == "header"}
            assert op["x-csrf-required-for-cookie-auth"] == (method != "get")
            assert set(headers) == ({"X-Rewind-CSRF", "Origin"} if method != "get" else set())
            assert all(p["required"] for p in headers.values())
            for code, response in op["responses"].items():
                if "$ref" in response:
                    response = API["components"]["responses"][response["$ref"].split("/")[-1]]
                assert response["headers"]["Cache-Control"]["schema"]["const"] == "no-store"
                assert (
                    response["headers"]["X-Request-ID"]["schema"]["pattern"]
                    == SCHEMAS["Identifier"]["pattern"]
                )
                if code not in {"200", "201"}:
                    assert response["content"]["application/json"]["schema"] == {
                        "$ref": "#/components/schemas/Fault"
                    }
            if "requestBody" in op:
                schema = op["requestBody"]["content"]["application/json"]["schema"]
                assert schema["$ref"].split("/")[-1] in {
                    "ProjectInput",
                    "MembershipInput",
                    "KeyInput",
                }
    assert set(API["x-error-codes"]["503"]) == {
        "schema_incompatible",
        "dependency_unavailable",
        "outcome_uncertain",
    }


@pytest.mark.parametrize("row", FIXTURE["examples"], ids=lambda row: row["schema"])
def test_synthetic_examples_satisfy_strict_bounded_shapes(row):
    validate(SCHEMAS[row["schema"]], row["value"])


@pytest.mark.parametrize(
    "schema,patch",
    [
        ("ProjectInput", {"name": ""}),
        ("ProjectInput", {"name": "x" * 121}),
        ("ProjectInput", {"name": "bad\0name"}),
        ("ProjectInput", {"name": "bad\nname"}),
        ("MembershipInput", {"role": "administrator"}),
        ("MembershipInput", {"role": "organization_admin"}),
        ("MembershipInput", {"role": "owner"}),
        ("MembershipInput", {"legacy_default": 1}),
        ("MembershipInput", {"administrator": True}),
        ("KeyInput", {"role": "maintainer"}),
        ("KeyInput", {"days": True}),
        ("KeyInput", {"days": 1.0}),
        ("KeyInput", {"days": 0}),
        ("KeyInput", {"days": 91}),
        ("KeyInput", {"project_id": "2" * 32}),
        ("KeyInput", {"secret": "private-canary"}),
        ("IssuedKey", {"expires_at": "infinity"}),
        ("IssuedKey", {"expires_at": "2026-02-30T00:00:00Z"}),
        ("InstallationMapping", {"administrators": []}),
        ("InstallationMapping", {"version": True}),
        ("InstallationMapping", {"client_secret": "private-canary"}),
        ("RecoveryRequest", {"replacement_administrators": []}),
        ("RecoveryRequest", {"operator_password": "private-canary"}),
    ],
)
def test_negative_schema_vectors_refuse_without_coercion(schema, patch):
    value = sample(schema)
    value.update(patch)
    with pytest.raises(ValueError):
        validate(SCHEMAS[schema], value)


@pytest.mark.parametrize(
    "schema,path,valid",
    [
        ("ProjectInput", ("properties", "name"), "valid"),
        ("KeyInput", ("properties", "name"), "valid"),
        ("InstallationMapping", ("properties", "group_claim"), "groups"),
        ("GroupRule", ("properties", "group"), "qa"),
        ("VerifiedGroupSnapshot", ("properties", "groups", "items"), "qa"),
        ("Identifier", (), "1" * 32),
        ("HumanPrincipal", (), "oidc:" + "1" * 64),
        ("Principal", (), "api-key:" + "1" * 32),
        ("IssuedKey", ("properties", "token"), "A" * 43),
    ],
)
def test_new_patterns_reject_controls_with_json_schema_search_semantics(schema, path, valid):
    field = SCHEMAS[schema]
    for part in path:
        field = field[part]
    validate(field, valid)
    # Probe the published regex itself: min/max length or the oracle's NUL
    # check must not conceal an end-anchor mismatch in a schema consumer.
    for control in ("\n", "\r", "\t", "\0", "\x1f", "\x7f", "\r\n"):
        for malformed in (control + valid, valid[:1] + control + valid[1:], valid + control):
            assert re.search(field["pattern"], malformed) is None
            with pytest.raises(ValueError):
                validate(field, malformed)


@pytest.mark.parametrize("field", ["group_claim", "group_rules"])
def test_mapping_semantics_refuse_terminal_controls_without_normalization(field):
    for control in ("\n", "\r", "\t", "\0", "\x1f", "\x7f", "\r\n"):
        value = sample("InstallationMapping")
        if field == "group_claim":
            value[field] += control
        else:
            value[field][0]["group"] += control
        with pytest.raises(ValueError):
            mapping_check(value)


def test_group_snapshot_refuses_terminal_control_but_preserves_exact_valid_space():
    mapping = sample("InstallationMapping")
    snapshot = sample("VerifiedGroupSnapshot")
    for control in ("\n", "\r", "\t", "\0", "\x1f", "\x7f", "\r\n"):
        with pytest.raises(ValueError):
            snapshot_check(mapping, {**snapshot, "groups": ["qa" + control]})
    for value in (" qa", "qa ", "\u00e9", "e\u0301"):
        assert snapshot_check(mapping, {**snapshot, "groups": [value]}) == {}
        validate(SCHEMAS["ProjectInput"], {"name": value})


def test_missing_null_and_unknown_fields_cannot_satisfy_mutations():
    for schema in ("ProjectInput", "MembershipInput", "KeyInput", "RecoveryRequest"):
        for field in SCHEMAS[schema]["required"]:
            for replacement in (None,):
                value = sample(schema)
                value[field] = replacement
                with pytest.raises(ValueError):
                    validate(SCHEMAS[schema], value)
            value = sample(schema)
            del value[field]
            with pytest.raises(ValueError):
                validate(SCHEMAS[schema], value)


def test_raw_limit_includes_wrapper_and_refuses_before_json_parse():
    body = b'{"name":"synthetic"}'
    exact = body + b" " * (LIMITS["raw_body_bytes"] - len(body))
    validate(SCHEMAS["ProjectInput"], decode_body(exact))
    with pytest.raises(ValueError):
        decode_body(exact + b" ")
    for malformed in (
        b'{"name":"first","name":"second"}',
        b'{"name":NaN}',
        b'{"name":Infinity}',
        b'{"name":"\xff"}',
        b'{"name":"\\ud800"}',
        b'{"name":"\\u0000"}',
        b"[" * 9 + b"0" + b"]" * 9,
        b"[" + b",".join([b"0"] * 513) + b"]",
    ):
        with pytest.raises(ValueError):
            decode_body(malformed)


def test_names_key_days_and_pages_support_boundary_and_refuse_extra_candidate():
    for days in (1, 90):
        validate(SCHEMAS["KeyInput"], {"name": "\U0001f600" * 120, "role": "viewer", "days": days})
    row = sample("ProjectPage")["items"][0]
    page = {"items": [row] * LIMITS["list_items"], "next_cursor": "A" * 1024}
    validate(SCHEMAS["ProjectPage"], page)
    assert len(canonical(page)) < LIMITS["response_bytes"]
    page["items"].append(row)
    with pytest.raises(ValueError):
        validate(SCHEMAS["ProjectPage"], page)
    page["items"].pop()
    page["next_cursor"] += "A"
    with pytest.raises(ValueError):
        validate(SCHEMAS["ProjectPage"], page)
    assert LIMITS["list_candidate_rows"] == LIMITS["list_items"] + 1


def test_admin_mapping_maximum_counts_are_supported_but_not_credentials():
    value = sample("InstallationMapping")
    value["administrators"] = [
        {"subject": f"human-{i}", "principal_id": oidc_principal_id(value["issuer"], f"human-{i}")}
        for i in range(32)
    ]
    value["group_rules"] = [
        {"group": f"group-{i}", "project_id": "1" * 32, "role": "viewer"} for i in range(64)
    ]
    mapping_check(value)
    for field in ("administrators", "group_rules"):
        oversized = copy.deepcopy(value)
        oversized[field].append(oversized[field][0])
        with pytest.raises(ValueError):
            mapping_check(oversized)
    # All field/count limits can pass while canonical aggregate bytes fail.
    value["administrators"] = [
        {
            "subject": "\U0001f600" * 250 + str(i),
            "principal_id": oidc_principal_id(value["issuer"], "\U0001f600" * 250 + str(i)),
        }
        for i in range(32)
    ]
    assert len(canonical(value)) > LIMITS["mapping_bytes"]
    with pytest.raises(ValueError):
        mapping_check(value)


@pytest.mark.parametrize(
    "mutation",
    [
        "issuer",
        "userinfo",
        "query",
        "fragment",
        "principal",
        "duplicate_admin",
        "duplicate_rule",
        "admin_rule",
        "foreign_installation_shape",
    ],
)
def test_invalid_mapping_never_mints_an_administrator(mutation):
    value = sample("InstallationMapping")
    if mutation == "issuer":
        value["issuer"] += "/"
    elif mutation == "userinfo":
        value["issuer"] = "https://user:private-canary@idp.example.invalid"
    elif mutation == "query":
        value["issuer"] += "?token=private-canary"
    elif mutation == "fragment":
        value["issuer"] += "#private-canary"
    elif mutation == "principal":
        value["administrators"][0]["principal_id"] = "oidc:" + "0" * 64
    elif mutation == "duplicate_admin":
        value["administrators"].append(value["administrators"][0])
    elif mutation == "duplicate_rule":
        value["group_rules"].append(value["group_rules"][0])
    elif mutation == "admin_rule":
        value["group_rules"][0]["role"] = "administrator"
    else:
        value["installation_key"] = "x" * 64
    with pytest.raises(ValueError):
        mapping_check(value)


def test_group_snapshot_exact_values_complete_empty_and_conflict():
    mapping = sample("InstallationMapping")
    snapshot = sample("VerifiedGroupSnapshot")
    assert snapshot_check(mapping, snapshot) == {"1" * 32: "viewer"}
    for groups in ([], ["QA"], [" qa"], ["unknown"]):
        changed = {**snapshot, "groups": groups}
        assert snapshot_check(mapping, changed) == {}
    missing = copy.deepcopy(snapshot)
    del missing["groups"]
    with pytest.raises(ValueError):
        snapshot_check(mapping, missing)
    for patch in (
        {"groups": ["qa", "qa"]},
        {"issuer": snapshot["issuer"] + "/"},
        {"mapping_digest": "f" * 64},
    ):
        with pytest.raises(ValueError):
            snapshot_check(mapping, {**snapshot, **patch})
    mapping["group_rules"].append({"group": "second", "project_id": "1" * 32, "role": "operator"})
    snapshot["mapping_digest"] = hashlib.sha256(canonical(mapping)).hexdigest()
    snapshot["groups"] = ["qa", "second"]
    with pytest.raises(ValueError):
        snapshot_check(mapping, snapshot)


def test_group_count_utf8_and_aggregate_bounds():
    snapshot = sample("VerifiedGroupSnapshot")
    snapshot["groups"] = [f"group-{i}" for i in range(128)]
    validate(SCHEMAS["VerifiedGroupSnapshot"], snapshot)
    snapshot["groups"].append("excess")
    with pytest.raises(ValueError):
        validate(SCHEMAS["VerifiedGroupSnapshot"], snapshot)
    snapshot["groups"] = ["\U0001f600" * 128]
    validate(SCHEMAS["VerifiedGroupSnapshot"], snapshot)
    snapshot["groups"] = ["\U0001f600" * 129]
    with pytest.raises(ValueError):
        validate(SCHEMAS["VerifiedGroupSnapshot"], snapshot)
    snapshot["groups"] = ["\U0001f600" * 120 + str(i) for i in range(16)]
    assert len(canonical(snapshot)) > LIMITS["group_snapshot_bytes"]
    with pytest.raises(ValueError):
        validate(SCHEMAS["VerifiedGroupSnapshot"], snapshot)


def test_exact_issuer_subject_and_unicode_identity_do_not_alias():
    issuer = sample("InstallationMapping")["issuer"]
    assert oidc_principal_id(issuer, "\u00e9") != oidc_principal_id(issuer, "e\u0301")
    assert oidc_principal_id(issuer, "Admin") != oidc_principal_id(issuer, "admin")
    assert oidc_principal_id(issuer, "admin") != oidc_principal_id(issuer + "/", "admin")
    validate(SCHEMAS["HumanPrincipal"], oidc_principal_id(issuer, "admin"))
    with pytest.raises(ValueError):
        validate(SCHEMAS["HumanPrincipal"], "api-key:" + "1" * 32)


def test_contract_vector_taxonomy_does_not_claim_runtime_execution():
    expected = {
        "missing_identity": (401, "unauthenticated"),
        "project_maintainer": (403, "forbidden"),
        "project_operator": (403, "forbidden"),
        "service_key": (401, "unauthenticated"),
        "mixed_credentials": (401, "unauthenticated"),
        "admin_visible_project": (200, None),
        "admin_foreign_project": (404, "not_found"),
        "admin_no_data_grant": (404, "not_found"),
    }
    rows = FIXTURE["authorization_vectors"]
    assert len(rows) == len(expected)
    assert {row["id"]: (row["status"], row["code"]) for row in rows} == expected
    scenarios = FIXTURE["required_scenarios"]
    assert set(scenarios) == {
        "membership_revocation",
        "stale_browser_response",
        "last_admin_race",
        "external_lockout",
        "recovery_uncertainty",
        "group_revocation",
        "key_revocation",
        "key_ack",
    }
    assert all(row["proof"] and row["sequence"] and row["owner"] for row in scenarios.values())
    assert FIXTURE["behavior_status"] == "planned-not-executed"


def recovery_check(request, mapping):
    """Association oracle only; no operator credential, durable ACK or execution."""
    mapping_check(mapping)
    validate(SCHEMAS["RecoveryRequest"], request)
    require(request["installation_key"] == mapping["installation_key"])
    require(request["expected_mapping_digest"] == hashlib.sha256(canonical(mapping)).hexdigest())
    replacement = {**mapping, "administrators": request["replacement_administrators"]}
    mapping_check(replacement)


def test_recovery_exact_installation_expected_version_and_human_binding():
    mapping = sample("InstallationMapping")
    request = sample("RecoveryRequest")
    recovery_check(request, mapping)
    for field, value in (
        ("installation_key", "f" * 64),
        ("expected_mapping_digest", "f" * 64),
        ("replacement_administrators", []),
        ("operation_id", "not-an-id"),
        ("reason", "force_reset"),
        (
            "replacement_administrators",
            [{"principal_id": "oidc:" + "0" * 64, "subject": "recovery-admin"}],
        ),
    ):
        with pytest.raises(ValueError):
            recovery_check({**request, field: value}, mapping)


def test_all_local_references_resolve_and_schema_subset_is_closed():
    def visit(value):
        if isinstance(value, dict):
            if "$ref" in value:
                reference = value["$ref"]
                assert re.fullmatch(r"#/components/(schemas|responses)/[A-Za-z0-9]+", reference)
                _, _, category, name = reference.split("/")
                assert name in API["components"][category]
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(API)
    with pytest.raises(ValueError, match="Unsupported"):
        validate({"type": "string", "unevaluatedProperties": False}, "text")
    # JSON Schema patterns search unless anchored; this is a prefix pattern.
    validate({"type": "string", "pattern": "^https://"}, "https://example.invalid/tenant")


def test_largest_pages_fit_response_cap_and_key_metadata_never_has_secrets():
    for kind in ("Project", "Membership", "Key"):
        row = sample(kind + "Page")["items"][0]
        if "name" in row:
            row["name"] = "\U0001f600" * 120
        page = {"items": [row] * 50, "next_cursor": "A" * 1024}
        validate(SCHEMAS[kind + "Page"], page)
        assert len(canonical(page)) < LIMITS["response_bytes"]
    assert not {"hash", "token", "secret"} & SCHEMAS["Key"]["properties"].keys()
    assert "token" in SCHEMAS["IssuedKey"]["properties"]


def test_limits_are_coherent_with_wire_and_internal_input_shapes():
    assert LIMITS["raw_body_bytes"] == 16384 and LIMITS["response_bytes"] == 131072
    assert LIMITS["sql_statements"] == 128 and LIMITS["sql_seconds"] == 5
    assert LIMITS["sqlite_vm_instructions"] == 5000000
    assert SCHEMAS["InstallationMapping"]["x-max-canonical-bytes"] == LIMITS["mapping_bytes"]
    assert (
        SCHEMAS["VerifiedGroupSnapshot"]["x-max-canonical-bytes"] == LIMITS["group_snapshot_bytes"]
    )
    for field, limit in (("administrators", "administrators"), ("group_rules", "group_rules")):
        assert SCHEMAS["InstallationMapping"]["properties"][field]["maxItems"] == LIMITS[limit]
    groups = SCHEMAS["VerifiedGroupSnapshot"]["properties"]["groups"]
    assert groups["maxItems"] == LIMITS["groups"]
    assert groups["items"]["maxLength"] == LIMITS["group_characters"]
    assert groups["items"]["x-max-utf8-bytes"] == LIMITS["group_utf8_bytes"]
