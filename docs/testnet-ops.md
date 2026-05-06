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
- on April 9, 2026 Hetzner exposed `/dev/sdb` as `30G`, but the guest still needed `sudo resize2fs /dev/sdb` before the mounted ext4 filesystem actually grew from about `10G` to `30G`
- after that live resize, `/mnt/HC_Volume_105319120` had about `21G` free and became a trustworthy local build scratch volume again

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
- the highest-value chain-ops work right now is restart reliability, monitoring, backup / restore ergonomics, and doc accuracy; peer isolation remains a separate caveat

## Build And Deploy

Preferred production path: build the linux/amd64 binary directly on the VPS, using the resized extra volume.

```bash
cd /var/www/WoloChain
sudo install -d -o tony -g tony -m 0755 \
  /mnt/HC_Volume_105319120/wolochain/go \
  /mnt/HC_Volume_105319120/wolochain/go/bin \
  /mnt/HC_Volume_105319120/wolochain/go-cache \
  /mnt/HC_Volume_105319120/wolochain/go-tmp
GOTOOLCHAIN=go1.24.0 \
sudo -u tony env \
  GOTMPDIR=/mnt/HC_Volume_105319120/wolochain/go-tmp \
  GOCACHE=/mnt/HC_Volume_105319120/wolochain/go-cache \
  ./scripts/build-linux-amd64.sh /mnt/HC_Volume_105319120/wolochain/go/bin/wolochaind.new
sudo env BACKUP_ROOT=/home/tony/wolochain-settlement-backups ./scripts/backup-live-settlement.sh
sudo install -o wolo -g wolo -m 0755 /mnt/HC_Volume_105319120/wolochain/go/bin/wolochaind.new /var/www/WoloChain/build/wolochaind
sudo systemctl restart wolochaind-testnet.service
sudo systemctl restart wolochain-settlement.service
sudo ./scripts/verify-live-settlement.sh
sudo -u tony ./scripts/run-settlement-alert-check.sh
rm -f /mnt/HC_Volume_105319120/wolochain/go/bin/wolochaind.new
```

Why this path exists:

- raw Linux `amd64` builds hit a `sonic` native-loader mismatch
- [`scripts/build-linux-amd64.sh`](../scripts/build-linux-amd64.sh) forces the safe compat path
- the live `30G` extra volume now has enough headroom for calm local builds once the mounted ext4 filesystem has been resized
- [`scripts/build-linux-amd64.sh`](../scripts/build-linux-amd64.sh) now defaults `GOPATH` / `GOMODCACHE` onto `/mnt/HC_Volume_105319120/wolochain/go` when that shared build path exists, so module downloads do not quietly eat `/home`
- the current `tony` sudo policy requires an interactive password and does not allow `sudo -n`; use explicit `sudo install`, `sudo systemctl`, and `sudo -u wolo ...` commands during live work
- if the node binary on disk is replaced, restart the node service so it does not keep running a deleted in-memory binary

If Hetzner expands the extra volume again later, verify the mounted filesystem before trusting the new capacity:

```bash
lsblk -o NAME,SIZE,FSTYPE,FSAVAIL,FSUSE%,MOUNTPOINTS
df -h /mnt/HC_Volume_105319120
sudo resize2fs /dev/sdb
df -h /mnt/HC_Volume_105319120
```

Off-box builds are still fine, but they are no longer the default. Use them only when the VPS volume is unavailable or you explicitly want a separate build venue.

## Operator Helpers

Repo-owned helpers:

- `./scripts/check-settlement-cutover.sh`
  - separates intended config checks, local CLI doctor truth, live service truth, and operator warnings
  - best used when the intended env is exported in the current shell or sourced from `SETTLEMENT_ENV_FILE`
- `./scripts/check-settlement-alerts.sh`
  - machine-readable JSON health / alert output with separate live / local / operator / storage scopes
  - exit `0` when healthy, `1` when alerts are present, and `2` when the script itself cannot produce a trustworthy result
