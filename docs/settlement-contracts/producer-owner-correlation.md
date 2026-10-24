---
id: "aoe2war.wolochain.producer-owner-triage"
title: "HD and DE Financial Producer Owner Review"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war","aoe2dewarwagers"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "git"
authority: "non-authorizing-financial-producer-evidence-correlation"
reviewed_at: "2026-10-20"
review_interval_days: 14
sensitivity: "internal"
---

# HD and DE Financial Producer Owner Review

## Non-authorizing contract

This runbook adds a **read-only source/runtime correlation report** to WoloChain's existing six-control financial release HOLD. The standalone `scripts/settlement_producer_owner_triage.py` does **not** access any service, database, signing key, wallet, network endpoint, or production checkout; it only reads three bounded sanitized JSON observations that an authorized operator has separately collected.

Inputs are (1) the established root-run `scripts/settlement-shared-producer-inventory-readonly.py --inspect` JSON, (2) the app-owned HD `scripts/aoe2_financial_producer_source_census.py` JSON, and (3) a DE web-source scan `scripts/settlement_de_producer_source_map.py --de-root <exact clean DE checkout> --check`. These observers are **not** trusted runtime financial attestations and have deliberate nonzero/noncertifying exit codes. No tool execution by itself grants a deployment approval.

The correlation tool uses `--runtime <file> --hd-source <file> --de-source <file>`, reads only regular bounded JSON files, rejects leaf symlinks, duplicate JSON keys and changed inodes, and prints a sanitized list of *public unit names* with owner-review classifications (HD/shared, DE or unknown). It will not emit financial environment names, values, signer locations or secrets present in the input. A runtime observation is labelled fresh only for a bounded one-hour window relative to UTC; future or invalid timestamps are stale. Duplicate, unknown, malformed or omitted units must be reviewed. The tool exits **3 even if all three inputs look valid**.

The report marks the following **false unconditionally**: deployed-source-to-running-executable parity, producer isolation, reconciled transfers, financial release, website release, and mutation of production. All input sources can be mutually consistent while independent HD/DE wallets, direct mnemonic and keyring paths, processes, HTTP/timer/cron ingress, and outstanding obligations remain unknown.

## First owner-review sequence

1. Obtain the current protected-systemd inventory through its existing audited root-read-only collector, without copying process environment values or shell command lines to public documents.
2. Verify the exact clean HD/DE source checkouts separately from their running service and build identities. Local Git HEAD alone cannot prove the running production build. Preserve a restricted raw receipt and publish sanitized summaries.
3. Correlate runtime units with HD and DE source edges, including **GET /api/lobby** → market ensure → settlement, DE faucet CLI, DE claim/admin payout, conditional payout mnemonic and staking signer fallback.
4. Have named HD, DE and external financial owners classify all discovered services/timers, independent signers, user managers, containers, cron, HTTP ingress, queued/in-flight/uncertain payments and expected restarts. An active unit is **not** automatically a producer; an inactive unit is **not** automatically safe.
5. Separately and explicitly approve a bounded coordinated fence/drain only after each producer authority and its restart paths are mapped. Do **not** blanket-stop app services, consensus, 8092 or 8093 based on this report.
6. Continue the other five financial controls: authenticated per-request outcomes, claim #889 continuing hold/disposition, quiesced state snapshots, paired settlement-only rollback rehearsal, and verified bank solvency with complete liability bound.

## Protected implementation boundaries

This is source evidence for WoloChain issue #5 and held financial-evidence PR #42. It is **not** a live Satchel or Auto Bets enabler, an authorization for the website-only lane, or a reason to change the documentation implementation baseline to the running VPS Git SHA. Source-only tests prove parsing/guard invariants, not independent chain or financial truth. All six controls continue in HOLD until accepted by the existing operator approval flow.

## October 20 — institutionalized maintenance lessons and the HOLD board

Owner authorization to arrange maintenance **is not an independently
authenticated six-control release permit**. The owner reported no present
player activity and authorized coordinated financial maintenance. Historical
production records still contain possible obligations: an accepted 100-WOLO
request with no independent finality, founder claim #889 (300 WOLO, attempted
with no recorded hash), and a scoped HD pending-claims observation of 947
claims / 993,189 WOLO. These amounts are from dated observations, may overlap
and cannot be added into a global solvency sum. Activity level is not debt
extinction or authority to retry uncertain payments.

