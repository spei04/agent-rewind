# CI and candidate delivery

AR-051-A builds and tests the public source on GitHub-hosted Ubuntu 24.04 runners.
The compatibility matrix is CPython 3.11 and 3.12; later Python versions are not
claimed tested. No production environment, customer data, provider credential,
paid inference, package publication or deployment is part of this workflow.

## Trust and ownership

Every pull request and main push runs core lint/format/types/contracts/tests,
real PostgreSQL integration, Node syntax, gVisor isolation, static security,
locked dependency auditing, package inspection and an isolated installed-runtime
smoke test. All four required jobs feed the exact `CI gate` check. Its always-run
validator rejects failure, cancellation, skipped jobs and missing result entries.
No path filter can turn a required job into a false success. PR updates may
cancel earlier PR runs; active main runs are never cancelled by concurrency.
GitHub can replace pending runs in a concurrency group; delivery is not a promise
that every intermediate main commit produces a candidate.

The workflow token has only `contents: read`; checkout credentials are not
persisted. There is no privileged PR trigger, OIDC grant, repository secret,
artifact upload on PRs, publication or deployment step. All external actions use
verified full commit identities. Caches are disabled for the setup action.
Dependency resolution belongs in a reviewed lock update. Each dependency-consuming job first checks manifest/lock consistency with
`uv lock --check --offline`; CI sync uses the frozen
lock; tests use `uv run --no-sync`, and package builds run offline with the locked
build backend and build isolation disabled.

`.github/CODEOWNERS` routes changes to `spei04`. All current contributors share
that account, so this is not independent human approval. Internal contributor
review remains recorded in the delivery log and PR discussion. A separate
repository settings owner configures main protection, fork approval, read-only
tokens and the required `CI gate`; this change does not mutate those settings.
The delivery job additionally requires GitHub's `ref_protected` signal. Until
that settings read-back is verified, main-only eligibility must not be described
as proof of an enforced protected branch.

## Package boundary and candidate identity

PR package tests build locally on their disposable hosted runner and upload
nothing. A main push with every required job successful and `ref_protected=true`
rebuilds the candidate and repeats package validation and runtime smoke. Only
these four files may be uploaded, with seven-day retention:

- `agent_rewind-0.1.0-py3-none-any.whl`
- `agent_rewind-0.1.0.tar.gz`
- `candidate.json` (source commit, lock/manifest SHA-256, distribution SHA-256,
  tooling identity and tested Python versions)
- `SHA256SUMS` (the two distributions and candidate record)

`scripts/distribution-files.json` is the explicit member allowlist for both
archives. Changes to packaged modules/data must update it in the same reviewed
PR. The inspector rejects traversal, links, duplicate members, unknown members,
missing runtime assets, excess entries and oversized distributions. Source
archives exclude tests, contracts, research evidence, docs, examples and deployment
files. No workspace-wide artifact glob is used. `MANIFEST.in` controls source
inclusion; the separate inspector fails on unexpected backend output.

The runtime smoke creates a fresh environment outside the checkout, installs
only hashed locked runtime dependencies plus the verified wheel with dependency
resolution disabled, clears `PYTHONPATH`, and uses Python isolated mode. It
checks module provenance under that environment, imports the API/CLI, verifies
packaged web assets and invokes the installed `rewind --help` command. It rejects
installed development/build/audit tools. This is an installability check, not a
live deployment, migration rehearsal or production readiness certification.

## Security checks and exceptions

Ruff's `S` rules scan runtime and delivery Python code. `pip-audit` audits all
locked groups with strict collection, hashes, no dependency resolution and no
vulnerability exclusions. A finding or unavailable audit service fails the job.
The audit is scoped to dependency markers for the tested Linux/Python 3.12
security environment; it is not an all-platform reachability proof. Weekly
Dependabot updates cover GitHub Actions and uv, with three open version-update
PRs per ecosystem; security alerts/fix PR policy is managed separately.

