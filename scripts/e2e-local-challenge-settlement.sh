#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BIN="${WOLO_E2E_BIN:-$ROOT/build/wolochaind}"
HOME_DIR="${WOLO_HOME:-$HOME/.wolochain}"
CHAIN_ID="${WOLO_CHAIN_ID:-wolo-testnet}"
NODE="${WOLO_NODE:-tcp://127.0.0.1:26657}"
RPC_HTTP="${WOLO_RPC_HTTP:-http://127.0.0.1:26657}"
REST_HTTP="${WOLO_REST_HTTP:-${WOLO_REST_URL:-http://127.0.0.1:1317}}"
FUNDER_KEY="${WOLO_E2E_FUNDER_KEY:-founderoperating}"
RUN_SUFFIX="${WOLO_E2E_RUN_SUFFIX:-$(date -u +%Y%m%d%H%M%S)-$$}"
SETTLEMENT_RUN_ID="${WOLO_E2E_SETTLEMENT_RUN_ID:-local-e2e-$RUN_SUFFIX}"
WORK_DIR="${WOLO_E2E_WORK_DIR:-$ROOT/build/local-settlement-e2e/$SETTLEMENT_RUN_ID}"
STATE_DIR="$WORK_DIR/state"
FEES="${WOLO_E2E_FEES:-0uwolo}"
WAGER_UWOLO="${WOLO_E2E_WAGER_UWOLO:-1000000}"
GUARANTEE_UWOLO="${WOLO_E2E_GUARANTEE_UWOLO:-500000}"
PLAYER_FUND_UWOLO="${WOLO_E2E_PLAYER_FUND_UWOLO:-5000000}"
WAIT_TIMEOUT_SEC="${WOLO_E2E_WAIT_TIMEOUT_SEC:-45}"

LEFT_KEY="e2e-left-$RUN_SUFFIX"
RIGHT_KEY="e2e-right-$RUN_SUFFIX"
PAYOUT_KEY="e2e-payout-$RUN_SUFFIX"
ESCROW_KEY="e2e-escrow-$RUN_SUFFIX"
SOURCE_APP="aoe2hdbets"
CHALLENGE_ID="local-e2e-challenge-$RUN_SUFFIX"
LEFT_ID="local-left-$RUN_SUFFIX"
RIGHT_ID="local-right-$RUN_SUFFIX"

mkdir -p "$WORK_DIR" "$STATE_DIR"

if [[ -z "${WOLO_E2E_BIN:-}" ]]; then
  mkdir -p "$ROOT/build"
  go build -o "$BIN" ./cmd/wolochaind
elif [[ ! -x "$BIN" ]]; then
  echo "Configured WOLO_E2E_BIN is not executable: $BIN" >&2
  exit 1
fi

if ! curl -fsS "$RPC_HTTP/status" >/dev/null 2>&1; then
  echo "WoloChain RPC is not reachable at $RPC_HTTP" >&2
  echo "Start the local chain first with: ./scripts/reset-and-start-local.sh" >&2
  exit 1
fi

if ! curl -fsS "$REST_HTTP/cosmos/base/tendermint/v1beta1/node_info" >/dev/null 2>&1; then
  echo "WoloChain REST is not reachable at $REST_HTTP" >&2
  echo "Start the local chain first with: ./scripts/reset-and-start-local.sh" >&2
  exit 1
fi

./scripts/check-chain-invariants.sh >/dev/null

addr() {
  "$BIN" keys show "$1" --address --keyring-backend test --home "$HOME_DIR"
}

ensure_key() {
  local name="$1"
  if ! "$BIN" keys show "$name" --address --keyring-backend test --home "$HOME_DIR" >/dev/null 2>&1; then
    "$BIN" keys add "$name" --keyring-backend test --home "$HOME_DIR" --output json >"$WORK_DIR/$name.key.json" 2>"$WORK_DIR/$name.key.stderr"
  fi
  addr "$name"
}

extract_tx_hash() {
  local file="$1"
  python3 - "$file" <<'PY'
import json
import sys
from pathlib import Path

raw = Path(sys.argv[1]).read_text()
start = raw.find("{")
end = raw.rfind("}")
if start < 0 or end < start:
    raise SystemExit("tx output did not contain JSON")
payload = json.loads(raw[start:end + 1])
tx_hash = (payload.get("txhash") or payload.get("tx_hash") or "").strip().upper()
if not tx_hash:
    raise SystemExit("tx output did not contain txhash")
print(tx_hash)
PY
}

