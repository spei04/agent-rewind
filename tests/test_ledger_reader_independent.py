"""Independent full-state reader contracts, not partial-reader substitutions."""

import json
from copy import deepcopy
from datetime import datetime

import pytest
from ledger_fixture import canonical_bytes
from ledger_reader_fixture import (
    complete_ar6,
    original_rows,
    replace_progress,
    seed_ar7,
    sqlite_snapshot,
)
from legacy_fixture import assert_preserved_rows
from pydantic import ValidationError
from sqlalchemy import text

from agent_rewind.migrations.ledger_state import (
    LedgerState,
    validate_ledger_chain,
    validate_progress_row,
)
from agent_rewind.migrations.ledger_transaction import LedgerOutcome, ledger_transaction
from agent_rewind.migrations.schema import LEDGER, MigrationRefused, catalog, checksum


@pytest.fixture
def reader_case(request, tmp_path):
    legacy, ledger, empty = request.param
    case = complete_ar6(tmp_path / "reader.sqlite", legacy=legacy)
    try:
        if ledger:
            seed_ar7(case, empty_accounts=empty)
        yield case
    finally:
        case.dispose()


COMPLETE_CASES = [
    pytest.param((False, False, False), id="fresh-ar6"),
    pytest.param((True, False, False), id="legacy-ar6"),
    pytest.param((False, True, True), id="empty-ar7"),
    pytest.param((False, True, False), id="organization-ar7"),
    pytest.param((True, True, False), id="legacy-opening-ar7"),
]


@pytest.mark.parametrize("reader_case", COMPLETE_CASES, indirect=True)
def test_fixture_has_real_complete_history_and_preserved_original_rows(reader_case):
    """Fixture acceptance runs independently while reader implementation is absent."""
    case = reader_case
    assert original_rows(case.engine) == case.original_rows
    if case.legacy:
        if case.revision != LEDGER:
            assert_preserved_rows(case.path)
        with case.engine.connect() as connection:
            assert (
                connection.exec_driver_sql("SELECT sum(reserved) FROM jobs").scalar_one() == 245000
            )
    with case.engine.connect() as connection:
        adoption = dict(
            connection.exec_driver_sql("SELECT * FROM installation_adoptions").mappings().one()
        )
        assert adoption["installed_schema_fingerprint"] == checksum(catalog(connection))
        assert {
            key: value for key, value in adoption.items() if key != "installed_schema_fingerprint"
        } == {
            key: value
            for key, value in case.adoption.items()
            if key != "installed_schema_fingerprint"
        }
        prior = [
            tuple(row)
            for row in connection.execute(
                text(
                    "SELECT * FROM migration_progress WHERE revision<>:revision "
                    "ORDER BY revision,phase"
                ),
                {"revision": LEDGER},
            )
        ]
        assert prior == case.previous_progress
        if case.revision == LEDGER:
            rows = list(
                connection.execute(
                    text(
                        "SELECT * FROM migration_progress WHERE revision=:revision ORDER BY phase"
                    ),
                    {"revision": LEDGER},
                ).mappings()
            )
            parsed = [validate_progress_row(connection, dict(row)) for row in rows]
            manifests = [value for value in parsed if hasattr(value, "manifest")]
            opening = next(value for value in parsed if hasattr(value, "jobs"))
            receipt = validate_ledger_chain(manifests, opening)
            assert receipt.model_dump(mode="json") == case.expected["head"]
            assert opening.model_dump(mode="json") == case.expected["opening"]
            assert len(case.original_rows["jobs"]) == opening.job_count
            assert (
                connection.exec_driver_sql("SELECT count(*) FROM budget_accounts").scalar_one()
                == case.expected["account_count"]
            )


def inspect(case):
    # Deliberately not importorskip: missing implementation is an explicit error.
    from agent_rewind.migrations.ledger_inspection import inspect_ledger_state

    engine = case.operator_engine()
    outcome = LedgerOutcome()
    try:
        with ledger_transaction(engine, outcome) as connection:
            result = inspect_ledger_state(connection)
        assert outcome.commit_acknowledged and not outcome.cleanup_failed
        assert engine.pool.checkedout() == 0
        return result
    finally:
        engine.dispose()


@pytest.mark.parametrize("reader_case", COMPLETE_CASES, indirect=True)
def test_complete_reader_returns_exact_immutable_state_without_writes(reader_case):
    case = reader_case
    before = sqlite_snapshot(case.path)
    result = inspect(case)
    assert type(result) is LedgerState
    assert result.model_dump(mode="json") == case.expected
    assert set(type(result).model_fields) == {
        "status",
        "installation_key",
        "revision",
        "head",
        "manifest_count",
        "account_count",
        "opening",
    }
    with pytest.raises(ValidationError, match="frozen_instance"):
        result.status = "absent"
    assert sqlite_snapshot(case.path) == before


