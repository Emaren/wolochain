#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
WOLOCHAIND_BIN="${WOLOCHAIND_BIN:-$ROOT_DIR/build/wolochaind}"
SETTLEMENT_ENV_FILE="${SETTLEMENT_ENV_FILE:-}"
SETTLEMENT_BASE_URL="${SETTLEMENT_BASE_URL:-http://127.0.0.1:8091}"
CHECK_SERVICE="${CHECK_SERVICE:-1}"
WOLOCHAIND_SUDO_USER="${WOLOCHAIND_SUDO_USER:-}"
CUTOVER_VERBOSE="${CUTOVER_VERBOSE:-0}"

if [[ -z "$SETTLEMENT_ENV_FILE" ]] && command -v systemctl >/dev/null 2>&1; then
  SETTLEMENT_ENV_FILE="$(systemctl show -p EnvironmentFiles --value wolochain-settlement.service 2>/dev/null | awk '{print $1}' | sed 's/^-//')"
fi
if [[ -n "$SETTLEMENT_ENV_FILE" ]]; then
  if [[ ! -r "$SETTLEMENT_ENV_FILE" ]]; then
    SETTLEMENT_ENV_FILE=""
  else
    set -a
    # shellcheck disable=SC1090
    source "$SETTLEMENT_ENV_FILE"
    set +a
  fi
fi

HAS_INTENDED_CONFIG=0
CONFIG_SOURCE="shell defaults only"
if [[ -n "$SETTLEMENT_ENV_FILE" ]]; then
  HAS_INTENDED_CONFIG=1
  CONFIG_SOURCE="$SETTLEMENT_ENV_FILE"
fi
for item in \
  WOLO_SETTLEMENT_PAYOUT_ADDRESS \
  WOLO_SETTLEMENT_ESCROW_ADDRESS \
  WOLO_SETTLEMENT_PUBLIC_REST_URL \
  WOLO_SETTLEMENT_AUTH_TOKEN \
  WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO \
  WOLO_SETTLEMENT_FEE_HEADROOM_UWOLO \
  WOLO_SETTLEMENT_MIN_ESCROW_BALANCE_UWOLO \
  WOLO_SETTLEMENT_ESCROW_FEE_HEADROOM_UWOLO; do
  if [[ -n "${!item:-}" ]]; then
    HAS_INTENDED_CONFIG=1
    if [[ -z "$SETTLEMENT_ENV_FILE" ]]; then
      CONFIG_SOURCE="current shell environment"
    fi
    break
  fi
done

WOLO_SETTLEMENT_HOME="${WOLO_SETTLEMENT_HOME:-${WOLO_HOME:-/var/lib/wolochaind-testnet}}"
WOLO_SETTLEMENT_STATE_DIR="${WOLO_SETTLEMENT_STATE_DIR:-/mnt/HC_Volume_105319120/wolochain/settlement-state}"
WOLO_SETTLEMENT_KEYRING_BACKEND="${WOLO_SETTLEMENT_KEYRING_BACKEND:-test}"
WOLO_SETTLEMENT_CHAIN_ID="${WOLO_SETTLEMENT_CHAIN_ID:-wolo-testnet}"
WOLO_SETTLEMENT_BASE_DENOM="${WOLO_SETTLEMENT_BASE_DENOM:-uwolo}"
WOLO_SETTLEMENT_DISPLAY_DENOM="${WOLO_SETTLEMENT_DISPLAY_DENOM:-wolo}"
WOLO_SETTLEMENT_ADDRESS_PREFIX="${WOLO_SETTLEMENT_ADDRESS_PREFIX:-wolo}"
WOLO_SETTLEMENT_PAYOUT_KEY_NAME="${WOLO_SETTLEMENT_PAYOUT_KEY_NAME:-payout}"
WOLO_SETTLEMENT_ESCROW_KEY_NAME="${WOLO_SETTLEMENT_ESCROW_KEY_NAME:-escrow}"
WOLO_SETTLEMENT_PAYOUT_ADDRESS="${WOLO_SETTLEMENT_PAYOUT_ADDRESS:-}"
WOLO_SETTLEMENT_ESCROW_ADDRESS="${WOLO_SETTLEMENT_ESCROW_ADDRESS:-}"
WOLO_SETTLEMENT_PUBLIC_REST_URL="${WOLO_SETTLEMENT_PUBLIC_REST_URL:-}"
WOLO_SETTLEMENT_AUTH_TOKEN="${WOLO_SETTLEMENT_AUTH_TOKEN:-}"
WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO="${WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO:-}"
WOLO_SETTLEMENT_FEE_HEADROOM_UWOLO="${WOLO_SETTLEMENT_FEE_HEADROOM_UWOLO:-}"
WOLO_SETTLEMENT_MIN_ESCROW_BALANCE_UWOLO="${WOLO_SETTLEMENT_MIN_ESCROW_BALANCE_UWOLO:-}"
WOLO_SETTLEMENT_ESCROW_FEE_HEADROOM_UWOLO="${WOLO_SETTLEMENT_ESCROW_FEE_HEADROOM_UWOLO:-}"

