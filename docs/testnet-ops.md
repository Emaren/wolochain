# WoloChain Testnet Ops

Verified against the live VPS on April 8, 2026.

## Current Services

- Node service: `wolochaind-testnet.service`
- Settlement service: `wolochain-settlement.service`
- Repo dir: `/var/www/WoloChain`
- Chain home: `/var/lib/wolochaind-testnet`

## Current Environment Files

Node env:

- `/etc/wolochaind-testnet.env`
- `WOLO_HOME=/var/lib/wolochaind-testnet`
- `CHAIN_ID=wolo-testnet`
- `MIN_GAS_PRICES=0uwolo`

Settlement env:

- `/etc/wolochain-settlement.env`
- `WOLO_SETTLEMENT_HOME=/var/lib/wolochaind-testnet`
- `WOLO_SETTLEMENT_RPC_HTTP=http://127.0.0.1:26657`
- `WOLO_SETTLEMENT_REST_URL=http://127.0.0.1:1317`
- `WOLO_SETTLEMENT_CHAIN_ID=wolo-testnet`
- `WOLO_SETTLEMENT_KEYRING_BACKEND=test`
- `WOLO_SETTLEMENT_PAYOUT_KEY_NAME=faucetgrowth`
- `WOLO_SETTLEMENT_PAYOUT_ADDRESS=wolo1jx4n3n2ey6uzfq28kplkmpd2am98xsmcn0nerx`
- `WOLO_SETTLEMENT_ESCROW_ADDRESS=wolo1jx4n3n2ey6uzfq28kplkmpd2am98xsmcn0nerx`
- `WOLO_SETTLEMENT_LISTEN_ADDR=127.0.0.1:8091`
- `WOLO_SETTLEMENT_STATE_DIR=/mnt/HC_Volume_105319120/wolochain/settlement-state`

## Current Service Units

Node:

- `ExecStart=/var/www/WoloChain/build/wolochaind start --home ${WOLO_HOME} --minimum-gas-prices ${MIN_GAS_PRICES}`

Settlement:

- `ExecStart=/var/www/WoloChain/build/wolochaind settlement serve`

## Storage Layout

The extra volume is mounted at:

- `/mnt/HC_Volume_105319120`

Current WoloChain-owned volume paths:

- build cache: `/mnt/HC_Volume_105319120/wolochain/go-cache`
- build temp: `/mnt/HC_Volume_105319120/wolochain/go-tmp`
- settlement state: `/mnt/HC_Volume_105319120/wolochain/settlement-state`

Observed on April 8, 2026:

- root disk `/`: `93%` used
- extra volume `/mnt/HC_Volume_105319120`: `98%` used

The extra volume is now part of production reality, not an optional optimization.

## Verified Runtime State

Checked live on April 8, 2026:

- chain ID: `wolo-testnet`
- moniker: `wolo-testnet-validator-1`
- settlement health: `ok=true`
- settlement payout proof lookup works
- payout replay is idempotent
- current peer count: `0`

The `0` peer state is the biggest current chain-ops gap.

## Build And Deploy

Use the repo-owned Linux build path:

```bash
cd /var/www/WoloChain
git pull --ff-only origin main
GOTOOLCHAIN=go1.24.0 \
GOTMPDIR=/mnt/HC_Volume_105319120/wolochain/go-tmp \
GOCACHE=/mnt/HC_Volume_105319120/wolochain/go-cache \
./scripts/build-linux-amd64.sh build/wolochaind
chown wolo:wolo build/wolochaind
systemctl restart wolochaind-testnet
systemctl restart wolochain-settlement
```

Why this path exists:

- raw Linux `amd64` builds hit a `sonic` native-loader mismatch
- [`scripts/build-linux-amd64.sh`](../scripts/build-linux-amd64.sh) forces the safe compat path
- compile scratch and cache belong on the extra volume, not `/tmp`

## Health Checks

Node status:

```bash
curl -sS http://127.0.0.1:26657/status
curl -sS http://127.0.0.1:26657/net_info
curl -sS http://127.0.0.1:1317/cosmos/base/tendermint/v1beta1/node_info
```

Settlement health:

```bash
curl -sS http://127.0.0.1:8091/settlement/v1/health
```

Systemd:

```bash
systemctl status wolochaind-testnet
systemctl status wolochain-settlement
journalctl -u wolochaind-testnet -n 100 --no-pager
journalctl -u wolochain-settlement -n 100 --no-pager
```

## Settlement API

Health:

```bash
curl -sS http://127.0.0.1:8091/settlement/v1/health
```

Execute payout:

```bash
curl -sS \
  -H 'content-type: application/json' \
  -d '{"request_id":"example-1","to_address":"wolo1...","amount_uwolo":"1","memo":"smoke"}' \
  http://127.0.0.1:8091/settlement/v1/payouts
```

Lookup tx proof:

```bash
curl -sS http://127.0.0.1:8091/settlement/v1/txs/TX_HASH
```

## Known Current Caveats

- The VPS validator currently has `0` peers.
- The settlement signer is still the temporary `faucetgrowth` key.
- Settlement still uses `test` keyring backend.
- `WOLO_SETTLEMENT_AUTH_TOKEN` is empty, so POST safety currently depends on loopback-only binding.
- Escrow and payout are currently pointed at the same address.
- The extra volume is close to full and needs cleanup or expansion soon.

## Next Operator Upgrades

Highest ROI items after this doc sync:

- add real peers and a second validator
- move settlement to a dedicated payout signer
- separate escrow and payout roles
- add auth for settlement POSTs
- add alerts for `n_peers=0`, settlement `5xx`, and low payout balance
