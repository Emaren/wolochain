#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mkdir -p build
./scripts/query-local-balances-json.sh > build/local-balances.json

echo "Wrote: $ROOT/build/local-balances.json"
cat build/local-balances.json