failures=0
warnings=0
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

note() {
  printf '\n## %s\n' "$1"
}

record_ok() {
  printf 'OK: %s\n' "$1"
}

record_failure() {
  printf 'FAIL: %s\n' "$1" >&2
  failures=$((failures + 1))
}

record_warning() {
  printf 'WARN: %s\n' "$1"
  warnings=$((warnings + 1))
}

run_wolochaind() {
  if [[ -n "$WOLOCHAIND_SUDO_USER" ]]; then
    sudo -u "$WOLOCHAIND_SUDO_USER" env \
      WOLO_SETTLEMENT_HOME="$WOLO_SETTLEMENT_HOME" \
      WOLO_SETTLEMENT_STATE_DIR="$WOLO_SETTLEMENT_STATE_DIR" \
      WOLO_SETTLEMENT_KEYRING_BACKEND="$WOLO_SETTLEMENT_KEYRING_BACKEND" \
      WOLO_SETTLEMENT_CHAIN_ID="$WOLO_SETTLEMENT_CHAIN_ID" \
      WOLO_SETTLEMENT_BASE_DENOM="$WOLO_SETTLEMENT_BASE_DENOM" \
      WOLO_SETTLEMENT_DISPLAY_DENOM="$WOLO_SETTLEMENT_DISPLAY_DENOM" \
      WOLO_SETTLEMENT_ADDRESS_PREFIX="$WOLO_SETTLEMENT_ADDRESS_PREFIX" \
      WOLO_SETTLEMENT_PAYOUT_KEY_NAME="$WOLO_SETTLEMENT_PAYOUT_KEY_NAME" \
      WOLO_SETTLEMENT_PAYOUT_ADDRESS="$WOLO_SETTLEMENT_PAYOUT_ADDRESS" \
      WOLO_SETTLEMENT_ESCROW_KEY_NAME="$WOLO_SETTLEMENT_ESCROW_KEY_NAME" \
      WOLO_SETTLEMENT_ESCROW_ADDRESS="$WOLO_SETTLEMENT_ESCROW_ADDRESS" \
      WOLO_SETTLEMENT_PUBLIC_REST_URL="$WOLO_SETTLEMENT_PUBLIC_REST_URL" \
      WOLO_SETTLEMENT_AUTH_TOKEN="$WOLO_SETTLEMENT_AUTH_TOKEN" \
      WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO="$WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO" \
      WOLO_SETTLEMENT_FEE_HEADROOM_UWOLO="$WOLO_SETTLEMENT_FEE_HEADROOM_UWOLO" \
      WOLO_SETTLEMENT_MIN_ESCROW_BALANCE_UWOLO="$WOLO_SETTLEMENT_MIN_ESCROW_BALANCE_UWOLO" \
      WOLO_SETTLEMENT_ESCROW_FEE_HEADROOM_UWOLO="$WOLO_SETTLEMENT_ESCROW_FEE_HEADROOM_UWOLO" \
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
    WOLO_SETTLEMENT_PAYOUT_KEY_NAME="$WOLO_SETTLEMENT_PAYOUT_KEY_NAME" \
    WOLO_SETTLEMENT_PAYOUT_ADDRESS="$WOLO_SETTLEMENT_PAYOUT_ADDRESS" \
    WOLO_SETTLEMENT_ESCROW_KEY_NAME="$WOLO_SETTLEMENT_ESCROW_KEY_NAME" \
    WOLO_SETTLEMENT_ESCROW_ADDRESS="$WOLO_SETTLEMENT_ESCROW_ADDRESS" \
    WOLO_SETTLEMENT_PUBLIC_REST_URL="$WOLO_SETTLEMENT_PUBLIC_REST_URL" \
    WOLO_SETTLEMENT_AUTH_TOKEN="$WOLO_SETTLEMENT_AUTH_TOKEN" \
    WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO="$WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO" \
    WOLO_SETTLEMENT_FEE_HEADROOM_UWOLO="$WOLO_SETTLEMENT_FEE_HEADROOM_UWOLO" \
    WOLO_SETTLEMENT_MIN_ESCROW_BALANCE_UWOLO="$WOLO_SETTLEMENT_MIN_ESCROW_BALANCE_UWOLO" \
    WOLO_SETTLEMENT_ESCROW_FEE_HEADROOM_UWOLO="$WOLO_SETTLEMENT_ESCROW_FEE_HEADROOM_UWOLO" \
    "$WOLOCHAIND_BIN" "$@"
}

