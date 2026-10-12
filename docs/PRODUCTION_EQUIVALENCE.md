# Production source and publication identities

The system manifest records the exact merged commits the cold-source runner checks
out and compiles. Performance measurements and earlier integration cohorts retain
their original source identities. Documentation commits, test corrections and merge
commits do not retroactively change a measurement's identity.

## Communication

Performance was measured at `83ffe6d77bf4cd249db863f4df1e9597938b59ad`.
The merged component is `12d3d5963fb3a962f10fd42449c96471f63c0bcf`.
The original 56-file Java/POM attestation belongs to the historical documentation
publication head `73d43d4d77a56d6fb5f8c31c0204fa5ae688a661` only. It must not be
extended to later commits as a claim that every test file is unchanged.

The Windows verification descendant `a125ff4bebb692c7d043a69307ae223525b97cd7`
changes `TinyRpcAdversarialTest.java` to exercise timeout behavior without a
platform-sensitive dispatch race. Production code, Maven POMs, benchmark harness
and measurement method remain unchanged. The separate
[57-file runtime/benchmark receipt](communication-runtime-equivalence.json) records
that scope and preserves the failed Windows run's identity/hash. This receipt is
not a new performance measurement or a claim of unchanged tests.

The Hub independently compared immutable Git blob identities at the merged head
against measured production: all 44 main-source/POM files and all 57 files in the
runtime/benchmark receipt match. Benchmark report additions and the one test
correction remain explicit publication differences.

## Logic Engine

Production source is pinned by downstream acceptance at
`971693b4cec8057239d6e742f958b61c83801781`; the merged repository commit is
`1ab52e55ff607c2141666812175d2ea8cbbd4088`. The Hub independently compared all
71 main-source/POM Git blobs and found them identical. The intervening difference
is the integration CI workflow's immutable Communication dependency pin.

[The merged production comparison](merged-production-equivalence.json) records
source identities, scope, matching Git blob IDs and changed paths. Source equality
supports these narrowly stated relationships. Final integration still requires a
fresh cold-source build and actual causal execution at the merged manifest commits;
previous proofs and benchmark archives never drive runtime actions.
