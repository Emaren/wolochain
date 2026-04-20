#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BIN="${WOLO_BIN:-$ROOT/build/wolochaind}"
HOME_DIR="${WOLO_HOME:-$HOME/.wolochain}"
RPC_HTTP="${WOLO_RPC_HTTP:-http://127.0.0.1:26657}"
REST_HTTP="${WOLO_REST_HTTP:-${WOLO_REST_URL:-http://127.0.0.1:1317}}"
SKIP_RUNTIME_CHECKS="${WOLO_SKIP_RUNTIME_CHECKS:-0}"

EXPECTED_CHAIN_ID="wolo-testnet"
EXPECTED_BASE_DENOM="uwolo"
EXPECTED_DISPLAY_DENOM="wolo"
EXPECTED_PREFIX="wolo"
EXPECTED_SYMBOL="WOLO"
EXPECTED_DECIMALS="6"
EXPECTED_TOTAL_SUPPLY="100000000000000"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    fail "Missing required command: $1"
  fi
}

require_fixed() {
  local needle="$1"
  local path="$2"
  local label="$3"

  if command -v rg >/dev/null 2>&1; then
    if rg -q --fixed-strings "$needle" "$path"; then
      return
    fi
  elif grep -Fq -- "$needle" "$path"; then
    return
  fi

  fail "$label"
}

scan_repo_pattern() {
  local pattern="$1"
  local label="$2"
  local hits

  if command -v rg >/dev/null 2>&1; then
    hits="$(rg -n -e "$pattern" "${TRACKED_FILES[@]}" || true)"
  else
    hits="$(grep -nE -- "$pattern" "${TRACKED_FILES[@]}" || true)"
  fi
  if [[ -n "$hits" ]]; then
    printf '%s\n' "$hits"
    fail "$label"
  fi
}

require_cmd git
require_cmd python3

