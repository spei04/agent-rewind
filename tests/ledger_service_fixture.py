"""Actual service-created PostgreSQL states shared by authored native tests."""

from types import SimpleNamespace

from ledger_fixture import identifier
from ledger_reader_fixture import complete_postgres_ar6
from test_ledger_service import intent
from test_run_projection_postgres import drain

from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.ledger_service import initialize_ledger


def provision_after(initial, receipt):
    return validate_ledger_manifest(
        {
            **initial.model_dump(mode="json"),
            "manifest_id": identifier(1_000_001),
            "operation": "provision",
            "parent_manifest_digest": receipt.manifest_digest,
            "opening_accounts": None,
            "accounts": [
                {
                    **initial.accounts[0].model_dump(mode="json"),
                    "id": identifier(40_000),
                    "period_start": "2100-01-01T00:00:00.000000Z",
                    "period_end": "2200-01-01T00:00:00.000000Z",
                }
            ],
        }
    )


def invoke_postgres(case, pg, manifest, *, engine=None):
    operator = case.operator_engine() if engine is None else engine
    try:
        return initialize_ledger(operator, manifest)
    finally:
        operator.dispose()
        drain(pg)


def apply_postgres_service(case, pg, *, history):
    """Keep predecessor witnesses; every returned receipt comes from the service."""
    if history not in {"empty", "legacy", "later"}:
        raise ValueError("unsupported service fixture history")
    initial = validate_ledger_manifest(intent(case, empty=history == "empty"))
    receipt = invoke_postgres(case, pg, initial)
    later = provision_after(initial, receipt) if history == "later" else None
    later_receipt = invoke_postgres(case, pg, later) if later is not None else None
    return SimpleNamespace(
        case=case,
        initial_manifest=initial,
        initial_receipt=receipt,
        later_manifest=later,
        later_receipt=later_receipt,
    )


def service_postgres_state(pg, *, history):
    """Create real ar6 history and execute initialization, optionally provision."""
    case = complete_postgres_ar6(pg, legacy=history != "empty")
    try:
        return apply_postgres_service(case, pg, history=history)
    except BaseException:
        case.dispose()
        raise
