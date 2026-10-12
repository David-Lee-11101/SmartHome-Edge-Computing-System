# Smart Home integration API 1.0

This document freezes the cross-repository integration boundary at catalog version `1.0.2`. JSON Schema files are normative for shape; this document is normative for ownership, ordering, and semantics. Canonical examples live in `contracts/fixtures/v1/valid` and schemas live in `contracts/schemas/v1`.

## Common rules

- All contracts use catalog major version `1`. Existing documents emit `1.0.1`; corrected `TrafficTrace` documents emit `1.0.2`. Consumers reject any other major.
- Identifiers are opaque correlation values matching `^[a-zA-Z][a-zA-Z0-9._:-]{2,127}$`. They must not encode a person, home, IP address, filesystem path, credential, or physical device serial number.
- Timestamps are UTC RFC 3339 values ending in `Z`. Runtime duration and ordering use bounded integer fields rather than wall-clock subtraction.
- Typed values are `{ "type": "boolean|integer|number|string|null|record", "value": ... }`; the declared type must match the JSON value. A record is an object with at most 32 constrained field names whose members are typed values. Record nesting is limited to four levels. Unknown wrapper members are rejected. No implicit coercion is allowed.
- Unknown properties are rejected. JSON text is UTF-8. Logs may record identifiers, status, size, and duration but must not record arguments, results, message payloads, credentials, endpoints, or private paths.
- A consumer validates structure and semantics before side effects. Validation failure returns a structured component error and cannot be converted to a permissive default.

## Contract ownership

| Contract | Producer | Consumer | Side-effect boundary |
| --- | --- | --- | --- |
| `ServiceDescriptor` | Management local registry / generated provider | Logic Engine | Registration only after validation |
| `InvocationRequest` | Logic Engine | Communication / provider | Deadline checked before dispatch |
| `InvocationResult` | Provider / Communication | Logic Engine | Correlated by `requestId` |
| `LogicDefinition` | Management | Logic Engine | DAG validated before execution |
| `TransportObservation` | Communication telemetry | Profiler trace collector | Payload-free at codec/frame boundary |
| `TrafficTrace` | Trace collector or test fixture | Profiler core | Ordered and source-labelled |
| `ProfileEvidence` | Profiler core | Scheduler and Management | Must exist before scheduling decision |
| `SchedulePlan` | Logic Engine / Management | Scheduler | No action before decision persistence |
| `SchedulingDecision` | Scheduler policy | Scheduler executor / Management | Authorizes or blocks actions |
| `ExecutionEvent` | Scheduler executor | Management / feedback analysis | Occurs after the decision |
| `GenerationManifest` | Management generator pipeline | Hub / Logic Engine | Registration status is explicit |
| `SystemProof` | Hub cold-source runner | Reviewer | Evidence only; never drives runtime |

## ServiceDescriptor

`serviceId` and `version` identify the callable contract. `endpoint.catalogId` is a local catalog lookup key, never a host or address. `transport.kind` is either `tiny-rpc-netty` or the preserved `legacy-typed-netty`. Each operation declares ordered parameters and a return type. A record parameter declares `fields`; a record return declares `returnFields`. Field descriptors recursively declare `name`, `type`, and nested `fields` only for record members. Scalar signatures cannot declare nested fields. `metadata.capabilityState` is one of `historical`, `experimental`, `verified-component`, `verified-integration`, or `future`.

Registration must reject duplicate `(serviceId, version)` entries with conflicting descriptors. The local demo resolves one deterministic descriptor; network registry selection is an optional adapter.

## InvocationRequest and InvocationResult

The Logic Engine creates a unique `requestId`, validates the operation against `ServiceDescriptor`, and sets an absolute `deadlineEpochMs`. Communication enforces frame and pending-request limits and returns exactly one terminal result.

A successful result has `value` and no `error`. `error`, `timeout`, and `cancelled` results have a structured `error` and no `value`. `durationMs` is non-negative. No component silently retries an invocation.

## LogicDefinition

`nodes` form a typed acyclic graph. A binding is exactly one of a typed constant or a previous node output. Allowed node kinds are constants, service calls, field selection, comparisons, boolean operations, and bounded numeric operations. Operator names are the schema enum; arbitrary expressions, reflection targets, class names, scripts, and shell commands are forbidden.

