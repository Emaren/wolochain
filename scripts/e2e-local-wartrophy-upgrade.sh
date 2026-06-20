#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

UPGRADE_NAME="warbound-trophy-v1"
OLD_COMMIT="${WOLO_UPGRADE_OLD_COMMIT:-d3bd624}"
KEEP_ARTIFACTS="${WOLO_UPGRADE_KEEP_ARTIFACTS:-0}"
TIMEOUT_SECONDS="${WOLO_UPGRADE_TIMEOUT_SECONDS:-180}"
WORK_DIR="${WOLO_UPGRADE_WORK_DIR:-$(mktemp -d /tmp/wolo-wartrophy-upgrade.XXXXXX)}"
CHAIN_HOME="$WORK_DIR/home"
OLD_SOURCE="$WORK_DIR/old-source"
OLD_BINARY="$WORK_DIR/wolochaind-old"
NEW_BINARY="$WORK_DIR/wolochaind-new"
OLD_LOG="$WORK_DIR/old-node.log"
NEW_LOG="$WORK_DIR/new-node.log"
CHAIN_ID="wartrophy-upgrade-proof"
KEY_NAME="validator"
OLD_PID=""
NEW_PID=""

cleanup() {
  if [[ -n "$OLD_PID" ]]; then
    kill "$OLD_PID" 2>/dev/null || true
    wait "$OLD_PID" 2>/dev/null || true
  fi
  if [[ -n "$NEW_PID" ]]; then
    kill "$NEW_PID" 2>/dev/null || true
    wait "$NEW_PID" 2>/dev/null || true
  fi

  if [[ "$KEEP_ARTIFACTS" == "1" ]]; then
    echo "proof artifacts retained at $WORK_DIR"
  else
    rm -rf "$WORK_DIR"
  fi
}
trap cleanup EXIT INT TERM

fail() {
  echo "ERROR: $*" >&2
  if [[ -f "$OLD_LOG" ]]; then
    echo "--- old node log ---" >&2
    tail -n 80 "$OLD_LOG" >&2 || true
  fi
  if [[ -f "$NEW_LOG" ]]; then
    echo "--- new node log ---" >&2
    tail -n 80 "$NEW_LOG" >&2 || true
  fi
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

for command in git go tar curl python3; do
  require_cmd "$command"
done

case "$WORK_DIR" in
  /var/lib/wolochaind-mainnet*|/var/lib/aoe2hdbets-wolo-mainnet*|"$HOME/.wolochain"*)
    fail "refusing unsafe proof work directory: $WORK_DIR"
    ;;
esac

mkdir -p "$WORK_DIR" "$OLD_SOURCE"

if ! git cat-file -e "$OLD_COMMIT^{commit}" 2>/dev/null; then
  fail "old commit does not exist: $OLD_COMMIT"
fi
if git ls-tree -r --name-only "$OLD_COMMIT" | grep -q '^x/wartrophy/'; then
  fail "old commit unexpectedly contains x/wartrophy: $OLD_COMMIT"
fi

read -r RPC_PORT GRPC_PORT < <(python3 - <<'PY'
import socket

sockets = []
ports = []
for _ in range(2):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sockets.append(sock)
    ports.append(sock.getsockname()[1])
print(*ports)
for sock in sockets:
    sock.close()
PY
)
RPC_URL="http://127.0.0.1:$RPC_PORT"
NODE_URL="tcp://127.0.0.1:$RPC_PORT"

echo "=== build old binary from $OLD_COMMIT ==="
git archive "$OLD_COMMIT" | tar -x -C "$OLD_SOURCE"
(
  cd "$OLD_SOURCE"
  go build -o "$OLD_BINARY" ./cmd/wolochaind
)

echo "=== build new binary from working tree ==="
go build -o "$NEW_BINARY" ./cmd/wolochaind

echo "=== create disposable synthetic chain ==="
"$OLD_BINARY" init wartrophy-upgrade-proof \
  --chain-id "$CHAIN_ID" \
  --home "$CHAIN_HOME" >/dev/null 2>&1
"$OLD_BINARY" keys add "$KEY_NAME" \
  --keyring-backend test \
  --home "$CHAIN_HOME" >/dev/null 2>&1
VALIDATOR_ADDRESS="$("$OLD_BINARY" keys show "$KEY_NAME" \
  --address \
  --keyring-backend test \
  --home "$CHAIN_HOME")"

