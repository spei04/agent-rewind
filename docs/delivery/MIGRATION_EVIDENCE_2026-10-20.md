# Explicit migration acceptance — 2026-10-20

[PR #35](https://github.com/spei04/agent-rewind/pull/35) merged at
`385e5ecf59b7b7bcf131969b915bac60275fec47`. The exact reviewed/tested source is
`6cf49a815f46eb72514a06d219c5d6a991fb59cf`.

## Executed checks

[Hosted run 39348158044](https://github.com/spei04/agent-rewind/actions/runs/39348158044)
passed the required CI gate. Python 3.11 and 3.12 each passed 656 tests; the three
Docker skips in each core job were covered by three passing real gVisor tests in
the separate isolation job. Forty-two PostgreSQL cases executed against the
pinned PostgreSQL 16 service. Security/locked dependency audit, formatting, lint,
type checking, contract validation and installed-distribution checks passed.
Pull-request candidate delivery was skipped and uploaded zero artifacts.

The PostgreSQL tests exercise explicit fresh installation and historical adoption,
exact retry/conflict behavior, frozen catalog validation, transactional interruption
and process termination, writer-role/session exclusion, future/multiple heads,
non-owner runtime refusal, namespace protection before dialect probing, repeated
connections, autocommit refusal and bounded strict source parsing. SQLite tests
also cover backup restoration and structural drift, including unindexed collation.
Installed-package smoke loads the shipped migration profiles and actually runs
installation/retry/status outside the checkout.

B independently accepted the exact catalog, transaction and privilege boundary.
A accepted the DB-only CLI, input bounds, redaction and packaging at `e7a6b20`;
those scoped files were unchanged by the final reconnect correction. B reviewed
that correction, including a bounded 10000-invocation check and its real PostgreSQL
reconnect regression. This is internal engineering review, not an external audit.

## Preserved identities and contract correction

The independent frozen fixture remains 14 rows and 18 encrypted objects, with
245000 microUSD held. Migration does not decrypt/rewrite objects, change event
identities or release reservations. The reviewed C04 implementation erratum binds
an explicit retired legacy writer-role inventory to adoption intent, addressing
the actual legacy application-superuser setup. Every listed writer must be disabled
and all other database sessions drained. Unrelated administrative authority stays
trusted; the tool cannot prove an operator supplied an honest inventory or backup.

| Frozen file | SHA-256 |
| --- | --- |
| `agent_rewind/migrations/profiles/postgresql16.json` | `10f7b64b8341096a69571da4449076bdffb05cb26dc2407b30cdf710bb8c5008` |
| `agent_rewind/migrations/profiles/sqlite.json` | `d7c949e9bae68f631665a18e450f697bdc5aac8a2357708dfeff6b1be523bb52` |
| `tests/fixtures/legacy_v0/baseline.sql` | `62cd159230e9f81336779658b706c161149c24115f6e0f54bdfe4f32c7bdb19a` |
| `tests/fixtures/legacy_v0/manifest.json` | `cd19df65a34668918118f878f5233abff081a54f1f6ebb2512e2e46cd3795b17` |

The PostgreSQL profile was independently compared with the explicit DDL before
acceptance. Its initial capture run intentionally failed until the reviewed
literal profile was committed; that capture is not used as passing evidence.
See [migration guide](../MIGRATIONS.md) for the separate capture identities.

## Acceptance limits and next work

AR-005-B is Verified for explicit metadata preparation only. Successful commands
return `prepared` and `customer_ready=false`. API/worker runtime guards are not yet
implemented by this slice; customer deployment or admission is not authorized by
migration success. AR-005-C adds that enforcement and a real PostgreSQL backup/
restore rehearsal. Existing PostgreSQL transaction rollback tests do not prove a
backup can be restored. AR-007-A owns ownership/backfill; full M1 runtime acceptance
and all production/data/spending gates remain open.

The private owner-readable release-record index retains this source identity,
observed checks and limitations outside disposable checkouts. No private data,
credentials, full log archive or generated distribution was added to this record.
No paid resources, provider calls or partner data were used for this slice.
