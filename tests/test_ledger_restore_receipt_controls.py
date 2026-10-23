"""Mutation controls for exact restored receipt identity and completion evidence."""

import json

import pytest
from ledger_restore_receipts import assert_original_receipt

from agent_rewind.migrations.ledger_state import LedgerManifestReceipt, LedgerProvisioning

VALUES = {
    "installation_key": "synthetic-postgres",
    "revision": "ar_0007_ledger",
    "manifest_id": "0" * 31 + "1",
    "manifest_digest": "1" * 64,
    "sequence": 0,
    "operation": "initialize",
    "source_digest": "2" * 64,
    "account_rows": 5,
    "imported_jobs": 3,
    "imported_opening_microusd": 245000,
    "initialized_at": "2026-10-23T08:09:00.632073Z",
}


def pair():
    return LedgerManifestReceipt(**VALUES), LedgerProvisioning(**VALUES, outcome="complete")


def collect():
    records = []
    return records, lambda name, value: records.append((name, json.loads(value)))


@pytest.mark.parametrize("operation", ["initialize", "provision"])
def test_complete_receipt_matches_all_fields_and_records_both_values(operation):
    recovered, original = pair()
    for item in (recovered, original):
        item.__dict__["operation"] = operation
    assert recovered != original, "inspection and provisioning are distinct model contracts"
    records, record = collect()
    assert_original_receipt(recovered, original, record)
    assert len(records) == 1
    name, witness = records[0]
    assert name == "restore_fresh_receipt_" + operation
    assert witness["original"] == {**VALUES, "operation": operation, "outcome": "complete"}
    assert witness["recovered"] == {**VALUES, "operation": operation}
    assert set(witness["compared_fields"]) == set(VALUES)
    assert witness["equal"] is True


@pytest.mark.parametrize("side", ["recovered", "original"])
@pytest.mark.parametrize("field", list(VALUES))
def test_every_receipt_field_mutation_is_rejected_and_retained(side, field):
    recovered, original = pair()
    item = recovered if side == "recovered" else original
    value = VALUES[field]
    changed = value + 1 if type(value) is int else value + "x"
    item.__dict__[field] = changed
    records, record = collect()
    with pytest.raises(AssertionError, match=field):
        assert_original_receipt(recovered, original, record)
    assert records[0][1][side][field] == changed
    assert records[0][1]["equal"] is False


@pytest.mark.parametrize("side", ["recovered", "original"])
@pytest.mark.parametrize("field", list(VALUES))
def test_every_missing_receipt_field_is_rejected(side, field):
    recovered, original = pair()
    item = recovered if side == "recovered" else original
    del item.__dict__[field]
    with pytest.raises(AssertionError):
        assert_original_receipt(recovered, original, lambda *_: None)


class StringSubclass(str):
    pass


class IntegerSubclass(int):
    pass


@pytest.mark.parametrize("side", ["recovered", "original"])
@pytest.mark.parametrize("field", list(VALUES))
@pytest.mark.parametrize("mutation", ["wrong_type", "subclass"])
def test_every_receipt_value_requires_its_exact_native_type(side, field, mutation):
    recovered, original = pair()
    item = recovered if side == "recovered" else original
    value = VALUES[field]
    if mutation == "subclass":
        changed = IntegerSubclass(value) if type(value) is int else StringSubclass(value)
    else:
        changed = float(value) if type(value) is int else value.encode()
    item.__dict__[field] = changed
    with pytest.raises(AssertionError):
        assert_original_receipt(recovered, original, lambda *_: None)


@pytest.mark.parametrize(
    "field", ["sequence", "account_rows", "imported_jobs", "imported_opening_microusd"]
)
@pytest.mark.parametrize("side", ["recovered", "original"])
def test_boolean_cannot_equal_an_integer_receipt_value(field, side):
    recovered, original = pair()
    for item in (recovered, original):
        item.__dict__[field] = 0
    (recovered if side == "recovered" else original).__dict__[field] = False
    with pytest.raises(AssertionError):
        assert_original_receipt(recovered, original, lambda *_: None)


@pytest.mark.parametrize("side", ["recovered", "original"])
@pytest.mark.parametrize("storage", ["fields", "pydantic_extra"])
def test_extra_fields_cannot_be_silently_discarded(side, storage):
    recovered, original = pair()
    item = recovered if side == "recovered" else original
    if storage == "fields":
        item.__dict__["unexpected"] = "kept"
    else:
        object.__setattr__(item, "__pydantic_extra__", {"unexpected": "kept"})
    with pytest.raises(AssertionError):
        assert_original_receipt(recovered, original, lambda *_: None)


@pytest.mark.parametrize(
    "outcome", [None, "pending", "failed", True, b"complete", StringSubclass("complete")]
)
def test_only_exact_complete_outcome_is_accepted(outcome):
    recovered, original = pair()
    original.__dict__["outcome"] = outcome
    with pytest.raises(AssertionError):
        assert_original_receipt(recovered, original, lambda *_: None)


def test_missing_outcome_is_rejected():
    recovered, original = pair()
    del original.__dict__["outcome"]
    with pytest.raises(AssertionError):
        assert_original_receipt(recovered, original, lambda *_: None)


@pytest.mark.parametrize("replacement", ["none", "dict", "swapped", "subclass"])
@pytest.mark.parametrize("side", ["recovered", "original"])
def test_receipts_require_the_exact_declared_model(side, replacement):
    recovered, original = pair()
    if replacement == "none":
        value = None
    elif replacement == "dict":
        value = dict(VALUES)
    elif replacement == "swapped":
        value = original if side == "recovered" else recovered
    elif side == "recovered":

        class DerivedReceipt(LedgerManifestReceipt):
            pass

        value = DerivedReceipt(**VALUES)
    else:

        class DerivedProvisioning(LedgerProvisioning):
            pass

        value = DerivedProvisioning(**VALUES, outcome="complete")
    if side == "recovered":
        recovered = value
    else:
        original = value
    with pytest.raises(AssertionError):
        assert_original_receipt(recovered, original, lambda *_: None)
