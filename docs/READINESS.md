# Safe errors and bounded readiness

AR-011-B implements the application boundary and installation sentinel described
by C04. The packaged schema profile remains migration-only. Passing transport
and sentinel tests does not activate customer traffic, authorize partner data,
provision infrastructure, or establish a production availability SLO.

## Public interface and admission

Every request reaching the application receives a freshly generated 128-bit
lowercase hexadecimal X-Request-ID. Caller-supplied correlation headers are
ignored. Responses use Cache-Control: no-store. Versioned API errors and
/readyz failures use exactly code, message, request_id and retryable; existing
legacy endpoints retain a fixed safe detail field. Authentication failures retain
WWW-Authenticate: Bearer, and the bounded quota response supplies Retry-After.
No exception string, validation input/location, SQL, provider body, cookie or
request path is serialized into these errors.

Known faults use the frozen templates. Generic ValueError and KeyError are
internal faults, not automatically validation/not-found responses. Explicit
record lookup translates only its documented absence into not_found. A database
fault during a mutation is outcome_uncertain: the request may have committed,
so clients must reconcile its original identity rather than assume failure.
Unexpected errors emit a restricted request_failed record containing only a
fixed error code and generated request ID. The logger never receives the
exception, its traceback, locals, class name or request contents. The bounded JSON
message includes correlation even under the default log formatter. If a logging
sink raises, that diagnostic is lost; its exception is never re-logged or allowed
to replace the safe response, including after streamed headers. No tracing or
metric exporter is enabled by this change. The serve command keeps access logs
disabled; deployments must not enable raw proxy/access/debug-body capture.

GET/HEAD /livez remains process liveness with {status:live}. GET/HEAD /healthz
retains its existing read-only database-connectivity behavior; an incompatible
schema can still have a healthy /healthz. GET/HEAD /readyz returns {status:ready}
only after the complete probe succeeds, otherwise a safe 503 envelope.
Incompatible schema maps to schema_incompatible; unknown, unavailable, timeout,
capacity exhaustion and drain map to dependency_unavailable.

Legacy POST /api/runs, /api/branches, /api/studies and /api/investigations require
readiness after the fresh schema guard and operator authorization, before any
artifact upload or admission commit. Cancellation, key revocation and logout
keep their existing schema/authentication/operation checks but do not depend on
sentinel availability. This is the boundary future versioned submission must
reuse; no versioned submission route is added here. A cached readiness success
never grants authorization, bypasses the per-request schema check or replaces
transactional ownership/budget/publication invariants.

## Physical resource and deadline contract

Production readiness is Linux-only. Unsupported platforms remain unready.
The application lifespan prewarms one fresh interpreter with no inherited
database-pool sockets. It owns a separate pool with size one and zero overflow.
The C14 envelope includes one fixed readiness connection per API process in
addition to application pools; readiness does not prove free application-pool
capacity.

Configuration travels through a private bounded pipe, never command-line
arguments or logs. The child receives only its database/store/encryption
configuration and an allowlisted storage environment. Provider and IdP secrets
are excluded. Modern AWS profile files, legacy Boto files and credential_process
are disabled; supported
storage identity comes from explicit AWS environment credentials, web identity,
container credentials or instance identity. No subprocess credential helper is
supported. Standard error is discarded and stdout is a finite three-result
protocol with a 64-byte frame limit. Invalid, oversized and partial frames
cannot be interpreted as success.

The child installs Linux PR_SET_PDEATHSIG=SIGKILL before client imports and
checks the expected parent PID to close the setup race. Core dumps are disabled.
Startup has a five-second bound; readiness fails immediately until the handshake
completes. The complete probe has one monotonic one-second deadline, starting
before its task is scheduled and covering IPC, database/schema inspection,
sentinel reads and decryption. A late success is discarded.

At most one physical readiness probe is owned at a time. Timeout or requester
cancellation kills the process group. The response need not wait for process
reaping: the slot remains unavailable until actual cleanup completes, and no
replacement is spawned before that. Restart initialization is lifecycle work
with a five-second delay, not work started by an incoming request. Application
shutdown marks drain, invalidates cache, terminates and reaps the worker. Pending
spawn ownership transfers to retained cleanup before a timeout/cancellation path
returns; repeated shutdown-caller cancellation cannot cancel that owner or permit
a replacement before the original child handle is delivered and reaped.
Parent-death containment prevents a crashed application leaving a live probe;
the operating system owns orphan reaping after parent death.

