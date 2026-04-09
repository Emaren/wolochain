# WoloChain

WoloChain is the fixed-supply Cosmos chain for the AoE2HDBets ecosystem.

## Canonical Identity

- Chain name: `WoloChain`
- Binary: `wolochaind`
- Chain ID: `wolo-testnet`
- Address prefix: `wolo`
- Base denom: `uwolo`
- Display denom: `wolo`
- Symbol: `WOLO`
- Decimals: `6`

## Ownership Boundary

WoloChain owns:

- chain identity
- balances and transfers
- settlement execution rails
- genesis and denom metadata
- node/bootstrap/testnet operations
- integration-facing proof and status primitives

WoloChain does not own:

- AoE2HDBets betting rules
- AoE2HDBets UX and operator presentation
- explorer UI bugs or Ping route presentation

## Current Live State

Verified on April 9, 2026:

- VPS node service: `wolochaind-testnet.service`
- VPS settlement service: `wolochain-settlement.service`
- VPS moniker: `wolo-testnet-validator-1`
- Runtime chain ID: `wolo-testnet`
- Settlement health: `ok=true`
- Current VPS peer count: `0`
- Public RPC host: `https://rpc.aoe2hdbets.com`
- Public REST host: `https://rest.aoe2hdbets.com`

Current caveats:

- The VPS validator is currently isolated with `0` peers.
- Settlement is live but still uses the temporary payout signer `faucetgrowth`.
- The live keyring now has `faucetgrowth`, `payout`, and `escrow`, but the new `payout.info` and `escrow.info` files are only readable by `wolo` unless you run the checks under root or `sudo -u wolo`.
- The staged dedicated payout address is `wolo1cy04t5af0mr9d8n6rrzgr8e9j4vuf42nfg02q5`, funded with `2000000000uwolo`, but the live service will not use it until the settlement env is installed and the service is restarted.
- The staged dedicated escrow address is `wolo1t4jq7wd4x030t9f0yfqfq74pt4pmaep5nu67y4`.
- Settlement currently uses the `test` keyring backend on the VPS.
- Settlement POST access currently relies on loopback-only binding because `WOLO_SETTLEMENT_AUTH_TOKEN` is empty.
- The deployed VPS settlement binary is still pre-rollout: `POST /settlement/v1/runs/validate` returns `404`, and the live CLI still lacks `inspect`, `recent`, and `run` settlement subcommands.
- Linux `amd64` production builds should use [`scripts/build-linux-amd64.sh`](scripts/build-linux-amd64.sh).

## Local Workflow

- Build: `go build -o build/wolochaind ./cmd/wolochaind`
- Linux build: `./scripts/build-linux-amd64.sh`
- Local health: `./scripts/check-local.sh`
- Clean local bring-up: `./scripts/reset-and-start-local.sh`
- Local balances snapshot: `./scripts/write-local-balances-json.sh`
- Chain invariant check: `./scripts/check-chain-invariants.sh`

## Settlement Surfaces

The chain-owned settlement server exposes loopback HTTP endpoints:

- `GET /settlement/v1/health`
- `POST /settlement/v1/payouts`
- `POST /settlement/v1/runs/validate`
- `POST /settlement/v1/runs`
- `GET /settlement/v1/txs/{tx_hash}`
- `GET /settlement/v1/escrow/txs/{tx_hash}`
- `GET /settlement/v1/escrow/deposits`

Auth behavior:

- when `WOLO_SETTLEMENT_AUTH_TOKEN` is set, settlement POST routes require `Authorization: Bearer ...`
- that includes `POST /settlement/v1/payouts`, `POST /settlement/v1/runs/validate`, and `POST /settlement/v1/runs`
- read-only health and proof routes remain open

This repo also exposes CLI settlement commands:

- `wolochaind settlement doctor`
- `wolochaind settlement execute`
- `wolochaind settlement escrow verify`
- `wolochaind settlement escrow recent`
- `wolochaind settlement lookup`
- `wolochaind settlement inspect`
- `wolochaind settlement recent`
- `wolochaind settlement run validate`
- `wolochaind settlement run execute`
- `wolochaind settlement run inspect`
- `wolochaind settlement run recent`
- `wolochaind settlement serve`

Settlement execution now supports:

- separate internal and public proof URLs via `WOLO_SETTLEMENT_PUBLIC_REST_URL`
- preferred proof links via `canonical_tx_lookup_preferred`
- payout reserve-floor enforcement via `WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO`
- fee headroom enforcement via `WOLO_SETTLEMENT_FEE_HEADROOM_UWOLO`
- read-only escrow deposit verification by tx hash
- read-only escrow deposit discovery for recent transfers into the configured escrow address
- stored request inspection by `request_id`
- grouped settlement runs over the same request-level idempotent payout rail
- dry-run validation before grouped execution, including requested totals and reserve/headroom impact
- stored grouped-run inspection by `settlement_run_id`
- recent failure/refusal summaries via `wolochaind settlement recent --summary-only`
- recent grouped-run summaries via `wolochaind settlement run recent --summary-only`

Operator helpers in this repo:

- [`scripts/check-settlement-cutover.sh`](scripts/check-settlement-cutover.sh): pre-cutover and post-cutover config, key, and route checks
- [`scripts/check-settlement-alerts.sh`](scripts/check-settlement-alerts.sh): machine-readable settlement health/alert JSON with exit codes for cron or VPSSentry
- [`scripts/verify-live-settlement.sh`](scripts/verify-live-settlement.sh): live HTTP/CLI surface verification
- [`scripts/backup-live-settlement.sh`](scripts/backup-live-settlement.sh): rollback-oriented backup of the current binary, env, and settlement state
- [`scripts/restore-live-settlement.sh`](scripts/restore-live-settlement.sh): restore a known-good settlement backup and restart the service

## Settlement Boundary

WoloChain only owns the settlement rail:

- validate payout recipients and amounts
- execute payout sends from the configured payout signer
- store idempotent request and run state
- expose proof links and operator inspection surfaces

AoE2HDBets or any other caller owns:

- who won
- how much each winner should receive
- pool math, market math, odds, refunds, or any business policy

Grouped settlement runs are intentionally generic. The caller can attach generic metadata like:

- `source_app`
- `source_event_id`
- `settlement_run_id`
- `note`
- `memo`

WoloChain does not infer meaning from those fields beyond validation, recording, and operator inspection.

Generic refunds or reversals do not need a special WoloChain abstraction. The existing single-payout and grouped-run rails already cover that operator path as long as the caller provides the recipient, amount, and metadata.

## Grouped Run Flow

For one logical result with many payouts, the preferred flow is:

1. Caller computes recipients and amounts outside WoloChain.
2. Caller sends the grouped payload to `POST /settlement/v1/runs/validate` or `wolochaind settlement run validate`.
3. Operator confirms totals, reserve-floor impact, fee headroom impact, and any line-item warnings.
4. Caller submits the same payload to `POST /settlement/v1/runs` or `wolochaind settlement run execute`.
5. Operator inspects the run with `wolochaind settlement run inspect --run-id ...`.
6. If needed, operator drills into individual request ids with `wolochaind settlement inspect --request-id ...`.

Example grouped payload:

```json
{
  "settlement_run_id": "settlement-2026-04-08-001",
  "source_app": "settler",
  "source_event_id": "event-42",
  "note": "weekly settlement",
  "memo": "weekly payouts",
  "payouts": [
    {
      "to_address": "wolo1recipienta000000000000000000000000000000",
      "amount_uwolo": "1500000"
    },
    {
      "request_id": "settlement-2026-04-08-001:item-002",
      "to_address": "wolo1recipientb000000000000000000000000000000",
      "amount_uwolo": "2500000"
    }
  ]
}
```

If a line item omits `request_id`, WoloChain derives a stable request id from `settlement_run_id` and the line-item index so grouped replays stay deterministic.

## Production Notes

- Do not commit compiled binaries or validator home data.
- Prefer [`scripts/build-linux-amd64.sh`](scripts/build-linux-amd64.sh) for VPS builds instead of raw `go build`.
- Treat settlement request state as operator data; it now lives on the VPS extra volume.
- Treat grouped run state as operator data too; it lives beside request state under the settlement state dir.
- Prefer setting `WOLO_SETTLEMENT_AUTH_TOKEN` even for localhost-only POSTs and have callers send bearer auth.
- `WOLO_SETTLEMENT_ESCROW_ADDRESS` only affects proof classification and operator warnings; it does not create escrow semantics by itself.
- Set `WOLO_SETTLEMENT_FEES` if you want dry-run grouped runs to return a deterministic fee estimate in `uwolo`.
- Use [`scripts/check-settlement-cutover.sh`](scripts/check-settlement-cutover.sh) before cutover with `CHECK_SERVICE=0` to verify env and key readiness.
- Use [`scripts/backup-live-settlement.sh`](scripts/backup-live-settlement.sh) immediately before cutover so rollback is one command sequence away.
- Use [`scripts/check-settlement-alerts.sh`](scripts/check-settlement-alerts.sh) after cutover for machine-readable cron/monitoring checks.
- If you run the alert script as an unprivileged operator user and the `wolo` keyring files are unreadable, the key-presence checks degrade to warnings instead of false alert failures; service-side doctor/health failures still alert.
- Use [`scripts/verify-live-settlement.sh`](scripts/verify-live-settlement.sh) or [`scripts/check-settlement-cutover.sh`](scripts/check-settlement-cutover.sh) after rollout to confirm the live service has the newer settlement surface and auth posture.
- Use [`scripts/restore-live-settlement.sh`](scripts/restore-live-settlement.sh) if the live service comes up wrong and you need to return to the last known-good backup quickly.
- Use `wolochaind settlement escrow verify` or `GET /settlement/v1/escrow/txs/{tx_hash}` when an app/operator needs to prove a deposit really hit the configured escrow address.
- Use `wolochaind settlement escrow recent` or `GET /settlement/v1/escrow/deposits` to recover from partial app-side state loss without adding market logic to WoloChain.

For the live VPS layout and deploy runbook, see [docs/testnet-ops.md](docs/testnet-ops.md).
