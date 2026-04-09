#!/usr/bin/env bash

set -euo pipefail

SETTLEMENT_BASE_URL="${SETTLEMENT_BASE_URL:-http://127.0.0.1:8091}"
WOLOCHAIND_BIN="${WOLOCHAIND_BIN:-./build/wolochaind}"
WOLOCHAIND_SUDO_USER="${WOLOCHAIND_SUDO_USER:-}"
WOLO_SETTLEMENT_HOME="${WOLO_SETTLEMENT_HOME:-/var/lib/wolochaind-testnet}"
WOLO_SETTLEMENT_STATE_DIR="${WOLO_SETTLEMENT_STATE_DIR:-/mnt/HC_Volume_105319120/wolochain/settlement-state}"
WOLO_SETTLEMENT_KEYRING_BACKEND="${WOLO_SETTLEMENT_KEYRING_BACKEND:-test}"
WOLO_SETTLEMENT_CHAIN_ID="${WOLO_SETTLEMENT_CHAIN_ID:-wolo-testnet}"
WOLO_SETTLEMENT_BASE_DENOM="${WOLO_SETTLEMENT_BASE_DENOM:-uwolo}"
WOLO_SETTLEMENT_DISPLAY_DENOM="${WOLO_SETTLEMENT_DISPLAY_DENOM:-wolo}"
WOLO_SETTLEMENT_ADDRESS_PREFIX="${WOLO_SETTLEMENT_ADDRESS_PREFIX:-wolo}"
VERIFY_REQUEST_ID="${VERIFY_REQUEST_ID:-verify-live-auth-check}"
VERIFY_RUN_ID="${VERIFY_RUN_ID:-verify-live-run-check}"
VERIFY_ESCROW_TX_HASH="${VERIFY_ESCROW_TX_HASH:-}"
VERIFY_ESCROW_EXPECTED_SENDER="${VERIFY_ESCROW_EXPECTED_SENDER:-}"
VERIFY_ESCROW_EXPECTED_AMOUNT_UWOLO="${VERIFY_ESCROW_EXPECTED_AMOUNT_UWOLO:-}"

failures=0
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

have() {
  command -v "$1" >/dev/null 2>&1
}

note() {
  printf '\n## %s\n' "$1"
}

record_failure() {
  printf 'FAIL: %s\n' "$1" >&2
  failures=$((failures + 1))
}

record_ok() {
  printf 'OK: %s\n' "$1"
}

curl_json() {
  local method="$1"
  local url="$2"
  local body_path="$3"
  shift 3

  curl -sS -X "$method" -o "$body_path" -w '%{http_code}' "$url" "$@"
}

looks_like_json_response() {
  local body_path="$1"
  grep -qE '"(ok|detail|failure_code|count|lookup|deposits)"' "$body_path"
}

settlement_env() {
  if [ -n "$WOLOCHAIND_SUDO_USER" ]; then
    sudo -u "$WOLOCHAIND_SUDO_USER" env \
      WOLO_SETTLEMENT_HOME="$WOLO_SETTLEMENT_HOME" \
      WOLO_SETTLEMENT_STATE_DIR="$WOLO_SETTLEMENT_STATE_DIR" \
      WOLO_SETTLEMENT_KEYRING_BACKEND="$WOLO_SETTLEMENT_KEYRING_BACKEND" \
      WOLO_SETTLEMENT_CHAIN_ID="$WOLO_SETTLEMENT_CHAIN_ID" \
      WOLO_SETTLEMENT_BASE_DENOM="$WOLO_SETTLEMENT_BASE_DENOM" \
      WOLO_SETTLEMENT_DISPLAY_DENOM="$WOLO_SETTLEMENT_DISPLAY_DENOM" \
      WOLO_SETTLEMENT_ADDRESS_PREFIX="$WOLO_SETTLEMENT_ADDRESS_PREFIX" \
      "$WOLOCHAIND_BIN" "$@"
    return
  fi

  env \
    WOLO_SETTLEMENT_HOME="$WOLO_SETTLEMENT_HOME" \
    WOLO_SETTLEMENT_STATE_DIR="$WOLO_SETTLEMENT_STATE_DIR" \
    WOLO_SETTLEMENT_KEYRING_BACKEND="$WOLO_SETTLEMENT_KEYRING_BACKEND" \
    WOLO_SETTLEMENT_CHAIN_ID="$WOLO_SETTLEMENT_CHAIN_ID" \
    WOLO_SETTLEMENT_BASE_DENOM="$WOLO_SETTLEMENT_BASE_DENOM" \
    WOLO_SETTLEMENT_DISPLAY_DENOM="$WOLO_SETTLEMENT_DISPLAY_DENOM" \
    WOLO_SETTLEMENT_ADDRESS_PREFIX="$WOLO_SETTLEMENT_ADDRESS_PREFIX" \
    "$WOLOCHAIND_BIN" "$@"
}

if ! have curl; then
  printf 'curl is required\n' >&2
  exit 2
