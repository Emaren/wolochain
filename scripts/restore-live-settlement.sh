#!/usr/bin/env bash

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-${1:-}}"
SETTLEMENT_BIN_PATH="${SETTLEMENT_BIN_PATH:-/var/www/WoloChain/build/wolochaind}"
SETTLEMENT_ENV_PATH="${SETTLEMENT_ENV_PATH:-/etc/wolochain-settlement.env}"
SETTLEMENT_STATE_DIR="${WOLO_SETTLEMENT_STATE_DIR:-/mnt/HC_Volume_105319120/wolochain/settlement-state}"
SETTLEMENT_SERVICE_NAME="${SETTLEMENT_SERVICE_NAME:-wolochain-settlement.service}"
VERIFY_AFTER_RESTORE="${VERIFY_AFTER_RESTORE:-1}"
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -z "$BACKUP_DIR" ]]; then
  printf 'usage: BACKUP_DIR=/path/to/backup %s\n' "${BASH_SOURCE[0]}" >&2
  exit 2
fi
if [[ ! -d "$BACKUP_DIR" ]]; then
  printf 'backup dir not found: %s\n' "$BACKUP_DIR" >&2
  exit 2
fi
if [[ ! -f "$BACKUP_DIR/wolochaind" ]]; then
  printf 'backup is missing wolochaind: %s\n' "$BACKUP_DIR/wolochaind" >&2
  exit 2
fi
if [[ ! -f "$BACKUP_DIR/wolochain-settlement.env" ]]; then
  printf 'backup is missing env file: %s\n' "$BACKUP_DIR/wolochain-settlement.env" >&2
  exit 2
fi
if [[ ! -d "$BACKUP_DIR/settlement-state" ]]; then
  printf 'backup is missing settlement-state: %s\n' "$BACKUP_DIR/settlement-state" >&2
  exit 2
fi

printf 'Restoring settlement backup from %s\n' "$BACKUP_DIR"

sudo systemctl stop "$SETTLEMENT_SERVICE_NAME"
sudo install -o wolo -g wolo -m 0755 "$BACKUP_DIR/wolochaind" "$SETTLEMENT_BIN_PATH"
sudo install -o root -g root -m 0640 "$BACKUP_DIR/wolochain-settlement.env" "$SETTLEMENT_ENV_PATH"
sudo rm -rf "$SETTLEMENT_STATE_DIR"
sudo cp -a "$BACKUP_DIR/settlement-state" "$SETTLEMENT_STATE_DIR"
sudo systemctl start "$SETTLEMENT_SERVICE_NAME"

printf 'Restore completed. Service restarted: %s\n' "$SETTLEMENT_SERVICE_NAME"

if [[ "$VERIFY_AFTER_RESTORE" == "1" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$BACKUP_DIR/wolochain-settlement.env"
  set +a
  WOLOCHAIND_SUDO_USER="${WOLOCHAIND_SUDO_USER:-wolo}" \
    SETTLEMENT_ENV_FILE="$BACKUP_DIR/wolochain-settlement.env" \
    "$ROOT_DIR/scripts/check-settlement-cutover.sh"
fi