mapfile -t TRACKED_FILES < <(git ls-files -- README.md config.yml go.mod app cmd docs proto scripts)
if (( ${#TRACKED_FILES[@]} == 0 )); then
  fail "Unable to collect tracked repo files for invariant scanning."
fi

filtered_files=()
for path in "${TRACKED_FILES[@]}"; do
  if [[ "$path" != "scripts/check-chain-invariants.sh" ]]; then
    filtered_files+=("$path")
  fi
done
TRACKED_FILES=("${filtered_files[@]}")

echo "=== repo drift scan ==="
scan_repo_pattern 'wolo-1|wolo-testnet-1' 'Legacy chain IDs are still present in tracked repo files.'
scan_repo_pattern '\butoken\b|\bustake\b' 'Legacy scaffold denoms are still present in tracked repo files.'
scan_repo_pattern 'tokenchain' 'Legacy scaffold chain naming is still present in tracked repo files.'
scan_repo_pattern '\bcosmos(valoper|valcons)?1[0-9a-z]{10,}\b' 'Legacy cosmos bech32 addresses are still present in tracked repo files.'
scan_repo_pattern 'default_denom:[[:space:]]*stake' 'config-level stake defaults are still present in tracked repo files.'
scan_repo_pattern 'bond_denom[^[:alnum:]]*stake|mint_denom[^[:alnum:]]*stake' 'Genesis or app denom defaults still drift to stake in tracked repo files.'

require_fixed 'Name                 = "WoloChain"' app/app.go 'app/app.go must keep the canonical WoloChain app name.'
require_fixed 'AccountAddressPrefix = "wolo"' app/app.go 'app/app.go must keep the wolo address prefix.'
require_fixed 'sdk.DefaultBondDenom = "uwolo"' app/app.go 'app/app.go must keep uwolo as the default bond denom.'
require_fixed 'config.SetBech32PrefixForAccount(AccountAddressPrefix, accountPubKeyPrefix)' app/config.go 'app/config.go must wire account bech32 prefixes from the canonical wolo prefix.'
require_fixed 'default_denom: uwolo' config.yml 'config.yml must keep uwolo as the default denom.'
require_fixed 'MIN_GAS_PRICES="${WOLO_MIN_GAS_PRICES:-0uwolo}"' scripts/start-local.sh 'start-local.sh must keep 0uwolo as the local minimum gas price default.'
require_fixed 'CHAIN_ID="${WOLO_CHAIN_ID:-wolo-testnet}"' scripts/bootstrap-local.sh 'bootstrap-local.sh must default to wolo-testnet.'
require_fixed 'g["chain_id"] = "wolo-testnet"' scripts/bootstrap-local.sh 'bootstrap-local.sh must patch genesis to wolo-testnet.'
require_fixed 'app["staking"]["params"]["bond_denom"] = "uwolo"' scripts/bootstrap-local.sh 'bootstrap-local.sh must patch staking bond denom to uwolo.'
require_fixed 'params["mint_denom"] = "uwolo"' scripts/bootstrap-local.sh 'bootstrap-local.sh must patch mint denom to uwolo.'
require_fixed 'app["crisis"]["constant_fee"]["denom"] = "uwolo"' scripts/bootstrap-local.sh 'bootstrap-local.sh must patch crisis constant fee denom to uwolo.'
require_fixed '"base": "uwolo"' scripts/bootstrap-local.sh 'bootstrap-local.sh must publish uwolo as the canonical base denom.'
require_fixed '"display": "wolo"' scripts/bootstrap-local.sh 'bootstrap-local.sh must publish wolo as the display denom.'
require_fixed 'export WOLO_CHAIN_ID_FALLBACK="${WOLO_CHAIN_ID:-wolo-testnet}"' scripts/query-local-balances-json.sh 'query-local-balances-json.sh must fall back to wolo-testnet.'
require_fixed '"denom": {"base": "uwolo", "display": "wolo", "decimals": 6},' scripts/query-local-balances-json.sh 'query-local-balances-json.sh must publish canonical WOLO denom metadata.'
require_fixed 'settlementCanonicalChainID      = "wolo-testnet"' cmd/wolochaind/cmd/settlement.go 'settlement.go must keep wolo-testnet as the canonical chain ID.'
require_fixed 'settlementCanonicalBaseDenom    = "uwolo"' cmd/wolochaind/cmd/settlement.go 'settlement.go must keep uwolo as the canonical base denom.'
require_fixed 'settlementCanonicalDisplayDenom = "wolo"' cmd/wolochaind/cmd/settlement.go 'settlement.go must keep wolo as the canonical display denom.'
require_fixed 'settlementCanonicalPrefix       = "wolo"' cmd/wolochaind/cmd/settlement.go 'settlement.go must keep wolo as the canonical address prefix.'
require_fixed 'settlementDefaultGasPrices      = "0.025uwolo"' cmd/wolochaind/cmd/settlement.go 'settlement.go must keep uwolo in the default gas price setting.'
require_fixed 'WOLO_SETTLEMENT_CHAIN_ID="${WOLO_SETTLEMENT_CHAIN_ID:-wolo-testnet}"' scripts/check-settlement-cutover.sh 'check-settlement-cutover.sh must default to wolo-testnet.'
require_fixed 'WOLO_SETTLEMENT_BASE_DENOM="${WOLO_SETTLEMENT_BASE_DENOM:-uwolo}"' scripts/check-settlement-cutover.sh 'check-settlement-cutover.sh must default to uwolo.'
require_fixed 'WOLO_SETTLEMENT_DISPLAY_DENOM="${WOLO_SETTLEMENT_DISPLAY_DENOM:-wolo}"' scripts/check-settlement-cutover.sh 'check-settlement-cutover.sh must default to wolo.'
require_fixed 'WOLO_SETTLEMENT_ADDRESS_PREFIX="${WOLO_SETTLEMENT_ADDRESS_PREFIX:-wolo}"' scripts/check-settlement-cutover.sh 'check-settlement-cutover.sh must default to the wolo prefix.'
require_fixed 'WOLO_SETTLEMENT_CHAIN_ID="${WOLO_SETTLEMENT_CHAIN_ID:-wolo-testnet}"' scripts/check-settlement-alerts.sh 'check-settlement-alerts.sh must default to wolo-testnet.'
require_fixed 'WOLO_SETTLEMENT_BASE_DENOM="${WOLO_SETTLEMENT_BASE_DENOM:-uwolo}"' scripts/check-settlement-alerts.sh 'check-settlement-alerts.sh must default to uwolo.'
require_fixed 'WOLO_SETTLEMENT_DISPLAY_DENOM="${WOLO_SETTLEMENT_DISPLAY_DENOM:-wolo}"' scripts/check-settlement-alerts.sh 'check-settlement-alerts.sh must default to wolo.'
require_fixed 'WOLO_SETTLEMENT_ADDRESS_PREFIX="${WOLO_SETTLEMENT_ADDRESS_PREFIX:-wolo}"' scripts/check-settlement-alerts.sh 'check-settlement-alerts.sh must default to the wolo prefix.'
require_fixed 'WOLO_SETTLEMENT_CHAIN_ID="${WOLO_SETTLEMENT_CHAIN_ID:-wolo-testnet}"' scripts/verify-live-settlement.sh 'verify-live-settlement.sh must default to wolo-testnet.'
require_fixed 'WOLO_SETTLEMENT_BASE_DENOM="${WOLO_SETTLEMENT_BASE_DENOM:-uwolo}"' scripts/verify-live-settlement.sh 'verify-live-settlement.sh must default to uwolo.'
require_fixed 'WOLO_SETTLEMENT_DISPLAY_DENOM="${WOLO_SETTLEMENT_DISPLAY_DENOM:-wolo}"' scripts/verify-live-settlement.sh 'verify-live-settlement.sh must default to wolo.'
require_fixed 'WOLO_SETTLEMENT_ADDRESS_PREFIX="${WOLO_SETTLEMENT_ADDRESS_PREFIX:-wolo}"' scripts/verify-live-settlement.sh 'verify-live-settlement.sh must default to the wolo prefix.'
require_fixed 'export WOLO_SETTLEMENT_GAS_PRICES="0.025uwolo"' scripts/settlement-env.example 'settlement-env.example must keep uwolo in the default gas price example.'

if [[ "$SKIP_RUNTIME_CHECKS" == "1" ]]; then
  echo
  echo "Repo invariants OK (runtime checks skipped)."
  exit 0
fi

if [[ ! -x "$BIN" ]]; then
  echo "=== build binary ==="
  require_cmd go
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
export WOLO_INVARIANT_PREFIX="$EXPECTED_PREFIX"
export WOLO_INVARIANT_SYMBOL="$EXPECTED_SYMBOL"
export WOLO_INVARIANT_DECIMALS="$EXPECTED_DECIMALS"
export WOLO_INVARIANT_TOTAL_SUPPLY="$EXPECTED_TOTAL_SUPPLY"
python3 - <<'PY'
import json
import os
import sys
from pathlib import Path

path = Path(os.environ["WOLO_INVARIANT_GENESIS"])
expected_chain_id = os.environ["WOLO_INVARIANT_CHAIN_ID"]
expected_base = os.environ["WOLO_INVARIANT_BASE_DENOM"]
expected_display = os.environ["WOLO_INVARIANT_DISPLAY_DENOM"]
expected_symbol = os.environ["WOLO_INVARIANT_SYMBOL"]
expected_decimals = int(os.environ["WOLO_INVARIANT_DECIMALS"])
expected_total_supply = int(os.environ["WOLO_INVARIANT_TOTAL_SUPPLY"])

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

crisis_denom = app.get("crisis", {}).get("constant_fee", {}).get("denom")
if crisis_denom and crisis_denom != expected_base:
    errors.append(f"crisis constant fee denom={crisis_denom} expected {expected_base}")

gov_params = app.get("gov", {}).get("params", {})
for key in ("min_deposit", "expedited_min_deposit"):
    for coin in gov_params.get(key, []):
        if isinstance(coin, dict) and coin.get("denom") != expected_base:
            errors.append(f"{key} denom={coin.get('denom')} expected {expected_base}")

total_supply = sum(
    int(coin["amount"])
    for coin in bank.get("supply", [])
    if coin.get("denom") == expected_base
)
if total_supply != expected_total_supply:
    errors.append(f"total {expected_base} supply={total_supply} expected {expected_total_supply}")

if not metadata:
    errors.append(f"bank denom metadata for {expected_base} is missing")
else:
    if metadata.get("display") != expected_display:
        errors.append(f'denom display={metadata.get("display")} expected {expected_display}')
    if metadata.get("base") != expected_base:
        errors.append(f'denom base={metadata.get("base")} expected {expected_base}')
    if metadata.get("name") != expected_symbol:
        errors.append(f'denom name={metadata.get("name")} expected {expected_symbol}')
    if metadata.get("symbol") != expected_symbol:
        errors.append(f'denom symbol={metadata.get("symbol")} expected {expected_symbol}')
    units = {
        unit.get("denom"): unit.get("exponent")
        for unit in metadata.get("denom_units", [])
        if isinstance(unit, dict)
    }
    if units.get(expected_base) != 0:
        errors.append(f"denom unit exponent for {expected_base}={units.get(expected_base)} expected 0")
    if units.get(expected_display) != expected_decimals:
        errors.append(
            f"denom unit exponent for {expected_display}={units.get(expected_display)} expected {expected_decimals}"
        )

print(json.dumps({
    "chain_id": payload.get("chain_id"),
    "bond_denom": staking_denom,
    "mint_denom": mint_denom,
    "crisis_constant_fee_denom": crisis_denom,
    "metadata_base": metadata.get("base") if metadata else None,
    "metadata_display": metadata.get("display") if metadata else None,
    "metadata_symbol": metadata.get("symbol") if metadata else None,
    "total_supply_uwolo": total_supply,
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
export WOLO_INVARIANT_CHAIN_ID="$EXPECTED_CHAIN_ID"
export WOLO_INVARIANT_PREFIX="$EXPECTED_PREFIX"
python3 - <<'PY'
import json
import os
import sys

payload = json.loads(os.environ["WOLO_DOCTOR_OUTPUT"])
expected_chain_id = os.environ["WOLO_INVARIANT_CHAIN_ID"]
expected_prefix = os.environ["WOLO_INVARIANT_PREFIX"]
errors = []

print(json.dumps(payload, indent=2))

if not payload.get("ok"):
    errors.append("settlement doctor reported ok=false")

configured_chain_id = payload.get("chain_id")
if configured_chain_id and configured_chain_id != expected_chain_id:
    errors.append(f"doctor chain_id={configured_chain_id} expected {expected_chain_id}")

runtime_chain_id = payload.get("runtime_chain_id") or configured_chain_id
if runtime_chain_id and runtime_chain_id != expected_chain_id:
    errors.append(f"runtime_chain_id={runtime_chain_id} expected {expected_chain_id}")

for key in ("payout_address", "escrow_address"):
    value = payload.get(key) or ""
    if value and not value.startswith(expected_prefix + "1"):
        errors.append(f"{key}={value} does not use the {expected_prefix} prefix")

if errors:
    print("\n".join(errors), file=sys.stderr)
    sys.exit(1)
PY

echo
echo "Chain invariants OK."
