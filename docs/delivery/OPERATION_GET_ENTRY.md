# GET Operation adapter entry

2026-10-21 · AR-008-B/P1 [#94](https://github.com/spei04/agent-rewind/issues/94).
Engineer C owns this GET slice in the reused secondary checkout. Engineer A
owns the separate cancellation phase helper and its shared private receipt
hooks. This document records the implementation handoff for review; it does
not implement a service, advance task status or establish final P1 acceptance.

The accepted [adapter entry](OPERATION_ADAPTER_ENTRY.md) and
[HTTP execution plan](OPERATION_HTTP_EXECUTION_PLAN.md) remain authoritative.
The starting composition is `e43aecfd255dadeadd4d4eab7d1eaead88aa1222`;
GET primitives remain those reviewed at `691ad66156ef9c19b7c953c5d194013f76fc7faf`.
Their independent SQLite and PostgreSQL evidence does not establish the
whole-service authority, loader, response or cleanup composition below.

## File and interface boundary

The next separately assigned runtime slice is one focused
`agent_rewind/operation_service.py`, dedicated GET tests, its one distribution
allowlist entry and a scoped implementation-guide update. Preserve the existing
public GET primitive signatures. A's cancellation work may factor shared
private internals without changing GET semantics; coordinate that immutable
handoff before composition. No cancellation method, effect or phase owner
belongs in this slice.

```python
class OperationService:
    def __init__(
        self,
        engine: Engine,
        authority: RequestAuthority,
        *,
        artifact_loader: ArtifactLoader | None = None,
    ) -> None: ...

    def schema_compatibility(self) -> CompatibilityResult: ...

    def read_operation(
        self,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        operation_id: str,
    ) -> OperationView: ...
```

`OperationView` is a focused strict typed mapping or validated value containing
exactly these ten required fields, including explicit null and false values:

| Field | Source |
| --- | --- |
| id | Original validated operation ID |
| project_id | Original named project |
| job_id | Original operation's actual associated job |
| client_operation_id | Original validated operation identity |
| status | Supported validated original job status |
| cancel_requested | Boolean from the validated original cancel field |
| result_run_id | Null, or verified result artifact's exact cohort member |
| budget_microusd | Original validated integer job budget |
| reserved_microusd | Original validated integer job reserved amount |
| error | Null for every initially supported row |

Preserve integer precision, including `2**53 + 1`, and permit a valid reserved
amount above budget. Do not derive execution status from evaluator success.
The canonical response must fit the accepted 2,048-byte response bound.

The supplied principal is authenticated identity, not a lasting grant. The
context is the original named-project context; never resolve the current
legacy default or redirect after a membership change. A same-project viewer
may differ from the creator. The configuration actor must still match the
original operation creator.

## Reuse and narrow new helpers

Reuse these existing APIs directly:

- `operation_work.OperationWork` and `operation_connection` for sequential
  read-only scopes, native limits, shared counters and mandatory cleanup.
- `RequestAuthority.check(connection, principal, context, action="read")`
  without resource arguments. Its resource path would invoke a separate
  Lineage closure; this service instead supplies the complete budgeted
  resource proof through the primitives below.
- `operation_reads.ReceiptBook`, `read_operation`, `read_job`,
  `read_descriptor`, `validate_association` and `observe_result`.
- `operation_sources.read_run_cohort`, `validate_result_member` and
  `verify_read_snapshot`.
- The real `runtime_schema_compatibility`, owned SQLite capability check,
  `scoped_artifacts.ArtifactLoader`, and existing finite error vocabulary.

Do not call `AdmissionRepository.get_operation`, resource-bearing
`RequestAuthority.check`, `RequestAuthority.named/legacy`, or an unscoped
Database accessor within the service. Their relevant semantics are retained,
but their independent connections or closure reads would bypass this
composition's explicit accounting.

Only three small service-local responsibilities are new: the support/response
mapping, strict result parsing, and a primary visibility check:

```python
_primary_visible(
    connection: Connection,
    context: ProjectContext,
    operation_id: str,
    original_job_id: str,
) -> None
```

This is one bounded constant-only SQL observation: the requested operation
exists in the original project, and the original actual job still exists with
its original project/job resource scope. It returns presence, not protected
row bodies. There is no operation resource-scope discriminator. It must not
follow a changed operation.job_id, traverse Lineage or reread job16 into the
receipt book. Association drift remains a final original-receipt mismatch. Do not join the
current operation.job_id to the original job in this presence query: a
reassociation is receipt-mismatch 503, not fabricated primary-resource 404.

This helper does not consume another source visit: it performs no source-body
load or ancestry expansion. Its SQL and execution time are fully charged.
That distinction preserves the supported one job plus 255 cohort records
within 256 visits; tests must verify it rather than silently raising the cap.

## Exact GET sequence

1. Validate principal shape without SQL. For SQLite, require the supported
   owned engine before the first acquisition, including compatibility
   inspection. Unknown or invalid provenance refuses; never catch an ownership
   failure to use the legacy path. PostgreSQL keeps the reviewed behavior.
   Run real compatibility inspection in its own completed scope, before
   OperationWork attaches. This avoids nested callback replacement.
   Migration-only/incompatible state produces schema_incompatible before
   customer rows; inspection unavailability produces dependency_unavailable.
   Only a per-instance synthetic test profile may exercise the future-ready
   path. Do not change packaged profiles or a global guard.

2. Create exactly one OperationWork and one strict GET ReceiptBook. In the
   first operation_connection scope, check current original-project read
   authority, then validate the operation identifier. Read the bounded
   operation14 and actual scoped job16. Read the job-owned admission_config
   descriptor and validate the version-2 run/config/digest/original-creator
   association. Apply the support table before storage work. Observe the
   optional result candidates even when jobs.result is null, then read and
   validate the complete scoped by-job root cohort. Check primary visibility
   and fresh same-context project authority before releasing the scope.

3. With all connections and locks released, handle the optional result as
   specified below. There is at most one loader call, no current registry,
   readiness, provider, Docker, admission or worker call. Retain original SQL
   receipts; artifact bytes never replace them.

4. Enter a second operation_connection with the same work and receipt book.
   Check current original-project authority and primary visibility. Construct
   and validate the exact bounded response from the retained original rows
   and verified optional result. Execute verify_read_snapshot once, then check
   fresh project read authority as the last protected SQL. No artifact load
   or protected query follows that check. Return the prepared value only after
   the connection scope's cleanup and work.finish succeed.

The final query retains the full original operation14/job16, native type/null
identity, config and optional result descriptors/ref IDs, scope membership,
candidate cardinalities, source bodies and complete by-job membership. It
must refuse missing, substituted, additional or malformed candidates.
Later reads never replace expected originals. This is optimistic
READ COMMITTED revalidation, not a response-linearizability promise.

## Supported status and result observations

Validate native row types and the operation/config/job association first.

| Job status | SQL jobs.error | GET behavior |
| --- | --- | --- |
| queued, running, succeeded, cancelled | NULL | Render stored status and error:null |
| failed | NULL | Fixed 503: required supported failure evidence is absent |
| Any recognized status | Any non-NULL value, including empty or JSON-looking text | Fixed 503 before loader; do not parse or expose it |
| Unknown status or malformed/contradictory source | Any | Fixed refusal; no partial response |

No stored Error envelope is currently supported. The current worker and
complete_job write legacy strings; admission's failure_correlation_id is
origin evidence, not a trusted failure code/envelope. Healthy rows may have
null correlation. No migration marker, failure code, polling correlation or
fake terminal outcome is invented. AR-010-B retains producer ownership.

For SQL NULL jobs.result, return result_run_id:null and make zero loader calls.
The primitive may observe zero or one valid job-owned result ref; preserve
that exact observation and descriptor, if present, for final revalidation.
Do not infer a run ID from such a ref. Zero-to-one, one-to-zero, one-to-two and
descriptor substitution changes must refuse the strict GET snapshot.

For non-null jobs.result:

- Require exactly one already observed same-project, job-owned role=result
  reference, an exact digest match and format-1 scoped object.
- Retain all seven descriptor values and the reference identity. The plaintext
  bound is 4,096 bytes, enforced by the verified loader using the validated
  descriptor before materialization. The existing local verified storage
  implementation uses that descriptor limit for ciphertext/plaintext reads.
- Invoke the synchronous ArtifactLoader exactly once outside SQL scopes. A
  missing loader or malformed/non-bytes result refuses. Verify returned type,
  length, digest and the 4,096-byte bound; the service does not trust an
  injected callback merely because its signature matches.
- Decode as strict UTF-8, then parse the decoded string with duplicate-key
  rejection. Require exactly one key, run_id, whose value is 32 lowercase
  hexadecimal characters, with no extra fields or nonfinite values. Do not
  pass original bytes directly to json.loads: its UTF-16/32 autodetection is
  not UTF-8 validation. Reuse existing duplicate-rejection behavior without
  introducing a general parser framework.
- Require exact membership in the original validated cohort. Multiple legal
  root runs remain supported, but no first/latest heuristic may choose one.
  A returned run ID proves neither graph completeness nor replay/evaluator
  success.

The cohort proof is complete for the supported admission run job: its parent
is null and it cannot own a study. All selected same-project by-job members,
including malformed study/unknown-kind candidates, remain refusal candidates.
Foreign scoped rows are excluded by ownership; a malformed selected member
cannot disappear through filtering. This is returned-result lineage, not
admission source ancestry.

## Visibility and finite failure boundaries

The requested operation and original actual job are primary resources.
Unknown/foreign operation or missing/inaccessible original job/scope is 404.
Once those are established, invalid config/result/ref/cohort evidence is a
secondary proof failure and produces dependency_unavailable only while the
caller remains authorized.

Keep authority calls outside secondary ResourceNotFound translation. After
a secondary proof or loader failure and connection cleanup, perform at most
one bounded fresh original-project authority/primary-visibility check using
the same remaining OperationWork. If a valid original job identity has not
yet been established, recheck project authority only; do not fabricate an ID.
Never issue this check inside an aborted PostgreSQL transaction. If fresh
authority cannot be established because SQL or remaining work is unavailable,
return fixed dependency_unavailable rather than inventing visibility. An
original typed denial is preserved without entering this secondary-failure
recheck. A revoked caller retains typed 401/403/404. In particular, revoked during
result load is 404, whereas an authorized caller with foreign secondary
result evidence receives 503. Exhaustion is not permission to reset a
budget, loop, acquire indefinitely or retry protected work.

| Boundary | Failure result |
| --- | --- |
| Real compatibility incompatible/migration-only | Fault(schema_incompatible), 503, not retryable |
| Compatibility unavailable; known SQL/native/budget/cleanup failure | Fault(dependency_unavailable), 503 |
| Typed current identity/project/action denial | Preserve IdentityInvalid / ResourceNotFound / ActionForbidden |
| Known bounded metadata, result parse, artifact verification or missing-loader failure | After the fresh-authority rule, fixed dependency_unavailable from None |
| Unexpected programming exception | Preserve the existing safe internal_error boundary |
| BaseException/interruption | Preserve identity after mandatory cleanup |

Map known AdmissionError/read-storage errors deliberately after release;
do not blanket-catch all exceptions or turn typed authority failures into
dependency errors. Ordinary operation_connection failures are reads and do
not invent outcome_uncertain. There is no successful mutation, audit, ref
change, reservation change or cancellation to reconcile in GET.

## Budget forecast and required measurement

All request SQL phases share the accepted 512 charged attempts, 10 SQL-active
seconds and 20,000,000 SQLite VM instructions. Receipt ownership retains
256 source visits, 512 edges, 4 MiB, 259 identities and the 64-bind final-query
cap. The one job and 255 roots plus operation/config/result reach 259 retained
identities. There is no second cumulative 4 MiB decode-work ceiling.

Normal-path forecast from the current source, not measured service evidence:

| Component | OIDC principal | API-key principal |
| --- | ---: | ---: |
| Four fresh project-authority checks | 4 SELECTs | 8 SELECTs |
| Operation, job, config, optional result, cohort | 5 SELECTs | 5 SELECTs |
| Two constant-only primary visibility checks | 2 SELECTs | 2 SELECTs |
| One final relational receipt check | 1 SELECT | 1 SELECT |
| Total body SELECTs | 12 | 16 |
| PostgreSQL charged attempts | 50 | 62 |
| SQLite charged attempts | 40 | 48 |

PostgreSQL normal setup/cleanup costs 7 per read scope and each body SELECT
costs 3 including the two native timeout setters. SQLite costs 8 per read scope
and 2 per SELECT including its setter. The forecast therefore uses
14 + 3N and 16 + 2N across two scopes. A normal exceptional authority/visibility
recheck adds at most 16 PostgreSQL or 14 SQLite attempts. Fault disposal can
use reserved cleanup attempts; the shared limit and eight-action cleanup
reserve remain authoritative, not these normal-path forecasts.

Compatibility has its separate reviewed finite inspection budget. Pool wait
and storage latency are not a new end-to-end 10-second guarantee. Work counters
and SQL-active time never reset between operation scopes; failed cleanup
cannot yield a successful response. Verify actual final counts after cleanup,
not just samples taken inside a connection scope.

The primitive PostgreSQL trace 26 was sampled before normal rollback/close,
so 28 is its source-derived final count, not a new measurement. The SQLite
distractor trace 16 similarly implies normal final 20; the clean SQLite final
20 was actually sampled after scope exit. The append-only private erratum
binds source691ad and guide correction2b83. These primitive numbers and the
earlier 74/162 phase proposals are not whole-service capacity proof.

## First vertical checkpoint acceptance

Keep the runtime slice independently reviewable before HTTP or cancellation:

- Real migration-only zero-customer-sink guard and invalid owned-engine refusal
  before any acquisition; per-instance future-profile tests remain distinct.
- Same-project noncreator viewer success; original creator/config association
  enforcement; cookie and API-key expiry, revocation and role ceiling;
  changed legacy default never redirects the original named context.
- Every support-table row, explicit null/false, integer precision and
  reserved-above-budget controls; no error canary or fabricated correlation.
- One real verified encrypted result load at the 4,096-byte boundary with no
  SQL checkout held; null result zero loads; missing loader, format, digest,
  byte count, UTF-16/32, duplicate key, extra key and invalid-member refusals.
- Revocation or primary deletion/scope loss during load gives typed denial;
  authorized foreign or malformed secondary evidence gives fixed 503.
- Original row/type/null, association, ref cardinality, absent-to-new ref and
  cohort phantom changes refuse in the final relational observation, without
  replacing original expected receipts.
- Full 255-root/259-identity matching service case, overflow and substantial
  same-project/foreign distractors under unchanged VM/time/statement budgets.
  Report actual complete traces; no index or throughput claim is added.
- Actual PostgreSQL SELECT-only app-role read proof, native read-only
  transaction behavior, final-deadline/cleanup failure refusal, usable pool
  reuse and zero audit/DML/storage-write effects.

A currently owns the existing synthetic PostgreSQL lifecycle for cancellation
phase proof. GET proof must wait for an explicit clean lifecycle handoff and
reuse that instance; no second instance, installation or resource is needed.
No runtime work begins merely because this document is committed.
