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

## November 8 — separate assignment and publication boundary

A further live HD REPEATABLE READ READ ONLY aggregate check of the
historical pending 100,000-WOLO gift established:

- Exactly one pending gift at that nominal value linked to exactly
  one existing opportunity via the gift's bounty-reference note.
- The opportunity's assigned_user_id is NULL; there is no assigned
  bounty beneficiary in the source record.
- The opportunity's reward_wolo is NULL; there is no approved
  numeric reward valuation in the source record.
- The opportunity's published_at is NULL; it lacks a recorded
  publication timestamp and its status remains available.
- There are zero matching bounty_events and no event payment hash.

These counts are source-data observations, NOT positive or negative
proof of a final offchain agreement, entitlement or bank payout.
The gift row may represent a proposed obligation, a draft or another
historical intention. Never infer cancellation, payment or retry.

The second source-only observer
scripts/settlement_c05_bounty_assignment_publication_hold.py,
SHA256
8d31a131c6e8b266c213666825dc608874020d88dca461e24fd346c57493d1b9,
uses bounded READ ONLY HD SQL and private root0600 SHA-pinned evidence.
It partitions linked source assignees, reward valuations, publication
state, availability and bounty event hashes. It rejects forged source
entitlement, fabricated finality, new or altered assignee, numeric
reward, publication, changed source status or any newly linked event.
It reports only aggregate counts; no gift, user, wallet, transaction,
opportunity ID or private note is printed by the classifier.

Twenty-one new adversarial tests passed, along with the 34 earlier
C05 null-reward regression tests. This observer's exact source has
not yet received a separate physical HEL1 acceptance receipt; the
database aggregate check above was a separate read-only query.
Even an exact future source match returns C05 HARD HOLD, never
gift acceptance, a payout, a refund or a wallet transaction.

Next evidence must include signed authority for the correct
recipient and approved reward, independently established
bounty-completion/eligibility source, unique economic obligation
identity, chain custody/finality and independently verified reserves.
C05 remains HARD HOLD regardless of the available status.
