---
id: "aoe2war.wolochain.settlement-contracts"
title: "Settlement Contracts"
type: "reference"
status: "active"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "git"
authority: "machine-readable-settlement-contract-index"
reviewed_at: "2026-10-20"
review_interval_days: 30
sensitivity: "public"
---

# Settlement Contracts

## Private War Satchel contract

[War Satchel OpenAPI 1.0.0](war-satchel-http-v1.openapi.json) describes the exact
loopback 8094 bearer protocol, including owner-reserved protocol-2 wagers,
owner-approved withdrawals, signed multi-leg return preparation/reconciliation,
portable proof export, durable operation lookup and safe failure states. ABI
tests compare routes and Go JSON structs to the document. This is a source
contract, not a live vault destination, custody attestation or release permit.
The [operator procedure](../war-satchel-controlled-release.md) preserves separate
consensus and legacy 8092/8093 authorities.


## Review Scope — 2026-10-10 UTC

Source contract boundaries reviewed. Live settlement signers, balances and execution endpoints were not independently reverified.

No runtime, wallet, liquidity, settlement, or chain mutation was performed during this documentation review.

## Review Renewal — 2026-09-09 UTC

The canonical challenge memo/request schemas and example payloads remain present in
source, and the settlement implementation still exposes the documented challenge
funding, validate, execute, inspect, and audit route family. Live mainnet settlement
health returned `ok=true`, `chain_id=wolo-1`, and the documented payout/escrow
signers. The contract boundary remains unchanged: WoloChain validates and executes
explicit money movement; AoE2HDBets decides gameplay outcomes. No settlement
execution or Wolo mutation was performed by this review.

Machine-readable WoloChain settlement contract files for AoE2HDBets challenge settlement integration.

WoloChain validates and executes explicit money movements. AoE2HDBets owns challenge outcome decisions and sends the already-decided transfer plan.

## Files

- `challenge-funding-memo.schema.json`: fields encoded after the `wolo.challenge.funding.v1:` escrow deposit memo prefix.
- `challenge-settlement-request.schema.json`: JSON payload accepted by challenge dry-run and execute paths.
- `examples/challenge-one-noshow.json`: checked-in player receives the no-show guarantee; both wagers refund.
- `examples/challenge-double-noshow.json`: both guarantees route to treasury; both wagers refund.
- `examples/challenge-played-match.json`: both guarantees return; wager buckets pay to the winner chosen by AoE2HDBets.
- `examples/challenge-canceled-refund.json`: all wager and guarantee buckets refund.
- `examples/challenge-funding-memos.json`: concrete canonical memo strings and parsed fields.
- `examples/responses/challenge-funding-verify-response.json`: tx-hash funding proof response shape.
- `examples/responses/challenge-funding-recent-response.json`: recent escrow deposit discovery response shape for app-side automatic funding detection.
- `examples/responses/challenge-validate-response.json`: dry-run response shape with verified funding and bucket totals.
- `examples/responses/challenge-execute-response.json`: execution response shape with transfer tx hashes, proof links, and optional escrow-to-payout top-up.
- `examples/responses/challenge-inspect-summary-response.json`: concise stored settlement state response for proof display.
- `examples/responses/challenge-audit-summary-response.json`: read-only reconciliation response for operator/auditor checks.

## Boundary

WoloChain accepts caller-supplied settlement disposition. It does not decide who checked in, who no-showed, who won, or whether a challenge should be canceled.

AoE2HDBets supplies:

- `source_app`, `challenge_id` and/or `source_event_id`
- the funding tx hashes it wants verified
- optional per-funding `settlement_run_id`, `expected_amount_uwolo`, `wager_uwolo`, and `guarantee_uwolo` expectations
- the explicit `wager` and `guarantee` bucket transfer list
- optional `treasury_address` for caller-decided forfeits

Canonical AoE2HDBets funding memo:

```text
wolo.challenge.funding.v1:app=aoe2hdbets&sid=aoe2hdbets:challenge-42:v1&cid=42&side=left&w=1000000&g=500000&t=1500000
```

WoloChain verifies:

- the transaction succeeded on `wolo-1`
- the exact sender sent one `uwolo` funding amount into the configured canonical escrow
- the canonical memo contains exactly `app`, `sid`, `cid`, `side`, `w`, `g`, and `t`, once each
- `app` is exactly `aoe2hdbets`
- `cid` is a canonical positive integer and `sid` is exactly `aoe2hdbets:challenge-<cid>:v1`
- `side` is exactly `left` or `right`
- `w` and `t` are positive canonical uwolo integers; `g` is canonical non-negative (including `g=0` for Championship V2); and `w + g = t =` the escrow transfer
- the settlement request allocates every verified participant bucket exactly once
- the settlement request uses the same canonical `sid` as its idempotency key and does not repeat a funding tx hash
- executed refund/payout/treasury/top-up tx hashes reconcile with stored state

