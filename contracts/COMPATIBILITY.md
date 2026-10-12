# Contract compatibility policy

The catalog version is `1.0.1`. Every document declares a `schemaVersion` or, for `SystemProof`, `manifestVersion`.

- Consumers must reject an unsupported major version.
- A minor version may add optional fields. Existing field meaning, type, enum values, and required status cannot change.
- A patch version may clarify documentation or tighten a validator only when every previously canonical valid fixture remains valid.
- Unknown fields are rejected. An extension must first enter a versioned schema.
- Producers must emit canonical identifiers and UTC timestamps. Correlation identifiers are opaque and must not contain personal, device, network, filesystem, or credential data.
- Typed values use an explicit `{type, value}` form. Version `1.0.1` adds bounded typed records and executable `select-field` semantics without changing existing scalar encodings. Implementations must not infer or evaluate arbitrary source text.
- `TransportObservation` and `TrafficTrace` are payload-free. The only accepted real source kind is instrumented RPC telemetry; it is not represented as packet capture.
- `SchedulingDecision` is persisted before an optional action. `ExecutionEvent` records runtime activity after that decision.

`contracts/fixtures/manifest.json` binds every canonical fixture to its SHA-256 digest. Changing a fixture therefore requires an explicit catalog change.
