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

Verified on April 8, 2026:

- VPS node service: `wolochaind-testnet.service`
- VPS settlement service: `wolochain-settlement.service`
- VPS moniker: `wolo-testnet-validator-1`
- Runtime chain ID: `wolo-testnet`
- Settlement health: `ok=true`
- Current VPS peer count: `0`

Current caveats:

- The VPS validator is currently isolated with `0` peers.
- Settlement is live but still uses the temporary payout signer `faucetgrowth`.
- Settlement currently uses the `test` keyring backend on the VPS.
- Settlement POST access currently relies on loopback-only binding because `WOLO_SETTLEMENT_AUTH_TOKEN` is empty.
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
- `GET /settlement/v1/txs/{tx_hash}`

This repo also exposes CLI settlement commands:

- `wolochaind settlement doctor`
- `wolochaind settlement execute`
- `wolochaind settlement lookup`
- `wolochaind settlement serve`

## Production Notes

- Do not commit compiled binaries or validator home data.
- Prefer [`scripts/build-linux-amd64.sh`](scripts/build-linux-amd64.sh) for VPS builds instead of raw `go build`.
- Treat settlement request state as operator data; it now lives on the VPS extra volume.

For the live VPS layout and deploy runbook, see [docs/testnet-ops.md](docs/testnet-ops.md).
