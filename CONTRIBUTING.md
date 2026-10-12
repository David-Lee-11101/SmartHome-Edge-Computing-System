# Contributing

Owner-authored source is visible for review; no reuse permission is granted. Read
RIGHTS.md before proposing changes. Preserve historical authorship and third-party
notices. Do not publish credentials, personal contacts, private paths or home/device
identities in issues, examples, telemetry or proof artifacts.

For contract changes, preserve existing major-version compatibility and update the
normative API, schemas, fixtures, digest inventory and consumer tests together. Do not
turn malformed evidence into permissive runtime defaults. For source pin updates,
record exact commits and repository IDs, run component tests and generate a fresh
cold-source proof; a manifest edit alone establishes no integration capability.

Run `python3 tools/validate_contracts.py` and
`python3 -m unittest discover -s tests -v` before a pull request. Runtime changes also
require the cold-source runner. Include the changed behavior, focused validation,
source identities, evidence location and explicit limits. Independent review precedes
integration/publication. CI contract tests establish shape and regression behavior;
they do not replace actual causal system proof.
