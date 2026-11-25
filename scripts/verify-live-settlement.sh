#!/usr/bin/env bash

set -euo pipefail

SETTLEMENT_ENV_FILE="${SETTLEMENT_ENV_FILE:-}"
if [[ -z "$SETTLEMENT_ENV_FILE" ]] && command -v systemctl >/dev/null 2>&1; then
  SETTLEMENT_ENV_FILE="$(systemctl show -p EnvironmentFiles --value wolochain-mainnet-settlement.service 2>/dev/null | awk '{print $1}' | sed 's/^-//')"
fi
if [[ -n "$SETTLEMENT_ENV_FILE" && -r "$SETTLEMENT_ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$SETTLEMENT_ENV_FILE"
  set +a
fi

SETTLEMENT_BASE_URL="${SETTLEMENT_BASE_URL:-http://127.0.0.1:8092}"
WOLOCHAIND_BIN="${WOLOCHAIND_BIN:-./build/wolochaind}"
WOLOCHAIND_SUDO_USER="${WOLOCHAIND_SUDO_USER:-}"
WOLO_SETTLEMENT_HOME="${WOLO_SETTLEMENT_HOME:-/var/lib/wolochaind-mainnet}"
WOLO_SETTLEMENT_STATE_DIR="${WOLO_SETTLEMENT_STATE_DIR:-/mnt/HC_Volume_105319120/wolochain-mainnet/settlement-state}"
WOLO_SETTLEMENT_KEYRING_BACKEND="${WOLO_SETTLEMENT_KEYRING_BACKEND:-os}"
WOLO_SETTLEMENT_KEYRING_DIR="${WOLO_SETTLEMENT_KEYRING_DIR:-}"
WOLO_SETTLEMENT_KEYRING_PASSPHRASE_FILE="${WOLO_SETTLEMENT_KEYRING_PASSPHRASE_FILE:-}"
WOLO_SETTLEMENT_CHAIN_ID="${WOLO_SETTLEMENT_CHAIN_ID:-wolo-1}"
WOLO_SETTLEMENT_BASE_DENOM="${WOLO_SETTLEMENT_BASE_DENOM:-uwolo}"
WOLO_SETTLEMENT_DISPLAY_DENOM="${WOLO_SETTLEMENT_DISPLAY_DENOM:-wolo}"
WOLO_SETTLEMENT_ADDRESS_PREFIX="${WOLO_SETTLEMENT_ADDRESS_PREFIX:-wolo}"
WOLO_SETTLEMENT_PAYOUT_ADDRESS="${WOLO_SETTLEMENT_PAYOUT_ADDRESS:-}"
WOLO_SETTLEMENT_PAYOUT_KEY_NAME="${WOLO_SETTLEMENT_PAYOUT_KEY_NAME:-mainnet-payout}"
WOLO_SETTLEMENT_ESCROW_KEY_NAME="${WOLO_SETTLEMENT_ESCROW_KEY_NAME:-mainnet-escrow}"
WOLO_SETTLEMENT_ESCROW_ADDRESS="${WOLO_SETTLEMENT_ESCROW_ADDRESS:-}"
WOLO_SETTLEMENT_MIN_ESCROW_BALANCE_UWOLO="${WOLO_SETTLEMENT_MIN_ESCROW_BALANCE_UWOLO:-}"
WOLO_SETTLEMENT_ESCROW_FEE_HEADROOM_UWOLO="${WOLO_SETTLEMENT_ESCROW_FEE_HEADROOM_UWOLO:-}"
VERIFY_REQUEST_ID="${VERIFY_REQUEST_ID:-verify-live-auth-check}"
VERIFY_RUN_ID="${VERIFY_RUN_ID:-settlement-health-probe-verify}"
VERIFY_CHALLENGE_RUN_ID="${VERIFY_CHALLENGE_RUN_ID:-verify-live-challenge-check}"
VERIFY_WAIT_FOR_READY="${VERIFY_WAIT_FOR_READY:-1}"
VERIFY_READY_TIMEOUT_SEC="${VERIFY_READY_TIMEOUT_SEC:-60}"
VERIFY_READY_INTERVAL_SEC="${VERIFY_READY_INTERVAL_SEC:-1}"
VERIFY_VERBOSE="${VERIFY_VERBOSE:-0}"
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

http_request() {
  local method="$1"
  local url="$2"
  local body_path="$3"
  shift 3

  if code="$(curl -sS -X "$method" -o "$body_path" -w '%{http_code}' "$url" "$@" 2>"$body_path.stderr")"; then
    printf '%s' "$code"
    return 0
  fi

  printf '000'
  return 1
}

print_response() {
  local body_path="$1"
  local mode="${2:-default}"
  if [[ "$mode" != "always" && "$VERIFY_VERBOSE" != "1" ]]; then
    return
  fi
  cat "$body_path" 2>/dev/null || true
  if [[ -s "$body_path.stderr" ]]; then
    printf '\n[curl stderr]\n'
    cat "$body_path.stderr"
  fi
  printf '\n'
}

strip_known_noise_file() {
  local path="$1"
  sed -i.bak '/^WARNING: sonic\/ast only supports .*fallback to encoding\/json$/d' "$path" 2>/dev/null || true
  rm -f "$path.bak"
}

looks_like_json_response() {
  local body_path="$1"
  grep -qE '"(ok|detail|failure_code|count|lookup|deposits|status|summary)"' "$body_path" 2>/dev/null
}

extract_json_string() {
  local key="$1"
  local body_path="$2"
  sed -n 's/.*"'"$key"'":[[:space:]]*"\([^"]*\)".*/\1/p' "$body_path" | head -n 1
}

extract_json_bool() {
  local key="$1"
  local body_path="$2"
  if grep -q '"'"$key"'":[[:space:]]*true' "$body_path" 2>/dev/null; then
    printf 'true\n'
    return
  fi
  if grep -q '"'"$key"'":[[:space:]]*false' "$body_path" 2>/dev/null; then
    printf 'false\n'
  fi
}

settlement_env() {
  if [ -n "$WOLOCHAIND_SUDO_USER" ]; then
    sudo -u "$WOLOCHAIND_SUDO_USER" env \
      WOLO_SETTLEMENT_HOME="$WOLO_SETTLEMENT_HOME" \
      WOLO_SETTLEMENT_STATE_DIR="$WOLO_SETTLEMENT_STATE_DIR" \
      WOLO_SETTLEMENT_KEYRING_BACKEND="$WOLO_SETTLEMENT_KEYRING_BACKEND" \
      WOLO_SETTLEMENT_KEYRING_DIR="$WOLO_SETTLEMENT_KEYRING_DIR" \
      WOLO_SETTLEMENT_KEYRING_PASSPHRASE_FILE="$WOLO_SETTLEMENT_KEYRING_PASSPHRASE_FILE" \
      WOLO_SETTLEMENT_CHAIN_ID="$WOLO_SETTLEMENT_CHAIN_ID" \
      WOLO_SETTLEMENT_BASE_DENOM="$WOLO_SETTLEMENT_BASE_DENOM" \
      WOLO_SETTLEMENT_DISPLAY_DENOM="$WOLO_SETTLEMENT_DISPLAY_DENOM" \
      WOLO_SETTLEMENT_ADDRESS_PREFIX="$WOLO_SETTLEMENT_ADDRESS_PREFIX" \
      WOLO_SETTLEMENT_PAYOUT_KEY_NAME="$WOLO_SETTLEMENT_PAYOUT_KEY_NAME" \
      WOLO_SETTLEMENT_PAYOUT_ADDRESS="$WOLO_SETTLEMENT_PAYOUT_ADDRESS" \
      WOLO_SETTLEMENT_ESCROW_KEY_NAME="$WOLO_SETTLEMENT_ESCROW_KEY_NAME" \
      WOLO_SETTLEMENT_ESCROW_ADDRESS="$WOLO_SETTLEMENT_ESCROW_ADDRESS" \
      WOLO_SETTLEMENT_MIN_ESCROW_BALANCE_UWOLO="$WOLO_SETTLEMENT_MIN_ESCROW_BALANCE_UWOLO" \
      WOLO_SETTLEMENT_ESCROW_FEE_HEADROOM_UWOLO="$WOLO_SETTLEMENT_ESCROW_FEE_HEADROOM_UWOLO" \
      "$WOLOCHAIND_BIN" "$@"
    return
  fi

  env \
    WOLO_SETTLEMENT_HOME="$WOLO_SETTLEMENT_HOME" \
    WOLO_SETTLEMENT_STATE_DIR="$WOLO_SETTLEMENT_STATE_DIR" \
    WOLO_SETTLEMENT_KEYRING_BACKEND="$WOLO_SETTLEMENT_KEYRING_BACKEND" \
    WOLO_SETTLEMENT_KEYRING_DIR="$WOLO_SETTLEMENT_KEYRING_DIR" \
    WOLO_SETTLEMENT_KEYRING_PASSPHRASE_FILE="$WOLO_SETTLEMENT_KEYRING_PASSPHRASE_FILE" \
    WOLO_SETTLEMENT_CHAIN_ID="$WOLO_SETTLEMENT_CHAIN_ID" \
    WOLO_SETTLEMENT_BASE_DENOM="$WOLO_SETTLEMENT_BASE_DENOM" \
    WOLO_SETTLEMENT_DISPLAY_DENOM="$WOLO_SETTLEMENT_DISPLAY_DENOM" \
    WOLO_SETTLEMENT_ADDRESS_PREFIX="$WOLO_SETTLEMENT_ADDRESS_PREFIX" \
    WOLO_SETTLEMENT_PAYOUT_KEY_NAME="$WOLO_SETTLEMENT_PAYOUT_KEY_NAME" \
    WOLO_SETTLEMENT_PAYOUT_ADDRESS="$WOLO_SETTLEMENT_PAYOUT_ADDRESS" \
    WOLO_SETTLEMENT_ESCROW_KEY_NAME="$WOLO_SETTLEMENT_ESCROW_KEY_NAME" \
    WOLO_SETTLEMENT_ESCROW_ADDRESS="$WOLO_SETTLEMENT_ESCROW_ADDRESS" \
    WOLO_SETTLEMENT_MIN_ESCROW_BALANCE_UWOLO="$WOLO_SETTLEMENT_MIN_ESCROW_BALANCE_UWOLO" \
    WOLO_SETTLEMENT_ESCROW_FEE_HEADROOM_UWOLO="$WOLO_SETTLEMENT_ESCROW_FEE_HEADROOM_UWOLO" \
    "$WOLOCHAIND_BIN" "$@"
}

capture_settlement_cli() {
  local output_path="$1"
  shift

  local rc=0
  if settlement_env "$@" >"$output_path" 2>&1; then
    rc=0
  else
    rc=$?
  fi
  strip_known_noise_file "$output_path"
  return "$rc"
}

fetch_health() {
  health_body="$tmpdir/health.json"
  health_rc=0
  if health_code="$(http_request GET "$SETTLEMENT_BASE_URL/settlement/v1/health" "$health_body")"; then
    health_rc=0
  else
    health_rc=$?
  fi
  strip_known_noise_file "$health_body"
  strip_known_noise_file "$health_body.stderr"
}

health_is_ready() {
  [[ "${health_code:-000}" == "200" ]] && grep -q '"ok":[[:space:]]*true' "$health_body" 2>/dev/null
}

wait_for_health() {
  local deadline=$((SECONDS + VERIFY_READY_TIMEOUT_SEC))
  local waited=0

  while true; do
    fetch_health
    if health_is_ready; then
      return 0
    fi

    if [[ "$SECONDS" -ge "$deadline" ]]; then
      return 1
    fi

    if [[ "$waited" -eq 0 ]]; then
      printf 'Waiting up to %ss for settlement health at %s/settlement/v1/health\n' \
        "$VERIFY_READY_TIMEOUT_SEC" "$SETTLEMENT_BASE_URL"
      waited=1
    fi
    sleep "$VERIFY_READY_INTERVAL_SEC"
  done
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
  systemctl is-active wolochaind-mainnet.service wolochain-mainnet-settlement.service wolochain-settlement.service || true
else
  printf 'systemctl not available; skipping service status check\n'
fi

note "Health"
if [[ "$VERIFY_WAIT_FOR_READY" == "1" ]]; then
  if wait_for_health; then
    record_ok "settlement health became ready"
  else
    record_failure "settlement health did not become ready within ${VERIFY_READY_TIMEOUT_SEC}s"
  fi
else
  fetch_health
fi

printf 'HTTP %s\n' "${health_code:-000}"

if [ "${health_code:-000}" != "200" ]; then
  print_response "$health_body" always
  record_failure "health endpoint returned HTTP ${health_code:-000}"
elif health_is_ready; then
  print_response "$health_body"
  record_ok "health endpoint returned HTTP 200 with ok=true"
else
  print_response "$health_body" always
  record_failure "health endpoint returned HTTP 200 but ok=true was not present"
fi

payout_address="$(extract_json_string payout_address "$health_body")"
escrow_address="$(extract_json_string escrow_address "$health_body")"
auth_token_set="$(extract_json_bool auth_token_set "$health_body")"
if [ -z "$payout_address" ]; then
  payout_address="${WOLO_SETTLEMENT_PAYOUT_ADDRESS:-}"
fi
grouped_probe_ready=1
if [ -z "$payout_address" ]; then
  grouped_probe_ready=0
  record_failure "payout address is not configured on the target service or in WOLO_SETTLEMENT_PAYOUT_ADDRESS"
else
  printf 'Payout address: %s\n' "$payout_address"
fi
if [ -z "$escrow_address" ]; then
  printf 'Escrow address is not configured on the target service.\n'
else
  printf 'Escrow address: %s\n' "$escrow_address"
fi

note "Auth Check"
auth_body="$tmpdir/auth.json"
auth_code="000"
if ! auth_code="$(http_request POST "$SETTLEMENT_BASE_URL/settlement/v1/payouts" "$auth_body" \
  -H 'content-type: application/json' \
  --data '{"request_id":"'"$VERIFY_REQUEST_ID"'","to_address":"wolo1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqe36l7r","amount_uwolo":"1","memo":"verify auth"}')"; then
  :
fi
printf 'HTTP %s\n' "$auth_code"
case "$auth_token_set" in
  true)
    if [ "$auth_code" = "401" ]; then
      print_response "$auth_body"
      record_ok "missing bearer token was rejected"
    else
      print_response "$auth_body" always
      record_failure "expected HTTP 401 without bearer token, got $auth_code"
    fi
    ;;
  false|"")
    if [ "$auth_code" = "401" ]; then
      print_response "$auth_body" always
      record_failure "service reports auth disabled but payout POST returned HTTP 401"
    else
      print_response "$auth_body"
      record_ok "auth token is not set on the target service"
    fi
    ;;
esac

note "Grouped Dry-Run Route"
run_body="$tmpdir/run.json"
if [ "$grouped_probe_ready" = "1" ]; then
  cat >"$run_body" <<EOF
{
  "settlement_run_id": "$VERIFY_RUN_ID",
  "source_app": "settlement-health-probe",
  "source_event_id": "health-probe-verify-$(date -u +%Y%m%dT%H%M%SZ)",
  "note": "health probe only; dry-run route validation",
  "memo": "health_probe_verify",
  "payouts": [
    {
      "to_address": "$payout_address",
      "amount_uwolo": "1"
    }
  ]
}
EOF

  run_check_body="$tmpdir/run-check.json"
  run_check_code="000"
  if ! run_check_code="$(http_request POST "$SETTLEMENT_BASE_URL/settlement/v1/runs/validate" "$run_check_body" \
    -H 'content-type: application/json' \
    --data @"$run_body")"; then
    :
  fi
  printf 'HTTP %s\n' "$run_check_code"
else
  run_check_body="$tmpdir/run-check.json"
  run_check_code="000"
  : >"$run_check_body"
  printf 'Skipping grouped dry-run because no payout address is configured.\n'
fi

if [ "$grouped_probe_ready" != "1" ]; then
  :
elif [ "$run_check_code" = "404" ]; then
  print_response "$run_check_body" always
  record_failure "grouped dry-run route is not deployed on this service"
elif [ "$run_check_code" = "401" ]; then
  print_response "$run_check_body"
  record_ok "grouped dry-run route exists and is auth-protected"
elif [ "$run_check_code" = "200" ] || [ "$run_check_code" = "400" ] || [ "$run_check_code" = "409" ] || [ "$run_check_code" = "503" ]; then
  print_response "$run_check_body"
  record_ok "grouped dry-run route responded with a structured application status"
else
  print_response "$run_check_body" always
  record_failure "unexpected grouped dry-run HTTP status $run_check_code"
fi

if [ "$grouped_probe_ready" = "1" ] && [ "${auth_token_set:-false}" = "true" ] && [ -n "${WOLO_SETTLEMENT_AUTH_TOKEN:-}" ] && [ "$run_check_code" != "404" ]; then
  note "Authorized Grouped Dry-Run"
  run_auth_body="$tmpdir/run-auth.json"
  run_auth_code="000"
  if ! run_auth_code="$(http_request POST "$SETTLEMENT_BASE_URL/settlement/v1/runs/validate" "$run_auth_body" \
    -H 'content-type: application/json' \
    -H "authorization: Bearer $WOLO_SETTLEMENT_AUTH_TOKEN" \
    --data @"$run_body")"; then
    :
  fi
  printf 'HTTP %s\n' "$run_auth_code"
  if [ "$run_auth_code" = "200" ] || [ "$run_auth_code" = "409" ]; then
    print_response "$run_auth_body"
    record_ok "authorized grouped dry-run completed"
  else
    print_response "$run_auth_body" always
    record_failure "authorized grouped dry-run returned HTTP $run_auth_code"
  fi
else
  printf 'Skipping authorized grouped dry-run because the token is not available in this shell or the route is not deployed.\n'
fi

note "Challenge Dry-Run Route"
challenge_body="$tmpdir/challenge.json"
cat >"$challenge_body" <<EOF
{
  "settlement_run_id": "$VERIFY_CHALLENGE_RUN_ID",
  "source_app": "verify-live-settlement",
  "challenge_id": "verify-challenge",
  "note": "dry-run only",
  "memo": "challenge dry-run verify",
  "funding": [],
  "transfers": []
}
EOF

challenge_check_body="$tmpdir/challenge-check.json"
challenge_check_code="000"
if ! challenge_check_code="$(http_request POST "$SETTLEMENT_BASE_URL/settlement/v1/challenges/validate" "$challenge_check_body" \
  -H 'content-type: application/json' \
  --data @"$challenge_body")"; then
  :
fi
printf 'HTTP %s\n' "$challenge_check_code"

if [ "$challenge_check_code" = "404" ]; then
  print_response "$challenge_check_body" always
  record_failure "challenge dry-run route is not deployed on this service"
elif [ "$challenge_check_code" = "401" ]; then
  print_response "$challenge_check_body"
  record_ok "challenge dry-run route exists and is auth-protected"
elif [ "$challenge_check_code" = "200" ] || [ "$challenge_check_code" = "400" ] || [ "$challenge_check_code" = "409" ] || [ "$challenge_check_code" = "503" ]; then
  print_response "$challenge_check_body"
  record_ok "challenge dry-run route responded with a structured application status"
else
  print_response "$challenge_check_body" always
  record_failure "unexpected challenge dry-run HTTP status $challenge_check_code"
fi

if [ "${auth_token_set:-false}" = "true" ] && [ -n "${WOLO_SETTLEMENT_AUTH_TOKEN:-}" ] && [ "$challenge_check_code" != "404" ]; then
  note "Authorized Challenge Dry-Run"
  challenge_auth_body="$tmpdir/challenge-auth.json"
  challenge_auth_code="000"
  if ! challenge_auth_code="$(http_request POST "$SETTLEMENT_BASE_URL/settlement/v1/challenges/validate" "$challenge_auth_body" \
    -H 'content-type: application/json' \
    -H "authorization: Bearer $WOLO_SETTLEMENT_AUTH_TOKEN" \
    --data @"$challenge_body")"; then
    :
  fi
  printf 'HTTP %s\n' "$challenge_auth_code"
  if [ "$challenge_auth_code" = "200" ] || [ "$challenge_auth_code" = "400" ] || [ "$challenge_auth_code" = "409" ]; then
    print_response "$challenge_auth_body"
    record_ok "authorized challenge dry-run completed"
  else
    print_response "$challenge_auth_body" always
    record_failure "authorized challenge dry-run returned HTTP $challenge_auth_code"
  fi
else
  printf 'Skipping authorized challenge dry-run because the token is not available in this shell or the route is not deployed.\n'
fi

note "Escrow Read-Only Routes"
escrow_recent_body="$tmpdir/escrow-recent.json"
escrow_recent_code="000"
if ! escrow_recent_code="$(http_request GET "$SETTLEMENT_BASE_URL/settlement/v1/escrow/deposits?limit=1" "$escrow_recent_body")"; then
  :
fi
printf 'HTTP %s\n' "$escrow_recent_code"
if [ "$escrow_recent_code" = "404" ]; then
  print_response "$escrow_recent_body" always
  record_failure "escrow recent route is not deployed on this service"
elif looks_like_json_response "$escrow_recent_body"; then
  print_response "$escrow_recent_body"
  record_ok "escrow recent route responded with a structured application status"
else
  print_response "$escrow_recent_body" always
  record_failure "escrow recent route did not return the expected JSON surface"
fi

escrow_probe_body="$tmpdir/escrow-probe.json"
escrow_probe_code="000"
if ! escrow_probe_code="$(http_request GET "$SETTLEMENT_BASE_URL/settlement/v1/escrow/txs/not-a-real-hash" "$escrow_probe_body")"; then
  :
fi
printf 'HTTP %s\n' "$escrow_probe_code"
if { [ "$escrow_probe_code" = "400" ] || [ "$escrow_probe_code" = "503" ]; } && looks_like_json_response "$escrow_probe_body"; then
  print_response "$escrow_probe_body"
  record_ok "escrow verify route is deployed and validates tx hash format"
else
  print_response "$escrow_probe_body" always
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
  escrow_verify_code="000"
  if ! escrow_verify_code="$(http_request GET "$escrow_verify_url" "$escrow_verify_body")"; then
    :
  fi
  printf 'HTTP %s\n' "$escrow_verify_code"
  if looks_like_json_response "$escrow_verify_body"; then
    print_response "$escrow_verify_body"
    record_ok "escrow verify request returned a structured application status"
  else
    print_response "$escrow_verify_body" always
    record_failure "escrow verify request did not return the expected JSON surface"
  fi
else
  printf 'Skipping live escrow deposit verification because VERIFY_ESCROW_TX_HASH is not set.\n'
fi

note "Challenge Read-Only Routes"
challenge_recent_body="$tmpdir/challenge-recent.json"
challenge_recent_code="000"
if ! challenge_recent_code="$(http_request GET "$SETTLEMENT_BASE_URL/settlement/v1/challenges?limit=1&summary_only=1" "$challenge_recent_body")"; then
  :
fi
printf 'HTTP %s\n' "$challenge_recent_code"
if [ "$challenge_recent_code" = "404" ]; then
  print_response "$challenge_recent_body" always
  record_failure "challenge recent route is not deployed on this service"
elif looks_like_json_response "$challenge_recent_body"; then
  print_response "$challenge_recent_body"
  record_ok "challenge recent route responded with a structured application status"
else
  print_response "$challenge_recent_body" always
  record_failure "challenge recent route did not return the expected JSON surface"
fi

challenge_funding_recent_body="$tmpdir/challenge-funding-recent.json"
challenge_funding_recent_code="000"
if ! challenge_funding_recent_code="$(http_request GET "$SETTLEMENT_BASE_URL/settlement/v1/challenges/funding/deposits?limit=1" "$challenge_funding_recent_body")"; then
  :
fi
printf 'HTTP %s\n' "$challenge_funding_recent_code"
if [ "$challenge_funding_recent_code" = "404" ]; then
  print_response "$challenge_funding_recent_body" always
  record_failure "challenge funding recent route is not deployed on this service"
elif looks_like_json_response "$challenge_funding_recent_body"; then
  print_response "$challenge_funding_recent_body"
  record_ok "challenge funding recent route responded with a structured application status"
else
  print_response "$challenge_funding_recent_body" always
  record_failure "challenge funding recent route did not return the expected JSON surface"
fi

challenge_funding_probe_body="$tmpdir/challenge-funding-probe.json"
challenge_funding_probe_code="000"
if ! challenge_funding_probe_code="$(http_request GET "$SETTLEMENT_BASE_URL/settlement/v1/challenges/funding/txs/not-a-real-hash" "$challenge_funding_probe_body")"; then
  :
fi
printf 'HTTP %s\n' "$challenge_funding_probe_code"
if { [ "$challenge_funding_probe_code" = "400" ] || [ "$challenge_funding_probe_code" = "404" ] || [ "$challenge_funding_probe_code" = "503" ]; } && looks_like_json_response "$challenge_funding_probe_body"; then
  print_response "$challenge_funding_probe_body"
  record_ok "challenge funding verify route is deployed and returns structured status"
else
  print_response "$challenge_funding_probe_body" always
  record_failure "challenge funding verify route did not return the expected structured response"
fi

note "CLI Surface"
cli_help="$tmpdir/settlement-help.txt"
capture_settlement_cli "$cli_help" settlement --help || true
print_response "$cli_help"

if grep -qE '(^|[[:space:]])inspect([[:space:]]|$)' "$cli_help" && grep -qE '(^|[[:space:]])recent([[:space:]]|$)' "$cli_help"; then
  record_ok "request-level inspect/recent commands are available"

  note "Request Recent Summary"
  request_recent="$tmpdir/request-recent.json"
  if capture_settlement_cli "$request_recent" settlement recent --summary-only; then
    print_response "$request_recent"
    record_ok "request-level recent summary command succeeded"
  else
    print_response "$request_recent" always
    record_failure "request-level recent summary failed"
  fi

  note "Missing Request Inspect"
  request_inspect="$tmpdir/request-inspect.json"
  if capture_settlement_cli "$request_inspect" settlement inspect --request-id verify-live-missing --summary-only; then
    print_response "$request_inspect"
    record_ok "request-level inspect command succeeded"
  else
    print_response "$request_inspect" always
    record_failure "request-level inspect failed"
  fi
else
  print_response "$cli_help" always
  record_failure "request-level inspect/recent commands are not deployed in the current binary"
fi

if grep -qE '(^|[[:space:]])run([[:space:]]|$)' "$cli_help"; then
  record_ok "grouped run commands are available"

  note "Run Recent Summary"
  run_recent="$tmpdir/run-recent.json"
  if capture_settlement_cli "$run_recent" settlement run recent --summary-only; then
    print_response "$run_recent"
    record_ok "grouped run recent summary command succeeded"
  else
    print_response "$run_recent" always
    record_failure "grouped run recent summary failed"
  fi

  note "Missing Run Inspect"
  run_inspect="$tmpdir/run-inspect.json"
  if capture_settlement_cli "$run_inspect" settlement run inspect --run-id verify-live-missing --summary-only; then
    print_response "$run_inspect"
    record_ok "grouped run inspect command succeeded"
  else
    print_response "$run_inspect" always
    record_failure "grouped run inspect failed"
  fi
else
  print_response "$cli_help" always
  record_failure "grouped run commands are not deployed in the current binary"
fi

if grep -qE '(^|[[:space:]])escrow([[:space:]]|$)' "$cli_help"; then
  record_ok "escrow verification commands are available"
else
  record_failure "escrow verification commands are not deployed in the current binary"
fi

if grep -qE '(^|[[:space:]])challenge([[:space:]]|$)' "$cli_help"; then
  record_ok "challenge settlement commands are available"

  note "Challenge Recent Summary"
  challenge_recent="$tmpdir/challenge-recent-cli.json"
  if capture_settlement_cli "$challenge_recent" settlement challenge recent --summary-only; then
    print_response "$challenge_recent"
    record_ok "challenge recent summary command succeeded"
  else
    print_response "$challenge_recent" always
    record_failure "challenge recent summary failed"
  fi

  note "Missing Challenge Inspect"
  challenge_inspect="$tmpdir/challenge-inspect-cli.json"
  if capture_settlement_cli "$challenge_inspect" settlement challenge inspect --settlement-id verify-live-missing --summary-only; then
    print_response "$challenge_inspect"
    record_ok "challenge inspect command succeeded"
  else
    print_response "$challenge_inspect" always
    record_failure "challenge inspect failed"
  fi
else
  record_failure "challenge settlement commands are not deployed in the current binary"
fi

note "Summary"
if [ "$failures" -eq 0 ]; then
  printf 'All settlement rollout checks passed.\n'
else
  printf 'Settlement rollout checks finished with %d failure(s).\n' "$failures"
fi

exit "$failures"
