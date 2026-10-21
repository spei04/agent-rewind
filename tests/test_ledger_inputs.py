"""Strict input and durable-provenance value checks, without provisioning SQL."""

import copy
import hashlib
import json
import os

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine

from agent_rewind.migrations.ledger_inputs import (
    decode_ledger_json,
    read_ledger_manifest,
    validate_ledger_manifest,
)
from agent_rewind.migrations.ledger_state import (
    validate_ledger_chain,
    validate_manifest_cursor,
    validate_opening_cursor,
    validate_progress_row,
)
from agent_rewind.migrations.schema import MigrationRefused, canonical, checksum

TIME = "2026-10-21T00:00:00.000000Z"


def identifier(number):
    return f"{number:032x}"


def intent():
    organization, project = identifier(90), identifier(91)
    accounts = []
    for number, scope, owner in [
        (1, "organization", organization),
        (2, "project", project),
        (3, "job", identifier(93)),
        (4, "job", identifier(94)),
        (5, "job", identifier(95)),
    ]:
        accounts.append(
            {
                "id": identifier(number),
                "organization_id": organization,
                "scope": scope,
                "scope_id": owner,
                "project_id": None if scope == "organization" else project,
                "job_id": owner if scope == "job" else None,
                "period_start": "2026-01-01T00:00:00.000000Z",
                "period_end": "2027-01-01T00:00:00.000000Z",
                "limit_microusd": 500000,
            }
        )
    return {
        "schema_version": 1,
        "installation_key": "synthetic-ledger",
        "manifest_id": identifier(99),
        "operation": "initialize",
        "source_digest": "a" * 64,
        "parent_manifest_digest": None,
        "backup_evidence_digest": "b" * 64,
        "drain_evidence_digest": "c" * 64,
        "accounts": accounts,
        "opening_accounts": {
            "organization_account_id": identifier(1),
            "projects": [{"project_id": project, "account_id": identifier(2)}],
        },
    }


def receipts():
    raw = intent()
    manifest = validate_ledger_manifest(raw)
    amounts = [125000, 85000, 35000]
    jobs = [
        {
            "job_id": account["job_id"],
            "project_id": account["project_id"],
            "budget_microusd": 500000,
            "legacy_reserved_microusd": amount,
        }
        for account, amount in zip(raw["accounts"][2:], amounts, strict=True)
    ]
    projection = [
        {**account, "opening_held_microusd": amount}
        for account, amount in zip(raw["accounts"], [245000, 245000, *amounts], strict=True)
    ]
    cursor = {
        "schema_version": 1,
        "manifest": raw,
        "manifest_digest": manifest.digest,
        "sequence": 0,
        "parent_manifest_digest": None,
        "database_role": None,
        "os_uid": os.getuid(),
        "initialized_at": TIME,
        "account_projection_digest": checksum(projection),
        "account_count": 5,
        "imported_jobs": 3,
        "imported_opening_microusd": 245000,
    }
    opening = {
        "schema_version": 1,
        "manifest_id": manifest.manifest_id,
        "manifest_digest": manifest.digest,
        "source_digest": manifest.source_digest,
        "initialized_at": TIME,
        "jobs": jobs,
        "jobs_digest": checksum(jobs),
        "project_totals": [
            {
                "project_id": identifier(91),
                "account_id": identifier(2),
                "opening_held_microusd": 245000,
            }
        ],
        "organization_account_id": identifier(1),
        "organization_opening_microusd": 245000,
        "job_count": 3,
    }
    return cursor, opening


@pytest.fixture
def connection():
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        yield connection
    engine.dispose()


def test_manifest_snapshot_is_deeply_immutable_and_canonical():
    raw = intent()
    value = validate_ledger_manifest(raw)
    original = value.canonical_bytes
    raw["accounts"][0]["limit_microusd"] = 0
    assert value.accounts[0].limit_microusd == 500000
    assert value.digest == hashlib.sha256(original).hexdigest()
    assert original == canonical(value.model_dump(mode="json"))
    assert isinstance(value.accounts, tuple)
    assert isinstance(value.opening_accounts.projects, tuple)
    with pytest.raises(ValidationError):
        value.accounts[0].limit_microusd = 1
    with pytest.raises(ValidationError):
        value.opening_accounts.projects[0].account_id = identifier(8)


@pytest.mark.parametrize("value", [True, 1.0, "1", -1, 2**63])
def test_money_does_not_coerce(value):
    raw = intent()
    raw["accounts"][0]["limit_microusd"] = value
    with pytest.raises(MigrationRefused, match="invalid_ledger_manifest"):
        validate_ledger_manifest(raw)


@pytest.mark.parametrize(
    "updates",
    [
        {"scope_id": identifier(80)},
        {"project_id": identifier(91)},
        {"period_end": "2026-01-01T00:00:00.000000Z"},
        {"period_start": "2026-02-29T00:00:00.000000Z"},
        {"period_start": "2026-01-01T00:00:00+00:00"},
        {"period_start": "2026-01-01T00:00:60.000000Z"},
        {"id": "A" * 32},
        {"id": "a" * 32 + "\n"},
        {"limit_microusd": None},
        {"held_microusd": 0},
    ],
)
def test_invalid_account_refuses(updates):
    raw = intent()
    raw["accounts"][0].update(updates)
    with pytest.raises(MigrationRefused, match="invalid_ledger_manifest"):
        validate_ledger_manifest(raw)


