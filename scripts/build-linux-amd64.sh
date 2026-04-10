#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_PATH="${1:-$ROOT_DIR/build/wolochaind}"
WOLO_BUILD_MIN_FREE_KB="${WOLO_BUILD_MIN_FREE_KB:-2621440}"
WOLO_BUILD_SHARED_GO_ROOT="${WOLO_BUILD_SHARED_GO_ROOT:-/mnt/HC_Volume_105319120/wolochain/go}"

if [[ -z "${GOPATH:-}" && -d "$(dirname "$WOLO_BUILD_SHARED_GO_ROOT")" ]]; then
  export GOPATH="$WOLO_BUILD_SHARED_GO_ROOT"
fi

WOLO_BUILD_GOMODCACHE_DIR="${GOMODCACHE:-${WOLO_BUILD_GOMODCACHE_DIR:-${GOPATH:-$HOME/go}/pkg/mod}}"
export GOMODCACHE="$WOLO_BUILD_GOMODCACHE_DIR"

existing_df_target() {
  local path="$1"
  while [[ ! -e "$path" && "$path" != "/" ]]; do
    path="$(dirname "$path")"
  done
  printf '%s\n' "$path"
}

usage_kb() {
  local path="$1"
  if [[ -n "$path" && -e "$path" ]]; then
    du -sk "$path" 2>/dev/null | awk '{print $1}'
    return
  fi
  printf '0\n'
}

ensure_dir() {
  local label="$1"
  local path="$2"
  mkdir -p "$path" 2>/dev/null || true
  if [[ -d "$path" && -w "$path" ]]; then
    return 0
  fi
  cat >&2 <<EOF
cannot prepare $label directory for linux/amd64 WoloChain builds:
  path=$path
  build_user=$(id -un)
  gopath=${GOPATH:-<unset>}

Create it as the build user or precreate it with sudo, for example:
  sudo install -d -o $(id -un) -g $(id -gn) -m 0755 "$path"
EOF
  exit 2
}

ensure_dir "Go module cache" "$GOMODCACHE"
if [[ -n "${GOCACHE:-}" ]]; then
  ensure_dir "Go build cache" "$GOCACHE"
fi
if [[ -n "${GOTMPDIR:-}" ]]; then
  ensure_dir "Go build temp" "$GOTMPDIR"
fi
ensure_dir "build output" "$(dirname "$OUT_PATH")"

if command -v df >/dev/null 2>&1; then
  build_space_path="${GOTMPDIR:-${GOCACHE:-$OUT_PATH}}"
  build_space_target="$(existing_df_target "$build_space_path")"
  available_kb="$(df -Pk "$build_space_target" | awk 'NR==2 {print $4}')"
  if [[ -n "${available_kb:-}" ]] && (( available_kb < WOLO_BUILD_MIN_FREE_KB )); then
    cache_usage_kb="$(usage_kb "${GOCACHE:-}")"
    modcache_usage_kb="$(usage_kb "$WOLO_BUILD_GOMODCACHE_DIR")"
    cat >&2 <<EOF
not enough free space on build volume $build_space_target for linux/amd64 WoloChain builds:
  available_kb=$available_kb
  required_min_kb=$WOLO_BUILD_MIN_FREE_KB
  gopath=${GOPATH:-<unset>}
  gotmpdir=${GOTMPDIR:-<unset>}
  gocache=${GOCACHE:-<unset>}
  gocache_usage_kb=$cache_usage_kb
  gomodcache=$WOLO_BUILD_GOMODCACHE_DIR
  gomodcache_usage_kb=$modcache_usage_kb

Clear Go build/module cache or point GOTMPDIR/GOCACHE at a roomier path, then rerun.
Preferred cleanup helper:
  ./scripts/clean-build-cache.sh
If the VPS still fails after cleanup, build the linux/amd64 binary on a roomier host and only install it on the VPS.
EOF
    exit 2
  fi
fi

# Force sonic onto its compat path for linux/amd64 builds.
# The native loader path currently trips a linker/runtime symbol mismatch.
GOOS=linux GOARCH=amd64 go build -tags go1.27 -o "$OUT_PATH" "$ROOT_DIR/cmd/wolochaind"
