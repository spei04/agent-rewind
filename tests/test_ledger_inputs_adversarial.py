"""Adversarial ledger intent/provenance tests; no SQL or provisioning acceptance."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from ledger_fixture import (
    DialectOnlyConnection,
    canonical_bytes,
    digest,
    initial_bundle,
    manifest,
    progress_row,
)
from pydantic import ValidationError

from agent_rewind.migrations import ledger_inputs
from agent_rewind.migrations.ledger_inputs import read_ledger_manifest, validate_ledger_manifest
from agent_rewind.migrations.ledger_state import (
    validate_ledger_chain,
    validate_manifest_cursor,
    validate_opening_cursor,
    validate_progress_row,
)
from agent_rewind.migrations.schema import MigrationRefused


def changed(raw, path, value):
    result = deepcopy(raw)
    target = result
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    return result


def refused(code):
    return pytest.raises(MigrationRefused, match=f"^{code}$")


def write_private(path, raw):
    path.write_bytes(raw)
    path.chmod(0o600)
    return path


def test_independent_manifest_canonicalization_and_defensive_immutability():
    raw = manifest()
    expected = canonical_bytes(raw)
    value = validate_ledger_manifest(raw)
    assert value.canonical_bytes == expected
    assert value.digest == digest(raw)
    assert value.model_dump(mode="json") == raw
    assert isinstance(value.accounts, tuple)
    assert isinstance(value.opening_accounts.projects, tuple)

    raw["accounts"][0]["limit_microusd"] = 0
    raw["opening_accounts"]["projects"].clear()
    dumped = value.model_dump(mode="json")
    dumped["accounts"].clear()
    assert value.canonical_bytes == expected
    with pytest.raises(ValidationError, match="frozen_instance"):
        value.accounts[0].limit_microusd = 0
    with pytest.raises(ValidationError, match="frozen_instance"):
        value.opening_accounts.organization_account_id = None
    with pytest.raises(AttributeError):
        value.accounts.append(value.accounts[0])


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("schema_version",), True),
        (("schema_version",), "1"),
        (("schema_version",), 1.0),
        (("schema_version",), 2),
        (("installation_key",), ""),
        (("installation_key",), "-untrusted"),
        (("installation_key",), "é"),
        (("installation_key",), "a" * 65),
        (("manifest_id",), "A" * 32),
        (("manifest_id",), "0" * 31),
        (("manifest_id",), "0" * 32 + "\n"),
        (("source_digest",), "g" * 64),
        (("source_digest",), b"0" * 64),
        (("backup_evidence_digest",), None),
        (("drain_evidence_digest",), "0" * 63),
        (("parent_manifest_digest",), "4" * 64),
        (("operation",), "INITIALIZE"),
        (("opening_accounts",), None),
        (("accounts", 0, "limit_microusd"), True),
        (("accounts", 0, "limit_microusd"), 1.0),
        (("accounts", 0, "limit_microusd"), "1"),
        (("accounts", 0, "limit_microusd"), -1),
        (("accounts", 0, "limit_microusd"), 2**63),
        (("accounts", 0, "project_id"), "1" * 32),
        (("accounts", 0, "job_id"), "1" * 32),
        (("accounts", 0, "scope_id"), "2" * 32),
        (("accounts", 1, "project_id"), None),
        (("accounts", 1, "job_id"), "1" * 32),
        (("accounts", 2, "job_id"), None),
        (("accounts", 2, "organization_id"), "9" * 32),
        (("accounts", 0, "period_start"), "2026-01-01T00:00:00Z"),
        (("accounts", 0, "period_start"), "2026-01-01T00:00:00.000000+00:00"),
        (("accounts", 0, "period_start"), "2026-02-29T00:00:00.000000Z"),
        (("accounts", 0, "period_start"), "2026-01-01T00:00:60.000000Z"),
        (("accounts", 0, "period_start"), "0000-01-01T00:00:00.000000Z"),
        (("accounts", 0, "period_end"), "2026-01-01T00:00:00.000000Z"),
        (("opening_accounts", "organization_account_id"), None),
        (("opening_accounts", "projects", 0, "account_id"), "f" * 32),
        (("opening_accounts", "projects", 0, "project_id"), "f" * 32),
    ],
)
def test_manifest_semantic_attacks_have_fixed_refusal(path, value):
    raw = manifest()
    validate_ledger_manifest(raw)
    with refused("invalid_ledger_manifest"):
        validate_ledger_manifest(changed(raw, path, value))


@pytest.mark.parametrize(
    "path",
    [(key,) for key in manifest()]
    + [("accounts", 0, key) for key in manifest()["accounts"][0]]
    + [("opening_accounts", key) for key in manifest()["opening_accounts"]]
    + [
        ("opening_accounts", "projects", 0, key)
        for key in manifest()["opening_accounts"]["projects"][0]
    ],
)
def test_every_manifest_member_is_required_including_explicit_nulls(path):
    raw = manifest()
    validate_ledger_manifest(raw)
    target = raw
    for part in path[:-1]:
        target = target[part]
    del target[path[-1]]
    with refused("invalid_ledger_manifest"):
        validate_ledger_manifest(raw)


@pytest.mark.parametrize("path", [(), ("accounts", 0), ("opening_accounts",)])
def test_unknown_authority_or_balance_members_are_not_accepted(path):
    raw = manifest()
    target = raw
    for part in path:
        target = target[part]
    target["operator_approved"] = True
    with refused("invalid_ledger_manifest"):
        validate_ledger_manifest(raw)


@pytest.mark.parametrize("kind", ["tuple", "mapping", "integer-key", "nested-control", "surrogate"])
def test_object_entry_requires_exact_json_native_values(kind):
    raw = manifest()
    if kind == "tuple":
        raw["accounts"] = tuple(raw["accounts"])
    elif kind == "mapping":
        raw = SimpleNamespace(**raw)
    elif kind == "integer-key":
        raw[1] = "untrusted"
    elif kind == "nested-control":
        raw["accounts"][0]["scope_id"] = "\x00" + "0" * 31
    else:
        raw["installation_key"] = "\ud800"
    with refused("invalid_ledger_manifest"):
        validate_ledger_manifest(raw)


@pytest.mark.parametrize("variant", ["reverse", "duplicate", "duplicate-job", "missing-project"])
def test_account_order_identity_and_opening_coverage(variant):
    raw = manifest()
    if variant == "reverse":
        raw["accounts"].reverse()
    elif variant == "duplicate":
        raw["accounts"].append(deepcopy(raw["accounts"][-1]))
    elif variant == "duplicate-job":
        raw["accounts"][-1]["job_id"] = raw["accounts"][-2]["job_id"]
        raw["accounts"][-1]["scope_id"] = raw["accounts"][-2]["scope_id"]
    else:
        raw["opening_accounts"]["projects"].clear()
    with refused("invalid_ledger_manifest"):
        validate_ledger_manifest(raw)


@pytest.mark.parametrize(
    "token",
    [b"-0", b"1.0", b"1e0", b"1E+0", b"NaN", b"Infinity", b"-Infinity", b"01", b"+1"],
)
def test_file_numeric_tokens_are_checked_before_json_erases_them(tmp_path, token):
    raw = canonical_bytes(manifest())
    assert b'"limit_microusd":1000000' in raw
    raw = raw.replace(b'"limit_microusd":1000000', b'"limit_microusd":' + token, 1)
    path = write_private(tmp_path / "private-manifest.json", raw)
    with refused("invalid_ledger_manifest_file") as error:
        read_ledger_manifest(path)
    assert str(path) not in str(error.value)


@pytest.mark.parametrize("variant", ["top-duplicate", "escaped-duplicate", "nested-duplicate"])
def test_duplicate_keys_refuse_even_when_values_match(tmp_path, variant):
    raw = canonical_bytes(manifest())
    if variant == "top-duplicate":
        raw = raw[:-1] + b',"schema_version":1}'
    elif variant == "escaped-duplicate":
        raw = raw[:-1] + b',"schema_\\u0076ersion":1}'
    else:
        raw = raw.replace(
            b'"limit_microusd":1000000',
            b'"limit_microusd":1000000,"limit_microusd":1000000',
            1,
        )
    with refused("invalid_ledger_manifest_file"):
        read_ledger_manifest(write_private(tmp_path / "intent.json", raw))


@pytest.mark.parametrize(
    "raw",
    [b"\xef\xbb\xbf{}", b"\xff{}", b'{"x":"\xff"}', b'{"x":"\\u0000"}', b"[" * 9 + b"]" * 9],
)
def test_unsafe_encoding_control_and_depth_are_lexical_failures(tmp_path, raw):
    with refused("invalid_ledger_manifest_file"):
        read_ledger_manifest(write_private(tmp_path / "intent.json", raw))


def test_lexically_valid_wrong_shape_is_semantic_not_file_failure(tmp_path):
    raw = canonical_bytes(changed(manifest(), ("schema_version",), True))
    with refused("invalid_ledger_manifest"):
        read_ledger_manifest(write_private(tmp_path / "intent.json", raw))


@pytest.mark.parametrize("mode", [0o000, 0o200, 0o640, 0o604, 0o444, 0o777])
def test_file_requires_owner_read_and_no_group_or_other_access(tmp_path, mode):
    path = write_private(tmp_path / "intent.json", canonical_bytes(manifest()))
    path.chmod(mode)
    try:
        with refused("invalid_ledger_manifest_file"):
            read_ledger_manifest(path)
    finally:
        path.chmod(0o600)


@pytest.mark.parametrize("mode", [0o400, 0o600])
def test_private_file_whitespace_and_member_order_preserve_intent(tmp_path, mode):
    import json

    raw = manifest()
    wire = json.dumps(dict(reversed(list(raw.items()))), indent=2).encode()
    path = write_private(tmp_path / "intent.json", wire)
    path.chmod(mode)
    result = read_ledger_manifest(path)
    assert result.digest == digest(raw)
    assert result.canonical_bytes == canonical_bytes(raw)


@pytest.mark.parametrize("kind", ["symlink", "directory", "fifo", "missing"])
def test_nonregular_or_missing_final_path_refuses_without_blocking(tmp_path, kind):
    path = tmp_path / "unsafe"
    if kind == "symlink":
        target = write_private(tmp_path / "target", canonical_bytes(manifest()))
        path.symlink_to(target)
    elif kind == "directory":
        path.mkdir()
    elif kind == "fifo":
        ledger_inputs.os.mkfifo(path, 0o600)
    with refused("invalid_ledger_manifest_file"):
        read_ledger_manifest(path)


def test_file_observed_owner_must_match_invoking_uid(tmp_path, monkeypatch):
    path = write_private(tmp_path / "intent.json", canonical_bytes(manifest()))
    observed = ledger_inputs.os.fstat

    def foreign_owner(descriptor):
        value = observed(descriptor)
        return SimpleNamespace(
            st_mode=value.st_mode, st_size=value.st_size, st_uid=value.st_uid + 1
        )

    monkeypatch.setattr(ledger_inputs.os, "fstat", foreign_owner)
    with refused("invalid_ledger_manifest_file"):
        read_ledger_manifest(path)


def test_receipts_preserve_exact_opening_and_do_not_acknowledge_a_commit():
    raw, cursor, opening = initial_bundle()
    connection = DialectOnlyConnection()
    value = validate_manifest_cursor(connection, cursor)
    original = validate_opening_cursor(opening)
    result = validate_ledger_chain((value,), original)
    assert result.model_dump(mode="json") == {
        "installation_key": raw["installation_key"],
        "revision": "ar_0007_ledger",
        "manifest_id": raw["manifest_id"],
        "manifest_digest": digest(raw),
        "sequence": 0,
        "operation": "initialize",
        "source_digest": raw["source_digest"],
        "account_rows": 4,
        "imported_jobs": 2,
        "imported_opening_microusd": 245_000,
        "initialized_at": cursor["initialized_at"],
    }
    assert "outcome" not in result.model_dump()
    cursor["manifest"]["accounts"].clear()
    opening["jobs"].clear()
    assert len(value.manifest.accounts) == 4
    assert len(original.jobs) == 2
    with pytest.raises(ValidationError, match="frozen_instance"):
        original.jobs[0].legacy_reserved_microusd = 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", True),
        ("manifest_digest", "0" * 64),
        ("sequence", 1),
        ("parent_manifest_digest", "f" * 64),
        ("account_count", 3),
        ("imported_jobs", 1),
        ("os_uid", True),
        ("os_uid", -1),
        ("os_uid", 2**63),
        ("database_role", "invented-sqlite-role"),
        ("initialized_at", "2026-01-15T12:00:00Z"),
        ("account_projection_digest", "x" * 64),
    ],
)
def test_manifest_cursor_rejects_type_and_binding_drift(field, value):
    _, cursor, _ = initial_bundle()
    connection = DialectOnlyConnection()
    validate_manifest_cursor(connection, cursor)
    cursor[field] = value
    with refused("ledger_progress_invalid"):
        validate_manifest_cursor(connection, cursor)


@pytest.mark.parametrize(
    ("role", "accepted"),
    [(None, False), ("", False), ("é" * 31 + "a", True), ("é" * 32, False), ("owner\n", False)],
)
def test_postgres_role_uses_utf8_bytes_and_actual_dialect_seam(role, accepted):
    _, cursor, _ = initial_bundle()
    cursor["database_role"] = role
    connection = DialectOnlyConnection("postgresql")
    if accepted:
        assert validate_manifest_cursor(connection, cursor).database_role == role
    else:
        with refused("ledger_progress_invalid"):
            validate_manifest_cursor(connection, cursor)


@pytest.mark.parametrize("opening", [False, True])
@pytest.mark.parametrize("postgres", [False, True])
def test_native_progress_rows_bind_both_cursor_kinds_and_dialects(opening, postgres):
    _, cursor, receipt = initial_bundle()
    cursor["database_role"] = "ledger_owner" if postgres else None
    raw = receipt if opening else cursor
    connection = DialectOnlyConnection("postgresql" if postgres else "sqlite")
    row = progress_row(raw, opening=opening, postgres=postgres)
    expected = (
        validate_opening_cursor(raw) if opening else validate_manifest_cursor(connection, raw)
    )
    assert validate_progress_row(connection, row) == expected
    if postgres:
        row["updated_at"] = row["updated_at"].astimezone(timezone(timedelta(hours=5, minutes=30)))
        assert validate_progress_row(connection, row) == expected


@pytest.mark.parametrize("opening", [False, True])
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("revision", "ar_0006_admission"),
        ("phase", "unknown_ledger_phase"),
        ("source_digest", "f" * 64),
        ("rows_verified", True),
        ("rows_verified", -1),
        ("status", "pending"),
        ("cursor", b"{}"),
        ("cursor", {}),
        ("updated_at", datetime(2026, 1, 15, 12, tzinfo=UTC)),
        ("updated_at", "2026-01-15T12:00:01.000000Z"),
    ],
)
def test_native_row_drift_refuses_before_exposing_receipt(opening, field, value):
    _, cursor, receipt = initial_bundle()
    row = progress_row(receipt if opening else cursor, opening=opening)
    connection = DialectOnlyConnection()
    validate_progress_row(connection, row)
    row[field] = value
    with refused("ledger_progress_invalid"):
        validate_progress_row(connection, row)


@pytest.mark.parametrize("value", [datetime(2026, 1, 15, 12), "2026-01-15T12:00:00.000000Z"])
def test_postgres_progress_timestamp_requires_native_aware_datetime(value):
    _, cursor, _ = initial_bundle()
    cursor["database_role"] = "ledger_owner"
    row = progress_row(cursor, postgres=True)
    row["updated_at"] = value
    with refused("ledger_progress_invalid"):
        validate_progress_row(DialectOnlyConnection("postgresql"), row)


@pytest.mark.parametrize("variant", ["missing-column", "extra-column", "duplicate-cursor-key"])
def test_progress_row_has_exact_columns_and_lexically_valid_native_cursor(variant):
    _, cursor, _ = initial_bundle()
    row = progress_row(cursor)
    if variant == "missing-column":
        del row["source_digest"]
    elif variant == "extra-column":
        row["actor"] = "trusted"
    else:
        row["cursor"] = row["cursor"][:-1] + ',"sequence":0}'
    with refused("ledger_progress_invalid"):
        validate_progress_row(DialectOnlyConnection(), row)