wait_tx() {
  local tx_hash="$1"
  local label="$2"
  local deadline=$((SECONDS + WAIT_TIMEOUT_SEC))

  while (( SECONDS < deadline )); do
    if "$BIN" query tx "$tx_hash" --node "$NODE" --output json >"$WORK_DIR/$label.query.json" 2>"$WORK_DIR/$label.query.stderr"; then
      return 0
    fi
    sleep 1
  done

  echo "Timed out waiting for $label tx $tx_hash" >&2
  if [[ -s "$WORK_DIR/$label.query.stderr" ]]; then
    cat "$WORK_DIR/$label.query.stderr" >&2
  fi
  return 1
}

tx_send() {
  local label="$1"
  local from="$2"
  local to="$3"
  local amount_uwolo="$4"
  local memo="${5:-}"
  local out="$WORK_DIR/$label.broadcast.json"
  local err="$WORK_DIR/$label.broadcast.stderr"

  local cmd=(
    "$BIN" tx bank send "$from" "$to" "${amount_uwolo}uwolo"
    --yes
    --output json
    --broadcast-mode sync
    --chain-id "$CHAIN_ID"
    --home "$HOME_DIR"
    --keyring-backend test
    --node "$NODE"
    --gas auto
    --gas-adjustment 1.5
    --fees "$FEES"
  )
  if [[ -n "$memo" ]]; then
    cmd+=(--note "$memo")
  fi

  if ! "${cmd[@]}" >"$out" 2>"$err"; then
    echo "Failed to broadcast $label" >&2
    cat "$err" >&2 || true
    exit 1
  fi

  local tx_hash
  tx_hash="$(extract_tx_hash "$out")"
  wait_tx "$tx_hash" "$label"
  printf '%s\n' "$tx_hash"
}

assert_json_ok() {
  local file="$1"
  local label="$2"
  python3 - "$file" "$label" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
label = sys.argv[2]
if not payload.get("ok"):
    print(f"{label} failed:", json.dumps(payload, indent=2), file=sys.stderr)
    raise SystemExit(1)
PY
}

assert_json_found() {
  local file="$1"
  local label="$2"
  python3 - "$file" "$label" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
label = sys.argv[2]
if not payload.get("found"):
    print(f"{label} failed:", json.dumps(payload, indent=2), file=sys.stderr)
    raise SystemExit(1)
PY
}

export WOLO_SETTLEMENT_HOME="$HOME_DIR"
export WOLO_SETTLEMENT_KEYRING_BACKEND="test"
export WOLO_SETTLEMENT_CHAIN_ID="$CHAIN_ID"
export WOLO_SETTLEMENT_NODE="$NODE"
export WOLO_SETTLEMENT_RPC_HTTP="$RPC_HTTP"
export WOLO_SETTLEMENT_REST_URL="$REST_HTTP"
export WOLO_SETTLEMENT_STATE_DIR="$STATE_DIR"
export WOLO_SETTLEMENT_BROADCAST_MODE="sync"
export WOLO_SETTLEMENT_GAS="auto"
export WOLO_SETTLEMENT_GAS_ADJUSTMENT="1.5"
export WOLO_SETTLEMENT_FEES="$FEES"
export WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO="0"
export WOLO_SETTLEMENT_FEE_HEADROOM_UWOLO="0"
export WOLO_SETTLEMENT_ESCROW_AUTO_TOP_UP_ENABLED="true"

if ! addr "$FUNDER_KEY" >/dev/null 2>&1; then
  echo "Missing local funder key '$FUNDER_KEY' in $HOME_DIR." >&2
  echo "Run ./scripts/bootstrap-local.sh or ./scripts/reset-and-start-local.sh first." >&2
  exit 1
fi

LEFT_ADDR="$(ensure_key "$LEFT_KEY")"
RIGHT_ADDR="$(ensure_key "$RIGHT_KEY")"
PAYOUT_ADDR="$(ensure_key "$PAYOUT_KEY")"
ESCROW_ADDR="$(ensure_key "$ESCROW_KEY")"
TREASURY_ADDR="$(addr communitytreasury)"

export WOLO_SETTLEMENT_PAYOUT_KEY_NAME="$PAYOUT_KEY"
export WOLO_SETTLEMENT_PAYOUT_ADDRESS="$PAYOUT_ADDR"
export WOLO_SETTLEMENT_ESCROW_KEY_NAME="$ESCROW_KEY"
export WOLO_SETTLEMENT_ESCROW_ADDRESS="$ESCROW_ADDR"
export WOLO_SETTLEMENT_TREASURY_ADDRESS="$TREASURY_ADDR"

TOTAL_DEPOSIT_UWOLO="$((WAGER_UWOLO + GUARANTEE_UWOLO))"

echo "=== local challenge settlement e2e ==="
printf 'settlement_run_id=%s\n' "$SETTLEMENT_RUN_ID"
printf 'work_dir=%s\n' "$WORK_DIR"
printf 'left=%s\nright=%s\npayout=%s\nescrow=%s\ntreasury=%s\n' "$LEFT_ADDR" "$RIGHT_ADDR" "$PAYOUT_ADDR" "$ESCROW_ADDR" "$TREASURY_ADDR"

