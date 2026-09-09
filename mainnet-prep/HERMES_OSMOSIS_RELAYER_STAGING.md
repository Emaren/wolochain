---
id: "aoe2war.wolochain.hermes-osmosis-relayer-staging"
title: "WoloChain Mainnet Osmosis Hermes Relayer Staging"
type: "reference"
status: "active"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "runtime-evidence"
authority: "ibc-relayer-operating-reference"
reviewed_at: "2026-09-09"
review_interval_days: 30
sensitivity: "restricted"
---

# WoloChain Mainnet Osmosis Hermes Relayer Staging

Status: the staged Hermes configuration remains the operating reference and the
`wolo-1` ↔ `osmosis-1` ICS-20 path is live. Later authorized phases already
completed the 1 WOLO test transfer, 200,000 WOLO liquidity transfer, and Pool
`3461` launch. This document is not authority to repeat those actions or move
funds.

## Operational Paths

- Config path: `/etc/wolochain-mainnet/hermes-osmosis.toml`
- Service path: `/etc/systemd/system/wolochain-mainnet-osmosis-relayer.service`
- Relayer state/home path: `/var/lib/wolochain-mainnet-relayer`

## Validation

Hermes config validation command run:

```bash
HOME=/var/lib/wolochain-mainnet-relayer \
/usr/local/bin/hermes --config /etc/wolochain-mainnet/hermes-osmosis.toml \
  config validate
```

Result:

```txt
SUCCESS configuration is valid
```

Systemd unit validation command run:

```bash
systemd-analyze verify /etc/systemd/system/wolochain-mainnet-osmosis-relayer.service
```

Result:

```txt
completed with no errors
```

## Chain Entries

Exact `wolo-1` chain entry staged:

```toml
[[chains]]
id = 'wolo-1'
type = 'CosmosSdk'
ccv_consumer_chain = false
rpc_addr = 'https://rpc-mainnet.aoe2war.com'
grpc_addr = 'http://127.0.0.1:9190'
event_source = { mode = 'push', url = 'wss://rpc-mainnet.aoe2war.com/websocket', batch_delay = '500ms' }
rpc_timeout = '10s'
trusted_node = false
account_prefix = 'wolo'
key_name = 'wolo-mainnet-osmosis-relayer'
store_prefix = 'ibc'
default_gas = 300000
max_gas = 2000000
gas_price = { price = 0.001, denom = 'uwolo' }
gas_multiplier = 1.3
max_msg_num = 30
max_tx_size = 180000
clock_drift = '10s'
max_block_time = '30s'
trusting_period = '9days'
trust_threshold = { numerator = '1', denominator = '3' }
```

Exact `osmosis-1` chain entry staged:

```toml
[[chains]]
id = 'osmosis-1'
type = 'CosmosSdk'
ccv_consumer_chain = false
rpc_addr = 'https://rpc.osmosis.zone'
grpc_addr = 'https://grpc.osmosis.zone:443'
event_source = { mode = 'push', url = 'wss://rpc.osmosis.zone/websocket', batch_delay = '500ms' }
rpc_timeout = '10s'
trusted_node = false
account_prefix = 'osmo'
key_name = 'osmosis-mainnet-wolo-relayer'
store_prefix = 'ibc'
default_gas = 400000
max_gas = 3000000
gas_price = { price = 0.03, denom = 'uosmo' }
gas_multiplier = 1.3
max_msg_num = 30
max_tx_size = 180000
clock_drift = '10s'
max_block_time = '30s'
trusting_period = '9days'
trust_threshold = { numerator = '1', denominator = '3' }
```

Current `osmosis-1` endpoint values after Phase 3 fallback handling:

```toml
rpc_addr = 'https://osmosis.rpc.kjnodes.com'
grpc_addr = 'https://grpc.osmosis.validatus.com:443'
event_source = { mode = 'push', url = 'wss://osmosis.rpc.kjnodes.com/websocket', batch_delay = '500ms' }
```

The Osmosis primary RPC `https://rpc.osmosis.zone` returned HTTP 429 during proof-bearing Hermes steps. The isolated WoloChain Hermes config was backed up before each endpoint fallback. `/etc/tokenchain/hermes.toml` was not touched.

## Review Renewal — 2026-09-09 UTC

Read-only chain queries reconfirmed `transfer/channel-0` open on `wolo-1` with
counterparty `channel-110224`, and the Osmosis side open with the reciprocal
counterparty. The privileged Hermes config still uses Wolo RPC
`https://rpc-mainnet.aoe2war.com` plus the Osmosis fallback
`https://osmosis.rpc.kjnodes.com` / `https://grpc.osmosis.validatus.com:443`.
`wolochain-mainnet-osmosis-relayer.service` was inactive at review time; no
relayer was started and no IBC packet or fund movement was created.

## Phase 3 Safety Confirmations — historical

- TokenChain relayer was not touched.
- `/etc/tokenchain/hermes.toml` was not modified.
- `/var/www/tokenchain-ops/relayer/hermes-config.toml` was not modified.
- At Phase 3 close, `tokenchain-relayer.service` was active and was not stopped or modified by the Wolo IBC work. It was inactive at the 2026-09-09 review observation; this document does not authorize changing it.
- `wolochain-mainnet-osmosis-relayer.service` is inactive and was not started.
- IBC clients, connections, and channels were created only for the approved Phase 3 `wolo-1` to `osmosis-1` path.
- At Phase 3 close, no WOLO or OSMO transfer had happened.
- At Phase 3 close, no liquidity or WOLO/USDC pool had been created.
- Those statements are historical Phase 3 boundaries; later authorized phases
  completed the test transfer, liquidity transfer, and Pool `3461` launch.

## Phase 3 Commands

Initial command run. This created the client pair and Wolo `connection-0`, then stopped before completing the connection because the Osmosis primary RPC returned HTTP 429:

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

Connection handshake completion commands run:

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

## Phase 3 Result

- Wolo client ID: `07-tendermint-0`
- Osmosis client ID: `07-tendermint-3705`
- Wolo connection ID: `connection-0`
- Osmosis connection ID: `connection-11058`
- Wolo transfer channel ID: `channel-0`
- Osmosis transfer channel ID: `channel-110224`
- Channel state: `Open` on both sides.
- Port: `transfer` on both sides.
- Ordering: `unordered`.
- Channel version: `ics20-1`.
- Wolo relayer balance after creation: `99998485uwolo`.
- Osmosis relayer balance after creation: `199266uosmo`.
- Marker: `/root/wolo-1-mainnet-prep-markers/wolo-osmosis-ibc-path-20260525T070440Z.txt`

## Historical Phase 4 Gate — superseded

The Phase 4 transfer gate recorded here was later satisfied through the separately
documented authorized test transfer. Subsequent receipts also record the
200,000-WOLO liquidity transfer and Pool `3461` launch. Do not replay those
operations from this staging document. Current post-launch work is metadata and
visibility, not another transfer or pool creation.
