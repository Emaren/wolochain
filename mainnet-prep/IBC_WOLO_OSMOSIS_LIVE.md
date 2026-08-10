---
id: "aoe2war.wolochain.ibc-wolo-osmosis-live"
title: "WoloChain Mainnet Osmosis IBC Path Live"
type: "reference"
status: "active"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "runtime-evidence"
authority: "live-ibc-path-receipt"
reviewed_at: "2026-08-10"
review_interval_days: 30
sensitivity: "internal"
---

# WoloChain Mainnet Osmosis IBC Path Live

Status: Phase 3 complete. The `wolo-1` to `osmosis-1` ICS-20 transfer path is open. Do not transfer WOLO, create liquidity, or create a WOLO/USDC pool from this document without Tony's explicit confirmation.

## Summary

- WoloChain chain ID: `wolo-1`
- Osmosis chain ID: `osmosis-1`
- Hermes config: `/etc/wolochain-mainnet/hermes-osmosis.toml`
- Hermes home: `/var/lib/wolochain-mainnet-relayer`
- Marker: `/root/wolo-1-mainnet-prep-markers/wolo-osmosis-ibc-path-20260525T070440Z.txt`

## IBC Identifiers

- Wolo client ID: `07-tendermint-0`
- Osmosis client ID: `07-tendermint-3705`
- Wolo connection ID: `connection-0`
- Osmosis connection ID: `connection-11058`
- Wolo transfer channel ID: `channel-0`
- Osmosis transfer channel ID: `channel-110224`

## Verified Channel Properties

- Wolo channel state: `Open`
- Osmosis channel state: `Open`
- Wolo port: `transfer`
- Osmosis port: `transfer`
- Ordering: `unordered`
- Channel version: `ics20-1`
- Wolo connection hop: `connection-0`
- Osmosis connection hop: `connection-11058`

## Commands Run

Initial command. This created the client pair and Wolo `connection-0`, then stopped before completing the connection because the Osmosis primary RPC returned HTTP 429:

```bash
HOME=/var/lib/wolochain-mainnet-relayer \
/usr/local/bin/hermes --config /etc/wolochain-mainnet/hermes-osmosis.toml \
  create channel \
  --a-chain wolo-1 \
  --b-chain osmosis-1 \
  --a-port transfer \
  --b-port transfer \
  --new-client-connection \
  --order unordered \
  --channel-version ics20-1 \
  --yes
```

Connection handshake completion:

```bash
HOME=/var/lib/wolochain-mainnet-relayer \
/usr/local/bin/hermes --config /etc/wolochain-mainnet/hermes-osmosis.toml \
  tx conn-try \
  --dst-chain osmosis-1 \
  --src-chain wolo-1 \
  --dst-client 07-tendermint-3705 \
  --src-client 07-tendermint-0 \
  --src-connection connection-0

HOME=/var/lib/wolochain-mainnet-relayer \
/usr/local/bin/hermes --config /etc/wolochain-mainnet/hermes-osmosis.toml \
  tx conn-ack \
  --dst-chain wolo-1 \
  --src-chain osmosis-1 \
  --dst-client 07-tendermint-0 \
  --src-client 07-tendermint-3705 \
  --dst-connection connection-0 \
  --src-connection connection-11058

HOME=/var/lib/wolochain-mainnet-relayer \
/usr/local/bin/hermes --config /etc/wolochain-mainnet/hermes-osmosis.toml \
  tx conn-confirm \
  --dst-chain osmosis-1 \
  --src-chain wolo-1 \
  --dst-client 07-tendermint-3705 \
  --src-client 07-tendermint-0 \
  --dst-connection connection-11058 \
  --src-connection connection-0
```

Transfer channel creation over the existing open connection:

```bash
HOME=/var/lib/wolochain-mainnet-relayer \
/usr/local/bin/hermes --config /etc/wolochain-mainnet/hermes-osmosis.toml \
  create channel \
  --a-chain wolo-1 \
  --a-connection connection-0 \
  --a-port transfer \
  --b-port transfer \
  --order unordered \
  --channel-version ics20-1
```

## Verification Commands

```bash
HOME=/var/lib/wolochain-mainnet-relayer \
/usr/local/bin/hermes --config /etc/wolochain-mainnet/hermes-osmosis.toml \
  query connection end --chain wolo-1 --connection connection-0

HOME=/var/lib/wolochain-mainnet-relayer \
/usr/local/bin/hermes --config /etc/wolochain-mainnet/hermes-osmosis.toml \
  query connection end --chain osmosis-1 --connection connection-11058

HOME=/var/lib/wolochain-mainnet-relayer \
/usr/local/bin/hermes --config /etc/wolochain-mainnet/hermes-osmosis.toml \
  query channel end --chain wolo-1 --port transfer --channel channel-0

HOME=/var/lib/wolochain-mainnet-relayer \
/usr/local/bin/hermes --config /etc/wolochain-mainnet/hermes-osmosis.toml \
  query channel end --chain osmosis-1 --port transfer --channel channel-110224
```

Results:

- Both connection ends are `Open`.
- Both channel ends are `Open`.
- Wolo chain state lists `channel-0` with counterparty `channel-110224`.

## Relayer Balances After Creation

- Wolo relayer `wolo-mainnet-osmosis-relayer`: `99998485uwolo`
- Osmosis relayer `osmosis-mainnet-wolo-relayer`: `199266uosmo`

## Endpoint Notes

The Osmosis primary RPC `https://rpc.osmosis.zone` returned HTTP 429 during proof-bearing Hermes steps. The isolated Wolo Hermes config was backed up before each endpoint fallback.

Current Osmosis endpoint settings in `/etc/wolochain-mainnet/hermes-osmosis.toml`:

```toml
rpc_addr = 'https://osmosis.rpc.kjnodes.com'
grpc_addr = 'https://grpc.osmosis.validatus.com:443'
event_source = { mode = 'push', url = 'wss://osmosis.rpc.kjnodes.com/websocket', batch_delay = '500ms' }
```

Backups created:

- `/root/wolo-1-mainnet-prep-markers/hermes-osmosis.toml.pre-stakin-fallback-20260525T065201Z.bak`
- `/root/wolo-1-mainnet-prep-markers/hermes-osmosis.toml.pre-validatus-fallback-20260525T065342Z.bak`
- `/root/wolo-1-mainnet-prep-markers/hermes-osmosis.toml.pre-noders-rpc-fallback-20260525T065440Z.bak`
- `/root/wolo-1-mainnet-prep-markers/hermes-osmosis.toml.pre-freshstaking-rpc-fallback-20260525T065520Z.bak`
- `/root/wolo-1-mainnet-prep-markers/hermes-osmosis.toml.pre-kjnodes-fallback-20260525T070134Z.bak`

## Safety Confirmations

- `wolo-testnet` was not touched.
- No testnet channel was reused.
- `/etc/tokenchain/hermes.toml` was not touched.
- `tokenchain-relayer.service` was not stopped or modified.
- `wolochain-mainnet-osmosis-relayer.service` remains inactive and was not started.
- No WOLO transfer happened.
- No OSMO transfer happened.
- The 200,000 WOLO liquidity transfer did not happen.
- No liquidity was created.
- No WOLO/USDC pool was created.

## Next Step

Phase 4 should perform only a tiny 1 WOLO test transfer, base amount `1000000uwolo`, over Wolo channel `channel-0` after Tony explicitly confirms.
