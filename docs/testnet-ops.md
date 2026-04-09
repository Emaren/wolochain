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
- currently known from live service/runtime checks:
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
  - `WOLO_SETTLEMENT_AUTH_TOKEN` is currently unset
- not directly observable without privileged env access on April 9, 2026:
  - `WOLO_SETTLEMENT_PUBLIC_REST_URL`
  - `WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO`
  - `WOLO_SETTLEMENT_FEE_HEADROOM_UWOLO`
  - `WOLO_SETTLEMENT_FEES`

Role semantics:

- `WOLO_SETTLEMENT_PAYOUT_KEY_NAME` is the only signer WoloChain uses for settlement sends.
- If that key still points at `faucetgrowth`, health output will warn.
- `WOLO_SETTLEMENT_ESCROW_ADDRESS` only affects proof classification and operator warnings.
- WoloChain does not create escrow semantics by config alone; the app must actually send stakes there.
- On April 9, 2026 the live test keyring contains `faucetgrowth`, `payout`, and `escrow`.
- The staged dedicated payout address is `wolo1cy04t5af0mr9d8n6rrzgr8e9j4vuf42nfg02q5`.
- The staged dedicated escrow address is `wolo1t4jq7wd4x030t9f0yfqfq74pt4pmaep5nu67y4`.
- The staged dedicated payout address has already been funded with `2000000000` `uwolo`.
- The new `payout.info` and `escrow.info` files are only readable by `wolo` unless the operator runs the checks as root or `sudo -u wolo`.

Expected live env split after hardening:

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
WOLO_SETTLEMENT_AUTH_TOKEN=<long-random-secret>
WOLO_SETTLEMENT_LISTEN_ADDR=127.0.0.1:8091
WOLO_SETTLEMENT_STATE_DIR=/mnt/HC_Volume_105319120/wolochain/settlement-state
```

Operator defaults used by the repo-owned cutover helpers:

- payout key name: `payout`
- escrow key name: `escrow`
- keyring backend: `test`
- fixed fees: unset by default
- reserve floor: `1000000000` `uwolo`
- fee headroom: `10000000` `uwolo`

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

Observed on April 9, 2026:

- root disk `/`: `95%` used
- extra volume `/mnt/HC_Volume_105319120`: `100%` used during the latest cutover prep
- the default extra-volume backup target is therefore not reliable right now; use `BACKUP_ROOT=/home/tony/wolochain-settlement-backups` until space is reclaimed

The extra volume is now part of production reality, not an optional optimization.

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

Observed rollout gap on the live VPS:

- settlement still uses the temporary `faucetgrowth` signer even though the dedicated `payout` and `escrow` keys are now staged in the live keyring
- auth token is not set, so payout POST safety still depends on loopback-only binding
- the deployed settlement binary is older than the current repo surface
- `POST /settlement/v1/runs/validate` currently returns `404`
- the live CLI still exposes only `doctor`, `execute`, `lookup`, and `serve`

The `0` peer state is still a chain-ops gap, but it is not the focus of this settlement rollout pass.

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
sudo systemctl restart wolochain-settlement
```

Why this path exists:

- raw Linux `amd64` builds hit a `sonic` native-loader mismatch
- [`scripts/build-linux-amd64.sh`](../scripts/build-linux-amd64.sh) forces the safe compat path
- compile scratch and cache belong on the extra volume, not `/tmp`
- on April 9, 2026 those extra-volume cache dirs were still owned by `root:root`, so the build needs a privileged ownership fix first
- the current `tony` sudo policy requires an interactive password and does not allow `sudo -n`; use explicit `sudo install`, `sudo systemctl`, and `sudo -u wolo ...` commands during the cutover
- restarting `wolochaind-testnet.service` is not required for this settlement-only cutover

## Operator Helpers

Repo-owned scripts added for the settlement cutover:

- `./scripts/check-settlement-cutover.sh`
  - pre-cutover mode: env + key + doctor checks with `CHECK_SERVICE=0`
  - post-cutover mode: the same checks plus live route verification
- `./scripts/check-settlement-alerts.sh`
  - machine-readable JSON health/alert output with exit code `0` when healthy and `1` when alerts are present
- `./scripts/verify-live-settlement.sh`
  - focused live surface check for auth, grouped routes, escrow routes, and CLI availability
