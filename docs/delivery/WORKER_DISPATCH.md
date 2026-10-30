# Internal worker dispatch boundary

The dispatch coordinator owns a new reservation and the durable
`reserved → dispatching` transition. It calls the bound adapter once, only
after both transactions acknowledge commit and release their connections cleanly.

The coordinator checks the original request bytes, scoped job and configuration,
price version, owner, generation, cancellation and database-time lease. Existing
reservations cannot authorize dispatch through this entry point. A lost commit
acknowledgment, failed cleanup or existing call refuses execution. No transaction
or database lock remains open during the adapter call.

Provider exceptions return a fixed uncertainty error. The call remains
`dispatching`; reservations, ledger entries and account balances are retained.
This state establishes neither a provider response nor a bill, refund or terminal
job failure. Cancellation and expiry can race after the final database check;
the component makes no exactly-once provider guarantee.

The server must supply an immutable adapter whose configuration matches its
installed image, code, endpoint and processor permissions. Its request validator
must enforce token and price bounds before reservation. There is no default
provider adapter. The caller's acknowledged claim and execution ownership remain
integration responsibilities.

## Validation and remaining work

SQLite tests cover the transition, competing callers, request/configuration
mismatch, cancellation, stale ownership, expiry, reservation and dispatch
acknowledgment loss, cleanup failure, provider failure and restart refusal.
The setup uses the existing synthetic admission fixture; these tests do not
establish unpatched admission or worker startup. PostgreSQL validation uses a
separate restricted application role and an explicit `UPDATE(state)` grant.

This is an internal prerequisite for [worker integration](../EXECUTION_BACKLOG.md#ar-010-b-p2).
Default admission, release compatibility and worker behavior remain unchanged.
Full admitted execution still requires the supported runtime profile, actual
configuration/provider adapter, failure persistence, Engine recording,
generation-fenced result publication and recovery integration.

The user has approved payment within **$200 total including prior charges**.
Unknown historical exposure still prevents assigning a verified paid allowance.
Component validation performs no model requests.

## Remaining admitted-startup integration — 2026-10-30

The source audit of `84d63879` and dispatch `67f14673` found concrete
composition work beyond the internal dispatch boundary. Accepted admission,
ledger, publication and failure components retain their own status. Their
integration is unfinished.

| Work boundary | Owner and prerequisite | Contract and acceptance evidence |
| --- | --- | --- |
| Admission and account provenance | Backend; accepted admission/ledger components, with P2 implementation after whole P1 | Freeze a finite immutable job account and its trusted provenance, scoped configuration and idempotent acknowledgment/recovery behavior. A queued job currently lacks the account required for claim, and a direct account INSERT fails manifest reconciliation. Use a separately versioned live provenance contract. Existing offline provisioning owns a separate transaction; it cannot join admission. Select storage and its revision explicitly before code; do not repurpose migration progress or expand F2. |
| Installed execution adapter | Backend/platform; accepted claim and dispatch plus P2 entry | Bind the frozen configuration to installed code/image, endpoint and processor permissions. Retain acknowledged claim ownership and validate the v2 envelope. No current-Settings fallback or caller-created execution capability. |
| Recording and terminal publication | Backend/storage; accepted P1 producers and C04 publication components | All Engine/job/event/root/ref/projection writers must participate in project-first exclusion and current-generation fencing. Validate the actual successor profile; broadening an old revision check is insufficient. Commit terminal state and evidence atomically; prove cancellation, takeover and unknown-ACK behavior. |
| Configured development startup | Platform/quality; the preceding integrations | Start the actual packaged application and worker, submit through authorized admission, claim, dispatch and observe a terminal result without patched readiness. Include process interruption, restart reconciliation and unsupported-profile refusal on SQLite and restricted PostgreSQL. |

The lead adopts a separate internal admission/account publication boundary.
Existing offline provisioning remains unchanged. Live admission must atomically
publish the operation, job, account and authentic provenance, with a fixed
trusted issuer and finite period/limit policy. Acknowledged commit and clean
release establish success; unknown acknowledgment or cleanup failure requires
fresh authorized SQL reconciliation of the complete tuple. Partial state or an
admission journal entry cannot authorize replay or dispatch. The exact storage
representation, writer permissions and bounded history-growth policy remain
entry decisions; no revision beyond the existing F2 reservation is assigned here.

The first end-to-end product proof remains one real coding-agent failure
restored from a saved checkpoint, with original and intervention branches plus
independently checkable evaluation results. It additionally needs accepted
checkpoint/restore support, a real model adapter and a reconciled experiment
allowance. Regional rollout and broader enterprise operations remain later
milestones; they do not replace this finite proof.

The initial adapter can be deterministic and disconnected for acceptance of
this plumbing. It cannot establish model quality, checkpoint replay, provider
billing or production readiness. Normal job completion remains distinct from a
resolved provider charge: AR-023-B owns observed receipts and AR-023-C owns
evidence-based settlement; unknown holds remain intact.

P2's retained **2 [2–3] day** estimate covers its earlier terminal-wiring scope.
It is not a credible forecast for all the integration above. Before assigning
P2 implementation, freeze the admission/account representation and independently
reviewable PR boundaries, then reforecast P2 and the aggregate schedule together.
If the handoff needs additive storage, explicitly allocate its owner, linear
revision, preservation/rollback tests and dependencies; the one-relation F2
scope does not expand implicitly.

The sequence remains F1 delivery → F2 dormant successor → F3 persistence →
F4 consumers → F5 recovery/P1 acceptance → P2 integration. Design review and
test-vector preparation may proceed in parallel; downstream implementation
retains these entry gates. AR-012-B verifies the integrated result and does not
own missing runtime implementation. AR-006-C retains stale-projection repair;
AR-014/AR-017 remain prerequisites for checkpoint restoration and broader
process recovery claims. Production and paid experiments remain separately
gated.
