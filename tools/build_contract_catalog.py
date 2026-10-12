#!/usr/bin/env python3
"""Generate the versioned schema catalog and deterministic canonical fixtures."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "contracts" / "schemas" / "v1"
VALID = ROOT / "contracts" / "fixtures" / "v1" / "valid"
INVALID = ROOT / "contracts" / "fixtures" / "v1" / "invalid"

IDENTIFIER = {"type": "string", "pattern": "^[a-zA-Z][a-zA-Z0-9._:-]{2,127}$"}
FIELD_NAME = {"type": "string", "pattern": "^[a-zA-Z][a-zA-Z0-9._-]{0,63}$"}
UTC = {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\\.[0-9]+)?Z$"}
SHA256 = {"type": "string", "pattern": "^[a-f0-9]{64}$"}
VERSION = {"type": "string", "pattern": "^1\\.[0-9]+\\.[0-9]+$"}


def obj(required, properties, **extra):
    result = {
        "type": "object",
        "required": required,
        "properties": properties,
        "additionalProperties": False,
    }
    result.update(extra)
    return result


def arr(items, minimum=0):
    return {"type": "array", "items": items, "minItems": minimum}


VALUE_TYPES = ["boolean", "integer", "number", "string", "null", "record"]
TYPED_VALUE = {"$ref": "#/$defs/typedValue"}
FIELD_DESCRIPTOR = obj(["name", "type"], {
    "name": FIELD_NAME,
    "type": {"enum": VALUE_TYPES},
    "fields": arr({"$ref": "#/$defs/fieldDescriptor"}, 1),
})
TYPED_VALUE_DEFINITION = {
    "oneOf": [
        obj(["type", "value"], {"type": {"const": kind}, "value": {"type": kind}})
        for kind in ["boolean", "integer", "number", "string", "null"]
    ] + [
        obj(["type", "value"], {
            "type": {"const": "record"},
            "value": {
                "type": "object",
                "propertyNames": FIELD_NAME,
                "additionalProperties": {"$ref": "#/$defs/typedValue"},
                "maxProperties": 32,
            },
        })
    ]
}


def schema(title, body):
    slug = "".join([("-" + c.lower()) if c.isupper() and i else c.lower() for i, c in enumerate(title)])
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://github.com/David-Lee-11101/SmartHome-Edge-Computing-System/contracts/schemas/v1/{slug}.schema.json",
        "title": title,
        "$defs": {"typedValue": TYPED_VALUE_DEFINITION, "fieldDescriptor": FIELD_DESCRIPTOR},
        **body,
    }


SCHEMA_MAP = {
    "ServiceDescriptor": schema("ServiceDescriptor", obj(
        ["schemaVersion", "serviceId", "version", "endpoint", "transport", "operations", "metadata"],
        {
            "schemaVersion": VERSION,
            "serviceId": IDENTIFIER,
            "version": {"type": "string", "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$"},
            "endpoint": obj(["catalogId"], {"catalogId": IDENTIFIER}),
            "transport": obj(["kind", "protocolVersion"], {
                "kind": {"enum": ["tiny-rpc-netty", "legacy-typed-netty"]},
                "protocolVersion": {"type": "string", "minLength": 1, "maxLength": 32},
            }),
            "operations": arr(obj(["name", "parameters", "returns"], {
                "name": IDENTIFIER,
                "parameters": arr(obj(["name", "type"], {
                    "name": IDENTIFIER,
                    "type": {"enum": VALUE_TYPES},
                    "fields": arr(FIELD_DESCRIPTOR, 1),
                })),
                "returns": {"enum": VALUE_TYPES},
                "returnFields": arr(FIELD_DESCRIPTOR, 1),
            }), 1),
            "metadata": obj(["capabilityState"], {
                "capabilityState": {"enum": ["historical", "experimental", "verified-component", "verified-integration", "future"]},
            }),
        },
    )),
    "InvocationRequest": schema("InvocationRequest", obj(
        ["schemaVersion", "requestId", "serviceId", "operation", "arguments", "deadlineEpochMs"],
        {
            "schemaVersion": VERSION, "requestId": IDENTIFIER, "serviceId": IDENTIFIER,
            "operation": IDENTIFIER, "arguments": arr(TYPED_VALUE),
            "deadlineEpochMs": {"type": "integer", "minimum": 1},
        },
    )),
    "InvocationResult": schema("InvocationResult", obj(
        ["schemaVersion", "requestId", "status", "completedAt", "durationMs"],
        {
            "schemaVersion": VERSION, "requestId": IDENTIFIER,
            "status": {"enum": ["success", "error", "timeout", "cancelled"]},
            "value": TYPED_VALUE,
            "error": obj(["code", "message", "retryable"], {
                "code": IDENTIFIER, "message": {"type": "string", "minLength": 1, "maxLength": 256},
                "retryable": {"type": "boolean"},
            }),
            "completedAt": UTC, "durationMs": {"type": "integer", "minimum": 0},
        },
    )),
    "LogicDefinition": schema("LogicDefinition", obj(
        ["schemaVersion", "graphId", "nodes", "outputs", "timeoutPolicy"],
        {
            "schemaVersion": VERSION, "graphId": IDENTIFIER,
            "nodes": arr(obj(["nodeId", "kind", "resultType", "inputs"], {
                "nodeId": IDENTIFIER,
                "kind": {"enum": ["constant", "service-call", "select-field", "compare", "boolean", "numeric"]},
                "resultType": {"enum": VALUE_TYPES},
                "resultFields": arr(FIELD_DESCRIPTOR, 1),
                "inputs": arr(obj(["bindingKind"], {
                    "bindingKind": {"enum": ["constant", "node-output"]},
                    "constant": TYPED_VALUE,
                    "nodeId": IDENTIFIER,
                })),
                "serviceId": IDENTIFIER, "operation": IDENTIFIER,
                "operator": {"enum": ["eq", "ne", "lt", "lte", "gt", "gte", "and", "or", "not", "add", "subtract", "multiply", "divide"]},
                "field": IDENTIFIER,
            }), 1),
            "outputs": arr(obj(["name", "nodeId"], {"name": IDENTIFIER, "nodeId": IDENTIFIER}), 1),
            "timeoutPolicy": obj(["graphTimeoutMs", "nodeTimeoutMs"], {
                "graphTimeoutMs": {"type": "integer", "minimum": 1, "maximum": 60000},
                "nodeTimeoutMs": {"type": "integer", "minimum": 1, "maximum": 30000},
            }),
        },
    )),
    "TransportObservation": schema("TransportObservation", obj(
        ["schemaVersion", "traceId", "sessionId", "requestId", "direction", "encodedFrameLength", "monotonicOffsetNanos", "transport", "protocolVersion"],
        {
            "schemaVersion": VERSION, "traceId": IDENTIFIER, "sessionId": IDENTIFIER, "requestId": IDENTIFIER,
            "direction": {"enum": ["client-to-server", "server-to-client"]},
            "encodedFrameLength": {"type": "integer", "minimum": 1, "maximum": 1048576},
            "monotonicOffsetNanos": {"type": "integer", "minimum": 0},
            "transport": {"const": "tiny-rpc-netty"},
            "protocolVersion": {"type": "string", "minLength": 1, "maxLength": 32},
        },
    )),
    "TrafficTrace": schema("TrafficTrace", obj(
        ["schemaVersion", "traceId", "sourceKind", "modelInputVersion", "observations"],
        {
            "schemaVersion": VERSION, "traceId": IDENTIFIER,
            "sourceKind": {"enum": ["instrumented-rpc", "synthetic-fixture"]},
            "modelInputVersion": IDENTIFIER,
            "observations": arr(obj(
                ["schemaVersion", "traceId", "sessionId", "requestId", "direction", "encodedFrameLength", "monotonicOffsetNanos", "transport", "protocolVersion"],
                {
                    "schemaVersion": VERSION, "traceId": IDENTIFIER, "sessionId": IDENTIFIER, "requestId": IDENTIFIER,
                    "direction": {"enum": ["client-to-server", "server-to-client"]},
                    "encodedFrameLength": {"type": "integer", "minimum": 1, "maximum": 1048576},
                    "monotonicOffsetNanos": {"type": "integer", "minimum": 0},
                    "transport": {"const": "tiny-rpc-netty"},
                    "protocolVersion": {"type": "string", "minLength": 1, "maxLength": 32},
                },
            ), 1),
        },
    )),
    "ProfileEvidence": schema("ProfileEvidence", obj(
        ["schemaVersion", "profileId", "traceId", "modelVersion", "modelHash", "fixtureHash", "distance", "label", "confidence", "anomaly", "ambiguity", "patterns", "producedAt"],
        {
            "schemaVersion": VERSION, "profileId": IDENTIFIER, "traceId": IDENTIFIER,
            "modelVersion": IDENTIFIER, "modelHash": SHA256, "fixtureHash": SHA256,
            "distance": {"type": "number", "minimum": 0}, "label": IDENTIFIER,
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "anomaly": obj(["detected", "reason"], {
                "detected": {"type": "boolean"}, "reason": {"type": "string", "maxLength": 256},
            }),
            "ambiguity": obj(["detected", "candidateLabels"], {
                "detected": {"type": "boolean"}, "candidateLabels": arr(IDENTIFIER),
            }),
            "patterns": arr(obj(["kind", "status", "details"], {
                "kind": {"enum": ["ordering", "conflict", "dependency", "frequency"]},
                "status": {"enum": ["matched", "violated", "unknown"]},
                "details": {"type": "string", "maxLength": 256},
            })),
            "producedAt": UTC,
        },
    )),
    "SchedulePlan": schema("SchedulePlan", obj(
        ["schemaVersion", "planId", "tasks", "conditions", "deadlineEpochMs"],
        {
            "schemaVersion": VERSION, "planId": IDENTIFIER,
            "tasks": arr(obj(["taskId", "dependencies", "readResources", "writeResources", "action"], {
                "taskId": IDENTIFIER, "dependencies": arr(IDENTIFIER), "readResources": arr(IDENTIFIER),
                "writeResources": arr(IDENTIFIER), "action": obj(["serviceId", "operation", "arguments"], {
                    "serviceId": IDENTIFIER, "operation": IDENTIFIER, "arguments": arr(TYPED_VALUE),
                }),
            }), 1),
            "conditions": arr(obj(["conditionId", "nodeId", "expected"], {
                "conditionId": IDENTIFIER, "nodeId": IDENTIFIER, "expected": TYPED_VALUE,
            })),
            "deadlineEpochMs": {"type": "integer", "minimum": 1},
        },
    )),
    "SchedulingDecision": schema("SchedulingDecision", obj(
        ["schemaVersion", "decisionId", "planId", "profileEvidenceId", "decision", "reason", "resolvedOrder", "persistedAt", "actionNotBefore"],
        {
            "schemaVersion": VERSION, "decisionId": IDENTIFIER, "planId": IDENTIFIER,
            "profileEvidenceId": IDENTIFIER,
            "decision": {"enum": ["proceed", "reorder", "defer", "abstain"]},
            "reason": {"type": "string", "minLength": 1, "maxLength": 256},
            "resolvedOrder": arr(IDENTIFIER), "persistedAt": UTC, "actionNotBefore": UTC,
        },
    )),
    "ExecutionEvent": schema("ExecutionEvent", obj(
        ["schemaVersion", "executionId", "decisionId", "taskId", "sequence", "state", "occurredAt"],
        {
            "schemaVersion": VERSION, "executionId": IDENTIFIER, "decisionId": IDENTIFIER, "taskId": IDENTIFIER,
            "sequence": {"type": "integer", "minimum": 0},
            "state": {"enum": ["accepted", "started", "completed", "failed", "cancelled", "timed-out"]},
            "resource": IDENTIFIER, "occurredAt": UTC,
            "error": obj(["code", "message"], {"code": IDENTIFIER, "message": {"type": "string", "maxLength": 256}}),
        },
    )),
    "GenerationManifest": schema("GenerationManifest", obj(
        ["schemaVersion", "generationId", "generatorVersion", "templateHash", "serviceContractHash", "outputFiles", "build", "registration"],
        {
            "schemaVersion": VERSION, "generationId": IDENTIFIER, "generatorVersion": IDENTIFIER,
            "templateHash": SHA256, "serviceContractHash": SHA256,
            "outputFiles": arr(obj(["relativePath", "sha256"], {
                "relativePath": {"type": "string", "pattern": "^(?!/)(?!.*\\.\\.)(?!.*\\\\).+$"}, "sha256": SHA256,
            }), 1),
            "build": obj(["status", "commandId"], {"status": {"enum": ["passed", "failed"]}, "commandId": IDENTIFIER}),
            "registration": obj(["status", "catalogId"], {"status": {"enum": ["registered", "failed", "not-attempted"]}, "catalogId": IDENTIFIER}),
        },
    )),
    "SystemProof": schema("SystemProof", obj(
        ["manifestVersion", "proofId", "generatedAt", "status", "components", "contractVersions", "commands", "outcomes", "skips", "causalOrder"],
        {
            "manifestVersion": VERSION, "proofId": IDENTIFIER, "generatedAt": UTC,
            "status": {"enum": ["passed", "failed", "pending"]},
            "components": arr(obj(["role", "repositoryId", "commit"], {
                "role": IDENTIFIER, "repositoryId": {"type": "integer", "minimum": 1}, "commit": {"type": "string", "pattern": "^[a-f0-9]{40}$"},
            }), 1),
            "contractVersions": obj([], {}, additionalProperties={"type": "string", "pattern": "^1\\.[0-9]+\\.[0-9]+$"}),
            "commands": arr(obj(["commandId", "environment", "durationMs", "status"], {
                "commandId": IDENTIFIER,
                "environment": obj(["os", "arch", "runtime"], {"os": IDENTIFIER, "arch": IDENTIFIER, "runtime": {"type": "string", "maxLength": 128}}),
                "durationMs": {"type": "integer", "minimum": 0}, "status": {"enum": ["passed", "failed", "skipped"]},
            })),
            "outcomes": arr(obj(["checkId", "status", "evidenceHash"], {
                "checkId": IDENTIFIER, "status": {"enum": ["passed", "failed", "pending"]}, "evidenceHash": SHA256,
            })),
            "skips": arr(obj(["checkId", "reason"], {"checkId": IDENTIFIER, "reason": {"type": "string", "minLength": 1, "maxLength": 256}})),
            "causalOrder": arr({"enum": ["instrumented-rpc-trace", "profile-evidence", "scheduling-decision", "optional-action", "feedback-journal"]}, 5),
        },
    )),
}

HASH = "0" * 64
NOW = "2026-10-12T00:00:00Z"
FIXTURES = {
    "ServiceDescriptor": {"schemaVersion": "1.0.1", "serviceId": "sensor.temperature", "version": "1.0.0", "endpoint": {"catalogId": "local.catalog.sensor"}, "transport": {"kind": "tiny-rpc-netty", "protocolVersion": "tiny-rpc/1"}, "operations": [{"name": "readEnvironment", "parameters": [], "returns": "record", "returnFields": [{"name": "temperature", "type": "number"}, {"name": "unit", "type": "string"}]}], "metadata": {"capabilityState": "experimental"}},
    "InvocationRequest": {"schemaVersion": "1.0.1", "requestId": "req.sensor.001", "serviceId": "sensor.temperature", "operation": "readEnvironment", "arguments": [], "deadlineEpochMs": 1791763260000},
    "InvocationResult": {"schemaVersion": "1.0.1", "requestId": "req.sensor.001", "status": "success", "value": {"type": "record", "value": {"temperature": {"type": "number", "value": 24.5}, "unit": {"type": "string", "value": "celsius"}}}, "completedAt": NOW, "durationMs": 8},
    "LogicDefinition": {"schemaVersion": "1.0.1", "graphId": "logic.cooling.001", "nodes": [{"nodeId": "sensor.read", "kind": "service-call", "resultType": "record", "resultFields": [{"name": "temperature", "type": "number"}, {"name": "unit", "type": "string"}], "inputs": [], "serviceId": "sensor.temperature", "operation": "readEnvironment"}, {"nodeId": "sensor.temperature", "kind": "select-field", "resultType": "number", "inputs": [{"bindingKind": "node-output", "nodeId": "sensor.read"}], "field": "temperature"}, {"nodeId": "threshold.value", "kind": "constant", "resultType": "number", "inputs": [{"bindingKind": "constant", "constant": {"type": "number", "value": 25.0}}]}, {"nodeId": "temperature.high", "kind": "compare", "resultType": "boolean", "inputs": [{"bindingKind": "node-output", "nodeId": "sensor.temperature"}, {"bindingKind": "node-output", "nodeId": "threshold.value"}], "operator": "gt"}], "outputs": [{"name": "shouldCool", "nodeId": "temperature.high"}], "timeoutPolicy": {"graphTimeoutMs": 2000, "nodeTimeoutMs": 500}},
    "TransportObservation": {"schemaVersion": "1.0.0", "traceId": "trace.sensor.001", "sessionId": "session.loopback.001", "requestId": "req.sensor.001", "direction": "client-to-server", "encodedFrameLength": 128, "monotonicOffsetNanos": 0, "transport": "tiny-rpc-netty", "protocolVersion": "tiny-rpc/1"},
    "TrafficTrace": {"schemaVersion": "1.0.2", "traceId": "trace.sensor.001", "sourceKind": "instrumented-rpc", "modelInputVersion": "trace-vector.001", "observations": [{"schemaVersion": "1.0.2", "traceId": "trace.sensor.001", "sessionId": "session.loopback.001", "requestId": "req.sensor.001", "direction": "client-to-server", "encodedFrameLength": 128, "monotonicOffsetNanos": 0, "transport": "tiny-rpc-netty", "protocolVersion": "1.0"}, {"schemaVersion": "1.0.2", "traceId": "trace.sensor.001", "sessionId": "session.loopback.001", "requestId": "req.sensor.001", "direction": "server-to-client", "encodedFrameLength": 96, "monotonicOffsetNanos": 8000000, "transport": "tiny-rpc-netty", "protocolVersion": "1.0"}]},
    "ProfileEvidence": {"schemaVersion": "1.0.0", "profileId": "profile.sensor.001", "traceId": "trace.sensor.001", "modelVersion": "medoid.001", "modelHash": HASH, "fixtureHash": HASH, "distance": 0.08, "label": "temperature-read", "confidence": 0.94, "anomaly": {"detected": False, "reason": ""}, "ambiguity": {"detected": False, "candidateLabels": ["temperature-read"]}, "patterns": [{"kind": "ordering", "status": "matched", "details": "request precedes response"}], "producedAt": NOW},
    "SchedulePlan": {"schemaVersion": "1.0.0", "planId": "plan.cooling.001", "tasks": [{"taskId": "task.fan.start", "dependencies": [], "readResources": ["sensor.temperature"], "writeResources": ["device.fan"], "action": {"serviceId": "device.fan", "operation": "setEnabled", "arguments": [{"type": "boolean", "value": True}]}}], "conditions": [{"conditionId": "condition.cooling", "nodeId": "temperature.high", "expected": {"type": "boolean", "value": True}}], "deadlineEpochMs": 1791763260000},
    "SchedulingDecision": {"schemaVersion": "1.0.0", "decisionId": "decision.cooling.001", "planId": "plan.cooling.001", "profileEvidenceId": "profile.sensor.001", "decision": "proceed", "reason": "known profile and condition satisfied", "resolvedOrder": ["task.fan.start"], "persistedAt": NOW, "actionNotBefore": "2026-10-12T00:00:01Z"},
    "ExecutionEvent": {"schemaVersion": "1.0.0", "executionId": "execution.cooling.001", "decisionId": "decision.cooling.001", "taskId": "task.fan.start", "sequence": 0, "state": "started", "resource": "device.fan", "occurredAt": "2026-10-12T00:00:01Z"},
    "GenerationManifest": {"schemaVersion": "1.0.0", "generationId": "generation.sensor.001", "generatorVersion": "generator.001", "templateHash": HASH, "serviceContractHash": HASH, "outputFiles": [{"relativePath": "src/main/java/research/generated/SensorProvider.java", "sha256": HASH}], "build": {"status": "passed", "commandId": "maven.compile.001"}, "registration": {"status": "registered", "catalogId": "local.catalog.sensor"}},
    "SystemProof": {"manifestVersion": "1.0.0", "proofId": "proof.pending.001", "generatedAt": NOW, "status": "pending", "components": [{"role": "communication", "repositoryId": 721463248, "commit": "3a804f4c045222380f0d2192f66f17ec92a8411c"}], "contractVersions": {"ServiceDescriptor": "1.0.0"}, "commands": [], "outcomes": [{"checkId": "cold.source.system", "status": "pending", "evidenceHash": HASH}], "skips": [], "causalOrder": ["instrumented-rpc-trace", "profile-evidence", "scheduling-decision", "optional-action", "feedback-journal"]},
}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main():
    for directory in (SCHEMAS, VALID, INVALID):
        directory.mkdir(parents=True, exist_ok=True)
    for name, contract_schema in SCHEMA_MAP.items():
        slug = "".join([("-" + c.lower()) if c.isupper() and i else c.lower() for i, c in enumerate(name)])
        write_json(SCHEMAS / f"{slug}.schema.json", contract_schema)
        version_field = "manifestVersion" if name == "SystemProof" else "schemaVersion"
        FIXTURES[name][version_field] = "1.0.2" if name == "TrafficTrace" else "1.0.1"
        write_json(VALID / f"{slug}.json", FIXTURES[name])
        invalid = json.loads(json.dumps(FIXTURES[name]))
        invalid[version_field] = "2.0.0"
        write_json(INVALID / f"{slug}-unsupported-major.json", invalid)
    # Focused unsafe cases beyond incompatible-major fixtures.
    unsafe = json.loads(json.dumps(FIXTURES["TransportObservation"]))
    unsafe["payload"] = "must never be captured"
    write_json(INVALID / "transport-observation-payload.json", unsafe)
    unsafe = json.loads(json.dumps(FIXTURES["GenerationManifest"]))
    unsafe["outputFiles"][0]["relativePath"] = "../../private/file.java"
    write_json(INVALID / "generation-manifest-traversal.json", unsafe)
    unsafe = json.loads(json.dumps(FIXTURES["LogicDefinition"]))
    unsafe["nodes"][0]["kind"] = "shell"
    write_json(INVALID / "logic-definition-arbitrary-execution.json", unsafe)
    unsafe = json.loads(json.dumps(FIXTURES["SchedulingDecision"]))
    unsafe["actionNotBefore"] = "2026-10-11T23:59:59Z"
    write_json(INVALID / "scheduling-decision-action-before-persist.json", unsafe)
    unsafe = json.loads(json.dumps(FIXTURES["InvocationResult"]))
    nested = {"type": "string", "value": "too-deep"}
    for index in range(6):
        nested = {"type": "record", "value": {f"level{index}": nested}}
    unsafe["value"] = nested
    write_json(INVALID / "invocation-result-record-depth.json", unsafe)
    unsafe = json.loads(json.dumps(FIXTURES["InvocationResult"]))
    unsafe["value"]["unexpected"] = True
    write_json(INVALID / "invocation-result-typed-extra-field.json", unsafe)
    unsafe = json.loads(json.dumps(FIXTURES["LogicDefinition"]))
    unsafe["nodes"][1]["field"] = "missingField"
    write_json(INVALID / "logic-definition-select-missing-field.json", unsafe)
    unsafe = json.loads(json.dumps(FIXTURES["LogicDefinition"]))
    unsafe["nodes"][1]["resultType"] = "string"
    write_json(INVALID / "logic-definition-select-type-mismatch.json", unsafe)
    unsafe = json.loads(json.dumps(FIXTURES["TrafficTrace"]))
    del unsafe["modelInputVersion"]
    write_json(INVALID / "traffic-trace-missing-model-input-version.json", unsafe)
    unsafe = json.loads(json.dumps(FIXTURES["TrafficTrace"]))
    unsafe["observations"][0] = {
        "observationId": "observation.legacy.001",
        "sessionId": "session.loopback.001",
        "requestId": "req.sensor.001",
        "direction": "client-to-server",
        "encodedFrameLength": 128,
        "monotonicOffsetNanos": 0,
    }
    write_json(INVALID / "traffic-trace-simplified-observation.json", unsafe)

    fixture_files = sorted([*VALID.glob("*.json"), *INVALID.glob("*.json")])
    manifest = {
        "catalogVersion": "1.0.2",
        "fixtures": [
            {"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in fixture_files
        ],
    }
    write_json(ROOT / "contracts" / "fixtures" / "manifest.json", manifest)


if __name__ == "__main__":
    main()
