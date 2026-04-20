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
- node / bootstrap / testnet operations
- integration-facing proof and status primitives

WoloChain does not own:

- AoE2HDBets betting rules
- AoE2HDBets UX and operator presentation
- explorer UI bugs or Ping route presentation
- market math, pool math, refund policy, or entitlement logic

## Current Live State

Verified on April 9, 2026.

- VPS node service: `wolochaind-testnet.service`
- VPS settlement service: `wolochain-settlement.service`
- VPS moniker: `wolo-testnet-validator-1`
- Runtime chain ID: `wolo-testnet`
- Settlement health: `ok=true`
- Current VPS peer count: `0`
- Public RPC host: `https://rpc.aoe2hdbets.com`
- Public REST host: `https://rest.aoe2hdbets.com`

Current live settlement posture:

- Settlement uses the dedicated `payout` signer.
- Payout address: `wolo1cy04t5af0mr9d8n6rrzgr8e9j4vuf42nfg02q5`
- Escrow address: `wolo1t4jq7wd4x030t9f0yfqfq74pt4pmaep5nu67y4`
- Payout and escrow are distinct live addresses.
- `WOLO_SETTLEMENT_AUTH_TOKEN` is set.
- Settlement POST routes reject missing bearer auth.
- `POST /settlement/v1/runs/validate` is live and auth-protected.
- Grouped settlement CLI surfaces are live.
- Escrow discovery and escrow verification routes are live.
- Settlement request / grouped-run state lives on the VPS extra volume.

Current live caveats:

- The VPS validator is currently isolated with `0` peers.
- Settlement still uses the `test` keyring backend on the VPS.
- The highest-value WoloChain work right now is restart reliability, operator truthfulness, monitoring, backup / restore ergonomics, and doc accuracy — not new chain features.

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
- `POST /settlement/v1/challenges/validate`
- `POST /settlement/v1/challenges`
- `GET /settlement/v1/challenges/{settlement_run_id}`
- `GET /settlement/v1/challenges`
- `GET /settlement/v1/challenges/funding/txs/{tx_hash}`
- `GET /settlement/v1/challenges/funding/deposits`

Auth behavior:

- when `WOLO_SETTLEMENT_AUTH_TOKEN` is set, settlement POST routes require `Authorization: Bearer ...`
- that includes `POST /settlement/v1/payouts`, `POST /settlement/v1/runs/validate`, `POST /settlement/v1/runs`, `POST /settlement/v1/challenges/validate`, and `POST /settlement/v1/challenges`
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
- `wolochaind settlement challenge funding verify`
- `wolochaind settlement challenge funding recent`
- `wolochaind settlement challenge validate`
- `wolochaind settlement challenge execute`
- `wolochaind settlement challenge inspect`
- `wolochaind settlement challenge recent`
- `wolochaind settlement challenge audit`
- `wolochaind settlement serve`

Settlement execution supports:

- separate internal and public proof URLs via `WOLO_SETTLEMENT_PUBLIC_REST_URL`
- preferred proof links via `canonical_tx_lookup_preferred`
- payout reserve-floor enforcement via `WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO`
- fee headroom enforcement via `WOLO_SETTLEMENT_FEE_HEADROOM_UWOLO`
- read-only escrow deposit verification by tx hash
- read-only escrow deposit discovery for recent transfers into the configured escrow address
- stored request inspection by `request_id`
- grouped settlement runs over the same request-level idempotent payout rail
- dry-run validation before grouped execution, including requested totals and reserve / headroom impact
- stored grouped-run inspection by `settlement_run_id`
- recent failure / refusal summaries via `wolochaind settlement recent --summary-only`
- recent grouped-run summaries via `wolochaind settlement run recent --summary-only`
- challenge funding verification from structured escrow deposit memos
- bucket-aware challenge settlement plans that keep `wager` and `guarantee` distinct
- optional escrow-to-payout shortfall top-up via `WOLO_SETTLEMENT_ESCROW_AUTO_TOP_UP_ENABLED`
- stored challenge settlement inspection by `settlement_run_id`
- recent challenge settlement summaries via `wolochaind settlement challenge recent --summary-only`
- read-only challenge reconciliation via `wolochaind settlement challenge audit --settlement-id ...`

Operator helpers in this repo:

- [`scripts/check-settlement-cutover.sh`](scripts/check-settlement-cutover.sh): separates intended config checks, local CLI doctor truth, live service truth, and operator warnings
- [`scripts/check-settlement-alerts.sh`](scripts/check-settlement-alerts.sh): machine-readable settlement JSON with separate live / local / operator / storage scopes and exit codes for cron or VPSSentry
- [`scripts/run-settlement-alert-check.sh`](scripts/run-settlement-alert-check.sh): writes the latest alert JSON to `$HOME/wolochain-settlement-alerts/latest.json` by default and preserves the alert script exit code
- [`scripts/install-settlement-alert-cron.sh`](scripts/install-settlement-alert-cron.sh): installs an idempotent `crontab` entry for the current user that runs the alert runner every 5 minutes by default
- [`scripts/verify-live-settlement.sh`](scripts/verify-live-settlement.sh): waits for settlement health after restart, then verifies the live HTTP / CLI surface
- [`scripts/e2e-local-challenge-settlement.sh`](scripts/e2e-local-challenge-settlement.sh): runs a real local-chain challenge settlement path from escrow funding through audit
- [`scripts/clean-build-cache.sh`](scripts/clean-build-cache.sh): clears Go build cache, module cache, and temp directories only; it does not touch settlement state
- [`scripts/backup-live-settlement.sh`](scripts/backup-live-settlement.sh): rollback-oriented backup with source-path and free-space sanity checks
- [`scripts/restore-live-settlement.sh`](scripts/restore-live-settlement.sh): defaults to a shared-binary rollback that restarts node + settlement; `RESTORE_MODE=settlement-only` is the explicit env/state-only path

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

## Challenge Settlement Primitives

Challenge settlement stays generic and app-owned at the decision layer.

WoloChain owns:

- verifying one escrow funding deposit per participant against the canonical memo convention
- preserving `wager` and `guarantee` buckets in dry-run, execute, and proof output
- validating that an explicit challenge settlement request allocates each verified bucket exactly once
- executing the resulting grouped transfers safely over the existing payout rail
- storing idempotent challenge settlement state by `settlement_run_id`
- exposing grouped proof URLs, transfer tx hashes, and recent/inspect surfaces
- optionally topping up the payout signer from escrow before execution when `WOLO_SETTLEMENT_ESCROW_AUTO_TOP_UP_ENABLED=true`

AoE2HDBets still owns:

- challenge terms
- check-in and no-show decisions
- match results
- deciding the exact transfer list for refunds, payouts, and treasury routing

The canonical funding memo convention is:

```text
wolo.challenge.funding.v1:source_app=aoe2hdbets&challenge_id=challenge-42&participant_side=left&participant_id=user-1&wager_uwolo=1000000&guarantee_uwolo=500000
```

AoE2HDBets should verify funding with `GET /settlement/v1/challenges/funding/txs/{tx_hash}` or `wolochaind settlement challenge funding verify`, then submit the explicit bucket moves to `POST /settlement/v1/challenges/validate` or `wolochaind settlement challenge validate` before calling `POST /settlement/v1/challenges` or `wolochaind settlement challenge execute`.

For automatic funding detection, AoE2HDBets can poll `GET /settlement/v1/challenges/funding/deposits?source_app=aoe2hdbets&challenge_id=...` or run `wolochaind settlement challenge funding recent`. That read-only surface proves which escrow deposits WoloChain can see; AoE2HDBets still decides whether a challenge is ready to lock, cancel, or settle.

After execution, operators can reconcile stored challenge state against chain reality with:

```bash
wolochaind settlement challenge audit --settlement-id aoe2hdbets:challenge-42:one-noshow:v1
```

The audit report re-checks escrow funding txs, wager and guarantee bucket totals, treasury routes, payout/refund tx hashes, grouped run state, per-transfer state, and escrow-to-payout top-ups when present.

The machine-readable integration contract lives in [`docs/settlement-contracts`](docs/settlement-contracts):

- [`challenge-settlement-request.schema.json`](docs/settlement-contracts/challenge-settlement-request.schema.json)
- [`challenge-funding-memo.schema.json`](docs/settlement-contracts/challenge-funding-memo.schema.json)
- example request payloads for one no-show, double no-show, played match, and canceled/refunded outcomes
- example response payloads for funding verify/recent, validate, execute, inspect, and audit

## Grouped Run Flow

For one logical result with many payouts, the preferred flow is:

1. Caller computes recipients and amounts outside WoloChain.
2. Caller sends the grouped payload to `POST /settlement/v1/runs/validate` or `wolochaind settlement run validate`.
3. Operator confirms totals, reserve-floor impact, fee headroom impact, and any line-item warnings.
4. Caller submits the same payload to `POST /settlement/v1/runs` or `wolochaind settlement run execute`.
5. Operator inspects the run with `wolochaind settlement run inspect --run-id ...`.
6. If needed, operator drills into individual request ids with `wolochaind settlement inspect --request-id ...`.

## Production Notes