The Logic Engine must validate unique node IDs, references, cycles, operation signatures, binding types, output references, division by zero, and finite numeric results before or during deterministic topological execution. Service-call preflight resolves the exact `ServiceDescriptor`, compares argument count and ordered parameter types, compares bounded record field signatures, and compares the result signature before dispatch. No coercion, reflective class loading, or fallback invocation is allowed. `graphTimeoutMs` bounds the graph and `nodeTimeoutMs` bounds each node.

`select-field` is executable, typed behavior: it requires exactly one node-output input whose declared result is a record, and its `field` must exist in that source node's `resultFields`. The selected field descriptor must exactly match the selecting node's `resultType` and optional nested `resultFields`. At runtime, an absent field produces a structured `logic.missing-field` failure; a mismatched typed value produces `logic.field-type-mismatch`. Neither condition yields `null`, a default value, or string coercion.

## TransportObservation and TrafficTrace

Communication emits an observation at the actual encoded-frame boundary with:

- the same `traceId`, `sessionId`, and `requestId` used for correlation;
- `direction` as `client-to-server` or `server-to-client`;
- encoded frame bytes after codec framing, limited to 1 MiB;
- a non-negative offset from a session-local monotonic origin;
- `transport=tiny-rpc-netty` and its protocol version.

The contract intentionally has no payload, endpoint, device, user, or network-address field. A `TrafficTrace` orders complete payload-free `TransportObservation` objects by monotonic offset, requires their schema version and `traceId` to match the envelope, binds one session and request, declares `modelInputVersion`, and labels the source as `instrumented-rpc` or `synthetic-fixture`. Only `instrumented-rpc` can satisfy the system integration proof. This interface describes application-instrumented RPC traffic, not packet capture.

## ProfileEvidence

The Profiler emits a stable `profileId` tied to one `traceId`. `modelVersion`, `modelHash`, and `fixtureHash` bind the algorithm and inputs. `distance`, `label`, and `[0,1]` confidence describe the nearest profile result. Anomaly and ambiguity are separate typed states; ambiguity lists competing labels. `patterns` records ordering, conflict, dependency, or frequency findings.

An anomaly requires a reason. Ambiguity requires at least two candidates. Scheduler policy treats anomaly as `defer` and unknown or ambiguous evidence as `abstain`; neither state authorizes an action.

## SchedulePlan and SchedulingDecision

Every task declares dependencies, read resources, write resources, and a typed service action. Task dependencies must be acyclic. The Scheduler sorts resource identifiers by the same stable total order, acquires them in that order, revalidates conditions after acquisition, and releases them in reverse order on every path.

The policy consumes the exact `profileEvidenceId` and persists a decision before any action. `proceed` and `reorder` require a non-empty `resolvedOrder`. `defer` and `abstain` require an empty order. `actionNotBefore` cannot precede `persistedAt`. A changed valid profile or conflict pattern must be able to change the decision or order.

## ExecutionEvent

Events correlate `executionId`, `decisionId`, and `taskId`; sequence starts at zero and increases per execution. States are `accepted`, `started`, `completed`, `failed`, `cancelled`, and `timed-out`. Errors are structured and bounded. An event documents execution after policy; it cannot serve as the pre-action decision.

## GenerationManifest

The generation pipeline binds `generatorVersion`, `templateHash`, and `serviceContractHash`. Every output file uses a relative forward-slash path contained within the configured output root and records its SHA-256. Traversal, absolute paths, backslashes, and symlink escape are rejected by the generator before writing. Build and local catalog registration have separate statuses and command/catalog identifiers.

## SystemProof

The cold-source runner records exact stable repository IDs and 40-character commits, the contract versions it actually consumed, bounded command/environment summaries, hashed outcomes, and explicit skips. Required checks cannot be hidden as skips; a passed proof has none. The canonical causal order is exactly:

1. `instrumented-rpc-trace`
2. `profile-evidence`
3. `scheduling-decision`
4. `optional-action`
5. `feedback-journal`

The current canonical proof is `pending`. It must not be edited to `passed`; the cold-source runner generates a new proof at exact component commits after all causal and failure scenarios succeed.

## Consumer commands

Validate the catalog and its hash manifest:

```bash
python3 tools/validate_contracts.py
```

Validate one producer document:

```bash
python3 tools/validate_contracts.py --contract ServiceDescriptor --document path/to/document.json
```

Component adapters should vendor or fetch the exact Hub commit and point tests at `contracts/schemas/v1` plus the relevant canonical fixtures. They must record that Hub commit in their integration evidence.
