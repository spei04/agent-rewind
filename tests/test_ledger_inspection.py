"""Authored complete reader and native scalar boundary controls."""

import ledger_reader_fixture
import pytest
from ledger_reader_fixture import complete_ar6, seed_ar7, sqlite_snapshot

from agent_rewind.migrations import ledger_reader_history
from agent_rewind.migrations.ledger_inspection import inspect_ledger_state
from agent_rewind.migrations.ledger_transaction import LedgerOutcome, ledger_transaction
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import ADMISSION, MigrationRefused


@pytest.mark.parametrize(
    "legacy,ledger,empty",
    [
        (False, False, False),
        (True, False, False),
        (False, True, True),
        (False, True, False),
        (True, True, False),
    ],
)
def test_complete_inspector_uses_one_work_and_preserves_source(tmp_path, legacy, ledger, empty):
    case = complete_ar6(tmp_path / "reader.sqlite", legacy=legacy)
    engine = None
    try:
        if ledger:
            seed_ar7(case, empty_accounts=empty)
        before = sqlite_snapshot(case.path)
        engine = case.operator_engine()
        work, outcome = LedgerWork(), LedgerOutcome()
        with ledger_transaction(engine, outcome, work=work) as connection:
            state = inspect_ledger_state(connection)
        assert state.model_dump(mode="json") == case.expected
        assert outcome.commit_acknowledged and not outcome.cleanup_failed
        assert work.prepaid_bootstrap == 12 and work.prepaid_cleanup == 8
        assert 0 < work.observed_ordinary <= 2028
        assert sqlite_snapshot(case.path) == before
    finally:
        if engine is not None:
            engine.dispose()
        case.dispose()


@pytest.mark.parametrize(
    "receipt",
    [
        {"candidate_rows": True, "invalid_rows": 0, "safe_revision": ADMISSION},
        {"candidate_rows": 1, "invalid_rows": False, "safe_revision": ADMISSION},
        {"candidate_rows": 1, "invalid_rows": 0, "safe_revision": ADMISSION.encode()},
        {"candidate_rows": 1, "invalid_rows": 0, "safe_revision": ADMISSION, "extra": 0},
    ],
)
def test_revision_receipt_refuses_coerced_native_classes(monkeypatch, receipt):
    monkeypatch.setattr(ledger_reader_history, "_query", lambda *args: [receipt])
    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
        ledger_reader_history.read_revision(object())


def test_original_api_key_grant_remains_valid_without_live_membership_equality(
    tmp_path, monkeypatch
):
    original = ledger_reader_fixture.mapping_for
    selected = []

    def mapping_with_key(engine):
        mapping = original(engine)
        with engine.connect() as connection:
            key_id = connection.exec_driver_sql(
                "SELECT id FROM api_keys ORDER BY id LIMIT 1"
            ).scalar_one()
        selected.append(key_id)
        mapping["key_dispositions"] = [{"key_id": key_id, "role": "viewer"}]
        mapping["principal_grants"].append(
            {"principal_id": "api-key:" + key_id, "role": "viewer", "legacy_default": False}
        )
        return mapping

    monkeypatch.setattr(ledger_reader_fixture, "mapping_for", mapping_with_key)
    case = complete_ar6(tmp_path / "reader.sqlite", legacy=True)
    engine = None
    try:
        assert len(selected) == 1
        with case.engine.begin() as connection:
            changed = connection.exec_driver_sql(
                "UPDATE project_memberships SET role='operator' WHERE principal_id=?",
                ("api-key:" + selected[0],),
            )
            assert changed.rowcount == 1
        engine = case.operator_engine()
        with ledger_transaction(engine, LedgerOutcome(), work=LedgerWork()) as connection:
            state = inspect_ledger_state(connection)
        assert state.model_dump(mode="json") == case.expected
    finally:
        if engine is not None:
            engine.dispose()
        case.dispose()


def test_expiry_between_descriptor_validations_stops_before_the_next_body(tmp_path, monkeypatch):
    from agent_rewind.migrations import ledger_reader_financial, ledger_work

    case = seed_ar7(complete_ar6(tmp_path / "reader.sqlite"))
    engine = None
    try:
        ledger_reader_fixture.later_admitted_call(case, effect="settled")
        engine = case.operator_engine()
        clock = [0.0]
        expire = [False]
        observed = []
        original = ledger_reader_financial._object

        def observed_descriptor(value):
            result = original(value)
            observed.append(value["id"])
            if expire[0]:
                clock[0] = 121.0
            return result

        monkeypatch.setattr(ledger_work, "monotonic", lambda: clock[0])
        monkeypatch.setattr(ledger_reader_financial, "_object", observed_descriptor)
        with ledger_transaction(engine, LedgerOutcome(), work=LedgerWork()) as connection:
            assert inspect_ledger_state(connection).model_dump(mode="json") == case.expected
        assert len(observed) >= 2

        observed.clear()
        expire[0] = True
        before = sqlite_snapshot(case.path)
        with (
            pytest.raises(MigrationRefused, match="^migration_busy$"),
            ledger_transaction(engine, LedgerOutcome(), work=LedgerWork()) as connection,
        ):
            inspect_ledger_state(connection)
        assert len(observed) == 1
        assert sqlite_snapshot(case.path) == before
    finally:
        if engine is not None:
            engine.dispose()
        case.dispose()
