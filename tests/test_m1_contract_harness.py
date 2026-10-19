"""Break proposal links and frozen oracles; no planned runtime case is executed."""

import json
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECKER = runpy.run_path(str(ROOT / "scripts/check_m1_contracts.py"))


@pytest.fixture
def contracts():
    api, data, models, database = CHECKER["load"]()
    return {
        "api": api,
        "data": data,
        "models": models,
        "database": database,
        "acceptance": CHECKER["read_json"](ROOT / "contracts/proposals/m1.acceptance.json"),
        "links": CHECKER["read_json"](ROOT / "contracts/fixtures/m1-contract-links.json"),
        "fixture": CHECKER["read_json"](ROOT / "tests/fixtures/legacy_v0/manifest.json"),
    }


def check_links(values):
    return CHECKER["check_planned_acceptance"](
        values["api"], values["data"], values["acceptance"], values["links"], values["fixture"]
    )


@pytest.fixture
def frozen(tmp_path):
    root = tmp_path / "legacy_v0"
    shutil.copytree(ROOT / "tests/fixtures/legacy_v0", root)
    return root, CHECKER["read_json"](root / "manifest.json")


def check_frozen(root, fixture):
    return CHECKER["check_fixture"](root, fixture, "8f1ae757005c95c50a789e4fa0a10aae9b3c4024")


def test_current_proposal_suite_checks_links_frozen_rows_and_openapi_model():
    result = CHECKER["check_proposal_suite"](openapi_model=True)
    assert result["operations"] == 5
    assert result["entities"] == 12
    assert result["planned_acceptance_cases"] == 24
    assert result["frozen_rows"] == 14
    assert result["frozen_objects"] == 18
    assert result["fixture_variants"] == 5
    assert result["approval_status"] == "pending"
    assert result["behavior_status"] == "planned-not-executed"
    assert result["openapi_model_checked"] is True


def test_duplicate_acceptance_ids_are_rejected(contracts):
    contracts["acceptance"]["cases"][1]["id"] = contracts["acceptance"]["cases"][0]["id"]
    with pytest.raises(ValueError, match="Duplicate acceptance case ID: CT-M1-001"):
        check_links(contracts)


def test_missing_and_duplicate_case_mappings_are_rejected(contracts):
    removed = contracts["links"]["links"].pop()
    with pytest.raises(ValueError, match="Missing contract mapping.*CT-M1-024"):
        check_links(contracts)
    contracts["links"]["links"].extend([removed, removed])
    with pytest.raises(ValueError, match="Duplicate contract mapping: CT-M1-024"):
        check_links(contracts)


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("operations", ["missingOperation"], "Unknown operation mapping"),
        ("entities", ["missing_entity"], "Unknown entity mapping"),
        ("schemas", ["MissingSchema"], "Unknown schema mapping"),
        ("legacy_fixtures", ["missing_variant"], "Unknown fixture mapping"),
        ("fields", ["operations.missing_column"], "Missing logical field mapping"),
        ("issue", "AR-006", "Acceptance owner mismatch"),
        ("case_id", "CT-M1-999", "unknown acceptance case"),
    ],
)
def test_invalid_cross_contract_links_fail_with_case_diagnostics(contracts, field, value, message):
    target = next(link for link in contracts["links"]["links"] if link["case_id"] == "CT-M1-010")
    target[field] = value
    with pytest.raises(ValueError, match=message):
        check_links(contracts)


def test_mapped_field_cannot_outlive_its_declared_entity(contracts):
    link = next(link for link in contracts["links"]["links"] if link["case_id"] == "CT-M1-010")
    link["entities"].remove("operations")
    with pytest.raises(ValueError, match="Field mapping lacks its entity for CT-M1-010"):
        check_links(contracts)


def test_new_api_operation_requires_acceptance_mapping(contracts):
    contracts["api"]["paths"]["/new"] = {"get": {"operationId": "newOperation"}}
    with pytest.raises(ValueError, match="API operation lacks an acceptance mapping"):
        check_links(contracts)


def test_new_logical_entity_requires_acceptance_mapping(contracts):
    contracts["data"]["entities"]["new_entity"] = {"fields": {"id": "id PK"}}
    with pytest.raises(ValueError, match="Logical entity lacks an acceptance mapping"):
        check_links(contracts)


