#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "=== stop existing local node ==="
pkill -f 'wolochaind start' || true

echo
echo "=== bootstrap local chain ==="
./scripts/bootstrap-local.sh

echo
echo "=== start local chain ==="
WOLO_START_BACKGROUND=1 \
WOLO_WAIT_READY=1 \
./scripts/start-local.sh

echo
echo "=== local health ==="
./scripts/check-local.sh
