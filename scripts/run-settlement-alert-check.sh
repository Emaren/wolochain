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

ALERT_OUTPUT_PATH="${SETTLEMENT_ALERT_OUTPUT_PATH:-$(user_home)/wolochain-settlement-alerts/latest.json}"
alert_output_dir="$(dirname "$ALERT_OUTPUT_PATH")"
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
tmp_output="$tmpdir/settlement-alerts.json"

mkdir -p "$alert_output_dir"

status=0
if "$ROOT_DIR/scripts/check-settlement-alerts.sh" >"$tmp_output"; then
  status=0
else
  status=$?
fi

if [[ ! -s "$tmp_output" ]]; then
  cat >"$tmp_output" <<EOF
{
  "ok": false,
  "status": "script_error",
  "timestamp_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "exit_code": $status,
  "detail": "check-settlement-alerts.sh exited before producing JSON"
}
EOF
fi

mv "$tmp_output" "$ALERT_OUTPUT_PATH"

printf 'ALERT_JSON=%s\n' "$ALERT_OUTPUT_PATH"
printf 'ALERT_EXIT_CODE=%s\n' "$status"

exit "$status"
