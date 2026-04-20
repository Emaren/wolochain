# Settlement Contracts

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

## Operator Flow

```bash
wolochaind settlement challenge funding verify --tx-hash <funding_tx_hash> ...
wolochaind settlement challenge validate --file docs/settlement-contracts/examples/challenge-one-noshow.json
wolochaind settlement challenge execute --file docs/settlement-contracts/examples/challenge-one-noshow.json
wolochaind settlement challenge inspect --settlement-id <settlement_run_id>
wolochaind settlement challenge audit --settlement-id <settlement_run_id>
```

Use real tx hashes and real `wolo1...` addresses before submitting an example payload.