@pytest.mark.parametrize("reader_case", [COMPLETE_CASES[0], COMPLETE_CASES[4]], indirect=True)
def test_unrelated_bounded_unicode_progress_keys_tolerate_opaque_body(reader_case):
    case = reader_case
    with case.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO migration_progress "
                "(revision,phase,source_digest,cursor,rows_verified,status,updated_at) "
                "VALUES (:revision,:phase,:digest,:cursor,0,'complete',:time)"
            ),
            {
                "revision": "unrelated-雪",
                "phase": "phase-λ",
                "digest": "a" * 64,
                "cursor": "opaque-unrelated-body" * 100_000,
                "time": "2026-01-15T12:00:00+00:00",
            },
        )
    before = sqlite_snapshot(case.path)
    assert inspect(case).model_dump(mode="json") == case.expected
    assert sqlite_snapshot(case.path) == before


@pytest.mark.parametrize("reader_case", [COMPLETE_CASES[1]], indirect=True)
def test_historical_mapping_keeps_plain_json_loads_semantics(reader_case):
    case = reader_case
    with case.engine.begin() as connection:
        raw = connection.exec_driver_sql("SELECT mapping FROM installation_adoptions").scalar_one()
        mapping = json.loads(raw)
        # Existing mapping semantics accept repeated identical members.
        altered = '{"schema_version":1,' + canonical_bytes(mapping).decode()[1:]
        connection.execute(
            text("UPDATE installation_adoptions SET mapping=:mapping"), {"mapping": altered}
        )
    assert inspect(case).model_dump(mode="json") == case.expected


def refused(case, code):
    before = sqlite_snapshot(case.path)
    returned = []
    with pytest.raises(MigrationRefused, match="^" + code + "$") as error:
        returned.append(inspect(case))
    assert error.value.code == code
    assert returned == []
    assert sqlite_snapshot(case.path) == before


@pytest.mark.parametrize(
    "column,value,code",
    [
        ("installed_schema_fingerprint", "0" * 64, "schema_incompatible"),
        ("schema_fingerprint", "0" * 64, "adoption_metadata_drift"),
        ("source_baseline", "0" * 40, "adoption_metadata_drift"),
        ("mapping_digest", "0" * 64, "adoption_metadata_drift"),
        ("installation_key", "not allowed", "adoption_metadata_drift"),
    ],
)
@pytest.mark.parametrize("reader_case", [COMPLETE_CASES[0]], indirect=True)
def test_complete_catalog_does_not_mask_durable_adoption_drift(reader_case, column, value, code):
    with reader_case.engine.begin() as connection:
        connection.execute(
            text(f"UPDATE installation_adoptions SET {column}=:value"), {"value": value}
        )
    refused(reader_case, code)


@pytest.mark.parametrize(
    "revision,phase,code",
    [
        ("ar_0003_ownership", "ownership", "ownership_progress_invalid"),
        ("ar_0005_run_index", "run_index", "projection_progress_invalid"),
    ],
)
@pytest.mark.parametrize("variant", ["missing", "duplicate-json-member", "incomplete", "bad-time"])
@pytest.mark.parametrize("reader_case", [COMPLETE_CASES[1]], indirect=True)
def test_required_historical_progress_is_complete_and_strict(
    reader_case, revision, phase, code, variant
):
    with reader_case.engine.begin() as connection:
        keys = {"revision": revision, "phase": phase}
        where = " WHERE revision=:revision AND phase=:phase"
        if variant == "missing":
            result = connection.execute(text("DELETE FROM migration_progress" + where), keys)
        elif variant == "duplicate-json-member":
            value = connection.execute(
                text("SELECT cursor FROM migration_progress" + where), keys
            ).scalar_one()
            parsed = json.loads(value)
            assert parsed["schema_version"] == 1
            value = '{"schema_version":1,' + canonical_bytes(parsed).decode()[1:]
            result = connection.execute(
                text("UPDATE migration_progress SET cursor=:value" + where),
                {**keys, "value": value},
            )
        elif variant == "incomplete":
            result = connection.execute(
                text("UPDATE migration_progress SET status='running'" + where), keys
            )
        else:
            result = connection.execute(
                text("UPDATE migration_progress SET updated_at='not-a-time'" + where), keys
            )
        assert result.rowcount == 1
    refused(reader_case, code)


