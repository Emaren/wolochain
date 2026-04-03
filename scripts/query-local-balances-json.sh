#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BIN="$ROOT/build/wolochaind"
HOME_DIR="${WOLO_HOME:-$HOME/.wolochain}"
NODE="${WOLO_NODE:-tcp://127.0.0.1:26657}"
RPC_HTTP="${WOLO_RPC_HTTP:-http://127.0.0.1:26657}"

if [[ ! -x "$BIN" ]]; then
  echo "Missing binary: $BIN" >&2
  exit 1
fi

if ! curl -fsS "$RPC_HTTP/status" >/dev/null 2>&1; then
  echo "WoloChain RPC is not reachable at $RPC_HTTP" >&2
  echo "Start the chain first with: ./scripts/start-local.sh" >&2
  exit 1
fi

export WOLO_BIN="$BIN"
export WOLO_HOME_DIR="$HOME_DIR"
export WOLO_NODE_ADDR="$NODE"
export WOLO_RPC_HTTP="$RPC_HTTP"
export WOLO_CHAIN_ID_FALLBACK="${WOLO_CHAIN_ID:-wolo-testnet}"

python3 - <<'PY'
import json
import os
import subprocess
import urllib.request

bin_path = os.environ["WOLO_BIN"]
home_dir = os.environ["WOLO_HOME_DIR"]
node = os.environ["WOLO_NODE_ADDR"]
rpc_http = os.environ["WOLO_RPC_HTTP"].rstrip("/")
chain_id_fallback = os.environ["WOLO_CHAIN_ID_FALLBACK"]

names = [
    "foundercold",
    "founderoperating",
    "communitytreasury",
    "dexliquidity",
    "faucetgrowth",
    "validatorops",
    "ecosystembounties",
]

def detect_chain_id() -> str:
    try:
        with urllib.request.urlopen(f"{rpc_http}/status", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return (
            payload.get("result", {})
            .get("node_info", {})
            .get("network")
            or chain_id_fallback
        )
    except Exception:
        return chain_id_fallback

out = {
    "chain_id": detect_chain_id(),
    "denom": {"base": "uwolo", "display": "wolo", "decimals": 6},
    "accounts": {},
}

for name in names:
    addr = subprocess.check_output(
        [bin_path, "keys", "show", name, "--address", "--keyring-backend", "test", "--home", home_dir],
        text=True,
    ).strip()

    balances_raw = subprocess.check_output(
        [bin_path, "query", "bank", "balances", addr, "--node", node, "--output", "json"],
        text=True,
    )
    balances = json.loads(balances_raw)

    uwolo = 0
    for coin in balances.get("balances", []):
        if coin.get("denom") == "uwolo":
            uwolo = int(coin["amount"])

    out["accounts"][name] = {
        "address": addr,
        "uwolo": uwolo,
        "wolo": uwolo / 1_000_000,
    }

print(json.dumps(out, indent=2))
PY