- `./scripts/backup-live-settlement.sh`
  - rollback-oriented backup of the current settlement binary, env file, state dir, and current health/unit snapshots
- `./scripts/restore-live-settlement.sh`
  - restore a backup directory created by `backup-live-settlement.sh` and restart the settlement service

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

Current live status on April 9, 2026:

- `GET /settlement/v1/health` is live on `127.0.0.1:8091`
- `POST /settlement/v1/payouts` is live and unauthenticated because `WOLO_SETTLEMENT_AUTH_TOKEN` is unset
- `POST /settlement/v1/runs/validate` is not live yet on the current systemd service
- `build/wolochaind settlement inspect`, `build/wolochaind settlement recent`, and `build/wolochaind settlement run ...` are not yet live on the VPS
- those newer routes and CLI surfaces still require a settlement binary rebuild and service restart before they are available on the systemd service

Post-rollout target surface:

Health:

```bash
curl -sS http://127.0.0.1:8091/settlement/v1/health
```

When `WOLO_SETTLEMENT_AUTH_TOKEN` is set:

- `POST /settlement/v1/payouts` requires `Authorization: Bearer ...`
- `POST /settlement/v1/runs/validate` requires `Authorization: Bearer ...`
- `POST /settlement/v1/runs` requires `Authorization: Bearer ...`
- `GET /settlement/v1/health` stays open
- `GET /settlement/v1/txs/{tx_hash}` stays open
- `GET /settlement/v1/escrow/txs/{tx_hash}` stays open
- `GET /settlement/v1/escrow/deposits` stays open

Execute payout:

```bash
curl -sS \
  -H "authorization: Bearer $WOLO_SETTLEMENT_AUTH_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"request_id":"example-1","to_address":"wolo1...","amount_uwolo":"1","memo":"smoke"}' \
  http://127.0.0.1:8091/settlement/v1/payouts
```

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

Key grouped-run response fields:

- dry-run response: `ok`, `status`, `requested_total_uwolo`, `projected_remaining_uwolo`, `estimated_fee_total_uwolo`, `failure_code`, `warnings`, `payouts`
- execute response: `ok`, `status`, `executed_payout_count`, `confirmed_payout_count`, `accepted_payout_count`, `refused_payout_count`, `replay_payout_count`, `executed_total_uwolo`, `failure_code`, `detail`, `payouts`
- per-payout response fields: `request_id`, `status`, `outcome`, `failure_code`, `retryable`, `idempotent_replay`, `tx_hash`, `canonical_tx_lookup_preferred`, `canonical_tx_lookup_public`, `canonical_tx_lookup_internal`

Lookup tx proof:

```bash
curl -sS http://127.0.0.1:8091/settlement/v1/txs/TX_HASH
```

Proof response fields:

