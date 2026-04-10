#!/usr/bin/env bash

set -euo pipefail

have() {
  command -v "$1" >/dev/null 2>&1
}

fail() {
  printf '%s\n' "$1" >&2
  exit 2
}

user_home() {
  if have getent; then
    getent passwd "$(id -un)" | cut -d: -f6
    return
  fi
  printf '%s\n' "${HOME:-/tmp}"
}

preferred_go_root() {
  local shared_root="/mnt/HC_Volume_105319120/wolochain/go"
  if [[ -d "$(dirname "$shared_root")" ]]; then
    printf '%s\n' "$shared_root"
    return
  fi
  printf '%s/go\n' "${current_home%/}"
}

safe_cache_path() {
  local path="$1"
  case "$path" in
    */wolochain/go-cache|*/wolochain/go-tmp|*/go/pkg/mod|*/go/pkg/sumdb)
      return 0
      ;;
  esac
  return 1
}

dir_size() {
  local path="$1"
  if [[ -d "$path" ]]; then
    du -sh "$path" 2>/dev/null | awk '{print $1}'
    return
  fi
  printf 'missing\n'
}

clear_dir_contents() {
  local label="$1"
  local path="$2"

  if [[ ! -d "$path" ]]; then
    printf 'SKIP: %s dir does not exist: %s\n' "$label" "$path"
    return 0
  fi
  if [[ "${WOLO_BUILD_CLEAN_ALLOW_ANY_PATH:-0}" != "1" ]] && ! safe_cache_path "$path"; then
    fail "refusing to clear unexpected path for $label: $path"
  fi

  printf 'Clearing %s: %s (before=%s)\n' "$label" "$path" "$(dir_size "$path")"
  find "$path" -mindepth 1 -maxdepth 1 -exec chmod -R u+w -- {} + 2>/dev/null || true
  find "$path" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
  printf 'Cleared %s: %s (after=%s)\n' "$label" "$path" "$(dir_size "$path")"
}

current_home="$(user_home)"
current_gopath="${GOPATH:-${WOLO_BUILD_GOPATH_DIR:-$(preferred_go_root)}}"
WOLO_BUILD_GOCACHE_DIR="${GOCACHE:-${WOLO_BUILD_GOCACHE_DIR:-/mnt/HC_Volume_105319120/wolochain/go-cache}}"
WOLO_BUILD_TMP_DIR="${GOTMPDIR:-${WOLO_BUILD_TMP_DIR:-/mnt/HC_Volume_105319120/wolochain/go-tmp}}"
WOLO_BUILD_GOMODCACHE_DIR="${GOMODCACHE:-${WOLO_BUILD_GOMODCACHE_DIR:-${current_gopath%/}/pkg/mod}}"
WOLO_BUILD_SUMDBCACHE_DIR="${WOLO_BUILD_SUMDBCACHE_DIR:-${current_gopath%/}/pkg/sumdb}"

printf 'Cleaning WoloChain build caches for user %s\n' "$(id -un)"
printf '  GOPATH=%s\n' "$current_gopath"
printf '  GOCACHE=%s\n' "$WOLO_BUILD_GOCACHE_DIR"
printf '  GOTMPDIR=%s\n' "$WOLO_BUILD_TMP_DIR"
printf '  GOMODCACHE=%s\n' "$WOLO_BUILD_GOMODCACHE_DIR"
printf '  GOSUMDBCACHE=%s\n' "$WOLO_BUILD_SUMDBCACHE_DIR"

clear_dir_contents "GOCACHE" "$WOLO_BUILD_GOCACHE_DIR"
clear_dir_contents "GOTMPDIR" "$WOLO_BUILD_TMP_DIR"
clear_dir_contents "GOMODCACHE" "$WOLO_BUILD_GOMODCACHE_DIR"
clear_dir_contents "GOSUMDBCACHE" "$WOLO_BUILD_SUMDBCACHE_DIR"
