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
reviewed_at: "2026-10-14"
review_interval_days: 14
sensitivity: "restricted"
---

# WoloChain Mainnet Settlement Runbook

## Parallel WOLO financial ingress and actual systemd rehearsal (October 14, 2026)

The October 14 VPS service inventory also showed
`aoe2dewarwagers-web.service` and `aoe2dewarwagers-api.service`
**active**. These are not part of the currently allowlisted stop/resume
manifest. Source in the separate `Emaren/aoe2dewarwagers-web` repository
contains executable endpoints for WOLO claims, scheduled settlement and
staking rewards. It has **not** been proven that the live instances do not
share a signer, database, or payout transport with AoE2WAR.

The draft controller therefore **blocks before the first service stop or
timer arm** if either parallel unit remains active. Never disable that
check merely to force deployment; instead independently establish the
live unit source/financial authority and design an explicit scoped ingress
pause and recovery, or show with source and runtime evidence that the
service cannot reach the affected signer. Other remote payout ingress
also requires proof of isolation before the maintenance window.

CI now includes `tests/settlement-watchdog-real-systemd-ci.sh` in its own
ephemeral Ubuntu runner, with a temporary synthetic node and rescuer,
sandbox-only files and uniquely named transient systemd timers. It
rehearses watchdog lock timeout and independent retry, watchdog skipping
a committed release, and already-rescued idempotency. It never invokes
any AoE2WAR production unit, wallet, chain endpoint, or executable.
**Even a passing runner integration test cannot certify the real VPS
recovery deadline, a hard-hung controller, detached SSH session or power
loss.** Keep PR #11 **draft** until operator-reviewed disposable-systemd
VPS rehearsal and complete financial quiescence proofs exist.

## Watchdog-gated dual-service promotion controller (October 14, 2026)

`scripts/settlement-two-lane-watchdog-controller.sh` is **SOURCE ONLY**. It
has not been installed, activated or executed against the VPS, and has not
been certified by a real maintenance-window recovery rehearsal. Its **default
`--inspect` mode is read-only**. No other process, app release or administrator
is authorized to set `--promote` until a separate operations approval gate is
recorded on Wolo issue #5.

