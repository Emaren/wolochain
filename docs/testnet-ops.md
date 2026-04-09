# WoloChain Testnet Ops

Verified against the live VPS on April 9, 2026.

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
- root-owned and not readable by the unprivileged `tony` user
- verified from root-level env inspection plus live service health:
  - `WOLO_SETTLEMENT_HOME=/var/lib/wolochaind-testnet`
  - `WOLO_SETTLEMENT_RPC_HTTP=http://127.0.0.1:26657`
  - `WOLO_SETTLEMENT_REST_URL=http://127.0.0.1:1317`
  - `WOLO_SETTLEMENT_PUBLIC_REST_URL=https://rest.aoe2hdbets.com`
  - `WOLO_SETTLEMENT_CHAIN_ID=wolo-testnet`
  - `WOLO_SETTLEMENT_KEYRING_BACKEND=test`
  - `WOLO_SETTLEMENT_PAYOUT_KEY_NAME=payout`
  - `WOLO_SETTLEMENT_PAYOUT_ADDRESS=wolo1cy04t5af0mr9d8n6rrzgr8e9j4vuf42nfg02q5`
  - `WOLO_SETTLEMENT_ESCROW_ADDRESS=wolo1t4jq7wd4x030t9f0yfqfq74pt4pmaep5nu67y4`
  - `WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO=1000000000`
  - `WOLO_SETTLEMENT_FEE_HEADROOM_UWOLO=10000000`
  - `WOLO_SETTLEMENT_LISTEN_ADDR=127.0.0.1:8091`
  - `WOLO_SETTLEMENT_STATE_DIR=/mnt/HC_Volume_105319120/wolochain/settlement-state`
  - `WOLO_SETTLEMENT_AUTH_TOKEN` is set in the live env but should stay masked in docs and operator output
- `WOLO_SETTLEMENT_FEES` is currently optional and may remain unset

Role semantics:

- `WOLO_SETTLEMENT_PAYOUT_KEY_NAME` is the signer WoloChain uses for settlement sends.
- `WOLO_SETTLEMENT_ESCROW_ADDRESS` affects proof classification and operator warnings; it does not create escrow semantics by itself.
- WoloChain does not create market semantics by config alone; the app must actually send stakes to escrow and interpret them.
- On April 9, 2026 the live test keyring contains `faucetgrowth`, `payout`, and `escrow`.
- The live dedicated payout address is `wolo1cy04t5af0mr9d8n6rrzgr8e9j4vuf42nfg02q5`.
- The live dedicated escrow address is `wolo1t4jq7wd4x030t9f0yfqfq74pt4pmaep5nu67y4`.
- The live payout address has `2000000000uwolo` available, with reserve floor and fee headroom enforced by the settlement service.
- The `payout.info` and `escrow.info` files are only readable by `wolo` unless the operator runs checks as root or `sudo -u wolo`.

Operator defaults currently in live use:

```bash
WOLO_SETTLEMENT_HOME=/var/lib/wolochaind-testnet
WOLO_SETTLEMENT_RPC_HTTP=http://127.0.0.1:26657
WOLO_SETTLEMENT_REST_URL=http://127.0.0.1:1317
WOLO_SETTLEMENT_PUBLIC_REST_URL=https://rest.aoe2hdbets.com
WOLO_SETTLEMENT_CHAIN_ID=wolo-testnet
WOLO_SETTLEMENT_KEYRING_BACKEND=test
WOLO_SETTLEMENT_PAYOUT_KEY_NAME=payout
WOLO_SETTLEMENT_PAYOUT_ADDRESS=wolo1cy04t5af0mr9d8n6rrzgr8e9j4vuf42nfg02q5
WOLO_SETTLEMENT_ESCROW_ADDRESS=wolo1t4jq7wd4x030t9f0yfqfq74pt4pmaep5nu67y4
WOLO_SETTLEMENT_FEES=
WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO=1000000000
WOLO_SETTLEMENT_FEE_HEADROOM_UWOLO=10000000
WOLO_SETTLEMENT_AUTH_TOKEN=<masked-live-secret>
WOLO_SETTLEMENT_LISTEN_ADDR=127.0.0.1:8091
WOLO_SETTLEMENT_STATE_DIR=/mnt/HC_Volume_105319120/wolochain/settlement-state
```

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

Operational note:

- the extra volume has already been used hard enough that space pressure matters
- verify `df -h / /mnt/HC_Volume_105319120` before large backups, rebuilds, or moving more live state there
- if the extra-volume backup target is too full, use a fallback backup root such as `/home/tony/wolochain-settlement-backups`

