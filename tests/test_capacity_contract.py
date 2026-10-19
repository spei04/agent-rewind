"""Cost/capacity arithmetic checks; no billed operation is performed."""

import json
import runpy
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
calculator = runpy.run_path(str(ROOT / "scripts/capacity_estimate.py"))
estimate, validation_budget = calculator["estimate"], calculator["validation_budget"]


class CapacityContractTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "contracts/fixtures/capacity-budget.json").read_text())
        self.pilot = self.data["scenarios"][0]

    def test_pilot_units_and_storage_reserve(self):
        result = estimate(self.data, self.pilot)
        self.assertEqual(result["monthly_continuations"], Decimal(14600))
        self.assertEqual(result["retained_gib_with_safety"], Decimal(1350))
        self.assertEqual(result["puts_per_continuation"], 2135)
        self.assertEqual(result["items_usd"]["api_cpu"], Decimal("94.608"))
        self.assertEqual(result["items_usd"]["sql_cpu"], Decimal("120.596"))
        self.assertEqual(result["planning_low_usd"].quantize(Decimal("0.01")), Decimal("1177.31"))
        self.assertEqual(result["planning_high_usd"].quantize(Decimal("0.01")), Decimal("2114.81"))

    def test_file_fanout_dominates_identical_byte_growth(self):
        small = estimate(self.data, self.pilot)
        large = estimate(self.data, self.data["scenarios"][1])
        self.assertEqual(large["retained_gib_with_safety"], small["retained_gib_with_safety"])
        self.assertEqual(large["puts_per_continuation"], 82085)
        self.assertEqual(large["items_usd"]["object_writes"], Decimal("5992.205"))
        self.assertGreater(large["items_usd"]["object_writes"], Decimal(3000))

    def test_forecast_concurrency_doubles_with_inference_duration(self):
        scenario = self.data["scenarios"][2]
        normal = estimate(self.data, scenario)["mean_live_slots"]
        scenario["mean_minutes"] = 20
        doubled = estimate(self.data, scenario)["mean_live_slots"]
        self.assertEqual(normal.quantize(Decimal("0.001")), Decimal("33.333"))
        self.assertEqual(doubled.quantize(Decimal("0.001")), Decimal("66.667"))
        self.assertGreater(doubled, Decimal(scenario["live_slots"]))

    def test_hour_second_unit_mix_is_rejected(self):
        self.data["rates"]["api_cpu"]["unit"] = "USD/vCPU-hour"
        with self.assertRaisesRegex(ValueError, "Unit mismatch"):
            estimate(self.data, self.pilot)

    def test_invalid_workload_is_rejected(self):
        self.pilot["decisions"] = 0
        with self.assertRaisesRegex(ValueError, "Invalid workload"):
            estimate(self.data, self.pilot)

    def test_negative_price_is_rejected(self):
        self.data["rates"]["worker"]["value"] = "-1"
        with self.assertRaisesRegex(ValueError, "Negative price"):
            estimate(self.data, self.pilot)

    def test_validation_bound_includes_discovery_and_both_arms(self):
        result = validation_budget(self.data)
        self.assertEqual(result["continuations"], 124)
        self.assertEqual(result["calls_upper"], 2483)
        self.assertEqual(result["arithmetic_remainder_microusd"], 163432026)
        self.assertEqual(result["uniform_call_bound_microusd"], 65820)
        self.assertEqual(result["illustrative_study_upper_microusd"], 248300000)
        self.assertGreater(result["illustrative_study_upper_microusd"], 200000000)
        self.assertFalse(result["dispatch_authorized"])
        self.assertIsNone(self.data["model_validation"]["reconciled_invoice_spend_microusd"])
        self.assertFalse(self.data["model_validation"]["ledger_current_verified"])

    def test_changed_validation_cap_is_rejected(self):
        self.data["model_validation"]["total_cap_microusd"] = 201000000
        with self.assertRaisesRegex(ValueError, "cap or reservation bounds"):
            validation_budget(self.data)

    def test_unpriced_allowance_is_separate_from_rates(self):
        result = estimate(self.data, self.pilot)
        subtotal = result["quoted_rate_subtotal_usd"]
        self.assertEqual(subtotal, sum(result["items_usd"].values()))
        self.assertEqual(result["planning_low_usd"], (subtotal + 250) * Decimal("1.25"))
        self.assertFalse(self.data["region_approved"])
        self.assertTrue(all(not scenario["measured"] for scenario in self.data["scenarios"]))
