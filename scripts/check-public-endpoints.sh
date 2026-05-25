#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CURRENT_RPC_URL="${WOLO_PUBLIC_RPC_URL:-https://aoe2war.com/rpc}"
CURRENT_REST_URL="${WOLO_PUBLIC_REST_URL:-https://aoe2war.com/rest}"
CURRENT_EXPLORER_URL="${WOLO_PUBLIC_EXPLORER_URL:-https://aoe2war.com/wolo-testnet}"
CURL_TIMEOUT="${WOLO_PUBLIC_ENDPOINT_TIMEOUT_SEC:-10}"

EXPECTED_CHAIN_ID="wolo-testnet"
EXPECTED_BASE_DENOM="uwolo"
EXPECTED_DISPLAY_DENOM="wolo"
EXPECTED_SYMBOL="WOLO"
EXPECTED_DECIMALS="6"
EXPECTED_SUPPLY_UWOLO="100000000000000"

failures=0

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  failures=$((failures + 1))
}

ok() {
  printf 'OK: %s\n' "$*"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    fail "missing required command: $1"
    return 1
  fi
}

json_field() {
  local expr="$1"
  python3 -c '
import json
import sys

expr = sys.argv[1]
payload = json.load(sys.stdin)
value = payload
for part in expr.split("."):
    if part == "":
        continue
    if isinstance(value, dict):
        value = value.get(part)
    else:
        value = None
        break
if value is None:
    print("")
else:
    print(value)
' "$expr"
}

check_equal() {
  local label="$1"
  local actual="$2"
  local expected="$3"
  if [[ "$actual" == "$expected" ]]; then
    ok "$label is $expected"
  else
    fail "$label is $actual, expected $expected"
  fi
}

fetch_json() {
  local url="$1"
  curl -fsS --max-time "$CURL_TIMEOUT" "$url"
}

require_cmd curl
require_cmd git
require_cmd python3
require_cmd rg

printf 'Current public RPC: %s/\n' "${CURRENT_RPC_URL%/}"
printf 'Current public REST: %s/\n' "${CURRENT_REST_URL%/}"
printf 'Current explorer route: %s\n' "$CURRENT_EXPLORER_URL"

if rpc_status="$(fetch_json "${CURRENT_RPC_URL%/}/status" 2>/tmp/wolo-public-rpc.err)"; then
  rpc_chain_id="$(printf '%s' "$rpc_status" | json_field "result.node_info.network")"
  check_equal "public RPC chain_id" "$rpc_chain_id" "$EXPECTED_CHAIN_ID"
else
  fail "public RPC status is unreachable at ${CURRENT_RPC_URL%/}/status: $(cat /tmp/wolo-public-rpc.err 2>/dev/null || true)"
fi

if rest_node_info="$(fetch_json "${CURRENT_REST_URL%/}/cosmos/base/tendermint/v1beta1/node_info" 2>/tmp/wolo-public-rest-node.err)"; then
  rest_chain_id="$(printf '%s' "$rest_node_info" | json_field "default_node_info.network")"
  check_equal "public REST chain_id" "$rest_chain_id" "$EXPECTED_CHAIN_ID"
else
  fail "public REST node_info is unreachable: $(cat /tmp/wolo-public-rest-node.err 2>/dev/null || true)"
fi

if supply="$(fetch_json "${CURRENT_REST_URL%/}/cosmos/bank/v1beta1/supply/by_denom?denom=${EXPECTED_BASE_DENOM}" 2>/tmp/wolo-public-supply.err)"; then
  supply_denom="$(printf '%s' "$supply" | json_field "amount.denom")"
  supply_amount="$(printf '%s' "$supply" | json_field "amount.amount")"
  check_equal "public REST supply denom" "$supply_denom" "$EXPECTED_BASE_DENOM"
  check_equal "public REST supply amount" "$supply_amount" "$EXPECTED_SUPPLY_UWOLO"
else
  fail "public REST supply endpoint is unreachable: $(cat /tmp/wolo-public-supply.err 2>/dev/null || true)"
fi

if metadata="$(fetch_json "${CURRENT_REST_URL%/}/cosmos/bank/v1beta1/denoms_metadata/${EXPECTED_BASE_DENOM}" 2>/tmp/wolo-public-metadata.err)"; then
  metadata_base="$(printf '%s' "$metadata" | json_field "metadata.base")"
  metadata_display="$(printf '%s' "$metadata" | json_field "metadata.display")"
  metadata_symbol="$(printf '%s' "$metadata" | json_field "metadata.symbol")"
  metadata_decimals="$(printf '%s' "$metadata" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
units = payload.get("metadata", {}).get("denom_units", [])
for unit in units:
    if unit.get("denom") == "wolo":
        print(unit.get("exponent", ""))
        break
else:
    print("")
'
)"
  check_equal "denom metadata base" "$metadata_base" "$EXPECTED_BASE_DENOM"
  check_equal "denom metadata display" "$metadata_display" "$EXPECTED_DISPLAY_DENOM"
  check_equal "denom metadata symbol" "$metadata_symbol" "$EXPECTED_SYMBOL"
  check_equal "denom metadata decimals" "$metadata_decimals" "$EXPECTED_DECIMALS"
else
  fail "public REST denom metadata endpoint is unreachable: $(cat /tmp/wolo-public-metadata.err 2>/dev/null || true)"
fi

if curl -fsSI --max-time "$CURL_TIMEOUT" "$CURRENT_EXPLORER_URL" >/dev/null 2>/tmp/wolo-public-explorer.err; then
  ok "explorer route responds at $CURRENT_EXPLORER_URL"
else
  fail "explorer route is unreachable at $CURRENT_EXPLORER_URL: $(cat /tmp/wolo-public-explorer.err 2>/dev/null || true)"
fi

legacy_domain="aoe2hdbets"
legacy_domain="${legacy_domain}.com"
stale_hosts=(
  "rpc.$legacy_domain"
  "rest.$legacy_domain"
  "explorer.testnet.$legacy_domain"
)

mapfile -t tracked_files < <(git ls-files -- README.md docs scripts cmd app config.yml Makefile go.mod proto)
scan_files=()
for path in "${tracked_files[@]}"; do
  if [[ "$path" != "scripts/check-public-endpoints.sh" ]]; then
    scan_files+=("$path")
  fi
done

if (( ${#scan_files[@]} > 0 )); then
  for host in "${stale_hosts[@]}"; do
    hits="$(rg -n --fixed-strings "$host" "${scan_files[@]}" || true)"
    if [[ -n "$hits" ]]; then
      printf '%s\n' "$hits" >&2
      fail "stale public Wolo endpoint host remains in tracked WoloChain files: $host"
    else
      ok "no tracked WoloChain references to stale host $host"
    fi
  done
fi

rm -f /tmp/wolo-public-rpc.err /tmp/wolo-public-rest-node.err /tmp/wolo-public-supply.err /tmp/wolo-public-metadata.err /tmp/wolo-public-explorer.err

if (( failures > 0 )); then
  exit 1
fi

printf '\nPublic endpoint checks OK.\n'
