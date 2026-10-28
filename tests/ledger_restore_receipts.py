"""Exact comparison of inspection receipts with completed provisioning evidence."""

import json

from agent_rewind.migrations.ledger_state import LedgerManifestReceipt, LedgerProvisioning

RECEIPT_TYPES = {
    "installation_key": str,
    "revision": str,
    "manifest_id": str,
    "manifest_digest": str,
    "sequence": int,
    "operation": str,
    "source_digest": str,
    "account_rows": int,
    "imported_jobs": int,
    "imported_opening_microusd": int,
    "initialized_at": str,
}


def assert_original_receipt(recovered, original, record_property):
    assert type(recovered) is LedgerManifestReceipt
    assert type(original) is LedgerProvisioning
    fields = set(RECEIPT_TYPES)
    assert set(LedgerManifestReceipt.model_fields) == fields
    assert set(LedgerProvisioning.model_fields) == fields | {"outcome"}
    expected, actual = vars(original), vars(recovered)
    assert set(expected) == fields | {"outcome"} and set(actual) == fields
    assert all(type(name) is str for name in (*expected, *actual))
    assert original.__pydantic_extra__ is None and recovered.__pydantic_extra__ is None
    assert type(expected["outcome"]) is str and expected["outcome"] == "complete"
    for name, kind in RECEIPT_TYPES.items():
        assert type(expected[name]) is kind and type(actual[name]) is kind
    # Persist both complete values before equality, including a mismatch if one occurs.
    record_property(
        "restore_fresh_receipt_" + expected["operation"],
        json.dumps(
            {
                "original_type": "LedgerProvisioning",
                "recovered_type": "LedgerManifestReceipt",
                "original": expected,
                "recovered": actual,
                "compared_fields": list(RECEIPT_TYPES),
                "equal": all(actual[name] == expected[name] for name in RECEIPT_TYPES),
            }
        ),
    )
    for name in RECEIPT_TYPES:
        assert actual[name] == expected[name], name