The parser retains expanded legacy aliases for noncanonical historical integrations. AoE2HDBets memos emitted with `app=aoe2hdbets` take the strict path above.

Canonical transfer reasons are caller-supplied proof labels:

- `return`: Match Guarantee returned to its original participant.
- `forfeit`: Match Guarantee forfeited to another participant.
- `treasury`: Match Guarantee routed to the explicit treasury address.
- `refund`: Wolo Wager or Match Guarantee refunded.
- `release` or `payout`: Wolo Wager released to the caller-supplied winner/payee.

## Operator Flow

```bash
wolochaind settlement challenge funding verify --tx-hash <funding_tx_hash> --settlement-run-id <settlement_run_id> ...
wolochaind settlement challenge funding recent --source-app aoe2hdbets --settlement-run-id <settlement_run_id> --challenge-id <challenge_id>
wolochaind settlement challenge validate --file docs/settlement-contracts/examples/challenge-one-noshow.json
wolochaind settlement challenge execute --file docs/settlement-contracts/examples/challenge-one-noshow.json
wolochaind settlement challenge inspect --settlement-id <settlement_run_id> --summary-only
wolochaind settlement challenge audit --settlement-id <settlement_run_id> --summary-only
```

Use real tx hashes and real `wolo1...` addresses before submitting an example payload.

## App Integration Flow

1. Watch or poll `GET /settlement/v1/challenges/funding/deposits?sender=<wallet>&source_app=aoe2hdbets&settlement_run_id=aoe2hdbets:challenge-<id>:v1&challenge_id=<id>&participant_side=<left|right>` for automatic funding detection.
2. Verify each candidate deposit with `GET /settlement/v1/challenges/funding/txs/{tx_hash}` and expected source/settlement/challenge/participant/bucket fields.
3. Submit the caller-decided transfer plan to `POST /settlement/v1/challenges/validate`.
4. Execute the exact same payload with `POST /settlement/v1/challenges`.
5. Show app users `canonical_tx_lookup_preferred` links from funding and transfer responses.
6. Use `GET /settlement/v1/challenges/{settlement_run_id}?summary_only=1` for stored run status and proof display. Repeating the same execution payload returns the stored idempotent result; changing a payload under the same ID returns an idempotency conflict.
7. Use `wolochaind settlement challenge audit --settlement-id <settlement_run_id>` for read-only operator reconciliation.

The read-only funding, inspect, recent, and audit surfaces are WoloChain truth. Challenge disposition fields such as no-show, winner, refund reason, or treasury policy remain caller-supplied AoE2HDBets truth.

## October 20 — independent PRE-BET live Watcher receipt issuer (SOURCE HOLD)

`internal/satchelservice/reviewer_live_witness_issuer.go` is a new
library-only, independently provisioned **v2 Ed25519 live game-start
witness signer**. The original `ReviewerWatcherLiveWitnessMessage`
protocol already exists and is verified at the independent reviewer;
this change closes the issuer-side primitive without creating an HTTP
ingress, a chain signing key or a payout worker.

Its operator-owned interfaces are separate: an **original append-only
live capture source** supplies the immutable operation/Steam/game/
market/proposition/roster identity, original captured/observed times
and checksum; an independently configured checkpoint reader opens the
actual immutable game-start bytes and recomputes their SHA-256. Neither
source is permitted to accept claims from the requesting user, a
mutable app projection or the wallet-funded ledger. Two original
capture reads and two original-byte digests must agree before signing.

The issuer checks the existing signed witness protocol's captured/
roster timing and source freshness, bounds the new receipt to at most
30 seconds from current time and 60 seconds from original observation,
and pins the exact operation into a private 0600 bbolt journal. The
journal saves **PENDING before signing**, and permanently refuses to
regenerate or extend the witness after an interrupted PENDING. An
already signed valid witness is returned only after fresh original
source/bytes verification; expiry never renews. The witness public
key is distinct from **both** financial approval keys.

