#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

have() {
  command -v "$1" >/dev/null 2>&1
}

user_home() {
  if have getent; then
    getent passwd "$(id -un)" | cut -d: -f6
    return
  fi
  printf '%s\n' "${HOME:-/tmp}"
}

fail() {
  printf '%s\n' "$1" >&2
  exit 2
}

if ! have crontab; then
  fail 'crontab is required to install settlement alert monitoring'
fi

SETTLEMENT_ALERT_CRON_SCHEDULE="${SETTLEMENT_ALERT_CRON_SCHEDULE:-*/5 * * * *}"
SETTLEMENT_ALERT_OUTPUT_PATH="${SETTLEMENT_ALERT_OUTPUT_PATH:-$(user_home)/wolochain-settlement-alerts/latest.json}"
SETTLEMENT_ALERT_LOG_PATH="${SETTLEMENT_ALERT_LOG_PATH:-$(user_home)/wolochain-settlement-alerts/runner.log}"
cron_output_dir="$(dirname "$SETTLEMENT_ALERT_OUTPUT_PATH")"
cron_log_dir="$(dirname "$SETTLEMENT_ALERT_LOG_PATH")"

mkdir -p "$cron_output_dir" "$cron_log_dir"

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
current_cron="$tmpdir/current.cron"
new_cron="$tmpdir/new.cron"

crontab -l 2>/dev/null >"$current_cron" || true
awk '
  BEGIN {skip = 0}
  /^# BEGIN wolochain-settlement-alerts$/ {skip = 1; next}
  /^# END wolochain-settlement-alerts$/ {skip = 0; next}
  skip == 0 {print}
' "$current_cron" >"$new_cron"

cat >>"$new_cron" <<EOF
# BEGIN wolochain-settlement-alerts
$SETTLEMENT_ALERT_CRON_SCHEDULE cd $ROOT_DIR && SETTLEMENT_ALERT_OUTPUT_PATH=$SETTLEMENT_ALERT_OUTPUT_PATH /usr/bin/env bash ./scripts/run-settlement-alert-check.sh >> $SETTLEMENT_ALERT_LOG_PATH 2>&1
# END wolochain-settlement-alerts
EOF

crontab "$new_cron"

printf 'Installed settlement alert cron for user %s\n' "$(id -un)"
printf 'SCHEDULE=%s\n' "$SETTLEMENT_ALERT_CRON_SCHEDULE"
printf 'ALERT_JSON=%s\n' "$SETTLEMENT_ALERT_OUTPUT_PATH"
printf 'RUN_LOG=%s\n' "$SETTLEMENT_ALERT_LOG_PATH"
