#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

EXPECTED_CHAIN_ID="wolo-1"
EXPECTED_SUPPLY_UWOLO="100000000000000"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

ok() {
  echo "OK: $*"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    fail "Missing required command: $1"
  fi
}

require_file() {
  local path="$1"
  [[ -f "$path" ]] || fail "Missing required file: $path"
}

require_fixed() {
  local needle="$1"
  local path="$2"
  local label="$3"
  if rg -q --fixed-strings "$needle" "$path"; then
    ok "$label"
  else
    fail "$label"
  fi
}

require_absent_regex() {
  local pattern="$1"
  shift
  local args=("$@")
  local last_index=$((${#args[@]} - 1))
  local label="${args[$last_index]}"
  unset "args[$last_index]"
  local hits
  hits="$(rg -n -e "$pattern" "${args[@]}" || true)"
  if [[ -n "$hits" ]]; then
    printf '%s\n' "$hits" >&2
    fail "$label"
  fi
  ok "$label"
}

require_cmd python3
require_cmd rg

require_file mainnet-prep/config/wolo-1-values.env.example
require_file mainnet-prep/config/wolo-1-node.env.example
require_file mainnet-prep/config/wolo-1-settlement.env.example
require_file mainnet-prep/genesis/allocation-template.csv
require_file mainnet-prep/systemd/wolochaind-mainnet.service.example
require_file mainnet-prep/systemd/wolochain-mainnet-settlement.service.example
require_file scripts/render-mainnet-allocation.sh
require_file scripts/check-mainnet-genesis-readiness.sh

require_fixed "WOLO_MAINNET_CHAIN_ID=$EXPECTED_CHAIN_ID" mainnet-prep/config/wolo-1-values.env.example "mainnet values define wolo-1"
require_fixed "WOLO_MAINNET_TOTAL_SUPPLY_UWOLO=$EXPECTED_SUPPLY_UWOLO" mainnet-prep/config/wolo-1-values.env.example "mainnet values define fixed supply"
require_fixed "CHAIN_ID=$EXPECTED_CHAIN_ID" mainnet-prep/config/wolo-1-node.env.example "node env uses wolo-1"
require_fixed "WOLO_HOME=/var/lib/wolochaind-mainnet" mainnet-prep/config/wolo-1-node.env.example "node env uses mainnet home"
require_fixed "WOLO_SETTLEMENT_CHAIN_ID=$EXPECTED_CHAIN_ID" mainnet-prep/config/wolo-1-settlement.env.example "settlement env uses wolo-1"
require_fixed "WOLO_SETTLEMENT_STATE_DIR=/mnt/HC_Volume_105319120/wolochain-mainnet/settlement-state" mainnet-prep/config/wolo-1-settlement.env.example "settlement env uses mainnet state dir"
require_fixed "ExecStart=/usr/local/bin/wolochaind-mainnet start" mainnet-prep/systemd/wolochaind-mainnet.service.example "node service uses verified mainnet binary path"
require_fixed "Requires=wolochaind-mainnet.service" mainnet-prep/systemd/wolochain-mainnet-settlement.service.example "settlement service depends on mainnet node"

require_absent_regex '/var/lib/wolochaind-testnet|wolochaind-testnet[.]service|wolochain-settlement[.]service|127[.]0[.]0[.]1:26657|127[.]0[.]0[.]1:1317|127[.]0[.]0[.]1:8091' mainnet-prep/config mainnet-prep/systemd "mainnet env/service templates do not point at live testnet homes/services/ports"
require_absent_regex 'rpc[.]aoe2hdbets[.]com|rest[.]aoe2hdbets[.]com|explorer[.]testnet[.]aoe2hdbets[.]com' mainnet-prep "mainnet prep templates do not contain stale old Wolo endpoints"
require_absent_regex 'mnemonic[[:space:]]*=|seed phrase[[:space:]]*=|private_key[[:space:]]*=|priv_validator_key[.]json' mainnet-prep "mainnet prep templates do not contain key material placeholders that look live"

./scripts/render-mainnet-allocation.sh --check
./scripts/check-mainnet-genesis-readiness.sh

echo
echo "Mainnet prep checks OK."