The only static-rule exceptions are attached to individual source lines:
`S311` for reproducible randomized trial order (no secret generation), `S108`
for the container's private bounded `/tmp` tmpfs (no host temp path), and `S608`
for identifiers from the validated frozen synthetic SQLite schema vocabulary.
S603 covers the container helper's fixed certificate-regeneration and subject-hash
commands; they accept no caller-controlled argv and run only on reviewed trust inputs.
Do not expand these to directory-wide ignores. Remove an exception if its
assumption stops being true; changes require the same review as runtime code.
Runtime assertion guards remain active when Python optimization is enabled.

The build backend is pinned to setuptools 84.1.0 in both build-system and build
group, addressing [GHSA-xmj3-9gf7-h52w](https://github.com/advisories/GHSA-xmj3-9gf7-h52w)
and retaining the earlier [GHSA-h35f-9h28-mq5c](https://github.com/advisories/GHSA-h35f-9h28-mq5c)
repair. The runtime lock uses opentelemetry-api 1.45.1 for
[CVE-2026-114603](https://github.com/open-telemetry/opentelemetry-python/security/advisories/GHSA-xcq7-p3pf-p88h).
Cryptography remains locked to 50.0.2. These updates are included in the unsuppressed
audit; a prior GitHub alert read-back is not proof of the current complete lock.

The build tool is pinned to uv 0.13.4 to address
[GHSA-hq85-5cpj-mr62](https://github.com/astral-sh/uv/security/advisories/GHSA-hq85-5cpj-mr62).
The advisory affects uv's default bundled CA store before 0.13.4. Updating the
Python dependency certifi (already locked to 2026.10.19) does not update uv's
separate trust store. The repair uses the patched default store; custom or
system CA overrides require their own operator review.

All CI jobs verify the reviewed Linux x86_64 archive checksum. The container
installs only the hashed 0.13.4 Linux wheels listed in
[scripts/uv-requirements.txt](../../scripts/uv-requirements.txt), obtained from
[official PyPI release metadata](https://pypi.org/pypi/uv/0.13.4/json).
The package script refuses a different uv version before building. No project
dependency or lock content changes are required. Historical candidate records
retain their original tooling identity; they are not retroactively patched.
The package job builds the container and runs its installed CLI with networking
disabled on Linux x86_64. Other wheel architectures are pinned but are not
validated by that job. The pinned base retains the affected emSign ECC Root CA-G3 in both its OS
and pip-vendored stores. Updating uv alone does not repair these stores.

Before any network bootstrap, the container-only
[scripts/container_ca.py](../../scripts/container_ca.py) helper verifies the
reviewed original trust sets and removes only DER SHA-256
86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b.
It disables the exact Debian source entry, removes that source certificate,
regenerates the OS bundle and hashed directory, and removes the same certificate
from base pip's separate bundle. It checks every hashed alias's subject hash,
collision sequence and resolved target. All identity, path, configuration and
PEM checks precede mutation; any mismatch stops the build before pip downloads.
TLS remains enabled and active CA, pip-configuration and OpenSSL configuration
overrides are rejected.

The final offline container check verifies four distinct stores: the OS bundle,
OpenSSL's actual hashed default directory, base pip's pinned vendored bundle, and
the installed application interpreter's certifi bundle. Versioned expected sets
require exactly 149, 149, 150 and 120 retained roots respectively. Set identities
are SHA-256 over sorted lowercase DER-SHA256 values joined by ASCII LF without a
terminal LF. The JSON container_final_ca_trust_verified marker binds these
identities, root counts, affected fingerprint and resolved store paths. The
candidate verifier must check this actual hosted image evidence; a passing source
test or prior uv-only build is insufficient.

This is an exact-image workaround, scoped to the tested Linux x86_64 build.
The immutable Python base and the separate gVisor isolation image remain
unchanged; the isolation fixture does not inherit this application-image repair.
No host trust store is modified. Remove the helper only after a reviewed immutable
upstream image fixes both OS and base pip trust, with explicit comparison of all
added/removed roots and final hosted-image verification. The inspected upstream
replacement removed another root while retaining G3 in pip, so it was unsuitable.

## Verified external inputs (actions and images: 2026-10-19; uv: 2026-10-21)

Action tag-to-commit associations and GitHub commit verification flags were
read from the official repository APIs. The full immutable commits are in the
workflow; the tags below identify the release notes used for review:

| Input | Reviewed source and identity |
| --- | --- |
| Checkout v7.0.1 | [Official release](https://github.com/actions/checkout/releases/tag/v7.0.1), `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| Setup Python v7.0.0 | [Official release](https://github.com/actions/setup-python/releases/tag/v7.0.0), `5fda3b95a4ea91299a34e894583c3862153e4b97` |
| Setup uv v10.3.0 | [Official release](https://github.com/astral-sh/setup-uv/releases/tag/v10.3.0), `1c37ad07a6a961277cf70c0d37d6f313000f5884` |
| Upload artifact v7.0.2 | [Official release](https://github.com/actions/upload-artifact/releases/tag/v7.0.2), `cf430e030ddbb5b0abf93d22962f4752f3646cd9` |
| uv 0.13.4 | [Official release](https://github.com/astral-sh/uv/releases/tag/0.13.4), Linux x86_64 archive SHA-256 `2b428396f12572d4429cf210ca234dd599a33b3af0958a4d5ed569d63e3f344f` |
| PostgreSQL 16.15/alpine3.24 | [Official image recipe](https://github.com/docker-library/postgres/tree/9d15534160ade17f2b6c455a39ee967c49b1937d/16/alpine3.24), registry index SHA-256 `721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea` |
| gVisor 20261012.0 amd64 Debian package | [Official package index](https://storage.googleapis.com/gvisor/releases/dists/release/main/binary-amd64/Packages), [release](https://github.com/google/gvisor/releases/tag/release-20261012.0), package SHA-256 `7a440a035128a52f489b0bb76f60ac4df9cabe7cdf31dd5fd79a3e80f8a707ca` |

The PostgreSQL raw manifest SHA-256 matched the registry digest header. The
runsc package filename is versioned and its reviewed hash and package version
are checked before installation; the moving package index is not consumed by CI.
The Debian package supplies the sidecars required by current gVisor. This is a
pinned-content check, not a claim that the package's release commit was signed.
The existing sandbox Python image digest is preserved unchanged.

For updates, resolve action tags through the official API, verify the returned
commit identity, inspect release changes, and replace the full SHA. Resolve image
manifests from the official registry and compare the raw digest/header. For runsc,
review the official package index/release and update version, URL and SHA together.
Use pinned uv to update lock metadata; never waive an advisory merely because
its affected code appears unreachable. Run the complete hosted workflow after
any input update. Primary references: [GitHub concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency),
[uv CLI](https://docs.astral.sh/uv/reference/cli/),
[pip-audit](https://github.com/pypa/pip-audit/tree/v2.10.1),
[gVisor install](https://gvisor.dev/docs/user_guide/install/), and
[Dependabot options](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference).

## Promotion and rollback

1. Select a successful main workflow and verify `CI gate` plus candidate delivery,
   the source commit, current protection/settings read-back and independent review
   record. Verify all three `SHA256SUMS` entries, then match `candidate.json` to
   the source commit and lockfile. Retain an approved candidate and its record in
   the designated release record store before the seven-day artifact expires;
   this workflow does not create that store or upload private evidence.
2. Promotion remains a separate operator decision requiring environment/data/
   budget approvals, deployed configuration, schema compatibility, recovery
   evidence and the relevant milestone gates. No auto-promotion is provided.
3. For rollback, choose a previously verified retained candidate whose reader and
   schema compatibility are explicitly supported. Restore application/config
   identity together; never downgrade a database by assumption. If schema rollback
   is unsupported, use the documented verified restore procedure and stop admission
   until recovery checks pass. Record incident/release identity outside disposable
   checkouts. Candidate delivery alone cannot satisfy those recovery gates.