`scripts/settlement_maintenance_board.py` is the **small, offline
read-only bridge** between our current six-control evidence checklist,
the previously reviewed source/producer triage, and a human-maintenance
task queue. It:

- Reads the canonical existing checklist through
  `financial_release_checklist_audit.audit` first, so missing evidence,
  noncanonical controls, forged PASS status, changed hashes or removed
  liabilities fail before reporting.
- Optionally reads the original sanitized
  `settlement_producer_owner_triage.py` JSON, refusing unreviewed owners,
  impossible counts, unsafe unit names, symlinks, duplicate JSON keys and
  attempts to promote a source observation into producer isolation proof.
- Never equates an earlier triage freshness flag with a fresh current live runtime observation: the report revalidates neither chain height nor producer status.
- Projects **only named public systemd units and fixed owner-review
  categories**, never copied process environment variables, mnemonics,
  complete shell arguments, payout keys or user balances.
- Prints an ordered finite operator review path: classify all HD/DE/external
  signers, cover user managers/containers/cron and hidden HTTP writers, approve
  the scoped fence/drain, resolve all uncertain payments, preserve #889,
  verify independent bank/global liability/gas, take fresh quiesced
  checksummed backups, witness paired code-only recovery and seek a **separate**
  cutover permit.
- Always returns exit **3 on a valid HOLD board**, exit 2 on invalid or
  missing evidence. It cannot produce success/exit 0, sign, transfer, change
  systemd or issue production permission. A green unit test is not a live
  witness. This remains true even when someone asserts there are zero users.

Example, in an **isolated, code-reviewed checkout** containing these scripts
(not by changing the live Wolo working tree):

```sh
python3 scripts/settlement_maintenance_board.py
# Expected: JSON status HOLD; process exit 3 (deliberate).
# Optional: --triage /path/to/sanitized-triage.json
```

The original **production** source checkout and both settlement services
MUST remain unchanged while collecting this diagnostic. To obtain fresh
read-only operator inputs, separately use the already reviewed protected
tools from a safely pinned checkout:

```sh
sudo python3 scripts/settlement-shared-producer-inventory-readonly.py --inspect
sudo python3 scripts/settlement-parallel-de-authority-inventory.py
sudo python3 scripts/settlement-bdbce253-code-cutover.py --mode inspect
```

These tools are intentionally nonauthorizing (some exit 3); do not chain
them with `&&` as though exit 0 meant financial clearance. Do not
paste raw private receipts into GitHub, an AI chat or public logs.
Keep sensitive raw evidence root-private and share only scrubbed,
scope-labeled summaries. No tool automatically fences producers.

### Incident-to-permanent-guard register

| Observed failure | Root cause / distinction | Permanent defense |
| --- | --- | --- |
| Watcher v1.6.5 docs sync crash | Public release state and README prepublication heading disagreed | Verify immutable artifact publication separately from historical README prose; CI contracts must distinguish current vs historical release |
| Cascade of central/docs/context P1 warnings | Generated source registry and dated archive snapshots lagged reviewed source | Use isolated `aoe2war update --maintenance-only` with checksum/ancestry checks; do not touch runtime or erase historical context |
| The app `finish --dry-run` blocked despite certified website | Active 8092/8093 binary/source at `78c25985` is NOT checked-in implementation baseline; code-only candidate `bdbce253` is neither current runtime nor newer Satchel | Keep binary SHA, running PID/exe, checkout and consensus attestation distinct. Never edit metadata or fast-forward checkout to fabricate parity |
| PostgreSQL reviewer impersonation gap | Checking `current_user` alone permits a privileged login to `SET ROLE` | Require both `session_user` and `current_user` pinned read-only/least-privilege for hold, signed owner mandate and market reads; regression-test every call site |
| App wager approval verified with withdrawal key | Multiple modules shared a generic “reviewer key” despite separate Wolo signing roles | Purpose-specific keys in pickup, ledger, signer and offline Comet proof; prevent role collision, symlinks, permissive files and prebroadcast file swaps |
| Signed HTTP/REST ACK treated as potential financial finality | Receipt transport, real chain bank effects and full asset/liability/fee reconciliation are different trust domains | One-shot durable request fence, no retries of UNKNOWN, original operation digest, independent canonical Comet finality and global solvency before credit/spend |
| Green CI mistaken for mainnet permission | Synthetic SDK fixtures cannot prove live wallet custody, unknown old payouts, operator approvals or producer drain | Maintain literal financial HOLD and six independently witnessed controls; require separate signed live production approval and end-to-end funded canary |
| Repeated uncertain obligations / incomplete producer ownership | Active units and idle player count do not enumerate cron, DE/HD side effects, keyrings, user units, containers and external signers | Sanitize and correlate all source/runtime producer paths; explicit owner classifications and maintenance window before scoped fence, quiesced snapshot and recovery test |
| Documentation temptation during difficult debugging | A stale registry or manually changed baseline can turn real financial drift into fake green | No documentation-only source-alignment bypass. The release board always exits HOLD and public source reports never become financial permits |

