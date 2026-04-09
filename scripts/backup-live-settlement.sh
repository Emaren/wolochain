#!/usr/bin/env bash

set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-/mnt/HC_Volume_105319120/wolochain/settlement-backups}"
SETTLEMENT_STATE_DIR="${WOLO_SETTLEMENT_STATE_DIR:-/mnt/HC_Volume_105319120/wolochain/settlement-state}"
SETTLEMENT_ENV_PATH="${SETTLEMENT_ENV_PATH:-/etc/wolochain-settlement.env}"
SETTLEMENT_BIN_PATH="${SETTLEMENT_BIN_PATH:-/var/www/WoloChain/build/wolochaind}"
SETTLEMENT_SERVICE_NAME="${SETTLEMENT_SERVICE_NAME:-wolochain-settlement.service}"
SETTLEMENT_BASE_URL="${SETTLEMENT_BASE_URL:-http://127.0.0.1:8091}"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="${BACKUP_ROOT%/}/$timestamp"
user_name="$(id -un)"
group_name="$(id -gn)"

if ! command -v sudo >/dev/null 2>&1; then
  printf 'sudo is required for live settlement backups\n' >&2
  exit 2
fi

sudo install -d -o "$user_name" -g "$group_name" -m 0755 "$BACKUP_ROOT"
sudo install -d -o "$user_name" -g "$group_name" -m 0755 "$backup_dir"
sudo install -o "$user_name" -g "$group_name" -m 0755 "$SETTLEMENT_BIN_PATH" "$backup_dir/wolochaind"
sudo install -o "$user_name" -g "$group_name" -m 0640 "$SETTLEMENT_ENV_PATH" "$backup_dir/wolochain-settlement.env"
sudo cp -a "$SETTLEMENT_STATE_DIR" "$backup_dir/settlement-state"

if command -v systemctl >/dev/null 2>&1; then
  sudo systemctl cat "$SETTLEMENT_SERVICE_NAME" >"$backup_dir/${SETTLEMENT_SERVICE_NAME}.unit.txt" || true
  sudo systemctl status "$SETTLEMENT_SERVICE_NAME" --no-pager >"$backup_dir/${SETTLEMENT_SERVICE_NAME}.status.txt" || true
fi

curl -sS "$SETTLEMENT_BASE_URL/settlement/v1/health" >"$backup_dir/health.json" || true

(
  cd "$backup_dir"
  sha256sum wolochaind wolochain-settlement.env >SHA256SUMS
) || true

cat >"$backup_dir/metadata.json" <<EOF
{
  "timestamp_utc": "$timestamp",
  "backup_dir": "$backup_dir",
  "service_name": "$SETTLEMENT_SERVICE_NAME",
  "binary_path": "$SETTLEMENT_BIN_PATH",
  "env_path": "$SETTLEMENT_ENV_PATH",
  "state_dir": "$SETTLEMENT_STATE_DIR",
  "health_url": "$SETTLEMENT_BASE_URL/settlement/v1/health"
}
EOF

printf 'BACKUP_DIR=%s\n' "$backup_dir"
printf 'METADATA=%s\n' "$backup_dir/metadata.json"

printf 'Created settlement rollback backup: %s\n' "$backup_dir"
printf '\nRollback commands if the new service comes up wrong:\n'
printf '  sudo systemctl stop %s\n' "$SETTLEMENT_SERVICE_NAME"
printf '  sudo install -o wolo -g wolo -m 0755 %s %s\n' "$backup_dir/wolochaind" "$SETTLEMENT_BIN_PATH"
printf '  sudo install -o root -g root -m 0640 %s %s\n' "$backup_dir/wolochain-settlement.env" "$SETTLEMENT_ENV_PATH"
printf '  sudo rm -rf %s\n' "$SETTLEMENT_STATE_DIR"
printf '  sudo cp -a %s %s\n' "$backup_dir/settlement-state" "$SETTLEMENT_STATE_DIR"
printf '  sudo systemctl start %s\n' "$SETTLEMENT_SERVICE_NAME"
