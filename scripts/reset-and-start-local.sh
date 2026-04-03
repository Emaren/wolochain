#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

pkill -f 'wolochaind start' || true

./scripts/bootstrap-local.sh

WOLO_START_BACKGROUND=1 \
WOLO_WAIT_READY=1 \
./scripts/start-local.sh