**Stop/go authority remains with WoloChain issue #5 and its single
six-control checklist.** Its historical target `bdbce253` is separate
from app PR #684, Wolo Satchel signer PR #39 and Replay API original
Watcher/market proof. The later automatic-wager service must establish
its own independently witnessed market, original signed owner mandate,
full global assets/liabilities and gas census, dedicated custody keys,
funded deposit/settlement/refund/withdrawal canary and separately
authorized production release. No amount of “no active players” can
replace those financial controls.


## October 20 — first fresh root-runtime observations and activation-topology follow-up

The operator ran exact old runtime inspection and two original-source-pinned
root read-only inventories at **2026-10-20 03:37 UTC**. This is a *dated*
observation, not continuous release proof. The runtime control returned
`LIVE_CODE_STATE=old` (exit 0), `FINANCIAL_DRAIN_CERTIFIED=false`,
`RELEASE_AUTHORIZED=false`. The HD/DE shared inventory observed 19
discoverable app service/timer units, zero incomplete discovered-unit
inspections, 11 active finance-maintenance *candidates* and deliberate
exit 3; no runtime mutation. Exactly 11 candidates means **not** 11
independently proven money-moving signers.

The HD website was active with *variable names* evidencing settlement URLs,
settlement bearer credentials, wallet payout-address configuration and local
faucet/staking CLI routes. A public GET lobby or live-games read may call
market-ensure and then settlement; HTTP inactivity or simply suppressing POST
does **not** isolate its financial ingress. The shared prewarm timer remains
active and may trigger those GETs. The HD staking reward, bet-stake,
challenge reconciliation and trophy tribute timers are active; their one-shot
services being inactive is not proof that a scheduled financial writer is
quiescent. The transfer heartbeat timer also remains active. **Do not
blanket stop these units** without the exact activation/ingress plan and
independently classified authorizations.

The DE web and API processes were active. In the separate DE inventory,
the web's process exposed WOLO RPC and payout account variable **names**,
but neither DE service exposed signing-secret variable names. Both tools
explicitly warn this cannot exclude app-loaded dotenv, CLI-keyring, remote
or external signing. Keep DE classified as potentially capable until
source/runtime/credentials/queues are independently established.

### Read-only activation dependency inspection

`scripts/settlement_producer_activation_topology.py --inspect` adds one
pure runtime metadata view to the existing financial HOLD, with no
`ExecStart`, env, command lines, wallets, request state or secret values:
all whitelisted HD/DE/shared systemd service and timer names, active state,
whether a PID exists, timer `Triggers` and `TriggeredBy`, and public unit
dependency/restart metadata. An unseen unit name is surfaced instead of
silently excluded. It intentionally omits consensus and both protected
settlement units from the candidate set, and every output remains
`cutoverAuthorized=false`, `financialIngressFenced=false`.
It returns exit 3 on an observation, exit 2 if any critical property is
missing/changed/unsafe. It discovers **only systemd system** units and
cannot prove cron, user-manager, container, external signer or API path
silence. Review named activated services; classify which can create
WOLO transfers, how they are triggered, and which upstream fences must
be verified before any side effect.

From the Mac, fetch the exact reviewed source commit into the local
*Git object database* only (do not change live Wolo checkout), then
pipe its `git show REV:scripts/settlement_producer_activation_topology.py`
to `ssh root@hel1 'python3 - --inspect'`. Never run
`systemctl stop`, `disable`, `daemon-reload`, `restart`,
a financial payout API or `git reset` from the observation report.