The extra volume is part of production reality, not an optional optimization.

## Verified Runtime State

Checked live on April 9, 2026:

- chain ID: `wolo-testnet`
- moniker: `wolo-testnet-validator-1`
- settlement health: `ok=true`
- node service state: `active`
- settlement service state: `active`
- public REST host responds: `https://rest.aoe2hdbets.com`
- public RPC host responds: `https://rpc.aoe2hdbets.com`
- current peer count: `0`
- grouped validate route is live and bearer-protected
- escrow recent / verify routes are live
- request-level inspect / recent CLI commands are live
- grouped run inspect / recent CLI commands are live

Current live caveats:

- the VPS validator still has `0` peers
- settlement still uses the `test` keyring backend
- peer health is now the main chain-ops gap; the settlement cutover itself is done

## Build And Deploy

Use the repo-owned Linux build path:

```bash
cd /var/www/WoloChain
git pull --ff-only origin main
sudo install -d -o tony -g tony -m 0755 /mnt/HC_Volume_105319120/wolochain/go-tmp
sudo install -d -o tony -g tony -m 0755 /mnt/HC_Volume_105319120/wolochain/go-cache
GOTOOLCHAIN=go1.24.0 \
GOTMPDIR=/mnt/HC_Volume_105319120/wolochain/go-tmp \
GOCACHE=/mnt/HC_Volume_105319120/wolochain/go-cache \
./scripts/build-linux-amd64.sh build/wolochaind
sudo install -o wolo -g wolo -m 0755 build/wolochaind /var/www/WoloChain/build/wolochaind
sudo systemctl restart wolochaind-testnet.service
sudo systemctl restart wolochain-settlement.service
```

Why this path exists:

- raw Linux `amd64` builds hit a `sonic` native-loader mismatch
- [`scripts/build-linux-amd64.sh`](../scripts/build-linux-amd64.sh) forces the safe compat path
- compile scratch and cache belong on the extra volume, not `/tmp`
- the current `tony` sudo policy requires an interactive password and does not allow `sudo -n`; use explicit `sudo install`, `sudo systemctl`, and `sudo -u wolo ...` commands during live work
- if the node binary on disk is replaced, restart the node service so it does not keep running a deleted in-memory binary

## Operator Helpers

Repo-owned helpers:

- `./scripts/check-settlement-cutover.sh`
  - config, key, doctor, and route checks
  - best used when the intended env is exported in the current shell
- `./scripts/check-settlement-alerts.sh`
  - machine-readable JSON health / alert output with exit code `0` when healthy and `1` when alerts are present
- `./scripts/verify-live-settlement.sh`
  - focused live surface check for auth, grouped routes, escrow routes, and CLI availability
- `./scripts/backup-live-settlement.sh`
  - rollback-oriented backup of the current settlement binary, env file, state dir, and current health / unit snapshots
- `./scripts/restore-live-settlement.sh`
  - restore a backup directory created by `backup-live-settlement.sh` and restart the settlement service

For live truth after deploy or restart, prefer this sequence:

```bash
cd /var/www/WoloChain
sudo ./scripts/verify-live-settlement.sh
curl -s http://127.0.0.1:26657/net_info | jq '{listening:.result.listening,n_peers:.result.n_peers,peers:[.result.peers[].node_info.moniker]}'
systemctl status --no-pager wolochaind-testnet.service wolochain-settlement.service
```

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

Env inspection:

```bash
systemctl show -p EnvironmentFiles wolochain-settlement.service
ENV_FILE=$(systemctl show -p EnvironmentFiles --value wolochain-settlement.service | awk '{print $1}' | sed 's/^-//')
sudo grep -E '^(WOLO_SETTLEMENT_(KEY_NAME|KEYRING_BACKEND|PAYOUT_ADDRESS|ESCROW_ADDRESS|AUTH_TOKEN|STATE_DIR|PUBLIC_REST_URL|MIN_PAYOUT_BALANCE_UWOLO|FEE_HEADROOM_UWOLO)|WOLO_(CHAIN_ID|NODE|HOME))=' "$ENV_FILE" \
  | sed -E 's#^(WOLO_SETTLEMENT_AUTH_TOKEN)=.*#\1=***MASKED***#'
```

## Settlement API

Current live surface on April 9, 2026:

- `GET /settlement/v1/health` is live on `127.0.0.1:8091`
- `POST /settlement/v1/payouts` is live and bearer-protected
- `POST /settlement/v1/runs/validate` is live and bearer-protected
- `POST /settlement/v1/runs` is part of the live settlement surface
- `GET /settlement/v1/escrow/deposits` is live
- `GET /settlement/v1/escrow/txs/{tx_hash}` is live
- the live CLI exposes `doctor`, `execute`, `lookup`, `inspect`, `recent`, `run`, `escrow`, and `serve`

