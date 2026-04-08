#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BIN="${WOLO_BIN:-$ROOT/build/wolochaind}"
HOME_DIR="${WOLO_HOME:-$HOME/.wolochain}"
RPC_HTTP="${WOLO_RPC_HTTP:-http://127.0.0.1:26657}"
REST_HTTP="${WOLO_REST_HTTP:-${WOLO_REST_URL:-http://127.0.0.1:1317}}"

EXPECTED_CHAIN_ID="wolo-testnet"
EXPECTED_BASE_DENOM="uwolo"
EXPECTED_DISPLAY_DENOM="wolo"
EXPECTED_PREFIX="wolo"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

require_fixed() {
  local needle="$1"
  local path="$2"
  local label="$3"
  if ! rg -q --fixed-strings "$needle" "$path"; then
    fail "$label"
  fi
}

echo "=== repo drift scan ==="
legacy_hits="$(rg -n 'wolo-1|wolo-testnet-1' . \
  -g '!build/**' \
  -g '!.git/**' \
  -g '!scripts/check-chain-invariants.sh' || true)"
if [[ -n "$legacy_hits" ]]; then
  echo "$legacy_hits"
  fail "Legacy chain IDs are still present in the repo."
fi

require_fixed 'AccountAddressPrefix = "wolo"' app/app.go 'app/app.go must keep the wolo address prefix.'
require_fixed 'sdk.DefaultBondDenom = "uwolo"' app/app.go 'app/app.go must keep uwolo as the default bond denom.'
require_fixed 'default_denom: uwolo' config.yml 'config.yml must keep uwolo as the default denom.'
require_fixed 'CHAIN_ID="${WOLO_CHAIN_ID:-wolo-testnet}"' scripts/bootstrap-local.sh 'bootstrap-local.sh must default to wolo-testnet.'
require_fixed 'g["chain_id"] = "wolo-testnet"' scripts/bootstrap-local.sh 'bootstrap-local.sh must patch genesis to wolo-testnet.'
require_fixed 'app["staking"]["params"]["bond_denom"] = "uwolo"' scripts/bootstrap-local.sh 'bootstrap-local.sh must patch staking bond denom to uwolo.'
require_fixed 'params["mint_denom"] = "uwolo"' scripts/bootstrap-local.sh 'bootstrap-local.sh must patch mint denom to uwolo.'
require_fixed '"display": "wolo"' scripts/bootstrap-local.sh 'bootstrap-local.sh must publish wolo as the display denom.'

if [[ ! -x "$BIN" ]]; then
  echo "=== build binary ==="
  mkdir -p "$ROOT/build"
  go build -o "$BIN" ./cmd/wolochaind
fi

GENESIS_PATH="$HOME_DIR/config/genesis.json"
if [[ ! -f "$GENESIS_PATH" ]]; then
  fail "Missing genesis at $GENESIS_PATH. Run ./scripts/bootstrap-local.sh first."
fi

echo
echo "=== local genesis ==="
export WOLO_INVARIANT_GENESIS="$GENESIS_PATH"
export WOLO_INVARIANT_CHAIN_ID="$EXPECTED_CHAIN_ID"
export WOLO_INVARIANT_BASE_DENOM="$EXPECTED_BASE_DENOM"
export WOLO_INVARIANT_DISPLAY_DENOM="$EXPECTED_DISPLAY_DENOM"
python3 - <<'PY'
import json
import os
import sys
from pathlib import Path

path = Path(os.environ["WOLO_INVARIANT_GENESIS"])
expected_chain_id = os.environ["WOLO_INVARIANT_CHAIN_ID"]
expected_base = os.environ["WOLO_INVARIANT_BASE_DENOM"]
expected_display = os.environ["WOLO_INVARIANT_DISPLAY_DENOM"]

payload = json.loads(path.read_text())
app = payload["app_state"]
bank = app["bank"]
metadata = next((entry for entry in bank.get("denom_metadata", []) if entry.get("base") == expected_base), None)
errors = []

if payload.get("chain_id") != expected_chain_id:
    errors.append(f'genesis chain_id={payload.get("chain_id")} expected {expected_chain_id}')

staking_denom = app.get("staking", {}).get("params", {}).get("bond_denom")
if staking_denom != expected_base:
    errors.append(f"staking bond_denom={staking_denom} expected {expected_base}")

mint_denom = app.get("mint", {}).get("params", {}).get("mint_denom")
if mint_denom != expected_base:
    errors.append(f"mint denom={mint_denom} expected {expected_base}")

if not metadata:
    errors.append(f"bank denom metadata for {expected_base} is missing")
else:
    if metadata.get("display") != expected_display:
        errors.append(f'denom display={metadata.get("display")} expected {expected_display}')
    if metadata.get("base") != expected_base:
        errors.append(f'denom base={metadata.get("base")} expected {expected_base}')

print(json.dumps({
    "chain_id": payload.get("chain_id"),
    "bond_denom": staking_denom,
    "mint_denom": mint_denom,
    "metadata_base": metadata.get("base") if metadata else None,
    "metadata_display": metadata.get("display") if metadata else None,
}, indent=2))

if errors:
    print("\n".join(errors), file=sys.stderr)
    sys.exit(1)
PY

echo
echo "=== live chain ==="
doctor_output="$(
  WOLO_SETTLEMENT_HOME="$HOME_DIR" \
  WOLO_SETTLEMENT_RPC_HTTP="$RPC_HTTP" \
  WOLO_SETTLEMENT_REST_URL="$REST_HTTP" \
  "$BIN" settlement doctor
)"
export WOLO_DOCTOR_OUTPUT="$doctor_output"
python3 - <<'PY'
import json
import os
import sys

payload = json.loads(os.environ["WOLO_DOCTOR_OUTPUT"])
print(json.dumps(payload, indent=2))
if not payload.get("ok"):
    sys.exit(1)
PY

echo
echo "Chain invariants OK."
