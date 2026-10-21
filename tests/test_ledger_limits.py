"""Supported input/chain boundaries only; no database or throughput proof."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from ledger_fixture import (
    MAX_MONEY,
    DialectOnlyConnection,
    canonical_bytes,
    cursor_for,
    digest,
    disjoint_accounts,
    identifier,
    initial_bundle,
    manifest,
    opening_for,
    progress_row,
    provision,
)

from agent_rewind.migrations import ledger_inputs
from agent_rewind.migrations.ledger_inputs import read_ledger_manifest, validate_ledger_manifest
from agent_rewind.migrations.ledger_state import (
    validate_ledger_chain,
    validate_manifest_cursor,
    validate_opening_cursor,
    validate_progress_row,
)
from agent_rewind.migrations.schema import MigrationRefused


def values(raws, opening):
    connection = DialectOnlyConnection()
    cursors = tuple(
        validate_manifest_cursor(
            connection, cursor_for(raw, sequence=index, opening=opening if index == 0 else None)
        )
        for index, raw in enumerate(raws)
    )
    return cursors, validate_opening_cursor(opening)


@pytest.mark.parametrize(("projects", "jobs", "accounts"), [(15, 48, 64), (16, 16, 33)])
def test_supported_simultaneous_input_boundaries_are_actually_valid(projects, jobs, accounts):
    raw = manifest(projects=projects, jobs=jobs)
    parsed = validate_ledger_manifest(raw)
    assert len(parsed.accounts) == accounts
    assert len(parsed.canonical_bytes) < 32_768
    opening = opening_for(raw)
    cursors, receipts = values([raw], opening)
    result = validate_ledger_chain(cursors, receipts)
    assert result.account_rows == accounts
    assert result.imported_jobs == jobs
    assert result.imported_opening_microusd == 0


@pytest.mark.parametrize(("projects", "jobs"), [(16, 48), (17, 17), (1, 49)])
def test_one_over_each_independent_input_cardinality_refuses(projects, jobs):
    raw = manifest(projects=projects, jobs=jobs)
    assert len(canonical_bytes(raw)) < 32_768
    with pytest.raises(MigrationRefused, match="^invalid_ledger_manifest$"):
        validate_ledger_manifest(raw)


@pytest.mark.parametrize("amount", [0, 2**53 + 1, MAX_MONEY])
def test_money_remains_exact_through_manifest_opening_chain_and_receipt(amount):
    raw = manifest()
    for row in raw["accounts"]:
        row["limit_microusd"] = MAX_MONEY
    opening = opening_for(raw, amounts=[amount, 0])
    cursors, receipts = values([raw], opening)
    result = validate_ledger_chain(cursors, receipts)
    assert type(result.imported_opening_microusd) is int
    assert result.imported_opening_microusd == amount
    assert digest(raw) == cursors[0].manifest_digest


def test_individually_valid_project_totals_cannot_hide_organization_overflow():
    raw = manifest(projects=2)
    for row in raw["accounts"]:
        row["limit_microusd"] = MAX_MONEY
    opening = opening_for(raw, amounts=[MAX_MONEY, 1])
    assert all(row["opening_held_microusd"] <= MAX_MONEY for row in opening["project_totals"])
    # A saturated persisted organization total must not hide the actual checked sum.
    opening["organization_opening_microusd"] = MAX_MONEY
    with pytest.raises(MigrationRefused, match="^ledger_progress_invalid$"):
        validate_opening_cursor(opening)


@pytest.mark.parametrize("extra", [0, 1])
def test_manifest_file_raw_byte_limit_is_independent_of_canonical_size(tmp_path, extra):
    raw = canonical_bytes(manifest())
    wire = raw + b" " * (32_768 + extra - len(raw))
    path = tmp_path / "intent.json"
    path.write_bytes(wire)
    path.chmod(0o600)
    if extra:
        with pytest.raises(MigrationRefused, match="^invalid_ledger_manifest_file$"):
            read_ledger_manifest(path)
    else:
        assert read_ledger_manifest(path).canonical_bytes == raw


def test_manifest_read_is_bounded_even_when_pre_read_file_size_is_stale(tmp_path, monkeypatch):
    path = tmp_path / "growing.json"
    path.write_bytes(canonical_bytes(manifest()) + b" " * 40_000)
    path.chmod(0o600)
    original_stat = ledger_inputs.os.fstat
    original_open = ledger_inputs.os.fdopen
    reads = []

    def stale_size(descriptor):
        info = original_stat(descriptor)
        return SimpleNamespace(st_mode=info.st_mode, st_uid=info.st_uid, st_size=0)

    class ObservedStream:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def fileno(self):
            return self.stream.fileno()

        def read(self, count=-1):
            reads.append(count)
            return self.stream.read(count)

    def observed_open(*args, **kwargs):
        return ObservedStream(original_open(*args, **kwargs))

    monkeypatch.setattr(ledger_inputs.os, "fstat", stale_size)
    monkeypatch.setattr(ledger_inputs.os, "fdopen", observed_open)
    with pytest.raises(MigrationRefused, match="^invalid_ledger_manifest_file$"):
        read_ledger_manifest(path)
    assert reads == [32_769]


@pytest.mark.parametrize("postgres", [False, True])
@pytest.mark.parametrize("extra", [0, 1])
def test_progress_raw_utf8_byte_ceiling_before_decoding(postgres, extra):
    import json

    _, cursor, _ = initial_bundle()
    cursor["database_role"] = "é" if postgres else None
    connection = DialectOnlyConnection("postgresql" if postgres else "sqlite")
    row = progress_row(cursor, postgres=postgres)
    source = json.dumps(cursor, ensure_ascii=False)
    row["cursor"] = source + " " * (65_536 + extra - len(source.encode("utf-8")))
    assert len(row["cursor"].encode("utf-8")) == 65_536 + extra
    if extra:
        with pytest.raises(MigrationRefused, match="^ledger_progress_invalid$"):
            validate_progress_row(connection, row)
    else:
        assert validate_progress_row(connection, row).manifest_digest == digest(cursor["manifest"])


def test_full_256_manifest_chain_is_contiguous_and_receipt_has_no_commit_claim():
    initial = manifest(empty=True)
    opening = opening_for(initial)
    raws = [initial]
    for sequence in range(1, 256):
        raws.append(provision(raws[-1], sequence))
    cursors, receipts = values(raws, opening)
    result = validate_ledger_chain(cursors, receipts)
    assert result.sequence == 255
    assert result.manifest_digest == digest(raws[-1])
    assert "outcome" not in result.model_dump()
    with pytest.raises(MigrationRefused, match="^ledger_progress_invalid$"):
        validate_ledger_chain((), receipts)
    with pytest.raises(MigrationRefused, match="^ledger_progress_invalid$"):
        validate_ledger_chain((*cursors, cursors[-1]), receipts)


def test_global_4096_account_chain_bound_has_valid_independent_per_input_cohorts():
    initial = manifest(empty=True)
    opening = opening_for(initial)
    raws = [initial]
    for sequence in range(1, 65):
        raw = provision(raws[-1], sequence, rows=disjoint_accounts(sequence))
        assert len(raw["accounts"]) == 64
        assert len({row["project_id"] for row in raw["accounts"]}) == 16
        assert len(canonical_bytes(raw)) < 32_768
        raws.append(raw)
    cursors, receipts = values(raws, opening)
    assert sum(cursor.account_count for cursor in cursors) == 4096
    assert validate_ledger_chain(cursors, receipts).sequence == 64

    raw = provision(raws[-1], 65, rows=disjoint_accounts(65, count=1))
    extra = validate_manifest_cursor(DialectOnlyConnection(), cursor_for(raw, sequence=65))
    with pytest.raises(MigrationRefused, match="^ledger_limit_exceeded$"):
        validate_ledger_chain((*cursors, extra), receipts)


@pytest.mark.parametrize(
    "variant",
    [
        "gap",
        "fork",
        "duplicate-manifest-id",
        "other-installation",
        "repeated-account-id",
        "repeated-job-id",
        "overlapping-period",
        "second-organization",
        "projection-digest",
    ],
)
def test_individually_valid_cursors_do_not_authorize_an_impossible_chain(variant):
    initial, first, opening = initial_bundle()
    later = provision(initial, 1)
    if variant == "fork":
        later["parent_manifest_digest"] = "f" * 64
    elif variant == "duplicate-manifest-id":
        later["manifest_id"] = initial["manifest_id"]
    elif variant == "other-installation":
        later["installation_key"] = "other-installation"
    elif variant in {"repeated-account-id", "overlapping-period"}:
        later["accounts"] = [deepcopy(initial["accounts"][0])]
        if variant == "overlapping-period":
            later["accounts"][0]["id"] = identifier(500_000)
    elif variant == "repeated-job-id":
        later["accounts"] = [deepcopy(initial["accounts"][-1])]
        later["accounts"][0]["id"] = identifier(500_000)
    elif variant == "second-organization":
        later["accounts"][0]["organization_id"] = identifier(2)
    second = cursor_for(later, sequence=2 if variant == "gap" else 1)
    if variant == "projection-digest":
        second["account_projection_digest"] = "f" * 64
    connection = DialectOnlyConnection()
    cursors = tuple(validate_manifest_cursor(connection, item) for item in [first, second])
    receipt = validate_opening_cursor(opening)
    with pytest.raises(MigrationRefused, match="^ledger_progress_invalid$"):
        validate_ledger_chain(cursors, receipt)


@pytest.mark.parametrize("scope_index", [0, 1, 2])
def test_initial_opening_cannot_exceed_any_account_cap(scope_index):
    raw, _, _ = initial_bundle()
    raw["accounts"][scope_index]["limit_microusd"] = 119_999
    # Persisted original job budgets are independent SQL observations, not a rewrite of intent.
    opening = opening_for(raw, amounts=[120_000, 125_000])
    for job in opening["jobs"]:
        job["budget_microusd"] = 1_000_000
    opening["jobs_digest"] = digest(opening["jobs"])
    cursors, receipt = values([raw], opening)
    with pytest.raises(MigrationRefused, match="^ledger_progress_invalid$"):
        validate_ledger_chain(cursors, receipt)


def test_job_account_cannot_expand_the_original_gross_budget():
    raw, _, opening = initial_bundle()
    opening["jobs"][0]["budget_microusd"] = 999_999
    opening["jobs_digest"] = digest(opening["jobs"])
    cursors, receipt = values([raw], opening)
    with pytest.raises(MigrationRefused, match="^ledger_progress_invalid$"):
        validate_ledger_chain(cursors, receipt)


@pytest.mark.parametrize(
    "variant", ["unknown-job", "wrong-project", "wrong-destination", "other-source"]
)
def test_complete_opening_must_bind_the_original_manifest_and_job_cohort(variant):
    raw, cursor, opening = initial_bundle()
    if variant == "unknown-job":
        opening["jobs"][-1]["job_id"] = identifier(9999)
        opening["jobs_digest"] = digest(opening["jobs"])
    elif variant == "wrong-project":
        raw["accounts"][-1]["project_id"] = identifier(777)
        # Keep both cursors structurally valid while changing the initial scope binding.
        raw["accounts"][1]["project_id"] = identifier(777)
        raw["accounts"][1]["scope_id"] = identifier(777)
        raw["accounts"][2]["project_id"] = identifier(777)
        raw["opening_accounts"]["projects"][0]["project_id"] = identifier(777)
        cursor = cursor_for(raw, opening=opening)
        opening["manifest_digest"] = digest(raw)
    elif variant == "wrong-destination":
        opening["project_totals"][0]["account_id"] = identifier(777)
    else:
        opening["source_digest"] = "f" * 64
    parsed = validate_manifest_cursor(DialectOnlyConnection(), cursor)
    receipt = validate_opening_cursor(opening)
    with pytest.raises(MigrationRefused, match="^ledger_progress_invalid$"):
        validate_ledger_chain((parsed,), receipt)


def test_selected_initial_import_period_must_contain_the_persisted_observation():
    raw = manifest()
    for row in raw["accounts"][:2]:
        row["period_start"] = "2025-01-01T00:00:00.000000Z"
        row["period_end"] = "2025-02-01T00:00:00.000000Z"
    opening = opening_for(raw)
    cursors, receipts = values([raw], opening)
    with pytest.raises(MigrationRefused, match="^ledger_progress_invalid$"):
        validate_ledger_chain(cursors, receipts)
