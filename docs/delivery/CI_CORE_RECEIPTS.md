# Complete core CI receipts

Core CI uses Python 3.11 `early` and `late` jobs, and one unpartitioned Python
3.12 `all` job. The 3.11 jobs and their pytest-session receipts retain
45-minute limits. The full 3.12 job has a 75-minute outer limit, while its
pytest-session receipt retains a separate 60-minute elapsed limit. A session
exceeding that receipt limit still fails the gate. Each job owns its disposable
PostgreSQL service. The 3.11 cut is by complete file at
`tests/test_ledger_recovery.py`: earlier paths run in `early`, the boundary and
later paths run in `late`. Original collection order is retained. Python 3.12
keeps the full order, including installed-package interaction checks.

The opt-in `scripts.ci_core` pytest plugin observes full collection before
selection and records setup, call and teardown outcomes. Ordinary collection,
including `--collect-only`, does not load the plugin or apply the partition.
Selection never reads the expectations file. Failed phases, interrupted
sessions, duplicate reports, changed source or missing terminal outcomes
cannot supply passing coverage. Core pytest uses `--maxfail=1` so the first
failure ends the session with its original traceback instead of waiting for a
later job timeout. Its incomplete or failed receipt cannot pass the gate.
Successful sessions still require every selected node and complete passing or
declared-skip phases. The 75-minute outer allowance provides bounded CI job
headroom, not a completion guarantee; the 60-minute session guard and product,
native and sandbox deadlines are unchanged.

## Updating the collection baseline

Test changes require a fresh, independently reviewed full collection for
**both Python versions** from the immutable composed source. Do not infer one
version's inventory from the other or execute test/fixture bodies to obtain
this baseline. Update `scripts/ci_core_expectations.json` with each version's
ordered count, collection digest and exact skip nodes/reasons. A pending
baseline fails the gate; it is not a usable default.

The digest is SHA-256 of the UTF-8 ordered JSON node array using
`ensure_ascii=False`, compact comma/colon separators and no trailing newline.
Expected skips are predeclared from source guards and the CI profile and
independently reviewed; collection does not execute test bodies to derive
them. Actual receipt skip reasons come only from the third element of
pytest's terminal skip report tuple, removing one fixed leading `Skipped: `
if present, and are compared exactly with those declarations. Whitespace and
other text remain exact; coordinates, raw exception bodies and private paths
are not retained.

The baseline update must not change test collection or receipt code. When
only the expectations file changes after collection, independently verify
that all collection inputs, pins and producer/validator bytes are otherwise
identical. Otherwise collect both versions again under the existing review
process. Tests must not generate parameters or IDs from baseline values.

## Required gate and retained attempts

Each core leg publishes one bounded `receipt.json` artifact named
`core-receipt-{run_id}-{run_attempt}-{checkout_commit}-py{python}-{leg}`.
The required `CI gate` retains the all-job-success requirement and validates
all three current-attempt receipts, the exact full inventories and ordered
selection, the disjoint 3.11 union, and exact expected skips. Passing calls
with failed teardown do not count as passes.

PR receipts distinguish the reviewed source head from the tested merge
checkout. The checkout must be a two-parent merge containing that head and
have the same tracked tree. The gate independently derives the same identity.
Protected-main receipts bind the actual main commit/tree.

Only a **complete rerun of all three core legs** can satisfy a new attempt.
Older-attempt receipts may be retained under an exact bounded history
allowlist, but are recorded separately and never downloaded or credited by
the gate. Missing current receipts, future/unknown artifacts and partial
reruns fail closed. The final main collector additionally requires the
separately validated current candidate artifact; its package contract is
unchanged.

Receipts are public source/outcome metadata, capped at 8 MiB, with no raw test
properties, environment values or arbitrary exception bodies. Node IDs have a
128 KiB UTF-8 limit to accommodate existing long parameter IDs; skip reasons
and other fields retain their narrower limits. Archives are
validated as one exact ordinary member before parsing, with no extraction.
Receipt coverage does not replace native component evidence, hosted job
conclusions, source review or candidate verification.
