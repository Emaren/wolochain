#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BIN="$ROOT/build/wolochaind"
HOME_DIR="${WOLO_HOME:-$HOME/.wolochain}"
CHAIN_ID="${WOLO_CHAIN_ID:-wolo-testnet}"
MONIKER="${WOLO_MONIKER:-local}"
ENV_FILE="${WOLO_LOCAL_ENV_FILE:-$ROOT/scripts/local-dev.env}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

required_vars=(
  WOLO_MNEMONIC_FOUNDERCOLD
  WOLO_MNEMONIC_FOUNDEROPERATING
  WOLO_MNEMONIC_COMMUNITYTREASURY
  WOLO_MNEMONIC_DEXLIQUIDITY
  WOLO_MNEMONIC_FAUCETGROWTH
  WOLO_MNEMONIC_VALIDATOROPS
  WOLO_MNEMONIC_ECOSYSTEMBOUNTIES
)

missing=()
for var in "${required_vars[@]}"; do
  if [[ -z "${!var:-}" ]]; then
    missing+=("$var")
  fi
done

if (( ${#missing[@]} > 0 )); then
  echo "Missing deterministic mnemonic env vars:"
  printf '  - %s\n' "${missing[@]}"
  echo
  echo "Create $ROOT/scripts/local-dev.env from scripts/local-dev.env.example and fill it in."
  exit 1
fi

build_binary() {
  mkdir -p "$ROOT/build"
  go build -o "$BIN" ./cmd/wolochaind
}

patch_app_toml() {
  python3 - <<'PY'
from pathlib import Path
import re

p = Path.home() / ".wolochain/config/app.toml"
s = p.read_text()

if 'minimum-gas-prices = ""' in s:
    s = s.replace('minimum-gas-prices = ""', 'minimum-gas-prices = "0uwolo"', 1)
else:
    s = re.sub(
        r'^minimum-gas-prices = ".*"$',
        'minimum-gas-prices = "0uwolo"',
        s,
        count=1,
        flags=re.MULTILINE,
    )

s = re.sub(
    r'(?ms)^\[api\]\n.*?(?=^\[|\Z)',
    '[api]\n'
    'enable = true\n'
    'swagger = false\n'
    'enabled-unsafe-cors = false\n'
    'address = "tcp://127.0.0.1:1317"\n'
    'max-open-connections = 1000\n'
    'rpc-read-timeout = 10\n'
    'rpc-write-timeout = 0\n'
    'rpc-max-body-bytes = 1000000\n\n',
    s,
    count=1,
)

p.write_text(s)
print(f"patched {p}")
PY
}

patch_genesis() {
  python3 - <<'PY'
import json
from pathlib import Path

p = Path.home() / ".wolochain/config/genesis.json"
g = json.loads(p.read_text())

g["chain_id"] = "wolo-testnet"
app = g["app_state"]

if "staking" in app and "params" in app["staking"]:
    app["staking"]["params"]["bond_denom"] = "uwolo"

if "mint" in app:
    params = app["mint"].setdefault("params", {})
    params["mint_denom"] = "uwolo"
    for k in ("inflation_rate_change", "inflation_max", "inflation_min"):
        if k in params:
            params[k] = "0.000000000000000000"
    minter = app["mint"].setdefault("minter", {})
    if "inflation" in minter:
        minter["inflation"] = "0.000000000000000000"
    if "annual_provisions" in minter:
        minter["annual_provisions"] = "0.000000000000000000"

if "crisis" in app and "constant_fee" in app["crisis"]:
    app["crisis"]["constant_fee"]["denom"] = "uwolo"

if "gov" in app and "params" in app["gov"]:
    gp = app["gov"]["params"]
    for key in ("min_deposit", "expedited_min_deposit"):
        if isinstance(gp.get(key), list):
            for coin in gp[key]:
                if isinstance(coin, dict) and "denom" in coin:
                    coin["denom"] = "uwolo"
    for key in (
        "burn_vote_quorum",
        "burn_proposal_deposit_prevote",
        "burn_vote_veto",
    ):
        if key in gp:
            gp[key] = False

bank = app.setdefault("bank", {})
bank["denom_metadata"] = [
    {
        "description": "WOLO is the fixed-supply native token of WoloChain.",
        "denom_units": [
            {"denom": "uwolo", "exponent": 0, "aliases": ["microWOLO"]},
            {"denom": "wolo", "exponent": 6},
        ],
        "base": "uwolo",
        "display": "wolo",
        "name": "WOLO",
        "symbol": "WOLO",
    }
]

p.write_text(json.dumps(g, indent=2) + "\n")
print(f"patched {p}")
PY
}

recover_key() {
  local name="$1"
  local mnemonic="$2"
  printf '%s\n\n' "$mnemonic" | "$BIN" keys add "$name" \
    --recover \
    --keyring-backend test \
    --home "$HOME_DIR" >/dev/null 2>&1
}

addr() {
  "$BIN" keys show "$1" --address --keyring-backend test --home "$HOME_DIR"
}

echo "=== build binary ==="
build_binary

echo
echo "=== reset local home ==="
rm -rf "$HOME_DIR"
"$BIN" init "$MONIKER" --chain-id "$CHAIN_ID" --home "$HOME_DIR" >/dev/null

VALIDATOR_DIR="$ROOT/scripts/local-validator"
mkdir -p "$VALIDATOR_DIR"

if [[ -f "$VALIDATOR_DIR/node_key.json" && -f "$VALIDATOR_DIR/priv_validator_key.json" ]]; then
  cp "$VALIDATOR_DIR/node_key.json" "$HOME_DIR/config/node_key.json"
  cp "$VALIDATOR_DIR/priv_validator_key.json" "$HOME_DIR/config/priv_validator_key.json"
  echo "restored canonical local validator identity"
fi

echo
echo "=== patch config ==="
patch_app_toml
patch_genesis

echo
echo "=== recover deterministic keys ==="
recover_key foundercold         "$WOLO_MNEMONIC_FOUNDERCOLD"
recover_key founderoperating    "$WOLO_MNEMONIC_FOUNDEROPERATING"
recover_key communitytreasury   "$WOLO_MNEMONIC_COMMUNITYTREASURY"
recover_key dexliquidity        "$WOLO_MNEMONIC_DEXLIQUIDITY"
recover_key faucetgrowth        "$WOLO_MNEMONIC_FAUCETGROWTH"
recover_key validatorops        "$WOLO_MNEMONIC_VALIDATOROPS"
recover_key ecosystembounties   "$WOLO_MNEMONIC_ECOSYSTEMBOUNTIES"

echo
echo "=== add genesis balances ==="
"$BIN" genesis add-genesis-account foundercold        60000000000000uwolo --keyring-backend test --home "$HOME_DIR"
"$BIN" genesis add-genesis-account founderoperating    5000000000000uwolo --keyring-backend test --home "$HOME_DIR"
"$BIN" genesis add-genesis-account communitytreasury  10000000000000uwolo --keyring-backend test --home "$HOME_DIR"
"$BIN" genesis add-genesis-account dexliquidity       10000000000000uwolo --keyring-backend test --home "$HOME_DIR"
"$BIN" genesis add-genesis-account faucetgrowth        7000000000000uwolo --keyring-backend test --home "$HOME_DIR"
"$BIN" genesis add-genesis-account validatorops        5000000000000uwolo --keyring-backend test --home "$HOME_DIR"
"$BIN" genesis add-genesis-account ecosystembounties   3000000000000uwolo --keyring-backend test --home "$HOME_DIR"

echo
echo "=== create gentx ==="
"$BIN" genesis gentx validatorops 1000000000uwolo \
  --chain-id "$CHAIN_ID" \
  --keyring-backend test \
  --home "$HOME_DIR"

echo
echo "=== collect + validate ==="
"$BIN" genesis collect-gentxs --home "$HOME_DIR"
"$BIN" genesis validate-genesis --home "$HOME_DIR"

echo
echo "=== write local addresses ==="
{
  echo "foundercold $(addr foundercold)"
  echo "founderoperating $(addr founderoperating)"
  echo "communitytreasury $(addr communitytreasury)"
  echo "dexliquidity $(addr dexliquidity)"
  echo "faucetgrowth $(addr faucetgrowth)"
  echo "validatorops $(addr validatorops)"
  echo "ecosystembounties $(addr ecosystembounties)"
} | tee "$ROOT/build/local-addresses.txt"

echo
echo "=== supply sanity check ==="
python3 - <<'PY'
import json
from pathlib import Path

p = Path.home() / ".wolochain/config/genesis.json"
g = json.loads(p.read_text())
bank = g["app_state"]["bank"]

balances = bank.get("balances", [])
supply = 0
for coin in bank.get("supply", []):
    if coin.get("denom") == "uwolo":
        supply += int(coin["amount"])

print("balance_count =", len(balances))
print("total_uwolo   =", supply)
print("total_wolo    =", supply / 1_000_000)
print("expected      =", 100_000_000_000_000)
print("match         =", supply == 100_000_000_000_000)
PY

echo
echo "Done."
echo "Home:   $HOME_DIR"
echo "Binary: $BIN"
echo "Addrs:  $ROOT/build/local-addresses.txt"
