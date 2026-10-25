"""Typed native financial projection and the original held-only reduction witness."""

from copy import deepcopy
from types import SimpleNamespace

from ledger_accounted_carry_fixture import replace_rows
from ledger_accounted_carry_observer import assert_carry
from ledger_accounted_carry_postgres_fixture import canonical_time
from ledger_eligibility_fixture import rows
from ledger_restore_authority import typed

FINANCIAL_TABLES = {
    "account": "budget_accounts",
    "job": "jobs",
    "call": "provider_calls",
    "entry": "budget_entries",
    "scope": "resource_scopes",
    "ref": "artifact_refs",
    "object": "artifact_objects",
    "operation": "operations",
    "project": "projects",
    "organization": "organizations",
}
TIME_FIELDS = {
    "account": ("period_start", "period_end"),
    "call": ("created_at",),
    "entry": ("created_at",),
    "object": ("created_at",),
    "operation": ("created_at", "retain_until"),
}


def financial_projection(before):
    """Project the financial reader subset without changing the complete native snapshot."""
    projected = deepcopy(before)
    result = {}
    for domain, table in FINANCIAL_TABLES.items():
        values = rows(before, table)
        if domain == "object":
            required = {}
            for reference in rows(before, "artifact_refs"):
                if reference["role"] in {"admission_config", "budget_evidence"}:
                    required.setdefault(reference["artifact_id"], set()).add(
                        reference["project_id"]
                    )
            values = [row for row in values if row["id"] in required]
            assert len(values) == len(required) and {row["id"] for row in values} == set(required)
            for row in values:
                projects = required[row["id"]]
                assert len(projects) == 1
                assert typed(next(iter(projects))) == typed(row["project_id"])
        for row in values:
            for name in TIME_FIELDS.get(domain, ()):
                row[name] = canonical_time(row[name])
        if domain in {"project", "organization"}:
            fields = ("id", "organization_id" if domain == "project" else "installation_key")
            result[domain] = [{field: row[field] for field in fields} for row in values]
        else:
            replace_rows(projected, table, values)
            result[domain] = values
    return projected, result


def ordered(values):
    return sorted(values, key=lambda row: repr(typed(row)))


def assert_native_carry(entry, sources, fixture, first, manifest, prior_state, watch):
    before, financial = financial_projection(fixture.before)
    projected = SimpleNamespace(source=fixture.source, before=before)
    assert_carry(entry, sources, projected, first, manifest, prior_state, watch)
    assert set(entry["financial"]) == set(financial)
    for domain, expected in financial.items():
        assert typed(ordered(entry["financial"][domain])) == typed(ordered(expected)), domain
    assert typed(entry["manifest"]) == typed(manifest)
    assert typed(entry["state"]) == typed(prior_state)
    assert typed(entry["prepared"]) == typed(
        {"jobs": [], "project_totals": [], "exposure": {}, "organization_opening": 0}
    )
    identity = {
        "work_id": id(watch.work),
        "raw_id": id(watch.work._raw),
        "engine_id": id(watch.engine),
    }
    assert typed({key: entry[key] for key in identity}) == typed(identity)
    for event, account in zip(entry["sums"], manifest["accounts"], strict=True):
        assert typed({key: event[key] for key in identity}) == typed(identity)
        assert typed(event["account"]) == typed(account)
        assert type(event["line"]) is int
        for name in ("position", "returned_at"):
            assert type(event[name]) is int and event[name] >= 0
    for event in sources:
        assert typed({key: event[key] for key in identity}) == typed(identity)
        assert type(event["position"]) is int and event["position"] >= 0
    for name in ("entered_at", "returned_at"):
        assert type(entry[name]) is int and entry[name] >= 0