The guarded `--promote` plan requires the exact old executable, candidate
SHA-256, unchanged consensus executable, private two-service backup receipts,
both preexisting original unit definitions, root-pinned installed independent
rescue script and verified read-only application finance auditor, and an
explicitly scoped operator acknowledgement. It takes a nonblocking exclusive
flock, **runs the financial audit before causing downtime**, and refuses to
start maintenance while unresolved historical claims (including #889) exist.

Only if that first financial scan is zero does it arm a **systemd monotonic
900-second (15-minute) independent rescue timer** (which survives SSH disconnection), record
which producer units were initially active, pause the specifically enumerated
six automatic payment/replay timers and the AoE2WAR web/API request ingress, and
wait for any running timer jobs to finish/stop. It then re-runs the live
read-only finance scan, verifies no active state locks and no established
connections on 8092/8093. If anything is ambiguous, the rescue script
restores original *code* for both settlement units and resumes the original
web/API/timer set from a root-private manifest. The validation may require a
brief site maintenance interruption; it never touches consensus units, chain
files, keys, wallets, historical primary/founder state or the shared original
settlement binary.

Only following a successful second drain can it stop **the two settlement
services only**, install exactly the versioned candidate `ExecStart` override
for each, reload systemd configuration, restart the two settlement processes,
verify exact running SHA-256 and healthy loopback APIs, recheck the consensus
executable, restore the originally active app ingress/timers, and disarm the
independent timer. An error leaves the timer armed and tries immediate rescue.
The original Wolo VPS **source checkout is deliberately not modified**;
a separate post-cutover source/runtime attestation and protected checkout
review are still required before the app's P1 Wolo source-drift gate can pass.

**Separate helper staging:** `scripts/settlement-release-helper-stage.sh`
defaults to read-only `--inspect`. An explicitly approved `--stage`
downloads the immutable Wolo rescue source at Wolo merge
`f547b5d6e25d0bf843fb6b83c8b88b4a3d1d5cbb` and app read-only
financial audit at app merge
`3ecc28bd983bd517f4e82b982ef5726f3f33eaf7`, independently checks both
pinned Git blob hashes, and installs root-controlled files outside both live
Git worktrees in `/usr/local/libexec/aoe2war-wolo`.
The rescue is mode 0500 root-only; the nonsecret auditor is mode 0444 and
can load production PostgreSQL access only through the private transient
systemd EnvironmentFile. Staging prints both SHA-256 digests to allow an
independent activation pin. **Staging is not activation**; it never stops
services or transmits WOLO.

**Hard pending blockers:** The source of the installed rescue and financial
audit must be independently pinned and root-owned; they are NOT currently
installed as controller dependencies. The live finance scan returned
`bet_claim_payout_attempt_without_proof=1`, legacy founder claim #889.
This must be proved against authoritative chain history or otherwise
resolved by a separately reviewed financial correction before an actual
activation is allowed. No bypass, status forgery, manual blind refund,
historical state rewind, or consensus restart is authorized.

The longer independent fallback interval avoids interrupting a still-running bounded multi-unit transition, but implies up to 15 minutes of unattended recovery delay after a hard SSH/process failure. A live rehearsal must prove both normal-window duration and immediate error-triggered rescue before approval.

Production release is NOT complete. A verified code-only rescue mechanism is
necessary but does not, by itself, establish an atomic payout drain or mainnet
solvency.

**Repeatability correction (source-only; October 14):** The independent
transient timer now combines `--on-active=900s` with
`--on-unit-inactive=60s`. If a watchdog invocation times out waiting for the
controller's bounded handoff mutex, exits with an error, or fails an initial
recovery attempt, the armed timer schedules another invocation after the last
attempt becomes inactive. The controller explicitly stops that repeating
timer only after a verified commit or completed immediate rescue. The watchdog
gate rechecks the durable COMMITTED/RESCUED marker under the mutex, so an
already finished transition is not rolled back on the next tick.
Synthetic promotion CI refuses a return to single-fire timers.

**This still is not live authorization.** The initial 15-minute recovery
delay, the watchdog's 150-second mutex wait, on-host `systemd-run` timer
behavior, and intervention on a permanently hung controller require a
disposable systemd transaction rehearsal and documented downtime objective.
The founder claim #889 and independently verified financial drain remain
separate, unresolved activation gates.

## Draft watchdog handoff correction — source rehearsal only (October 14, 2026)

The earlier dual-settlement controller had a real race: it reopened
aoe2war web/API and payment timers **before** disarming its independent
one-shot rollback timer. If the timer had already fired and was waiting to
run, it could revert both newly healthy settlement executables *after*
financial ingress reopened. **That version must never be run on mainnet.**

The revised draft introduces `scripts/settlement-two-lane-watchdog-gate.sh`.
The operator must separately source-pin this third private helper before any
promotion is even considered. The controller now:

1. Captures the original producer roster in a complete root-only file and
   atomically publishes it **before** arming the independent timer.
2. Holds a dedicated `handoff.lock` from **before the first producer stop**
   through verified service health, producer resumption, an atomically
   written `COMMITTED-3EA79363` outcome and disarming the timer.
3. Schedules the watchdog *gate*, not the raw code rollback. The gate waits
   for the same lock and inspects the outcome: committed release => no action;
   verified prior rescue => no action; otherwise run exact pinned two-service
   `--rescue` and persist `RESCUED-3EA79363`.
4. On a trapped normal failure, attempts immediate code-only rescue under
   the same controller-held lock. The timer remains a disconnected-session
   contingency and cannot misread an already committed outcome.

Isolated tests must exercise a timer already waiting at commit, operator
crash before commit, idempotent duplicate wakeup, invalid marker and
unsafe/incomplete roster. **Synthetic tests cannot certify behavior during a
real Linux power loss, hung controller, network interruption or failed
systemd service transaction.** The watchdog still has a bounded 900-second
delay plus a 150-second lock wait, and on lock timeout cannot guarantee
automated restoration. A protected disposable systemd fault-injection
rehearsal, audited helper staging, app payout-drain proof and explicit
maintenance authorization remain required. This PR stays DRAFT;
`--promote` is **not authorized**.

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


## Emergency code-only two-service rollback (October 14, 2026)

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