"$OLD_BINARY" genesis add-genesis-account "$VALIDATOR_ADDRESS" \
  100000000000uwolo \
  --home "$CHAIN_HOME"
"$OLD_BINARY" genesis gentx "$KEY_NAME" 1000000000uwolo \
  --chain-id "$CHAIN_ID" \
  --keyring-backend test \
  --home "$CHAIN_HOME" >/dev/null
"$OLD_BINARY" genesis collect-gentxs --home "$CHAIN_HOME" >/dev/null 2>&1

python3 - "$CHAIN_HOME/config/genesis.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
genesis = json.loads(path.read_text())
app = genesis["app_state"]

gov = app["gov"]["params"]
gov["min_deposit"] = [{"denom": "uwolo", "amount": "1"}]
gov["expedited_min_deposit"] = [{"denom": "uwolo", "amount": "2"}]
gov["max_deposit_period"] = "8s"
gov["voting_period"] = "8s"
gov["expedited_voting_period"] = "4s"

mint = app["mint"]
mint["minter"]["inflation"] = "0.000000000000000000"
mint["minter"]["annual_provisions"] = "0.000000000000000000"
mint["params"]["inflation_rate_change"] = "0.000000000000000000"
mint["params"]["inflation_max"] = "0.000000000000000000"
mint["params"]["inflation_min"] = "0.000000000000000000"

path.write_text(json.dumps(genesis, indent=2) + "\n")
PY

python3 - "$CHAIN_HOME/config/config.toml" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
config = path.read_text()
config = re.sub(r'^timeout_propose = ".*"$', 'timeout_propose = "500ms"', config, flags=re.MULTILINE)
config = re.sub(r'^timeout_commit = ".*"$', 'timeout_commit = "500ms"', config, flags=re.MULTILINE)
path.write_text(config)
PY

"$OLD_BINARY" genesis validate --home "$CHAIN_HOME" >/dev/null

start_node() {
  local binary="$1"
  local log_file="$2"
  "$binary" start \
    --home "$CHAIN_HOME" \
    --minimum-gas-prices 0uwolo \
    --rpc.laddr "tcp://127.0.0.1:$RPC_PORT" \
    --rpc.pprof_laddr "127.0.0.1:0" \
    --p2p.laddr "tcp://127.0.0.1:0" \
    --grpc.address "127.0.0.1:$GRPC_PORT" \
    --grpc-web.enable=false \
    --api.enable=false \
    >"$log_file" 2>&1 &
  echo $!
}

current_height() {
  curl -fsS "$RPC_URL/status" | python3 -c '
import json, sys
print(int(json.load(sys.stdin)["result"]["sync_info"]["latest_block_height"]))
'
}

wait_for_height() {
  local target="$1"
  local deadline=$((SECONDS + TIMEOUT_SECONDS))
  while (( SECONDS < deadline )); do
    local height
    height="$(current_height 2>/dev/null || true)"
    if [[ -n "$height" ]] && (( height >= target )); then
      return 0
    fi
    sleep 1
  done
  fail "timed out waiting for height $target"
}

wait_for_proposal() {
  local expected_status="$1"
  local deadline=$((SECONDS + TIMEOUT_SECONDS))
  while (( SECONDS < deadline )); do
    local status
    status="$("$OLD_BINARY" query gov proposal 1 \
      --home "$CHAIN_HOME" \
      --node "$NODE_URL" \
      --output json 2>/dev/null | python3 -c '
import json, sys
payload = json.load(sys.stdin)
print(payload.get("proposal", {}).get("status", ""))
' 2>/dev/null || true)"
    if [[ "$status" == "$expected_status" ]]; then
      return 0
    fi
    sleep 1
  done
  fail "timed out waiting for proposal status $expected_status"
}

assert_tx_success() {
  local response_file="$1"
  python3 - "$response_file" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1]))
code = int(payload.get("code", 0))
if code != 0:
    raise SystemExit(f"transaction failed: code={code} raw_log={payload.get('raw_log', '')}")
PY
}

echo "=== start old binary and schedule governance upgrade ==="
OLD_PID="$(start_node "$OLD_BINARY" "$OLD_LOG")"
wait_for_height 2
START_HEIGHT="$(current_height)"
UPGRADE_HEIGHT=$((START_HEIGHT + 40))

