---
id: "aoe2war.wolochain.production-p1-and-authority-gates-20261024"
title: "Production P1 source integrity, writer evidence, five-person authority and bounded recovery proposal — 2026-10-24"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war","aoe2dewarwagers"]
audience: ["operators","developers","ai-agents"]
source_of_truth: "git"
authority: "non-authorizing-financial-human-signature-review"
reviewed_at: "2026-10-24"
review_interval_days: 14
sensitivity: "internal"
---

# Production P1 source integrity, writer evidence, five-person authority and bounded recovery proposal

**NONAUTHORIZING.** This document is a draft evidence contract, NOT a maintenance permit, attestation, five-human signature, or approved financial-source change. Original Wolo #100 source and 8092/8093/consensus are untouched. Never merge this review branch into app production. Never ask an operator to format, mount, restart, fence, replay, sign, transfer or restore in order to test this document.

## 1. Independent P1 disposition: historical binary identity is known; historical signed build chain is not

At 2026-10-24 17:37 UTC, owner read-only evidence proved:
- **Consensus** `/usr/local/bin/wolochaind-mainnet-node-prewartrophy`, SHA256 `4b77f622191db7550cb87cafb8f1886a0aadebee3eb6565f9f90036f809e61d3`, embedded source `d3bd62414a047a492a3814b7d3baa2717d64db2e`, `vcs.modified=true`, compiled June 5. Intentional pre-War-Trophy override; source SHA alone cannot reconstruct unknown modified files. Do not replace this binary.
- **Both 8092/8093 settlements** `/usr/local/bin/wolochaind-mainnet`, SHA256 `040126a2884946caf1651a50b7d8115c5a6fb2d5aa94fcbbe150694602d451a5`, embedded `78c25985420ee41a6678c42fab8ea8d6c3b1b519`, `vcs.modified=false`, compiled Oct 1. The Go embedded revision is metadata, not an independent signed compilation/deployment attestation.
- **DocsV2 comparison** `78c25985...` → `4ce11c4965da64e3d4dee6a8681b6198e1aba1eb`: 171 commits, 61 files, custody-sensitive delta. Historical GitHub CI/release runs 36930772811/36930772807 succeeded but return no retained run artifacts: release workflow includes conditional `GOFLAGS=-buildvcs=false`, so green source CI cannot prove these exact installed binaries. Root-private Oct14 historical snapshot yielded no filename matches for narrowly searched signed provenance names within depth 3; no assertion that other evidence is absent. Historical October binary hashes repeated in Wolo issue #5.

### Exact high-risk Go behavior delta

| Operation | Running settlement `78c25985...` | Newer `4ce11c4...` | P1 disposition requirement |
|---|---|---|---|
| Prebroadcast | Bank `send` called before durable stored result | `writeSettlementPrebroadcastHold` persists ambiguous nonretryable request before signer | Independently enumerate historical request IDs, in-flight/restarted sends, signer sequence, and chain effects BEFORE adopting updated journal semantics |
| Unknown broadcast | Earlier result/retry classification may not preserve unknown effect safely | `preserveUnresolvedSettlementBroadcast` retains nonretryable unknown result | Do not retry unknown; independently reconcile original tx bytes, chain membership, sender and bank effects |
| Confirmation | Old lookup/wait permits weaker payment-context association | Requires exact expected signer/recipient/denom/amount/memo and uniqueness/coherent transfer events | Independent trusted consensus and bank-effect witness still missing; do not equate a node RPC response with final settlement |
| Receipt ownership | Historical request storage lacks newer tx-hash/transfer-index ownership registry | New receipt registry checks claimed ownership and historical conflicts | Prove legacy migration/reconciliation is replay-free; no heuristic backfill from duplicate hashes |
| Consensus | Deliberately modified and 25 commits earlier than settlement | No permission to synchronize | Freeze binary and preserve original node state and signer custody while comparing independently |

**Disposition as of this document: P1 PARTIALLY CHARACTERIZED, STILL OPEN.** Acceptable *review* evidence: original separately controlled build recipe/toolchain, exact source and dirty patch hash for modified consensus, chain-of-custody receipts binding installed SHA256 to original build output and deployer, full raw-journal and separate chain-history reconciliation, reviewer digest from Chain Reviewer and independent Source Reviewer. If irrecoverable, record `historical_build_provenance=UNRECOVERABLE` rather than inventing a reproducible hash. A compensating HOLD may accept old bits *for temporary non-writing observation only*, never replace source integrity as satisfied for a financial write. `p1_resolved` remains false and admission stays blocked pending independently accepted source disposition. No 171-commit blanket upgrade.

## 2. Writer-authority inventory — twelve finite categories

Each category below requires an *actual capable principal*, account/credential owner and a **different** independent reviewer. Status is UNKNOWN/BLOCKED until nonsecret observation, off-host attestation and no-run enforcement are independently witnessed. Systemd's 18 units are only a candidate scope; they have NOT been production-fenced.