key_address() {
  local key_name="$1"
  if [[ -n "$WOLOCHAIND_SUDO_USER" ]]; then
    sudo -u "$WOLOCHAIND_SUDO_USER" "$WOLOCHAIND_BIN" keys show "$key_name" \
      --address \
      --home "$WOLO_SETTLEMENT_HOME" \
      --keyring-backend "$WOLO_SETTLEMENT_KEYRING_BACKEND"
    return
  fi

  "$WOLOCHAIND_BIN" keys show "$key_name" \
    --address \
    --home "$WOLO_SETTLEMENT_HOME" \
    --keyring-backend "$WOLO_SETTLEMENT_KEYRING_BACKEND"
}

is_wolo_address() {
  local value="$1"
  [[ "$value" =~ ^wolo1[0-9a-z]{38,}$ ]]
}

is_positive_integer() {
  local value="$1"
  [[ "$value" =~ ^[0-9]+$ ]] && [[ "$value" != "0" ]]
}

is_key_access_limited() {
  local detail="${1,,}"
  [[ "$detail" == *"permission denied"* || "$detail" == *"password is required"* || "$detail" == *"not readable"* ]]
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
  cat "$body_path" 2>/dev/null || true
  if [[ -s "$body_path.stderr" ]]; then
    printf '\n[curl stderr]\n'
    cat "$body_path.stderr"
  fi
  printf '\n'
}

print_file_if_needed() {
  local body_path="$1"
  local mode="${2:-default}"
  if [[ "$mode" != "always" && "$CUTOVER_VERBOSE" != "1" ]]; then
    return
  fi
  cat "$body_path" 2>/dev/null || true
  printf '\n'
}

