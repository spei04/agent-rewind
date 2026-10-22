"""Pure transition/cursor boundaries; these synthetic inputs establish no SQL authority."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from ledger_fixture import (
    OBSERVED,
    DialectOnlyConnection,
    account,
    cursor_for,
    identifier,
    initial_bundle,
    manifest,
)
from sqlalchemy import BigInteger, Integer, String, bindparam, text
from sqlalchemy.dialects import postgresql, sqlite

from agent_rewind.migrations.ledger_inputs import MAX_MONEY, validate_ledger_manifest
from agent_rewind.migrations.ledger_provisioning import (
    _classify_manifest,
    _ledger_cursors,
    _prepare_ledger,
)
from agent_rewind.migrations.ledger_state import ManifestCursor
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.ledger_writer_sql import PARAMETER_TYPES, SQL
from agent_rewind.migrations.schema import ADMISSION, LEDGER, MigrationRefused


def context(raw, *, held=(120000, 125000)):
    jobs = [row for row in raw["accounts"] if row["scope"] == "job"]
    assert len(held) == len(jobs)
    organization = raw["accounts"][0]["organization_id"] if raw["accounts"] else identifier(1)
    return SimpleNamespace(
        state=SimpleNamespace(
            revision=ADMISSION,
            installation_key=raw["installation_key"],
            manifest_count=0,
            account_count=0,
            head=None,
        ),
        history=SimpleNamespace(
            ownership=SimpleNamespace(organization_id=organization),
            manifests=(),
            opening=None,
            adoption={"installed_schema_fingerprint": "a" * 64},
        ),
        financial={
            "job": [
                {
                    "id": row["job_id"],
                    "budget": row["limit_microusd"],
                    "reserved": amount,
                    "status": "succeeded",
                    "payload_version": 1,
                    "owner": "finished-worker",
                    "lease_until": 1700000060.0,
                }
                for row, amount in zip(jobs, held, strict=True)
            ],
            "scope": [
                {
                    "resource_id": row["job_id"],
                    "resource_kind": "job",
                    "project_id": row["project_id"],
                }
                for row in jobs
            ],
            "account": [],
        },
    )


def test_checked_opening_is_exact_at_each_level_and_uses_real_provenance():
    raw = manifest()
    current, work = context(raw), LedgerWork()
    checked = validate_ledger_manifest(raw)
    prepared = _prepare_ledger(current, checked, work)
    cursor, opening = _ledger_cursors(
        DialectOnlyConnection(), checked, prepared, OBSERVED, None, 1234, work
    )
    assert opening.organization_opening_microusd == 245000
    assert sum(row.opening_held_microusd for row in opening.project_totals) == 245000
    assert [row.legacy_reserved_microusd for row in opening.jobs] == [120000, 125000]
    assert cursor.os_uid == 1234 and cursor.database_role is None
    assert cursor.initialized_at == OBSERVED and cursor.imported_jobs == 2
    assert current.financial["job"][0]["owner"] == "finished-worker"


@pytest.mark.parametrize("marker", ["future", "missing", "nonfinite", "queued"])
def test_ambiguous_or_live_lease_refuses_without_rewriting_historical_fields(marker):
    raw, work = manifest(), LedgerWork()
    current = context(raw)
    job = current.financial["job"][0]
    if marker == "future":
        job["lease_until"] = 253402300799.0
    elif marker == "missing":
        job["lease_until"] = None
    elif marker == "nonfinite":
        job["lease_until"] = float("inf")
    else:
        job.update(status="queued", payload_version=2, reserved=0)
    before = deepcopy(current.financial)
    checked = validate_ledger_manifest(raw)
    with pytest.raises(MigrationRefused, match="^ledger_history_unsupported$"):
        prepared = _prepare_ledger(current, checked, work)
        _ledger_cursors(DialectOnlyConnection(), checked, prepared, OBSERVED, None, 1, work)
    assert current.financial == before


def test_terminal_null_owner_with_expired_finite_deadline_is_supported():
    raw, work = manifest(), LedgerWork()
    current = context(raw)
    for job in current.financial["job"]:
        job["owner"] = None
    prepared = _prepare_ledger(current, validate_ledger_manifest(raw), work)
    assert prepared.organization_opening == 245000


@pytest.mark.parametrize(
    "boundary", ["cap", "overflow", "missing-job", "account-count", "manifest-count"]
)
def test_prewrite_exact_count_and_exposure_refusals(boundary):
    raw, work = manifest(), LedgerWork()
    current = context(raw)
    code = "ledger_exposure_refused"
    if boundary == "cap":
        raw["accounts"][0]["limit_microusd"] = 244999
    elif boundary == "overflow":
        for row in raw["accounts"]:
            row["limit_microusd"] = MAX_MONEY
        current = context(raw, held=(MAX_MONEY, MAX_MONEY))
    elif boundary == "missing-job":
        raw["accounts"].pop()
        code = "ledger_history_unsupported"
    elif boundary == "account-count":
        current.state.account_count = 4096
        code = "ledger_limit_exceeded"
    else:
        current.state.manifest_count = 256
        code = "ledger_limit_exceeded"
    with pytest.raises(MigrationRefused, match="^" + code + "$"):
        _prepare_ledger(current, validate_ledger_manifest(raw), work)


@pytest.mark.parametrize("held,cap,expected", [(20, 20, None), (20, 19, "ledger_exposure_refused")])
def test_new_period_carries_all_older_held_once(held, cap, expected):
    raw = manifest(empty=True)
    current = context(raw, held=())
    raw.update(operation="provision", opening_accounts=None, parent_manifest_digest="a" * 64)
    row = account(10_001, start="2026-02-01T00:00:00.000000Z", end="2026-03-01T00:00:00.000000Z")
    row["limit_microusd"] = cap
    raw["accounts"] = [row]
    current.financial["account"] = [
        {
            **account(10_000),
            "held_microusd": held,
            "accounted_microusd": 30,
            "opening_held_microusd": 0,
        }
    ]
    current.state.account_count = 1
    work = LedgerWork()
    if expected:
        with pytest.raises(MigrationRefused, match="^" + expected + "$"):
            _prepare_ledger(current, validate_ledger_manifest(raw), work)
    else:
        prepared = _prepare_ledger(current, validate_ledger_manifest(raw), work)
        assert prepared.exposure == {} and prepared.organization_opening == 0


def test_known_older_manifest_returns_original_receipt_before_new_intent_checks():
    raw, original, _ = initial_bundle()
    current = context(raw)
    first = ManifestCursor.model_validate(original)
    later = deepcopy(raw)
    later.update(
        manifest_id=identifier(1_000_001),
        operation="provision",
        opening_accounts=None,
        parent_manifest_digest=first.manifest_digest,
        accounts=[
            account(50_000, start="2026-02-01T00:00:00.000000Z", end="2026-03-01T00:00:00.000000Z")
        ],
    )
    second = ManifestCursor.model_validate(cursor_for(later, sequence=1))
    current.state.revision, current.state.head = LEDGER, second.receipt
    current.history.manifests = (first, second)
    current.state.manifest_count = 2
    checked = validate_ledger_manifest(raw)
    assert _classify_manifest(current, checked, LedgerWork()) == first.receipt
    changed = {**raw, "source_digest": "f" * 64}
    with pytest.raises(MigrationRefused, match="^ledger_manifest_conflict$"):
        _classify_manifest(current, validate_ledger_manifest(changed), LedgerWork())


def test_fixed_writer_statements_stay_within_real_bind_limit_and_money_width():
    types = {"String": String, "Integer": Integer, "BigInteger": BigInteger}
    assert len(SQL) == len(PARAMETER_TYPES) == 16
    for key, sql in SQL.items():
        statement = text(sql).bindparams(
            *(bindparam(name, type_=types[value]) for name, value in PARAMETER_TYPES[key].items())
        )
        driver = sqlite.dialect() if key[0] == "sqlite" else postgresql.dialect()
        compiled = statement.compile(dialect=driver)
        assert len(compiled.positiontup or compiled.params) <= 16
        for name, expected in PARAMETER_TYPES[key].items():
            if name in {
                "opening",
                "limit_microusd",
                "held_microusd",
                "opening_held_microusd",
                "accounted_microusd",
            }:
                assert expected == "BigInteger" and isinstance(
                    compiled.binds[name].type, BigInteger
                )


@pytest.mark.parametrize(
    "observed",
    [
        "2025-12-31T23:59:59.999999Z",
        "2026-02-01T00:00:00.000000Z",
    ],
)
def test_new_initial_import_period_must_contain_actual_observation(observed):
    raw, work = manifest(), LedgerWork()
    checked = validate_ledger_manifest(raw)
    prepared = _prepare_ledger(context(raw), checked, work)
    with pytest.raises(MigrationRefused, match="^invalid_ledger_manifest$"):
        _ledger_cursors(DialectOnlyConnection(), checked, prepared, observed, None, 1, work)


def test_new_expired_job_window_is_invalid_intent_not_exposure_or_stored_corruption():
    raw, original, opening = initial_bundle()
    checked = validate_ledger_manifest(raw)
    current = context(raw)
    current.history.manifests = (ManifestCursor.model_validate(original),)
    from agent_rewind.migrations.ledger_state import validate_opening_cursor

    current.history.opening = validate_opening_cursor(opening)
    new_job = identifier(90_000)
    project = raw["accounts"][-1]["project_id"]
    row = account(60_000, "job", project=project, job=new_job)
    current.financial["job"].append({"id": new_job, "budget": row["limit_microusd"], "reserved": 0})
    current.financial["scope"].append(
        {"resource_kind": "job", "resource_id": new_job, "project_id": project}
    )
    raw.update(
        manifest_id=identifier(1_000_001),
        operation="provision",
        opening_accounts=None,
        parent_manifest_digest=checked.digest,
        accounts=[row],
    )
    work = LedgerWork()
    checked = validate_ledger_manifest(raw)
    prepared = _prepare_ledger(current, checked, work)
    with pytest.raises(MigrationRefused, match="^invalid_ledger_manifest$"):
        _ledger_cursors(
            DialectOnlyConnection(),
            checked,
            prepared,
            "2026-02-01T00:00:00.000000Z",
            None,
            1,
            work,
        )
