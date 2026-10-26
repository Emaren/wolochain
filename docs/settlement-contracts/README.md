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

## October 21, 2026 — proof-bound reserve reviewer contract (source-only)

The package `internal/satchelservice/reserve_review.go` implements
`EvaluateProofBoundReserveReview(now, evidence, review, operatorAuthority)`,
a **NON-ACTIVATING** reviewer of potential dedicated Satchel-vault reserves.

The bank input is the actual `satchel.AuthenticatedBankEvidence` value
returned by the native CometBFT/SDK ICS23 bank-state proof verifier; callers
cannot construct an authenticated instance by putting
`"consensus_authenticated":true` in a JSON payload. It must be **current**,
with both independently obtained head observations identifying the same exact
H+1 committing header, matching vault, full account balance, height and block
hash. A stale/historical bank proof is explicitly rejected.

The *other* input is `SignedReserveReview`, independently prepared from a
fresh quiesced and complete liability inventory. It records separate
confirmed obligations, **maximum uncertain obligations** (historical unknowns
including founder #889 and unreconciled legacy transfer when relevant), gas
reserve and a minimum unencumbered cushion. It also commits cryptographically
to the liability inventory, journal snapshot, nonoverlap witness, exact running
binary/configuration and currently approved execution permit. Two separately
provisioned Ed25519 reviewer public keys must verify signatures over the same
full canonical statement: one accounting reviewer and one custody reviewer.
Reusing the same public key for both roles fails. Both reviewer keys
must also be different from **all three** operator-provisioned execution permit,
wager approval and withdrawal approval public keys, and those three operational
roles must remain distinct from each other. No signer or financial reviewer may
attest their own role's supposed independence.

A read-only source decision requires

`authenticated current bank >= confirmed liabilities + uncertain maximum + gas reserve + unencumbered minimum`.

All strings are canonical bounded `uwolo` integers, with big-integer sums and
overflow refusal. Freshness is bounded to 120 seconds or the bank-proof expiry,
whichever comes first. Any missing/unknown evidence, claim coverage assertion,
bank reconciliation, duplicate reviewer key, incomplete overlap witness,
stale permit/config/build, mismatched header, expired attestation or insufficient
assets fails closed. Even a positive source decision only reports the
checked conservative balance: **`CustodyCapability()` remains
`"UNAVAILABLE"`**. The separate [runtime custody issuer](../war-satchel-mainnet-execution.md#october-22--qualified-runtime-capability-no-live-activation)
now consumes this decision only together with actual native bank, recovered
journal, held keyring lease and current exact-build/config/permit evidence.
The primitive itself cannot create reserves, prove inventory completeness by itself,
establish reviewer independence, discharge founder claim #889 or activate
funded Auto Bets.

Before that runtime issuer may genuinely qualify a deployment, operators must
independently prove signers' authority, reviewer identity/independence,
completeness and non-overlap of every historical/current liability and
customer Satchel ledger, dedicated vault key isolation, authenticated bank
consensus trust root, actual fresh state, backup/rollback and explicit bounded
financial release permits. **Do not set Wolo's `custody_capability` to
AVAILABLE just because this signed reserve arithmetic succeeds.**

## October 21, 2026 — historical accepted 100-WOLO proof, offline and non-authorizing

The accepted legacy escrow send, transaction
`D5B4CFAA5E9063F8342EA9E2B6119FCFF28DEE20B2E1DD6803944933B237D699`,
was observed by our own chain endpoints as a successful
`100000000 uwolo` `MsgSend` at height `1078913`. Agreement between
`127.0.0.1` and our public RPC is **one chain-operator trust domain**, not
independent financial finality. This specific historical event is not claim
#889 (unproven founder 300 WOLO).

The isolated `wolosatcheld verify-historical-transfer` command provides a
non-broadcasting, no-keyring, no-DB **native CometBFT/SDK proof replay** for
the historical transaction **only if** an appropriate portable proof and a
genuine independently provisioned trusted checkpoint already exist:

```bash
# Run only against separately operator-provisioned read-only files.
# Do not paste wallet secrets or private signer configurations here.
wolosatcheld verify-historical-transfer \
  --anchor /absolute/operator/trusted-anchor.json \
  --expected /absolute/operator/immutable-original-100wolo-journal-intent.json \
  --proof /absolute/operator/archived-100wolo-portable-proof.json
```

`--expected` must independently specify the original
`legacy-settlement-accepted-escrow-100` obligation, exact uppercase
transaction hash, `wolo-1`, height `1078913`, amount `100000000` uwolo,
original sender, recipient, memo and a nonzero 64-hex journal-identity digest.
**Never derive expected sender, recipient or memo from the supplied proof.**
The NONAUTHORIZING report now includes `anchor_sha256`, `expected_sha256`,
`proof_sha256` and `historical_as_of_utc`: all three exact inputs are bound for
review/reproduction. These hashes do not attest checkpoint origin, the declared
time, solvency, claim disposition or owner permission. No current funding
interface accepts archived evidence as a live balance/deposit proof.

The `--anchor` file is an operator-provisioned `satchel.TrustAnchor` with
height, hash, period_seconds and evidence_reference. The `--proof` file is
the already existing strict `satchel.PortableProof` wire format (`kind=transfer`).

The command replays actual signed headers and transaction/result commitments
against the supplied root, requires the exact original transfer and successful
inclusion, prints fixed redacted evidence and **exits 3 on verified observation**
or **2 on refusal**. It neither authorizes ledger credit nor issues a payout,
retry, production permit, reserve witness or claim #889 resolution. Its output
explicitly marks independently sourced checkpoint provenance and the original
journal identity as **not independently established by this command**.
Credential material, account addresses and full original memo are never printed.

**Historical proof limitation:** the current live reader enforces a fresh
CometBFT trust period (maximum 24 hours), fresh head, and bounded validator
proof travel. It is not a historical archive light client; today's ordinary
chain status and an old untrusted July transaction cannot manufacture a
valid archival transcript or an independently corroborated historical
checkpoint. If the necessary authentic signed checkpoint/transcript cannot be
recovered or verified, this command **must return refusal**, and Wolo #5 remains
on HOLD with the accepted transaction quarantined for manual reconciliation.
Do not turn off freshness checks or attempt to rebroadcast.

A separate independent operator still must attest the original journal
obligation and checkpoint provenance, then reconcile any bank debit/credit,
in-flight effects, duplicated claims and solvency before financial release.

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