For the next **separately approved** scoped fence packet, include unit to
owner, entry point, timer and HTTP trigger, signer/account class, process
restart/cron/container/user-systemd path, drain method, pending request
reconciliation source and reversible resume procedure. A list of units or
restart policy is not by itself financial isolation; Wolo issue #5's six
controls and Satchel custody release remain held.


## October 20 — operator source-census / cron / user-manager / container discovery

Fresh owner-supplied Mac source census, from the certified app `main`
checkout, observed **all 21 known HD financial edges** and returned
`known_source_edges_intact=true`. This is a static source fingerprint,
not `cross_repo_runtime_attestation`, producer isolation or permission
to release. The source graph confirms GET `/`, `/api/lobby`, and
`/api/live-games` can schedule asynchronous `ensureBetMarkets`,
settlement, unmatched claims and founder-payment work. The app's
process-local single-flight and one queue preview flag cannot globally
quiesce or fence those paths. `GET /api/bets` has an explicit
`ensureMarkets:false` exception, not a guarantee for other routes.

The owner separately enumerated *names only* on the live VPS. A
per-user crontab `/var/spool/cron/crontabs/tony` exists but its
contents were NOT read. `/etc/crontab` exists and ordinary
`/etc/cron.d` and periodic run-parts directories contain named OS
jobs; names alone do not prove no WOLO side effects. Active systemd
**user** managers `user@0.service` and `user@1000.service` were
observed, but their user-level units and timers were not listed.
The Docker container running Hasura was observed;
its network, role, credentials, database write capability and restart
paths are unverified. These gaps are outside the earlier *system*
systemd topology (18 discovered units, 7 active timers).

### New auxiliary inspection contract

`scripts/settlement_auxiliary_producer_surfaces.py --inspect` is
an entirely separate **read-only** inspection from the Mac-driven SSH
pipeline. It completes the bounded discovery without printing private
material:

- Bounded `O_NOFOLLOW` reads of known root/tony/system cron files:
  only source path, scheduled job-line count and **heuristic** finance
  keyword count are emitted. No scheduled commands, tokens, passwords,
  shell parameters, env assignments, script content or user secrets.
  Keyword absence never proves a cron job harmless.
- System-level `user@*.service` discovery followed by a read-only
  `systemctl --user list-units` query through `runuser` for each
  visible account, preserving the actual UID. It emits public unit
  names and active timer names, **not** user-manager env, ExecStart,
  logs, credential or service file content. Missing or inaccessible
  user DBus creates `NOT_INSPECTED`, not empty evidence.
- Read-only `docker ps`/`podman ps` container names with their
  restart-policy boolean. It does not inspect volume mounts,
  environment, tokens, network bindings, grants, or database contents.
  A running Hasura service is treated as a *potential* financial
  writer until independently classified; absent Docker/Podman tooling
  is `ENGINE_UNAVAILABLE`, not complete host coverage.
- All financial-ready, producer-fenced and Satchel activation flags
  stay false; successful observational output exits **3** and
  critical evidence failures exit 2. It cannot start/stop systemd,
  write a DB, contact the chain, sign, retry a payment, move WOLO,
  or alter the protected 8092/8093 settlement services.
- GitHub Foundation CI explicitly runs all three safety-contract suites:
  `test_settlement_maintenance_board.py`,
  `test_settlement_producer_activation_topology.py`, and
  `test_settlement_auxiliary_producer_surfaces.py`. The previous
  workflow invoked Python contracts by individual filenames, so a
  newly added test file was not automatically covered by a green
  workflow. This permanently closes that testing omission.
- It does **not** establish host-wide `/etc/cron.*` external
  runner semantics, any unenumerated alternate crontab spool or
  out-of-band keyring, external/off-host signer or manual payouts.
  All still require separate authorization and independent proof.

Do not publish raw cron contents, Docker inspect output, env files,
process command lines, or passwords in the task tracker or chat. The
exact source-bound command may be piped from a reviewed Git commit
over SSH onto the live VPS *without changing its Wolo checkout*.
The result is one more classification packet, not authorization to
disable timers. Production cutoff still requires a specific,
independently reviewed freeze/drain/rollback scope and Wolo issue #5's
six financial-control proofs. The app's held War Satchel and Mecha
Auto Betting cannot activate from this inventory.