def test_general_inventory_is_separate_from_review_gate(contracts):
    contracts["api"]["x-approval-status"] = "reviewed"
    contracts["data"]["approval_status"] = "reviewed"
    assert (
        CHECKER["check"](
            contracts["api"], contracts["data"], contracts["models"], contracts["database"]
        )["operations"]
        == 5
    )


@pytest.mark.parametrize(
    "document,field", [("acceptance", "status"), ("links", "acceptance_status")]
)
def test_structural_checks_cannot_claim_behavior_cases_passed(contracts, document, field):
    contracts[document][field] = "passed"
    with pytest.raises(ValueError, match="planned-not-executed|cannot claim executed behavior"):
        check_links(contracts)


def test_broken_reference_diagnostic_names_location_not_external_value(contracts):
    schema = contracts["api"]["components"]["schemas"]["RunPage"]["properties"]["items"]["items"]
    schema["$ref"] = "https://private.invalid/?secret=DO_NOT_PRINT"
    with pytest.raises(ValueError) as error:
        CHECKER["check"](
            contracts["api"], contracts["data"], contracts["models"], contracts["database"]
        )
    assert "RunPage.properties.items.items" in str(error.value)
    assert "DO_NOT_PRINT" not in str(error.value)
    assert "private.invalid" not in str(error.value)


def test_duplicate_json_members_and_oversized_files_are_rejected(tmp_path):
    path = tmp_path / "contract.json"
    path.write_text('{"status":"pending","status":"approved"}')
    with pytest.raises(ValueError, match="Duplicate JSON member"):
        CHECKER["read_json"](path)
    path.write_bytes(b" " * (CHECKER["MAX_FILE_BYTES"] + 1))
    with pytest.raises(ValueError, match="1 MiB contract file limit"):
        CHECKER["read_json"](path)


def test_nested_contract_input_is_bounded():
    value = {}
    for _ in range(CHECKER["MAX_DEPTH"] + 1):
        value = {"next": value}
    with pytest.raises(ValueError, match="node/depth limit"):
        CHECKER["bounded_tree"](value)


def test_frozen_sql_bytes_and_original_rows_are_independent_checks(frozen):
    root, fixture = frozen
    sql = (root / "baseline.sql").read_bytes().replace(b"125000", b"125001", 1)
    (root / "baseline.sql").write_bytes(sql)
    with pytest.raises(ValueError, match="Frozen SQL checksum mismatch"):
        check_frozen(root, fixture)
    fixture["baseline_sql_sha256"] = CHECKER["sha256"](sql)
    with pytest.raises(ValueError, match="Frozen original row values changed: jobs"):
        check_frozen(root, fixture)


def test_changed_ciphertext_and_unsafe_variant_path_fail(frozen):
    root, fixture = frozen
    obj = next(iter(fixture["objects"].values()))
    path = root / "objects" / obj["address"]
    original = path.read_bytes()
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="ciphertext checksum mismatch"):
        check_frozen(root, fixture)
    path.write_bytes(original)
    fixture["variants"]["corrupt_ciphertext"]["object_override"]["file"] = "../../outside"
    with pytest.raises(ValueError, match="Unsafe corruption fixture path"):
        check_frozen(root, fixture)


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("reservation_total_microusd", 0, "reservation total mismatch"),
        ("source_commit", "0" * 40, "baseline differs"),
        ("synthetic_only", False, "explicitly synthetic"),
    ],
)
def test_frozen_manifest_identity_fields_cannot_drift(frozen, field, value, message):
    root, fixture = frozen
    fixture[field] = value
    with pytest.raises(ValueError, match=message):
        check_frozen(root, fixture)


