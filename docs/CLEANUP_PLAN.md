# Bounded integration cleanup

Scope: Hub runner, immutable component manifest, architecture documentation, and
runner tests. Component implementations remain independently owned.

Behavior lock: the 14 existing contract tests pass before edits. Add targeted tests
for cold checkout identity, causal evidence references, and failed proof rejection.

Order: replace stale capability claims with measured states; implement one explicit
runner path; reject missing commands/interfaces instead of replaying snapshots;
validate producer artifacts and independent state/count reads; remove debug output;
rerun contract and runner tests.

Fallback inventory: historical proof fixtures are examples only. They must never
drive runtime actions or become integration evidence. Missing source access, build
failure, malformed producer output, or failed causal assertions abort the run.
No masking fallback, permissive default, synthetic RPC substitute, or new dependency
is accepted. Standard runtime environment overrides select installed tools explicitly.

Review separation: independent component and Hub reviewers assess the completed
diff after focused validation; the implementation author does not approve it.
