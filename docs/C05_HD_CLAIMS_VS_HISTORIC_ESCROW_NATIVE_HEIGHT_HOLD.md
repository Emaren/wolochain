---
id: "aoe2war.wolochain.c05-hd-claim-nominal-legacy-escrow-single-height-held"
title: "C04/C05 Read-Only HD Claim Nominal Versus Historical Escrow: Real Native Height and Economic HOLD"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2hdbets"]
audience: ["operators", "developers", "financial-reviewers", "ai-agents"]
source_of_truth: "git"
authority: "physical-aggregate-reconciliation-observation-not-financial-solvency-or-release"
reviewed_at: "2026-11-08"
review_interval_days: 7
sensitivity: "restricted"
---

# C04/C05 Read-Only HD Claim Nominal Versus Historical Escrow: Real Native Height and Economic HOLD

## Actual business decision gap

The chain must never replay an ambiguous payment or declare solvency by comparing one historical wallet balance to database status counts. The existing owner-authorized WoloChain holds include 69 claimed-but-hashless records and 948 pending HD claims, plus many other potentially overlapping financial liability surfaces (wager principal, DE, staking, founder requests, NFT/bounty and historical duplicates). The historical settlement escrow wallet is only a dated source label; its on-chain balance neither proves signer possession nor all spendable reserves.

The bounded, read-only `scripts/settlement_c05_claimed_pending_vs_legacy_escrow_hold.py` physically requires actual HEL1 root observation of the real running WoloChain binary PID1009, `wolo-1` Comet RPC status not catching up, real block hash at an exact local height, and the native binary's `query bank balances` at **that same pinned height**. This is not independent external chain finality. The HD counterpart is a `BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY; SET LOCAL statement_timeout='9000ms'; ... ROLLBACK` query on `aoe2hd_db`, comparing only distinct claim IDs and observed status categories. No arbitrary wallet, chain height, DB, transaction, SQL statement or age/owner key may be supplied by a caller.

The source fails closed if the previously enumerated HD claims drift from exactly 69 claimed-but-hashless / 120,443 WOLO and 948 pending / 993,289 WOLO; if native bank response gains an unreviewed denom; if the trusted running node/home/height/network changes; if receipt paths exist; or if any participant returns malformed output. This is a **freshness alarm**, not a control that freezes all financial claims.

## Physical HEL1 evidence — November 8, 2026

The initial read-only source execution on HEL1 completed, exit **3 intentional financial HOLD**, and root-only mode0700/0600 receipt was saved without logging user wallets, claim IDs, transaction hashes, DB credentials or private keys.

- Native `wolo-1` bank height: **2,878,675**.
- Historical mainnet settlement escrow public wallet: `wolo1zygwt232ymc4h2g52yvkntffhmd5alx2kglw7p`; actual native balance **826,713.5 WOLO** (`826713500000 uwolo`).
- HD `claimed` without payout hash: **69**, recorded **120,443 WOLO**.
- HD `pending`: **948**, recorded **993,289 WOLO**.
- Sum of *these two disjoint current database categories* only: **1,113,732 WOLO**.
- Arithmetic one-wallet minus gross recorded nominal: **−287,018.5 WOLO** (`-287018500000 uwolo`).
- Root-private physical receipt `/root/aoe2war-c05-hd-escrow-comparison-20261108/claims-vs-historic-escrow-single-height.json` SHA256 **`b225bc3fd77f9840d734ec1baba0a2094b023348059f97525991bc43764daa45`**. Initial executed source SHA256 `a5c4ab2a6aa2e518576b4b0306eec94edc1cd80b9e98d32743eb2cd5efe59d51`; the later source-only change to use the effective UID in isolated test-receipt handling does not change the database or native chain query.

**Interpretation: not insolvency proof.** The 69 missing-hash claimed records could be paid, unpaid, or partially paid; unknown states are quarantined, not blindly counted as new obligations or marked zero. The 948 pending claim records may have overlaps with already-proven stakes or other producer records. This one wallet does not comprise complete WOLO holdings or bank reserves, and chain height vs PostgreSQL repeatable-read snapshot is not atomic. The difference is a concrete **reserve-review reconciliation target**, never an independently certified solvency shortfall.

## Controls and next admissible step

The source's 13 dedicated adversarial unit tests check exact two categories/counts/IDs, malformed/duplicate/status changes, foreign bank denominations, denial of dynamic RPC/send/broadcast, no financial service commands, source-wallet pinning, offline 0700/0600 private exclusive receipt, symlink refusal, financial HOLD flags and explicit SQL rollback. It is registered in the canonical Foundation CI workflow with generated docs register.

Before C04 can be accepted, each claimed-nohash payout requires independently authenticated chain execution identity or a conservatively approved quarantine with **no replay**. Before C05 can be accepted, a complete collision-free HD/DE obligation inventory and authenticated custodian-held reserve inventory at a consistent chain height must be reconciled; fresh custody proof, fee cushion and separate reviewer are mandatory. Do not add the 69 nominal automatically to wager principal, claim customer insolvency or initiate a treasury top-up merely on this comparison. Any funded canary remains behind separately current C03/C06/C07/C08/C09 permission gates. No finance runtime, DB row, wallet or Wolo transfer was changed by this observation.
