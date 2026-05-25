# Settlement Contracts

Machine-readable WoloChain settlement contract files for AoE2HDBets challenge settlement integration.

WoloChain validates and executes explicit money movements. AoE2HDBets owns challenge outcome decisions and sends the already-decided transfer plan.

The checked-in response examples are testnet-shaped. Do not copy their `wolo-testnet` chain ID, `https://aoe2war.com/rest` proof links, sample tx hashes, or sample `wolo1...` addresses into the live AoE2WAR mainnet app.

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

WoloChain verifies:

- each funding tx sent `uwolo` into the configured escrow address
- the memo has the expected app, settlement-run, challenge/event, and participant fields when supplied
- funded totals split cleanly into `wager_uwolo` and `guarantee_uwolo`
- the settlement request allocates every verified participant bucket exactly once
- executed refund/payout/treasury/top-up tx hashes reconcile with stored state

Use compact aliases in actual funding tx memos to stay under the chain memo limit: `app`, `sid`, `cid`, `eid`, `side`, `pid`, `w`, `g`, and `t`. WoloChain normalizes them to the expanded contract fields in verification, inspect, and audit responses.

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

1. Watch or poll `GET /settlement/v1/challenges/funding/deposits?source_app=aoe2hdbets&settlement_run_id=<settlement_run_id>&challenge_id=<challenge_id>` for automatic funding detection.
2. Verify each candidate deposit with `GET /settlement/v1/challenges/funding/txs/{tx_hash}` and expected source/settlement/challenge/participant/bucket fields.
3. Submit the caller-decided transfer plan to `POST /settlement/v1/challenges/validate`.
4. Execute the exact same payload with `POST /settlement/v1/challenges`.
5. Show app users `canonical_tx_lookup_preferred` links from funding and transfer responses.
6. Use `GET /settlement/v1/challenges/{settlement_run_id}?summary_only=1` for stored run status and proof display.
7. Use `wolochaind settlement challenge audit --settlement-id <settlement_run_id>` for read-only operator reconciliation.

The read-only funding, inspect, recent, and audit surfaces are WoloChain truth. Challenge disposition fields such as no-show, winner, refund reason, or treasury policy remain caller-supplied AoE2HDBets truth.
