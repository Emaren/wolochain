---
id: "aoe2war.wolochain.c05-bounty-gift-null-valuation-hold"
title: "C05 pending bounty gift — missing reward valuation"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war", "aoe2dewarwagers"]
audience: ["developers", "operators", "ai-agents"]
source_of_truth: "git"
authority: "source-only-financial-hold-not-a-funding-or-replay-permit"
reviewed_at: "2026-11-08"
review_interval_days: 7
sensitivity: "restricted"
---

# C05 pending bounty gift — missing reward valuation

## Physical anomaly and exact interpretation

During a read-only HD/DE census on 2026-11-08 UTC, aoe2hd_db contained
two pending WOLO gifts with combined recorded amount **100,100 WOLO**.
One pending gift nominal **100,000 WOLO** referenced an existing available
public.bounty_opportunities row. Its nullable reward_wolo field was
**NULL**. The source reward-matching count was zero, but this was NOT
evidence of a known non-null reward unequal to 100,000.

aoe2de_db had zero matching pending WOLO gifts. Nine HD NFT custody-seat
records existed, but do not constitute independently verified on-chain
ownership. Same-height bank custody and liability/nonoverlap remain absent.

Private HD/DE source census and NULL-specific SHA-256 receipts are in the
canonical Chain [release HOLD register](https://github.com/Emaren/wolochain/issues/5).
Never publish recipient identities, gift notes, wallet addresses, private
event IDs or database records in this document.

## Engineering change: source-only, no execution authority

The source settlement_c05_gifts_nft_full_catalog_hold.py v2 preserves
the prior 190-HD/52-DE full catalog inventory, bounded READ ONLY SQL,
strict SHA-bound private evidence and unconditional financial HOLD.

It separately counts mutually exclusive states for linked pending gifts:

- **Reward matched:** non-null source reward equals recorded gift amount
- **Reward NULL:** no source valuation, with sum of the unpriced gift nominal
- **Reward conflict:** non-null source reward differs from gift amount

The classifier requires these category counts to equal the total
linked-source count; refuses inconsistent amounts, duplicate records,
schema drift, unauthenticated source files, altered authority flags,
and unsourced external chain or custody claims.

A NULL source reward is NOT automatically an authentic 100,000-WOLO
award, an additional liability, a duplicate, a discharge or a safely
retryable payout. None is inferable from the gift note alone.

## Independent financial closure

Authenticate original bounty valuation and intended entitlement
through an independently controlled economic event record. Reconcile
the pending gift against bounty_events, pending_wolo_claims,
staking/rewards and authenticated bank effects to establish economic
disjointness. All ambiguous claims remain NO REPLAY / NO PAYOUT.

Actual C03 global writer containment, coherent C06 encrypted capture,
independent C07 same-backup restore, C05 same-height bank/reserve proof,
ratified C08 authority and human-confirmed C09 exact payment permission
remain separate hard requirements.

This source/document review is NOT an independent natural-human
signature and did not modify production financial data or authority.