- `canonical_tx_lookup_preferred`: operator/app-safe link to prefer
- `canonical_tx_lookup_public`: public REST proof URL when configured
- `canonical_tx_lookup_internal`: loopback/internal REST proof URL
- `canonical_tx_lookup`: legacy-compatible field, still present

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
build/wolochaind settlement run recent --status failed --failure-code PAYOUT_RESERVE_FLOOR_HIT --summary-only
```

Escrow verification and discovery from the CLI:

```bash
build/wolochaind settlement escrow verify --tx-hash TX_HASH
build/wolochaind settlement escrow verify --tx-hash TX_HASH --expected-sender wolo1sender... --expected-amount-uwolo 1500000
build/wolochaind settlement escrow recent --limit 20
build/wolochaind settlement escrow recent --limit 20 --sender wolo1sender...
```

Operator questions these commands should answer quickly:

- what happened: `summary.outcome` / `summary.status`
- what signer was used: `summary.signer_role` / `summary.signer_address`
- why it failed or refused: `summary.failure_code` / `summary.detail`
- whether it replayed idempotently: `summary.idempotent_replay`
- what proof links exist: `summary.canonical_tx_lookup_preferred` plus public/internal fields

Grouped-run operator questions these commands should answer quickly:

- what run was attempted: `summary.settlement_run_id`, `summary.source_app`, `summary.source_event_id`, `summary.note`
- how many payouts were requested vs executed: `summary.requested_payout_count`, `summary.executed_payout_count`
- what totals were requested vs executed: `summary.requested_total_uwolo`, `summary.executed_total_uwolo`
- which payouts succeeded, refused, or replayed: inspect `record.response.payouts`
- what proof links exist per payout: inspect `canonical_tx_lookup_preferred`, `canonical_tx_lookup_public`, and `canonical_tx_lookup_internal` on each payout line

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

If `WOLO_SETTLEMENT_FEES` is unset, grouped dry-runs still validate reserve/headroom math but return a warning that deterministic fee estimates are unavailable.

No extra refund primitive was added in this pass. The existing single-payout and grouped-run rails already cover generic refund or reversal sends as long as the caller provides the recipient, amount, and metadata.

## Escrow Recovery Boundary

The new escrow helpers stay generic and read-only.

WoloChain can now answer:

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

## Verification Helper

This repo now includes two boring verification paths.

Pre-cutover config/key/doctor check:

```bash
cd /var/www/WoloChain
set -a
. /tmp/wolochain-settlement.env
set +a
WOLOCHAIND_SUDO_USER=wolo \
CHECK_SERVICE=0 \
./scripts/check-settlement-cutover.sh
```

What the cutover checker verifies:

- required env values are set
- payout key exists
- escrow key exists
- payout/escrow addresses are distinct
- auth token is set
- public REST URL is set
- reserve floor and fee headroom are set
- `settlement doctor` returns healthy output
- if `CHECK_SERVICE!=0`, the live grouped and escrow routes exist too

Post-cutover config + live surface check:

```bash
cd /var/www/WoloChain
set -a
. /etc/wolochain-settlement.env
set +a
WOLOCHAIND_SUDO_USER=wolo \
./scripts/check-settlement-cutover.sh
WOLOCHAIND_SUDO_USER=wolo \
./scripts/check-settlement-alerts.sh
```

The lower-level live verifier remains available when you only want the HTTP/CLI surface check:

```bash
cd /var/www/WoloChain
set -a
. /etc/wolochain-settlement.env
set +a
WOLOCHAIND_SUDO_USER=wolo \
./scripts/verify-live-settlement.sh
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
- missing request/run ids for inspect checks

Optional deeper escrow verification:

```bash
cd /var/www/WoloChain
set -a
. /etc/wolochain-settlement.env
set +a
WOLOCHAIND_SUDO_USER=wolo \
VERIFY_ESCROW_TX_HASH='<known-live-deposit-tx-hash>' \
VERIFY_ESCROW_EXPECTED_SENDER='wolo1sender...' \
VERIFY_ESCROW_EXPECTED_AMOUNT_UWOLO='1500000' \
./scripts/verify-live-settlement.sh
```

## Machine-Readable Alert Check

Daily/cron-friendly alert surface:

```bash
cd /var/www/WoloChain
set -a
. /tmp/wolochain-settlement.env
set +a
./scripts/check-settlement-alerts.sh
```

Alert script contract:

- exit `0`: settlement surface is healthy for the checks below
- exit `1`: at least one operator-relevant alert is present
- exit `2`: local script/config/runtime problem prevented a valid check

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
- escrow proof/discovery routes exist

The output is JSON so VPSSentry, cron, or a future monitor can consume it directly.
If the current operator shell cannot read the `wolo` keyring files directly, the key-presence checks degrade to warnings instead of false alert failures; service-side doctor/health/route drift still fails hard.

## Live Rollout Checklist

Manual decisions still required before the final privileged edit:

1. Confirm the staged dedicated payout address `wolo1cy04t5af0mr9d8n6rrzgr8e9j4vuf42nfg02q5` is the signer you want the live service to use.
2. Confirm the staged dedicated escrow address `wolo1t4jq7wd4x030t9f0yfqfq74pt4pmaep5nu67y4` is the escrow classifier you want in the live service.
3. Decide whether to keep the current `test` keyring backend or migrate deliberately to `file` or `os`.
4. Decide whether to set `WOLO_SETTLEMENT_FEES` for deterministic grouped-run fee estimates.
5. Choose a real `WOLO_SETTLEMENT_AUTH_TOKEN`.
6. Confirm `WOLO_SETTLEMENT_PUBLIC_REST_URL=https://rest.aoe2hdbets.com`.

