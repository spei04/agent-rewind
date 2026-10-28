"""Native representations for the same finite-account transition; no new lifecycle hooks."""

import json
from copy import deepcopy

from ledger_account_identity_fixture import expected_first
from ledger_accounted_carry_fixture import replace_rows
from ledger_accounted_carry_postgres_fixture import canonical_time, native_time
from ledger_eligibility_fixture import rows
from ledger_provisioning_fixture import canonical
from ledger_restore_authority import typed


def expected_native_first(frozen, first, initial, predecessor, one, written, role):
    assert type(role) is str and role
    projected = deepcopy(predecessor)
    for table, fields in (
        ("budget_accounts", ("period_start", "period_end")),
        ("migration_progress", ("updated_at",)),
    ):
        values = rows(projected, table)
        for row in values:
            for field in fields:
                row[field] = canonical_time(row[field])
            if table == "migration_progress":
                row["cursor"] = canonical(row["cursor"]).decode()
        replace_rows(projected, table, values)
    expected, state = expected_first(frozen, first, initial, projected, one, written, role=role)
    # Preserve unrelated native rows and historical JSONB values byte/type-exactly.
    result = deepcopy(predecessor)
    (account,) = one["accounts"]
    native = {
        **account,
        "period_start": native_time(account["period_start"]),
        "period_end": native_time(account["period_end"]),
        "opening_held_microusd": 0,
        "held_microusd": 0,
        "accounted_microusd": 0,
    }
    replace_rows(result, "budget_accounts", rows(predecessor, "budget_accounts") + [native])
    phase = "ledger_manifest_" + one["manifest_id"]
    (added,) = [row for row in rows(expected, "migration_progress") if row["phase"] == phase]
    added["cursor"] = json.loads(added["cursor"])
    added["updated_at"] = native_time(added["updated_at"])
    replace_rows(result, "migration_progress", rows(predecessor, "migration_progress") + [added])
    assert typed(projected["catalog"]) == typed(predecessor["catalog"])
    return result, state
