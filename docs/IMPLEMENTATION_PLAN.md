# Contract baseline implementation plan

1. Freeze the twelve cross-component messages before any adapter work.
2. Lock each message with one canonical valid fixture and at least one rejected fixture.
3. Validate schema structure, compatibility rules, identifiers, typed values, causal timing, and privacy constraints with Python's standard library.
4. Publish an immutable component manifest and a truthful capability map while the Hub remains private.
5. Keep system-proof fields present but mark the cold-source integration result as pending until the independent runner has passed.

This pass only establishes the Hub and its integration boundary. It does not rename component repositories, publish the Hub, or claim that the end-to-end system has passed.