- `./scripts/run-settlement-alert-check.sh`
  - writes the latest alert JSON to `$HOME/wolochain-settlement-alerts/latest.json` by default
  - preserves the underlying alert exit code so cron or VPSSentry can alert on `1` and distinguish local runtime failures on `2`
  - appends a short runner line to `$HOME/wolochain-settlement-alerts/runner.log`; rotate that log with host tooling if you want retention control
- `./scripts/install-settlement-alert-cron.sh`
  - installs or updates the current user's `crontab` block for settlement alert checks
  - defaults to every 5 minutes and preserves unrelated cron entries
  - the live `tony` crontab already has this block installed on the VPS
- `./scripts/verify-live-settlement.sh`
  - waits for settlement health to become ready after restart, then checks auth, grouped routes, escrow routes, and CLI availability
- `./scripts/clean-build-cache.sh`
  - clears Go build cache, module cache, and temp paths only
  - does not touch settlement state, validator state, or other operator data
- `./scripts/backup-live-settlement.sh`
  - rollback-oriented backup of the current shared binary, env file, state dir, and current node / settlement unit snapshots
  - fails fast on missing source paths or low free space unless you deliberately override the safety check
- `./scripts/restore-live-settlement.sh`
  - default `RESTORE_MODE=shared-binary` restores the shared binary, settlement env, and settlement state, then restarts node + settlement
  - `RESTORE_MODE=settlement-only` is the explicit env/state-only rollback path when you want to leave the shared node binary untouched

For live truth after deploy or restart, prefer this sequence:

```bash
cd /var/www/WoloChain
sudo ./scripts/verify-live-settlement.sh
./scripts/check-settlement-alerts.sh
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
sudo grep -E '^(WOLO_SETTLEMENT_(KEY_NAME|KEYRING_BACKEND|PAYOUT_ADDRESS|ESCROW_ADDRESS|TREASURY_ADDRESS|AUTH_TOKEN|STATE_DIR|PUBLIC_REST_URL|MIN_PAYOUT_BALANCE_UWOLO|FEE_HEADROOM_UWOLO|ESCROW_AUTO_TOP_UP_ENABLED)|WOLO_(CHAIN_ID|NODE|HOME))=' "$ENV_FILE" \
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
- `POST /settlement/v1/challenges/validate` is part of the live settlement surface
- `POST /settlement/v1/challenges` is part of the live settlement surface
- `GET /settlement/v1/challenges`, `GET /settlement/v1/challenges/{settlement_run_id}`, `GET /settlement/v1/challenges/funding/deposits`, and `GET /settlement/v1/challenges/funding/txs/{tx_hash}` are part of the live read-only surface
- the live CLI exposes `doctor`, `execute`, `lookup`, `inspect`, `recent`, `run`, `escrow`, `challenge`, and `serve`

When `WOLO_SETTLEMENT_AUTH_TOKEN` is set:

- `POST /settlement/v1/payouts` requires `Authorization: Bearer ...`
- `POST /settlement/v1/runs/validate` requires `Authorization: Bearer ...`
- `POST /settlement/v1/runs` requires `Authorization: Bearer ...`
- `POST /settlement/v1/challenges/validate` requires `Authorization: Bearer ...`
- `POST /settlement/v1/challenges` requires `Authorization: Bearer ...`
- `GET /settlement/v1/health` stays open
- `GET /settlement/v1/txs/{tx_hash}` stays open
- `GET /settlement/v1/escrow/txs/{tx_hash}` stays open
- `GET /settlement/v1/escrow/deposits` stays open
- challenge funding proof / discovery routes stay open
- challenge inspect / recent routes stay open

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

## Challenge Settlement Contract

Challenge settlement stays operator-driven and app-owned at the decision layer.

AoE2HDBets owns:

- challenge terms
- who checked in
- no-show and result decisions
- the exact transfer list for refunds, payouts, and treasury routing

WoloChain owns:

- challenge funding proof from escrow deposits
- exact `wager` / `guarantee` bucket accounting
- dry-run validation of the explicit transfer plan
- safe idempotent execution over the existing payout rail
- grouped proof surfaces, tx hashes, and inspect / recent state
- optional escrow-to-payout shortfall top-up before execution

Canonical challenge funding memo for actual funding transactions:

```text
wolo.challenge.funding.v1:app=aoe2hdbets&sid=aoe2hdbets:challenge-42:one-noshow:v1&cid=challenge-42&side=left&pid=user-1&w=1000000&g=500000&t=1500000
```

Use the compact aliases on chain so the memo stays under the chain memo limit. WoloChain proof responses normalize those aliases back to the expanded field names.

Accepted funding memo aliases:

- `app` for `source_app`
- `run_id` or `sid` for `settlement_run_id`
- `cid` for `challenge_id`
- `event_id` or `eid` for `source_event_id`
- `side` for `participant_side`
- `pid` for `participant_id`
- `w` for `wager_uwolo`
- `g` for `guarantee_uwolo`
- optional `total_funded_uwolo`, `total_uwolo`, `total`, or `t`

Read-only funding verification:

```bash
curl -sS \
  "http://127.0.0.1:8091/settlement/v1/challenges/funding/txs/TX_HASH?source_app=aoe2hdbets&settlement_run_id=aoe2hdbets:challenge-42:one-noshow:v1&challenge_id=challenge-42&participant_side=left&participant_id=user-1&expected_amount_uwolo=1500000&wager_uwolo=1000000&guarantee_uwolo=500000"

