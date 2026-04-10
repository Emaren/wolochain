#!/usr/bin/env bash

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-${1:-}}"
SETTLEMENT_BIN_PATH="${SETTLEMENT_BIN_PATH:-/var/www/WoloChain/build/wolochaind}"
SETTLEMENT_ENV_PATH="${SETTLEMENT_ENV_PATH:-/etc/wolochain-settlement.env}"
SETTLEMENT_STATE_DIR="${WOLO_SETTLEMENT_STATE_DIR:-/mnt/HC_Volume_105319120/wolochain/settlement-state}"
NODE_SERVICE_NAME="${NODE_SERVICE_NAME:-wolochaind-testnet.service}"
SETTLEMENT_SERVICE_NAME="${SETTLEMENT_SERVICE_NAME:-wolochain-settlement.service}"
RESTORE_MODE="${RESTORE_MODE:-shared-binary}"
VERIFY_AFTER_RESTORE="${VERIFY_AFTER_RESTORE:-1}"
RESTORE_FREE_HEADROOM_KB="${RESTORE_FREE_HEADROOM_KB:-131072}"
RESTORE_SKIP_SPACE_CHECK="${RESTORE_SKIP_SPACE_CHECK:-0}"
RESTORE_READY_TIMEOUT_SEC="${RESTORE_READY_TIMEOUT_SEC:-60}"
RESTORE_READY_INTERVAL_SEC="${RESTORE_READY_INTERVAL_SEC:-1}"
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
tmp_state_dir=""

have() {
  command -v "$1" >/dev/null 2>&1
}

fail() {
  printf '%s\n' "$1" >&2
  exit 2
}

cleanup() {
  if [[ -n "$tmp_state_dir" ]]; then
    sudo rm -rf "$tmp_state_dir" 2>/dev/null || true
  fi
}

existing_df_target() {
  local path="$1"
  while [[ ! -e "$path" && "$path" != "/" ]]; do
    path="$(dirname "$path")"
  done
  printf '%s\n' "$path"
}

require_active_service() {
  local service_name="$1"
  sudo systemctl is-active --quiet "$service_name" || fail "service did not become active after restore: $service_name"
}

wait_for_http_ready() {
  local url="$1"
  local label="$2"
  local deadline=$((SECONDS + RESTORE_READY_TIMEOUT_SEC))
  local waited=0

  while true; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    if (( SECONDS >= deadline )); then
      return 1
    fi
    if (( waited == 0 )); then
      printf 'Waiting up to %ss for %s at %s\n' "$RESTORE_READY_TIMEOUT_SEC" "$label" "$url"
      waited=1
    fi
    sleep "$RESTORE_READY_INTERVAL_SEC"
  done
}

trap cleanup EXIT

if [[ -z "$BACKUP_DIR" ]]; then
  fail "usage: BACKUP_DIR=/path/to/backup $0"
fi
if [[ ! -d "$BACKUP_DIR" ]]; then
  fail "backup dir not found: $BACKUP_DIR"
fi
if [[ ! -f "$BACKUP_DIR/wolochaind" ]]; then
  fail "backup is missing wolochaind: $BACKUP_DIR/wolochaind"
fi
if [[ ! -f "$BACKUP_DIR/wolochain-settlement.env" ]]; then
  fail "backup is missing env file: $BACKUP_DIR/wolochain-settlement.env"
fi
if [[ ! -d "$BACKUP_DIR/settlement-state" ]]; then
  fail "backup is missing settlement-state: $BACKUP_DIR/settlement-state"
fi
if ! have sudo; then
  fail 'sudo is required for live settlement restores'
fi
if ! have systemctl; then
  fail 'systemctl is required for live settlement restores'
fi
if ! have df || ! have du; then
  fail 'df and du are required for live settlement restores'
fi
case "$RESTORE_MODE" in
  shared-binary|settlement-only)
    ;;
  *)
    fail "RESTORE_MODE must be one of: shared-binary, settlement-only"
    ;;
esac

if [[ -f "$BACKUP_DIR/SHA256SUMS" ]] && have sha256sum; then
  (
    cd "$BACKUP_DIR"
    sha256sum -c SHA256SUMS >/dev/null
  ) || fail "backup checksum verification failed in $BACKUP_DIR"
fi

restore_state_size_kb="$(du -sk "$BACKUP_DIR/settlement-state" | awk '{print $1}')"
restore_space_target="$(existing_df_target "$(dirname "$SETTLEMENT_STATE_DIR")")"
restore_available_kb="$(df -Pk "$restore_space_target" | awk 'NR==2 {print $4}')"
if [[ -z "$restore_state_size_kb" || -z "$restore_available_kb" ]]; then
  fail "could not determine restore free space for $restore_space_target"
