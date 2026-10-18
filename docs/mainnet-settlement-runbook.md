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
reviewed_at: "2026-10-16"
review_interval_days: 14
sensitivity: "restricted"
---

# WoloChain Mainnet Settlement Runbook

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

