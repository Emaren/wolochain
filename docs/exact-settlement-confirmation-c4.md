---
id: "aoe2war.wolochain.exact-settlement-confirmation-c4"
title: "Exact Settlement Confirmation C4"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "git"
authority: "source-only-exact-settlement-confirmation"
reviewed_at: "2026-10-16"
review_interval_days: 14
sensitivity: "restricted"
---

# Exact Settlement Confirmation C4

C4 corrects the legacy false-confirmation path from merged
[PR #20](https://github.com/Emaren/wolochain/pull/20),
`87f9c0f9e4c9ad92520d72ac0df5fae9718c923a`. The implementation baseline in the
[documentation index](DOCUMENTATION_CONTROL_PLANE.md) identifies the code
described here. This is a source contract, not a production activation receipt.

## Defect and bounded correction

Previously, `lookupSettlementTx` decoded an HTTP-success response into value
fields and set `OK` and `Found` without requiring a complete transaction result.
An empty `{}` therefore inherited `code=0`. `waitForTxConfirmation` supplied no
payout expectations and could promote that incomplete observation to confirmed
payment. Recipient-and-amount event matching also selected the first matching
effect without establishing unique ownership of that effect.

[`settlement_confirmation_test.go`](../cmd/wolochaind/cmd/settlement_confirmation_test.go)
starts with adversarial cases for that path: empty/missing/null envelopes,
absent or substituted hashes, invalid/nonpositive heights, malformed execution
codes, invalid transaction bodies and inconsistent effects. The initial suite
ran against the unchanged starting implementation and reproduced 30 failing
assertions: 28 table cases, empty-response confirmation polling and ambiguous
effect selection. Five initially tested malformed forms were already rejected.
The later raw-byte, strict-context and receipt fixtures expand that suite; they
are not all claimed as failing-before cases. Tests use loopback HTTP sources
and a synthetic CLI; they use no keys or real transaction.
PR #20's canonical positive signed-integer amount and multiplication bounds are
retained unchanged.

## Exact configured-source proof

[`lookupSettlementTx`](../cmd/wolochaind/cmd/settlement.go) requires a valid
requested transaction hash and the configured `wolo-1` chain identity. The
[bounded reader](../cmd/wolochaind/cmd/settlement_confirmation.go) requires an
HTTP-200 object containing non-null `tx_response`, `tx` and `tx.body`, exact
returned-versus-requested hash, canonical positive signed committed height and
a decodable Cosmos transaction body. Execution code must be a valid uint32;
null, negative, fractional, overflow and noncanonical forms are invalid.
Proto3 may omit a successful zero code **inside the required result object**.
That omission never substitutes for the result object, hash, height or body.

Generic lookup can report `status=committed` or a committed `failed` result. It
cannot confirm a payout obligation without the complete strict payout context.
`waitForTxConfirmation` requires that context and polls only transaction-not-found
observations within its existing timeout and cancellation bounds. Malformed,
conflicting or unavailable evidence stops confirmation. Polling is read-only
and cannot broadcast a replacement transaction.

Strict payout confirmation binds all of the following:

- Exactly one decoded `cosmos.bank.v1beta1.MsgSend`, one coin and `uwolo`.
- The authorized signer supplied by the existing service-specific signer
  resolution, the normalized recipient and exact normalized base-unit amount.
- The exact normalized memo, including an intentionally empty memo. Where a
  caller supplies canonical request context in that memo, the entire supplied
  context must agree. The legacy contract does not universally encode
  `request_id` on-chain; C4 does not invent that evidence.
- Actual `TxRaw` bytes returned by the configured CometBFT RPC `/tx`, their
  SHA-256 transaction identity, a decoded body equal to the REST body, and
  matching RPC/REST execution code and committed height.
- One uniquely matching bank effect in each transfer-bearing representation.
  RPC and REST top-level effects must agree in order. REST logs may omit fee
  effects, so their log-first list must be an ordered subsequence of the
  top-level effects, with exactly one wanted effect. Empty logs or logs without
  transfer effects retain the shared top-level fallback. Identical matching
  effects are ambiguous. [`internal/chainevents`](../internal/chainevents/transfers.go)
  retains the legacy log-first display ordering; fees are not manually filtered
  or renumbered. The displayed `MatchedTransferIndex` can differ between valid
  log representations and is not the receipt ownership authority.

The implementation reuses the pinned Cosmos protobuf and CometBFT transaction
types, C3's transfer parser, and
[`internal/chainjson`](../internal/chainjson/response.go) guards. Source responses
are bounded to 1 MiB; duplicate JSON keys, trailing JSON, excessive nesting or
node count, compressed bodies and redirects are refused. Request contexts bound
reads and cancellation; the dedicated client bounds response headers and host
connections. Remote payloads do not become proof merely by decoding.

## Execution states and local receipt ownership

`settlementExecuteResponse.confirmation_status` separates the confirmation
observation from the historical broadcast outcome:

| Broadcast/execution status | Confirmation status | Meaning |
| --- | --- | --- |
| `accepted` | `pending` | Broadcast accepted; committed proof not yet available. |
| `accepted` | `unverifiable` | Broadcast accepted; proof or receipt ownership could not be established. |
| `confirmed` | `confirmed` | Exact payout proof and durable local receipt ownership succeeded. |
| `failed` | `failed` | The identified committed transaction executed unsuccessfully. |

`OK=true` for `accepted` preserves acceptance compatibility and is not evidence
of payment. Accepted uncertain outcomes have `retryable=false`. A lookup failure,
404, cancellation, mismatched transfer, ambiguous effect or receipt conflict
never proves nonpayment or authorizes a resend. Existing stored accepted results
remain subject to the historical no-resend guard; C4 adds no background
reconciliation, claim retry or migration of past records.

[`settlement_receipt.go`](../cmd/wolochaind/cmd/settlement_receipt.go) uses version
`wolo.settlement.confirmation.v1` and reserves `wolo-1` + uppercase hash + strict
body effect `0` for one durable request ID, normalized request fingerprint and
signer. Strict C4 admits only body message `0` with coin `0`, so internal
`ReceiptTransferIndex=0` is fixed despite display-event fee variations. This local
body-effect namespace is not C3's global bank-event receipt namespace and grants
no Satchel receipt ownership. The registry lives under the service's configured
`StateDir/confirmation-receipts`. Exclusive per-receipt locks,
file/directory synchronization and conservative existing-request checks precede
a confirmed acknowledgment. A same-owner replay can reuse its own reservation;
another owner cannot. A legacy same-hash record belonging to any other request
blocks every ordinal because legacy records supply no trustworthy ordinal.

The history scan is bounded to 10,000 entries, 64 KiB per record and 16 MiB
aggregate. Unsafe, malformed, unreadable or excessive history refuses
confirmation. A leftover `requests/*.json.tmp` also refuses confirmation:
the historical writer can leave uncertain ownership between broadcast and
request-record rename. No temporary record is deleted or repaired automatically.
A stale exclusive lock is not aged or stolen. Operators must not remove
receipts, locks or historical request records to bypass uncertainty.
This registry protects only the configured service state directory; it is not
a global application ledger or cross-service receipt registry. Distinct payout
signer binding preserves the 8092/8093 separation. The shared escrow does not
become an independent vault.

## Trust and operational blockers remain

The confirmation claim relies on the configured chain sources reporting genuine
execution. RPC/REST agreement and hash-bound bytes detect incomplete/substituted
observations; they do not independently authenticate validator commits or bank
event provenance. C4 does not fetch or verify the C3 inclusion/H+1 commitment
chain, establish a light-client root, or call matching endpoints independent
authorities. A compromised source can fabricate a self-consistent observation.
Source tests cannot certify the operator's endpoint governance or signer control.

[C2 custody](war-satchel-custody-c2.md) remains `UNAVAILABLE` and
[C3 evidence](war-satchel-chain-evidence-c3.md) remains `NONCREDITING`.
Independent vault control, authenticated consensus trust, reserve/liability
reconciliation, global receipt ownership and balanced credits remain separate
gates before real Satchel deposits. C4 does not close the historical
broadcast-before-request-record crash gap, re-prove previously persisted
outcomes, or implement durable withdrawal/refund recovery.

The [settlement runbook](mainnet-settlement-runbook.md) retains the live-service
and financial release authority. No deployment, restart, consensus executable
change, key/signer operation, real transaction, database mutation, app/API source
change or founder claim #889 replay is part of C4. Existing liabilities and
protected 8092/8093 release/drain/recovery holds remain in force. Any later
activation requires source review and the existing independent protected
financial proof and operator release procedure; a green source PR cannot clear
those holds.

## Verification contract

The focused tests cover malformed and substituted evidence, legitimate omitted
zero serialization, body/bytes/result mismatches, unique effect matching, accepted
uncertainty, committed failure and receipt ownership/replay. Existing settlement,
challenge, signer separation and Satchel guards must continue to pass.

```bash
go test -tags go1.27 ./cmd/wolochaind/cmd -run 'TestSettlementConfirmation|TestSettlementReceipt' -count=1
go test -tags go1.27 ./... -count=1
go test -tags go1.27 -race ./... -count=1
go vet -tags go1.27 ./...
go build -tags go1.27 -o /tmp/wolo-settlement-c4-wolochaind ./cmd/wolochaind
WOLO_SKIP_RUNTIME_CHECKS=1 ./scripts/check-chain-invariants.sh
./scripts/check-generated-protos.sh
python3 -m unittest discover -s tests -p 'test_settlement_founder15_state_readonly.py' -v
for script in scripts/*.sh; do bash -n "$script" || exit; done
python3 scripts/docs_v2_check.py
```

Local validation at implementation
`d32ee6c6a61024f0610922b1e1b67318eb51fbc2` passed 614 Go tests/subtests
(129 top-level tests), with zero failures. Full-repository race validation also
passed 614 tests/subtests. Four existing opt-in application simulations remained
skipped: `TestFullAppSimulation`, `TestAppImportExport`,
`TestAppSimulationAfterImport` and `TestAppStateDeterminism`.
Vet, build, generated-protobuf drift, all 11 Python contracts, source invariants
and each operator script's syntax passed. Production runtime invariant checks
were intentionally excluded with `WOLO_SKIP_RUNTIME_CHECKS=1`.

CI now includes command-package race tests, vet and source-bound documentation
validation, and checks each shell script individually. Documentation validation
runs immediately after a full-history checkout: the first hosted attempt proved
that a shallow checkout cannot resolve the recorded implementation ancestor.
The checkout now fetches that history; the authority guard remains unchanged. A single `bash -n
scripts/*.sh` treats later script paths as arguments to the first script and is
not an all-script syntax check. The final-head hosted CI receipt and final source
SHA belong in the draft PR; these local validation results do not imply hosted
CI completion, mainnet payment or activation certification.
