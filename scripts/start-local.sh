#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BIN="$ROOT/build/wolochaind"
HOME_DIR="${WOLO_HOME:-$HOME/.wolochain}"
RPC_HTTP="${WOLO_RPC_HTTP:-http://127.0.0.1:26657}"
REST_HTTP="${WOLO_REST_HTTP:-${WOLO_REST_URL:-http://127.0.0.1:1317}}"
MIN_GAS_PRICES="${WOLO_MIN_GAS_PRICES:-0uwolo}"
START_BACKGROUND="${WOLO_START_BACKGROUND:-0}"
WAIT_READY="${WOLO_WAIT_READY:-0}"
WAIT_TIMEOUT_SEC="${WOLO_WAIT_TIMEOUT_SEC:-60}"
LOG_FILE="${WOLO_LOG_FILE:-/tmp/wolochain-local.log}"

if [[ ! -x "$BIN" ]]; then
  mkdir -p "$ROOT/build"
  go build -o "$BIN" ./cmd/wolochaind
fi

wait_for_ready() {
  local deadline=$((SECONDS + WAIT_TIMEOUT_SEC))

  while (( SECONDS < deadline )); do
    if curl -fsS "$RPC_HTTP/status" 2>/dev/null | python3 -c '
import json, sys
payload = json.load(sys.stdin)
result = payload.get("result", {})
node_info = result.get("node_info", {})
sync_info = result.get("sync_info", {})
chain_id = node_info.get("network") or ""
height = int(sync_info.get("latest_block_height") or "0")
sys.exit(0 if chain_id and height >= 1 else 1)
' >/dev/null 2>&1 && curl -fsS "$REST_HTTP/cosmos/base/tendermint/v1beta1/node_info" >/dev/null 2>&1; then
      return 0
    fi

    sleep 1
  done

  echo "WoloChain did not become ready within ${WAIT_TIMEOUT_SEC}s at $RPC_HTTP" >&2
  if [[ -f "$LOG_FILE" ]]; then
    echo "--- recent log tail ($LOG_FILE) ---" >&2
    tail -n 40 "$LOG_FILE" >&2 || true
  fi
  return 1
}

print_status_summary() {
  curl -fsS "$RPC_HTTP/status" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
result = payload.get("result", {})
node_info = result.get("node_info", {})
sync_info = result.get("sync_info", {})
print("chain_id=" + str(node_info.get("network", "unknown")))
print("moniker=" + str(node_info.get("moniker", "unknown")))
print("height=" + str(sync_info.get("latest_block_height", "0")))
print("block_time=" + str(sync_info.get("latest_block_time", "unknown")))
'
}

CMD=(
  "$BIN" start
  --home "$HOME_DIR"
  --minimum-gas-prices "$MIN_GAS_PRICES"
)

if [[ "$START_BACKGROUND" == "1" ]]; then
  "${CMD[@]}" >"$LOG_FILE" 2>&1 &
  PID=$!
  echo "started wolochaind pid=$PID"
  echo "log=$LOG_FILE"

  if [[ "$WAIT_READY" == "1" ]]; then
    wait_for_ready
    ./scripts/check-chain-invariants.sh >/dev/null
    print_status_summary
    echo "invariants=ok"
  fi

  exit 0
fi

if [[ "$WAIT_READY" == "1" ]]; then
  "${CMD[@]}" >"$LOG_FILE" 2>&1 &
  PID=$!
  trap 'kill "$PID" 2>/dev/null || true' INT TERM EXIT

  echo "started wolochaind pid=$PID"
  echo "log=$LOG_FILE"

  wait_for_ready
  ./scripts/check-chain-invariants.sh >/dev/null
  print_status_summary
  echo "invariants=ok"

  trap - INT TERM EXIT
  wait "$PID"
else
  exec "${CMD[@]}"
fi