## October 20, 04:35 UTC — current auxiliary inventory reconciled with October 18 producer-capability assessment

The owner ran the independently reviewed auxiliary observer at source commit
`29948f5bbf992618f7d3c69dafe81993a57e08b2` over root SSH on the
production host. Receipt: `2026-10-20T04:35:27.956008+00:00`,
`AUXILIARY_FINANCIAL_SURFACES_EXIT=3`, no mutation, all finance authority
flags false.

| Auxiliary surface | Latest observed fact | Earlier source/host assessment | Release decision |
| --- | --- | --- | --- |
| Tony's crontab | 0 active job lines | Earlier inventory classified no active Wolo user cron entry | No specific cron writer identified; still not full cron/spool or manual signer exclusion |
| System cron | 9 job lines across 6 files, 0 WOLO financial keyword hits | Earlier 44-entry scheduler classification contained ordinary OS maintenance; keyword heuristic was not signer proof | Do not stop `cron.service` wholesale; keep in scope for any independently demonstrated financial side effect |
| Root user-manager | Active; `launchpadlib-cache-clean.timer` observed active | Earlier user-manager observations contained no Wolo job | No identified Wolo-specific timer; `user@0` must not be blanket stopped |
| UID 1000 user-manager | Active; same cache-clean timer | Earlier user-manager observations contained no Wolo job | No identified Wolo-specific timer; `user@1000` must not be blanket stopped |
| Hasura container | Running, restart policy disabled, no env/mount/DB privilege inspection in this receipt | Historical producer-capability document classified separate indexer / DB-writable consumer, separate DB, no identified Wolo signer or scheduled payment actions | Provisional separate-indexer exclusion **only after** current DB separation/role/capability corroboration; neither a verified Wolo signer nor provably harmless |
| Podman | Tool unavailable | No active Podman application identified | Tool absence is not comprehensive container absence |