The current VPS already has staged `payout` and `escrow` keys in `/var/lib/wolochaind-testnet/keyring-test`.
Use these commands to verify them from an interactive `sudo` shell:

```bash
sudo -u wolo /var/www/WoloChain/build/wolochaind keys show payout \
  --address \
  --home /var/lib/wolochaind-testnet \
  --keyring-backend test

sudo -u wolo /var/www/WoloChain/build/wolochaind keys show escrow \
  --address \
  --home /var/lib/wolochaind-testnet \
  --keyring-backend test
```

If you need to recreate or recover them instead, use:

```bash
sudo -u wolo /var/www/WoloChain/build/wolochaind keys add payout \
  --recover \
  --home /var/lib/wolochaind-testnet \
  --keyring-backend test

sudo -u wolo /var/www/WoloChain/build/wolochaind keys add escrow \
  --recover \
  --home /var/lib/wolochaind-testnet \
  --keyring-backend test
```

One-shot cutover order:

1. Run `BACKUP_ROOT=/home/tony/wolochain-settlement-backups ./scripts/backup-live-settlement.sh`.
2. Verify the staged `payout` and `escrow` keys with `sudo -u wolo ... keys show ...`.
3. Verify the dedicated payout balance is still at least `2000000000uwolo` or top it up before cutover.
4. Build the new Linux binary or use the already-staged `/home/tony/wolochaind-live-cutover`.
5. Stage `/tmp/wolochain-settlement.env`.
6. Run `CHECK_SERVICE=0 ./scripts/check-settlement-cutover.sh` from an interactive root shell or with `sudo -u wolo` available.
7. Install the binary.
8. Install `/etc/wolochain-settlement.env`.
9. Restart `wolochain-settlement.service`.
10. Run `./scripts/check-settlement-cutover.sh`.
11. Run `./scripts/check-settlement-alerts.sh`.
12. Run `./scripts/verify-live-settlement.sh`.
13. If anything looks wrong, run `./scripts/restore-live-settlement.sh`.

Exact privileged rollout path once those values are decided:

```bash
ssh tony@ubuntu-4gb-hel1-11
cd /var/www/WoloChain
git pull --ff-only origin main
BACKUP_ROOT=/home/tony/wolochain-settlement-backups ./scripts/backup-live-settlement.sh
sudo -u wolo /var/www/WoloChain/build/wolochaind keys show payout \
  --address \
  --home /var/lib/wolochaind-testnet \
  --keyring-backend test
sudo -u wolo /var/www/WoloChain/build/wolochaind keys show escrow \
  --address \
  --home /var/lib/wolochaind-testnet \
  --keyring-backend test
sudo -u wolo /var/www/WoloChain/build/wolochaind query bank balances \
  wolo1cy04t5af0mr9d8n6rrzgr8e9j4vuf42nfg02q5 \
  --node tcp://127.0.0.1:26657 \
  --output json
sudo install -d -o tony -g tony -m 0755 /mnt/HC_Volume_105319120/wolochain/go-tmp
sudo install -d -o tony -g tony -m 0755 /mnt/HC_Volume_105319120/wolochain/go-cache
GOTOOLCHAIN=go1.24.0 \
GOTMPDIR=/mnt/HC_Volume_105319120/wolochain/go-tmp \
GOCACHE=/mnt/HC_Volume_105319120/wolochain/go-cache \
./scripts/build-linux-amd64.sh build/wolochaind
cat >/tmp/wolochain-settlement.env <<'EOF'
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
WOLO_SETTLEMENT_AUTH_TOKEN=<long-random-secret>
WOLO_SETTLEMENT_LISTEN_ADDR=127.0.0.1:8091
WOLO_SETTLEMENT_STATE_DIR=/mnt/HC_Volume_105319120/wolochain/settlement-state
EOF
set -a
. /tmp/wolochain-settlement.env
set +a
WOLOCHAIND_SUDO_USER=wolo \
CHECK_SERVICE=0 \
./scripts/check-settlement-cutover.sh
sudo install -o wolo -g wolo -m 0755 /home/tony/wolochaind-live-cutover /var/www/WoloChain/build/wolochaind
sudo install -o root -g root -m 0640 /tmp/wolochain-settlement.env /etc/wolochain-settlement.env
sudo systemctl restart wolochain-settlement.service
WOLOCHAIND_SUDO_USER=wolo ./scripts/check-settlement-cutover.sh
./scripts/check-settlement-alerts.sh
WOLOCHAIND_SUDO_USER=wolo ./scripts/verify-live-settlement.sh
```

