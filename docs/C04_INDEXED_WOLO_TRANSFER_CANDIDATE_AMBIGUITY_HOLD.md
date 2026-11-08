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

## 2026-11-08 private local-Comet inclusion verification

The **single** bet_payout record with exactly one local
wallet/amount indexed candidate was reviewed without exposing
its claim ID, wallet address or transaction hash publicly.

The exact private transaction was fetched by its existing indexed
hash through HEL1 loopback Comet RPC at /tx?hash with prove=true.
A same-height /block was fetched separately from the same local node.
The new offline verifier
scripts/settlement_c04_local_comet_inclusion_hold.py:

- Verifies SHA256 of the encoded transaction equals the private
  indexed hash, and execution code is zero.
- Recomputes the Tendermint Merkle *leaf over SHA256(tx bytes)*:
  SHA256(0x00 concatenated with SHA256(tx bytes)), NOT over raw tx bytes.
- Reconstructs any aunts with SHA256(0x01 + left + right),
  matches the RPC proof root against local block header data_hash,
  and checks the exact transaction position and block height.
- Verifies at least one actual transfer event has the exact indexed
  native uwolo amount and recipient. The local response may show
  more than one event row for the same transfer (e.g. message
  instrumentation); that does not imply multiple bank transfers.
- Checks owner-private 0600 input file identities and SHA256 digests,
  fails closed on malformed proof, mutated bytes, wrong block,
  recipient, amount, execution status, or missing event.
- Returns HOLD, never independent bank proof or customer
  payment-finality acceptance.

The source SHA256 is
502789cf9ace1ef39724ff4bf9441a81c0a0fd958f640ebc4a586254444c5c47.
Nineteen focused adversarial tests passed, including two-leaf
Merkle proof positive/negative cases.

A real HEL1 offline verification returned
HOLD_C04_LOCAL_MERKLE_INCLUSION_NOT_INDEPENDENT_PAYMENT_FINALITY;
its protected root0600 physical receipt SHA256 is
67769cf8ead7d1476d70b9b28ae4af2b3a53286da5bcada6460d294eafcce8cb
at
/root/aoe2war-session-a-c04-indexed-transfer-20261108/local-comet-inclusion-hold-receipt-20261108.json.

The cryptographic verification is only a link between the local
node's RPC transaction, proof, events and block header. The same
operator supplies all those inputs. **No independent validator
checkpoint, claimed payout purpose, authorized custody signer, unique
economic link, or recipient claim discharge is established**.
The historical claim still has no recorded payout hash; do not write
one or trigger payment based on this observation. C04 HARD HOLD.

## November 8 — exact v2 temporal partition of the lone unique candidate

The first indexed-transfer guard established one bet-payout
claim with exactly one recipient-plus-amount local index candidate.
That narrow uniqueness by itself has **no payment-finality value**.

The revised C04 v2 aggregate SQL now independently partitions
**every** exactly-one-candidate claim into mutually exclusive:
inside the payout-attempt window (one day before through seven days
after), before the window, after the window, and unavailable
comparable timestamps. The validator rejects impossible or missing
partitions, unknown claim kinds, changed 69-claim totals, falsified
financial release assertions and incompatible time-window settings.

The actual HEL1 PostgreSQL 16 REPEATABLE READ READ ONLY run returned
exactly **one** unique indexed candidate, **zero** inside the
near-attempt window and **one more than seven days after** the
recorded attempt. It is a bet-payout claim. Separate private
provenance checks found the local indexed transaction sender among
senders associated with hash-bearing bet payouts, but the transfer
memo contained no tested source-market reference or settlement/payout
labels. Neither an address overlap nor the absence of a memo substring
authenticates or disproves the economic purpose of that transaction.

The new exact C04 time-partition source is
scripts/settlement_c04_indexed_transfer_ambiguity_hold.py,
SHA256:
f824aa48b4c3509771f25d69d2872661078b22f814c8b41e63a911ed3de3877b.
The first source v1 receipt remains historical evidence for
its original snapshot and must not be silently relabelled v2.

Real private source-bound time-partition evidence SHA256:
17c890c014141c4bc392dfad8b9d529e1a1994737d82d7b141ea1998d6ba13d3.
Private root0600 path:
/root/aoe2war-session-a-c04-index-timing-v2-20261108/physical-v2-index-time-partition-hold-20261108.json.

**Result: financial HARD HOLD**. The indexed recipient/amount
candidate exists in local same-node chain data, but the claimed
historical payout's source intent, independent finality, signer
identity, ledger non-overlap and discharge are still unproven.
No automatic retry, refund, credit, claim rewrite or payout.

## November 8 — unique candidate linked to OTHER market's void refund

Further read-only PostgreSQL correlation exposed an economic
overlap that the original recipient+amount index scan could not
distinguish. The only uniquely matched local transfer candidate
for a historical hashless bet_payout is already referenced by:

- **One claimed, hash-bearing bet_refund record**, and
- **One void bet_wager payout record** with the same chain hash.

The pre-existing refund claim and void wager agree on claimant,
source market, and nominal amount. The original hashless bet_payout
has the **same claimant and amount but a DIFFERENT source market
and DIFFERENT claim kind**. The candidate transfer occurred more
than seven days after its attempted payout timestamp.

This is an unambiguous **database attribution conflict**.
The existing transaction is already allocated to a different
market's refund record. It **must not** be reused as automatic proof
that the separate hashless payout was satisfied, or automatically
replayed without independent finality, entitlement, custody signer
and disjointness proof. The records could still require independent
review to prove whether the existing refund was in fact final.

The new source-only fail-closed guard
scripts/settlement_c04_unique_candidate_refund_overlap_hold.py
validates that exact cross-surface overlap using SHA-bound,
root-private PostgreSQL REPEATABLE READ READ ONLY evidence. It
requires explicit **different market** identity, same claimant
and amount, previously hash-bearing claimed refund, void wager,
and matching payout hash. The only external output is aggregate
counts; no claim IDs, addresses, raw error text, wallet keys,
transaction hashes or other customer data are published.

Source SHA256:
f26c10f0dbe6ba7db686310bc800c06f3ff45880dc795bcf846cf953695b7399.
The physical HEL1 query and classification both passed as
HOLD_C04_UNIQUE_TRANSFER_ALREADY_ATTRIBUTED_TO_OTHER_MARKET_REFUND.
Owner-private root0600 physical receipt SHA256:
b8b3f7708ba449828013c383b6b399de7fa6e76f7f71311887ab17aa07b5683a,
stored at
/root/aoe2war-session-a-c04-crossrefund-20261108/physical-c04-cross-market-refund-overlap-hold-20261108.json.

Sixteen additional adversarial regression tests pass. This is
a new economic-source disambiguation, **not** a bank payout,
payment reversal, claim write, refund, credit, or financial
gate acceptance. C04 remains HARD HOLD.
