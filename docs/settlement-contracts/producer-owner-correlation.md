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