"$OLD_BINARY" tx upgrade software-upgrade "$UPGRADE_NAME" \
  --title "Warbound Trophy v1" \
  --summary "Synthetic local upgrade proof" \
  --deposit 1uwolo \
  --upgrade-height "$UPGRADE_HEIGHT" \
  --upgrade-info '{"binaries":{"linux/amd64":"https://example.invalid/wolochaind"}}' \
  --daemon-name wolochaind \
  --no-checksum-required \
  --no-validate \
  --from "$KEY_NAME" \
  --keyring-backend test \
  --chain-id "$CHAIN_ID" \
  --home "$CHAIN_HOME" \
  --node "$NODE_URL" \
  --fees 0uwolo \
  --output json \
  --yes >"$WORK_DIR/upgrade-proposal-tx.json"
assert_tx_success "$WORK_DIR/upgrade-proposal-tx.json"

wait_for_proposal PROPOSAL_STATUS_VOTING_PERIOD
"$OLD_BINARY" tx gov vote 1 yes \
  --from "$KEY_NAME" \
  --keyring-backend test \
  --chain-id "$CHAIN_ID" \
  --home "$CHAIN_HOME" \
  --node "$NODE_URL" \
  --fees 0uwolo \
  --output json \
  --yes >"$WORK_DIR/upgrade-vote-tx.json"
assert_tx_success "$WORK_DIR/upgrade-vote-tx.json"
wait_for_proposal PROPOSAL_STATUS_PASSED

"$OLD_BINARY" query bank balance "$VALIDATOR_ADDRESS" uwolo \
  --home "$CHAIN_HOME" --node "$NODE_URL" --output json >"$WORK_DIR/balance-before.json"
"$OLD_BINARY" query bank total-supply-of uwolo \
  --home "$CHAIN_HOME" --node "$NODE_URL" --output json >"$WORK_DIR/supply-before.json"
"$OLD_BINARY" query staking validators \
  --home "$CHAIN_HOME" --node "$NODE_URL" --output json >"$WORK_DIR/validators-before.json"

echo "=== wait for old binary to halt at height $UPGRADE_HEIGHT ==="
deadline=$((SECONDS + TIMEOUT_SECONDS))
while (( SECONDS < deadline )); do
  if [[ -f "$CHAIN_HOME/data/upgrade-info.json" ]]; then
    break
  fi
  sleep 1
done
if [[ ! -f "$CHAIN_HOME/data/upgrade-info.json" ]]; then
  fail "old binary did not write upgrade-info.json"
fi

HALTED_HEIGHT="$(current_height)"
sleep 2
if [[ "$(current_height)" != "$HALTED_HEIGHT" ]] ||
  (( HALTED_HEIGHT < UPGRADE_HEIGHT - 1 || HALTED_HEIGHT > UPGRADE_HEIGHT )); then
  fail "old binary did not halt before the planned upgrade height"
fi

kill -INT "$OLD_PID" 2>/dev/null || true
wait "$OLD_PID" 2>/dev/null || true
OLD_PID=""

python3 - "$CHAIN_HOME/data/upgrade-info.json" "$UPGRADE_NAME" "$UPGRADE_HEIGHT" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1]))
assert payload["name"] == sys.argv[2], payload
assert int(payload["height"]) == int(sys.argv[3]), payload
PY

echo "=== start new binary and apply upgrade ==="
NEW_PID="$(start_node "$NEW_BINARY" "$NEW_LOG")"
wait_for_height $((UPGRADE_HEIGHT + 2))

"$NEW_BINARY" query wartrophy authority \
  --home "$CHAIN_HOME" --node "$NODE_URL" --output json >"$WORK_DIR/wartrophy-authority.json"
"$NEW_BINARY" query wartrophy trophies \
  --home "$CHAIN_HOME" --node "$NODE_URL" --output json >"$WORK_DIR/wartrophies.json"
"$NEW_BINARY" query bank balance "$VALIDATOR_ADDRESS" uwolo \
  --home "$CHAIN_HOME" --node "$NODE_URL" --output json >"$WORK_DIR/balance-after.json"
"$NEW_BINARY" query bank total-supply-of uwolo \
  --home "$CHAIN_HOME" --node "$NODE_URL" --output json >"$WORK_DIR/supply-after.json"
