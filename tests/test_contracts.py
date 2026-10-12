import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("contract_validator", ROOT / "tools" / "validate_contracts.py")
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class ContractCatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = validator.load_catalog()

    def fixture(self, name):
        path = ROOT / "contracts" / "fixtures" / "v1" / "valid" / name
        return json.loads(path.read_text(encoding="utf-8"))

    def assert_rejected(self, contract, document):
        with self.assertRaises(validator.ContractError):
            validator.validate_document(contract, document, self.catalog)

    def test_catalog_and_hashed_fixtures(self):
        self.assertGreaterEqual(validator.validate_fixture_catalog(), 28)
        self.assertEqual(validator.validate_component_manifest(), 6)

    def test_typed_value_mismatch_is_rejected(self):
        data = self.fixture("invocation-request.json")
        data["arguments"] = [{"type": "boolean", "value": "true"}]
        self.assert_rejected("InvocationRequest", data)

    def test_record_result_and_select_field_are_valid(self):
        descriptor = self.fixture("service-descriptor.json")
        logic = self.fixture("logic-definition.json")
        result = self.fixture("invocation-result.json")
        validator.validate_document("InvocationResult", result, self.catalog)
        validator.preflight_logic_definition(logic, [descriptor], self.catalog)

    def test_service_signature_mismatch_is_rejected(self):
        descriptor = self.fixture("service-descriptor.json")
        logic = self.fixture("logic-definition.json")
        descriptor["operations"][0]["returnFields"][0]["type"] = "string"
        with self.assertRaises(validator.ContractError):
            validator.preflight_logic_definition(logic, [descriptor], self.catalog)

    def test_logic_cycle_is_rejected(self):
        data = self.fixture("logic-definition.json")
        data["nodes"][0]["inputs"] = [{"bindingKind": "node-output", "nodeId": "temperature.high"}]
        self.assert_rejected("LogicDefinition", data)

    def test_non_monotonic_trace_is_rejected(self):
        data = self.fixture("traffic-trace.json")
        data["observations"][1]["monotonicOffsetNanos"] = -1
        self.assert_rejected("TrafficTrace", data)

    def test_ambiguous_profile_needs_candidates(self):
        data = self.fixture("profile-evidence.json")
        data["ambiguity"] = {"detected": True, "candidateLabels": ["only-one"]}
        self.assert_rejected("ProfileEvidence", data)

    def test_schedule_cycle_is_rejected(self):
        data = self.fixture("schedule-plan.json")
        task = copy.deepcopy(data["tasks"][0])
        task["taskId"] = "task.fan.stop"
        task["dependencies"] = ["task.fan.start"]
        data["tasks"][0]["dependencies"] = ["task.fan.stop"]
        data["tasks"].append(task)
        self.assert_rejected("SchedulePlan", data)

    def test_abstain_cannot_authorize_action(self):
        data = self.fixture("scheduling-decision.json")
        data["decision"] = "abstain"
        self.assert_rejected("SchedulingDecision", data)

    def test_private_paths_are_rejected(self):
        data = self.fixture("generation-manifest.json")
        data["generatorVersion"] = "/Users/private/research"
        self.assert_rejected("GenerationManifest", data)

    def test_passed_proof_cannot_hide_skips(self):
        data = self.fixture("system-proof.json")
        data["status"] = "passed"
        data["skips"] = [{"checkId": "required.integration", "reason": "not run"}]
        self.assert_rejected("SystemProof", data)


if __name__ == "__main__":
    unittest.main()
