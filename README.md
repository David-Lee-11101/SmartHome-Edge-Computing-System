# Smart Home Edge Computing System

A source-pinned integration hub for independent research on smart-home service
communication, typed logic execution, traffic profiling, scheduling, and local
management. Five repositories preserve their own history; this Hub owns the
integration contracts and reproducible system runner.

| Component | Source repository |
| --- | --- |
| Smart Home Communication | [Communication](https://github.com/David-Lee-11101/Handwritten-Netty-RPC) |
| Logic Engine | [Typed execution](https://github.com/David-Lee-11101/SmartService-Discovery-RPC) |
| Traffic Profiling | [Traffic models](https://github.com/David-Lee-11101/SmartRule-Conflict-Analyzer) |
| Thread-Safe Scheduler | [Evidence-aware execution](https://github.com/David-Lee-11101/SmartRule-Concurrency-Scheduler) |
| Integrated Logic Management | [Management and generation](https://github.com/David-Lee-11101/SmartRule-Automate-Composer) |

The manifest pins tested production source commits. Later CI-only commits can retain
the same production source; a branch's latest metadata is not a dependency upgrade.

![Causal architecture](architecture/causal-system.svg)

## Reproduce the integration

Requirements: Git and access to pinned repositories, JDK 21, Maven, Node.js/npm and
Python 3. Dependency downloads require network access. The runner uses fresh source
checkouts and a fresh Maven repository.

```bash
python3 tools/validate_contracts.py
python3 -m unittest discover -s tests -v
python3 tools/run_cold_system.py --workspace /tmp/smarthome-cold-run
```

Choose a new, nonexistent workspace. The runner fetches exact commits from
[components.json](components.json), builds and tests the components, generates and
compiles a stateful virtual switch, starts it on loopback and registers its typed
descriptor. A validated Logic Engine graph invokes actual Netty TinyRPC; payload-free
frame observations produce profile evidence before the scheduler persists a decision
and performs authorized actions. Separate RPC reads prove state and count changes.
Management reads back actual logic, profile, decision and execution records. A
post-action trace also returns to the profiler.

Outputs: `system-proof.json`, local command logs, generated sources and
`runtime/evidence/`. Any failed build or causal assertion produces a failed proof and
nonzero exit status. Saved proof snapshots and canonical fixtures never drive runtime.

## Evidence and limits

| Check | Evidence |
| --- | --- |
| Source identity | Clean checkouts at immutable commits |
| Real transport | Instrumented encoded frame lengths and directions |
| Profile before policy | Actual trace and model references |
| Decision before action | Durable decision read by actual callback |
| Actual effects | Independent readEnabled/readActionCount calls |
| Conservative policy | Controlled anomaly, ambiguity and conflict probes |
| Feedback | Execution records, management readback and profiler feedback |

The model calibrates on one local read and classifies a fresh read. This proves
software integration, not physical-device classifier accuracy. Policy probes explicitly
modify evidence to test decision sensitivity; these are controlled counterfactuals,
not claims that anomalies or conflicts were detected in a home. The normal action
uses unchanged evidence produced by the profiler.

See [integration API](contracts/INTEGRATION_API.md),
[compatibility policy](contracts/COMPATIBILITY.md) and [runner notes](docs/RUNNER.md).

## Research boundaries

The research manuscript's three conceptual components are **Detector → Synchronizer
→ Executor**. The five repositories are a distinct engineering decomposition. New
loopback verification does not reproduce historical experiments or validate reported
device measurements. Historical code remains provenance. arXiv work is planning only;
no submission or publication is asserted.

Contracts and the runner are implemented. Integration capability requires a passed
run at the manifest commits. Independent review and publication remain separate gates.

## Rights

Source visibility grants no reuse license for owner-authored material. Third-party
notices and historical provenance remain intact. See [RIGHTS.md](RIGHTS.md).