@pytest.mark.parametrize("member", list(intent()))
def test_every_top_level_member_is_explicit(member):
    raw = intent()
    del raw[member]
    with pytest.raises(MigrationRefused, match="invalid_ledger_manifest"):
        validate_ledger_manifest(raw)


def test_initialize_empty_is_explicit_and_provision_cannot_be_empty():
    raw = intent()
    raw["accounts"] = []
    raw["opening_accounts"] = {"organization_account_id": None, "projects": []}
    assert validate_ledger_manifest(raw).accounts == ()
    raw.update(operation="provision", opening_accounts=None, parent_manifest_digest="d" * 64)
    with pytest.raises(MigrationRefused, match="invalid_ledger_manifest"):
        validate_ledger_manifest(raw)


def test_half_open_period_endpoints_are_allowed_but_overlap_refuses():
    raw = intent()
    new = copy.deepcopy(raw["accounts"][0])
    new.update(
        id=identifier(6), period_start=new["period_end"], period_end="2028-01-01T00:00:00.000000Z"
    )
    raw["accounts"].append(new)
    assert len(validate_ledger_manifest(raw).accounts) == 6
    new["period_start"] = "2026-12-31T23:59:59.999999Z"
    with pytest.raises(MigrationRefused, match="invalid_ledger_manifest"):
        validate_ledger_manifest(raw)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"x":1,"x":2}',
        b'{"x":-0}',
        b'{"x":1.0}',
        b'{"x":1e0}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":"\\u0000"}',
        b"\xef\xbb\xbf{}",
        b'{"x":"\xff"}',
        b"[" * 9 + b"0" + b"]" * 9,
    ],
)
def test_lexical_refusals(raw):
    with pytest.raises(ValueError):
        decode_ledger_json(raw, maximum=32768)


def test_eight_nested_arrays_and_quoted_brackets_are_not_conflated():
    assert decode_ledger_json(b"[" * 8 + b"0" + b"]" * 8, maximum=32768)
    assert decode_ledger_json(b'{"x":"[[[\\"["}', maximum=32768) == {"x": '[[["['}


def test_private_file_round_trip_and_symlink_refusal(tmp_path):
    path = tmp_path / "intent.json"
    path.write_bytes(canonical(intent()))
    path.chmod(0o600)
    assert read_ledger_manifest(path).digest == validate_ledger_manifest(intent()).digest
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(MigrationRefused, match="invalid_ledger_manifest_file"):
        read_ledger_manifest(link)
    path.chmod(0o640)
    with pytest.raises(MigrationRefused, match="invalid_ledger_manifest_file"):
        read_ledger_manifest(path)


def test_opening_245000_receipt_and_progress_binding(connection):
    raw, raw_opening = receipts()
    cursor = validate_manifest_cursor(connection, raw)
    opening = validate_opening_cursor(raw_opening)
    receipt = validate_ledger_chain((cursor,), opening)
    assert receipt.imported_opening_microusd == 245000
    assert not hasattr(receipt, "outcome")
    row = {
        "revision": "ar_0007_ledger",
        "phase": "ledger_manifest_" + cursor.manifest.manifest_id,
        "source_digest": cursor.manifest.source_digest,
        "cursor": canonical(raw).decode("ascii"),
        "rows_verified": 5,
        "status": "complete",
        "updated_at": TIME,
    }
    assert validate_progress_row(connection, row) == cursor
    row["rows_verified"] = 4
    with pytest.raises(MigrationRefused, match="ledger_progress_invalid"):
        validate_progress_row(connection, row)


@pytest.mark.parametrize(
    "field,value",
    [
        ("manifest_digest", "f" * 64),
        ("sequence", 1),
        ("database_role", "owner"),
        ("account_count", 4),
        ("parent_manifest_digest", "e" * 64),
        ("schema_version", True),
        ("initialized_at", "2026-02-30T00:00:00.000000Z"),
    ],
)
def test_manifest_cursor_exact_bindings(connection, field, value):
    raw, _ = receipts()
    raw[field] = value
    with pytest.raises(MigrationRefused, match="ledger_progress_invalid"):
        validate_manifest_cursor(connection, raw)


def test_opening_aggregate_and_immutable_projection_both_required(connection):
    raw, raw_opening = receipts()
    opening = validate_opening_cursor(raw_opening)
    raw["account_projection_digest"] = "f" * 64
    cursor = validate_manifest_cursor(connection, raw)
    with pytest.raises(MigrationRefused, match="ledger_progress_invalid"):
        validate_ledger_chain((cursor,), opening)
    raw_opening["organization_opening_microusd"] = 244999
    with pytest.raises(MigrationRefused, match="ledger_progress_invalid"):
        validate_opening_cursor(raw_opening)


def test_cursor_lexical_duplicate_is_not_lost_to_json_binding(connection):
    raw, _ = receipts()
    row = {
        "revision": "ar_0007_ledger",
        "phase": "ledger_manifest_" + raw["manifest"]["manifest_id"],
        "source_digest": raw["manifest"]["source_digest"],
        "cursor": json.dumps(raw)[:-1] + ',"account_count":5}',
        "rows_verified": 5,
        "status": "complete",
        "updated_at": TIME,
    }
    with pytest.raises(MigrationRefused, match="ledger_progress_invalid"):
        validate_progress_row(connection, row)
