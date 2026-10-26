---
id: "aoe2war.wolochain.mainnet-settlement-runbook"
title: "WoloChain Mainnet Settlement Runbook"
type: "runbook"
status: "active"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "runtime-evidence"
authority: "mainnet-settlement-operations"
reviewed_at: "2026-10-26"
review_interval_days: 14
sensitivity: "restricted"
---

# WoloChain Mainnet Settlement Runbook

## October 26, 2026 — aggregate replay evidence and actual P1 frontier

[Held PR107](https://github.com/Emaren/wolochain/pull/107) extends qualified
PR106 without merging or replacing any existing branch. Failing-before CI
[40295076807](https://github.com/Emaren/wolochain/actions/runs/40295076807)
proved two false confirmations: a fingerprint-matching grouped cache could
report confirmed without leaf records, and a challenge cache could override an
invalid funding plan. Aggregate readers also accepted case aliases and linked
files. These are source defects, separate from unavailable chain evidence.

The repair validates **every** existing aggregate before final replay or
retry, using read-only original leaf requests, existing physical-effect owners,
exact role/recipient/memo/uwolo identity and conserved micro/display totals.
It binds cached challenge funding/participants to the already-collected plan
and validates nested run, transfer and top-up evidence. Missing ownership,
contradiction or uncertain prior execution returns
`AGGREGATE_REPLAY_UNVERIFIABLE`, with nested confirmation claims removed and
`retryable=false`. No guard calls an executor, queries a chain or changes
historical journal bytes. It does not prove payment absence. Existing proven
pre-signing refusal rules remain distinct from ambiguous broadcast history.

Journal reads share folded-JSON rejection, regular-file/inode checks,
nonblocking/no-follow acquisition and read bounds:64KiB leaves,16MiB aggregates
(the valid250-payout contract can exceed64KiB). Aggregate validation has a
30-second cancellation budget. Historical offline proof reports additionally
bind exact anchor, expected-intent and portable-proof bytes plus declared
historical time. The as-of field is not authenticated provenance. Nil/canceled
contexts refuse verification; successful historical verification still exits3,
NONAUTHORIZING, with all financial/retry/custody authorization false.

**Fresh nonmutating runtime:** the linked single
[canonical checklist](settlement-contracts/financial-release-checklist.json)
retains five BLOCKED controls and solvency UNKNOWN. Root SSH on October26
observed checkout78c25985 clean, settlement1012/1010 with original040126a2
hash and unmodified78c VCS; consensus1009 with4b77f622 hash, intentionally
modifiedd3bd6241 VCS, and local wolo-1 height2649282→2649283. Six financial
timer families remain active. This is continuity, not independent finality or
producer isolation. Old source→settlement byte parity is already reproduced;
do not repeat it or use it as a permit. Original install custody, consensus
provenance and compatibility of actual historical obligations remain distinct.

There is one human owner. No source result appoints a nonexistent reviewer
council or manufactures signatures. Existing old multi-role controllers/permits
are not silently converted to single-owner authority. Before any operation,
qualify a genuine single-owner policy preserving chain proofs, one-use leases,
fences, state ownership, full-size backup/recovery and separate final approval.
No key creation or policy activation is part of PR107.

**Shortest safe operator action:** obtain/provision the missing authentically
sourced checkpoint and validator/header archive outside the existing RPC trust
domain, the immutable accepted100WOLO intent and authentic historical as-of.
Then run the already existing offline command documented in
[the proof contract](settlement-contracts/README.md#october-21-2026--historical-accepted-100-wolo-proof-offline-and-non-authorizing).
Never guess those files/time to make verification pass. Later current-bank
proofs must bind all distinct accounts to one committed SDK height and complete
nonoverlapping liabilities. Preserve300WOLO #889, #8477, #947 and shared
#2712/#2760 ordinal uncertainty; never retry the historical100WOLO transfer.
No maintenance, binary switch, chain restart, state restore or funded canary
is authorized by this source work.

## October 25, 2026 — held legacy replay qualification, no live upgrade

The held descendant of [PR #104](https://github.com/Emaren/wolochain/pull/104)
adds source-only corrections at `c2fd512`, `8be2d93` and
`cb24cb2546392c981da8dcac18a04d1df4241330`. No production process, financial
record, signer, keyring or consensus executable was accessed or changed by this
qualification. Issue #5 remains HOLD; source tests do not reconcile a payment.

**Proven defects and repair:** a request lock previously expired by timestamp.
With one caller paused in preflight, a second caller could delete its old lock
before either caller persisted a prebroadcast marker. Deterministic payout and
escrow tests observed two synthetic CLI sends for one request. Request, grouped
run and challenge locks now remain exclusively owned regardless of age. An
abandoned lock is interruption evidence, not authority to retry. The service
continues to report the existing `*_IN_PROGRESS` refusal while that lock exists;
its `retryable` field permits another status attempt, never lock stealing.

Stored success also bypassed the current confirmation contract. Replay now
checks the journal fingerprint and exact chain/request/role/recipient/amount,
rejects contradictory execution/confirmation states, and requires a canonical
hash and zero execution code for success. Historical `confirmed` records with
no exact-confirmation marker become `LEGACY_CONFIRMATION_UNVERIFIED`, with no
signing or file rewrite. A newer confirmed replay also needs its existing
durable receipt owner and conflict-free request history; a missing/conflicting
receipt produces `TX_RECEIPT_UNAVAILABLE`. Replay never creates a receipt to
retroactively bless old history. Invalid journal structure is `STATE_FILE_INVALID`.
The reader bounds request records to 64 KiB, requires a regular file and rejects
duplicate JSON members, including decoder case aliases. Every held original
record remains byte-for-byte unchanged. Valid accepted broadcasts stay distinct
from confirmed payments and are never rebroadcast.

The #104 role-specific, proven pre-signing failure allowlist is retained.
Regression tests show one successful synthetic execution from a genuine old
balance refusal and no second signing call after restart/replay. Ambiguous old
RPC errors, lost signer replies and prebroadcast holds remain nonretryable.
The retained confirmation registry owns one physical message/coin effect per
request only within its configured state tree; it does not establish global
financial solvency, independently authenticated consensus or original history.

**Artifact boundary:** the named `legacy-replay` profile reuses
`build-settlement-artifact.sh` and `settlement-artifact.py`, pinned to immutable
implementation `cb24cb2546392c981da8dcac18a04d1df4241330`, Go 1.24.6,
Linux/amd64, CGO off and the existing exact build recipe. Its separate no-deploy
workflow verifies two fresh-cache builds, clean embedded VCS metadata and a
machine-readable manifest. All financial/production authority fields remain
false. Historical `bdbce253`, old live bytes and their release controllers are
unchanged; this candidate cannot be substituted into a historical permit.

**Recovery boundary:** never remove a stale lock, discard a request/receipt or
restore an old state tree to make a retry possible. Prove the original writer
has stopped, independently reconcile the original chain effect and obtain
separate owner authorization for any recovery. A code-only rollback to legacy
semantics requires continued producer fencing; legacy code cannot enforce these
newer receipt/uncertainty guards. The two settlement services keep independent
roles/state, and consensus remains separately executable. No new source result
resolves the accepted 100 WOLO, claim #889, refund #8477, shared claim ordinals,
external liabilities, bank solvency, historical finality or recovery evidence.

## October 18, 18:12 UTC — financial release HOLD and six-control handoff

The **[financial release checklist](settlement-contracts/financial-release-checklist.json)**
is the single current machine-readable six-control index. Its keys are the exact
`ATTESTED` controls consumed by the existing cutover controller. Dated receipts
remain immutable history; they are not competing readiness checklists. The index
is observational and never a permit, continuous monitor, chain trust root or
financial certification. Refresh it after every maintenance or financial change.

The app owner independently deployed website `78d2a3329096c25b9429a3536f08c33d1d9dc96f`;
its read-only status is CERTIFIED. Website delivery no longer depends on rushing
this Wolo release. No app source was edited. The historical `bdbce253` settlement
artifact remains distinct from the unactivated newer custody/escrow source.

| Existing control | Status | Evidence and exact missing action |
| --- | --- | --- |
| HD/DE/external producers isolated | **BLOCKED** | 19 discovered app units, 11 active candidates; HD has independent staking/faucet configuration. Cron, two user managers and one container also exist. Named owners must classify every HTTP, queued, timer, cron, user and external signer path, then explicitly approve coordinated fencing. Do not blanket-stop all candidates. |
| In-flight/accepted outcomes reconciled | **BLOCKED** | Primary still has one recorded accepted 100 WOLO request. Configured-node bytes/hash agree and report code 0 at height 1078913; this is not independently authenticated finality or authorized reconciliation. Independently bind bank effects to every obligation; never retry an unknown. |
| Claim #889 preserved/reviewed | **BLOCKED** | A fresh READ ONLY / REPEATABLE READ query confirms the same 300 WOLO pending claim, attempted 2026-07-04T22:23:41.342Z, no stored hash. Preserve its liability and history. No exhausted historical cache search was repeated. Finance must supply independently reviewed paid/unpaid or continuing-hold disposition. |
| Fresh quiesced verified backup | **BLOCKED** | Existing `--inspect` checks passed at 18:12:48 UTC, but created no backup and proved no quiescence. Approve the coordinated fence/drain first; then capture fresh restricted state/config/unit backups, verify checksums and exclusive state ownership. Never restore old payout histories as binary rollback. |
| Reviewed code-only rollback rehearsed | **BLOCKED** | Existing offline controller tests cover uncertainty, permit expiry/revocation, partial rollout and bounded recovery; they are not a live rehearsal. Named operator must approve and witness the exact two-service rehearsal/recovery with producers fenced and consensus untouched. |
| Bank solvency independently checked | **UNKNOWN** | Three distinct configured-node accounts observed; common escrow counted once. HD records 947 pending claims totaling 993,189 WOLO. Complete DE/external, escrow, unmaterialized obligations and fee liabilities remain unknown. Independently reconcile their overlap, ownership and fees before asserting solvency. |

At 18:16:25 UTC, the sensor read 1,566 leaf requests and 793 runs: primary
920 (914 recorded confirmed, 5 failed, 1 accepted) and founder 646 (609 recorded
confirmed, 37 failed). It deduplicated 886 run references. The single run-only
1,323,000 WOLO requested child has a recorded prebroadcast funds/reserve refusal
(`attempted=false`, no hash), confirmed by the bounded 18:18:02 UTC follow-up.
This is not independently proved payment absence or a certified debt. No finite
execution-principal bound was emitted because evidence gaps remain. The primary
count increased from the earlier 919; production was not quiesced.

At 18:12 UTC, health and bank REST observations within the **same node trust
domain** agreed on primary payout **396,507 WOLO**, founder payout
**356,787.241424 WOLO**, and shared escrow **825,469.5 WOLO**. Configured payout
floors are 250,000 and 1,000 WOLO respectively; escrow floor is 100 WOLO; each
reported fee headroom is 10 WOLO. These values are configuration/local-node
observations, not authenticated balances, fee estimates, available collateral
or proof that any obligation is funded. The three HD pending claim groups are
207,979 WOLO founder bonuses, 110,524 WOLO founder wins, and 674,686 WOLO winner
bounties. Claim #889 is included in founder wins. **Do not add these claims to
journal amounts**: their obligations may overlap. No finite global liability
upper bound is established; missing records never mean zero.

### Bounded journal accounting sensor

`scripts/settlement-state-evidence.py` recovers preserved unfinished work and
adds exact decimal integer accounting by input lane, signer role and recorded
status. Run the reviewed source against only the two governed roots:

```sh
sudo python3 scripts/settlement-state-evidence.py \
  --state-root /mnt/HC_Volume_105319120/wolochain-mainnet/settlement-state \
  --state-root /mnt/HC_Volume_105319120/wolochain-mainnet/founder-rewards-settlement-state
```

Exit **3** means bounded evidence collected with the HOLD retained; **2** means
unavailable/unsafe/inconsistent evidence. Neither exit allows release or retry.
The sensor never accesses the network, changes financial state, deletes locks,
prints wallet addresses, memos, request IDs or raw errors. It verifies stored
normalized request fingerprints, bounds bytes/entries/depth, rejects symlinks
and ambiguous records, checks receipt reuse, and separates aggregate runs from
leaf obligations. Run children do not become extra liabilities when identical
leaf records already account for them; missing/conflicting child evidence
remains explicit. Every recorded payment status is an assertion requiring chain
reconciliation. Observed principal uncertainty is bounded only for the records
actually read; fees and global liabilities remain unknown. A stable read is
**not an atomic or exclusive snapshot**, producer drain or proof of absence.
When invoked through stdin without remote files, the reader's own source hash
is unavailable; the collecting operator must retain the exact input-byte hash
separately. Never infer provenance from a self-declared field.

### Complete escrow-100 identity snapshots and read-only deltas (HELD)

The existing `--focus-escrow-100` mode deliberately returns **at most sixteen
recently filesystem-modified confirmed** 100-WOLO escrow records plus accepted
records. That subset cannot certify which eight local confirmations appeared
between October 18 and 20; their earlier full request identities were not
captured. Never infer that filesystem mtime is a payment timestamp.

The optional `--full-escrow-100-manifest` mode reuses the same strict, bounded,
read-only two-root journal reader. It emits a complete sorted identity manifest
**only for observed exact 100000000-uwolo escrow accepted/confirmed requests**,
up to the existing 2,500-match fail-closed limit. Each row contains only lane
index, status, SHA-256 of the private request ID and SHA-256 of original record
bytes. It does not emit raw request IDs, addresses, signers or memos. This mode
is opt-in because full manifests are larger than the normal sixteen-row focus.

Use the *same root order* (primary then founder), separately verify source Git
identity and capture the exact producer state conditions. No live file, service,
wallet, payout or state mutation is required; output is saved on the operator's
Mac, **not written on the VPS**. Example after checkout/fetching the reviewed
held source, using a privately verified exact commit:

```sh
umask 077
cd ~/projects/WoloChain-wolo-1
REV='REPLACE_WITH_REVIEWED_FULL_GIT_SHA'
set -o pipefail
git show "${REV}:scripts/settlement-state-evidence.py" |
  ssh root@hel1 'python3 - --full-escrow-100-manifest \
    --state-root /mnt/HC_Volume_105319120/wolochain-mainnet/settlement-state \
    --state-root /mnt/HC_Volume_105319120/wolochain-mainnet/founder-rewards-settlement-state' \
  > ~/escrow100-observation-A.private.json
echo "COLLECT_EXIT=$?"
```

A **3** is a valid but financially HELD observed snapshot; **2** is invalid.
Retain the source Git SHA, exact source-byte SHA-256, capture time, user,
root-order attestation and JSON-file SHA-256 separately. An stdin invocation
cannot self-attest its reader source. Repeat for observation B in the identical
order. The comparison is local/read-only:

```sh
python3 scripts/compare_settlement_escrow_100_manifests.py \
  --before ~/escrow100-observation-A.private.json \
  --after ~/escrow100-observation-B.private.json
echo "COMPARE_EXIT=$?"
```

The comparator strictly rejects incomplete/malformed/unordered/duplicate
manifests and differing root counts, and returns hashed added, removed and
changed request identities. **Exit 3 means a valid financial HOLD comparison**;
exit 2 means invalid evidence. The operator must still independently authenticate
the original captures and the root-lane mapping; neither file has a trusted
signature merely by containing SHA-256 values. Even a changed `accepted` to
`confirmed` journal status remains an unauthenticated local claim, not chain
finality or payment proof. Missing prior identities cannot be reconstructed.
Never use these deltas to approve retry, spend, release, solvency or promotion.

### All-user cron, periodic cron and at-queue financial-writer census (HELD)

**Operator host preflight:** this collector must run inside the Linux VPS
SSH session, not in the Mac terminal used to launch SSH. Check `hostname`
and `uname -s` on the remote shell before collecting financial evidence.
On macOS, the reviewed collector now returns exit 2 with
`WRONG_HOST_LINUX_REQUIRED` **without executing any host inventory commands**.
That is not evidence about the VPS. Do not upload a Mac-generated `STOP`
report as a VPS financial inventory. The host identity itself must still be
verified by the operator; simply seeing `Linux` does not prove connection
to the correct VPS.


Before *any* approved producer fence/drain, the root-side read-only
`scripts/settlement_auxiliary_producer_surfaces.py --inspect` collector now
enumerates accessible crontab files in both conventional spool directories,
not only the historically named `tony` and `root` entries. It additionally
counts `/etc/crontab`, `/etc/anacrontab`, `/etc/cron.d` entries, files in
`/etc/cron.hourly`, `cron.daily`, `cron.weekly`, `cron.monthly`, and
`cron.yearly`, and an `atq` pending-job count (where accessible).
It records filenames only for the original fixed crontab sources and never
prints cron command bodies, secret environment assignments, periodic script
contents or `atq` job details. Any discovered cron job, even one whose command
does not mention money, still requires operator classification.

The scan is **not a complete inventory guarantee**: directory absence,
an inaccessible `atq`, unexpected nested/spool paths, unknown runtime
scheduler implementations, containers, user managers, HTTP-triggered writes,
external signers, or unobserved direct bank transfers remain unresolved. Unsafe
spool/scheduled directory symlinks and unbounded listings fail closed.
The parent `/var/spool/cron` and child `crontabs` are separately enumerated,
so the child folder is not counted as a job or silently ignored.

**Observed Ubuntu 24.04 VPS layout (October 20, 2026):** the correct-host
read-only `lstat` census on `ubuntu-4gb-hel1-11` showed exactly the
`atjobs` and `atspool` directories under `/var/spool/cron`, with no
unexpected entry types in the other seven scheduler roots. Their existence
triggered the old `UNSAFE_SCHEDULER_ENTRY` despite being ordinary `at(1)`
queue storage, **not additional user crontab files**. The corrected scanner
accepts these two names **only as actual non-symlink directories in the
conventional parent cron spool**. It still rejects files/symlinks under those
names, unexpected nested directories and hard-linked files, and it never
opens or prints `at` job bodies. Its source-controlled fields
`atSpoolDirectoriesObserved`, `atSpoolDirectoriesMissingOrUnverified`,
`atSpoolJobPayloadsInspected:false`, and
`atSpoolFinancialWriterCapabilityExcluded:false` preserve an explicit
unresolved queue-signer coverage boundary. `atq` is still a **separate
read-only count**, with an unavailable queue recorded as `UNOBSERVED`.
These facts do not certify producer isolation, source ownership, custody or
solvency; a new PINNED **live VPS** collection is required.


**Diagnostic STOP semantics:** the collector intentionally makes no
financial-release claim even on a complete root-host observation. When a
critical enumeration fails, it emits only the allowlisted
`failureStage` (`CRON`, `USER_SYSTEMD`, `DOCKER`, or `PODMAN`) and a
fixed `failureCode` taken from the audited collector source; it never
prints raw OSError, command output, cron contents, secrets or exception
parameters. Unknown/unclassified errors are redacted, not silently treated
as empty sources. A `STOP` report remains code 2 and financially **HELD**.
The operator should capture a redacted report, investigate the named
failure stage read-only, and never work around the STOP by deleting files,
stopping services, changing permissions, skipping a section or setting
an activation flag.

Run the **reviewed, exact-version source** with no sudo shell expansion,
financial flags, cron modifications or systemctl operations. Exit code **3**
means metadata observed and FINANCIAL HOLD; code **2** means STOP / unsafe
observation. Do not interpret a zero job count, absent directory or missing
`atq` binary as producer isolation. The six release controls and global
solvency remain BLOCKED/UNKNOWN until separately witnessed, complete
operator/finance evidence exists.

### Shortest protected operator sequence

1. Independently classify the remaining producer/signing paths and designate HD,
   DE, finance and recovery owners. Obtain **explicit owner approval for a
   bounded financial maintenance window**, including the specific fences,
   quiesced snapshots and two-service recovery rehearsal. That approval has not
   been granted by this engineering work. The website stays independent.
2. Under that approval, fence every classified financial producer and direct
   signer; verify queues, accepted/uncertain requests and exclusive state
   ownership. Preserve #889. Collect independently authenticated exact bank
   effects and complete liabilities/fees. An unresolved payout is held, not
   retried. If any control remains UNKNOWN/BLOCKED, do not promote.
3. Capture fresh private checksummed snapshots with the existing snapshot tool
   after quiescence, witness the reviewed binary-only rollback/recovery scope,
   and update the same checklist with independently reviewed receipts. No
   consensus restart, database rewind or restoration of financial state.
4. Only after all six controls have real independent evidence, obtain the
   owner's separate **paired code-only cutover approval**. Issue the existing
   short-lived root:root 0600 permit bound to exact `bdbce253` and binary
   `44d8aed5550d1b33635c734c1a359d0cb69e854093ef8c9a8a3da4f99d416ede`.
   Use the existing commands below; never derive its witnessed controls from
   CI or this checklist alone:

   ```sh
   sudo python3 scripts/settlement-bdbce253-code-cutover.py --mode inspect
   sudo python3 scripts/settlement-bdbce253-code-cutover.py --mode promote \
     --permit /root/aoe2war-release/approved-two-service-permit.json
   ```

5. Keep producers fenced. Verify both actual runtime PIDs/executable/VCS/health,
   unchanged node PID/hash and chain progress. Failure permits only bounded
   old-binary recovery for both settlement lanes; preserve all request, run,
   receipt and financial state. A separately requested rollback or interrupted
   recovery needs fresh authority. Keep CRITICAL recovery failures fenced.
6. After actual paired runtime verification, separately approve source
   alignment using the fail-fast exact-object/ancestry procedure below. Privately
   preserve/review the ignored build-output directory; do not erase it to pass
   a cleanliness check. Producer resumption and Satchel custody activation are
   separate decisions. Satchel remains **UNAVAILABLE / NONCREDITING**.

### Source ancestry and release independence

PR #38 (`68cdc1ae`) integrates the existing ops and Satchel ancestry; #39
(`7611946c`) builds on #38, #40 (`6ea89143`) on #39, and #41 (`9fb53d95`)
on #40. Each remains an unchanged CI-green draft. This evidence/accounting leaf
stacks on #41; no existing branch or valuable dirty worktree was discarded.
Review/merge these source dependencies in order, or review an explicitly scoped
backport separately. Neither merging them nor installing their operator scripts
changes the pinned historical settlement binary target. Do not substitute the
newer Satchel backend artifact for `bdbce253`, and do not deploy the full branch
as a shortcut. Source tests and artifact receipts do not certify live custody.

## October 18, 14:24 UTC — earlier release frontier (superseded)

PRs #38–40 are unchanged CI-green draft source; none is a production release.
The new controller correction binds the original operator permit and reloads it
immediately before each forward side effect and after final verification.
It opens the permit without following symlinks, checks the opened root-private
descriptor and stable path, bounds the read below 8KiB, rejects duplicate fields
and evaluates expiry after acquisition and parsing finish.
Expiry, revocation or changed approval before the first mutation causes zero
changes. After an approved mutation starts, failure allows only the fixed
old-code cleanup: two settlement stops, at most two owned override removals,
one reload and two settlement starts. This cleanup may finish after permit
expiry so a half-switched pair is not abandoned. It never resumes financial
producers, restores request/run history, renews rollout authority or changes
consensus. A separately requested rollback/recovery requires fresh authority.
The original five-minute issuance and ten-minute maximum permit bounds remain;
every revalidation must satisfy both. Cleanup failure is CRITICAL and requires
human inspection under the continuing financial fence.

The dated [release-frontier receipt](settlement-contracts/protected-release-frontier-20261018.json)
separates source proof, actual observations and missing independent controls:

| Requirement | Established evidence | Remaining authority/evidence |
| --- | --- | --- |
| Exact legacy candidate | Staged `bdbce253` binary hash `44d8aed5…`; unchanged old lanes use `040126a2…` | Fresh protected preflight and independently approved paired installation. |
| Consensus separation/progress | PID 1009 and hash `4b77f622…` unchanged; local `wolo-1` RPC advanced 2515247 → 2515266 | This is local operational progress, not independently authenticated financial finality. Never restart the node. |
| Accepted/uncertain obligations | Primary: 913 recorded confirmed, 5 failed, 1 accepted; founder: 609 confirmed, 37 failed | Exclusive current reconciliation against independent chain evidence and app liabilities; recorded statuses never prove payment or zero liability. No retry. |
| Founder #889 | Existing unresolved hold retained; exhausted historical investigation not repeated | App/finance owner must provide independently reviewed claim-to-payment evidence and preserved liability disposition. No inferred paid/unpaid result. |
| HD/DE signer/producer isolation | Eleven discovered app unit candidates in a noncertifying inventory | Independent owners must fence all HTTP, workers, cron, external signers and queued/in-flight work. A list of processes is not a fence. |
| Backups and recovery | Existing root-private snapshot/paired code-only controls and offline fault tests | Fresh quiesced checksummed snapshots, exclusive state ownership, actual operator recovery/watchdog authority and bounded window. An October 14 snapshot is not current certification. |
| Reserves/financial authority | No new balance, solvency or custody certification issued | Independently reconcile bank reserves, all liabilities and fee headroom; issue the existing exact root-private permit only after all six witnessed controls. |
| Source transition | Checkout still `78c25985`, with one preserved ignored build-output directory | Privately review/preserve ignored content; real two-lane runtime cutover must precede separately approved exact source fast-forward. |

The next operator action is to assemble one dated, independently witnessed
packet for the six existing `witnessedControls`, bound to the exact candidate,
both services, current state/snapshot identities and maintenance window. Do not
issue a permit from these observations or CI results. Once that packet passes,
the owner can approve the existing paired code-only cutover and its recovery
scope; only then may the reviewed `promote --permit` procedure below execute.
Financial producers remain fenced through runtime verification and the separate
source transition. No automatic caller or retry may resolve an unknown payment.

The earlier website-only route was implemented and independently released by
the app owner. Current website delivery is separate from this financial HOLD;
see the current six-control packet above. Preserve these earlier observations
as historical evidence rather than interpreting them as current release status.

## October 18 — machine-readable source/runtime authority gate

The website's `vps-source-drift` hold must not be cleared by changing a Git SHA
while 8092/8093 still execute the legacy code. Source authority and running
executable authority are independently inspected by the existing controller:

```sh
sudo python3 scripts/settlement-bdbce253-code-cutover.py --mode source-authority
```

This mode is strictly read-only, accepts no financial permit, and returns one
`aoe2war.wolo.settlement-source-authority.v1` JSON receipt. Exit 2 means source
or runtime is blocked/unverifiable; exit 0 means only
`SOURCE_RUNTIME_ALIGNED_FINANCIAL_HOLD`. All financial/custody/release authority
flags remain false. It verifies both active legacy lanes, exact executable
hashes and units, canonical health, unchanged consensus identity, and stable
Git observations before/after runtime inspection, final settlement generation/health
and stable PID checks, and a final UTC observation timestamp. The receipt names
both settlement PIDs and the consensus PID; it proves a bounded observation,
not continuing authority. Git repository/index/config environment overlays are
cleared and the canonical checkout top-level is verified. Hidden tracked index flags,
ignored/untracked source, dirty files, output/resource refusal and source drift
cannot pass. It never prints source filenames or secret configuration.

| Actual runtime | Actual checkout | Result and next protected action |
| --- | --- | --- |
| old `78c25985` | old `78c25985` | Both `code_cutover_required` and `source_transition_required`; separately approved guarded two-service cutover comes first. |
| old `78c25985` | new `bdbce253` | Still blocked; a checkout-only change is not a deployment and cannot clear the website gate. |
| both new `bdbce253` | old `78c25985` | Runtime prerequisite met; source transition remains separately protected and required. |
| both new `bdbce253` | clean exact `bdbce253` | Source/runtime aligned; existing financial, custody, #889 and app release gates remain held. |

The reviewed source is exactly
`bdbce253c524d6faac14f61cd129ac5072287c3f` and its staged binary is exactly
`44d8aed5550d1b33635c734c1a359d0cb69e854093ef8c9a8a3da4f99d416ede`.
The new Satchel backend has a different source/artifact authority and must not
replace either identity. In particular, aligned `bdbce253` is only the exact
issue #5 legacy authority target: later integrated escrow-evidence source
`7a830e8` and custody source `99f32de` need their own exact release review and
artifacts. This gate does not certify their deployment or the complete hardened
backend. All financial producers remain fenced. No live checkout or process is changed by this source
fix. A successful web-only build or KingdomIndex merge cannot supply the
missing live execution proof.

After the **separately approved** existing paired cutover has succeeded, retain
its exact two-lane/PID/health receipt and unchanged consensus receipt. Only then
may the operator, under explicit source-transition authorization and the same
fenced maintenance window, advance the clean checkout. The operator must first
prove no service launches consensus or financial execution from that source
working tree. Never reset, force, clean, discard work, run build/install, or
invoke old release/rollback scripts to clear this hold. The intended source
transition is narrowly:

```sh
(
set -eu
umask 077
: "${REVIEWED_CONTROLLER:?retained exact reviewed operator-tool path}"
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_CONFIG GIT_CONFIG_COUNT \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_SYSTEM GIT_CONFIG_GLOBAL GIT_CONFIG_NOSYSTEM \
  GIT_CEILING_DIRECTORIES GIT_DISCOVERY_ACROSS_FILESYSTEM
export GIT_OPTIONAL_LOCKS=0 GIT_NO_REPLACE_OBJECTS=1
wgit() {
  command git --no-optional-locks --no-replace-objects \
    -c core.fsmonitor=false -c core.hooksPath=/dev/null \
    -C /var/www/WoloChain-wolo-1 "$@"
}
SOURCE_RECEIPT="$(mktemp)"
trap 'rm -f -- "$SOURCE_RECEIPT"' EXIT
require_source_transition() {
  GATE_STATUS=0
  sudo python3 -I "$REVIEWED_CONTROLLER" --mode source-authority > "$SOURCE_RECEIPT" || GATE_STATUS=$?
  test "$GATE_STATUS" -eq 2
  python3 -I - "$SOURCE_RECEIPT" <<'PY'
import json, sys
from datetime import datetime, timezone
with open(sys.argv[1], "rb") as stream:
    data = stream.read(65537)
assert len(data) <= 65536
r = json.loads(data)
expected = {
    "schema": "aoe2war.wolo.settlement-source-authority.v1",
    "mode": "READ_ONLY", "status": "BLOCKED",
    "expected_revision": "bdbce253c524d6faac14f61cd129ac5072287c3f",
    "checkout_revision": "78c25985420ee41a6678c42fab8ea8d6c3b1b519",
    "checkout_clean": True, "tracked_index_visible": True,
    "ignored_entries": 0, "untracked_entries": 0, "tracked_change_entries": 0,
    "live_code_state": "new",
    "live_settlement_revision": "bdbce253c524d6faac14f61cd129ac5072287c3f",
    "live_settlement_sha256": "44d8aed5550d1b33635c734c1a359d0cb69e854093ef8c9a8a3da4f99d416ede",
    "code_cutover_required": False, "source_transition_required": True,
    "source_transition_runtime_prerequisite_met": True,
    "source_runtime_aligned": False, "consensus_unchanged": True,
    "release_authorized": False, "financial_drain_certified": False,
    "custody_authorized": False, "claim_889_resolved": False,
    "production_mutated": False,
    "blockers": ["SOURCE_TRANSITION_REQUIRED_AFTER_VERIFIED_CODE_CUTOVER"],
}
assert all(type(r.get(k)) is type(v) and r[k] == v for k, v in expected.items())
pids = r["settlement_pids"]
assert set(pids) == {"wolochain-mainnet-settlement.service", "wolochain-founder-rewards-settlement.service"}
assert all(type(pid) is int and pid > 0 for pid in [*pids.values(), r["consensus_pid"]])
observed = datetime.fromisoformat(r["observed_at_utc"].replace("Z", "+00:00"))
assert observed.utcoffset().total_seconds() == 0
assert 0 <= (datetime.now(timezone.utc) - observed).total_seconds() <= 30
PY
  test "$(wgit symbolic-ref --quiet --short HEAD)" = wolo-1-mainnet-prep
  test "$(wgit rev-parse HEAD)" = 78c25985420ee41a6678c42fab8ea8d6c3b1b519
  test -z "$(wgit status --porcelain=v1 --untracked-files=all --ignored=matching)"
}
# Requires explicit source-transition approval and the existing exclusive,
# fenced maintenance window. A checkout-only operation cannot satisfy this.
require_source_transition
case "$(wgit remote get-url origin)" in
  https://github.com/Emaren/wolochain.git|git@github.com:Emaren/wolochain.git) ;;
  *) exit 2 ;;
esac
wgit fetch --no-tags --no-write-fetch-head origin bdbce253c524d6faac14f61cd129ac5072287c3f
test "$(wgit rev-parse 'bdbce253c524d6faac14f61cd129ac5072287c3f^{commit}')" = bdbce253c524d6faac14f61cd129ac5072287c3f
wgit merge-base --is-ancestor 78c25985420ee41a6678c42fab8ea8d6c3b1b519 bdbce253c524d6faac14f61cd129ac5072287c3f
require_source_transition
wgit merge --ff-only --no-edit bdbce253c524d6faac14f61cd129ac5072287c3f
# The old source predates this mode; use the retained reviewed tooling path.
sudo python3 -I "$REVIEWED_CONTROLLER" --mode source-authority
)
```

The exact-object fetch and fast-forward above require their own authorization;
none was executed during this engineering work. The procedure never pulls an
unreviewed branch, detaches the protected branch or executes new source. Retain both
old/new source identities and all current request/run histories for recovery.
If code rollback becomes necessary, source alignment is blocked again until its
separate controlled transition is reviewed; financial producers stay fenced.
Only a fresh aligned receipt supports rerunning the app engineer's existing
web-only Finish dry-run. It grants no financial activation or Finish bypass.


## October 17, 2026 — authenticated bridge and fresh release HOLD

The [financial bridge](war-satchel-financial-bridge.md),
[composed artifact](war-satchel-exact-source-artifact.md) and
[controlled release gates](war-satchel-controlled-release.md) supersede older
source-readiness observations for this candidate. Fresh read-only runtime
inspection still finds settlement source `78c25985`, separate consensus
identity, no 8094 listener and accepted legacy records. No drain, complete
liability reconciliation, independent vault control or live canary is proved.
Keep HD financial hold and C2 UNAVAILABLE. Never rebroadcast an uncertain
request or treat a checkout/artifact change as a changed running process.


## October 17, 2026 — dedicated Satchel execution source, no activation

The [Satchel execution/operator contract](war-satchel-mainnet-execution.md)
describes the new restricted 8094 service, immutable one-shot operation journal,
independent withdrawal approval, exact HD wire adapters, owner-attributed return
requirements and staged provisioning/canary procedure. It creates no wallet,
key, funded deposit, app ledger credit or real transfer. C2 remains
`UNAVAILABLE` and C3 remains `NONCREDITING` until independently verified custody,
complete accounting and authenticated chain trust are genuinely established.

8094 must use a dedicated keyring, OS authority, private credential and current
journal; existing payout, betting escrow, founder, treasury, staking and validator
keys are excluded. UNKNOWN attempts remain fenced across restart and block new
operations; neither HTTP success nor a bearer token proves payment or approval.
No producer may blindly retry, delete holds or restore an older journal.

The current base is PR #24 merge
`c1210dda37b725a5b141ad63361048d4b37731c2`. It retired the obsolete
`3ea79363` mutating rollback/rescue paths; do not resurrect them or reuse unrelated
draft release branches. Existing 8092/8093 source/runtime mismatch, founder #889
UNKNOWN, fresh ingress/drain and protected recovery holds remain unchanged.
The dedicated consensus executable must remain untouched and running.

Installation, new custody provisioning, paired settlement maintenance and one
small real-chain canary each require their separately reviewed operator
authorization. Current source-readiness evidence is not a deployment controller
or authorization. Preserve the latest request/run/receipt/prebroadcast state
through code-only recovery; keep financial producers quiesced if reverting to
legacy grouped/receipt semantics. No live operation or repeated founder
investigation was performed by this source work.

## October 17, 2026 — source hardening and protected release remain separate

The [legacy settlement hardening handoff](legacy-settlement-hardening.md)
records the source-only candidate and precise remaining operator evidence.
No new VPS observation was made. The `78c25985` live-source observations and
`bdbce253` reviewed candidate below are dated history; neither is asserted as
current production truth or the binary containing this new source work.
The existing no-deploy candidate workflow still builds exactly `bdbce253`.
A new reviewed immutable artifact must identify the final approved source SHA.

The old provenance, preflight and snapshot helpers remain pinned to historical
runtime/artifact identities. Their source checks cannot certify a modern
cutover, and changing their pins alone cannot establish financial drain or
recovery safety. The preflight now requires the founder bind to be exactly `127.0.0.1:8093`;
previously it accepted other distinct loopback ports. Six offline release-policy
tests pass, including the unchanged refusal of `--rollback` and `--rescue`
before live checks. The retired procedures below
are retained only as engineering history; their imperative wording is not an
instruction to execute them.

A future release needs independent HD+DE financial-ingress isolation and active
job drain, current chain/request-state reconciliation including the unresolved
founder #889 hold, both private state trees preserved, and a separately reviewed
`QUIESCED_RECOVERY_ONLY` controller/watchdog. Financial producers remain fenced
through recovery until named approval. No source test or artifact authorizes
resuming them. Preserve 8092/8093 signer/state separation, the dedicated consensus
executable and all current liabilities. Satchel PR #25 remains separate and
unmerged; C2 custody remains `UNAVAILABLE`.

## October 16, 2026 — current exact candidate build, NOT a cutover

The current governed financial Go implementation is
`bdbce253c524d6faac14f61cd129ac5072287c3f`.
The earlier non-deploying `3ea79363` candidate workflow has now been
retired from the current release line; its old binary source could not represent
the present implementation because Go settlement confirmation, durable payment markers,
replay ownership, and request-state behavior have substantively changed.
The old controller and its binary digests are historical and **must not
be used for promotion**.

The new `.github/workflows/settlement-current-implementation-candidate.yml`
is a separate **source-pinned, no-deploy** verification lane. It checks
out exactly `bdbce253`, runs financial/race tests, builds a versioned
Linux amd64 binary outside the source tree, verifies embedded Go VCS
revision and unmodified flag, and records SHA-256 and an explicit
`production_authorized=false` statement. This artifact cannot certify
current on-chain payer liability, signer ingress/drain, founder claim
#889, a two-settlement rollback rehearsal, or the consensus node's
unchanged identity. It performs no live SSH, key access, financial send,
deployment, or node restart.

Source-bound Documentation OS may advance its **repository-wide
implementation baseline** to the commit adding the workflow, because
the workflow itself is executable source. That Git ancestry seal is
not a claim that the Go binary is built from the documentation commit:
the candidate binary must still attest `bdbce253` exactly. Runtime
settlement VCS, live VPS checkout, source baseline, and CI artifact are
**four separately reported authorities**. Do not greenwash their drift
or use the new artifact in the old `3ea79363` controller.

Release remains held on independent complete proof of founder #889;
signed HD+DE payment-ingress isolation, zero inflight/authorized drain,
governed snapshots and a rehearsed settlement-only rescue watchdog;
then named authorization, protected two-lane activation, unchanged
consensus PID/binary SHA and observed exact runtime receipt. Until
then, no `finish` workaround, manual Git checkout fast-forward,
payout retry or generic shared-node binary replacement is allowed.

## October 16, 2026 — crash-durable prebroadcast request holds (C4b)

**Observed defect:** the payout and escrow sender paths historically executed
`broadcastPayout` / `broadcastEscrowTransfer` **before** saving the individual
request record. A process crash, out-of-memory kill or filesystem fault after
broadcast but before the write could erase the accepted transfer's request
identity. Replaying the same request ID could then attempt a second transfer.

**Source-only mitigation:** after successful independent signer/reserve
preflight, both paths now fsync a minimal owner-bound, non-retryable
`BROADCAST_OUTCOME_UNRECORDED` request marker **before calling the signer**.
The marker records the exact normalized request, intended role, signer,
recipient and amount, but **no invented transaction hash or payment status**.
Its status is `unverifiable` and `retryable=false`. The file and parent
directory must both sync successfully; otherwise no broadcast begins.

Once the signer/broadcast step returns, the existing writer replaces the
marker with actual evidence. If the CLI returns **without a hash**, even when
its legacy error classifier calls the outcome retryable, that result becomes
`unverifiable` / `BROADCAST_OUTCOME_UNRECORDED` / `retryable=false` before
storage. Otherwise a transient RPC error after broadcasting could overwrite
the durable hold with a retryable result, defeating the fix. A known hash
retains the distinct pending/confirmed/failed evidence classification but
cannot be rebroadcast under the same request ID. Grouped settlement runs containing a no-hash
unverifiable payout now explicitly return `status=unverifiable`,
`retryable=false` and replay the same held result. Previously their
aggregate status could be empty because only refused/rejected counts
were classified; that is a control-plane correctness defect. Historical
test expectations allowing a second CLI attempt are superseded by this
stricter financial safety contract. If the process dies or the final write fails,
the preceding durable marker remains or may reappear after a filesystem
crash, so an idempotent replay refuses re-broadcasting. Prebroadcast
marker existence **never proves a payment was sent**; it can also
represent a crash occurring before the signer was invoked.

**Remaining limits:** a marker with no final hash requires independent
operator reconciliation from actual chain history, signer sequence and
request memo. There is no automatic resolution, no clearing legacy
ambiguous attempts (including founder #889), and no independent node
consensus authentication or global cross-service request store. Do not
delete the marker or stale lock to retry. This is NOT a Satchel vault,
ledger credit, staking payout authorization or production deployment.
The live 8092/8093 services are unchanged until a separately approved
protected release.


## October 16, 2026 — exact settlement confirmation source contract (C4)

[C4's source contract](exact-settlement-confirmation-c4.md) hardens transaction
lookup and payout confirmation from merged PR #20 at
`87f9c0f9e4c9ad92520d72ac0df5fae9718c923a`. An HTTP-success response, missing
transaction fields, or broadcast acceptance cannot establish payment. A payout
can become `confirmed` only after the configured sources report the requested
hash at a positive committed height with valid successful execution; actual
hash-bound transaction bytes decode to the exact authorized signer, recipient,
one `uwolo` amount and normalized memo; and a unique bank effect is reserved for
the durable request in this service's state directory. Legitimate omitted
Cosmos proto3 zero execution codes remain valid inside a complete response.

`status=accepted` records broadcast acceptance, including when
`confirmation_status=pending` or `unverifiable`; it does **not** mean paid.
`OK=true` on that response retains its historical acceptance meaning. Confirmed
payment requires `status=confirmed` and `confirmation_status=confirmed` under
the exact proof contract. A committed failed execution is `failed`. Unavailable,
malformed, conflicting or incomplete evidence stays unverifiable, without
automatically retrying or rebroadcasting the payment. Do not delete request
records, incomplete `*.json.tmp` records, confirmation receipts or stale receipt
locks to make a retry possible; uncertain local ownership refuses confirmation.

Versioned confirmation receipts own `wolo-1` + transaction hash + strict body
effect `0` (the sole `MsgSend` and sole coin) for one request fingerprint and
signer within the configured `StateDir`. The displayed log-first event index
can vary when logs omit fees; it is not the receipt ownership index.
Pre-existing same-hash records owned by a different request conservatively block
confirmation. This is a local reuse guard; it establishes no cross-service
ledger uniqueness, independent consensus authentication or Satchel credit.
8092/8093 retain their distinct payout signer and state authorities. The shared
betting escrow is not Satchel collateral.

This is a **source-only** correction. No production service was deployed,
restarted, reconfigured or freshly certified, and no key, transfer, database or
claim retry was performed. Existing financial drain/release gates, the separate
consensus executable, all liabilities, and founder claim #889 remain unchanged.
Previously persisted outcomes are not rewritten or independently re-proved;
the historical broadcast-before-request-write crash gap and recovery work remain
separate prerequisites. Satchel custody remains `UNAVAILABLE` and C3 evidence
remains `NONCREDITING`. The dated runtime observations below retain their
original scope and dates.

## October 16, 2026 — canonical payout amount and int64 conversion boundary

Source-level audit found `normalizeAmountUWolo(amount_uwolo, amount_wolo)`
could multiply a positive `int64` whole-WOLO input by 1,000,000 without
an overflow guard. A large malformed request could wrap its requested
base units before hashing/settlement validation. The micro-WOLO text path
also used unsigned parsing, accepted leading-zero decimal aliases and
could pass `uint64` values that cannot be represented by the signed
integer format and downstream `formatDisplayAmount` path.

The corrected validator accepts only canonical decimal-positive
`int64` micro-unit text, rejects padded zeros, plus signs, zero,
negative values, oversized values and mixed whole/micro input—even if
the whole-WOLO field is negative. The whole-WOLO path now checks
`amount_wolo <= MaxInt64 / 1_000_000` before multiplication. Focused
tests cover the exact representable maximum, the first overflowing
value, maximal signed whole input, padded-zero input, uint64-only micro
values, and mixed representations.

This is **source-only hardening** of request normalization, not an
assertion that such a request occurred in production. It changes no
existing payout records, account balance, signer, vault, or consensus
executable and does not authorize a settlement cutover. Existing Wolo
liabilities, historical founder claim #889, private service separation
and the dedicated Satchel vault/consensus trust holds remain unchanged.
Any deployment still requires independent protected financial proof,
review of previously persisted request shapes and release-controller
approval.


## Original request-record forensics for founder bonus #15 (October 15, 2026)

Two independently observed mainnet read-only settlement preflights succeeded:
original shared settlement executable, independently staged candidate,
separate unchanged consensus executable, both active 8092/8093 services,
root-private immutable snapshot integrity, healthy loopback ports and no
observed locks. These do **not** authorize protected service cutover.

App claim #889 remains `pending` with a recorded attempted payout, no
confirmed transaction hash. Three cached same-amount `wolo-1` transfers were
verified independently against public canonical transaction REST at heights
324458, 322609 and 1468795: all successful transfers, but none carries the
deterministic Founder bonus #15 payout memo. The app cache is incomplete;
absence of an exact-memo candidate in that cache **does not prove nonpayment**.

`scripts/settlement-founder15-state-readonly.py --inspect` adds a more direct
on-VPS evidence check against the two existing **root-private live**
settlement request stores, without copying private files into chat. It
reads only bounded `aoe2-founder-15-*.json` records, verifies stored request
identity, rejects symlinks/oversize/malformed files, and prints only a
hashed request fingerprint, lane, sanitized status, boolean memo/failure
flags and any publicly checkable transaction hash. It never prints private
addresses, raw memo, amounts, signer credentials, file paths or errors.
No records found is an inconclusive result—not evidence of zero payouts.
Record presence is not proof of a canonical transaction unless independently
reconciled with correct recipient, signer, chain success and complete history.
It always returns exit **3**, reports **releaseAuthorized=false** and
**retryAuthorized=false**, and never changes a file, environment, process,
wallet, validator or database. Exit 2 means evidence unavailable or unsafe.

Operator use (read only, from a source-verified clean checkout):
`sudo python3 scripts/settlement-founder15-state-readonly.py --inspect`.
Do not activate either financial service, replay claim #889, rewind stored
request state, or make `aoe2war finish` green by faking the VPS source SHA.
The current Wolo settlement binary and repository authorities must be
reconciled only after independent full finance drain, signer boundaries and
live recovery rehearsal are certified.

## October 15 read-only signer coverage correction

The 2026-10-15 DE process inventory found active web and API services,
`WOLO_BET_PAYOUT_ADDRESS` on web and database authorities on both.
It found no sampled process keys for the **first** signing allowlist, and
reported NOT_CERTIFIED (exit 3). That first allowlist omitted the live DE
source's `WOLO_STAKING_WALLET_MNEMONIC` and fallback/keyring settings.
Absence from that historical report is **not** evidence of no signer.

The corrected inventory now includes staking-wallet mnemonic, payout mnemonic
fallback, keyring disable/selector, faucet sender, chain and RPC selectors,
and staking wallet address. It still prints **only allowlisted key names**,
not values, URLs, wallet addresses, keyring homes, or tokens; it still
returns exit 3 and grants no service-stop or financial authority.
DE code includes public staking/unstake and faucet claims plus admin
scheduled-settlement and treasury-execute paths; runtime authorization and
signer state require a separate reviewed active-process and DB drain proof.
Never treat an empty startup environment as evidence that separately loaded
dotenv or other signer material is absent.

## DE sister-site payout authority — read-only classification (October 14, 2026)

The two WoloChain settlement services operate on a VPS which also hosts
`aoe2dewarwagers-web.service` and `aoe2dewarwagers-api.service`. Those
separate active services cannot be assumed inert merely because HD payment
timers and web/API are paused. The DE web code has independently callable
WOLO claim and staking operations, including a possible CLI keyring signer
that would **not** require a mnemonic to appear in its process environment.

`scripts/settlement-parallel-de-authority-inventory.py` is a strictly
read-only, root-scoped inventory of both DE process environments, bounded
local app dotenv **key names** and DE service/timer names. It reports the
*presence* of allowlisted signing, CLI keyring, remote settlement and
database configuration names, **never their values**, paths to wallet homes,
addresses, wallet seeds, DB URLs or money amounts. It does not open keyring
files, send HTTP requests, modify services or print raw unit/environment
contents. Missing or empty configuration keys are not proof that a payout
cannot occur: app-loaded environment, keyring fallback, scheduled jobs,
other signers and live request ingress must also be considered.

The result **always ends** with
`NOT_CERTIFIED_FOR_SHARED_WOLO_SETTLEMENT_DOWNTIME` and exit code 3
(or exit 2 when metadata cannot be safely inspected). It is never a
promotion/maintenance authorization, and it does not remove the DE gate in
the draft two-service watchdog controller. The next engineering decision
must either prove independent immutable signer isolation *and* no shared
settlement use, or prepare a separately reviewed DE ingress freeze and
recovery manifest. Any such future change must protect DE users and avoid
touching DE services without explicit approval. The existing historical
founder claim #889 also independently blocks financial drain clearance.


## Emergency code-only two-service rollback (October 14, 2026 — HISTORICAL, RETIRED)

**October 16 supersession (PR #24, SOURCE ONLY):** The original
`scripts/settlement-two-service-code-rollback.sh` now has a read-only
`--inspect` mode only. Its `--rollback` and `--rescue` modes exit **2**
with `OBSOLETE_LEGACY_RECOVERY` before any root/process or service operation.
The formerly documented automatic restart of web/API and timer producers
was deleted. The former `3ea79363` candidate-build CI job was also retired.
The historical procedure below is **not currently executable** and must
not be used as a cutover, watchdog, rollback, or approval playbook.

For the modern `bdbce253` implementation, build a separately reviewed
two-settlement-only rollback/watchdog with **QUIESCED_RECOVERY_ONLY**
semantics: keep all financial signers, requests and producers fenced until
independent canonical chain/request-state reconciliation and named approval.
Never infer payout safety merely from restoring an executable hash.
This retirement changes GitHub source only; it does not change production.



`scripts/settlement-two-service-code-rollback.sh` is a separately audited
**rollback-only** implementation. It does NOT activate the candidate and cannot
be used as evidence of a completed production promotion.

- `--inspect` verifies the pinned original binary, dedicated running
  consensus executable, root-private backup receipts, original settlement unit
  identities and, if they exist, the **exact** versioned override bytes.
  Inspection does not write or restart anything.
- `--rollback` switches the two settlement units back to the original,
  **unchanged** `/usr/local/bin/wolochaind-mainnet` executable. It removes
  only its exactly matching `50-aoe2war-settlement-3ea79363.conf` override
  from **each settlement unit**; any unexpected file/symlink aborts. It does
  not stop, restart or reload the consensus unit. It never copies historical
  payout records or old environment files into the live state paths.
- `--rescue` first performs that same code-only recovery and checks health
  on loopback 8092 and 8093. **Only after settlement recovery passes**, it
  can resume the allowlisted web/API services and timers recorded in a
  root-owned 0600 maintenance manifest at
  `/run/aoe2war-wolo-two-service-cutover/restore-units`. No manifest means
  no automatic producer restart. Unknown service names fail closed.

This rescue helper must be present in a pinned, root-owned path before
any separate activation controller stops application ingress. Run it under
an independent transient systemd timer so it survives an interrupted SSH
session. The helper **does not arm a watchdog itself**; do not mistake its
presence for active timeout recovery. A cutover remains BLOCKED until the
operator can prove the watchdog is armed and can safely resume the right
site services, and the application financial-drain checks are complete.

**Irreversibility boundary:** A historic online state copy is useful for
disaster evidence, but restoring it after new chain payouts can cause duplicate
transfers. Revert code only, preserving the current live primary and founder
request/run state. Should code rollback itself fail, keep payout ingress
paused and escalate rather than trying the generic shared-binary restore
(that can restart the validator).

## Production two-lane release preflight and rollback limits (October 14, 2026)

The operator's live backup receipt for
`20261014T091735Z-two-settlement-node-untouched` was rechecked **after**
creation. Both config/unit checksum manifests and both state-tree checksum
manifests passed. The two actual systemd unit files each have exactly
`ExecStart=/usr/local/bin/wolochaind-mainnet settlement serve`, with no
settlement drop-ins; only the **consensus node** has its own preserved binary
override. The mounted WoloChain volume is `rw,relatime,discard` (no
`noexec` flag was reported). The backup covers two distinct root:root 0600
environment files and independent state directories.

Run `scripts/settlement-dual-service-release-preflight.sh` in an
independently verified version-pinned copy as root, in a child shell. This
tool does **not** write to the VPS. It fails closed unless all of these
remain true:

- Original and staged executable hashes, clean legacy VPS checkout and all
  three active runtime executable fingerprints match their established pins.
- Both settlement units still have their exact original executable and
  `settlement serve` invocation, with **no unreviewed drop-ins**.
- Private October 14 backup is root:root 0700, does not have an
  `INCOMPLETE` marker, and passes checksum validation for both unit/env
  copies and both historical state copies.
- The two 0600 env files contain distinct loopback bind addresses. The
  primary is required to use `127.0.0.1:8092`; live unauthenticated health
  probes of both settlement services must succeed. State directories must
  have no observed in-flight `*.lock` files.

Source comparison from the old VPS revision
`78c25985420ee41a6678c42fab8ea8d6c3b1b519` to the candidate source
`3ea79363695dd93be5f0a5e8a5121cf6e31d27b8` is 11 ancestry commits
and implementation changes limited to
`cmd/wolochaind/cmd/settlement.go` plus tests. Other changed files are
documentation. This is nevertheless **not proof of a drained payout
pipeline** or that old and new binaries have identical runtime behavior.

A separate reviewed switch/rollback procedure is still mandatory. Intended
mechanics: install **two service-specific** `ExecStart` overrides that
point to the already verified versioned candidate, coordinate both
settlement-only service stops/starts, retain existing live request/run state,
and verify current binary hashes and HTTP health on both lanes. An error
must trigger a rollback to the *untouched* original shared binary for both
settlement services, retaining **current** live request state. Do not
change the source checkout baseline, the node binary or the node unit as
part of that action. Avoid `systemctl restart` on the node. Require a
quiet/pending-settlement drain confirmation from the app and the chain,
and a protected release window, before ever allowing an activation action.

Runbook statuses: **backup verified and candidate staged**; source-side
preflight under review; **no live release authorized or performed**.

## Two-service private snapshot and state continuity (October 14, 2026)

The live primary and founder-rewards settlement units use **different**
root:root mode-600 environment files:
`/etc/wolochain-mainnet-settlement.env` and
`/etc/wolochain-founder-rewards-settlement.env`. Their persistent state
roots are **also separate**:
`/mnt/HC_Volume_105319120/wolochain-mainnet/settlement-state` and
`/mnt/HC_Volume_105319120/wolochain-mainnet/founder-rewards-settlement-state`.
Both services currently execute the exact older
`/usr/local/bin/wolochaind-mainnet` binary; the consensus node executes a
different dedicated override, `wolochaind-mainnet-node-prewartrophy`.

`scripts/settlement-dual-service-snapshot.sh` provides two constrained modes
for this explicitly pinned candidate and existing live binaries:

- `sudo bash scripts/settlement-dual-service-snapshot.sh --inspect` checks
  the clean VPS source checkout, three active processes and their SHA-256
  fingerprints, installed and staged binary hashes, private env file modes,
  both state directories, lock files and mounted-volume free space, without
  writing a file.
- `sudo bash scripts/settlement-dual-service-snapshot.sh --snapshot` repeats
  the checks and creates a **new root-owned 0700 directory** inside
  `wolochain-mainnet/settlement-backups`. The backup contains the old
  settlement executable, both 0600 env files, both settlement unit files,
  effective node unit evidence, and a separate copy plus sorted SHA-256
  file manifest for each state tree. It fails closed if live files drift
  during the copy, if a lock file is present, or if the expected running
  executables have changed. Failed backups retain an `INCOMPLETE` marker
  and must never be restored. No systemd mutations occur.
- A passing snapshot captures an observed state interval, **not a logically
  atomic transaction across simultaneous on-chain payouts**. Operator
  maintenance must still reconcile in-flight and pending operations.

**High-stakes rollback constraint:** restoring a historical settlement request
or run record after new chain payouts can re-enable a previously consumed
request. The normal rollback must switch **both settlement services** back
to the original, untouched shared executable (by removing only their
versioned `ExecStart` override drop-ins), while preserving authoritative
*current* live request/run state and both live env files. Historical state
snapshots are disaster-recovery evidence only; their restore requires a
separate transaction-by-transaction chain reconciliation. Never use
`scripts/restore-live-settlement.sh` in its default `shared-binary` mode:
it restarts the consensus node. Its existing `settlement-only` path does not
coordinate the founder service. Neither generic restore path is the approved
two-service rollback.

The live observer on October 14 verified ~5.0 GiB free on root, ~56 GiB on
the mounted volume, primary state ~7 MiB, and protected staging candidate
SHA-256 `af18e18bd32ef5763d3e414a37dd7886fe4065b640bb5a89ae742ee860fb9b87`.
The snapshot script makes no claim of a post-deployment result and does not
authorize signing, settlement execution, balance movement, or consensus changes.

## Settlement-only verifier candidate — source-controlled proof lane (October 14, 2026)

**Source identity has been verified, but the security patch has not yet been deployed.**
At `2026-10-14T03:32:39Z`, the active mainnet settlement and founder-rewards
settlement processes were both running a SHA-256
`040126a2884946caf1651a50b7d8115c5a6fb2d5aa94fcbbe150694602d451a5`
binary with embedded `vcs.revision=78c25985420ee41a6678c42fab8ea8d6c3b1b519`
and `vcs.modified=false`. The VPS checkout is clean at this exact source.

The *consensus node*, separately, runs
`/usr/local/bin/wolochaind-mainnet-node-prewartrophy` with SHA-256
`4b77f622191db7550cb87cafb8f1886a0aadebee3eb6565f9f90036f809e61d3`,
embedded source `d3bd62414a047a492a3814b7d3baa2717d64db2e`,
and `vcs.modified=true`. The node executable is **intentionally distinct**.
Never replace, restart, or repoint it as part of this settlement-only campaign.

Newer implementation `3ea79363695dd93be5f0a5e8a5121cf6e31d27b8`
([settlement PR #4](https://github.com/Emaren/wolochain/pull/4)) strengthens
escrow verification of failed transactions, wrong-denomination transfers, and
unique matched transfer ordinal. WoloChain Go CI passed, but its existing generic
release workflow is a conditional prerelease workflow and **is not proof of a
built production artifact or live installation**. The settlement-only candidate
workflow addresses that missing evidence by compiling the *exact reviewed source*
from a pinned, clean checkout and retaining the Linux/amd64 binary with a
SHA-256 and embedded Go VCS manifest. Artifacts are UNDEPLOYED by construction.
They do not grant permission to fund the War Satchel or enable auto betting.

### Operator gates (explicit human-controlled deployment)

1. Confirm the `Settlement-only candidate (NO DEPLOY)` GitHub Actions run is
   successful and download `wolo-settlement-3ea79363-linux-amd64-UNDEPLOYED`.
   Verify artifact's `SHA256SUMS`, `SOURCE.txt`, `go-build-metadata.txt` and
   exact `3ea79363` VCS inside the binary. Never assume the conditional generic
   release workflow produced this artifact.
2. Transfer the binary only into **non-live staging storage** with enough free
   space. Run the separately reviewed, read-only
   `scripts/settlement-only-provenance.sh --candidate PATH --sha256 DIGEST`
   as a privileged inspection. This command checks both live settlement
   processes, node SHA, clean old VPS Git checkout, and the staged candidate.
   It does not copy, install, restart, or update anything.
3. Independently prove real-time active settlement health, pending requests,
   signer reserve floors, escrow liabilities, rollback restore points, staging
   storage capacity and consistency. Do not print secret environment files,
   auth headers, keyring material, or wallet credentials. Require positive and
   negative escrow verification, duplicate event, old manual ticket, and
   founder reward compatibility tests. A healthy HTTP endpoint alone is not
   semantic parity.
4. Approve a specific maintenance window with rollback operator and receipt.
   The two settlement units **share** the same live binary, so treat both as one
   coordinated deployment while keeping the consensus node PID, binary,
   chain home and block state untouched. Choose an independently verified
   versioned settlement executable path / unit override and safe rollback;
   never use the general `shared-binary` recovery path that restarts the node.
5. After settlement-only promotion, prove new running PID executable hashes and
   Go VCS `3ea79363`, unchanged running node SHA, chain `wolo-1` progress,
   `8092` and protected founder listener health, auth rejection, historical
   idempotency and exact transfer semantics. On regression, use the separately
   rehearsed **settlement-only** rollback, not a consensus restart.
6. Only after execution evidence is captured, advance the VPS source checkout
   to the approved SHA and reconcile central documentation. Then retry the
   web-only `aoe2war finish --dry-run` without bypassing its P1 gate.

**Authority separation:** Git source, binary provenance, live chain runtime,
settlement API, central documentation baseline and Satchel custody certification
are six independent identities. A release that changes one does not implicitly
certify the others. See [WoloChain ops #5](https://github.com/Emaren/wolochain/issues/5)
and [Kingdom Shepherd #554](https://github.com/Emaren/app-prodn/issues/554).



## Review Renewal — 2026-10-07 UTC

A bounded read-only review against the October 6 VPS context reconfirmed the
live `wolo-1` operating boundary. The scheduled mainnet health check completed
successfully at height `2313501` with `catching_up=False`; the mainnet node and
mainnet settlement service were active, and recent settlement validation /
execution evidence remained bound to chain `wolo-1`.

This documentation renewal performs no chain, validator, keyring, wallet,
transfer, relayer, liquidity, settlement, or Wolo mutation. It does not
silently re-prove total supply, every wallet balance, validator voting power,
IBC/Osmosis state, pool state, or other dated historical claims; those remain
bound to their explicitly dated evidence below.

This runbook is for `wolo-1` mainnet settlement only. Do not reuse the old testnet service, state, signer keys, or port.

## Review Renewal — 2026-09-22 UTC

A read-only VPS context capture at `2026-09-22T04:35:41Z` reconfirmed the
operational settlement boundary. The node and mainnet settlement services were
active, `127.0.0.1:8092` was listening, and the mainnet health check reported
`wolo-1` healthy with `catching_up=false`.

Settlement logs from September 21–22 contain successful validation and confirmed
execution events for both configured signer roles. A payout-signed staking
Treasury run used
`wolo1zfa9ssu2gpgqg7yzvhmjt4w66mza07qr2a4rwu`; escrow-signed betting and
staking runs used
`wolo1zygwt232ymc4h2g52yvkntffhmd5alx2kglw7p`. The separate protected
`8093` listener was also present, but it is not the `8092` settlement API.

The capture did not expose the secret-bearing environment file, perform fresh
bank-balance queries, or re-evaluate reserve floors. The September 9 reserve
policy and point-in-time signer balances below therefore remain dated evidence,
not claims re-proved by this review. No chain, keyring, balance, service, or
settlement mutation was performed.

## Review Renewal — 2026-09-09 UTC

A read-only production review confirmed `wolochaind-mainnet.service` and
`wolochain-mainnet-settlement.service` active, loopback settlement on `8092`,
chain ID `wolo-1`, and `ok=true` from `/settlement/v1/health`. The live payout
and escrow signer addresses still match this runbook.

The live payout reserve policy has tightened since the June operating notes:
`WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO=250000000000` (`250,000 WOLO`) plus
`10 WOLO` fee headroom. The escrow reserve remains `100 WOLO` plus `10 WOLO`
fee headroom. At the review observation the payout signer held `417,051.500000
WOLO` and the escrow signer held `1,913,217.500000 WOLO`; those balances are
point-in-time evidence, not static targets.

This review changed documentation only. It did not alter the live environment,
keyring, balances, settlement state, chain, validator, or Wolo transfers. Dated
June funding/floor events below remain historical evidence and are not rewritten
as if their then-current reserve policy still governs production.

## Hard Rules

- Mainnet settlement API: `http://127.0.0.1:8092`.
- Old testnet settlement API: `http://127.0.0.1:8091`.
- Never point AoE2HDBets mainnet settlement, staking reward, or Community Treasury payout calls at `8091`.
- Never commit or print mnemonics, keyring passphrases, or auth tokens.
- Do not replace `/var/lib/wolochaind-mainnet/keyring-file`; use the dedicated settlement keyring dir below.

## Live Shape

| Item | Value |
| --- | --- |
| Node service | `wolochaind-mainnet.service` |
| Settlement service | `wolochain-mainnet-settlement.service` |
| Chain ID | `wolo-1` |
| RPC | `tcp://127.0.0.1:27657` |
| REST | `http://127.0.0.1:1318` |
| Public REST | `https://rest-mainnet.aoe2war.com` |
| Settlement bind | `127.0.0.1:8092` |
| State dir | `/mnt/HC_Volume_105319120/wolochain-mainnet/settlement-state` |
| Keyring backend | `file` |
| Keyring dir | `/var/lib/wolochain-mainnet-settlement/keyring` |
| Passphrase file | `/etc/wolochain-mainnet-settlement.keyring-passphrase` |
| Payout signer | `mainnet-payout` / `wolo1zfa9ssu2gpgqg7yzvhmjt4w66mza07qr2a4rwu` |
| Escrow signer | `mainnet-escrow` / `wolo1zygwt232ymc4h2g52yvkntffhmd5alx2kglw7p` |
| Community Treasury | `wolo1hlfvzuv4dc46ngvh3zlteuegx0xga20hj20zd2` |

## Env File

Install `/etc/wolochain-mainnet-settlement.env` with root-only permissions:

```bash
WOLO_SETTLEMENT_HOME=/var/lib/wolochaind-mainnet
WOLO_SETTLEMENT_NODE=tcp://127.0.0.1:27657
WOLO_SETTLEMENT_RPC_HTTP=http://127.0.0.1:27657
WOLO_SETTLEMENT_REST_URL=http://127.0.0.1:1318
WOLO_SETTLEMENT_PUBLIC_REST_URL=https://rest-mainnet.aoe2war.com
WOLO_SETTLEMENT_CHAIN_ID=wolo-1
WOLO_SETTLEMENT_BASE_DENOM=uwolo
WOLO_SETTLEMENT_DISPLAY_DENOM=wolo
WOLO_SETTLEMENT_ADDRESS_PREFIX=wolo
WOLO_SETTLEMENT_KEYRING_BACKEND=file
WOLO_SETTLEMENT_KEYRING_DIR=/var/lib/wolochain-mainnet-settlement/keyring
WOLO_SETTLEMENT_KEYRING_PASSPHRASE_FILE=/etc/wolochain-mainnet-settlement.keyring-passphrase
WOLO_SETTLEMENT_PAYOUT_KEY_NAME=mainnet-payout
WOLO_SETTLEMENT_PAYOUT_ADDRESS=wolo1zfa9ssu2gpgqg7yzvhmjt4w66mza07qr2a4rwu
WOLO_SETTLEMENT_ESCROW_KEY_NAME=mainnet-escrow
WOLO_SETTLEMENT_ESCROW_ADDRESS=wolo1zygwt232ymc4h2g52yvkntffhmd5alx2kglw7p
WOLO_SETTLEMENT_TREASURY_ADDRESS=wolo1hlfvzuv4dc46ngvh3zlteuegx0xga20hj20zd2
WOLO_SETTLEMENT_ESCROW_AUTO_TOP_UP_ENABLED=true
WOLO_SETTLEMENT_GAS=auto
WOLO_SETTLEMENT_GAS_ADJUSTMENT=1.5
WOLO_SETTLEMENT_GAS_PRICES=0.025uwolo
WOLO_SETTLEMENT_BROADCAST_MODE=sync
WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO=250000000000
WOLO_SETTLEMENT_FEE_HEADROOM_UWOLO=10000000
WOLO_SETTLEMENT_MIN_ESCROW_BALANCE_UWOLO=100000000
WOLO_SETTLEMENT_ESCROW_FEE_HEADROOM_UWOLO=10000000
WOLO_SETTLEMENT_LISTEN_ADDR=127.0.0.1:8092
WOLO_SETTLEMENT_STATE_DIR=/mnt/HC_Volume_105319120/wolochain-mainnet/settlement-state
WOLO_SETTLEMENT_AUTH_TOKEN=<secret outside git>
```

## Key Setup

Create the passphrase file and dedicated keyring before starting the service:

```bash
sudo install -d -m 0700 /var/lib/wolochain-mainnet-settlement/keyring
sudo install -d -m 0700 /root/wolochain-mainnet-settlement-keys
sudo sh -c 'openssl rand -base64 48 > /etc/wolochain-mainnet-settlement.keyring-passphrase'
sudo chmod 0600 /etc/wolochain-mainnet-settlement.keyring-passphrase
```

Generate fresh mainnet signer keys with `--keyring-dir /var/lib/wolochain-mainnet-settlement/keyring` and store mnemonic JSON backups only under `/root/wolochain-mainnet-settlement-keys`.

## Funding Gate

The fresh signers were funded on June 4, 2026 from the approved mainnet Faucet Hot Wallet `wolo1dshyzxffd0jj39k7gj9tq9hgsx96ylxamyp5g0`. Tony restored that Faucet Hot Wallet into the AoE2HDBets app keyring at `/var/lib/aoe2hdbets-wolo-mainnet` as `faucet-hot-mainnet`; do not use old testnet `faucetgrowth` for mainnet faucet claims.

Initial seeded balances (historical June 4 funding):

```text
Bet Payout Signer: 5000 WOLO
Bet Escrow Signer: 500 WOLO
```

Funding txs:

| Purpose | Tx Hash |
| --- | --- |
| Seed Bet Payout Signer with `5000 WOLO` | `F9BBCD8439538E23181F8EC7F43FF6FCA705CB5675C35B2FFA84030DB5DB304C` |
| Seed Bet Escrow Signer with `500 WOLO` | `1FD8AE967608737E3FDD8F8D9E473C1D1FE3D638A221E6C1892284BA26564233` |

On June 27, 2026, normal payout activity reduced the payout signer to `999.750000 WOLO`, correctly tripping `PAYOUT_RESERVE_FLOOR_HIT`. The floor remained at `1000 WOLO`. The approved Faucet Hot Wallet replenished `4000.250000 WOLO`, restoring the signer to the documented `5000 WOLO` operating target:

| Purpose | Tx Hash | Height | Result |
| --- | --- | --- | --- |
| Restore Bet Payout Signer to `5000 WOLO` | `16E19830351313A983BA1FD08C66658C213ECCD7C73CE3B17FDAC246FD8DD56B` | `580909` | `code=0`; `/settlement/v1/health` returned `ok=true` |

The current production service must refuse live payouts when the payout signer would fall below `250,000 WOLO` plus fee headroom. It must refuse escrow-signed runs when escrow would fall below `100 WOLO` plus fee headroom.

## Validation

After restart:

```bash
curl -fsS http://127.0.0.1:8092/settlement/v1/health
sudo SETTLEMENT_ENV_FILE=/etc/wolochain-mainnet-settlement.env \
  WOLOCHAIND_BIN=/usr/local/bin/wolochaind-mainnet \
  /var/www/WoloChain-wolo-1/scripts/verify-live-settlement.sh
```

As of the June 4 funding check, `/settlement/v1/health` must report `ok=true`, `chain_id=wolo-1`, and funded payout and escrow signer balances above their configured reserve floors.

For AoE2HDBets challenge funding, use the exact compact memo:

```text
wolo.challenge.funding.v1:app=aoe2hdbets&sid=aoe2hdbets:challenge-<id>:v1&cid=<id>&side=<left|right>&w=<uwolo>&g=<uwolo>&t=<uwolo>
```

Verify with all identity filters, not just `source_app`:

```bash
curl -sS "http://127.0.0.1:8092/settlement/v1/challenges/funding/deposits?sender=<wallet>&source_app=aoe2hdbets&settlement_run_id=aoe2hdbets:challenge-<id>:v1&challenge_id=<id>&participant_side=<left|right>"
```

Only successful `wolo-1` transfers to the configured escrow are eligible. WoloChain binds `sid` to `cid`, limits the side to `left|right`, requires positive `w` and `t`, permits canonical `g=0` for Championship V2, proves `w + g = t =` the escrow transfer, rejects duplicate funding tx hashes, and uses the same `sid` as the immutable challenge settlement idempotency key.

The June 27 production proof used a deliberately unique operator challenge ID and the approved Faucet Hot Wallet as the exact sender:

| Field | Proof |
| --- | --- |
| Tx hash | `50D5D6A59085A47EBA5C42F1E29BFC1611F813938A744EAFD696CD21F18CDF71` |
| Height / status | `581100` / `code=0`, `tx_success=true` |
| Sender | `wolo1dshyzxffd0jj39k7gj9tq9hgsx96ylxamyp5g0` |
| Canonical escrow | `wolo1zygwt232ymc4h2g52yvkntffhmd5alx2kglw7p` |
| Challenge / side | `20260627230359` / `left` |
| Settlement ID | `aoe2hdbets:challenge-20260627230359:v1` |
| Buckets | `w=1000000`, `g=1000000`, `t=2000000` uwolo |
| Discovery replay | two identical responses; SHA-256 `7f464768d2e0e513e6eae621a90bac324d344a897257c6abc80fbfcc460b825b` |

The exact-filter discovery route returned `count=1`. Wrong side and cross-challenge `sid` filters returned HTTP `400`; an incorrect expected sender on the tx route returned HTTP `409`.

Every grouped app run should be submitted to `POST /settlement/v1/runs/validate` first. Execute the matching `POST /settlement/v1/runs` only after the dry-run response confirms:

- `chain_id` is `wolo-1`
- `signer_role` is expected
- `signer_address` matches payout or escrow signer above
- requested total and projected remaining balance are acceptable
- no reserve-floor or fee-headroom refusal exists

## AoE2HDBets Cutover Values

Use these values in the separate AoE2HDBets app pass now that funding and health are green:

```bash
WOLO_SETTLEMENT_URL=http://127.0.0.1:8092
WOLO_SETTLEMENT_AUTH_TOKEN=<copy from /etc/wolochain-mainnet-settlement.env>
WOLO_BET_PAYOUT_ADDRESS=wolo1zfa9ssu2gpgqg7yzvhmjt4w66mza07qr2a4rwu
WOLO_BET_ESCROW_ADDRESS=wolo1zygwt232ymc4h2g52yvkntffhmd5alx2kglw7p
WOLO_COMMUNITY_TREASURY_ADDRESS=wolo1hlfvzuv4dc46ngvh3zlteuegx0xga20hj20zd2
```

Leave `127.0.0.1:8091` out of every mainnet app env.

## 2026-10-18: current `bdbce253` release candidate and two-service review

The **current** settlement candidate at source
`bdbce253c524d6faac14f61cd129ac5072287c3f` passed the
source-pinned GitHub Actions build and Go financial/race tests. The immutable
candidate artifact `settlement-bdbce253-linux-amd64-UNDEPLOYED` from
run `39083111834` was independently checksum-verified on Mac and VPS.
The root-owned, non-live executable path is:

`/mnt/HC_Volume_105319120/wolochain-mainnet/settlement-candidates/bdbce253-UNDEPLOYED/wolochaind-settlement-only-linux-amd64`

The executable SHA-256 is
`44d8aed5550d1b33635c734c1a359d0cb69e854093ef8c9a8a3da4f99d416ede`.
Do not substitute the retired `3ea79363` binary or any historical promotion
controller. The candidate's authority receipt explicitly says
`production_authorized=false`; checksum validation does not change that.

The root read-only provenance report dated
`2026-10-18T00:47:32Z` confirmed the two existing settlement processes
at `78c25985420ee41a6678c42fab8ea8d6c3b1b519`, PIDs 1012/1010,
original executable SHA-256 `040126a2884946caf1651a50b7d8115c5a6fb2d5aa94fcbbe150694602d451a5`,
and separately preserved consensus PID 1009 / executable
`4b77f622191db7550cb87cafb8f1886a0aadebee3eb6565f9f90036f809e61d3`.
No consensus upgrades/restarts are authorized.

The **current-version** source-controlled
`scripts/settlement-dual-service-release-preflight.sh` and
`scripts/settlement-dual-service-snapshot.sh` now recognize the exact
root-owned `bdbce253` artifact and source pins. Run only reviewed sources
and use the former's read-only preflight and the latter's
`--inspect` option to review invariants before any backup.
The snapshot's `--snapshot` mode creates restricted historical evidence
only; **never restore copied payout request/run state over live state**.
Even when preflight succeeds, it does not prove HD or DE payout ingress
is quiesced, request drain, chain finality, a tested rollback/watchdog,
or authorization to promote. The historical
`scripts/settlement-two-service-code-rollback.sh` remains deliberately
`--inspect`-only and refuses `--rollback` or `--rescue`.

The primary settlement durable-request census has since shown
908 confirmed, 5 failed and one accepted request (versus 904 confirmed
at an earlier comparable observation). The accepted request's public
transaction `D5B4CFAA5E9063F8342EA9E2B6119FCFF28DEE20B2E1DD6803944933B237D699`
was matched by the configured RPC/REST interfaces to a successful
`wolo-1` bank transfer at height `1078913` with the original sender,
recipient, memo and amount. This is **not** signed independent light-client
proof or authority to delete, rebroadcast, or unilaterally finalize its
stored `accepted` state. Founder bonus #15 / claim #889 remains
a separate unresolved legacy liability.

**Still blocking production code cutover:** independently certify HD+DE
payment-producer isolation and no in-flight writes; reconcile live durable
requests against canonically finalized bank effects without replay;
prove exact reserves and liabilities; capture a checksum-verified
restricted backup after protected quiescence; rehearse a current-version
rollback/watchdog that reverts **only** the two settlement units while
leaving the consensus executable, PID, state and chain height untouched;
and obtain explicit named operator approval. App protected Finish and
War Satchel live custody require their own separate migration and
financial-bridge release gates.

## October 18 current-version rollback-state plan — no mutating recovery yet

The production operator's exact reviewed preflight from WoloChain PR #31
returned `PREFLIGHT_PASS` on 2026-10-18 at 01:21:40 UTC. Both existing
settlement units (PIDs 1012 and 1010), dedicated consensus PID 1009,
root-owned non-live `bdbce253` candidate, original systemd units,
restricted historical snapshot integrity, and health ports 8092/8093
matched their exact pins. No lock files were observed, and about 50 GB
remained on the dedicated volume. The receipt explicitly retained
`FINANCIAL_DRAIN_CERTIFIED=false`,
`PARALLEL_HD_DE_SIGNER_FREEZE_CERTIFIED=false`, and
`CURRENT_VERSION_ROLLBACK_CERTIFIED=false`. No promotion occurred.

The source-only `scripts/settlement-bdbce253-recovery-plan.sh --inspect`
now validates the exact rollback *shape* without permitting any systemd
or filesystem mutation. It recognizes both an original two-service
state and an exact two-service candidate state; mismatched, partial,
foreign or modified drop-in configurations block. It pins the preserved
consensus executable and checks that its PID has not changed during
inspection. `--rollback`, `--apply` and `--rescue` remain unsupported.
This is **not** a live rollback tool and is **not** a rehearsed
rollback. It cannot be substituted for an approved current-version
two-service recovery controller and watchdog.

Independent live `findmnt` returned
`/mnt/HC_Volume_105319120 ext4 rw,relatime,discard` with no `noexec`
option. Both systemd units have empty User/Group/RootDirectory/
NoExecPaths and DynamicUser=no, consistent with root execution of the
root-only candidate; no service identity or mode changes were made.

Before any mutating controller is introduced or invoked, provide proof
of HD and DE payment-producer fencing, in-flight drain, exact accepted
bank receipt ownership and outstanding liability reconciliation,
post-quiescence restricted backup, offline rollback rehearsals with
negative tests, an independently reviewed watchdog that never touches
the sole consensus node, and named operator approval. Rollback must
switch **code only** for the two settlement services: never restore
old request/run-state trees into live directories and never
automatically reopen payout ingress. Production website Finish,
database migration and Satchel enablement are separate approval rails.

## October 18: fault-injected OFFLINE cutover rehearsal (not live certification)

`scripts/settlement_bdbce253_offline_rehearsal.py --simulate-all`
creates disposable synthetic systemd-unit override directories and
artificial settlement request records under Python's private
`TemporaryDirectory`. It never calls `systemctl`, SSH, RPC, wallet
signers, database clients, or an actual WoloChain runtime.

The simulation models both exact service names, the root-private
`bdbce253` executable identity, a code-only switch using the same
override bytes as the read-only recovery-state planner, two service
stops/starts, and a recovery that removes **only** the exact owned
override content. Fault injection covers before stop, after stop,
after first/second override, after simulated reload, after first/second
start, and a clean switch/rollback. Each path must return to both
original executables, preserve the synthetic request files exactly,
never alter the synthetic consensus process identity, and keep payout
producer ingress fenced. A foreign or symlinked override is rejected
rather than overwritten; the simulation accepts no live action flags.

This is a useful **design regression**, not a rehearsed real rollback,
not a snapshot, not financial drain, and not evidence of host systemd
semantics. No real services or funds move. It MUST NOT set
`CURRENT_VERSION_ROLLBACK_CERTIFIED=true` or
`FINANCIAL_DRAIN_CERTIFIED=true`. A separate reviewed, operationally
rehearsed current-version controller, producer isolation, independent
liability reconciliation, and explicit named release approval remain
mandatory before installing either two-settlement override in
production.

## October 18: shared HD/DE financial producer enumeration (read only)

`scripts/settlement-shared-producer-inventory-readonly.py --inspect`
is a root-only, bounded, **noncertifying** inventory of active and
installed systemd services/timers with the known HD/DE prefixes
`aoe2hdbets-`, `aoe2war-`, `aoe2dewarwagers-`, and `aoe2-wolo-`, plus
the four explicit web/API service names and bare application service/timer unit names. The `aoe2-wolo-transfer-heartbeat.timer` family is explicitly covered because prior settlement maintenance listed it as a payout-ingress producer despite its different prefix. It reports unit names,
active/loading status, the existence (not values) of PIDs,
and the presence of allowlisted payout/settlement/database **key
names** in bounded process environments. It never reports passwords,
database URLs, mnemonics, wallet values or filesystem keyring paths.

The output supplies **candidates for independent maintenance review,
not units to automatically stop**. In particular the list
`wolochaind-mainnet.service`,
`wolochain-mainnet-settlement.service`, and
`wolochain-founder-rewards-settlement.service` is explicitly
excluded from app-producer stop candidates. No automation in this
source stops or restarts any unit.

The 2026-10-18 VPS read-only inventory returned
`BLOCKED: incomplete systemd unit inventory` with exit code 2 because
the original discovery path **synthesized** extra expected unit names
and attempted `systemctl show` against units that may not be installed.
That generic error did **not** establish that a real signer was active,
missing, or misconfigured. The corrected inventory enumerates only
actual loaded/installed units, lists known exact-name units absent from
the discovery separately as `expectedNamedUnitsNotFound`, and prints
successful per-unit observations even when a particular installed unit
cannot be inspected. The unresolved unit names are retained in
`unitsWithIncompleteInspection`, with exit code 2, never reported
as safe. An entirely inspected inventory still deliberately exits 3,
not a financial fence certificate.

**2026-10-18T03:37:46Z VPS receipt:** The corrected real-unit inventory
identified active HD and DE web/API processes with database keys, HD web
with both settlement endpoint/token key names and staking/faucet CLI key
names, and active WOLO transfer heartbeat, stake reconcile, challenge
reconcile, replay recovery, staking rewards, trophy tributes and
prewarm timers. It printed **no secret values** and changed no services.
Three unresolved inspection errors were `aoe2war-build@.service`,
`aoe2war-deps@.service`, and
`aoe2war-speedos-cloudflare@.service`. They are uninstantiated systemd
`@.` **template definitions** rather than runnable unit instances.
The repaired discovery explicitly records these names in
`templateDefinitionsNotServiceInstances` without asking
`systemctl show` to inspect them. Instantiated template units such as
`aoe2war-build@job42.service` remain included and a failed inspection
of one still produces exit 2. With only template definitions skipped,
a complete report returns noncertifying exit 3 as designed. The HD
and DE active web/API and timer list is for **human classification**,
not a blanket stop list; an active timer can trigger an inactive
financial service while maintenance is underway, and unit environment
key presence alone is not evidence of an active wallet key.

Absent process environment keys do not prove disabled signers, and
installed unit enumeration cannot find every cron, container,
external signer, database job or HTTP caller. Its exit code is 3
even if every inventoried app unit is inactive. It cannot certify
a payment freeze. The two settlement units must be changed only
under a separately reviewed, coordinated operator procedure
supported by positive HD+DE signing authority and in-flight
financial drain evidence. The sole consensus node stays untouched.

## 2026-10-18: independent root + Wolo-volume predeployment capacity guard

The source-only `scripts/settlement-predeploy-capacity-readonly.py --inspect`
checks **both** mounted filesystems before a production Next.js build, a large
bank/ledger snapshot, or a settlement candidate switch. A previous operator
receipt showed approximately **50 GiB free** on the dedicated Wolo volume
(83% used), but older system information showed only **4–5 GiB free** on
the **separate OS root disk**. These are historical observations, not current
capacity evidence.

The guard demands at least **8 GiB available** for unprivileged processes on
`/` and at least **20 GiB available** on the dedicated Wolo state volume,
`/mnt/HC_Volume_105319120`. It refuses a symlink/missing/unmounted Wolo
volume and any volume mapped to the OS root device, so an unexpectedly
unmounted data disk cannot silently consume root space. It performs no writes
or subprocess invocations. No override of these fixed floors is supported.
Missing mount information returns exit code 2; inadequate space returns exit
code 3. A passing minimum headroom check returns exit code 0 but still
reports `productionAuthorized=false`, `financialDrainCertified=false`,
`rollbackCertified=false`.

This is a **screening floor**, not a measured production build, database
backup, state-copy, or rollback footprint. Size the actual backups separately
and retain independent protected snapshots with sufficient capacity. Never
prune chain state, receipt journals, financial backups, or payout records just
to make this check pass. If root is low, add verified storage or otherwise
recover unrelated expendable capacity under a separately reviewed procedure.
Do not attempt protected Finish or wallet maintenance based solely on this
capacity report.

## October 18: source-controlled two-service CODE-only controller (NO LIVE CUTOVER)

The new `scripts/settlement-bdbce253-code-cutover.py` narrows all
service mutations to the two exact systemd services
`wolochain-mainnet-settlement.service` and
`wolochain-founder-rewards-settlement.service`. The dedicated
`wolochaind-mainnet.service` is inspected and pinned by executable and
unchanged PID, **NEVER stopped/restarted/overridden**. Both old and new
settlement executables remain immutable and must match previously reviewed
SHA-256 values. This script never copies, deletes, restores or rewinds
settlement request/run state. App payment producers remain fenced after
either cutover or rollback; code-only recovery is **NOT** permission to
restart financial ingress.

CLI defaults to root-only `--mode inspect`, with no service mutations.
Exact `--mode promote`, `--mode rollback` and `--mode
recover-interrupted` are guarded by an **explicit fresh operator finance
permit** (`--permit`, absolute root-owned and root-group 0600 JSON with
exact implementation revision, candidate SHA, operator acknowledgement,
current 10-minute-or-less validity and named independently reviewed
conditions). The external permit is a *human attestation*, **not**
cryptographic proof of financial drain or bank reconciliation. It MUST NOT
be created until independent evidence establishes ALL of the following:
HD+DE, timers, HTTP, cron, and external signer origins fenced and retained
throughout maintenance; in-flight/accepted chain receipts reconciled;
founder claim #889 entitlement preserved with bank/liability review;
verified fresh post-quiescence state and unit backup; independently reviewed
live service rollback rehearsal; and proven bank solvency. Source CI alone
cannot issue that authority.

The controller checks exact original override-free service identity,
both endpoints and consensus continuity, then serializes operator mutations
under a root-only nonblocking `flock` file. Promotion stops only the two
settlement services, creates two exact exclusive-owned drop-ins, reloads
systemd, starts only those services, and verifies running executables and
the chain-specific health endpoints. systemd can report a service active before
its loopback HTTP listener binds, so a **15-second bounded per-lane readiness
wait** retries only temporary connection-refused/reset/timeout errors. A
wrong-chain or malformed response, HTTP failure, unexpected process
executable or consensus PID drift fails immediately. After both lanes pass
startup readiness, executable identities and both health endpoints are
checked again. Offline fault tests cover delayed HTTP binding, timeout and
wrong-chain rejection. A failure triggers **code-only**
rollback to the original existing binary (not a state-tree restore);
if rollback also fails, it explicitly blocks financial ingress until
manual recovery. Interrupted-code recovery can handle exactly owned
mixed overrides or stopped lanes with the same permit. Foreign drop-ins
and unexpected executable identities are never overwritten.

Offline CI injects errors at service stop, override installation, reload,
service start and health, checking original program restoration, unchanged
simulated request data, no consensus mutation, and no application writer
resume. **These simulated tests are not a real systemd rehearsal**. PR
approval is a SOURCE-ONLY milestone; `LIVE_ROLLBACK_CERTIFIED=false` and
`CUTOVER_AUTHORIZED=false` remain until the operator executes a separately
approved maintenance rehearsal with recorded results. Do not run a
mutating mode until that certification and a named go/no-go are documented.
The protected HD `finish`, eighth schema migration, and dedicated Satchel
8094 activation require separate explicit approval and receipts.

## October 23: distinct first-rehearsal authority and verified backup path

The recovered controller work adds a **separate first-rehearsal permit**. The
existing production permit, its six controls, and its `promote`, `rollback`
and `recover-interrupted` modes retain their existing requirements. A first
rehearsal requires the other five independently evidenced controls; it does
not require an attestation of its own future completion. Neither a permit
parser nor synthetic CI supplies those independent attestations.

The exact historical transition remains `78c25985` / executable SHA-256
`040126a2884946caf1651a50b7d8115c5a6fb2d5aa94fcbbe150694602d451a5`
to the preserved `bdbce253` candidate / SHA-256
`44d8aed5550d1b33635c734c1a359d0cb69e854093ef8c9a8a3da4f99d416ede`,
then back to the original code. Newer held custody source and the separate
federated source baseline are not substitutes for either pinned executable.
The consensus executable/PID remain independently pinned and untouched.

`scripts/settlement_financial_maintenance.py` defaults to nonmutating `scope`
and exits 3. The explicit `fence`, `backup`, and `restore-isolated` modes
require fresh root-private human authority. The shared nonblocking operator
mutex is `/run/lock/aoe2war-wolo-two-settlement-code-only.lock`, also used by
the two-service controller. These modes must never run concurrently.

The fixed activation-fence scope is four services:
`aoe2hdbets-web.service`, `aoe2hdbets-api.service`,
`aoe2dewarwagers-web.service`, `aoe2dewarwagers-api.service`; and both the
`.timer` and `.service` for each of these seven families:
`aoe2hdbets-bet-stake-reconcile`, `aoe2hdbets-challenge-reconcile`,
`aoe2hdbets-replay-auto-recovery`, `aoe2hdbets-staking-rewards`,
`aoe2hdbets-trophy-tributes`, `aoe2war-prewarm`,
`aoe2-wolo-transfer-heartbeat`.
This is a proposed, expressly approved maintenance scope, not permission to
stop all inventory candidates. Consensus and the two
settlement services are outside this producer-fence list. External callers,
manual signers, cron, user managers, containers and every database writer
still require separate positive owner classification and isolation evidence.

The heartbeat runs `backfill-wolo-mainnet-transfers.mjs`: it writes HD indexed
transfer observations, even though it is not an outgoing signer. It therefore
belongs in the quiesced full-database writer fence. Both its timer and service
must be gated before any stop, and either reactivating invalidates the receipt.
This changes the maintenance scope from 16 to 18 units and invalidates the old
scope/tool permit hashes; obtain a newly reviewed exact permit before execution.
The historical two-settlement cutover allowlist is unchanged. The
[independent producer review](https://github.com/Emaren/app-prodn/issues/839#issuecomment-6382780071)
identified the gap. A fresh read-only inventory at 10:09:30 UTC on October 24
found the heartbeat timer active and its writer inactive; see the
[noncertifying receipt](settlement-contracts/financial-release-evidence-20261018/producer-observation-20261024.json).
That observation is neither isolation nor drain; no unit was stopped.

The fence creates a persistent root-private
`/etc/wolochain-financial-maintenance/HOLD` and exact owned systemd
`90-wolo-financial-maintenance.conf` drop-ins. It verifies the effective
D-Bus conditions before stopping timers, their services, then the four apps.
It verifies every scoped unit is inactive with no PID/cgroup or queued job.
HOLD and gates remain after errors, expiry, controller death or reboot.
There is deliberately no automatic unfence or producer-resume command.
The complete operator procedure must separately approve exact gate removal,
the captured prestate restoration order, unresolved-queue disposition and
post-resume checks before a live maintenance window is execution-ready.

The `wolo.financial-maintenance-permit.v1` contract binds exact tool/scope,
review packet and procedure hashes, five human approval references,
external-writer attestations, a maximum 30-minute UTC window, a measured
backup budget, two distinct HD/DE database identities and reviewed financial
table inventories. It requires a pre-provisioned digest-pinned PostgreSQL
image. Database credentials are read only from pinned root-private `/etc`
files and passed in child environments, never command arguments or receipts.
Permit validation checks the syntax and source binding of approval references;
it does not authenticate human signatures, their independence or the truth of
asserted attestations. A trusted owner-controlled issuance procedure and
independent review of the referenced artifacts must establish those facts
before an operator supplies the root-private permit. Test fixtures are never
approval artifacts.

After approved fencing and independently proved in-flight drain, `backup`
reuses the pinned `settlement-dual-service-snapshot.sh` bytes for both
settlement state/config/binary receipts. It creates full HD and DE custom
PostgreSQL archives, compares canonical financial rows, constraints and
sequence state before/after and across both dumps, and rechecks the producer
fence and both journal trees. Hidden or idle sessions, prepared transactions,
changing databases, insufficient space, stale authority and incomplete
snapshots refuse admission. Separate database transactions are not an atomic
distributed snapshot; maintained independently witnessed quiescence is required.

The archive limit is **one aggregate budget**, including the settlement
snapshot: HD may use more than half if DE and the snapshot still fit. Each
`pg_dump` receives the remaining aggregate bytes as its kernel file-size limit;
an exhausted budget refuses the next dump. Actual sizes and the combined
footprint are checked again. This removes an artificial equal-size allocation,
not the approved total or any capacity guard. Archive sizes must be measured;
the ~9.95 GiB live HD database size is not its custom-archive size.

`restore-isolated` actually runs `pg_restore` into separate disposable HD
and DE databases in a digest-pinned container with no network, host credentials
or production PostgreSQL connection. **The held loop-backed restoration revision requires** a pre-provisioned
root:root 0700 `/var/lib/wolo-financial-restore` *wrapper directory*
on the OS-root ext4 device, which must not itself be a mount point. Its only
members must be `bounded.ext4` (a root:root 0600, singly linked, fully
allocated 8–64 GiB regular backing file on OS root) and `bounded/` (a
root:root 0700, separately mounted ext4 filesystem on a Linux loop device).
The backing file and bounded mount are prepared **out of band** by an
independently reviewed operator procedure; this script NEVER invokes
`losetup`, `truncate`, `mkfs`, `mount`, or `umount`. Do not infer
that availability of those tools or an idle `/dev/loopN` provisions storage.

A read-only operator preflight is available:
`scripts/settlement_financial_maintenance.py --mode inspect-storage`
(requires root; returns exit 3 with JSON schema
`wolo.bounded-restore-storage-inspection.v1` when its precise
kernel/backing admission succeeds). It reads filesystem metadata without
opening HD or DE, creating a maintenance lock, fencing a service, creating a
backup, initiating a restore or changing any live process. Its report includes
logical and allocated backing bytes, bounded total/free bytes, OS-root free
bytes, and explicit false financial/quiescence/backup authorizations. Exit 2
means HOLD/incomplete; neither exit code authorizes fund movement.

The script checks one exact kernel mountinfo entry, `ext4`, required
`rw,nodev,nosuid,noexec` flags, exact block-device identity and sysfs loop
backing-file identity, full physical backing-file allocation, finite
filesystem size no greater than that file, and >= twice the authorized
backup budget in *available bounded filesystem capacity*. It also requires
at least 8 GiB free on OS root after preallocation. An absent, sparse,
symlinked, wrong-device, unexpected, extra-member, too-large, undersized or
unmounted backing filesystem refuses restore admission.

Only a uniquely named uid 999-owned `bounded/restore-<random>` directory
may be bound read/write into the network-disabled PostgreSQL container at
`/var/lib/postgresql/data`; the private root-only wrapper never enters the
container. The container root remains read-only, and no production socket,
keys, wallet, state volume or credentials are mounted. Mount association
is rechecked after Docker identity validation and after restoration, and a
verified owned container must be removed before symlink-safe scratch cleanup.
Cleanup separately revalidates the bounded mount before deleting only its
own child; any unknown container, changed mount or stale `restore-*` path
preserves `INCOMPLETE` and fails closed. No verified restore receipt may
be published until cleanup, bounded mount recheck and a fresh current producer
fence/window check have succeeded. Backup publication also rechecks the current
fence after all final census and receipt-hash I/O. Window expiry at either
boundary preserves `INCOMPLETE`; it cannot publish a success receipt or resume
producers. Cleanup of the verified disposable container still runs on expiry.

The finite loop image is an enforced maximum for PGDATA writes, **not**
proof of full-size restoration, source/mount integrity across a hostile root
operator, durable off-host backup, quota for Docker daemon logs, financial
quiescence, or custody release. The real ~9.95 GiB HD plus DE restoration
and census/sequence checks still require independently witnessed proof,
along with authorized HD/DE writer fencing and finance review. Central Command
[reported the 40 GiB fully allocated mount and exact-source storage inspection](https://github.com/Emaren/app-prodn/issues/839#issuecomment-6382701190)
on October 24, 2026; that storage-only receipt does not certify a production-size
restore. No production backup/restore or cutover has been approved, and original
consensus/settlement services must remain untouched.

Before scheduling the approved window, the operator and recovery witness must
qualify full HD **and** DE archives on the exact pinned source/image and bounded
filesystem. Record archive bytes, peak PGDATA usage, each dump/restore duration,
financial row/constraint/sequence census time, cleanup time and time remaining
for paired binary recovery and safe abort. The unchanged limits are 300 seconds
per dump/restore, 2 GiB memory, two CPUs, and at most 30 minutes of permit
authority across the procedure. Small CI fixtures do not prove those limits fit
production. If they do not fit, retain HOLD and obtain independent review of
measured resource/window changes and a fresh permit; never extend a live permit
or drop census comparisons to finish. Use independently approved recovery
copies for a pre-window size/timing trial; obtaining a current quiesced copy
from production is itself a separately approved fence/drain/backup operation.
Off-host checksum and recovery verification, complete producer/queue drain,
privilege recovery and human approvals remain separate prerequisites.
The present controller requires the original fence window to remain current for
both backup and isolated restore. `verify_retained_fence` is observational only;
it cannot renew that authority. Separating a short live capture window from a
longer offline verification phase would require a separately reviewed bounded
authority contract, not reusing an expired permit.

Full row hashes, constraints and sequences must match. A checksum alone
or `pg_restore --list` cannot pass. `INCOMPLETE` remains until this
succeeds; only final `restore.json`, bound to its manifest and fence,
can admit a rehearsal.
These receipts explicitly do not prove off-host survival, independent witness
approval, owner/privilege recovery, point-in-time WAL recovery or solvency.
Those recovery requirements remain separately reviewed operator evidence.

`scripts/settlement-bdbce253-code-cutover.py --mode first-rehearsal
--permit ABSOLUTE_PROTECTED_FILE` accepts only
`aoe2war.wolochain.first-settlement-rehearsal.v1`. It binds exact binaries,
source/evidence/approval hashes, the verified fence and isolated-restore
receipts, a unique execution ID and a bounded UTC operator/witness window.
Individual authority is at most ten minutes and must be newly issued.
The only allowed successful sequence is paired old → candidate → old.
Caught failures receive bounded original-code cleanup and retain all fences.
No financial journal is restored or rewound, and no payment is retried.

The root-private journal under `/var/lib/aoe2war-wolo-first-rehearsal` is
fsynced before service changes. A transient independent systemd watchdog is
bound to the controller's boot ID/PID/start time and its own InvocationID.
It survives SSH/controller death and records immutable detected-loss time.
Controller loss alone never authorizes recovery. Later manual or watchdog
recovery requires `aoe2war.wolochain.fresh-rehearsal-recovery.v1`, issued
after that loss, bound to the exact session and fresh human approvals. Each
attempt is consumed durably; retries need new authority. A changed host boot
identity requires a separate incident procedure. Expired original fence
authority is observable as retained gates, never renewed into new permission.

Completion receipts keep `production_authorized=false`,
`financial_resume_authorized=false` and `independent_witness_attested=false`.
They never update the canonical six-control checklist automatically. A real
independent witness must review actual live paired runtime, unchanged
consensus, state and drain evidence before the sixth production control can
be attested under a separate final promotion authorization.

CI exercises fault-injected controller/backup contracts, actual disposable
Linux systemd activation denial and watchdog SIGKILL survival, and real
isolated PostgreSQL archive restoration and corruption refusal. These tests
qualify source mechanics, not a live financial rehearsal or backup. The
canonical `docs/settlement-contracts/financial-release-checklist.json` remains
the only six-control index: five controls BLOCKED, independent global solvency
UNKNOWN. Preserve the accepted 100-WOLO UNKNOWN outcome, claim #889 and
nonadditive historical obligations. Satchel custody stays UNAVAILABLE; the
financial bridge, signer activation, migrations and funded canary remain on
their separate protected approval rails.

## 2026-10-25 — historical-100-WOLO archive-only time verification

The original `verify-historical-transfer` command passed a months-old portable
Comet transcript through the LIVE `VerifyTransferProof` wall clock, which
rejects authentic old signed heads and anchor periods as stale. This is not a
false chain-signature finding: the command used today's expiry conditions for
an explicitly historical transaction.

This held source candidate adds a **separate type**
`satchel.ArchivedTransferEvidence` and a single
`satchel.VerifyArchivedTransferProof` path, exclusively used by the
offline accepted-100 historical command. The operator-provisioned
`ExpectedHistoricalTransfer.historical_as_of_utc` value is a strict UTC
seconds timestamp, not a new trust anchor or external attestation. It must
fall within the original signed Comet time/anchor/witness validity verified
cryptographically by the *same* bounded light client, H and H+1 proof,
signed exact transfer and original receipt ordinal checks. The historical
as-of comes from separate independently reviewed historical records and
must **not** be guessed from a convenient untrusted head. Caller clock
substitution is explicit in this *single offline* proof verifier only.

The result's type cannot be passed to the normal live credit/settlement
admission APIs; `CreditAuthorized=false`, and even successful historical
verification returns exit **3**, flags independent anchor/journal proof,
solvency, custody, retry and release permission **false**. It does not
create a durable receipt, unlock any payout, mutate Wolo, or mark original
accepted 100 WOLO as paid. Mainnet settlement still holds until independently
grounded original obligation identity, root provenance and global accounting.
The original LIVE `VerifyTransferProof`, all bank/deposit freshness and
production settlement guard paths are unchanged.

Exact-head CI and offline adversarial fixture tests are required before even
source-only qualification. No production binary deployment or historical
payment retry is authorized by this source review.

### Exact-source Linux artifact for the historical-only verifier

The archived proof candidate has a **separate** reproducible Linux AMD64
`wolosatcheld` artifact, built twice with disjoint fresh Go build caches by
`.github/workflows/archived-wolosatcheld-artifact.yml` under Go 1.24.6,
`CGO_ENABLED=0`, `-trimpath`, VCS provenance and strict manifest comparison.
The implementation pinned is
`c575b175e6dc74c720479a04e41490a842032203`. That commit includes
the explicitly separate `ArchivedTransferEvidence` path and offline
historical accepted-100 verifier; it predates only source-artifact
administration and subsequent documentation. The builder pin is not a
running mainnet binary, settlement service upgrade approval, trust anchor,
solvency witness, custody authorization, or owner financial signature.

Use the artifact solely for offline evidence review after authentic
operator-provisioned historical checkpoint/as-of and exact signed
original journal intent have been established; **do not install**
`wolosatcheld` on the HD production server, enable its custody
routes, replace Wolo settlement services, or rebroadcast historic 100-WOLO
or claim payouts from this build. The CI artifact must be independently
retrieved and SHA-256 checked against the authenticated GitHub workflow
identity before a separate operator inspection.


## Single-owner maintenance runtime candidate — October 26

The source-only #109 intent verifier remains NONAUTHORIZING. The separately
versioned `scripts/settlement_solo_runtime.py` uses the signature domain
`AOE2WAR-WOLO-SOLO-MAINTENANCE-RUNTIME-V1\0` and packet schema
`wolo.solo-maintenance-runtime-packet.v1`. Old offline signatures and five-role
permits cannot be relabelled into this domain. One enrolled Ed25519 owner signs
each capture and isolated verification phase. No private owner key is loaded by
the controller. Revoked/expired enrollments fail before nonce consumption.

The existing `settlement_financial_maintenance.py` lease now dispatches
`solo-capture` and `solo-offline-restore`. The new permit schema
`wolo.solo-owner-maintenance-permit.v1` accepts exactly one owner approval;
all original scope, source, database, attestation, image, byte-budget and window
guards remain. The old v1 schema still requires its original five role refs.
Capture fences the existing **18 units** (4 apps, 7 oneshots and 7 timers), drains them and calls the original
bounded snapshot/dump implementation. Restore uses a separate signature, retained
fence, exact completed capture lineage and the existing bounded ext4 isolated
PostgreSQL mechanics. A restore window may be up to four hours; this never
extends the original maximum 30-minute capture authorization. No automatic
unfence or resume occurs at either expiry. An outage extending beyond capture
must be explicitly accepted in the owner's complete procedure before capture.

Admission requires root-private enrollment at
`/etc/wolochain-financial-maintenance/authority/solo-runtime.json` and
`solo-owner.json`; no environment variable or caller-supplied hash substitutes
for those operator-provisioned files. The runtime enrollment binds the exact
four controller module hashes, source commit, actual host identity and owner
public-key/enrollment digests. Actual running consensus and both settlement
executable hashes are checked before and after authority consumption; none of
those processes is stopped or changed. All 12 writer categories must resolve to
retained observation bytes whose hashes are bound by the signed procedure.
These observations and the owner's external-fence attestations are **not** a
machine certification that every external writer is excluded. Successful
receipts explicitly retain `global_writers_fenced=false`,
`custody_or_solvency_certified=false` and `financial_release_authorized=false`.

The off-host nonce witness is executable code, rather than an always-refuse
stub. Install the same reviewed protocol on a separately controlled host outside
VPS rollback scope. Pin the target VPS identity and owner/source enrollment there;
pin the witness host identity and SSH host key on the VPS. On the witness, the
fixed `wolo-maintenance-witness-v1` SSH forced command invokes:

```sh
python3 /protected/reviewed/scripts/settlement_solo_runtime.py --witness-stdin
```

Use an existing dedicated operator transport credential with a restricted SSH
forced command, no PTY, forwarding or agent access. Never reuse a WOLO signer
key. On macOS, enroll canonical `/private/etc` and `/private/var` witness paths.
Both hosts pin their own absolute OpenSSL 3 executable and binary digest in the
protected enrollment; a restricted SSH PATH must not select macOS LibreSSL,
which lacks the required Ed25519 `pkeyutl -rawin` operation.
The witness verifies the original owner signature and time/phase before
atomic, fsynced O_EXCL consumption in its separately provisioned 0700 nonce
ledger. The ledger must never be restored from a VPS snapshot, automatically
pruned, or recreated after loss. Any corrupt/partial record blocks subsequent
admission. An SSH timeout or lost acknowledgement means **nonce may already be
consumed**: inspect both retained ledgers; never redispatch the same authority.
The witness authenticates consumption, not chain finality, human review or funds.

After legitimate enrollment and procedure review, the read-only preparation CLI
emits the exact unsigned request and base64 signing message (exit 3):

```sh
sudo python3 scripts/settlement_solo_runtime.py --prepare \
  --mode solo-capture --procedure /root/reviewed/capture-procedure.json
```

The real owner inspects the complete procedure and signs that message locally
using the existing protected key. Supply the resulting packet and exact permit:

```sh
sudo python3 scripts/settlement_financial_maintenance.py --mode solo-capture \
  --packet /root/reviewed/owner-capture-packet.json \
  --procedure /root/reviewed/capture-procedure.json \
  --writer-inventory /root/reviewed/writer-observations.json \
  --permit /root/reviewed/solo-capture-permit.json \
  --fence-receipt /root/reviewed/fence.json \
  --output /mnt/HC_Volume_105319120/wolochain-mainnet/financial-maintenance-backups/OWNER_SELECTED_NEW_CAPTURE \
  --completion-receipt /root/reviewed/capture-completed.json
```

**Live capture status: HOLD_ENGINEERING. Do not issue a live owner challenge yet.**
The current fence does not retain all producer unit/env/build fingerprints, and
a qualified resume path and production-size outage bound remain engineering
requirements. The 12 category observation files alone do not prove global writer
exclusion. No actual enrollment, witness,
owner approval or global fence has been installed by source development. Resume
and financial activation remain refused; their real recovery and financial
predicates must be qualified before a maintenance window is approved. In
particular a four-hour isolated verification is incompatible with promising a
30-minute full outage unless production-size evidence proves the total fits.
Historical 100-WOLO uncertainty, claim #889, refund #8477, shared DE liabilities,
original source provenance and the independent historical checkpoint remain
unchanged. The website stays at its existing certified release.
