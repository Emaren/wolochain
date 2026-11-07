---
id: "aoe2war.wolochain.c05-semantic-money-staking-exposure-hold"
title: "C05 Semantic Money Columns and Staking Exposure — Independent HOLD"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["developers", "operators", "ai-agents"]
source_of_truth: "git"
authority: "read-only-physical-observer-no-solvency-or-funding-authority"
reviewed_at: "2026-11-07"
review_interval_days: 7
sensitivity: "restricted"
---

# C05 Semantic Money Columns and Staking Exposure — Independent HOLD

**C05 and C04 financial HARD HOLD.** This is Session B's non-mutating accounting work, not Session A's C03 writer isolation or C06/C07 backup/recovery. Nothing here permits a funded transfer, a retry, a NOLOGIN change, service restart, consensus change, or financial data modification.

## Additional source coverage, per table

Session A's November 7 live metadata scan found **24 HD and nine DE legacy-owner-writable tables** with money or chain-related columns that the 30 HD / 11 DE name-based C03 list missed. Some are configuration, analytics or event-history; others carry staking positions, funding proofs and recorded payments. All are candidate *write-risk* surfaces, but not necessarily separate monetary debts.

The C05 offline one-height arithmetic now has exactly **52 mandatory `scope_coverage` entries**: ten original source categories, seven newly discovered explicit payout/NFT tables, two semantic money-column catalog domains, and **33 per-table named classification requirements**. Omission or incompleteness of a single per-table entry stops even a *conditional* margin. A nominal table-count, synthetic source hash or complete flag is not independent source attestation, live chain finality or release authority. The arithmetic's output remains financial HOLD.

`scripts/settlement_c05_semantic33_readonly_hold.py` has a fixed 24-HD/9-DE allowlist linked to the exact one-height accounting source. It emits bounded PostgreSQL `REPEATABLE READ READ ONLY` table-count queries, no user fields, credentials or writes. Its classifier only accepts pinned SHA256 owner-0600 JSON from private 0700 directories and returns **HOLD/exit3**. The exact SQL emitted by reviewed source matched the already-run live HD/DE count SQL bytes.

**Real November 7 independent counts:** HD 20 nonempty tables (1,600 records across all 24), four empty; DE four nonempty (16 records across all nine), five empty. HD includes 29 scheduled-match funding proof records, 37 scheduled matches, 229 staking event records, four staking positions and two marketplace payment records. These records cannot be added to obligations without economic-identity and lifecycle classification. HD and DE reads were separate, not a jointly quiesced C06 checkpoint.

M1 owner-private count receipt: `~/.cache/aoe2war/session-b-c05-semantic-33-readonly-20261107/receipt.json`, SHA256 **`e5cb9e08c628ea0cf0e6c1cea5b9dd7cc6cd6cfacdc3d5f69f2a994d4619805d`**. Recomputed source SQL SHA HD `89b54bd3e6b57a2a0028230f0a0faad8cc87a860658c00c5d44395d3b9168d22`, DE `80324ee1557a4cdb79e2c8eca9be526c698ca548ad9dbed1069b1a0a0d812cb1`, each matching the live-read SQL file byte-for-byte.

## Recorded staking principal is a new mandatory accounting input

`scripts/settlement_c05_hd_staking_readonly_hold.py` emits fixed aggregate SQL covering HD `staking_positions` and `staking_events`, not wallet addresses or personal data. Owner-0600 SHA-pinned classifier always returns HOLD.

Real live HD position snapshot:
- Three **active** staking positions record **5,356,076 WOLO** principal, zero `pending_rewards_wolo`, and **1,357,679 uWOLO** micro-reward carry; one inactive position has zero principal and 1,109 uWOLO carry.
- `staking_events` records **one** `PENDING_CHAIN` STAKE of **1,000 WOLO without a tx hash**. This is an ambiguous transfer effect and never automatically retried. The event cannot be added to active principal, or netted away, without identity/finality evidence.
- 228 `CONFIRMED`-labeled staking events carry hashes, but `CONFIRMED` is an App database label, not independent authenticated native chain finality. Historical STAKE/UNSTAKE/COMPOUND/CLAIM events are flows; do **not** add them to current position principal again.

Independent M1 owner-private physical staking receipt SHA256 **`8a4458741bcaa5ae8855e21f4ff8a4eee3955891bbd87f24e738b85ad589ae4e`**, under `~/.cache/aoe2war/session-b-c05-staking-live-20261107/receipt.json`. Staking source SHA256 `3eacbd4179611949861e30c601bd30f5d0af0ff95a3bbc166b79703c26ed76c0`, input packet SHA256 `301a9eeb0619b5e137cfb0519f08c88c9fdf72de2715ff3fdc1ebbf1f4ccb461`; classification intentionally exit3/HOLD.

## Residual release dependencies

- C03 global writer fences remain exclusively Session A, including all 54 HD / 20 DE finance-risk tables, surrounding service and owner-role paths.
- C04: 69 claimed-but-hashless historical outcomes plus any unproven native payment hashes stay quarantined. No retry or recredit.
- C05: complete nonoverlapping source liabilities, per-entity staking account mapping, independent same-height native custody/bank assets, independent consensus checkpoint and economic-ID overlap proofs still missing. The observed 5,356,076 WOLO principal is **recorded candidate exposure**, not a certified global liability upper bound.
- C06/C07 coordinated backup and exact restore remain Session A. C01 custody/reviewer, C08 notice/witness and C09 exact funded owner permit remain separately HOLD.

**Formal mainnet financial release stays HARD HOLD; no WOLO moved.**
