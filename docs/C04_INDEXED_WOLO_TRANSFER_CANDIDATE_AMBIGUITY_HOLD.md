---
id: "aoe2war.wolochain.c04-indexed-wolo-transfer-ambiguity-hold"
title: "C04 indexed WOLO transfer candidate ambiguity and hashless claim finality"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war", "aoe2dewarwagers"]
audience: ["developers", "operators", "ai-agents"]
source_of_truth: "git"
authority: "source-only-c04-reconciliation-evidence-no-payment-authorization"
reviewed_at: "2026-11-08"
review_interval_days: 7
sensitivity: "restricted"
---

# C04 indexed WOLO transfer candidate ambiguity and hashless claim finality

## Physical problem and observed populations

The HD public.pending_wolo_claims table has **69 records**
marked claimed without a payout_tx_hash, amount **120,443 WOLO**.
They comprise **51 founders_bonus / 4,138 WOLO**,
**15 bet_payout / 109,504 WOLO** and
**3 bet_refund / 6,801 WOLO**. All 69 have a linked user wallet,
66 have a database-recorded payout attempt, none have a
payout_proof_url, and 67 have nonempty error_state fields.

This proves **neither unpaid nor paid**. No retry, credit,
refund, recipient update or signer action is authorized.

A separately run, SHA-bound C04 identity fingerprint source has
previously verified the 69-row population with claimset SHA256
eec442d8ea865fd41be47f89a2578fb807851b37e1d426c8f657341c895e9323.
This new candidate-matching observer pins cohort size/nominal but
does not recompute the complete independent identity fingerprint.
Therefore both remain separate inputs to eventual release review.

## Indexed transfers are candidates, not payment proofs

The local read-only HD transfer index had **4,300 wolo-1/uwolo
records**, latest indexed block height **2,813,553**, with latest
timestamp dated November 4, 2026.

The exact source-bound SQL matches each ambiguous claim against
local indexed transfers requiring:

- Exact user wallet ↔ recipient address after lowercase normalization.
- Exact amount conversion: one WOLO = 1,000,000 uwolo.
- Chain ID wolo-1 and denom uwolo.
- Optional nearest-attempt window: one day before to seven days
  after the claimed payout attempt (also reported at 30 days).

A local index entry is **not** an independently authenticated
consensus inclusion proof, signer/custody key proof, disjoint
economic event proof, or entitlement to discharge any claim.

### Physical results

| Kind | Claimed/hashless | Any indexed wallet+amount candidate | Near-attempt candidates | Exactly one indexed candidate |
| --- | ---: | ---: | ---: | ---: |
| founders_bonus | 51 | 51 | 49 | 0 |
| bet_payout | 15 | 9 | 4 | 1 |
| bet_refund | 3 | 1 | 1 | 0 |
| **Total** | **69** | **61** | **54** | **1** |

Recurring founder-bonus transfers generate **5,412 indexed
candidate rows** for the 51 claims; amount/address alone is very
weak identity evidence. Bet payouts have **691 candidate rows**,
bet refunds **43**. Even the single exact wallet+amount match
could be a coincidental, unrelated, incomplete or unauthenticated
transfer. It **must not** be treated as final payment.

The physical observation had root0400 SHA-pinned source, PostgreSQL
REPEATABLE READ READ ONLY, owner-private root0600 raw data and
classification, and a separate root0600 source/evidence envelope.
Source SHA256:
3213b777ce5d2d8a61ee5f44f07897b9b266c058cde783fc118e478fad5fafdc.
Receipt SHA256:
b57fca2ef690e8541c7d46bb2d97a2f1f2407732770d98149d97a52765bfebbf.
Private path:
/root/aoe2war-session-a-c04-indexed-transfer-20261108/physical-ambiguity-hold-receipt-20261108.json.
No wallets, recipient identities, claim IDs or raw payment errors are
released in GitHub documentation.

## Actual C04 acceptance remains blocked

Investigate any candidate transaction against a source-pinned
authenticated Wolo bank proof at an exact height, match transaction
hash, recipient, amount, source event, custody signer, economic
purpose, replay/idempotency journal, and recipient entitlement;
prove archive freshness/completeness and independent checkpoint.
Do not use a single-node current height or indexed transfer row as
a financial finality attestation.

The approved C04 process must reconcile every one of the 69
historical records, including multiple candidate rows and cases
with **zero** indexed matches. Preserve an immutable HOLD receipt
for each unresolved item. No replay, refund or automatic correction.

This audit never transfers funds and never closes financial C04,
C05, C03, C06, C07, C08 or C09 gates. The separate signed
transaction-specific owner permit remains mandatory for actual
funded activity after all physical prerequsites pass.
