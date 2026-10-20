# G0 development decision

Recorded 2026-10-19. Owner: spei04. Coordinator: project lead.

**Decision: proceed with the reviewed development and test scope.** The project
owner explicitly approved the execution backlog and instructed the project lead
to assign independent contributors and reassign completed slots. This records that
existing authorization; it does not invent a later production approval or require
reapproval of ordinary implementation choices. The owner subsequently confirmed:
“Yes—build and test first; gate production spending and partner data.”

## Reviewed inputs and scope

C04 revision `m1-review-2`, reviewed source
`22c43765f83d815328e3a222a1d56e2aca4dff8c`, was merged in
[PR #24](https://github.com/spei04/agent-rewind/pull/24) at `4a1a5ae`.
The [machine review record](../../contracts/proposals/m1.freeze.json) names each
actual contributor, role, date, disposition and source commit. A accepted FE/RS;
C accepted PL/QE/SEC; B supplied the backend proposal and checks; the lead reviewed
source, independently reran 147 targeted tests and accepted integration after
core/PostgreSQL and gVisor CI passed. These are internal engineering reviews,
not external security or statistical certifications.

The first runtime slice is **AR-005-B then AR-005-C**:

- Install a linear Alembic baseline/adoption history using explicit frozen DDL;
  classify known PostgreSQL/SQLite schemas and refuse unknown or partial shapes.
- Require bounded migration locking and actual legacy-writer exclusion. Persist
  fresh/legacy installation provenance and explicit adoption intent without
  creating the later organization/project/membership ownership schema.
- Preserve literal historical rows, timestamps, event identities, ciphertext and
  conservative reservations; prove refusal, interruption and recovery on fixtures.
- Add read-only release-profile guards before API admission and worker claims.
  Migration-only readiness cannot activate customer service before required
  ownership and scoped backfills are complete.

AR-007-A retains ownership DDL/backfill and fresh organization initialization.
AR-011-B follows AR-005-C and owns the bounded readiness byte reader; AR-009-A
consumes it. Subsequent engineering work proceeds only when its prerequisites and
integration gates pass.

## Capacity, environment and funding disposition

Execution uses three delegated contributor slots selected by the lead;
it is not six confirmed human full-time hires. C is assigned the migration after this record integrates. A newly prioritized
CI/CD slice assigns B implementation and A independent review; migration review
will use the next available independent slot. AR-033-A stays queued. Named production
operators and support capacity remain unconfirmed.

Development continues in the existing cloud workspace. Use synthetic fixtures,
existing tooling and hosted CI; no production deployment or new paid resource is
authorized here. The `us-central1` cost-model example remains an example, not a
residency decision. ENV0 owns actual production project, region, network, IAM,
recurring funding and operating responsibility. Customer-data, IdP, partner,
independent assessment, pilot and release gates remain unsatisfied.

Existing total model-validation authorization remains **$200**. Historical
conservative reservations are $36.567974; their arithmetic remainder is not an
invoice reconciliation. This execution batch has made zero provider calls.
PAID0 must reconcile authorization, rates and reservations before a new live
experiment. No study or recurring infrastructure budget is inferred.

Shared storage remains constrained. Do not provision a local database, download
new environments or build images without safe headroom; use hosted CI for heavier
PostgreSQL and sandbox checks. Preserve active checkouts and private evidence.
Capacity failure changes the work plan, not preservation criteria.

## Gate evidence and limitations

E0 is the owner's actual execution approval. ARCH0 is satisfied **for this bounded
development/test scope**, using the accepted single-organization self-hosted
architecture and the dispositions above. AR-004-C records the decision; G0 joins
verified AR-001-B, AR-002-B, AR-003-B and AR-004-C. Production-specific assumptions
are routed to their existing external gates, not marked approved.

The 24 CT-M1 behavioral cases remain **planned, not executed**. No schema migration,
restore drill, project-isolation behavior, new live agent outcome or enterprise
readiness is claimed. G1 requires actual implementation and integration evidence.
Unknown schema/profile findings block adoption and use existing task contingency;
they never justify guessing historical ownership or relaxing preservation.

Record validation: Engineer A independently accepted this authority/evidence and
test transition on 2026-10-19T23:57:30Z; 79 review/harness tests and the full
contract checker passed. Lead integration passed 435 core tests (one environment
skip), lint and formatting. These checks validate the decision record and existing
implementation; the 24 new M1 runtime cases remain planned.
