---
id: "aoe2war.wolochain.c05-pending-gift-same-nominal-claim-collision-hold"
title: "C05 pending gift nominal collisions — not proof of payment"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war", "aoe2dewarwagers"]
audience: ["developers", "operators", "ai-agents"]
source_of_truth: "git"
authority: "source-only-c05-historical-payment-ambiguity-no-payment-authority"
reviewed_at: "2026-11-27"
review_interval_days: 7
sensitivity: "restricted"
---

# C05 pending gift nominal collisions — not proof of payment

## Physical read-only HD source observations

A live HD PostgreSQL REPEATABLE READ READ ONLY anonymous aggregate
on November 8 found exactly two pending WOLO gifts:

- One pending 100,000-WOLO bounty-reference gift. It has
  **zero** same-recipient, same-nominal pending_wolo_claims.
- One separate pending 100-WOLO gift. It has **24**
  same-recipient, same-nominal pending_wolo_claims, all
  status claimed and all carrying an existing payout_tx_hash.
  They consist of 20 bet_refund and 4 bet_payout records.
  Zero matching claim records were created within a day
  before or after the gift; 13 were created within 30 days.

Only aggregate counts left PostgreSQL. No user ID, wallet address,
gift ID, note, claim ID, payout hash or recipient identity is
included here. The live SQL was a separate manual read-only
observation, **not** the first exact-source observer run.

**Neither finding proves gift payment or discharge.**
A same-recipient/same-amount payment for an unrelated market
cannot automatically be used to discharge a pending gift, even
when a transaction hash is present. The opposite is equally
important: absence of a same-nominal claim does not establish
that the 100,000-WOLO gift was never paid externally.

## Reviewed source-only fail-closed observer

The new observer
scripts/settlement_c05_pending_gift_claim_nominal_collision_hold.py
SHA256
55b0b0b95b3992f1bd2991a92e7fdc5053fa7c349ddff60f21aa238440efb6bc
emits a bounded READ ONLY aggregate SQL census. It reports no
customer identifiers and requires a root/owner-only 0600 input
whose byte-exact SHA256 matches an explicit argument.

The classifier checks two expected pending gift amounts and
the exact nominal claim overlap partitions, with 20 negative
adversarial tests. Unexpected gift/claim/hash count, claim type,
time proximity or a fabricated identity, payment or financial
authorization flag returns STOP. Exact source evidence returns
HOLD_C05_SAME_RECIPIENT_AMOUNT_IS_NOT_GIFT_PAYOUT_IDENTITY.

The same test is explicitly enrolled into the required GitHub
Foundation workflow. All added checks are offline and do not
open a signer, change an HD/DE claim, publish a gift or move WOLO.
The independent source-only PR and required exact-head GitHub
checks must qualify separately; its initial physical HEL1
source/receipt has not been executed or accepted.

## Next economic closure evidence

Require a unique original gift obligation and entitlement source,
the proper recipient and authorized reward, independent bank
and reserve proofs, and chain transaction purpose explicitly tied
to that same obligation. Reconcile already recorded bet_refund and
bet_payout economic events disjointly before clearing any gift.

No outstanding C03/C04/C05 or C01-C09 financial gate is accepted
by this observer. Financial service activation, payment retry,
gift cancellation and customer WOLO mutation remain HARD HOLD.

## November 19, 2026 — limited authority and dated evidence review

An AI source examiner acting through the sole owner's existing connected source workspace checked this document's 64 original body lines for repository-source links, gate-authorization claims, older governance conditions and current-versus-historical language; 1 referenced local source paths were resolved. This is a **scope and safety review**, not an independent human signature or a fresh validation of each historical physical claim. Original observations remain dated and unmodified.

**Topic-specific reconciliation (reserves and liabilities):** C05 is OPEN. Amounts, 24-wallet indexes and earlier bank results are not an independently authenticated, disjoint same-height liability/reserve solvency proof.

**Current controlling decision:** WoloChain issue #239 and reviewed code head `70a95e8f9cb0facbec314063e9deafe7e15aa550`. C04 and C08 CLOSED; C01/C02/C03/C05/C06/C07/C09 OPEN; funding DENIED. The original test/source facts remain evidence only and may not authorize live SQL, HBA, custody, funds, backups or a canary. Live acceptance requires exact source, legitimate protected owner authority and independent physical readback.

## Current applicability — 2026-11-27

Exact source and dated-evidence scope review only: this document was byte-identical to the November 19 reviewed version before this renewal. Its earlier observations, commands and receipts remain historical; they do not authorize live execution. Current gate precedence: [#239](https://github.com/Emaren/wolochain/issues/239), C04/C08 closed, seven gates open, no funded operation authorized. No new custody, reserve, backup, writer-fence or funded-canary certification. See `docs/WE1_SOURCE_SCOPE_REVIEW_20261127.md` for preserved preimage hashes and review limitations.
