#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_PATH="${1:-$ROOT_DIR/build/wolochaind}"

# Force sonic onto its compat path for linux/amd64 builds.
# The native loader path currently trips a linker/runtime symbol mismatch.
GOOS=linux GOARCH=amd64 go build -tags go1.27 -o "$OUT_PATH" "$ROOT_DIR/cmd/wolochaind"