build/wolochaind settlement challenge funding verify \
  --tx-hash TX_HASH \
  --source-app aoe2hdbets \
  --settlement-run-id aoe2hdbets:challenge-42:one-noshow:v1 \
  --challenge-id challenge-42 \
  --participant-side left \
  --participant-id user-1 \
  --expected-amount-uwolo 1500000 \
  --wager-uwolo 1000000 \
  --guarantee-uwolo 500000
```

Recent challenge funding discovery:

```bash
curl -sS "http://127.0.0.1:8091/settlement/v1/challenges/funding/deposits?limit=20&source_app=aoe2hdbets&settlement_run_id=aoe2hdbets:challenge-42:one-noshow:v1&challenge_id=challenge-42"
build/wolochaind settlement challenge funding recent --limit 20 --source-app aoe2hdbets --settlement-run-id aoe2hdbets:challenge-42:one-noshow:v1 --challenge-id challenge-42
```

Dry-run and execute use the same JSON body. Dry-run first:

```bash
curl -sS \
  -H "authorization: Bearer $WOLO_SETTLEMENT_AUTH_TOKEN" \
  -H 'content-type: application/json' \
  -d @challenge.json \
  http://127.0.0.1:8091/settlement/v1/challenges/validate
```

Then execute the exact same payload:

```bash
curl -sS \
  -H "authorization: Bearer $WOLO_SETTLEMENT_AUTH_TOKEN" \
  -H 'content-type: application/json' \
  -d @challenge.json \
  http://127.0.0.1:8091/settlement/v1/challenges
