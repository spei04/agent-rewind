# F4 validation status

**R4 is closed and rejected. The subsequent source repair passes lint and formatting; product qualification remains incomplete.** The original candidate `e02ad6be0a44d282085e534212ce237377d6be64` and failed evidence are retained. Its one approved attempt is consumed.

## R4 observed outcome

| Stage | Actual result |
| --- | --- |
| R3 unused future-access retirement | Original writer and independent reader exited 0. Historical reservations and evidence were preserved. |
| R4 preflight and admission reader | Both exited 0 on the original clock. |
| Metadata controls | 16 passed; retained JUnit and terminal records agree. |
| Python 3.11 focused tests | 320 passed, with zero failures, errors or skips. |
| Python 3.12 | Ruff lint exited 1 after 0.423 seconds. Pytest did not run. |
| Installed package | Skipped after the Python 3.12 failure. |
| Independent review | REJECTED; delivered 105.135 seconds after review start. |
| Failure closeout | Closeout, root-exit retention, terminal writer and terminal reader exited 0. Product acceptance remained false. |

Ruff reported **50 findings**: 10 E501, 2 I001, 2 F401, 23 SIM117, 1 UP012, 11 B023 and 1 B007. These affected 15 test/helper files and two long lines in the production cancellation module. The outer caller's 124 was its generic unsuccessful code; the retained remote result was exit 1. This was not a timeout.

The run began November 7, 2026 at **00:36:29.921 PST**, with deadline **01:06:29.921 PST**. Closeout began at 00:41:26.132. The final terminal reader returned at 00:42:16.428; external completion was observed at **00:42:26.438**, within the 120-second closeout deadline of 00:43:26.132. All 14 attempted caller operations closed; the independent ownership checks found no remaining declared processes or groups.

The two terminal callers' original outputs and external observations were also preserved at **00:43:43.862 PST**, 17.730 seconds after the closeout deadline. This was later supplementary preservation. It does not retroactively make that write timely or change the original completion time.

Approval bound preparation completion to Unix **1794039906.157** (November 7, 00:25:06.157 PST), with conservative preparation **26,037 seconds**, carried interval **27,018**, actual prior **40,832** and campaign ceiling **42,632**. These overlapping elapsed intervals are not added together or treated as CPU usage. Source work after the failed run does not reset the consumed attempt or create reusable time.

## Reviewed source repair

