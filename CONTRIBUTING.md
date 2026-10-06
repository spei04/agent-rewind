# Contributing

Keep changes focused and include tests for externally observable behavior.
Protocol or snapshot changes must document compatibility and restoration rules.
Never submit real traces, credentials, private repositories, or proprietary
model outputs as test fixtures.

Run formatting, lint, type, and test checks from the README. Sandbox changes also
need the gVisor integration job; metadata changes need the PostgreSQL concurrency
tests. Statistical changes must cover missing trials and boundary outcomes.

A useful issue includes the version, deployment mode, expected behavior, actual
behavior, and a minimal public task fixture. Remove private data before sharing.