fi
if [[ "$RESTORE_SKIP_SPACE_CHECK" != "1" ]]; then
  restore_required_kb=$((restore_state_size_kb + RESTORE_FREE_HEADROOM_KB))
  if (( restore_available_kb < restore_required_kb )); then
    fail "not enough free space under $restore_space_target for restore staging: need ${restore_required_kb}KB (state ${restore_state_size_kb}KB + headroom ${RESTORE_FREE_HEADROOM_KB}KB), have ${restore_available_kb}KB. Clear space or set RESTORE_SKIP_SPACE_CHECK=1 if you have already validated disk pressure."
  fi
fi

printf 'Restoring settlement backup from %s\n' "$BACKUP_DIR"
if [[ -f "$BACKUP_DIR/metadata.json" ]]; then
  printf 'Backup metadata:\n'
  sed -n '1,160p' "$BACKUP_DIR/metadata.json"
  printf '\n'
fi
printf 'Restore mode: %s\n' "$RESTORE_MODE"
if [[ "$RESTORE_MODE" == "shared-binary" ]]; then
  printf 'Binary restore target: %s (shared by %s and %s)\n' "$SETTLEMENT_BIN_PATH" "$NODE_SERVICE_NAME" "$SETTLEMENT_SERVICE_NAME"
else
  printf 'Binary restore target: skipped; leaving shared node binary untouched\n'
fi
printf '\n'

tmp_state_dir="${SETTLEMENT_STATE_DIR%/}.restore-$$"
sudo rm -rf "$tmp_state_dir"
sudo cp -a "$BACKUP_DIR/settlement-state" "$tmp_state_dir"

sudo systemctl stop "$SETTLEMENT_SERVICE_NAME"
if [[ "$RESTORE_MODE" == "shared-binary" ]]; then
  sudo systemctl stop "$NODE_SERVICE_NAME"
  sudo install -o wolo -g wolo -m 0755 "$BACKUP_DIR/wolochaind" "$SETTLEMENT_BIN_PATH"
fi
sudo install -o root -g root -m 0640 "$BACKUP_DIR/wolochain-settlement.env" "$SETTLEMENT_ENV_PATH"
sudo rm -rf "$SETTLEMENT_STATE_DIR"
sudo mv "$tmp_state_dir" "$SETTLEMENT_STATE_DIR"
tmp_state_dir=""
if [[ "$RESTORE_MODE" == "shared-binary" ]]; then
  sudo systemctl start "$NODE_SERVICE_NAME"
  require_active_service "$NODE_SERVICE_NAME"
fi
sudo systemctl start "$SETTLEMENT_SERVICE_NAME"
require_active_service "$SETTLEMENT_SERVICE_NAME"

if [[ "$RESTORE_MODE" == "shared-binary" ]]; then
  printf 'Restore completed. Restarted services: %s, %s\n' "$NODE_SERVICE_NAME" "$SETTLEMENT_SERVICE_NAME"
else
  printf 'Restore completed. Restarted service: %s\n' "$SETTLEMENT_SERVICE_NAME"
fi

if [[ "$VERIFY_AFTER_RESTORE" == "1" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$BACKUP_DIR/wolochain-settlement.env"
  set +a
  if [[ "$RESTORE_MODE" == "shared-binary" ]]; then
    require_active_service "$NODE_SERVICE_NAME"
  fi
  require_active_service "$SETTLEMENT_SERVICE_NAME"
  if [[ "$RESTORE_MODE" == "shared-binary" ]] && have curl && [[ -n "${WOLO_SETTLEMENT_REST_URL:-}" ]]; then
    if wait_for_http_ready "$WOLO_SETTLEMENT_REST_URL/cosmos/base/tendermint/v1beta1/node_info" "node REST"; then
      printf 'Node REST became ready: %s\n' "$WOLO_SETTLEMENT_REST_URL"
    else
      fail "node REST did not become ready within ${RESTORE_READY_TIMEOUT_SEC}s: ${WOLO_SETTLEMENT_REST_URL}/cosmos/base/tendermint/v1beta1/node_info"
    fi
  fi
  WOLOCHAIND_SUDO_USER="${WOLOCHAIND_SUDO_USER:-wolo}" \
    SETTLEMENT_ENV_FILE="$BACKUP_DIR/wolochain-settlement.env" \
    VERIFY_WAIT_FOR_READY=1 \
    "$ROOT_DIR/scripts/check-settlement-cutover.sh"
fi