When `WOLO_SETTLEMENT_AUTH_TOKEN` is set:

- `POST /settlement/v1/payouts` requires `Authorization: Bearer ...`
- `POST /settlement/v1/runs/validate` requires `Authorization: Bearer ...`
- `POST /settlement/v1/runs` requires `Authorization: Bearer ...`
- `GET /settlement/v1/health` stays open
- `GET /settlement/v1/txs/{tx_hash}` stays open
- `GET /settlement/v1/escrow/txs/{tx_hash}` stays open
- `GET /settlement/v1/escrow/deposits` stays open

Dry-run grouped settlement run:

```bash
curl -sS \
  -H "authorization: Bearer $WOLO_SETTLEMENT_AUTH_TOKEN" \
  -H 'content-type: application/json' \
  -d '{
    "settlement_run_id":"run-2026-04-08-001",
    "source_app":"settler",
    "source_event_id":"event-42",
    "note":"weekly settlement",
    "memo":"weekly payouts",
    "payouts":[
      {"to_address":"wolo1recipienta000000000000000000000000000000","amount_uwolo":"1500000"},
      {"to_address":"wolo1recipientb000000000000000000000000000000","amount_uwolo":"2500000"}
    ]
  }' \
  http://127.0.0.1:8091/settlement/v1/runs/validate
```

Execute grouped settlement run:

```bash
curl -sS \
  -H "authorization: Bearer $WOLO_SETTLEMENT_AUTH_TOKEN" \
  -H 'content-type: application/json' \
  -d @run.json \
  http://127.0.0.1:8091/settlement/v1/runs
```

Lookup tx proof:

```bash
curl -sS http://127.0.0.1:8091/settlement/v1/txs/TX_HASH
```

Verify that a transfer really hit the configured escrow address:

```bash
curl -sS \
  "http://127.0.0.1:8091/settlement/v1/escrow/txs/TX_HASH?expected_sender=wolo1sender...&expected_amount_uwolo=1500000"
```

Recent escrow deposit discovery:

```bash
curl -sS "http://127.0.0.1:8091/settlement/v1/escrow/deposits?limit=20"
curl -sS "http://127.0.0.1:8091/settlement/v1/escrow/deposits?limit=20&sender=wolo1sender..."
```

Inspect stored settlement state by request id:

```bash
build/wolochaind settlement inspect --request-id example-1
build/wolochaind settlement inspect --request-id example-1 --summary-only
build/wolochaind settlement recent --status failed --limit 20
build/wolochaind settlement recent --status refused --summary-only
```

Inspect grouped settlement state by run id:

```bash
build/wolochaind settlement run inspect --run-id run-2026-04-08-001
build/wolochaind settlement run inspect --run-id run-2026-04-08-001 --summary-only
build/wolochaind settlement run recent --status partial --limit 20
build/wolochaind settlement run recent --status failed --summary-only
```

Escrow verification and discovery from the CLI:

```bash
build/wolochaind settlement escrow verify --tx-hash TX_HASH
build/wolochaind settlement escrow verify --tx-hash TX_HASH --expected-sender wolo1sender... --expected-amount-uwolo 1500000
build/wolochaind settlement escrow recent --limit 20
build/wolochaind settlement escrow recent --limit 20 --sender wolo1sender...
```

## Grouped Settlement Boundary

Grouped settlement runs are generic WoloChain settlement wrappers, not app logic.

WoloChain owns:

- validating addresses and amounts
- deriving stable per-line request ids when omitted
- checking payout balance, reserve floor, and fee headroom
- executing sends from the payout signer
- storing run state and per-request state
- exposing proof links and operator inspection surfaces

The caller owns:

- deciding who won
- deciding payout amounts
- market or pool math
- refund policy
- any app-specific reconciliation or user messaging

Safe operator flow:

1. Caller computes payouts outside WoloChain.
2. Caller submits `runs/validate`.
3. Operator reviews totals, warnings, reserve impact, and fee estimate.
4. Caller submits the exact same payload to `runs`.
5. Operator inspects the grouped run and, if needed, the per-request records.

If `WOLO_SETTLEMENT_FEES` is unset, grouped dry-runs still validate reserve / headroom math but return a warning that deterministic fee estimates are unavailable.

## Escrow Recovery Boundary

The escrow helpers stay generic and read-only.

WoloChain can answer:

- did tx `X` send `uwolo` into the configured escrow address
- who sent it
- how much arrived
- what proof link to use
- what recent successful deposits hit escrow

WoloChain still does not answer:

- what market the deposit belonged to
- whether a deposit should open, match, refund, or settle a market
- any betting or pool interpretation

That keeps the recovery surface useful for AoE2HDBets without pushing app logic into this repo.

## Verification Helpers

Focused live verification:

```bash
cd /var/www/WoloChain
sudo ./scripts/verify-live-settlement.sh
```

What it checks:

- node and settlement services are active
- health route returns `200`
- missing bearer auth is rejected when auth is enabled
- grouped dry-run route exists and responds structurally
- escrow read-only routes exist and respond structurally
- request-level `inspect` / `recent` commands are available
- grouped `run inspect` / `run recent` commands are available
- `settlement escrow ...` CLI commands are available

The script intentionally avoids live payout execution. It uses:

- an invalid-address payout POST for auth probing
- a grouped `runs/validate` dry-run only
- an invalid tx hash against the escrow verify route
- a read-only escrow recent query
- missing request / run ids for inspect checks

Machine-readable alerts:

```bash
cd /var/www/WoloChain
./scripts/check-settlement-alerts.sh
```

Alert script contract:

- exit `0`: settlement surface is healthy for the checks below
- exit `1`: at least one operator-relevant alert is present
- exit `2`: local script / config / runtime problem prevented a valid check

Current checks:

- settlement service reachable on the target base URL
- `settlement doctor` reports `ok=true`
- auth is enabled
- payout key exists
- escrow key exists
- payout and escrow are distinct
- payout balance meets the configured reserve floor
- public proof URL is set
- grouped settlement route exists
- escrow proof / discovery routes exist

If the current operator shell cannot read the `wolo` keyring files directly, key-presence checks may degrade to warnings instead of false alert failures; service-side doctor / health / route drift still fails hard.

## Live Rollout Status

The settlement cutover is complete.

What is live now:

- dedicated payout signer
- distinct escrow address
- auth-protected mutating settlement routes
- grouped settlement validate surface
- grouped settlement CLI commands
- escrow verify / recent routes
- public proof URL wiring
- reserve-floor and fee-headroom enforcement
- persisted settlement request / run state on the extra volume

What still needs follow-through:

1. fix peer isolation on the validator
2. wire `check-settlement-alerts.sh` into cron or VPSSentry
3. prove the full AoE2HDBets -> escrow -> recovery -> settlement path with a real end-to-end wager
4. keep docs aligned with live truth after changes

## Settlement State Backup

The request / run state under `/mnt/HC_Volume_105319120/wolochain/settlement-state` is operational truth. Back it up before risky changes.

Preferred helper:

```bash
cd /var/www/WoloChain
BACKUP_ROOT=/home/tony/wolochain-settlement-backups ./scripts/backup-live-settlement.sh
```

That helper snapshots:

- current `build/wolochaind`
- current `/etc/wolochain-settlement.env`
- current settlement state dir
- current settlement service unit / status
- current settlement health output
- machine-readable metadata at `metadata.json`

Preferred restore helper:

```bash
cd /var/www/WoloChain
BACKUP_DIR="/path/to/backup-dir" ./scripts/restore-live-settlement.sh
```

Manual restore path remains:

```bash
backup_dir="/path/to/backup-dir"
sudo systemctl stop wolochain-settlement.service
sudo install -o wolo -g wolo -m 0755 "$backup_dir/wolochaind" /var/www/WoloChain/build/wolochaind
sudo install -o root -g root -m 0640 "$backup_dir/wolochain-settlement.env" /etc/wolochain-settlement.env
sudo rm -rf /mnt/HC_Volume_105319120/wolochain/settlement-state
sudo cp -a "$backup_dir/settlement-state" /mnt/HC_Volume_105319120/wolochain/settlement-state
sudo systemctl start wolochain-settlement.service
```

## Known Current Caveats

- The VPS validator currently has `0` peers.
- Settlement currently uses the `test` keyring backend.
- The extra volume needs to be watched for space pressure.
- The highest-ROI WoloChain work now is networking, monitoring, and clean operator proof — not more chain-side abstractions.

## Next Operator Upgrades

Highest-ROI items after this doc sync:

- add real peers and verify public P2P reachability
- wire `check-settlement-alerts.sh` into cron or VPSSentry
- run one real end-to-end AoE2HDBets escrowed wager against the live rail
- run one grouped settlement dry-run from the app against live WoloChain
- update docs immediately when live operator truth changes