echo
echo "=== fund disposable player keys ==="
LEFT_FUND_TX="$(tx_send fund-left "$FUNDER_KEY" "$LEFT_ADDR" "$PLAYER_FUND_UWOLO" "local e2e fund left")"
RIGHT_FUND_TX="$(tx_send fund-right "$FUNDER_KEY" "$RIGHT_ADDR" "$PLAYER_FUND_UWOLO" "local e2e fund right")"
printf 'left_fund_tx=%s\nright_fund_tx=%s\n' "$LEFT_FUND_TX" "$RIGHT_FUND_TX"

LEFT_MEMO="wolo.challenge.funding.v1:app=$SOURCE_APP&sid=$SETTLEMENT_RUN_ID&cid=$CHALLENGE_ID&side=left&pid=$LEFT_ID&w=$WAGER_UWOLO&g=$GUARANTEE_UWOLO&t=$TOTAL_DEPOSIT_UWOLO"
RIGHT_MEMO="wolo.challenge.funding.v1:app=$SOURCE_APP&sid=$SETTLEMENT_RUN_ID&cid=$CHALLENGE_ID&side=right&pid=$RIGHT_ID&w=$WAGER_UWOLO&g=$GUARANTEE_UWOLO&t=$TOTAL_DEPOSIT_UWOLO"

echo
echo "=== send challenge funding deposits into escrow ==="
LEFT_FUNDING_TX="$(tx_send left-funding "$LEFT_KEY" "$ESCROW_ADDR" "$TOTAL_DEPOSIT_UWOLO" "$LEFT_MEMO")"
RIGHT_FUNDING_TX="$(tx_send right-funding "$RIGHT_KEY" "$ESCROW_ADDR" "$TOTAL_DEPOSIT_UWOLO" "$RIGHT_MEMO")"
printf 'left_funding_tx=%s\nright_funding_tx=%s\n' "$LEFT_FUNDING_TX" "$RIGHT_FUNDING_TX"

"$BIN" settlement challenge funding verify \
  --tx-hash "$LEFT_FUNDING_TX" \
  --expected-sender "$LEFT_ADDR" \
  --source-app "$SOURCE_APP" \
  --settlement-run-id "$SETTLEMENT_RUN_ID" \
  --challenge-id "$CHALLENGE_ID" \
  --participant-side left \
  --participant-id "$LEFT_ID" \
  --expected-amount-uwolo "$TOTAL_DEPOSIT_UWOLO" \
  --wager-uwolo "$WAGER_UWOLO" \
  --guarantee-uwolo "$GUARANTEE_UWOLO" >"$WORK_DIR/left-funding-verify.json"
assert_json_ok "$WORK_DIR/left-funding-verify.json" "left funding verify"

"$BIN" settlement challenge funding verify \
  --tx-hash "$RIGHT_FUNDING_TX" \
  --expected-sender "$RIGHT_ADDR" \
  --source-app "$SOURCE_APP" \
  --settlement-run-id "$SETTLEMENT_RUN_ID" \
  --challenge-id "$CHALLENGE_ID" \
  --participant-side right \
  --participant-id "$RIGHT_ID" \
  --expected-amount-uwolo "$TOTAL_DEPOSIT_UWOLO" \
  --wager-uwolo "$WAGER_UWOLO" \
  --guarantee-uwolo "$GUARANTEE_UWOLO" >"$WORK_DIR/right-funding-verify.json"
assert_json_ok "$WORK_DIR/right-funding-verify.json" "right funding verify"

REQUEST_FILE="$WORK_DIR/challenge-one-noshow-request.json"
export REQUEST_FILE SETTLEMENT_RUN_ID SOURCE_APP CHALLENGE_ID LEFT_ID RIGHT_ID LEFT_ADDR RIGHT_ADDR TREASURY_ADDR LEFT_FUNDING_TX RIGHT_FUNDING_TX WAGER_UWOLO GUARANTEE_UWOLO
python3 <<'PY'
import json
import os
from pathlib import Path

