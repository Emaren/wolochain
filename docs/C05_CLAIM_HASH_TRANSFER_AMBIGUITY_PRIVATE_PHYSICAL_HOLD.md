---
id: "aoe2war.wolochain.c05-private-claimed-hash-ambiguity-physical-hold"
title: "C05 Exact Claim-to-Transfer Ambiguity Manifest: Private Physical HOLD"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["operators", "developers", "financial-reviewers", "ai-agents"]
source_of_truth: "git"
authority: "root-private-repeatable-read-historical-claim-attribution-never-payment-or-reserve-admission"
reviewed_at: "2026-11-09"
review_interval_days: 7
sensitivity: "restricted"
---

# C05 Exact Claim-to-Transfer Ambiguity Manifest

**Formal C05 is OPEN.** This is an actual source-pinned historical database investigation, never a proof of signed chain inclusion, a waiver of liability, reserve admission, or authority to repay.

## Physical HEL1 production execution, November 9, 2026

The reviewed script is scripts/settlement_c05_claim_hash_collision_manifest_hold.py. It performs one PG16 REPEATABLE READ READ ONLY snapshot of aoe2hd_db and reads the full pending_wolo_claims and wolo_indexed_transfers tables. It has no SQL write, wallet, transfer, payout, or reserve-admission path; it sets default_transaction_read_only=on, enforces statement and lock timeouts, and restricts the production DB target.

Verified source SHA256:
42c7af6f65e628566ad5031f3c45d3ff0f9000f13d16bb38b7853b3bae7fa9a1

Physical root-only evidence directory, mode0700:
/root/aoe2war-c05-claim-hash-manifest-20261109

Private individual-claim attribution manifest, mode0600, SHA256:
38ae54df7233c4b4d0c2e3ded1ff6f1310243fcde4a2f65de764b071adccfb3d

Aggregate noncrediting HOLD receipt, mode0600, SHA256:
16641fa580b76211fcbb41379031232cc1e98809e733879508d4ace0781ed20a

Canonical full input snapshot SHA256:
21078690c1ee88ba92cc197ae4cf29a1e7a9bd4fddf26a89837a3c6ee5ef9f96

The classifier retained all **2,453 historical claims**, including 1,312 claimed, 948 pending, and 193 rescinded, and considered all **4,300 indexed native transfers** (4,300 unique transaction hashes). There were 1,167 distinct claimed hashes.

The actual result classes:

- **1,017 indexed single-claim amount matches:** arithmetic match, NOT signed payment finality.
- **97 hashes / 108 claims / nominal 2,146,500 WOLO:** missing from local transfer index. A missing index is NOT proof of nonpayment.
- **31 hashes / 62 claims:** same apparent source-based economic tuple, repeated-hash excess of 2,252 WOLO. Must not automatically delete, credit, or repay.
- **22 hashes / 56 claims:** distinct economic tuples reuse a hash, with 29,347 WOLO arithmetic discrepancy to one indexed transfer. Individual attribution REQUIRED.
- **69 claimed records without payout hash:** separate unknown cohort; cannot be marked paid or unpaid automatically.
- **Rescinded claim 822 still carries a payout hash:** explicit exceptional source and financial adjustment review required.

The economic comparison tuple is claim_kind, claimed_by_user_id, source_market_id, source_game_stats_id, source_founder_bonus_id and amount_wolo. This is an *investigation key*, not proof of legal/economic obligation equivalence. All manifest rows explicitly have payment_proven=false, eligible_to_repay=false and solvency_admitted=false. No reserve figures are admitted.

**There are 158 ambiguous claimed hash groups** (97 index missing plus 31 apparently identical-source plus 22 distinct-source); these counts are NOT additive to verified unpaid debt. Existing C04 quarantine and the C05 complete liability envelope remain binding.

## Privacy, evidence identity and testing

Private claim IDs, hash IDs and economic sources are in the HEL1 root-owned mode0600 manifest only; DO NOT paste them into public GitHub, CI logs, App APIs or unapproved remote storage. Only aggregate receipts and cryptographic hashes belong in the PR.

The script only creates a fresh root directory and files with exclusive O_EXCL, O_NOFOLLOW semantics. It never overwrites a previous sealed evidence package; a repeated run reports HOLD. Reproducible tests run with in-memory fixtures without accessing PostgreSQL.

Offline test command: python3 -m unittest discover -s tests -p 'test_settlement_c05_claim_hash_collision_manifest_hold.py' -v

**10/10 tests passed** covering exact arithmetic without payment authority, apparent identical and distinct economic sources, batch amount ambiguity, missing index, wrong denomination, duplicated transfer index, absent source provenance, rescinded/pending preservation, malformed hashes, duplicate IDs, and cryptographic canonicalization.

## Session A C05 admission work remaining

1. Bind each historical claim to an original economic operation, authenticated native bank event, actual receiver, amount, and independently verified inclusion/commit proof. A local index match alone is insufficient.
2. Independently adjudicate the 22 distinct-economic-source reused hash groups and all index-missing groups, then validate the 31 apparently duplicated economic-source groups without silently erasing or repaying them.
3. Retain claim 822 and every C04 UNKNOWN outcome conservatively until exact non-additive liability and adjustment evidence is accepted.
4. Sign the completed, disjoint liability manifest and independently verify actual *pledged, unencumbered* Satchel collateral at one fixed chain height, with proper fee and reserve margin.
5. Keep C01 keys, C02 native financial listeners and C09 funded canary held until all their separate predicates pass.

**Physically PASS:** exact source-matched READ ONLY classifier, private sealed artifact, all-claim preservation, ten adversarial tests.

**Still HOLD:** individual financial finality; signed complete liability manifest; admitted reserve collateral; C05 gate closure; funded transfers.