```

Or from the CLI:

```bash
build/wolochaind settlement challenge validate --file challenge.json
build/wolochaind settlement challenge execute --file challenge.json
build/wolochaind settlement challenge inspect --settlement-id challenge-run-42
build/wolochaind settlement challenge recent --summary-only
```

Request contract:

- `settlement_run_id`: stable idempotency key for the whole challenge settlement
- `source_app`: stable caller id like `aoe2hdbets`
- `challenge_id` and/or `source_event_id`: challenge reference from the app
- `treasury_address`: optional explicit destination for treasury forfeits; falls back to `WOLO_SETTLEMENT_TREASURY_ADDRESS`
- `funding[]`: one verified escrow funding tx per participant; include optional `settlement_run_id`, `expected_amount_uwolo`, `wager_uwolo`, and `guarantee_uwolo` to pin the tx to caller-expected proof fields
- `transfers[]`: explicit bucket movements with `bucket`, `reason`, `to_address`, and amount

Canonical transfer reasons are proof labels, not WoloChain policy:

- `return`: return a Match Guarantee to its original participant.
- `forfeit`: pay a forfeited Match Guarantee to the caller-supplied recipient.
- `treasury`: route a Match Guarantee to the explicit treasury address.
- `refund`: refund a Wolo Wager or Match Guarantee.
- `release` or `payout`: release Wolo Wager funds to the caller-supplied winner/payee.

Each transfer line must name the originating participant with `participant_side` and/or `participant_id`. WoloChain verifies that every participant's funded `wager` and `guarantee` buckets are allocated exactly once across the request.

### One No-Show

Dry-run request:

```json
{
  "settlement_run_id": "challenge-run-noshow-42",
  "source_app": "aoe2hdbets",
  "challenge_id": "challenge-42",
  "note": "left checked in, right no-show",
  "memo": "challenge-42-noshow",
  "funding": [
    {
      "funding_tx_hash": "LEFT_FUNDING_TX_HASH",
      "depositor_address": "wolo1leftplayer...",
      "settlement_run_id": "challenge-run-noshow-42",
      "participant_side": "left",
      "participant_id": "left-user",
      "expected_amount_uwolo": "1500000",
      "wager_uwolo": "1000000",
      "guarantee_uwolo": "500000"
    },
    {
      "funding_tx_hash": "RIGHT_FUNDING_TX_HASH",
      "depositor_address": "wolo1rightplayer...",
      "settlement_run_id": "challenge-run-noshow-42",
      "participant_side": "right",
      "participant_id": "right-user",
      "expected_amount_uwolo": "1500000",
      "wager_uwolo": "1000000",
      "guarantee_uwolo": "500000"
    }
  ],
  "transfers": [
    {
      "participant_side": "left",
      "participant_id": "left-user",
      "bucket": "guarantee",
      "reason": "return",
      "to_address": "wolo1leftplayer...",
      "amount_uwolo": "500000",
      "memo": "left guarantee return"
    },
    {
      "participant_side": "right",
      "participant_id": "right-user",
      "bucket": "guarantee",
      "reason": "forfeit",
      "to_address": "wolo1leftplayer...",
      "amount_uwolo": "500000",
      "memo": "right guarantee forfeit"
    },
    {
      "participant_side": "left",
      "participant_id": "left-user",
      "bucket": "wager",
      "reason": "refund",
      "to_address": "wolo1leftplayer...",
      "amount_uwolo": "1000000",
      "memo": "left wager refund"
    },
    {
      "participant_side": "right",
      "participant_id": "right-user",
      "bucket": "wager",
      "reason": "refund",
      "to_address": "wolo1rightplayer...",
      "amount_uwolo": "1000000",
      "memo": "right wager refund"
    }
  ]
}
```

### Double No-Show

Dry-run request:

```json
{
  "settlement_run_id": "challenge-run-double-noshow-42",
  "source_app": "aoe2hdbets",
  "challenge_id": "challenge-42",
  "treasury_address": "wolo1treasury...",
  "note": "double no-show",
  "memo": "challenge-42-double-noshow",
  "funding": [
    {
      "funding_tx_hash": "LEFT_FUNDING_TX_HASH",
      "depositor_address": "wolo1leftplayer...",
      "settlement_run_id": "challenge-run-double-noshow-42",
      "participant_side": "left",
      "participant_id": "left-user",
      "expected_amount_uwolo": "1500000",
      "wager_uwolo": "1000000",
      "guarantee_uwolo": "500000"
    },
    {
      "funding_tx_hash": "RIGHT_FUNDING_TX_HASH",
      "depositor_address": "wolo1rightplayer...",
      "settlement_run_id": "challenge-run-double-noshow-42",
      "participant_side": "right",
      "participant_id": "right-user",
      "expected_amount_uwolo": "1500000",
      "wager_uwolo": "1000000",
      "guarantee_uwolo": "500000"
    }
  ],
  "transfers": [
    {
      "participant_side": "left",
      "participant_id": "left-user",
      "bucket": "guarantee",
      "reason": "treasury",
      "to_address": "wolo1treasury...",
      "amount_uwolo": "500000",
      "memo": "left guarantee treasury"
    },
    {
      "participant_side": "right",
      "participant_id": "right-user",
      "bucket": "guarantee",
      "reason": "treasury",
      "to_address": "wolo1treasury...",
      "amount_uwolo": "500000",
      "memo": "right guarantee treasury"
    },
    {
      "participant_side": "left",
      "participant_id": "left-user",
      "bucket": "wager",
      "reason": "refund",
      "to_address": "wolo1leftplayer...",
      "amount_uwolo": "1000000",
      "memo": "left wager refund"
    },
    {
      "participant_side": "right",
      "participant_id": "right-user",
      "bucket": "wager",
      "reason": "refund",
      "to_address": "wolo1rightplayer...",
      "amount_uwolo": "1000000",
      "memo": "right wager refund"
    }
  ]
}
```

### Played Match Settlement

Dry-run request:

```json
{
  "settlement_run_id": "challenge-run-played-42",
  "source_app": "aoe2hdbets",
  "challenge_id": "challenge-42",
  "note": "left won played match",
  "memo": "challenge-42-played",
  "funding": [
    {
      "funding_tx_hash": "LEFT_FUNDING_TX_HASH",
      "depositor_address": "wolo1leftplayer...",
      "settlement_run_id": "challenge-run-played-42",
      "participant_side": "left",
      "participant_id": "left-user",
      "expected_amount_uwolo": "1500000",
      "wager_uwolo": "1000000",
      "guarantee_uwolo": "500000"
    },
    {
      "funding_tx_hash": "RIGHT_FUNDING_TX_HASH",
      "depositor_address": "wolo1rightplayer...",
      "settlement_run_id": "challenge-run-played-42",
      "participant_side": "right",
      "participant_id": "right-user",
      "expected_amount_uwolo": "1500000",
      "wager_uwolo": "1000000",
      "guarantee_uwolo": "500000"
    }
  ],
  "transfers": [
    {
      "participant_side": "left",
      "participant_id": "left-user",
      "bucket": "guarantee",
      "reason": "return",
      "to_address": "wolo1leftplayer...",
      "amount_uwolo": "500000",
      "memo": "left guarantee return"
    },
    {
      "participant_side": "right",
      "participant_id": "right-user",
      "bucket": "guarantee",
      "reason": "return",
      "to_address": "wolo1rightplayer...",
      "amount_uwolo": "500000",
      "memo": "right guarantee return"
    },
    {
      "participant_side": "left",
      "participant_id": "left-user",
      "bucket": "wager",
      "reason": "release",
      "to_address": "wolo1leftplayer...",
      "amount_uwolo": "1000000",
      "memo": "left wager release"
    },
    {
      "participant_side": "right",
      "participant_id": "right-user",
      "bucket": "wager",
      "reason": "release",
      "to_address": "wolo1leftplayer...",
      "amount_uwolo": "1000000",
      "memo": "right wager release"
    }
  ]
}
```

## Grouped Settlement Boundary

Grouped settlement runs are generic WoloChain settlement wrappers, not app logic.

WoloChain owns:

- validating addresses and amounts
- deriving stable per-line request ids when omitted
- checking the selected signer balance; payout runs also enforce reserve floor and fee headroom
- executing sends from the payout signer by default, or from escrow when the grouped run explicitly sets `signer_role=escrow`
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

Challenge-specific config:

- `WOLO_SETTLEMENT_ESCROW_KEY_NAME`: escrow signer key name used for challenge auto-top-up
- `WOLO_SETTLEMENT_TREASURY_ADDRESS`: default treasury route for challenge guarantee forfeits
- `WOLO_SETTLEMENT_ESCROW_AUTO_TOP_UP_ENABLED=true`: allow escrow -> payout shortfall funding before challenge execution

When top-up is enabled, challenge dry-run shows whether the payout signer is short, how much must move from escrow, and whether escrow can cover that shortfall. If top-up is disabled or impossible, dry-run fails early with a specific failure code instead of letting the later payout run die on an underfunded signer.

Challenge reconciliation:

```bash
wolochaind settlement challenge audit \
  --settlement-id aoe2hdbets:challenge-42:one-noshow:v1
