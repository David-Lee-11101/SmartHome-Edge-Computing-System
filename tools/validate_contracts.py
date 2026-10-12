#!/usr/bin/env python3
"""Zero-dependency structural and semantic contract validator."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "contracts" / "schemas" / "v1"
FIXTURE_ROOT = ROOT / "contracts" / "fixtures"


class ContractError(ValueError):
    pass


def fail(path: str, message: str):
    raise ContractError(f"{path}: {message}")


def matches_type(value, expected):
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
        "record": isinstance(value, dict),
    }.get(expected, False)


def validate_schema(value, schema, path="$", root_schema=None):
    root_schema = root_schema or schema
    if not schema:
        return
    if "$ref" in schema:
        if not schema["$ref"].startswith("#/"):
            fail(path, "only local schema references are supported")
        target = root_schema
        for part in schema["$ref"][2:].split("/"):
            target = target[part]
        validate_schema(value, target, path, root_schema)
        return
    if "oneOf" in schema:
        matches = 0
        for candidate in schema["oneOf"]:
            try:
                validate_schema(value, candidate, path, root_schema)
                matches += 1
            except ContractError:
                pass
        if matches != 1:
            fail(path, f"expected exactly one schema alternative, got {matches}")
        return
    if "type" in schema and not matches_type(value, schema["type"]):
        fail(path, f"expected {schema['type']}, got {type(value).__name__}")
    if "enum" in schema and value not in schema["enum"]:
        fail(path, f"value is not in {schema['enum']}")
    if "const" in schema and value != schema["const"]:
        fail(path, f"expected constant {schema['const']!r}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            fail(path, "string is shorter than minLength")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            fail(path, "string is longer than maxLength")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            fail(path, f"string does not match {schema['pattern']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            fail(path, "number is below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            fail(path, "number is above maximum")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            fail(path, "array is shorter than minItems")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            fail(path, "array is longer than maxItems")
        for index, item in enumerate(value):
            validate_schema(item, schema.get("items", {}), f"{path}[{index}]", root_schema)
    if isinstance(value, dict):
        if "maxProperties" in schema and len(value) > schema["maxProperties"]:
            fail(path, "object has too many properties")
        if "propertyNames" in schema:
            for key in value:
                validate_schema(key, schema["propertyNames"], f"{path}.<propertyName>", root_schema)
        for required in schema.get("required", []):
            if required not in value:
                fail(path, f"missing required property {required}")
        properties = schema.get("properties", {})
        extra_policy = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in properties:
                validate_schema(item, properties[key], f"{path}.{key}", root_schema)
            elif extra_policy is False:
                fail(path, f"unknown property {key}")
            elif isinstance(extra_policy, dict):
                validate_schema(item, extra_policy, f"{path}.{key}", root_schema)


def parse_utc(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_typed_value(value, path, depth=0):
    if depth > 4:
        fail(path, "record nesting exceeds the maximum depth of four")
    expected = value["type"]
    if not matches_type(value["value"], expected):
        fail(path, f"declared type {expected} does not match value")
    if expected == "number" and not math.isfinite(value["value"]):
        fail(path, "number must be finite")
    if expected == "record":
        if len(value["value"]) > 32:
            fail(path, "record has more than 32 fields")
        for field, item in value["value"].items():
            if re.fullmatch(r"[a-zA-Z][a-zA-Z0-9._-]{0,63}", field) is None:
                fail(path, f"invalid record field name {field}")
            validate_typed_value(item, f"{path}.value.{field}", depth + 1)


PRIVATE_KEY = re.compile(r"(?:password|passwd|secret|token|credential|api[_-]?key|authorization)", re.I)
PRIVATE_VALUE = re.compile(
    r"(?:/Users/|/home/|(?:^|\\s)[A-Za-z]:[\\/]|-----BEGIN [A-Z ]+PRIVATE KEY-----|"
    r"(?:gh[opusr]_|github_pat_|sk-)[A-Za-z0-9_-]{8,}|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})"
)


def scan_privacy(value, path="$", parent_key=""):
    if PRIVATE_KEY.search(parent_key):
        fail(path, "credential-like field names are forbidden")
    if isinstance(value, dict):
        for key, item in value.items():
            scan_privacy(item, f"{path}.{key}", key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            scan_privacy(item, f"{path}[{index}]", parent_key)
    elif isinstance(value, str) and PRIVATE_VALUE.search(value):
        fail(path, "private path, credential, or personal contact pattern is forbidden")


def assert_unique(values, path):
    if len(values) != len(set(values)):
        fail(path, "values must be unique")


def assert_acyclic(nodes, edges, path):
    visiting, visited = set(), set()

    def visit(node):
        if node in visiting:
            fail(path, "cycle detected")
        if node in visited:
            return
        visiting.add(node)
        for dependency in edges.get(node, []):
            if dependency not in nodes:
                fail(path, f"unknown dependency {dependency}")
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in nodes:
        visit(node)


def semantic_validate(contract, data):
    version = data.get("manifestVersion", data.get("schemaVersion"))
    if not isinstance(version, str) or version.split(".", 1)[0] != "1":
        fail("$", "unsupported contract major")
    scan_privacy(data)

    def typed_list(items, path):
        for index, item in enumerate(items):
            validate_typed_value(item, f"{path}[{index}]")

    def validate_fields(fields, path, depth=0):
        if depth > 4:
            fail(path, "record signature nesting exceeds four")
        names = [field["name"] for field in fields]
        assert_unique(names, path)
        for index, field in enumerate(fields):
            if field["type"] == "record":
                if "fields" not in field:
                    fail(f"{path}[{index}]", "record field requires nested fields")
                validate_fields(field["fields"], f"{path}[{index}].fields", depth + 1)
            elif "fields" in field:
                fail(f"{path}[{index}]", "scalar field cannot declare nested fields")

    if contract == "ServiceDescriptor":
        operation_names = [operation["name"] for operation in data["operations"]]
        assert_unique(operation_names, "$.operations")
        for index, operation in enumerate(data["operations"]):
            parameter_names = [parameter["name"] for parameter in operation["parameters"]]
            assert_unique(parameter_names, f"$.operations[{index}].parameters")
            for parameter_index, parameter in enumerate(operation["parameters"]):
                if parameter["type"] == "record":
                    if "fields" not in parameter:
                        fail(f"$.operations[{index}].parameters[{parameter_index}]", "record parameter requires fields")
                    validate_fields(parameter["fields"], f"$.operations[{index}].parameters[{parameter_index}].fields")
                elif "fields" in parameter:
                    fail(f"$.operations[{index}].parameters[{parameter_index}]", "scalar parameter cannot declare fields")
            if operation["returns"] == "record":
                if "returnFields" not in operation:
                    fail(f"$.operations[{index}]", "record return requires returnFields")
                validate_fields(operation["returnFields"], f"$.operations[{index}].returnFields")
            elif "returnFields" in operation:
                fail(f"$.operations[{index}]", "scalar return cannot declare returnFields")
    elif contract == "InvocationRequest":
        typed_list(data["arguments"], "$.arguments")
    elif contract == "InvocationResult":
        if data["status"] == "success":
            if "value" not in data or "error" in data:
                fail("$", "success requires value and forbids error")
            validate_typed_value(data["value"], "$.value")
        elif "error" not in data or "value" in data:
            fail("$", "non-success requires error and forbids value")
    elif contract == "LogicDefinition":
        ids = [node["nodeId"] for node in data["nodes"]]
        assert_unique(ids, "$.nodes")
        edges = {}
        for index, node in enumerate(data["nodes"]):
            if node["resultType"] == "record":
                if "resultFields" not in node:
                    fail(f"$.nodes[{index}]", "record result requires resultFields")
                validate_fields(node["resultFields"], f"$.nodes[{index}].resultFields")
            elif "resultFields" in node:
                fail(f"$.nodes[{index}]", "scalar result cannot declare resultFields")
            refs = []
            for binding_index, binding in enumerate(node["inputs"]):
                if binding["bindingKind"] == "constant":
                    if "constant" not in binding or "nodeId" in binding:
                        fail(f"$.nodes[{index}].inputs[{binding_index}]", "constant binding shape is invalid")
                    validate_typed_value(binding["constant"], f"$.nodes[{index}].inputs[{binding_index}].constant")
                else:
                    if "nodeId" not in binding or "constant" in binding:
                        fail(f"$.nodes[{index}].inputs[{binding_index}]", "node-output binding shape is invalid")
                    refs.append(binding["nodeId"])
            edges[node["nodeId"]] = refs
            if node["kind"] == "service-call" and not {"serviceId", "operation"} <= node.keys():
                fail(f"$.nodes[{index}]", "service-call requires serviceId and operation")
            if node["kind"] == "select-field":
                if len(refs) != 1 or "field" not in node:
                    fail(f"$.nodes[{index}]", "select-field requires one node input and a field")
                source = next((candidate for candidate in data["nodes"] if candidate["nodeId"] == refs[0]), None)
                if source is None or source["resultType"] != "record":
                    fail(f"$.nodes[{index}]", "select-field source must be a typed record")
                selected = next((field for field in source.get("resultFields", []) if field["name"] == node["field"]), None)
                if selected is None:
                    fail(f"$.nodes[{index}].field", "selected field is absent from the record signature")
                if selected["type"] != node["resultType"] or selected.get("fields") != node.get("resultFields"):
                    fail(f"$.nodes[{index}]", "selected field signature does not match result signature")
            if node["kind"] in {"compare", "boolean", "numeric"} and "operator" not in node:
                fail(f"$.nodes[{index}]", "operator node requires operator")
        assert_acyclic(set(ids), edges, "$.nodes")
        for output in data["outputs"]:
            if output["nodeId"] not in ids:
                fail("$.outputs", "output references unknown node")
    elif contract == "TrafficTrace":
        offsets = [item["monotonicOffsetNanos"] for item in data["observations"]]
        if offsets != sorted(offsets):
            fail("$.observations", "observations must be monotonic")
        assert_unique([item["observationId"] for item in data["observations"]], "$.observations")
    elif contract == "ProfileEvidence":
        if data["anomaly"]["detected"] and not data["anomaly"]["reason"]:
            fail("$.anomaly.reason", "detected anomaly requires a reason")
        if data["ambiguity"]["detected"] and len(data["ambiguity"]["candidateLabels"]) < 2:
            fail("$.ambiguity.candidateLabels", "ambiguity requires at least two candidates")
    elif contract == "SchedulePlan":
        ids = [task["taskId"] for task in data["tasks"]]
        assert_unique(ids, "$.tasks")
        assert_acyclic(set(ids), {task["taskId"]: task["dependencies"] for task in data["tasks"]}, "$.tasks")
        for index, task in enumerate(data["tasks"]):
            assert_unique(task["readResources"], f"$.tasks[{index}].readResources")
            assert_unique(task["writeResources"], f"$.tasks[{index}].writeResources")
            typed_list(task["action"]["arguments"], f"$.tasks[{index}].action.arguments")
        for index, condition in enumerate(data["conditions"]):
            validate_typed_value(condition["expected"], f"$.conditions[{index}].expected")
    elif contract == "SchedulingDecision":
        if parse_utc(data["actionNotBefore"]) < parse_utc(data["persistedAt"]):
            fail("$.actionNotBefore", "action cannot precede persisted decision")
        if data["decision"] in {"defer", "abstain"} and data["resolvedOrder"]:
            fail("$.resolvedOrder", "defer or abstain cannot authorize actions")
        if data["decision"] in {"proceed", "reorder"} and not data["resolvedOrder"]:
            fail("$.resolvedOrder", "authorized decision requires an order")
    elif contract == "GenerationManifest":
        for index, item in enumerate(data["outputFiles"]):
            path = PurePosixPath(item["relativePath"])
            if path.is_absolute() or ".." in path.parts:
                fail(f"$.outputFiles[{index}].relativePath", "path must remain in the output root")
    elif contract == "SystemProof":
        expected = ["instrumented-rpc-trace", "profile-evidence", "scheduling-decision", "optional-action", "feedback-journal"]
        if data["causalOrder"] != expected:
            fail("$.causalOrder", "causal proof order is not canonical")
        if data["status"] == "passed" and data["skips"]:
            fail("$.skips", "a passed proof cannot contain skips")


def load_catalog():
    result = {}
    for path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        result[document["title"]] = document
    return result


def validate_component_manifest():
    path = ROOT / "components.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    scan_privacy(data)
    if data.get("manifestVersion", "").split(".", 1)[0] != "1":
        fail("components.json", "unsupported manifest major")
    hub = data.get("hub", {})
    required_hub = {"repositoryId", "repository", "visibility", "defaultBranch", "capabilityState"}
    if set(hub) != required_hub or hub["visibility"] != "private":
        fail("components.json.hub", "Hub identity must be exact and private during integration")
    required = {"role", "repositoryId", "repository", "targetName", "commit", "defaultBranch", "contractMajor", "capabilityState"}
    ids, roles = [], []
    for index, component in enumerate(data.get("components", [])):
        if set(component) != required:
            fail(f"components.json.components[{index}]", "component fields do not match manifest contract")
        if not re.fullmatch(r"[a-f0-9]{40}", component["commit"]):
            fail(f"components.json.components[{index}].commit", "commit must be exact")
        if component["contractMajor"] != 1:
            fail(f"components.json.components[{index}].contractMajor", "unsupported contract major")
        if not component["repository"].startswith("https://github.com/David-Lee-11101/"):
            fail(f"components.json.components[{index}].repository", "unexpected repository owner")
        ids.append(component["repositoryId"])
        roles.append(component["role"])
    if len(ids) < 6:
        fail("components.json.components", "component provenance inventory is incomplete")
    assert_unique(ids, "components.json.components.repositoryId")
    assert_unique(roles, "components.json.components.role")
    return len(ids)


def validate_document(contract, data, catalog=None):
    catalog = catalog or load_catalog()
    if contract not in catalog:
        fail("$", f"unknown contract {contract}")
    validate_schema(data, catalog[contract])
    semantic_validate(contract, data)


def preflight_logic_definition(logic, descriptors, catalog=None):
    catalog = catalog or load_catalog()
    validate_document("LogicDefinition", logic, catalog)
    indexed = {}
    nodes = {node["nodeId"]: node for node in logic["nodes"]}

    def canonical_fields(fields):
        return sorted(
            [
                {
                    "name": field["name"],
                    "type": field["type"],
                    **({"fields": canonical_fields(field["fields"])} if field["type"] == "record" else {}),
                }
                for field in fields
            ],
            key=lambda field: field["name"],
        )

    def fields_from_value(value):
        return sorted(
            [
                {
                    "name": name,
                    "type": item["type"],
                    **({"fields": fields_from_value(item["value"])} if item["type"] == "record" else {}),
                }
                for name, item in value.items()
            ],
            key=lambda field: field["name"],
        )
    for descriptor in descriptors:
        validate_document("ServiceDescriptor", descriptor, catalog)
        indexed[descriptor["serviceId"]] = descriptor
    for index, node in enumerate(logic["nodes"]):
        if node["kind"] != "service-call":
            continue
        descriptor = indexed.get(node["serviceId"])
        if descriptor is None:
            fail(f"$.nodes[{index}].serviceId", "service is not registered")
        operation = next((item for item in descriptor["operations"] if item["name"] == node["operation"]), None)
        if operation is None:
            fail(f"$.nodes[{index}].operation", "operation is not registered")
        if len(node["inputs"]) != len(operation["parameters"]):
            fail(f"$.nodes[{index}].inputs", "argument count does not match service signature")
        for argument_index, (binding, parameter) in enumerate(zip(node["inputs"], operation["parameters"])):
            if binding["bindingKind"] == "constant":
                actual_type = binding["constant"]["type"]
                actual_fields = None
                if actual_type == "record":
                    actual_fields = fields_from_value(binding["constant"]["value"])
            else:
                source = nodes[binding["nodeId"]]
                actual_type = source["resultType"]
                actual_fields = canonical_fields(source.get("resultFields", [])) if actual_type == "record" else None
            if actual_type != parameter["type"]:
                fail(f"$.nodes[{index}].inputs[{argument_index}]", "argument type does not match service signature")
            expected_fields = canonical_fields(parameter.get("fields", [])) if parameter["type"] == "record" else None
            if actual_type == "record" and actual_fields != expected_fields:
                fail(f"$.nodes[{index}].inputs[{argument_index}]", "record argument signature does not match service signature")
        expected_return_fields = canonical_fields(operation.get("returnFields", [])) if operation["returns"] == "record" else None
        actual_return_fields = canonical_fields(node.get("resultFields", [])) if node["resultType"] == "record" else None
        if operation["returns"] != node["resultType"] or expected_return_fields != actual_return_fields:
            fail(f"$.nodes[{index}]", "service result signature does not match descriptor")


def contract_for_fixture(path, catalog):
    slug = path.name
    for contract in catalog:
        candidate = re.sub(r"(?<!^)(?=[A-Z])", "-", contract).lower()
        if slug == f"{candidate}.json" or slug.startswith(f"{candidate}-"):
            return contract
    fail(str(path), "fixture does not map to a contract")


def validate_fixture_catalog():
    catalog = load_catalog()
    if len(catalog) != 12:
        fail("catalog", f"expected 12 schemas, found {len(catalog)}")
    manifest_path = FIXTURE_ROOT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_paths = []
    for entry in manifest["fixtures"]:
        path = ROOT / entry["path"]
        expected_paths.append(path.resolve())
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != entry["sha256"]:
            fail(entry["path"], "fixture digest mismatch")
    actual_paths = sorted([*(FIXTURE_ROOT / "v1" / "valid").glob("*.json"), *(FIXTURE_ROOT / "v1" / "invalid").glob("*.json")])
    if sorted(expected_paths) != sorted(path.resolve() for path in actual_paths):
        fail("manifest", "fixture inventory does not match manifest")
    for path in sorted((FIXTURE_ROOT / "v1" / "valid").glob("*.json")):
        contract = contract_for_fixture(path, catalog)
        validate_document(contract, json.loads(path.read_text(encoding="utf-8")), catalog)
    for path in sorted((FIXTURE_ROOT / "v1" / "invalid").glob("*.json")):
        contract = contract_for_fixture(path, catalog)
        try:
            validate_document(contract, json.loads(path.read_text(encoding="utf-8")), catalog)
        except ContractError:
            continue
        fail(str(path), "invalid fixture was accepted")
    validate_component_manifest()
    return len(actual_paths)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract")
    parser.add_argument("--document", type=Path)
    args = parser.parse_args()
    try:
        if args.contract or args.document:
            if not (args.contract and args.document):
                parser.error("--contract and --document must be supplied together")
            validate_document(args.contract, json.loads(args.document.read_text(encoding="utf-8")))
            print(f"PASS {args.contract} {args.document}")
        else:
            count = validate_fixture_catalog()
            print(f"PASS 12 schemas and {count} hashed fixtures")
    except (ContractError, json.JSONDecodeError, OSError) as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