Negative tests cover missing/changed original captures, wrong roster,
expired records, mismatched original bytes, wrong keys, invalid
financial-key reuse, symlink/world-readable state, and crash-safe
idempotence. Any failed source or signature stays PENDING; there is
no transfer request, wallet interface, ledger mutation or Wolo
broadcast in the issuer.

**Not deployment-ready:** the independently governed production
`OriginalLiveCaptureSource` and immutable
`ReviewerIndependentLiveCheckpointReader` adapters, dedicated
private witness signing-key custody, provenance-backed API-to-HD
original operation binding, separately authenticated fee/bank/global
liability census, six Wolo historical financial release controls,
and live funded end-to-end Keplr/Watcher/wager/withdrawal replay
are still separate **HOLD** gates. The source-only issuer does
not activate 8094 or 8095 and must never be interpreted as a
financial authorization. No production runtime or keys were changed.

## October 18 dated release evidence

The **[financial release checklist](financial-release-checklist.json)** is the
single current six-control index, using the existing controller's exact control
names. Its linked dated observations are nonauthorizing evidence, not independent
consensus or financial certification. The current website release is independent
and CERTIFIED at `78d2a332`; the Wolo financial HOLD is unchanged. See the
[finite maintenance/cutover sequence](../mainnet-settlement-runbook.md#shortest-protected-operator-sequence).

The earlier receipts below remain immutable historical records, including their
then-current website assumptions; they do not supersede the current checklist.

The [protected release-frontier receipt](protected-release-frontier-20261018.json)
records subsequent unchanged runtime identities, local chain progress and
noncertifying producer/request-store observations. The
[website HOLD evidence schema](wolo-website-hold-evidence-v1.schema.json) is the
structural contract for a future app-owned website-only lane; every authority
flag stays false. It cannot authenticate a baseline, certify financial holds or
authorize the current website candidate. See the
[consumer requirements](../war-satchel-controlled-release.md#future-website-only-lane-observational-evidence-separate-authority).

The [exact backend artifact receipt](custody-backend-artifact-20261018.json)
binds the independently verified Linux AMD64 binary to source `99f32de6`, builder
`7611946c` and three successful GitHub CI runs. It remains UNDEPLOYED.
The [read-only source/runtime receipt](settlement-source-authority-20261018.json)
records old `78c25985` settlement runtime and checkout, unchanged consensus and
one preserved ignored build-output directory. The source gate correctly remains
BLOCKED. Neither receipt authorizes funds, claim retries, custody or deployment;
see the [protected authority procedure](../mainnet-settlement-runbook.md).

## Review Scope — 2026-10-10 UTC

Source contract boundaries reviewed. Live settlement signers, balances and execution endpoints were not independently reverified.

No runtime, wallet, liquidity, settlement, or chain mutation was performed during this documentation review.

## Review Renewal — 2026-09-09 UTC

The canonical challenge memo/request schemas and example payloads remain present in
source, and the settlement implementation still exposes the documented challenge
funding, validate, execute, inspect, and audit route family. Live mainnet settlement
health returned `ok=true`, `chain_id=wolo-1`, and the documented payout/escrow
signers. The contract boundary remains unchanged: WoloChain validates and executes
explicit money movement; AoE2HDBets decides gameplay outcomes. No settlement
execution or Wolo mutation was performed by this review.

Machine-readable WoloChain settlement contract files for AoE2HDBets challenge settlement integration.

WoloChain validates and executes explicit money movements. AoE2HDBets owns challenge outcome decisions and sends the already-decided transfer plan.

## Files

- `challenge-funding-memo.schema.json`: fields encoded after the `wolo.challenge.funding.v1:` escrow deposit memo prefix.
- `challenge-settlement-request.schema.json`: JSON payload accepted by challenge dry-run and execute paths.
- `examples/challenge-one-noshow.json`: checked-in player receives the no-show guarantee; both wagers refund.
- `examples/challenge-double-noshow.json`: both guarantees route to treasury; both wagers refund.
- `examples/challenge-played-match.json`: both guarantees return; wager buckets pay to the winner chosen by AoE2HDBets.
- `examples/challenge-canceled-refund.json`: all wager and guarantee buckets refund.
- `examples/challenge-funding-memos.json`: concrete canonical memo strings and parsed fields.
- `examples/responses/challenge-funding-verify-response.json`: tx-hash funding proof response shape.
- `examples/responses/challenge-funding-recent-response.json`: recent escrow deposit discovery response shape for app-side automatic funding detection.
- `examples/responses/challenge-validate-response.json`: dry-run response shape with verified funding and bucket totals.
- `examples/responses/challenge-execute-response.json`: execution response shape with transfer tx hashes, proof links, and optional escrow-to-payout top-up.
- `examples/responses/challenge-inspect-summary-response.json`: concise stored settlement state response for proof display.
- `examples/responses/challenge-audit-summary-response.json`: read-only reconciliation response for operator/auditor checks.

## Boundary

WoloChain accepts caller-supplied settlement disposition. It does not decide who checked in, who no-showed, who won, or whether a challenge should be canceled.

AoE2HDBets supplies:

- `source_app`, `challenge_id` and/or `source_event_id`
- the funding tx hashes it wants verified
- optional per-funding `settlement_run_id`, `expected_amount_uwolo`, `wager_uwolo`, and `guarantee_uwolo` expectations
- the explicit `wager` and `guarantee` bucket transfer list
- optional `treasury_address` for caller-decided forfeits

Canonical AoE2HDBets funding memo:

```text
wolo.challenge.funding.v1:app=aoe2hdbets&sid=aoe2hdbets:challenge-42:v1&cid=42&side=left&w=1000000&g=500000&t=1500000
```

WoloChain verifies:

- the transaction succeeded on `wolo-1`
- the exact sender sent one `uwolo` funding amount into the configured canonical escrow
- the canonical memo contains exactly `app`, `sid`, `cid`, `side`, `w`, `g`, and `t`, once each
- `app` is exactly `aoe2hdbets`
- `cid` is a canonical positive integer and `sid` is exactly `aoe2hdbets:challenge-<cid>:v1`
- `side` is exactly `left` or `right`
- `w` and `t` are positive canonical uwolo integers; `g` is canonical non-negative (including `g=0` for Championship V2); and `w + g = t =` the escrow transfer
- the settlement request allocates every verified participant bucket exactly once
- the settlement request uses the same canonical `sid` as its idempotency key and does not repeat a funding tx hash
- executed refund/payout/treasury/top-up tx hashes reconcile with stored state

The parser retains expanded legacy aliases for noncanonical historical integrations. AoE2HDBets memos emitted with `app=aoe2hdbets` take the strict path above.

Canonical transfer reasons are caller-supplied proof labels:

- `return`: Match Guarantee returned to its original participant.
- `forfeit`: Match Guarantee forfeited to another participant.
- `treasury`: Match Guarantee routed to the explicit treasury address.
- `refund`: Wolo Wager or Match Guarantee refunded.
- `release` or `payout`: Wolo Wager released to the caller-supplied winner/payee.

## Operator Flow

```bash
wolochaind settlement challenge funding verify --tx-hash <funding_tx_hash> --settlement-run-id <settlement_run_id> ...
wolochaind settlement challenge funding recent --source-app aoe2hdbets --settlement-run-id <settlement_run_id> --challenge-id <challenge_id>
wolochaind settlement challenge validate --file docs/settlement-contracts/examples/challenge-one-noshow.json
wolochaind settlement challenge execute --file docs/settlement-contracts/examples/challenge-one-noshow.json
wolochaind settlement challenge inspect --settlement-id <settlement_run_id> --summary-only
wolochaind settlement challenge audit --settlement-id <settlement_run_id> --summary-only
```

Use real tx hashes and real `wolo1...` addresses before submitting an example payload.

## App Integration Flow

1. Watch or poll `GET /settlement/v1/challenges/funding/deposits?sender=<wallet>&source_app=aoe2hdbets&settlement_run_id=aoe2hdbets:challenge-<id>:v1&challenge_id=<id>&participant_side=<left|right>` for automatic funding detection.
2. Verify each candidate deposit with `GET /settlement/v1/challenges/funding/txs/{tx_hash}` and expected source/settlement/challenge/participant/bucket fields.
3. Submit the caller-decided transfer plan to `POST /settlement/v1/challenges/validate`.
4. Execute the exact same payload with `POST /settlement/v1/challenges`.
5. Show app users `canonical_tx_lookup_preferred` links from funding and transfer responses.
6. Use `GET /settlement/v1/challenges/{settlement_run_id}?summary_only=1` for stored run status and proof display. Repeating the same execution payload returns the stored idempotent result; changing a payload under the same ID returns an idempotency conflict.
7. Use `wolochaind settlement challenge audit --settlement-id <settlement_run_id>` for read-only operator reconciliation.

The read-only funding, inspect, recent, and audit surfaces are WoloChain truth. Challenge disposition fields such as no-show, winner, refund reason, or treasury policy remain caller-supplied AoE2HDBets truth.