The comprehensive earlier source-bound capability work has **already been done**
and MUST NOT be discarded or reinvented. The historical,
non-merged [producer-plan PR #43](https://github.com/Emaren/wolochain/pull/43)
on `codex/producer-maintenance-plan` contains
`docs/settlement-contracts/producer-capabilities-20261018.json`
(schema `aoe2war.wolo.producer-capability-observations.v1`,
18 October 19:07–19:15 UTC), including **17 HD system units,
2 DE app units, 44 scheduler entries, manual/external paths, queue
requirements, Hasura capability and a proposed minimum fence**.
It is dated, unmerged source/host evidence, **not a live readiness
certificate**. Reconcile today's 18-unit systemd topology and auxiliary
observations against it. Do not call the prior 19-unit inventory
`aoe2hdbets-bet-stake-reconcile-plan.service` permanently absent simply
because it did not appear in the later `systemctl list-units --all` set.

### Proposed bounded financial-maintenance scope — PLAN ONLY, NOT AN ORDER TO EXECUTE

**Financial ingress / app ownership (four original currently active services):**
`aoe2hdbets-web.service`,
`aoe2hdbets-api.service`,
`aoe2dewarwagers-web.service`,
`aoe2dewarwagers-api.service`.

All four are in the conservative **proposed app-level fence** pending
independent review of actual runtime source, startup/health, aliases and
DB/CLI signing paths. The HD web is a confirmed primary/founder payout
initiator and independent faucet/staking CLI signer. Its `GET /`,
`GET /api/lobby`, `GET /api/live-games` and detached timers can
initiate settlement; HTTP GET/read-only and the one preview flag are not
an isolation boundary. The HD API can update recipient identity and
commit/retry replay post-ingest callbacks into HD payout routes.
DE web and API remain possible financial writers/identity sources.
**Any fence therefore causes a bounded HD/DE website/API outage.**
This is not the protected Wolo consensus or 8092/8093 settlement outage.

**Scheduled reactivation / work (six timer+service pairs):**
`aoe2hdbets-bet-stake-reconcile`,
`aoe2hdbets-challenge-reconcile`,
`aoe2hdbets-replay-auto-recovery`,
`aoe2hdbets-staking-rewards`,
`aoe2hdbets-trophy-tributes`,
`aoe2war-prewarm`.
The seven-timer live observation also contains
`aoe2-wolo-transfer-heartbeat`, a chain-cache writer previously
classified *nonpaying*: keep it running if exclusively settling
payout state; determine separately if a whole-DB quiescent snapshot
requires a cache write pause. The inactive
`aoe2hdbets-bet-stake-reconcile-plan.service` was previously
classified read-only, but must be rechecked against its live unit
activation and should never be started as part of the freeze.
Existing `Wants`/`Requires` relations mean replay, reward or tribute
jobs may wake HD web; freezing the web alone cannot seal ingress.

**Keep outside app-producer fence unless separately established:**
`wolochaind-mainnet.service`, the consensus executable and canonical
RPC/REST; `wolochain-mainnet-settlement.service` and
`wolochain-founder-rewards-settlement.service` at their old binary
until a **separately approved paired code-only cutover**; root and
UID-1000 user managers; generic cron; and Hasura (only after
independently corroborating separation). Do not stop public
chain access to prevent already-signed user WalletConnect/Keplr
transactions; their late effects require finality and liability
accounting, not censorship or guessed absence.

**Out-of-band signer scope:** existing/manual signed transfers,
CLI/keyring faucet and staking sends, direct account/wallet
transactions, old accepted/unknown requests, off-host/CI,
Operator Bridge, DE signing and an optional dormant relayer
must have a named owner and a witnessed freeze/late-arrival rule
before the window. A server process list cannot revoke a wallet
signature already broadcast.

### Explicit proposed human-reviewed sequence — no mutating commands authorized

1. **Pre-window admission:** verify source and runtime for every named
   HD/DE service and timer, distinct Wolo code/consensus PID+SHA
   boundaries and actual DB/access role paths. Confirm historical
   capability classifications, real service and API aliases, systemd
   restart/activation behavior and exact four-app/six-pair scope.
   Validate separate indexer/Hasura database boundaries. Inventory
   direct/off-host signing and queues; establish a named operator,
   start/end and reversible availability impact.
2. **Pre-approve a narrow outage** specifying upstream HTTP blocking
   *and* scheduled triggers, direct signers, DB callback writers,
   in-process WarGraph leases, and all queued/accepted/uncertain
   payment sources. Record the current unit and timer states,
   restart/dependency paths, pending intents, and an exact restore
   map. **Do not infer** that `systemctl mask --runtime` can
   reliably override custom `/etc/systemd/system` units; prove
   the mechanism, its error recovery and triggers in a rehearsal
   before applying it to production.
3. **Future explicit operator-executed reversible fence:** only under
   that separately signed scope, close all newly admitted ingress
   and approved external signers; quiesce the six reviewed
   scheduled families and all four app producer processes; prove
   there are no remaining or reawakened writer PIDs, open signers,
   active callbacks, concurrent DB writers or queued future
   triggers. A process stop does not by itself certify payout
   finality. Any missing or newly discovered writer means stop
   the maintenance, preserve the HOLD and evaluate recovery.
4. **Two bounded, independently verified observations** across
   quiescence, including no additional money-moving commits or
   unreviewed database writes; classify late/mempool signed
   deposits without giving them free credit. Reconcile Wolo main
   journal's accepted 100-WOLO operation and founder claim #889's
   pending 300-WOLO attempt with *independent authenticated
   finality*. Never automatically retry UNKNOWN or double-pay.
5. **Fresh checked backups, paired code-only recovery and global
   solvency:** snapshot exactly preserved state/config and
   manifests after independent DB/chain quiescence, reproduce
   checksums off-host, independently attest *all* HD, DE,
   external, escrow, overlapping/unsettled customer liabilities
   and pending gas. Obtain separate witnessed approval for the
   `bdbce253` historical two-service code-only release, and
   preserve consensus and both original financial-state journals.
6. **Restore only when independently authorized:** verify original
   or reviewed paired runtime, PID/hash/health, unchanged
   consensus and full financial state. Restore previously active
   app services/timers **one at a time** and prove each restart
   policy, `Persistent` catch-up and queued task will not
   replay old payouts. Previously inactive one-shot services
   stay inactive until intentionally activated. Never assume
   a missing tx hash means payment was absent. Reopen HTTP
   and resume external signers only under a separate owner
   decision and rollback plan.

If any of these prerequisites remains unproved, do **not** execute
the fence or downstream cutover. Owner willingness to arrange
maintenance grants preparation, not an assertion that unresolved
funds or customer liabilities can be discarded. All existing issue
#5 six financial controls remain BLOCKED/UNKNOWN; War Satchel
and Auto Betting 8094/8095 have an additional independent Watcher
witness, funded lifecycle and custody-release gate.

**Engineering lesson:** avoid repeatedly rediscovering source
capabilities already established in an independently dated study.
Treat a past static classification, today's real-time PID/state
inspection and a protected financial authorization as **three
different evidence types**, joined by explicit references—not
interchangeable documents or a single green flag.

## October 20 — targeted 100-WOLO escrow evidence after 8 new confirmed journal rows

The owner ran the original two-root `settlement-state-evidence.py` over
root SSH. The current complete bounded **non-atomic** source-tree digest
was `2a8155ee589dce276ac93313449ad1808b5aead71d1295941e3de1eed2f36025`.
Against the previously preserved October 18 receipt, the primary
escrow `confirmed` request count grew **724 to 732** (plus eight),
and recorded requested principal increased **800 WOLO**. Total
requests grew 1566→1574 and runs 793→801. Accepted primary escrow
100-WOLO status remains one; failures remain 42; founder claim #889
remains pending; aggregate-only child **1,323,000 WOLO** remains a
prebroadcast-refused local observation without independent chain proof.

The prior Wolo configured-node bank observation for the accepted
request reported a matching transaction hash/bytes with code zero at
block 1078913, **not** independently authenticated finality. Never
retry that accepted request, the aggregate-only child or claim #889
solely because its local record is not confirmed.

The existing, source-validating journal parser now offers explicit
`--focus-escrow-100` while retaining the original default report:
- It runs all old bounded strict root and JSON parsing checks,
  Go-compatible request fingerprint validation, role and recipient
  integrity tests and duplicate receipt/tx checks first. It cannot
  turn an invalid journal into a permissive targeted report.
- It filters the **primary or founder 100-WOLO escrow** records
  carrying `accepted` or `confirmed` local status and includes
  all accepted records (with conservative limit 16). It presents
  at most **16 recently filesystem-modified confirmed records**;
  more are explicitly counted as omitted.
- Per focus record it prints only the lane, local status, principal,
  SHA256 of the durable request ID, SHA256 of the recorded JSON bytes,
  a journal-claimed **public tx hash** (no raw wallet address, private
  memo, signer key, or raw request ID), and file mtime nanoseconds
  as a **non-trusted sorting hint**.
- File mtime is not a creation date, transaction date, immutable
  receipt, or evidence that those 16 are the eight newly
  observed requests. An accepted status and a transaction hash
  **never imply safe retry or independently authenticated on-chain
  settlement**, and the whole reader is non-atomic while production
  writers remain active.
- Exit remains 3 on a valid observation, 2 on any unsafe/malformed
  journal. `chain_proof_verified=false`, `retry_authorized=false`,
  global liability upper bound null, and the financial six-control
  issue remain held. The opt-in focus flag never changes the
  behavior, custody or zero-output-credentials guarantees of the
  original default reader.

Once tests and exact-source workflow pass, the operator can run a
single restricted streaming command from the source-pinned Git object:

```sh
cd ~/projects/WoloChain-wolo-1
git fetch origin
REV=<merge-commit-from-green-held-Wolo-PR>
git cat-file -e "${REV}^{commit}" || exit 1
set -o pipefail
git show "${REV}:scripts/settlement-state-evidence.py" |
  ssh root@hel1 'python3 - --focus-escrow-100 \
    --state-root /mnt/HC_Volume_105319120/wolochain-mainnet/settlement-state \
    --state-root /mnt/HC_Volume_105319120/wolochain-mainnet/founder-rewards-settlement-state'
```

Private transaction correlation is the next authority boundary:
the output's public transaction hashes are leads requiring a pinned
independent CometBFT consensus checkpoint, cryptographic bank-event
authentication, identity/amount/account/fee attribution, and de-dup
against HD/DE/external pending obligations. Public hash comparisons
or two calls to the same node are not independence. For the eight
new journal rows, an immutable per-request before/after checkpoint
would be required to **prove** their identities; aggregate count delta
and file mtime alone cannot prove membership. Do not turn journal
recording into chain solvency, finance approval, replay, refund, or
automatic betting permission.