strip_known_noise_file() {
  local path="$1"
  sed -i.bak '/^WARNING: sonic\/ast only supports .*fallback to encoding\/json$/d' "$path" 2>/dev/null || true
  rm -f "$path.bak"
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

compare_live_value() {
  local label="$1"
  local expected="$2"
  local actual="$3"

  if [[ -z "$expected" ]]; then
    record_warning "skipping $label comparison because the intended value is unavailable"
    return
  fi
  if [[ "$expected" == "$actual" ]]; then
    record_ok "$label matches live service"
  else
    record_failure "$label drift: intended=$expected live=${actual:-<unset>}"
  fi
}

if [[ ! -x "$WOLOCHAIND_BIN" ]]; then
  printf 'missing executable settlement binary: %s\n' "$WOLOCHAIND_BIN" >&2
  exit 2
fi
if [[ "$CHECK_SERVICE" != "0" ]] && ! command -v curl >/dev/null 2>&1; then
  printf 'curl is required when CHECK_SERVICE=1\n' >&2
  exit 2
fi

note "Context"
printf 'Binary: %s\n' "$WOLOCHAIND_BIN"
printf 'Home: %s\n' "$WOLO_SETTLEMENT_HOME"
printf 'State dir: %s\n' "$WOLO_SETTLEMENT_STATE_DIR"
printf 'Keyring backend: %s\n' "$WOLO_SETTLEMENT_KEYRING_BACKEND"
printf 'Payout key: %s\n' "$WOLO_SETTLEMENT_PAYOUT_KEY_NAME"
printf 'Escrow key: %s\n' "$WOLO_SETTLEMENT_ESCROW_KEY_NAME"
printf 'Target service: %s\n' "$SETTLEMENT_BASE_URL"
printf 'Intended config source: %s\n' "$CONFIG_SOURCE"
if [[ -n "$WOLOCHAIND_SUDO_USER" ]]; then
  printf 'CLI user: %s\n' "$WOLOCHAIND_SUDO_USER"
fi

note "Intended Config"
if [[ "$HAS_INTENDED_CONFIG" -eq 1 ]]; then
  for item in \
    WOLO_SETTLEMENT_PAYOUT_ADDRESS \
    WOLO_SETTLEMENT_ESCROW_ADDRESS \
    WOLO_SETTLEMENT_PUBLIC_REST_URL \
    WOLO_SETTLEMENT_AUTH_TOKEN \
    WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO \
    WOLO_SETTLEMENT_FEE_HEADROOM_UWOLO \
    WOLO_SETTLEMENT_MIN_ESCROW_BALANCE_UWOLO \
    WOLO_SETTLEMENT_ESCROW_FEE_HEADROOM_UWOLO; do
    value="${!item:-}"
    if [[ -n "$value" ]]; then
      record_ok "$item is set"
    else
      record_failure "$item is not set"
    fi
  done

  if [[ -d "$WOLO_SETTLEMENT_STATE_DIR" ]]; then
    record_ok "settlement state dir exists"
  else
    record_failure "settlement state dir does not exist: $WOLO_SETTLEMENT_STATE_DIR"
  fi

  if is_wolo_address "$WOLO_SETTLEMENT_PAYOUT_ADDRESS"; then
    record_ok "payout address looks like a WOLO address"
  else
    record_failure "WOLO_SETTLEMENT_PAYOUT_ADDRESS is not a valid-looking WOLO address"
  fi

  if is_wolo_address "$WOLO_SETTLEMENT_ESCROW_ADDRESS"; then
    record_ok "escrow address looks like a WOLO address"
  else
    record_failure "WOLO_SETTLEMENT_ESCROW_ADDRESS is not a valid-looking WOLO address"
  fi

  if [[ "$WOLO_SETTLEMENT_PAYOUT_ADDRESS" == "$WOLO_SETTLEMENT_ESCROW_ADDRESS" ]]; then
    record_failure "payout and escrow addresses are still the same in the intended config"
  else
    record_ok "payout and escrow addresses are distinct in the intended config"
  fi

  if [[ "$WOLO_SETTLEMENT_PUBLIC_REST_URL" =~ ^https?://[^[:space:]]+$ ]]; then
    record_ok "public REST URL is shaped like an HTTP URL"
  else
    record_failure "WOLO_SETTLEMENT_PUBLIC_REST_URL is not a valid-looking HTTP URL"
  fi

  if is_positive_integer "$WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO"; then
    record_ok "reserve floor is set to a positive integer"
  else
    record_failure "WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO must be a positive integer"
  fi

  if is_positive_integer "$WOLO_SETTLEMENT_FEE_HEADROOM_UWOLO"; then
    record_ok "fee headroom is set to a positive integer"
  else
    record_failure "WOLO_SETTLEMENT_FEE_HEADROOM_UWOLO must be a positive integer"
  fi

  if is_positive_integer "$WOLO_SETTLEMENT_MIN_ESCROW_BALANCE_UWOLO"; then
    record_ok "escrow reserve floor is set to a positive integer"
  else
    record_failure "WOLO_SETTLEMENT_MIN_ESCROW_BALANCE_UWOLO must be a positive integer"
  fi

  if is_positive_integer "$WOLO_SETTLEMENT_ESCROW_FEE_HEADROOM_UWOLO"; then
    record_ok "escrow fee headroom is set to a positive integer"
  else
    record_failure "WOLO_SETTLEMENT_ESCROW_FEE_HEADROOM_UWOLO must be a positive integer"
  fi
else
  record_warning "no readable settlement env file or explicit shell overrides were provided; skipping intended-config assertions"
fi

note "Operator Key Access"
if payout_key_address="$(key_address "$WOLO_SETTLEMENT_PAYOUT_KEY_NAME" 2>"$tmpdir/payout-key.stderr")"; then
  printf 'Payout key address: %s\n' "$payout_key_address"
  record_ok "payout key exists"
  if [[ -n "$WOLO_SETTLEMENT_PAYOUT_ADDRESS" ]] && [[ "$payout_key_address" != "$WOLO_SETTLEMENT_PAYOUT_ADDRESS" ]]; then
    record_failure "WOLO_SETTLEMENT_PAYOUT_ADDRESS does not match the payout key address"
  elif [[ -n "$WOLO_SETTLEMENT_PAYOUT_ADDRESS" ]]; then
    record_ok "payout key address matches WOLO_SETTLEMENT_PAYOUT_ADDRESS"
  fi
else
  payout_key_error="$(tr '\n' ' ' <"$tmpdir/payout-key.stderr" | sed 's/[[:space:]]\+/ /g; s/^ //; s/ $//')"
  if is_key_access_limited "$payout_key_error"; then
    record_warning "payout key lookup is permission-limited for the current operator context: $payout_key_error"
  else
    record_failure "payout key does not exist or could not be resolved: ${payout_key_error:-unknown error}"
  fi
fi

if escrow_key_address="$(key_address "$WOLO_SETTLEMENT_ESCROW_KEY_NAME" 2>"$tmpdir/escrow-key.stderr")"; then
  printf 'Escrow key address: %s\n' "$escrow_key_address"
  record_ok "escrow key exists"
  if [[ -n "$WOLO_SETTLEMENT_ESCROW_ADDRESS" ]] && [[ "$escrow_key_address" != "$WOLO_SETTLEMENT_ESCROW_ADDRESS" ]]; then
    record_failure "WOLO_SETTLEMENT_ESCROW_ADDRESS does not match the escrow key address"
  elif [[ -n "$WOLO_SETTLEMENT_ESCROW_ADDRESS" ]]; then
    record_ok "escrow key address matches WOLO_SETTLEMENT_ESCROW_ADDRESS"
  fi
else
  escrow_key_error="$(tr '\n' ' ' <"$tmpdir/escrow-key.stderr" | sed 's/[[:space:]]\+/ /g; s/^ //; s/ $//')"
  if is_key_access_limited "$escrow_key_error"; then
    record_warning "escrow key lookup is permission-limited for the current operator context: $escrow_key_error"
  else
    record_failure "escrow key does not exist or could not be resolved: ${escrow_key_error:-unknown error}"
  fi
fi

note "Local CLI Doctor"
if [[ "$HAS_INTENDED_CONFIG" -eq 1 ]]; then
  doctor_output="$tmpdir/doctor.json"
  doctor_rc=0
  if run_wolochaind settlement doctor >"$doctor_output" 2>&1; then
    doctor_rc=0
  else
    doctor_rc=$?
  fi
  strip_known_noise_file "$doctor_output"

  if [[ "$doctor_rc" -ne 0 ]]; then
    print_file_if_needed "$doctor_output" always
    record_failure "settlement doctor exited with code $doctor_rc"
  elif grep -q '"ok":[[:space:]]*true' "$doctor_output"; then
    print_file_if_needed "$doctor_output"
    record_ok "settlement doctor returned ok=true"
  else
    print_file_if_needed "$doctor_output" always
    record_failure "settlement doctor did not return ok=true"
  fi
  if grep -q '"public_rest_url":[[:space:]]*"' "$doctor_output"; then
    record_ok "settlement doctor reports a public proof URL"
  else
    record_failure "settlement doctor did not report public_rest_url"
  fi
  if grep -q '"auth_token_set":[[:space:]]*true' "$doctor_output"; then
    record_ok "settlement doctor reports auth enabled"
  else
    record_failure "settlement doctor did not report auth_token_set=true"
  fi
else
  record_warning "skipping local CLI doctor because the intended config is unavailable"
fi

if [[ "$CHECK_SERVICE" != "0" ]]; then
  note "Live Service Verification"
  verify_output="$tmpdir/live-verify.txt"
  if WOLOCHAIND_BIN="$WOLOCHAIND_BIN" \
    WOLOCHAIND_SUDO_USER="$WOLOCHAIND_SUDO_USER" \
    SETTLEMENT_BASE_URL="$SETTLEMENT_BASE_URL" \
    WOLO_SETTLEMENT_HOME="$WOLO_SETTLEMENT_HOME" \
    WOLO_SETTLEMENT_STATE_DIR="$WOLO_SETTLEMENT_STATE_DIR" \
    WOLO_SETTLEMENT_KEYRING_BACKEND="$WOLO_SETTLEMENT_KEYRING_BACKEND" \
    WOLO_SETTLEMENT_CHAIN_ID="$WOLO_SETTLEMENT_CHAIN_ID" \
    WOLO_SETTLEMENT_BASE_DENOM="$WOLO_SETTLEMENT_BASE_DENOM" \
    WOLO_SETTLEMENT_DISPLAY_DENOM="$WOLO_SETTLEMENT_DISPLAY_DENOM" \
    WOLO_SETTLEMENT_ADDRESS_PREFIX="$WOLO_SETTLEMENT_ADDRESS_PREFIX" \
    WOLO_SETTLEMENT_PAYOUT_ADDRESS="$WOLO_SETTLEMENT_PAYOUT_ADDRESS" \
    WOLO_SETTLEMENT_AUTH_TOKEN="$WOLO_SETTLEMENT_AUTH_TOKEN" \
    VERIFY_VERBOSE="$CUTOVER_VERBOSE" \
    "$ROOT_DIR/scripts/verify-live-settlement.sh" >"$verify_output" 2>&1; then
    print_file_if_needed "$verify_output"
    record_ok "live service verification passed"
  else
    verify_exit=$?
    print_file_if_needed "$verify_output" always
    record_failure "live service verification failed with exit code $verify_exit"
  fi

  note "Live Service Health"
  live_health_body="$tmpdir/live-health.json"
  live_health_rc=0
  if live_health_code="$(http_request GET "$SETTLEMENT_BASE_URL/settlement/v1/health" "$live_health_body")"; then
    live_health_rc=0
  else
    live_health_rc=$?
  fi
  strip_known_noise_file "$live_health_body"
  strip_known_noise_file "$live_health_body.stderr"
  printf 'HTTP %s\n' "$live_health_code"

  if [[ "$live_health_rc" -ne 0 ]]; then
    print_response "$live_health_body"
    record_failure "could not reach live settlement health endpoint"
  elif [[ "$live_health_code" != "200" ]]; then
    print_response "$live_health_body"
    record_failure "live settlement health returned HTTP $live_health_code"
  else
    print_file_if_needed "$live_health_body"
    record_ok "live settlement health returned HTTP 200"
  fi

  live_payout_address="$(extract_json_string payout_address "$live_health_body")"
  live_escrow_address="$(extract_json_string escrow_address "$live_health_body")"
  live_public_rest_url="$(extract_json_string public_rest_url "$live_health_body")"
  live_auth_token_set="$(extract_json_bool auth_token_set "$live_health_body")"
  live_min_payout_balance="$(extract_json_string min_payout_balance_uwolo "$live_health_body")"
  live_fee_headroom="$(extract_json_string fee_headroom_uwolo "$live_health_body")"
  live_min_escrow_balance="$(extract_json_string min_escrow_balance_uwolo "$live_health_body")"
  live_escrow_fee_headroom="$(extract_json_string escrow_fee_headroom_uwolo "$live_health_body")"

  if [[ "$HAS_INTENDED_CONFIG" -eq 1 ]]; then
    compare_live_value "payout address" "$WOLO_SETTLEMENT_PAYOUT_ADDRESS" "$live_payout_address"
    compare_live_value "escrow address" "$WOLO_SETTLEMENT_ESCROW_ADDRESS" "$live_escrow_address"
    compare_live_value "public REST URL" "$WOLO_SETTLEMENT_PUBLIC_REST_URL" "$live_public_rest_url"
    compare_live_value "reserve floor" "$WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO" "$live_min_payout_balance"
    compare_live_value "fee headroom" "$WOLO_SETTLEMENT_FEE_HEADROOM_UWOLO" "$live_fee_headroom"
    compare_live_value "escrow reserve floor" "$WOLO_SETTLEMENT_MIN_ESCROW_BALANCE_UWOLO" "$live_min_escrow_balance"
    compare_live_value "escrow fee headroom" "$WOLO_SETTLEMENT_ESCROW_FEE_HEADROOM_UWOLO" "$live_escrow_fee_headroom"

    expected_auth_enabled="false"
    if [[ -n "$WOLO_SETTLEMENT_AUTH_TOKEN" ]]; then
      expected_auth_enabled="true"
    fi
    compare_live_value "auth enabled flag" "$expected_auth_enabled" "${live_auth_token_set:-false}"
  else
    record_warning "skipping live-vs-intended comparisons because the intended config is unavailable"
  fi

  if [[ -n "$live_payout_address" && -n "$live_escrow_address" && "$live_payout_address" != "$live_escrow_address" ]]; then
    record_ok "live payout and escrow addresses are distinct"
  elif [[ -n "$live_payout_address" || -n "$live_escrow_address" ]]; then
    record_failure "live payout and escrow addresses are not distinct"
  fi
else
  printf 'Skipping live service verification because CHECK_SERVICE=0.\n'
fi

note "Summary"
if [[ "$failures" -eq 0 ]]; then
  printf 'Settlement cutover checks passed'
else
  printf 'Settlement cutover checks finished with %d failure(s)' "$failures"
fi
if [[ "$warnings" -gt 0 ]]; then
  printf ' and %d warning(s)' "$warnings"
fi
printf '.\n'

exit "$failures"