def test_expanded_run_identity_and_schema_fingerprint_are_verified(frozen):
    root, fixture = frozen
    fixture["runs"]["1" * 32]["head"] = "0" * 64
    with pytest.raises(ValueError, match="timestamp/head/step identity mismatch"):
        check_frozen(root, fixture)
    fixture = CHECKER["read_json"](root / "manifest.json")
    fixture["variants"]["unknown_schema"]["schema_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="schema fingerprint mismatch: unknown_schema"):
        check_frozen(root, fixture)


def test_fixture_sql_cannot_attach_host_files_or_load_extensions(tmp_path):
    forbidden = tmp_path / "must-not-exist.sqlite"
    for sql in [
        f"ATTACH DATABASE '{forbidden}' AS host;",
        "SELECT load_extension('private');",
        "SELECT randomblob(999999999);",
    ]:
        with pytest.raises(ValueError, match="forbidden I/O"):
            CHECKER["fixture_connection"](sql)
    assert not forbidden.exists()


def test_cli_reports_proposal_scope_with_no_behavior_pass_count():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_m1_contracts.py")],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["behavior_status"] == "planned-not-executed"
    assert report["approval_status"] == "pending"
    assert report["planned_acceptance_cases"] == 24
    assert not any("passed" in key for key in report)


@pytest.mark.parametrize(
    "sql",
    [
        "CREATE TEMP TABLE escape(value TEXT);",
        "CREATE TEMPORARY TABLE escape(value TEXT);",
        "CREATE TABLE temp.escape(value TEXT);",
        "CREATE TEMP VIEW escape AS SELECT 1;",
        "CREATE TABLE original(value); CREATE TEMP TRIGGER escape AFTER INSERT ON original "
        "BEGIN DELETE FROM original; END;",
        "CREATE TABLE escape AS SELECT 1 AS value;",
        "CREATE TABLE original(value); INSERT INTO original SELECT 1;",
        "SELECT * FROM temp.sqlite_schema;",
        "WITH RECURSIVE sequence(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM sequence) "
        "SELECT x FROM sequence ORDER BY x DESC;",
    ],
)
def test_fixture_sql_rejects_temp_objects_and_select_based_temp_work(sql):
    # Refuse at statement authorization, without allocating large temporary data.
    with pytest.raises(ValueError, match="forbidden I/O"):
        CHECKER["fixture_connection"](sql)


def test_schema_reference_cannot_target_openapi_metadata_string(contracts):
    from fastapi.openapi.models import OpenAPI

    target = contracts["api"]["components"]["schemas"]["RunPage"]["properties"]["items"]["items"]
    target["$ref"] = "#/info/title"
    # The installed structural model alone does not resolve this reference.
    OpenAPI.model_validate(contracts["api"])
    with pytest.raises(ValueError, match="Unsupported reference target.*RunPage"):
        CHECKER["check"](
            contracts["api"], contracts["data"], contracts["models"], contracts["database"]
        )


@pytest.mark.parametrize("value", ["not a schema", 42, None, [], {"type": "string"}])
def test_m1_schema_targets_require_direct_object_schema_shape(contracts, value):
    schemas = contracts["api"]["components"]["schemas"]
    schemas["WrongShape"] = value
    schemas["RunPage"]["properties"]["items"]["items"]["$ref"] = "#/components/schemas/WrongShape"
    with pytest.raises(ValueError, match="Invalid schema reference target"):
        CHECKER["check"](
            contracts["api"], contracts["data"], contracts["models"], contracts["database"]
        )


@pytest.mark.parametrize("value", [True, False])
def test_boolean_schema_reference_targets_are_explicitly_outside_m1_profile(contracts, value):
    schemas = contracts["api"]["components"]["schemas"]
    schemas["BooleanSchema"] = value
    schemas["RunPage"]["properties"]["items"]["items"]["$ref"] = (
        "#/components/schemas/BooleanSchema"
    )
    with pytest.raises(ValueError, match="Boolean schema target.*M1 reference profile"):
        CHECKER["check"](
            contracts["api"], contracts["data"], contracts["models"], contracts["database"]
        )


def test_schema_reference_in_non_schema_context_is_rejected(contracts):
    contracts["api"]["info"]["x-reference"] = {"$ref": "#/components/schemas/Error"}
    with pytest.raises(ValueError, match="Unsupported reference context.*schema slot"):
        CHECKER["check"](
            contracts["api"], contracts["data"], contracts["models"], contracts["database"]
        )


def test_reference_aliases_require_an_explicit_profile_extension(contracts):
    schemas = contracts["api"]["components"]["schemas"]
    schemas["Alias"] = {"$ref": "#/components/schemas/RunSummary"}
    schemas["RunPage"]["properties"]["items"]["items"]["$ref"] = "#/components/schemas/Alias"
    with pytest.raises(ValueError, match="direct object with properties"):
        CHECKER["check"](
            contracts["api"], contracts["data"], contracts["models"], contracts["database"]
        )
