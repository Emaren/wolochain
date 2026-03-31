#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BIN="$ROOT/build/wolochaind"
HOME_DIR="${WOLO_HOME:-$HOME/.wolochain}"
NODE="${WOLO_NODE:-tcp://127.0.0.1:26657}"

if [[ ! -x "$BIN" ]]; then
  echo "Missing binary at $BIN"
  exit 1
fi

echo "=== node status ==="
curl -s http://127.0.0.1:26657/status | python3 -m json.tool | sed -n '1,80p'
echo

echo "=== total supply ==="
"$BIN" query bank total --node "$NODE" --output json
echo

echo "=== key balances ==="
for name in foundercold founderoperating faucetgrowth validatorops; do
  addr="$("$BIN" keys show "$name" --address --keyring-backend test --home "$HOME_DIR")"
  echo "--- $name ($addr) ---"
  "$BIN" query bank balances "$addr" --node "$NODE" --output json
  echo
done