request = {
    "settlement_run_id": os.environ["SETTLEMENT_RUN_ID"],
    "source_app": os.environ["SOURCE_APP"],
    "challenge_id": os.environ["CHALLENGE_ID"],
    "treasury_address": os.environ["TREASURY_ADDR"],
    "note": "local e2e one no-show: left checked in, right no-show",
    "memo": "local-e2e-one-noshow",
    "funding": [
        {
            "funding_tx_hash": os.environ["LEFT_FUNDING_TX"],
            "depositor_address": os.environ["LEFT_ADDR"],
            "settlement_run_id": os.environ["SETTLEMENT_RUN_ID"],
            "participant_side": "left",
            "participant_id": os.environ["LEFT_ID"],
            "expected_amount_uwolo": str(int(os.environ["WAGER_UWOLO"]) + int(os.environ["GUARANTEE_UWOLO"])),
            "wager_uwolo": os.environ["WAGER_UWOLO"],
            "guarantee_uwolo": os.environ["GUARANTEE_UWOLO"],
        },
        {
            "funding_tx_hash": os.environ["RIGHT_FUNDING_TX"],
            "depositor_address": os.environ["RIGHT_ADDR"],
            "settlement_run_id": os.environ["SETTLEMENT_RUN_ID"],
            "participant_side": "right",
            "participant_id": os.environ["RIGHT_ID"],
            "expected_amount_uwolo": str(int(os.environ["WAGER_UWOLO"]) + int(os.environ["GUARANTEE_UWOLO"])),
            "wager_uwolo": os.environ["WAGER_UWOLO"],
            "guarantee_uwolo": os.environ["GUARANTEE_UWOLO"],
        },
    ],
    "transfers": [
        {
            "participant_side": "left",
            "participant_id": os.environ["LEFT_ID"],
            "bucket": "guarantee",
            "reason": "return",
            "to_address": os.environ["LEFT_ADDR"],
            "amount_uwolo": os.environ["GUARANTEE_UWOLO"],
            "memo": "local-e2e-left-guarantee-return",
        },
        {
            "participant_side": "right",
            "participant_id": os.environ["RIGHT_ID"],
            "bucket": "guarantee",
            "reason": "forfeit",
            "to_address": os.environ["LEFT_ADDR"],
            "amount_uwolo": os.environ["GUARANTEE_UWOLO"],
            "memo": "local-e2e-right-guarantee-forfeit",
        },
        {
            "participant_side": "left",
            "participant_id": os.environ["LEFT_ID"],
            "bucket": "wager",
            "reason": "refund",
            "to_address": os.environ["LEFT_ADDR"],
            "amount_uwolo": os.environ["WAGER_UWOLO"],
            "memo": "local-e2e-left-wager-refund",
        },
        {
            "participant_side": "right",
            "participant_id": os.environ["RIGHT_ID"],
            "bucket": "wager",
            "reason": "refund",
            "to_address": os.environ["RIGHT_ADDR"],
            "amount_uwolo": os.environ["WAGER_UWOLO"],
            "memo": "local-e2e-right-wager-refund",
        },
    ],
}
Path(os.environ["REQUEST_FILE"]).write_text(json.dumps(request, indent=2) + "\n")
PY

echo
echo "=== dry-run challenge settlement ==="
"$BIN" settlement challenge validate --file "$REQUEST_FILE" >"$WORK_DIR/validate.json"
assert_json_ok "$WORK_DIR/validate.json" "challenge dry-run"

echo
echo "=== execute challenge settlement ==="
"$BIN" settlement challenge execute --file "$REQUEST_FILE" >"$WORK_DIR/execute.json"
assert_json_ok "$WORK_DIR/execute.json" "challenge execute"

echo
echo "=== inspect and audit stored challenge settlement ==="
"$BIN" settlement challenge inspect --settlement-id "$SETTLEMENT_RUN_ID" >"$WORK_DIR/inspect.json"
assert_json_found "$WORK_DIR/inspect.json" "challenge inspect"

"$BIN" settlement challenge audit --settlement-id "$SETTLEMENT_RUN_ID" >"$WORK_DIR/audit.json"
assert_json_ok "$WORK_DIR/audit.json" "challenge audit"

python3 - "$WORK_DIR/execute.json" "$WORK_DIR/audit.json" "$WORK_DIR/summary.json" <<'PY'
import json
import sys
from pathlib import Path

execute = json.loads(Path(sys.argv[1]).read_text())
audit = json.loads(Path(sys.argv[2]).read_text())
summary = {
    "ok": bool(execute.get("ok") and audit.get("ok")),
    "settlement_run_id": execute.get("settlement_run_id"),
    "execute_status": execute.get("status"),
    "confirmed_transfer_count": execute.get("confirmed_transfer_count"),
    "requested_total_uwolo": execute.get("requested_total_uwolo"),
    "confirmed_total_uwolo": execute.get("confirmed_total_uwolo"),
    "top_up_required": bool((execute.get("top_up") or {}).get("required")),
    "top_up_tx_hash": ((execute.get("top_up") or {}).get("response") or {}).get("tx_hash"),
    "audit_ok": audit.get("ok"),
    "audit_transfer_tx_checked_count": (audit.get("summary") or {}).get("transfer_tx_checked_count"),
    "audit_top_up_tx_checked": (audit.get("summary") or {}).get("top_up_tx_checked"),
}
Path(sys.argv[3]).write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
PY

echo
echo "Artifacts written to $WORK_DIR"
