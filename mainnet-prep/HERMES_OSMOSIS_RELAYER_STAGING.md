# WoloChain Mainnet Osmosis Hermes Relayer Staging

Status: Phase 2 staging complete. Do not create IBC clients, connections, channels, transfers, liquidity, or pools from this document without Tony's explicit confirmation.

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

## Safety Confirmations

- TokenChain relayer was not touched.
- `/etc/tokenchain/hermes.toml` was not modified.
- `/var/www/tokenchain-ops/relayer/hermes-config.toml` was not modified.
- `tokenchain-relayer.service` remains active and was not stopped or modified.
- `wolochain-mainnet-osmosis-relayer.service` is inactive and was not started.
- No IBC clients were created.
- No IBC connections were created.
- No IBC channels were created.
- No WOLO transfers happened.
- No OSMO transfers happened.
- No liquidity was created.
- No WOLO/USDC pool was created.

## Prepared Phase 3 Command

NOT RUN:

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

## Blockers Before Phase 3

- `wolo-1` relayer key is missing.
- `osmosis-1` relayer key is missing.
- Relayer wallets need funded with small gas balances:
  - `uwolo` for WoloChain relayer fees.
  - `uosmo` for Osmosis relayer fees.
- `systemctl daemon-reload` has not been run for the staged service unit.
- `wolochain-mainnet-osmosis-relayer.service` has not been started.

