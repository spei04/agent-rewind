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