fi
if [ ! -x "$WOLOCHAIND_BIN" ]; then
  printf 'missing executable settlement binary: %s\n' "$WOLOCHAIND_BIN" >&2
  exit 2
fi

note "Service Status"
if have systemctl; then
  systemctl is-active wolochaind-testnet.service wolochain-settlement.service || true
else
  printf 'systemctl not available; skipping service status check\n'
fi

note "Health"
health_body="$tmpdir/health.json"
health_code="$(curl_json GET "$SETTLEMENT_BASE_URL/settlement/v1/health" "$health_body")"
cat "$health_body"
printf '\n'
if [ "$health_code" != "200" ]; then
  record_failure "health endpoint returned HTTP $health_code"
else
  record_ok "health endpoint returned HTTP 200"
fi

payout_address="$(sed -n 's/.*"payout_address":[[:space:]]*"\([^"]*\)".*/\1/p' "$health_body" | head -n 1)"
escrow_address="$(sed -n 's/.*"escrow_address":[[:space:]]*"\([^"]*\)".*/\1/p' "$health_body" | head -n 1)"
auth_token_set="$(sed -n 's/.*"auth_token_set":[[:space:]]*\(true\|false\).*/\1/p' "$health_body" | head -n 1)"
if [ -z "$payout_address" ]; then
  payout_address="wolo1jx4n3n2ey6uzfq28kplkmpd2am98xsmcn0nerx"
fi
if [ -z "$escrow_address" ]; then
  printf 'Escrow address is not configured on the target service.\n'
else
  printf 'Escrow address: %s\n' "$escrow_address"
fi

note "Auth Check"
auth_body="$tmpdir/auth.json"
auth_code="$(curl_json POST "$SETTLEMENT_BASE_URL/settlement/v1/payouts" "$auth_body" \
  -H 'content-type: application/json' \
  --data '{"request_id":"'"$VERIFY_REQUEST_ID"'","to_address":"wolo1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqe36l7r","amount_uwolo":"1","memo":"verify auth"}')"
printf 'HTTP %s\n' "$auth_code"
cat "$auth_body"
printf '\n'
case "$auth_token_set" in
  true)
    if [ "$auth_code" = "401" ]; then
      record_ok "missing bearer token was rejected"
    else
      record_failure "expected HTTP 401 without bearer token, got $auth_code"
    fi
    ;;
  false|"")
    if [ "$auth_code" = "401" ]; then
      record_failure "service reports auth disabled but payout POST returned HTTP 401"
    else
      record_ok "auth token is not set on the target service"
    fi
    ;;
esac

note "Grouped Dry-Run Route"
run_body="$tmpdir/run.json"
cat >"$run_body" <<EOF
{
  "settlement_run_id": "$VERIFY_RUN_ID",
  "source_app": "verify-live-settlement",
  "source_event_id": "verify-$(date -u +%Y%m%dT%H%M%SZ)",
  "note": "dry-run only",
  "memo": "dry-run verify",
  "payouts": [
    {
      "to_address": "$payout_address",
      "amount_uwolo": "1"
    }
  ]
}
EOF

run_check_body="$tmpdir/run-check.json"
run_check_code="$(curl_json POST "$SETTLEMENT_BASE_URL/settlement/v1/runs/validate" "$run_check_body" \
  -H 'content-type: application/json' \
  --data @"$run_body")"
printf 'HTTP %s\n' "$run_check_code"
cat "$run_check_body"
printf '\n'
if [ "$run_check_code" = "404" ]; then
  record_failure "grouped dry-run route is not deployed on this service"
elif [ "$run_check_code" = "401" ]; then
  record_ok "grouped dry-run route exists and is auth-protected"
elif [ "$run_check_code" = "200" ] || [ "$run_check_code" = "400" ] || [ "$run_check_code" = "409" ]; then
  record_ok "grouped dry-run route responded with a structured application status"
else
  record_failure "unexpected grouped dry-run HTTP status $run_check_code"
fi

if [ "${auth_token_set:-false}" = "true" ] && [ -n "${WOLO_SETTLEMENT_AUTH_TOKEN:-}" ] && [ "$run_check_code" != "404" ]; then
  note "Authorized Grouped Dry-Run"
  run_auth_body="$tmpdir/run-auth.json"
  run_auth_code="$(curl_json POST "$SETTLEMENT_BASE_URL/settlement/v1/runs/validate" "$run_auth_body" \
    -H 'content-type: application/json' \
    -H "authorization: Bearer $WOLO_SETTLEMENT_AUTH_TOKEN" \
    --data @"$run_body")"
  printf 'HTTP %s\n' "$run_auth_code"
  cat "$run_auth_body"
  printf '\n'
  if [ "$run_auth_code" = "200" ] || [ "$run_auth_code" = "409" ]; then
    record_ok "authorized grouped dry-run completed"
  else
    record_failure "authorized grouped dry-run returned HTTP $run_auth_code"
  fi
else
  printf 'Skipping authorized grouped dry-run because the token is not available in this shell or the route is not deployed.\n'
fi

note "Escrow Read-Only Routes"
escrow_recent_body="$tmpdir/escrow-recent.json"
escrow_recent_code="$(curl_json GET "$SETTLEMENT_BASE_URL/settlement/v1/escrow/deposits?limit=1" "$escrow_recent_body")"
printf 'HTTP %s\n' "$escrow_recent_code"
cat "$escrow_recent_body"
printf '\n'
if [ "$escrow_recent_code" = "404" ]; then
  record_failure "escrow recent route is not deployed on this service"
elif looks_like_json_response "$escrow_recent_body"; then
  record_ok "escrow recent route responded with a structured application status"
else
  record_failure "escrow recent route did not return the expected JSON surface"
fi

escrow_probe_body="$tmpdir/escrow-probe.json"
escrow_probe_code="$(curl_json GET "$SETTLEMENT_BASE_URL/settlement/v1/escrow/txs/not-a-real-hash" "$escrow_probe_body")"
printf 'HTTP %s\n' "$escrow_probe_code"
cat "$escrow_probe_body"
printf '\n'
if [ "$escrow_probe_code" = "400" ] && looks_like_json_response "$escrow_probe_body"; then
  record_ok "escrow verify route is deployed and validates tx hash format"
else
  record_failure "escrow verify route did not return the expected structured invalid-tx response"
fi

if [ -n "$VERIFY_ESCROW_TX_HASH" ]; then
  note "Escrow Deposit Verify"
  escrow_verify_url="$SETTLEMENT_BASE_URL/settlement/v1/escrow/txs/$VERIFY_ESCROW_TX_HASH"
  if [ -n "$VERIFY_ESCROW_EXPECTED_SENDER" ] || [ -n "$VERIFY_ESCROW_EXPECTED_AMOUNT_UWOLO" ]; then
    escrow_verify_url="$escrow_verify_url?"
    if [ -n "$VERIFY_ESCROW_EXPECTED_SENDER" ]; then
      escrow_verify_url="${escrow_verify_url}expected_sender=$VERIFY_ESCROW_EXPECTED_SENDER"
    fi
    if [ -n "$VERIFY_ESCROW_EXPECTED_AMOUNT_UWOLO" ]; then
      if [ "$escrow_verify_url" != "${escrow_verify_url%\?}" ] && [ "${escrow_verify_url: -1}" != "?" ]; then
        escrow_verify_url="${escrow_verify_url}&"
      fi
      escrow_verify_url="${escrow_verify_url}expected_amount_uwolo=$VERIFY_ESCROW_EXPECTED_AMOUNT_UWOLO"
    fi
  fi

  escrow_verify_body="$tmpdir/escrow-verify.json"
  escrow_verify_code="$(curl_json GET "$escrow_verify_url" "$escrow_verify_body")"
  printf 'HTTP %s\n' "$escrow_verify_code"
  cat "$escrow_verify_body"
  printf '\n'
  if looks_like_json_response "$escrow_verify_body"; then
    record_ok "escrow verify request returned a structured application status"
  else
    record_failure "escrow verify request did not return the expected JSON surface"
  fi
else
  printf 'Skipping live escrow deposit verification because VERIFY_ESCROW_TX_HASH is not set.\n'
fi

note "CLI Surface"
cli_help="$tmpdir/settlement-help.txt"
settlement_env settlement --help >"$cli_help" 2>&1 || true
cat "$cli_help"
printf '\n'

if grep -qE '(^|[[:space:]])inspect([[:space:]]|$)' "$cli_help" && grep -qE '(^|[[:space:]])recent([[:space:]]|$)' "$cli_help"; then
  record_ok "request-level inspect/recent commands are available"

  note "Request Recent Summary"
  settlement_env settlement recent --summary-only || record_failure "request-level recent summary failed"

  note "Missing Request Inspect"
  settlement_env settlement inspect --request-id verify-live-missing --summary-only || record_failure "request-level inspect failed"
else
  record_failure "request-level inspect/recent commands are not deployed in the current binary"
fi

if grep -qE '(^|[[:space:]])run([[:space:]]|$)' "$cli_help"; then
  record_ok "grouped run commands are available"

  note "Run Recent Summary"
  settlement_env settlement run recent --summary-only || record_failure "grouped run recent summary failed"

  note "Missing Run Inspect"
  settlement_env settlement run inspect --run-id verify-live-missing --summary-only || record_failure "grouped run inspect failed"
else
  record_failure "grouped run commands are not deployed in the current binary"
fi

if grep -qE '(^|[[:space:]])escrow([[:space:]]|$)' "$cli_help"; then
  record_ok "escrow verification commands are available"
else
  record_failure "escrow verification commands are not deployed in the current binary"
fi

note "Summary"
if [ "$failures" -eq 0 ]; then
  printf 'All settlement rollout checks passed.\n'
else
  printf 'Settlement rollout checks finished with %d failure(s).\n' "$failures"
fi

exit "$failures"
