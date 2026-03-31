#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BIN="$ROOT/build/wolochaind"
HOME_DIR="${WOLO_HOME:-$HOME/.wolochain}"

if [[ ! -x "$BIN" ]]; then
  mkdir -p "$ROOT/build"
  go build -o "$BIN" ./cmd/wolochaind
fi

exec "$BIN" start \
  --home "$HOME_DIR" \
  --minimum-gas-prices 0uwolo