"$NEW_BINARY" query staking validators \
  --home "$CHAIN_HOME" --node "$NODE_URL" --output json >"$WORK_DIR/validators-after.json"
"$NEW_BINARY" query upgrade applied "$UPGRADE_NAME" \
  --home "$CHAIN_HOME" --node "$NODE_URL" --output json >"$WORK_DIR/upgrade-applied.json"

python3 - "$WORK_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])

def load(name):
    return json.loads((root / name).read_text())

before_balance = load("balance-before.json")["balance"]
after_balance = load("balance-after.json")["balance"]
assert before_balance == after_balance, (before_balance, after_balance)

before_supply = load("supply-before.json")["amount"]
after_supply = load("supply-after.json")["amount"]
assert before_supply == after_supply, (before_supply, after_supply)

def validators_from(payload):
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("validators"), list):
        return payload["validators"]
    staking = payload.get("staking")
    if isinstance(staking, dict) and isinstance(staking.get("validators"), list):
        return staking["validators"]
    app_state = payload.get("app_state")
    if isinstance(app_state, dict):
        staking = app_state.get("staking")
        if isinstance(staking, dict) and isinstance(staking.get("validators"), list):
            return staking["validators"]
    return []

def validator_snapshot(payload):
    return sorted(
        (
            item.get("operator_address", ""),
            item.get("status", ""),
            item.get("tokens", ""),
            item.get("delegator_shares", ""),
            item.get("jailed", False),
        )
        for item in validators_from(payload)
    )

before_validators = validator_snapshot(load("validators-before.json"))
after_validators = validator_snapshot(load("validators-after.json"))
assert before_validators == after_validators, (before_validators, after_validators)

authority = load("wartrophy-authority.json")["authority"]
assert authority.startswith("wolo1"), authority
assert load("wartrophies.json").get("trophies", []) == []
assert int(load("upgrade-applied.json")["height"]) > 0
PY

echo "=== stop upgraded node and validate exported state ==="
kill -INT "$NEW_PID" 2>/dev/null || true
wait "$NEW_PID" 2>/dev/null || true
NEW_PID=""

"$NEW_BINARY" export --home "$CHAIN_HOME" >"$WORK_DIR/export.json"
"$NEW_BINARY" init export-validation \
  --chain-id "$CHAIN_ID" \
  --home "$WORK_DIR/export-home" >/dev/null 2>&1
python3 - "$WORK_DIR/export.json" "$WORK_DIR/export-home/config/genesis.json" <<'PY'
import json
import sys
from pathlib import Path

exported = json.loads(Path(sys.argv[1]).read_text())
genesis_path = Path(sys.argv[2])
genesis = json.loads(genesis_path.read_text())

genesis["app_state"] = exported["app_state"]
genesis["validators"] = exported.get("validators", genesis.get("validators", []))
export_height = exported.get("height") or exported.get("initial_height") or genesis.get("initial_height") or "1"
genesis["initial_height"] = str(export_height)
if exported.get("consensus_params") is not None:
    genesis["consensus_params"] = exported["consensus_params"]

assert "wartrophy" in genesis["app_state"]
genesis_path.write_text(json.dumps(genesis, indent=2) + "\n")
PY
"$NEW_BINARY" genesis validate --home "$WORK_DIR/export-home" >/dev/null

if [[ "$(grep -c 'applying upgrade \"warbound-trophy-v1\"' "$NEW_LOG" || true)" -ne 1 ]]; then
  fail "upgrade handler did not execute exactly once"
fi

POST_HEIGHT="$(python3 - "$WORK_DIR/upgrade-applied.json" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1]))["height"])
PY
)"

echo "upgrade_name=$UPGRADE_NAME"
echo "old_commit=$(git rev-parse "$OLD_COMMIT")"
echo "upgrade_height=$UPGRADE_HEIGHT"
echo "applied_height=$POST_HEIGHT"
echo "post_upgrade_height=$((UPGRADE_HEIGHT + 2))"
echo "bank_balance_preserved=true"
echo "total_supply_preserved=true"
echo "staking_validators_preserved=true"
echo "wartrophy_query_ok=true"
echo "exported_genesis_valid=true"
echo "handler_execution_count=1"
echo "mainnet_state_used=false"
echo "synthetic_state_used=true"