- Do not commit compiled binaries or validator home data.
- The live VPS extra volume is now a real `30G` ext4 filesystem. Verify that truth with `lsblk -o NAME,SIZE,FSTYPE,FSAVAIL,FSUSE%,MOUNTPOINTS` and `df -h / /mnt/HC_Volume_105319120` before large builds or backups.
- The preferred production build venue is now the VPS itself, using the resized extra volume for `GOTMPDIR`, `GOCACHE`, and the build-helper default `GOPATH` / `GOMODCACHE`.
- Before the first local VPS build, precreate `/mnt/HC_Volume_105319120/wolochain/go`, `/mnt/HC_Volume_105319120/wolochain/go/bin`, `/mnt/HC_Volume_105319120/wolochain/go-cache`, and `/mnt/HC_Volume_105319120/wolochain/go-tmp` for the build user.
- If Hetzner expands the volume again later, the guest still needs the on-host filesystem step. For the current ext4 layout that means `sudo resize2fs /dev/sdb`, then re-check `df -h /mnt/HC_Volume_105319120`.
- Treat settlement request state as operator data; it lives on the VPS extra volume.
- Treat grouped run state as operator data too; it lives beside request state under the settlement state dir.
- Prefer keeping `WOLO_SETTLEMENT_AUTH_TOKEN` enabled even for localhost-only POSTs and have callers send bearer auth.
- `WOLO_SETTLEMENT_ESCROW_ADDRESS` only affects proof classification and operator warnings; it does not create escrow semantics by itself.
- `WOLO_SETTLEMENT_ESCROW_KEY_NAME` and `WOLO_SETTLEMENT_ESCROW_ADDRESS` are both required if you want challenge auto-top-up from escrow.
- `WOLO_SETTLEMENT_TREASURY_ADDRESS` sets the default challenge treasury route, but callers can still pass an explicit `treasury_address` per challenge request.
- `WOLO_SETTLEMENT_ESCROW_AUTO_TOP_UP_ENABLED=true` lets challenge execution move only the shortfall needed to make the payout signer whole before the grouped payout run starts.
- Set `WOLO_SETTLEMENT_FEES` if you want dry-run grouped runs to return a deterministic fee estimate in `uwolo`.
- Use [`scripts/install-settlement-alert-cron.sh`](scripts/install-settlement-alert-cron.sh) as the repo-owned cron installer for [`scripts/run-settlement-alert-check.sh`](scripts/run-settlement-alert-check.sh).
- [`scripts/run-settlement-alert-check.sh`](scripts/run-settlement-alert-check.sh) overwrites the latest JSON on each run and preserves the underlying alert exit code.
- [`scripts/check-settlement-alerts.sh`](scripts/check-settlement-alerts.sh) also watches free space on `/` and `/mnt/HC_Volume_105319120`. The default thresholds are root warn below `2GiB` / fail below `1GiB`, and extra-volume warn below `8GiB` / fail below `4GiB`.
- Downstream consumers should invoke `sudo -u tony ./scripts/run-settlement-alert-check.sh`, page on exit `1`, treat exit `2` as a local monitoring failure, and read `/home/tony/wolochain-settlement-alerts/latest.json` for `failed_checks_by_scope`, `warn_checks_by_scope`, and the `storage` summary.
- The cron-installed `runner.log` is append-only by design; rotate it with host-level logrotate or existing ops tooling if you want retention control.
- Use [`scripts/verify-live-settlement.sh`](scripts/verify-live-settlement.sh) after deploys or service restarts; it now waits for `GET /settlement/v1/health` to return `200` with `ok=true` before running the deeper checks.
- Run [`scripts/clean-build-cache.sh`](scripts/clean-build-cache.sh) before retrying VPS builds under disk pressure; it only clears Go build/module cache and temp paths.
- If the VPS still fails a fresh build after cleanup, stop and re-check the mounted extra-volume size and free space before falling back to an off-box build.
- Prefer `BACKUP_ROOT=/home/tony/wolochain-settlement-backups ./scripts/backup-live-settlement.sh` when the extra volume is tight on free space.
- Use [`scripts/restore-live-settlement.sh`](scripts/restore-live-settlement.sh) if the live service comes up wrong and you need to return to the last known-good backup quickly. The default restore mode is `shared-binary`, because the live node and settlement services both execute `/var/www/WoloChain/build/wolochaind`.
- Use `wolochaind settlement escrow verify` or `GET /settlement/v1/escrow/txs/{tx_hash}` when an app / operator needs to prove a deposit really hit the configured escrow address.
- Use `wolochaind settlement escrow recent` or `GET /settlement/v1/escrow/deposits` to recover from partial app-side state loss without adding market logic to WoloChain.
- Use `wolochaind settlement challenge funding verify` or `GET /settlement/v1/challenges/funding/txs/{tx_hash}` when AoE2HDBets needs a challenge-aware proof surface for escrow funding.
- Use `wolochaind settlement challenge recent --summary-only` or `GET /settlement/v1/challenges?summary_only=1` for operator visibility into challenge settlement replays, partial failures, and top-up history.

For the live VPS layout and deploy runbook, see [docs/testnet-ops.md](docs/testnet-ops.md).
