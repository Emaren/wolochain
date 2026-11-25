#!/usr/bin/env bash

set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-/mnt/HC_Volume_105319120/wolochain-mainnet/settlement-backups}"
SETTLEMENT_STATE_DIR="${WOLO_SETTLEMENT_STATE_DIR:-/mnt/HC_Volume_105319120/wolochain-mainnet/settlement-state}"
SETTLEMENT_ENV_PATH="${SETTLEMENT_ENV_PATH:-/etc/wolochain-mainnet-settlement.env}"
SETTLEMENT_BIN_PATH="${SETTLEMENT_BIN_PATH:-/usr/local/bin/wolochaind-mainnet}"
NODE_SERVICE_NAME="${NODE_SERVICE_NAME:-wolochaind-mainnet.service}"
SETTLEMENT_SERVICE_NAME="${SETTLEMENT_SERVICE_NAME:-wolochain-mainnet-settlement.service}"
SETTLEMENT_BASE_URL="${SETTLEMENT_BASE_URL:-http://127.0.0.1:8092}"
BACKUP_FREE_HEADROOM_KB="${BACKUP_FREE_HEADROOM_KB:-262144}"
BACKUP_SKIP_SPACE_CHECK="${BACKUP_SKIP_SPACE_CHECK:-0}"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="${BACKUP_ROOT%/}/$timestamp"
user_name="$(id -un)"
group_name="$(id -gn)"
root_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

have() {
  command -v "$1" >/dev/null 2>&1
}

fail() {
  printf '%s\n' "$1" >&2
  exit 2
}

existing_df_target() {
  local path="$1"
  while [[ ! -e "$path" && "$path" != "/" ]]; do
    path="$(dirname "$path")"
  done
  printf '%s\n' "$path"
}

source_size_kb() {
  sudo du -sk "$SETTLEMENT_BIN_PATH" "$SETTLEMENT_ENV_PATH" "$SETTLEMENT_STATE_DIR" 2>/dev/null \
    | awk '{total += $1} END {print total + 0}'
}

if ! have sudo; then
  fail 'sudo is required for live settlement backups'
fi
if ! have df || ! have du; then
  fail 'df and du are required for live settlement backups'
fi

sudo test -x "$SETTLEMENT_BIN_PATH" || fail "settlement binary is missing or not executable: $SETTLEMENT_BIN_PATH"
sudo test -r "$SETTLEMENT_ENV_PATH" || fail "settlement env file is missing or not readable: $SETTLEMENT_ENV_PATH"
sudo test -d "$SETTLEMENT_STATE_DIR" || fail "settlement state dir is missing: $SETTLEMENT_STATE_DIR"

space_check_target="$(existing_df_target "$BACKUP_ROOT")"
available_kb="$(df -Pk "$space_check_target" | awk 'NR==2 {print $4}')"
required_kb="$(source_size_kb)"

if [[ -z "$available_kb" || -z "$required_kb" ]]; then
  fail "could not determine backup free space for $space_check_target"
fi

if [[ "$BACKUP_SKIP_SPACE_CHECK" != "1" ]]; then
  required_with_headroom_kb=$((required_kb + BACKUP_FREE_HEADROOM_KB))
  if (( available_kb < required_with_headroom_kb )); then
    fail "not enough free space under $space_check_target for settlement backup: need ${required_with_headroom_kb}KB (source ${required_kb}KB + headroom ${BACKUP_FREE_HEADROOM_KB}KB), have ${available_kb}KB. Use BACKUP_ROOT=/home/tony/wolochain-settlement-backups or set BACKUP_SKIP_SPACE_CHECK=1 if you have already validated disk pressure."
  fi
fi

sudo install -d -o "$user_name" -g "$group_name" -m 0755 "$BACKUP_ROOT"
sudo install -d -o "$user_name" -g "$group_name" -m 0755 "$backup_dir"
sudo install -o "$user_name" -g "$group_name" -m 0755 "$SETTLEMENT_BIN_PATH" "$backup_dir/wolochaind"
sudo install -o "$user_name" -g "$group_name" -m 0640 "$SETTLEMENT_ENV_PATH" "$backup_dir/wolochain-settlement.env"
sudo install -d -o "$user_name" -g "$group_name" -m 0755 "$backup_dir/settlement-state"
sudo cp -a "$SETTLEMENT_STATE_DIR"/. "$backup_dir/settlement-state/"

if have systemctl; then
  sudo systemctl cat "$NODE_SERVICE_NAME" >"$backup_dir/${NODE_SERVICE_NAME}.unit.txt" || true
  sudo systemctl status "$NODE_SERVICE_NAME" --no-pager >"$backup_dir/${NODE_SERVICE_NAME}.status.txt" || true
  sudo systemctl cat "$SETTLEMENT_SERVICE_NAME" >"$backup_dir/${SETTLEMENT_SERVICE_NAME}.unit.txt" || true
  sudo systemctl status "$SETTLEMENT_SERVICE_NAME" --no-pager >"$backup_dir/${SETTLEMENT_SERVICE_NAME}.status.txt" || true
fi

curl -sS "$SETTLEMENT_BASE_URL/settlement/v1/health" >"$backup_dir/health.json" 2>"$backup_dir/health.stderr" || true
df -Pk "$space_check_target" >"$backup_dir/df-before.txt"
du -sk "$backup_dir" >"$backup_dir/backup-size.txt" || true

repo_commit=""
if git -C "$root_dir" rev-parse --short HEAD >/dev/null 2>&1; then
  repo_commit="$(git -C "$root_dir" rev-parse --short HEAD)"
  git -C "$root_dir" status --short >"$backup_dir/repo-status.txt" || true
fi

if have sha256sum; then
  (
    cd "$backup_dir"
    sha256sum wolochaind wolochain-settlement.env >SHA256SUMS
  )
fi

cat >"$backup_dir/metadata.json" <<EOF
{
  "timestamp_utc": "$timestamp",
  "backup_dir": "$backup_dir",
  "node_service_name": "$NODE_SERVICE_NAME",
  "service_name": "$SETTLEMENT_SERVICE_NAME",
  "binary_path": "$SETTLEMENT_BIN_PATH",
  "env_path": "$SETTLEMENT_ENV_PATH",
  "state_dir": "$SETTLEMENT_STATE_DIR",
  "default_restore_mode": "shared-binary",
  "health_url": "$SETTLEMENT_BASE_URL/settlement/v1/health",
  "backup_root_space_check_path": "$space_check_target",
  "backup_root_available_kb_before": "$available_kb",
  "source_size_kb": "$required_kb",
  "free_headroom_kb": "$BACKUP_FREE_HEADROOM_KB",
  "repo_commit": "${repo_commit:-unknown}"
}
EOF

printf 'BACKUP_DIR=%s\n' "$backup_dir"
printf 'METADATA=%s\n' "$backup_dir/metadata.json"
printf 'SOURCE_SIZE_KB=%s\n' "$required_kb"
printf 'AVAILABLE_KB_BEFORE=%s\n' "$available_kb"

printf 'Created settlement rollback backup: %s\n' "$backup_dir"
printf '\nRollback commands if the new service comes up wrong:\n'
printf '  # Default shared-binary rollback: restart node + settlement\n'
printf '  BACKUP_DIR=%s ./scripts/restore-live-settlement.sh\n' "$backup_dir"
printf '  # Settlement-only rollback: restore env/state, leave shared node binary untouched\n'
printf '  RESTORE_MODE=settlement-only BACKUP_DIR=%s ./scripts/restore-live-settlement.sh\n' "$backup_dir"
