#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
WOLOCHAIND_BIN="${WOLOCHAIND_BIN:-$ROOT_DIR/build/wolochaind}"
SETTLEMENT_ENV_FILE="${SETTLEMENT_ENV_FILE:-}"
SETTLEMENT_BASE_URL="${SETTLEMENT_BASE_URL:-http://127.0.0.1:8091}"
CHECK_SERVICE="${CHECK_SERVICE:-1}"
WOLOCHAIND_SUDO_USER="${WOLOCHAIND_SUDO_USER:-}"

if [[ -n "$SETTLEMENT_ENV_FILE" ]]; then
  if [[ ! -r "$SETTLEMENT_ENV_FILE" ]]; then
    printf 'SETTLEMENT_ENV_FILE is not readable: %s\n' "$SETTLEMENT_ENV_FILE" >&2
    exit 2
  fi
  set -a
  # shellcheck disable=SC1090
  source "$SETTLEMENT_ENV_FILE"
  set +a
fi

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

failures=0

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
      WOLO_SETTLEMENT_ESCROW_ADDRESS="$WOLO_SETTLEMENT_ESCROW_ADDRESS" \
      WOLO_SETTLEMENT_PUBLIC_REST_URL="$WOLO_SETTLEMENT_PUBLIC_REST_URL" \
      WOLO_SETTLEMENT_AUTH_TOKEN="$WOLO_SETTLEMENT_AUTH_TOKEN" \
      WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO="$WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO" \
      WOLO_SETTLEMENT_FEE_HEADROOM_UWOLO="$WOLO_SETTLEMENT_FEE_HEADROOM_UWOLO" \
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
    WOLO_SETTLEMENT_ESCROW_ADDRESS="$WOLO_SETTLEMENT_ESCROW_ADDRESS" \
    WOLO_SETTLEMENT_PUBLIC_REST_URL="$WOLO_SETTLEMENT_PUBLIC_REST_URL" \
    WOLO_SETTLEMENT_AUTH_TOKEN="$WOLO_SETTLEMENT_AUTH_TOKEN" \
    WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO="$WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO" \
    WOLO_SETTLEMENT_FEE_HEADROOM_UWOLO="$WOLO_SETTLEMENT_FEE_HEADROOM_UWOLO" \
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

if [[ ! -x "$WOLOCHAIND_BIN" ]]; then
  printf 'missing executable settlement binary: %s\n' "$WOLOCHAIND_BIN" >&2
  exit 2
fi

note "Config Surface"
printf 'Binary: %s\n' "$WOLOCHAIND_BIN"
printf 'Home: %s\n' "$WOLO_SETTLEMENT_HOME"
printf 'State dir: %s\n' "$WOLO_SETTLEMENT_STATE_DIR"
printf 'Keyring backend: %s\n' "$WOLO_SETTLEMENT_KEYRING_BACKEND"
printf 'Payout key: %s\n' "$WOLO_SETTLEMENT_PAYOUT_KEY_NAME"
printf 'Escrow key: %s\n' "$WOLO_SETTLEMENT_ESCROW_KEY_NAME"
printf 'Target service: %s\n' "$SETTLEMENT_BASE_URL"
if [[ -n "$WOLOCHAIND_SUDO_USER" ]]; then
  printf 'CLI user: %s\n' "$WOLOCHAIND_SUDO_USER"
fi

note "Required Env"
for item in \
  WOLO_SETTLEMENT_PAYOUT_ADDRESS \
  WOLO_SETTLEMENT_ESCROW_ADDRESS \
  WOLO_SETTLEMENT_PUBLIC_REST_URL \
  WOLO_SETTLEMENT_AUTH_TOKEN \
  WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO \
  WOLO_SETTLEMENT_FEE_HEADROOM_UWOLO; do
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

if [[ "$WOLO_SETTLEMENT_PAYOUT_ADDRESS" != "" ]] && [[ "$WOLO_SETTLEMENT_PAYOUT_ADDRESS" == "$WOLO_SETTLEMENT_ESCROW_ADDRESS" ]]; then
  record_failure "payout and escrow addresses are still the same"
else
  record_ok "payout and escrow addresses are distinct"
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

note "Key Checks"
if payout_key_address="$(key_address "$WOLO_SETTLEMENT_PAYOUT_KEY_NAME" 2>/dev/null)"; then
  printf 'Payout key address: %s\n' "$payout_key_address"
  record_ok "payout key exists"
  if [[ -n "$WOLO_SETTLEMENT_PAYOUT_ADDRESS" ]] && [[ "$payout_key_address" != "$WOLO_SETTLEMENT_PAYOUT_ADDRESS" ]]; then
    record_failure "WOLO_SETTLEMENT_PAYOUT_ADDRESS does not match the payout key address"
  else
    record_ok "payout key address matches WOLO_SETTLEMENT_PAYOUT_ADDRESS"
  fi
else
  record_failure "payout key does not exist or is not readable via current user/sudo setup"
fi

if escrow_key_address="$(key_address "$WOLO_SETTLEMENT_ESCROW_KEY_NAME" 2>/dev/null)"; then
  printf 'Escrow key address: %s\n' "$escrow_key_address"
  record_ok "escrow key exists"
  if [[ -n "$WOLO_SETTLEMENT_ESCROW_ADDRESS" ]] && [[ "$escrow_key_address" != "$WOLO_SETTLEMENT_ESCROW_ADDRESS" ]]; then
    record_failure "WOLO_SETTLEMENT_ESCROW_ADDRESS does not match the escrow key address"
  else
    record_ok "escrow key address matches WOLO_SETTLEMENT_ESCROW_ADDRESS"
  fi
else
  record_failure "escrow key does not exist or is not readable via current user/sudo setup"
fi

note "Settlement Doctor"
doctor_output="$(run_wolochaind settlement doctor 2>&1 || true)"
printf '%s\n' "$doctor_output"
if grep -q '"ok":[[:space:]]*true' <<<"$doctor_output"; then
  record_ok "settlement doctor returned ok=true"
else
  record_failure "settlement doctor did not return ok=true"
fi
if grep -q '"public_rest_url":[[:space:]]*"' <<<"$doctor_output"; then
  record_ok "settlement doctor reports a public proof URL"
else
  record_failure "settlement doctor did not report public_rest_url"
fi
if grep -q '"auth_token_set":[[:space:]]*true' <<<"$doctor_output"; then
  record_ok "settlement doctor reports auth enabled"
else
  record_failure "settlement doctor did not report auth_token_set=true"
fi

if [[ "$CHECK_SERVICE" != "0" ]]; then
  note "Service Verification"
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
    WOLO_SETTLEMENT_AUTH_TOKEN="$WOLO_SETTLEMENT_AUTH_TOKEN" \
    "$ROOT_DIR/scripts/verify-live-settlement.sh"; then
    record_ok "service verification passed"
  else
    verify_exit=$?
    record_failure "service verification failed with exit code $verify_exit"
  fi
else
  printf 'Skipping service verification because CHECK_SERVICE=0.\n'
fi

note "Summary"
if [[ "$failures" -eq 0 ]]; then
  printf 'Settlement cutover checks passed.\n'
else
  printf 'Settlement cutover checks finished with %d failure(s).\n' "$failures"
fi

exit "$failures"