| Category key | Concrete capability that must be excluded | Minimum independent proof |
|---|---|---|
| `hd_web_api` | HD web/API data writes / bank requests | service, DB roles, active session cgroups, ingress and credential revocation/no-run |
| `de_web_api` | DE web/API equivalent | same plus DE-specific manual endpoints |
| `seven_timer_service_pairs` | seven timers + seven oneshot commands (18 units with four apps) | effective systemd activation guards, jobs, cgroups, timer state |
| `postgres_dba` | postgres superuser, ownership, manual SQL, restore/migration | independent DBA permission/custody and no-SQL capability under approved window |
| `manual_sql_and_ssh` | privileged SSH/sudo and ad hoc SQL scripts | named operator accounts, authorized keys, sudo policy, scheduled jobs; no secret material published |
| `cron_and_user_systemd` | root/user crontabs, user timers and scripts outside 18 units | root/user scheduler enumeration and owner exclusion |
| `ci_and_deployment` | GitHub runners, deploy SSH tokens, secrets and webhook writers | protected environments, branch rules, active runs and independent deploy credential suspension |
| `settlement_8092_8093_bearers` | both legacy settlement API bearer credentials and keyrings | independent bearer holder list, wallet signer access test without signing, fail-safe containment |
| `offhost_wallet_and_chain_signers` | off-host key custodians, relayers, RPC signing capability | independently signed custody/no-broadcast exclusion from every possible signer |
| `auxiliary_settlement_and_indexers` | reward, transfer, reconciliation, indexer/script processes | process/scheduler/credential owner survey; no duplicate effect processors |
| `hasura_secondary_targets` | Hasura routes including tokenchain_callisto and any secondary DB | separately verify remote DB/role reachability, permissions and service principals |
| `legacy_and_de_manual_executors` | manually invoked HD/DE legacy executables and replay paths | inventory scripts/cron/manual keys and independent isolated replay prohibition |

The controller's **new gate** requires a pre-existing canonical root-private `writer-coverage/<category>.json` for each of these exact categories and hash equality to its entry in `independent-writer-coverage.json`. Required closed fields: `schema="wolo.financial-writer-coverage-evidence.v1"`, `category`, `owner_id`, `independent_reviewer_id`, `excluded_during_window=true`, `scope_sha256`, `source_commit`, `not_before`, `expires_at`, `observation_sha256`, `independent_witness_sha256`. An absent, changed, uncanonical, wrong source, missing witness digest or wrong-time-window file blocks *before nonce consumption*. A sha-shaped field alone no longer qualifies. Each independent reviewer must actually attest external evidence, including what privilege was disabled and how it was verified: **the fields themselves cannot authenticate a reviewer**, cannot neutralize a DBA/root attacker and cannot replace off-host custody or five real signed phase approvals. Synthetic CI fixture evidence is not human evidence.

The previously tested founder `aoe2war_founder_audit_ro` is NOLOGIN, two readable/zero writable public relations, but that says nothing about DBA/root/sudo, settlement keyring access or off-host writers. RLS is off on the two tables, so do not publish raw beneficiary records.

## 3. Genuine five-human ceremony / external nonce

Exactly five distinct natural persons must independently enroll under separately checked identity and sole-key custody: **Owner** verifies commercial phase scope and explicitly forbids funding; **Operator** verifies 18-unit scope, all 12 independent writer exclusions and existing scratch identity; **Chain Reviewer** independently authenticates consensus/8092/8093 custody, effects, height/finality, unresolved broadcast and signer state; **Finance Reviewer** witnesses complete HD+DE/external liabilities and pending obligations; **Recovery Witness** independently authenticates durable capture/restore lineage, storage bounds, independent nonce receipts and retained HOLD. Each controls a different private Ed25519 key. Real out-of-band enrollment custodian registers five separate public keys, roles, key IDs, human proof-of-possession and UTC expiry. Registry version, revocation epochs and exact source/host/source-disposition digests must be independently pinned. No project default `None` trust anchor is an enrollment. Do not upload or log private keys. CI synthetic keys do NOT count.

The independently hosted nonce service MUST live in a different administrative/security domain from hel1. Require TLS authenticated controller identity, strict request schema (nonce, phase, SHA256 of canonical signed packet, exact tool/source/scope/host/registry, expiry and revocation epoch), transactional uniqueness constraint on nonce across ALL phases/hosts, signed independently verifiable response with previous/current monotonic counter, durable fsync/committed WAL and off-host immutable checkpoint. Verify issuance and revocation epochs from the independent custodian; on network error, timeout, duplicate, rollback, restarted old state, missing signature or wrong identity **REFUSE**. Test two concurrent contenders, crash before/after commit, host-root rollback, replay from different host and revoked key. PR100 currently uses a production nonce consumer that **always refuses**; no real service, trust enrollment or online adapter exists.

Each phase demands five fresh signatures and a uniquely consumed nonce. LIVE_CAPTURE (≤30 min) only may attempt a writer HOLD and bounded archive under its own signed permit; OFFLINE_VERIFY (separate window, ≤4 hours) only uses an already sealed archive with the old HOLD retained; RESUME remains separately unimplemented and **unconditionally refused**. Success at an earlier phase never authorizes the next.

