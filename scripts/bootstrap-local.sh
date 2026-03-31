#!/usr/bin/env bash
set -euo pipefail

CHAIN_HOME="${HOME}/.wolochain"
CHAIN_ID="wolo-1"
KEY_NAME="validator"
DENOM="uwolo"
SELF_DELEGATION="1000000000${DENOM}"
GENESIS_BALANCE="100000000000000${DENOM}"

cd "$(dirname "$0")/.."

echo "==> building binary"
mkdir -p build
go build -o ./build/wolochaind ./cmd/WoloChaind

echo "==> resetting local chain home"
rm -rf "${CHAIN_HOME}"

echo "==> init chain"
./build/wolochaind init local --chain-id "${CHAIN_ID}" --home "${CHAIN_HOME}"

echo "==> create validator key"
./build/wolochaind keys add "${KEY_NAME}" --keyring-backend test --home "${CHAIN_HOME}" >/dev/null 2>&1 || true

ADDR="$(./build/wolochaind keys show "${KEY_NAME}" -a --keyring-backend test --home "${CHAIN_HOME}")"
echo "validator address: ${ADDR}"

echo "==> add genesis account"
./build/wolochaind genesis add-genesis-account "${ADDR}" "${GENESIS_BALANCE}" --home "${CHAIN_HOME}" --keyring-backend test

echo "==> create gentx"
./build/wolochaind genesis gentx "${KEY_NAME}" "${SELF_DELEGATION}" \
  --from "${KEY_NAME}" \
  --chain-id "${CHAIN_ID}" \
  --home "${CHAIN_HOME}" \
  --keyring-backend test

GENTX="$(ls "${CHAIN_HOME}"/config/gentx/gentx-*.json | head -n1)"
echo "gentx: ${GENTX}"

echo "==> patch empty delegator_address if needed"
python3 - "$ADDR" "$GENTX" <<'PY'
import json, pathlib, sys

addr = sys.argv[1]
gentx = pathlib.Path(sys.argv[2])

data = json.loads(gentx.read_text())
msg = data["body"]["messages"][0]

if msg.get("delegator_address", "") != addr:
    msg["delegator_address"] = addr
    gentx.write_text(json.dumps(data, indent=2) + "\n")
    print(f"patched delegator_address -> {addr}")
else:
    print("delegator_address already correct")
PY

echo "==> re-sign gentx"
./build/wolochaind tx sign "$GENTX" \
  --from "${KEY_NAME}" \
  --chain-id "${CHAIN_ID}" \
  --home "${CHAIN_HOME}" \
  --keyring-backend test \
  --offline \
  --account-number 0 \
  --sequence 0 \
  --output-document "$GENTX" \
  --overwrite >/dev/null

echo "==> collect gentxs"
./build/wolochaind genesis collect-gentxs --home "${CHAIN_HOME}"

echo "==> zero mint inflation in genesis safely"
python3 - "${CHAIN_HOME}/config/genesis.json" <<'PY'
import json, pathlib, sys

genesis_path = pathlib.Path(sys.argv[1])
data = json.loads(genesis_path.read_text())

mint = data["app_state"]["mint"]
mint["minter"]["inflation"] = "0.000000000000000000"
mint["minter"]["annual_provisions"] = "0.000000000000000000"
mint["params"]["inflation_rate_change"] = "0.000000000000000000"
mint["params"]["inflation_max"] = "0.000000000000000000"
mint["params"]["inflation_min"] = "0.000000000000000000"
mint["params"]["goal_bonded"] = "0.670000000000000000"
mint["params"]["mint_denom"] = "uwolo"

staking = data["app_state"]["staking"]
staking["params"]["bond_denom"] = "uwolo"

gov = data["app_state"]["gov"]["params"]
for key in ("min_deposit", "expedited_min_deposit"):
    for coin in gov.get(key, []):
        coin["denom"] = "uwolo"

genesis_path.write_text(json.dumps(data, indent=2) + "\n")
print("patched genesis mint/staking/gov and zeroed inflation safely")
PY

echo "==> validate genesis"
./build/wolochaind genesis validate --home "${CHAIN_HOME}"

echo "==> recreate validator state file"
mkdir -p "${CHAIN_HOME}/data"
cat > "${CHAIN_HOME}/data/priv_validator_state.json" <<'EOF'
{"height":"0","round":0,"step":0}
EOF

echo "==> done"
echo
echo "Start with:"
echo "./build/wolochaind start --home ${CHAIN_HOME} --minimum-gas-prices 0${DENOM}"