Successful results are cached for at most five seconds; failures are not cached.
Exit, restart and drain invalidate success. A busy probe refuses another check
instead of queueing unlimited work. The one-second limit is an application
deadline, not a hard realtime guarantee under an unscheduled process or an
uninterruptible kernel. Cleanup ownership remains retained in those cases.

## Explicit installation sentinel

Set the private REWIND_INSTALLATION_KEY to the installation identity already
established by metadata migration, together with the artifact encryption and
local/S3 configuration. The identity uses the shared metadata grammar: 1–64 ASCII
letters, digits, underscores or hyphens, starting with a letter or digit. Invalid
identities are rejected before publishing bytes. Run:

    rewind doctor --provision-sentinel

This flag executes only sentinel installation. It does not initialize/upgrade
metadata, enumerate customer objects, call a model, start a sandbox or validate
sandbox images. The other doctor behavior is unchanged.

The command publishes one encrypted object at
system/<installation_key>/readiness-v1. Its plaintext is canonical JSON containing
exactly schema:1, purpose:"readiness" and the configured installation_key.
Only after verifying publication does it atomically write the fixed locator,
installation identity and plaintext SHA-256 into data_dir/readiness.json.
Configuration is owner-readable mode 0600; root/intermediate/final symlinks and
special files are refused. The installation identity is private configuration,
never a public health field.

Local publication writes and fsyncs a private temporary inode, then atomically
links it to the final name without replacing existing bytes. Interruption before
publication cannot leave a partial authoritative object. A valid existing object
can be reused; corrupt or wrong-key existing bytes are refused. For a previously
corrupted installation, an operator must preserve/inspect the old sentinel and
deliberately remove or relocate it before reinstalling. No request performs this
repair. Interrupted private .sentinel-* temporary files may be reviewed and removed
after confirming no active installer; they are not referenced by readiness.
S3 publication uses conditional object creation. Config replacement is available
only through the explicit operator command, after successful verification.

The probe consumes only this private installation config and a nonempty
installation identity from the validated schema result. A missing or different
metadata identity refuses before artifact I/O. The future customer-ready schema
handler must derive that identity in the same validated metadata transaction;
current migration-only handlers deliberately provide no readiness authority.

Local reads use directory-relative no-follow opens, nonblocking regular-file
checks, fstat and a capped stream. S3 reads request bytes 0–5560, validate returned
length/range, close the body, and retain a read cap if the service ignores Range.
The reader consumes at most the first excess byte: ciphertext over 5560 bytes
fails before decryption. Authenticated plaintext is bounded at 4096 bytes and
must match both the configured SHA-256 and exact canonical payload. A customer
objects/ locator cannot pass, even with a matching digest.

read_system_sentinel(settings, deadline, installation_key=validated_identity)
is installation-only and must run inside the supervised deadline. The bounded
read/decrypt primitive in bounded_bytes.py is reusable by AR-009-A, but grants no
namespace authorization and provides no independent wall-clock cancellation.
Customer storage requires its separate scoped interface. The sentinel read does
not prove object write permission, retention, provider availability, sandbox
capacity or IdP availability.

## Verification and remaining gates

Tests exercise first-excess-byte detection, short reads, regular-file/FIFO/symlink
refusal, corrupt keys/ciphertext/config, S3 length/range mismatches, exact identity
binding, atomic publication, safe CLI errors and installed package resources.
Real subprocess tests cover no-output and partial-frame stalls, timeout/cancel
with actual SIGKILL/reaping, startup timeout followed by repeated shutdown
cancellation, held cleanup capacity, cache expiry, parent death,
finite IPC, child stderr/traceback canaries, and DB/DNS/store/body/decrypt stalls.
Synthetic ready workers are test-only; there is no runtime profile override.

API tests cover fixed error templates, hostile exception formatting, nested
exceptions, failing log sinks before/after headers, default-format correlation,
missing requested records versus corrupt internal evidence, private validation
paths/inputs, generated correlation, ambiguous
mutation outcomes, auth-before-probe and readiness-before-upload, as well as
cancellation/revocation/logout during storage failure. Legacy guard tests retain
their actual refusal cases with safe public responses.

Local verification may borrow a read-only interpreter from another contributor's
owned environment while importing this checkout explicitly; it is not proof of a
fresh locked install. Hosted frozen dependency checks, real PostgreSQL cases and
the isolated installed-wheel smoke provide the integration evidence. No paid
provider calls, customer data, production installation, cloud store or HA/DR
rehearsal is included in this slice.