@pytest.mark.parametrize(
    "variant", ["manifest-digest", "opening-job-digest", "manifest-count", "missing-opening"]
)
@pytest.mark.parametrize("reader_case", [COMPLETE_CASES[4]], indirect=True)
def test_ar7_returns_no_partial_state_after_progress_or_chain_mismatch(reader_case, variant):
    case = reader_case
    if variant == "manifest-digest":
        cursor = deepcopy(case.cursor)
        cursor["manifest_digest"] = "0" * 64
        replace_progress(case, "ledger_manifest_" + case.manifest["manifest_id"], cursor)
    elif variant == "opening-job-digest":
        opening = deepcopy(case.opening)
        opening["jobs_digest"] = "0" * 64
        replace_progress(case, "ledger_opening", opening)
    elif variant == "manifest-count":
        with case.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE migration_progress SET rows_verified=rows_verified+1 "
                    "WHERE revision=:revision AND phase=:phase"
                ),
                {"revision": LEDGER, "phase": "ledger_manifest_" + case.manifest["manifest_id"]},
            )
    else:
        with case.engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM migration_progress WHERE revision=:revision "
                    "AND phase='ledger_opening'"
                ),
                {"revision": LEDGER},
            )
    refused(case, "ledger_progress_invalid")


@pytest.mark.parametrize("reader_case", [COMPLETE_CASES[0]], indirect=True)
def test_current_memberships_are_not_reconstructed_from_historical_grants(reader_case):
    with reader_case.engine.begin() as connection:
        before = connection.exec_driver_sql("SELECT count(*) FROM project_memberships").scalar_one()
        assert before > 0
        connection.exec_driver_sql("DELETE FROM project_memberships")
    assert inspect(reader_case).model_dump(mode="json") == reader_case.expected


@pytest.mark.parametrize("reader_case", [COMPLETE_CASES[0]], indirect=True)
def test_current_project_count_does_not_reapply_historical_128_project_cursor_limit(reader_case):
    with reader_case.engine.begin() as connection:
        seed = dict(connection.exec_driver_sql("SELECT * FROM projects").mappings().one())
        for number in range(2000, 2129):
            connection.execute(
                text(
                    "INSERT INTO projects(id,organization_id,name,created_at,run_sequence) "
                    "VALUES (:id,:organization,:name,:created,0)"
                ),
                {
                    "id": f"{number:032x}",
                    "organization": seed["organization_id"],
                    "name": "Later project",
                    "created": seed["created_at"],
                },
            )
        assert connection.exec_driver_sql("SELECT count(*) FROM projects").scalar_one() == 130
    assert inspect(reader_case).model_dump(mode="json") == reader_case.expected


@pytest.mark.parametrize("reader_case", [COMPLETE_CASES[4]], indirect=True)
def test_later_job_budget_growth_does_not_rewrite_immutable_opening(reader_case):
    with reader_case.engine.begin() as connection:
        connection.exec_driver_sql("UPDATE jobs SET budget=budget+1")
    state = inspect(reader_case)
    assert state.model_dump(mode="json") == reader_case.expected
    assert state.opening.organization_opening_microusd == 245000


@pytest.mark.parametrize("representation", ["utc-offset", "basic-date", "long-fraction"])
@pytest.mark.parametrize("reader_case", [COMPLETE_CASES[0]], indirect=True)
def test_historical_aware_timestamp_grammar_is_preserved(reader_case, representation):
    with reader_case.engine.begin() as connection:
        for table, field, where in (
            ("installation_adoptions", "created_at", ""),
            ("organizations", "created_at", ""),
            ("projects", "created_at", ""),
            ("migration_progress", "updated_at", " WHERE revision='ar_0003_ownership'"),
        ):
            original = connection.exec_driver_sql(
                f"SELECT {field} FROM {table}" + where
            ).scalar_one()
            at = datetime.fromisoformat(original)
            assert at.utcoffset() is not None
            if representation == "utc-offset":
                changed = at.isoformat(timespec="microseconds")
            elif representation == "basic-date":
                changed = at.strftime("%Y%m%dT%H%M%S.%f%z")
            else:
                # Python's old parser truncates excess fractional digits without changing time.
                changed = at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "0" * 4096 + "+00:00"
            assert datetime.fromisoformat(changed) == at
            connection.execute(
                text(f"UPDATE {table} SET {field}=:value" + where), {"value": changed}
            )
    assert inspect(reader_case).model_dump(mode="json") == reader_case.expected


@pytest.mark.parametrize("native_value", ["bytes", "huge-text"])
@pytest.mark.parametrize("reader_case", [COMPLETE_CASES[1]], indirect=True)
def test_financial_native_job_values_refuse_without_publication(reader_case, native_value):
    value = b"opaque-byte-payload" if native_value == "bytes" else "x" * (2 * 1024 * 1024 + 1)
    with reader_case.engine.begin() as connection:
        job = connection.exec_driver_sql("SELECT id FROM jobs ORDER BY id LIMIT 1").scalar_one()
        connection.execute(
            text("UPDATE jobs SET payload=:value WHERE id=:id"), {"value": value, "id": job}
        )
    refused(
        reader_case, "invalid_source_data" if native_value == "bytes" else "ledger_limit_exceeded"
    )