[Repair commit `e706f1e`](https://github.com/spei04/agent-rewind/commit/e706f1e1a60dd8efd6dc8d8a5f6773208d2b86c7) is a separate repair based on the unchanged original candidate. Exactly **31 files** changed: 16 lint-repair files plus 15 additional files requiring formatting.

- The original 16-file lint repair binds per-iteration callback values, preserves the loop value later reported in evidence, preserves context-manager entry and cleanup order, removes unused imports and wraps long lines.
- The required formatting check identified 29 files, including 14 of the original 16. Independent before/after AST comparison confirmed formatting preserved behavior.
- Two formatted string literals still exceeded the lint length limit. Adjacent literal splits preserved their exact values and ASTs.

No rule, check scope, assertion or dependency was weakened. Both existing checkouts were reused; the original feature branch and the primary checkout's 13 untracked files remain intact.

| Source verification | Result |
| --- | --- |
| Initial lint / format check | Lint passed; format reported 29 files requiring formatting. Original results retained. |
| Post-format lint / format check | Two E501 findings; format passed for all 569 files. Original results retained. |
| Final lint | `ruff check --no-cache .`: exit 0, 0.356 seconds. |
| Final formatting | `ruff format --check --no-cache .`: exit 0, 0.368 seconds; all 569 files already formatted. |
| Independent review | Original lint changes reviewed for behavior; all final 31 AST digests matched the reviewed snapshots. |
| Product tests on repaired commit | Not run. Python 3.12 and installed-package qualification remain open. |

The final five-context-line diff is **267,477 bytes**, SHA-256 `f5516070d3a9df76bf8b3fca3f688c1418c4a92d7054d1bfbd046aba10ce8c13`. Its exact source and AST manifest is `1790fd957d3cfa7995cc5c2bc76cfc8359e1f9e730a359690e015dc37d287f17`. The committed source reproduces the final diff; a redundant copy was not stored. Publication preserves all six commits after the public ancestor `439fca5`, with exact object hashes and existing author metadata. All 113 published objects matched their original hashes; the branch readback matched `e706f1e`, and GitHub reported zero workflow runs. Source moved through memory only, with no local checkout, cloud authentication change or additional cloud Git writes.

The final combined source-check and commit receipt is 1,957 compressed bytes (4 KiB allocated), SHA-256 `3415fb27c905c5f7d1228c090f85d16b1417c7f067297f98f8a9a29f3c7ca05d`. It decodes to 5,099 bytes, SHA-256 `ab9d31a7c4ec0d1bf1720e7298b474831443bf821e20a466fb31d7efbf261b76`. Both final checks had true exit 0, complete streams and reaped processes. The independent source-review record is 3,600 compressed bytes, SHA-256 `f2f5af117b00c78a0ca7a45d22b5e0434a138ed1ccec481cbc0319f1fff6fa2b`. Its original save/readback exited 0; it accepts the source repair only. The four repair result/review records use exactly 16 KiB of the existing metadata allowance.

## Resources and remaining gates

A post-T0 reconciliation verified 32 named references and the scoped published registries. Two distinct Intake allowances raised the known shared requirement to **38,699,559,168 bytes**; free space at entry was **38,992,666,624 bytes**. Completed records without release authority remained counted. This describes known commitments at admission, not a freeze on other projects.

The final source audit at **01:11:24.084 PST** passed. Source growth was **180,224 bytes** (Git 159,744; working files 8,192; retained original patch 12,288). The preparation pool uses **1,949,696 / 2,097,152 bytes**: source 1,486,848 / 1,572,864, metadata 262,144 / 262,144, correction 196,608 / 196,608, and directory allocation 4,096. Metadata and correction partitions are full and cannot be borrowed from. The complete source category uses **158,097,408 bytes**, or **159,145,984** with the existing publication margin, below **268,435,456**.

Free space was **38,971,203,584 bytes**. The audit verified a clean repair checkout, the unchanged original candidate, all 13 primary untracked files, pinned dependencies and exactly two required worktrees. Neither checkout is disposable at this transition. No files were removed or disk savings claimed.

The R4 grant remains retained. Future scratch access totals **8 GiB**; cumulative scratch reservation lineage is **20 GiB**, not measured usage. Cumulative normal/failure ceilings remain **512 / 1,792 MiB**. No historical charge, unknown usage or remaining time was released.

The repair used the remaining source and metadata partitions within the existing 2 MiB preparation pool. Git import and index-refresh phases were reviewed separately, including their temporary allocations. No new checkout, dependency installation, product run, hosted CI, paid provider call, infrastructure or production change occurred.

Conservatively retaining the additional 196,608 bytes of actual source and receipt growth, the known floor is **38,699,755,776 bytes**. At that observation, an additional 64 MiB normal + 256 MiB failure reservation would require **39,035,300,096 free bytes**, leaving a **64,096,512-byte shortfall**. Retaining all existing scratch holds and adding another 4 GiB would require **43,330,267,392 bytes**, a **4,359,063,808-byte shortfall**. The lower scenario is conditional on separately authorized and verified scratch retirement; neither scenario admits a run. These are planning comparisons, not new allocations.

Before another product attempt:

1. Freeze the repair commit and regenerate affected candidate manifests and qualification inputs.
2. Independently review the complete successor package and current evidence/accounting.
3. Reconcile all current commitments and establish sufficient capacity. Any retirement must have separate authority and verified readback; a completed attempt alone does not release a hold.
4. Obtain a new bounded execution decision. The original R4 allowance supplies no retry.
5. Execute the complete qualification inventory on the repaired candidate: 16 metadata controls, 320 focused cases on each Python version, and installed-package smoke, with original exits, evidence joins, cleanup and timely external completion.

F4 qualification would still leave native-path, database/dialect, concurrency, protected integration and production gates open. F5, worker P2, AR-012-B and an admitted release profile remain prerequisites for the live failure-to-branch workflow. The compatibility release keeps customer/auth routes unavailable and worker claims disabled. Static dashboard evidence remains labeled as such.

The research cap remains **$200 total**, including earlier charges. The **$36.567974** historical reservation is distinct from unknown settled spend and unknown available balance. No paid experiment was run here.

## Evidence index

Private evidence remains owner-readable and outside disposable checkouts. The following identifiers support the outcome; private contents and session credentials are not published.

| Record | SHA-256 |
| --- | --- |
| Actual R4 approval | `b9e6c9b3b2a48370b84131aa53c261adec2cea7a470a0066a45ed47e354126c1` |
| Terminal manifest | `3ebeb27c9a1c6e15cde7b76fdbdf7961e67786bf249a2f9430d20e1311189731` |
| Terminal readback | `c46d75c48a3f780bdd7b91c4d1872b6f517a8aca51a59bc8292dc7cfc8d9e561` |
| Closeout index | `56736129560ff47b549617024a3794b93436a2fb024a262e13cdcd3878da4d33` |
| Root-exit record | `88640eb6a06d17318400dc3f4f46aa9211f667d5462d99a6d8d23bf44550bccb` |
| Original Ruff output | `0153fdc903c721cd2f4d804cd866b3a8b5517c934e9a4c727461d1582a904378` |
| Later supplementary observations | `c0b3c16c19d69675f55faf0162401e0ceeb194afee247e43b169a9a5361080c7` |

The supplementary archive is 47,065 bytes and decodes to 125,749 bytes with SHA-256 `71702f0693cd8b79707a84d73d97307e8473132fb61b31ce7db42d1604a3e5da`. Independent review checked the exact originals, completion and ownership observations against the retained chain.

Historical preparation, earlier failures and accounting remain in immutable records:

- [R4 source package, original preparation witness and prior R3 history](https://github.com/spei04/agent-rewind/blob/397e2c15d41c2056241085594c75e0db71aa864a/docs/F4_VALIDATION_PLAN.md).
- [C4 source checks and earlier engineering assignments](https://github.com/spei04/agent-rewind/blob/64cbc794bbe7f37f92f231ead942e435d733441b/docs/F4_VALIDATION_PLAN.md).
- [Original R3 proposal](https://github.com/spei04/agent-rewind/blob/b2bd4765c40fbfc13cac14878404c775fcc36c34/docs/F4_VALIDATION_PLAN.md).

[Assignments](ASSIGNMENTS.md) · [Roadmap](PLAN.md) · [Execution backlog](EXECUTION_BACKLOG.md#ar-010-b)
