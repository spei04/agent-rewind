"""Negative checks for the design-time contract inventory, without service startup."""

import copy
import runpy
import unittest
from pathlib import Path

# The pytest console entrypoint need not put the repository root on sys.path.
checker = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts" / "check_m1_contracts.py")
)
check, load = checker["check"], checker["load"]


class ContractInventoryTests(unittest.TestCase):
    def setUp(self):
        self.api, self.data, self.models, self.database = load()

    def verify(self):
        return check(self.api, self.data, self.models, self.database)

    def test_current_proposal_has_complete_projection_mapping(self):
        result = self.verify()
        self.assertEqual(result["operations"], 5)
        self.assertEqual(result["entities"], 12)
        self.assertEqual(result["legacy_tables"], 5)

    def test_broken_reference_is_rejected(self):
        self.api["components"]["schemas"]["RunPage"]["properties"]["items"]["items"] = {
            "$ref": "#/components/schemas/Absent"
        }
        with self.assertRaisesRegex(ValueError, "Unresolved reference"):
            self.verify()

    def test_new_response_field_requires_persistence_disposition(self):
        self.api["components"]["schemas"]["Operation"]["properties"]["extra"] = {"type": "string"}
        with self.assertRaisesRegex(ValueError, "Unmapped API projection"):
            self.verify()

    def test_missing_logical_column_is_rejected(self):
        del self.data["entities"]["operations"]["fields"]["job_id"]
        with self.assertRaisesRegex(ValueError, "Missing persistence field"):
            self.verify()

    def test_path_parameter_drift_is_rejected(self):
        path = "/api/v1/projects/{project_id}/runs"
        self.api["paths"][path]["parameters"] = []
        with self.assertRaisesRegex(ValueError, "Path parameter mismatch"):
            self.verify()

    def test_task_model_field_drift_is_rejected(self):
        self.models = self.models.replace(
            "class TaskSpec(StrictModel):", "class TaskSpec(StrictModel):\n    extra: str"
        )
        with self.assertRaisesRegex(ValueError, "TaskDefinition field coverage"):
            self.verify()

    def test_duplicate_operation_id_is_rejected(self):
        path = "/api/v1/projects/{project_id}/runs"
        self.api["paths"][path]["post"]["operationId"] = self.api["paths"][path]["get"][
            "operationId"
        ]
        with self.assertRaisesRegex(ValueError, "Duplicate operation ID"):
            self.verify()

    def test_unknown_security_scheme_is_rejected(self):
        self.api["security"] = [{"unknown": []}]
        with self.assertRaisesRegex(ValueError, "Unknown security scheme"):
            self.verify()

    def test_mismatched_baseline_is_rejected(self):
        self.data = copy.deepcopy(self.data)
        self.data["baseline"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "Baseline identities disagree"):
            self.verify()