```

The audit command is read-only. It reloads stored challenge state, verifies the state fingerprint, re-checks each funding tx against the escrow memo convention, recomputes `wager` and `guarantee` bucket totals, validates treasury routes, compares grouped run and per-transfer state files, and re-queries payout/refund/top-up tx hashes through REST.

For local runtime coverage against a real node:

```bash
./scripts/reset-and-start-local.sh
./scripts/e2e-local-challenge-settlement.sh
```

The E2E script creates disposable local test keys, sends one real escrow funding deposit per player, verifies funding, runs challenge dry-run, executes a one-no-show settlement, inspects stored state, and finishes with the audit command. Artifacts are written under `build/local-settlement-e2e/`.

Machine-readable contracts and examples live under `docs/settlement-contracts/`:

- `challenge-settlement-request.schema.json`
- `challenge-funding-memo.schema.json`
- `examples/challenge-one-noshow.json`
- `examples/challenge-double-noshow.json`
- `examples/challenge-played-match.json`
- `examples/challenge-canceled-refund.json`
- `examples/responses/challenge-funding-verify-response.json`
- `examples/responses/challenge-funding-recent-response.json`
- `examples/responses/challenge-validate-response.json`
- `examples/responses/challenge-execute-response.json`
- `examples/responses/challenge-inspect-summary-response.json`
- `examples/responses/challenge-audit-summary-response.json`

For AoE2HDBets automatic funding detection, use the recent funding route as read-only WoloChain truth:

```bash
curl -sS "http://127.0.0.1:8091/settlement/v1/challenges/funding/deposits?source_app=aoe2hdbets&challenge_id=challenge-42&limit=20"
```

Then verify each candidate tx hash with the expected participant and bucket fields before building the challenge settlement request. WoloChain proves escrow/bucket/tx state; AoE2HDBets still owns whether that proof means the challenge is funded, canceled, won, no-showed, or ready to settle.

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

Default readiness behavior:

- the script now waits up to `60s` for `GET /settlement/v1/health` to return `200` with `ok=true`
- that removes the common restart race where `systemctl` says `active` but the settlement port is still warming up
- set `VERIFY_WAIT_FOR_READY=0` only if you deliberately want an immediate probe instead of a restart-safe verification

What it checks:

- node and settlement services are active
- health route returns `200`
- missing bearer auth is rejected when auth is enabled
- grouped dry-run route exists and responds structurally
- challenge dry-run route exists and responds structurally
- escrow read-only routes exist and respond structurally
- challenge read-only routes exist and respond structurally
- request-level `inspect` / `recent` commands are available
- grouped `run inspect` / `run recent` commands are available
- challenge `inspect` / `recent` commands are available
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
- settlement service healthy on the target base URL
- free space on `/`
- free space on `/mnt/HC_Volume_105319120`
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

Preferred live cron install:

```bash
cd /var/www/WoloChain
sudo -u tony ./scripts/install-settlement-alert-cron.sh
sudo -u tony crontab -l | sed -n '/BEGIN wolochain-settlement-alerts/,/END wolochain-settlement-alerts/p'
```

Default behavior:

- schedule: every 5 minutes
- latest JSON path: `/home/tony/wolochain-settlement-alerts/latest.json`
- runner log path: `/home/tony/wolochain-settlement-alerts/runner.log`
- JSON retention: latest file only; each run overwrites it
- root free-space thresholds: warn below `2GiB`, fail below `1GiB`
- extra-volume free-space thresholds: warn below `8GiB`, fail below `4GiB`
- override thresholds with `WOLO_ALERT_ROOT_WARN_FREE_KB`, `WOLO_ALERT_ROOT_FAIL_FREE_KB`, `WOLO_ALERT_EXTRA_WARN_FREE_KB`, and `WOLO_ALERT_EXTRA_FAIL_FREE_KB` when you deliberately want different values
- exit `1`: real settlement alert
- exit `2`: local monitoring/runtime failure

Downstream consumer contract:

- invoke `sudo -u tony ./scripts/run-settlement-alert-check.sh`
- page on exit `1`
- treat exit `2` as a local monitoring/runtime failure instead of a chain-health page
- read `/home/tony/wolochain-settlement-alerts/latest.json`
- use `failed_checks_by_scope.storage` and `warn_checks_by_scope.storage` for disk-pressure routing
- use the top-level `storage.root` and `storage.extra_volume` objects for the exact free-space snapshot and thresholds in force

VPSSentry can follow that contract directly.

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
- settlement alert cron installed for `tony`, writing latest JSON to `/home/tony/wolochain-settlement-alerts/latest.json`
- storage alerting for `/` and `/mnt/HC_Volume_105319120` inside the same JSON / exit-code path
- helper-driven shared-binary restore rehearsed again after the VPS-local build venue shift

What still needs follow-through:

1. keep the build -> restart -> verify path boring and consistent after each live change
2. keep rollback backups on a root with enough free space
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
- current node service unit / status
- current settlement service unit / status
- current settlement health output
- machine-readable metadata at `metadata.json`
- checksums for the backed-up binary and env file when `sha256sum` is available

Safety notes:

- the helper refuses to run when the source binary, env file, or state dir is missing
- the helper checks free space under the selected backup root before copying unless you set `BACKUP_SKIP_SPACE_CHECK=1`
- if the extra volume is tight, prefer `BACKUP_ROOT=/home/tony/wolochain-settlement-backups`

Preferred restore helper:

```bash
cd /var/www/WoloChain
BACKUP_DIR="/path/to/backup-dir" ./scripts/restore-live-settlement.sh
```

Explicit settlement-only rollback:

```bash
cd /var/www/WoloChain
RESTORE_MODE=settlement-only BACKUP_DIR="/path/to/backup-dir" ./scripts/restore-live-settlement.sh
```

Restore helper behavior:

- defaults to `RESTORE_MODE=shared-binary`, because both live services execute `/var/www/WoloChain/build/wolochaind`
- in `shared-binary` mode it restores the binary, settlement env, and settlement state, then restarts `wolochaind-testnet.service` before `wolochain-settlement.service`
- in `settlement-only` mode it restores settlement env + state only, leaves the shared binary untouched, and restarts only `wolochain-settlement.service`
- verifies `SHA256SUMS` when present
- checks there is enough free space to stage the restored state dir
- stages the restored state under a temporary path before replacing the live dir
- verifies that the restarted services are actually `active`
- in `shared-binary` mode it waits for the node REST endpoint to become reachable before running the post-restore cutover check
- reruns `check-settlement-cutover.sh` after restart by default

Manual restore path remains:

```bash
backup_dir="/path/to/backup-dir"
sudo systemctl stop wolochaind-testnet.service
sudo systemctl stop wolochain-settlement.service
sudo install -o wolo -g wolo -m 0755 "$backup_dir/wolochaind" /var/www/WoloChain/build/wolochaind
sudo install -o root -g root -m 0640 "$backup_dir/wolochain-settlement.env" /etc/wolochain-settlement.env
sudo rm -rf /mnt/HC_Volume_105319120/wolochain/settlement-state
sudo cp -a "$backup_dir/settlement-state" /mnt/HC_Volume_105319120/wolochain/settlement-state
sudo systemctl start wolochaind-testnet.service
sudo systemctl start wolochain-settlement.service
```

## Known Current Caveats

- The VPS validator currently has `0` peers.
- Settlement currently uses the `test` keyring backend.
- The extra volume needs to be watched for space pressure.
- The highest-ROI WoloChain work now is restart reliability, monitoring, backup / restore trustworthiness, and clean operator proof — not more chain-side abstractions.

## Next Operator Upgrades

Highest-ROI items after this doc sync:

- keep root free-space monitoring calm and truthful as the main remaining disk risk
- keep the alert runner wired into cron or VPSSentry with the latest JSON path monitored
- keep the build / install / restart / verify path concise and current in this doc
- run one real end-to-end AoE2HDBets escrowed wager against the live rail
- update docs immediately when live operator truth changes
