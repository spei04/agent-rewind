"""Static C03 policy checks; these do not contact or certify a live deployment."""

import ast
import copy
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "contracts/fixtures/trust-boundaries.json"


def validate(contract):
    def require(value, message):
        if not value:
            raise ValueError(message)

    require(
        contract["contract_id"] == "C03" and contract["schema_version"] == 1,
        "Unknown topology contract",
    )
    scope = contract["scope"]
    require(
        scope["installation"] == "self_hosted" and scope["organizations_per_installation"] == 1,
        "Installation boundary changed",
    )
    require(not scope["customer_database_connection"], "Customer DB access is out of scope")
    require(
        scope["sandbox_runtime"] == "runsc" and not scope["insecure_fallback"],
        "Production isolation fallback is forbidden",
    )
    require(scope["dedicated_worker_hosts"], "Worker authority requires dedicated hosts")
    require(
        not scope["provisioning_authorized"] and not scope["live_isolation_verified_by_fixture"],
        "Fixture cannot authorize or verify a deployment",
    )
    components = contract["components"]
    policy = contract["network_policy"]
    require(policy["default"] == "deny", "Network policy must deny by default")
    allowed = set()
    denied = set()
    for key, edges in (("allowed", allowed), ("explicit_denials", denied)):
        for edge in policy[key]:
            pair = (edge["source"], edge["target"])
            require(set(pair) <= components.keys(), "Unknown component in network policy")
            require(pair not in edges, "Duplicate network policy edge")
            edges.add(pair)
    require(not allowed & denied, "Allowed connection contradicts explicit denial")
    for sandbox in ("sandbox", "evaluator_sandbox"):
        require(not components[sandbox]["credentials"], "Sandbox credential exposure")
        expected = {(sandbox, target) for target in components if target != sandbox}
        require(expected <= denied, "Missing sandbox denial")
        require(not any(source == sandbox for source, _ in allowed), "Sandbox network egress")
    for pair in (
        ("api", "docker_daemon"),
        ("api", "model_provider"),
        ("api", "customer_database"),
        ("worker", "customer_database"),
        ("browser", "artifact_store"),
        ("browser", "model_provider"),
        ("browser", "metadata_db"),
        ("internet", "metadata_db"),
        ("internet", "docker_daemon"),
        ("internet", "worker"),
    ):
        require(pair in denied, "Missing service denial")
    require(
        ("worker", "docker_daemon") in allowed and ("worker", "model_provider") in allowed,
        "Trusted worker authority is not declared",
    )
    for secret, recipients in contract["secret_recipients"].items():
        require(set(recipients) <= components.keys(), "Unknown secret recipient")
        require(
            not {"sandbox", "evaluator_sandbox", "browser", "internet"} & set(recipients),
            "Service secret crosses untrusted boundary",
        )
        actual = {name for name, item in components.items() if secret in item["credentials"]}
        require(actual == set(recipients), "Secret recipient inventory disagrees")
    require(
        contract["secret_recipients"]["model_provider"] == ["worker"],
        "Provider secret must remain worker-only",
    )
    config = contract["sandbox_config"]
    expected = {
        "network_mode": "none",
        "user": "1000:1000",
        "read_only": True,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges"],
        "privileged": False,
        "host_bind_mounts": [],
        "docker_socket_mount": False,
        "credentials": [],
        "model_key": False,
    }
    require(
        all(config.get(key) == value for key, value in expected.items()),
        "Sandbox configuration weakens boundary",
    )
    return len(components), len(allowed), len(denied)


class TrustContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads(FIXTURE.read_text())

    def test_complete_topology_and_denied_paths(self):
        self.assertEqual(validate(self.contract), (16, 15, 40))

    def test_sandbox_network_exception_is_rejected(self):
        self.contract["network_policy"]["allowed"].append(
            {"source": "sandbox", "target": "model_provider", "channel": "https"}
        )
        with self.assertRaisesRegex(ValueError, "contradicts explicit denial"):
            validate(self.contract)

    def test_omitted_metadata_denial_is_rejected(self):
        self.contract["network_policy"]["explicit_denials"] = [
            edge
            for edge in self.contract["network_policy"]["explicit_denials"]
            if (edge["source"], edge["target"]) != ("sandbox", "cloud_metadata")
        ]
        with self.assertRaisesRegex(ValueError, "Missing sandbox denial"):
            validate(self.contract)

    def test_provider_key_in_api_is_rejected(self):
        self.contract["components"]["api"]["credentials"].append("model_provider")
        with self.assertRaisesRegex(ValueError, "Secret recipient inventory disagrees"):
            validate(self.contract)

    def test_host_socket_mount_is_rejected(self):
        self.contract["sandbox_config"]["docker_socket_mount"] = True
        with self.assertRaisesRegex(ValueError, "Sandbox configuration weakens boundary"):
            validate(self.contract)

    def test_fixture_cannot_claim_live_verification(self):
        self.contract["scope"]["live_isolation_verified_by_fixture"] = True
        with self.assertRaisesRegex(ValueError, "cannot authorize or verify"):
            validate(self.contract)

    def test_unlisted_component_is_rejected(self):
        self.contract["network_policy"]["allowed"][0]["target"] = "unknown"
        with self.assertRaisesRegex(ValueError, "Unknown component"):
            validate(self.contract)

    def test_standard_runtime_fallback_is_rejected(self):
        self.contract["scope"]["insecure_fallback"] = True
        with self.assertRaisesRegex(ValueError, "fallback is forbidden"):
            validate(self.contract)

    def test_current_container_constructor_matches_core_denials(self):
        source = ast.parse((ROOT / "agent_rewind/runner.py").read_text())
        constructors = [
            node
            for node in ast.walk(source)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "containers"
        ]
        self.assertEqual(len(constructors), 2, "Review every new container creation path")
        expected = copy.deepcopy(self.contract["sandbox_config"])
        for constructor in constructors:
            kwargs = {arg.arg: arg.value for arg in constructor.keywords}
            for key in ("network_mode", "user", "read_only", "cap_drop", "security_opt"):
                self.assertEqual(ast.literal_eval(kwargs[key]), expected[key])
            self.assertNotIn("privileged", kwargs)
            self.assertEqual(ast.unparse(kwargs["runtime"]), "self.settings.sandbox_runtime")
            environment = ast.literal_eval(kwargs["environment"]) if "environment" in kwargs else {}
            self.assertLessEqual(set(environment), {"HOME", "PYTHONDONTWRITEBYTECODE"})
            for key in ("mem_limit", "memswap_limit", "nano_cpus", "pids_limit"):
                self.assertIn(key, kwargs)