## 4. Production-size budget: independently reviewable numerical proposal, NOT signed

Read-only owner observations October 24: HD PostgreSQL 16.15 `10,691,197,975` bytes, 190 selected tables, 937 indexes; DE PostgreSQL 16.15 `15,301,655` bytes, 52 tables, 235 indexes; combined `10,706,499,630` bytes (**9.9712 GiB**). These were separate read-only DB transactions, not a consistent cross-DB financial snapshot. Existing `/var/lib/wolo-financial-restore/bounded` exact kernel loop4↔preallocated 40GiB backing and `rw,nosuid,nodev,noexec` verified, bounded free `39,792,615,424` bytes, root free `73,142,366,208` bytes. Required root reserve `8 GiB`, capacity ratio `2 × signed max_total_bytes`.

**DRAFT option for five humans to reject or approve**: signed `max_total_bytes=15,032,385,536` bytes (**14 GiB**). Required isolated free under 2× = `30,064,771,072` bytes (**28 GiB**); observed surplus after that requirement = `9,727,844,352` bytes (**9.0598 GiB**). Proposed budget is **40.4% above** observed combined physical database bytes; it is NOT a measured pg_dump size, full restored PostgreSQL peak, archive checksum or signed permit. The controller can refuse if refreshed observed free bytes, actual archive size, PG version, image digest, cleanup or approved period fail. Finance Reviewer and Recovery Witness must confirm that final *real* financial table census, indexes, sequences, constraints, schema versions and independent bank effects can fit the approved budget before anyone authorizes LIVE_CAPTURE.

**Source-bound proposal commitment input** (no fabricated human signatures):
```json
{
  "schema": "wolo.financial-recovery-budget-proposal.v1",
  "status": "PROPOSED_NONAUTHORIZING",
  "source_base_commit": "5ba96f3f49baad58686a9679578d6c372efebda0",
  "postgres_major": 16,
  "hd_database_bytes_observed": 10691197975,
  "de_database_bytes_observed": 15301655,
  "bounded_available_bytes_observed": 39792615424,
  "root_available_bytes_observed": 73142366208,
  "capacity_factor": 2,
  "proposed_max_total_bytes": 15032385536,
  "actual_capture_hash_sha256": null,
  "actual_restore_hash_sha256": null,
  "five_human_signatures_present": false,
  "approved_for_live_capture": false,
  "approved_for_offline_restore": false,
  "approved_for_resume": false
}
```

This input MUST be independently reviewed and included through the existing phase/request/procedure commitment mechanism; it does not introduce a new permit format or itself meet the verifier. Before real LIVE_CAPTURE require genuine enrollment, independent durable nonce, resolved code/source P1, *all* 12 categories with real independently verified exclusions and measured fresh capacity. On any exception retain HOLD. A separately signed OFFLINE_VERIFY then restores **full actual** HD+DE in existing isolated ext4, network disabled, using only approved fixed PostgreSQL image digest and sealed original archive; independently compare complete enumerated financial tables, canonical rows/digests, constraints, sequences, exact indexes/validity, ownership/privileges and chain effects, and attest cleanup. NO live backup/restore or temporary permissions changes authorized by this proposal.

## 5. Website-only release decision to Session 1

**No independent website production waiver yet.** The code-only website source/review gate can progress separately, but source-only review exit-2 nonauthorization does NOT satisfy the real app release controller or resolve the Wolo P1. Protected funds, financial DB writes, War Satchel/Mecha automations, settlement 8092/8093 signing and chain consensus remain specifically excluded. Session 1 must obtain independent nonfunded source/DB and release rollback proof and an actually approved website-specific controller route that cannot trigger money, wallet, watcher payout or chain financial events. No automatic waiver or production deploy claimed by this Wolo document.

## Shortest real-human order

1. Build/deployment custodian + independent chain/source reviewers produce contemporaneous exact binary provenance or honestly mark it unrecoverable and retain P1 with non-writing containment; no install.
2. Owner names the other four distinct humans and an independent public-key enrollment custodian; five keys and revocation custody genuinely established.
3. Independent nonce/witness custodian deploys *off-host* transactional monotonic service with crash/replay/rollback tests; reviews signed witness protocol and integrates into controller on a new reviewed branch.
4. Each writer owner plus a different independent reviewer establishes actual no-run capability evidence in all 12 categories, not merely in the 18 service units; complete signed-root-private files.
5. Five humans review the 14GiB **proposal**, fresh physical free space, source/build identity and all original obligations; only if P1 and writers are resolved issue genuine fresh LIVE_CAPTURE approval.
6. Separate five signatures and fresh nonce enable independent OFFLINE_VERIFY and complete production-size restore; only a separately reviewed RESUME executor and genuine finance/chain bank solvency may ever move the final GO decision.

**CURRENT STATE: engineering candidate only, operational financial HOLD.** No historical human enrollment, real nonce service, complete writer exclusion, signed recovery budget, production-size capture/restore, full bank solvency or safe RESUME shown.
