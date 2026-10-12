# Cold-source causal runner

The Python runner owns clean immutable checkout, build orchestration and proof.
The Node session uses Management's generator lifecycle API to keep a real provider
alive while external profiler and scheduler processes run. The Java bridge is a
trusted, explicitly selected Scheduler callback; plan data cannot choose commands.

Maven uses an isolated local repository. npm consumes its committed lockfile. Python
uses standard-library tooling and pinned profiler source. A new workspace protects
previous evidence from overwrite.

The Logic build selects `-DtinyRpcAdapter -pl logic-engine-tiny-rpc-adapter -am
install`, with tests enabled. This builds the current typed core and real TinyRPC
adapter used by generated providers. Historical legacy RPC modules have separate
Java 8 compatibility CI; their obsolete Lombok processors do not compile on JDK 21.
An initial full-reactor cold run failed at that historical boundary, and its failed
proof/log remains evidence. The current integration does not require those modules;
no dependency override or test suppression is used to mask that failure.

The scheduler owns decision persistence, locks, execution and events. The bridge
reads an authorizing decision before dispatching its fixed supported action through
the Logic Engine. Its condition evaluator supports an independent live read after
locking; this demo declares no conditions, which are covered in scheduler tests.

One normal action and two reordered policy-probe actions produce exactly three
counter increments. Deferred and abstaining probes cause zero increments. Unsupported
contract major fails before persistence. Independent final reads verify state and count.

RPC subprocesses are terminated and reaped with bounded waits on success, failure,
timeout and interruption; interrupt status is restored. Process cleanup cannot roll
back an action already committed by the external provider. Cancellation prevents
new dispatch where observed; independent reads remain the evidence of committed effects.

Every actual action's trace/session/request tuple is correlated with its instrumented trace, completed
execution event and persisted decision. The real Profiler CLI classifies each action
trace and its exact emitted evidence is saved in the feedback journal. These are
post-action diagnostics, distinct from the pre-action read evidence that authorized
scheduling. A model calibrated only on reads may report an action as anomalous or
uncertain; the runner preserves that classification instead of forcing a normal label.
Separate CLI processes have separate sessions; a request identifier alone must not
be used as a global join key. The bridge reads trace/session identity from the exact
emitted trace file for that invocation before recording the correlation.

Public proof contains command identifiers, environment summaries and artifact hashes.
Full logs, endpoints, paths and caches remain local and require privacy review before
publication. Controlled anomaly/ambiguity/conflict inputs are clearly identified as
policy counterfactuals, not profiler detections. Physical deployment, learned classifier
accuracy, distributed failures and historical experiments remain outside this proof.
