"""Reproducible planning arithmetic, with no cloud or inference side effects."""

import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def estimate(data, scenario):
    hours = Decimal(data["hours_per_month"])
    seconds = hours * data["seconds_per_hour"]

    def price(name, quantity, unit):
        rate = data["rates"][name]
        if rate["unit"] != unit:
            raise ValueError(f"Unit mismatch for {name}")
        value = Decimal(rate["value"])
        if value < 0 or quantity < 0:
            raise ValueError("Negative price or quantity")
        return Decimal(quantity) * value

    arrivals = Decimal(scenario["continuations_per_hour"])
    count = arrivals * hours
    decisions, files = scenario["decisions"], scenario["files_per_capture"]
    if decisions < 1 or files < 0 or hours <= 0 or arrivals < 0:
        raise ValueError("Invalid workload")
    # Before+after each decision, final workspace, checkpoint/event JSON,
    # task/evaluation JSON and two conservative admission/result objects.
    puts = (2 * decisions + 1) * (files + 1) + 2 * decisions + 4
    storage_gib = (
        arrivals
        * 24
        * scenario["new_mib_per_continuation"]
        / 1024
        * scenario["retention_days"]
        * scenario["storage_safety_factor"]
    )
    items = {
        "workers": price("worker", scenario["worker_hosts"] * hours, "USD/worker-hour"),
        "sql_cpu": price("sql_cpu", scenario["sql_vcpu"] * hours, "USD/vCPU-hour"),
        "sql_memory": price("sql_memory", scenario["sql_gib"] * hours, "USD/GiB-hour"),
        "api_cpu": price(
            "api_cpu",
            scenario["api_instances"] * scenario["api_vcpu_each"] * seconds,
            "USD/vCPU-second",
        ),
        "api_memory": price(
            "api_memory",
            scenario["api_instances"] * scenario["api_gib_each"] * seconds,
            "USD/GiB-second",
        ),
        "object_storage": price("object_storage", storage_gib * hours, "USD/GiB-hour"),
        "object_writes": price("object_write", puts * count / 1000, "USD/1000-class-A-operations"),
        "object_reads": price(
            "object_read",
            scenario["get_ops_per_continuation"] * count / 1000,
            "USD/1000-class-B-operations",
        ),
    }
    subtotal = sum(items.values(), Decimal(0))
    factor = 1 + Decimal(data["contingency_fraction"])
    low = Decimal(scenario["other_services_low_usd"])
    high = Decimal(scenario["other_services_high_usd"])
    if low < 0 or high < low or factor < 1:
        raise ValueError("Invalid unpriced-services allowance")
    return {
        "items_usd": items,
        "quoted_rate_subtotal_usd": subtotal,
        "planning_low_usd": (subtotal + low) * factor,
        "planning_high_usd": (subtotal + high) * factor,
        "puts_per_continuation": puts,
        "monthly_continuations": count,
        "retained_gib_with_safety": storage_gib,
        "mean_live_slots": arrivals * scenario["mean_minutes"] / 60,
        "model_decisions_per_minute": arrivals * decisions / 60,
    }


def validation_budget(data):
    plan = data["model_validation"]
    cap, reserved = plan["total_cap_microusd"], plan["historical_reservations_microusd"]
    if not 0 <= reserved <= cap or cap != 200000000:
        raise ValueError("Validation cap or reservation bounds changed")
    continuations = (
        plan["screened_candidates"] * plan["screening_pairs_each"] + plan["confirmation_pairs"]
    ) * plan["arms_per_pair"]
    calls = continuations * plan["decisions_per_continuation_upper"] + plan["discovery_calls_upper"]
    remainder = cap - reserved
    return {
        "continuations": continuations,
        "calls_upper": calls,
        "arithmetic_remainder_microusd": remainder,
        "uniform_call_bound_microusd": remainder // calls,
        "illustrative_study_upper_microusd": calls * plan["illustrative_call_upper_microusd"],
        "dispatch_authorized": False,
    }


if __name__ == "__main__":
    fixture = json.loads((ROOT / "contracts/fixtures/capacity-budget.json").read_text())
    print(
        json.dumps(
            {
                "scenarios": {s["id"]: estimate(fixture, s) for s in fixture["scenarios"]},
                "model": validation_budget(fixture),
            },
            indent=2,
            default=str,
        )
    )