Required env target in `/etc/wolochain-settlement.env`:

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
WOLO_SETTLEMENT_AUTH_TOKEN=<long-random-secret>
WOLO_SETTLEMENT_LISTEN_ADDR=127.0.0.1:8091
WOLO_SETTLEMENT_STATE_DIR=/mnt/HC_Volume_105319120/wolochain/settlement-state
```

If you deliberately choose `file` or `os` instead of `test`, substitute that backend consistently in both the key commands and the env file.

Post-rollout verification:

```bash
cd /var/www/WoloChain
set -a
. /tmp/wolochain-settlement.env
set +a
WOLOCHAIND_SUDO_USER=wolo ./scripts/check-settlement-cutover.sh
./scripts/check-settlement-alerts.sh
WOLOCHAIND_SUDO_USER=wolo ./scripts/verify-live-settlement.sh
```

Minimum expected results after rollout:

- `GET /settlement/v1/health` returns `200`
- missing bearer auth returns `401`
- `POST /settlement/v1/runs/validate` no longer returns `404`
- `GET /settlement/v1/escrow/deposits?limit=1` no longer returns a plain `404 page not found`
- `GET /settlement/v1/escrow/txs/not-a-real-hash` returns a structured invalid-tx response
- `build/wolochaind settlement recent --summary-only` works
- `build/wolochaind settlement run recent --summary-only` works
- `build/wolochaind settlement escrow recent --limit 1` works

## Settlement State Backup

The request/run state under `/mnt/HC_Volume_105319120/wolochain/settlement-state` is now operational truth. Back it up before and after cutover.

Preferred helper:

```bash
ssh tony@ubuntu-4gb-hel1-11
cd /var/www/WoloChain
BACKUP_ROOT=/home/tony/wolochain-settlement-backups ./scripts/backup-live-settlement.sh
```

That helper snapshots:

- current `build/wolochaind`
- current `/etc/wolochain-settlement.env`
- current settlement state dir
- current settlement service unit/status
- current settlement health output
- machine-readable metadata at `metadata.json`

Preferred restore helper:

```bash
ssh tony@ubuntu-4gb-hel1-11
cd /var/www/WoloChain
BACKUP_DIR="/mnt/HC_Volume_105319120/wolochain/settlement-backups/<timestamp>" \
./scripts/restore-live-settlement.sh
```

Manual restore path remains:

```bash
ssh tony@ubuntu-4gb-hel1-11
backup_dir="/mnt/HC_Volume_105319120/wolochain/settlement-backups/<timestamp>"
sudo systemctl stop wolochain-settlement.service
sudo install -o wolo -g wolo -m 0755 "$backup_dir/wolochaind" /var/www/WoloChain/build/wolochaind
sudo install -o root -g root -m 0640 "$backup_dir/wolochain-settlement.env" /etc/wolochain-settlement.env
sudo rm -rf /mnt/HC_Volume_105319120/wolochain/settlement-state
sudo cp -a "$backup_dir/settlement-state" /mnt/HC_Volume_105319120/wolochain/settlement-state
sudo systemctl start wolochain-settlement.service
```

If the service comes up wrong immediately after cutover, that restore helper or manual restore path is the rollback path.

## Known Current Caveats

- The VPS validator currently has `0` peers.
- The settlement signer is still the temporary `faucetgrowth` key.
- Settlement still uses `test` keyring backend.
- `WOLO_SETTLEMENT_AUTH_TOKEN` is empty, so POST safety currently depends on loopback-only binding.
- Escrow and payout are currently pointed at the same address.
- The extra volume is close to full and needs cleanup or expansion soon.

## Next Operator Upgrades

Highest ROI items after this doc sync:

- create the dedicated `payout` and `escrow` keys on the VPS
- install the newer settlement binary and `/etc/wolochain-settlement.env`
- run `./scripts/backup-live-settlement.sh` before the service restart
- run `./scripts/check-settlement-cutover.sh` after the service restart
- add alerts for settlement `5xx`, auth drift, and low payout balance
- add real peers and a second validator when builder mode is no longer the priority
