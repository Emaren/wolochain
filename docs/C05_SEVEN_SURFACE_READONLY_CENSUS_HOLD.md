---
id: "aoe2war.wolochain.c05-seven-surface-readonly-census-hold"
title: "C05 Expanded Payout and NFT-Transfer Surface Census — Read-Only HOLD"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["developers", "operators", "ai-agents"]
source_of_truth: "git"
authority: "read-only-source-and-physical-financial-hold-not-c03-maintenance-or-funded-permit"
reviewed_at: "2026-11-07"
review_interval_days: 7
sensitivity: "restricted"
---

# C05 Expanded Payout and NFT-Transfer Surface Census — Read-Only HOLD

**Status: HARD HOLD.** This observer does not authorize banking, service activation, database migration, retry, refund, custody use or a mainnet transfer. No source-positive status, nominal amount, receipt hash or local test is chain finality or solvency evidence.

## Why the expanded scope is required

Session A's independent C03 inventory found seven payout / transfer tables **outside** the previous 24 HD / 10 DE owner migration rehearsal. All seven have real financial, asset, recipient, payout-status, hash, or retry columns. Session A owns expanding and deploying the C03 writer fence; this independent C04/C05 source audit does **not** alter the owner-migration plan.

Source: `scripts/settlement_c05_seven_surface_readonly_hold.py`. The fixed SQL whitelist covers six HD objects and one DE object, uses `BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY` and a 9-second query statement bound, and outputs only aggregate counts, statuses, hash-presence and nominal amounts. These HD and DE database observations are **not mutually atomic**. The classification CLI verifies owner-only 0700 private directories, 0600 exact file modes, SHA256-pinned input bytes, exact tables/units, canonical nonnegative counts, bucket coverage and no mismatched hash totals. It **always** returns HOLD (exit 3), even if no rows exist.

## Real November 7 observation (not a complete liability inventory)

| Surface | Database | Rows | Meaning still unresolved |
|---|---|---:|---|
| `bounty_payouts` | HD | 0 | Must stay inside protected future writer scope |
| `championship_transfer_groups` | HD | 8 | `changed:blocked`, frozen_bounty_wolo total 0, no linked bounty payout |
| `championship_transfer_seats` | HD | 9 | `blocked`, no tx hashes or proof; NFT obligations require separate adjudication |
| `trophy_payout_allocations` | HD | 0 | `amount_uwolo` unit **not** `amount_wolo` |
| `trophy_payouts` | HD | 512 | 340 `paid`, nominal 3850 WOLO, 340 hash-present; 172 `dry_run`, nominal 1935 WOLO, zero hash-present |
| `war_graph_payout_events` | HD | 0 | Events do **not** independently carry an amount |
| `trophy_payouts` | DE | 0 | Must still be protected before future writes |

Important source nuance: App `lib/trophies/service.ts` includes `dry_run` among **executable** daily tribute statuses, contingent on other gates. Therefore the 172 nominal 1935 WOLO dry-run records cannot be automatically dismissed as non-liabilities, counted as confirmed debts or sent; they require custody, eligibility, reconciliation, and overlap adjudication. The 340 `paid` records likewise have transaction hashes but **no independent authenticated native chain finality established by this census**.

Additional separately executed **HD-only READ ONLY** hash-overlap check: all 340 paid-labeled trophy rows have 340 distinct nonempty transaction hashes; none match any nonempty `pending_wolo_claims.payout_tx_hash` in that snapshot. No paid row is missing `paid_at`, and none of 172 dry-run rows carries a paid timestamp or transaction hash. This is **syntactic consistency and observed zero hash overlap**, not independent native-chain proof, not a complete identity overlap map, and not a proof of 340 disjoint obligations.

These nominal amounts are not summed into prior C04 claims or active wager totals without an independently proved economic-ID overlap map. Distinct `amount_uwolo`, `amount_wolo`, NFT-seat state and event counts are not interchangeable.

## Source-level C05 arithmetic hard gate

The existing offline one-height arithmetic was **also corrected**, not just supplemented with an observer. Its exact `scope_coverage` contract now requires **19** individually identified complete source scopes (the original ten, seven newly identified payout/NFT/transfer surfaces, and two semantic money-column catalog/classification domains for the further 24 HD + nine DE owner-writable relations found by Session A on November 7). Old ten- or 17-scope candidate evidence receives `UNSCOPED_FINANCIAL_OWNERS`; a single missing, incomplete, or unhashed new surface prevents a conditional recorded reserve or margin. Synthetic tests deliberately verify all seven table omissions and both monetary-catalog-domain omission denials and the negative-margin condition. The engine still always exits HOLD and never authenticates a balance, finality, global liability ceiling, independent reviewer, custody or owner permit.

## Authentic independent capture (November 7, 2026 UTC)

Two separate live HD/DE transactions were executed through source-emitted SQL and saved in private owner 0700/0600 M1 files. The source exact HEAD `a90499e100e0227d4c5134d53cccf593b857a015`, source script SHA256 `7bf33af9d2c9c0d52fd7b9fb3af590fc1ce0331ec4c1e8fa546af82c4e92876f`, authentic HD source-input SHA256 `c7a4518fdc418f6d936bd175e1c1886173a9e6fd22a77f43b7fe484962a1a552`, and DE input SHA256 `72c02998b11fe427783be72b85b920c8526186e5aa6927609339c3c43ab73535` were independently reclassified with intentional `HOLD`/exit 3.

Source-bound M1 mode 0600 receipt: `~/.cache/aoe2war/session-b-c05-seven-surface-live-20261107/independent-physical-receipt-sourcebound-v2.json`; SHA256 **`22f07db80df542dea704fe55789c76c2f6ba0c5c9be669e4e7d9521dae0e5382`**. Zero live SQL writes; no services, funds, custody or financial gates changed. These source observations do not establish a cross-database atomic snapshot.

## Qualification and dependencies

Run isolated tests with `python3 -B -m unittest discover -s tests -p 'test_settlement_c05_seven_surface_readonly_hold.py' -q`. Emit read-only fixed HD and DE SQL separately, execute against live PostgreSQL only through an operator's bounded `psql -X -qAt -v ON_ERROR_STOP=1` read-only transaction, store JSON separately under owner-private 0700 / 0600 on the M1, and classify using their exact SHA256. These two reads are **not** a C06 coordinated backup nor a C07 restore.

C04 remains HOLD on the original 69 claimed-but-hashless historical payout outcomes and these additional unverified paid labels. C05 remains HOLD until a source-sealed complete nonoverlapping HD/DE/founder/journal/Satchel/NFT/escrow/refund/staking/unknown inventory and independent same-height authenticated native bank proofs can be reconciled. C03 live owner-role and service isolation, C06 backup, C07 recovery and all production PG writes belong only to Session A. C08 governance and C09 transaction-specific owner authority remain separate.

**Formal release 10/19. No WOLO moved.**
