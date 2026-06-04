#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
WOLOCHAIND_BIN="${WOLOCHAIND_BIN:-$ROOT_DIR/build/wolochaind}"
SETTLEMENT_ENV_FILE="${SETTLEMENT_ENV_FILE:-}"
SETTLEMENT_BASE_URL="${SETTLEMENT_BASE_URL:-http://127.0.0.1:8092}"
WOLOCHAIND_SUDO_USER="${WOLOCHAIND_SUDO_USER:-}"
WOLO_ALERT_ROOT_PATH="${WOLO_ALERT_ROOT_PATH:-/}"
WOLO_ALERT_ROOT_WARN_FREE_KB="${WOLO_ALERT_ROOT_WARN_FREE_KB:-2097152}"
WOLO_ALERT_ROOT_FAIL_FREE_KB="${WOLO_ALERT_ROOT_FAIL_FREE_KB:-1048576}"
WOLO_ALERT_EXTRA_PATH="${WOLO_ALERT_EXTRA_PATH:-/mnt/HC_Volume_105319120}"
WOLO_ALERT_EXTRA_WARN_FREE_KB="${WOLO_ALERT_EXTRA_WARN_FREE_KB:-8388608}"
WOLO_ALERT_EXTRA_FAIL_FREE_KB="${WOLO_ALERT_EXTRA_FAIL_FREE_KB:-4194304}"

if [[ -z "$SETTLEMENT_ENV_FILE" ]] && command -v systemctl >/dev/null 2>&1; then
  SETTLEMENT_ENV_FILE="$(systemctl show -p EnvironmentFiles --value wolochain-mainnet-settlement.service 2>/dev/null | awk '{print $1}' | sed 's/^-//')"
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

WOLO_SETTLEMENT_HOME="${WOLO_SETTLEMENT_HOME:-${WOLO_HOME:-/var/lib/wolochaind-mainnet}}"
WOLO_SETTLEMENT_STATE_DIR="${WOLO_SETTLEMENT_STATE_DIR:-/mnt/HC_Volume_105319120/wolochain-mainnet/settlement-state}"
WOLO_SETTLEMENT_KEYRING_BACKEND="${WOLO_SETTLEMENT_KEYRING_BACKEND:-os}"
WOLO_SETTLEMENT_KEYRING_DIR="${WOLO_SETTLEMENT_KEYRING_DIR:-}"
WOLO_SETTLEMENT_KEYRING_PASSPHRASE_FILE="${WOLO_SETTLEMENT_KEYRING_PASSPHRASE_FILE:-}"
WOLO_SETTLEMENT_CHAIN_ID="${WOLO_SETTLEMENT_CHAIN_ID:-wolo-1}"
WOLO_SETTLEMENT_BASE_DENOM="${WOLO_SETTLEMENT_BASE_DENOM:-uwolo}"
WOLO_SETTLEMENT_DISPLAY_DENOM="${WOLO_SETTLEMENT_DISPLAY_DENOM:-wolo}"
WOLO_SETTLEMENT_ADDRESS_PREFIX="${WOLO_SETTLEMENT_ADDRESS_PREFIX:-wolo}"
WOLO_SETTLEMENT_PAYOUT_KEY_NAME="${WOLO_SETTLEMENT_PAYOUT_KEY_NAME:-mainnet-payout}"
WOLO_SETTLEMENT_ESCROW_KEY_NAME="${WOLO_SETTLEMENT_ESCROW_KEY_NAME:-mainnet-escrow}"
WOLO_SETTLEMENT_PAYOUT_ADDRESS="${WOLO_SETTLEMENT_PAYOUT_ADDRESS:-}"
WOLO_SETTLEMENT_ESCROW_ADDRESS="${WOLO_SETTLEMENT_ESCROW_ADDRESS:-}"
WOLO_SETTLEMENT_AUTH_TOKEN="${WOLO_SETTLEMENT_AUTH_TOKEN:-}"
WOLO_SETTLEMENT_MIN_ESCROW_BALANCE_UWOLO="${WOLO_SETTLEMENT_MIN_ESCROW_BALANCE_UWOLO:-}"
WOLO_SETTLEMENT_ESCROW_FEE_HEADROOM_UWOLO="${WOLO_SETTLEMENT_ESCROW_FEE_HEADROOM_UWOLO:-}"

HAS_INTENDED_CONFIG=0
CONFIG_SOURCE="unavailable"
if [[ -n "$SETTLEMENT_ENV_FILE" ]]; then
  HAS_INTENDED_CONFIG=1
  CONFIG_SOURCE="$SETTLEMENT_ENV_FILE"
fi
for item in \
  WOLO_SETTLEMENT_PAYOUT_ADDRESS \
  WOLO_SETTLEMENT_ESCROW_ADDRESS \
  WOLO_SETTLEMENT_AUTH_TOKEN; do
  if [[ -n "${!item:-}" ]]; then
    HAS_INTENDED_CONFIG=1
    if [[ "$CONFIG_SOURCE" == "unavailable" ]]; then
      CONFIG_SOURCE="current shell environment"
    fi
    break
  fi
done

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

have() {
  command -v "$1" >/dev/null 2>&1
}

fail() {
  printf '%s\n' "$1" >&2
  exit 2
}

require_non_negative_int() {
  local name="$1"
  local value="$2"
  [[ "$value" =~ ^[0-9]+$ ]] || fail "$name must be a non-negative integer in KB: $value"
}

run_wolochaind() {
  if [[ -n "$WOLOCHAIND_SUDO_USER" ]]; then
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
      WOLO_SETTLEMENT_AUTH_TOKEN="$WOLO_SETTLEMENT_AUTH_TOKEN" \
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
    WOLO_SETTLEMENT_AUTH_TOKEN="$WOLO_SETTLEMENT_AUTH_TOKEN" \
    WOLO_SETTLEMENT_MIN_ESCROW_BALANCE_UWOLO="$WOLO_SETTLEMENT_MIN_ESCROW_BALANCE_UWOLO" \
    WOLO_SETTLEMENT_ESCROW_FEE_HEADROOM_UWOLO="$WOLO_SETTLEMENT_ESCROW_FEE_HEADROOM_UWOLO" \
    "$WOLOCHAIND_BIN" "$@"
}

key_address() {
	local key_name="$1"
	local args=(
		keys show "$key_name"
		--address
		--home "$WOLO_SETTLEMENT_HOME"
		--keyring-backend "$WOLO_SETTLEMENT_KEYRING_BACKEND"
	)
	if [[ -n "$WOLO_SETTLEMENT_KEYRING_DIR" ]]; then
		args+=(--keyring-dir "$WOLO_SETTLEMENT_KEYRING_DIR")
	fi
	if [[ -n "$WOLOCHAIND_SUDO_USER" ]]; then
		if [[ -n "$WOLO_SETTLEMENT_KEYRING_PASSPHRASE_FILE" ]]; then
			sudo -u "$WOLOCHAIND_SUDO_USER" "$WOLOCHAIND_BIN" "${args[@]}" <"$WOLO_SETTLEMENT_KEYRING_PASSPHRASE_FILE"
		else
			sudo -u "$WOLOCHAIND_SUDO_USER" "$WOLOCHAIND_BIN" "${args[@]}"
		fi
		return
	fi

	if [[ -n "$WOLO_SETTLEMENT_KEYRING_PASSPHRASE_FILE" ]]; then
		"$WOLOCHAIND_BIN" "${args[@]}" <"$WOLO_SETTLEMENT_KEYRING_PASSPHRASE_FILE"
	else
		"$WOLOCHAIND_BIN" "${args[@]}"
	fi
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

strip_known_noise_file() {
  local path="$1"
  sed -i.bak '/^WARNING: sonic\/ast only supports .*fallback to encoding\/json$/d' "$path" 2>/dev/null || true
  rm -f "$path.bak"
}

if ! have curl; then
  printf 'curl is required\n' >&2
  exit 2
fi
if ! have python3; then
  printf 'python3 is required\n' >&2
  exit 2
fi
if [[ ! -x "$WOLOCHAIND_BIN" ]]; then
  printf 'missing executable settlement binary: %s\n' "$WOLOCHAIND_BIN" >&2
  exit 2
fi

require_non_negative_int "WOLO_ALERT_ROOT_WARN_FREE_KB" "$WOLO_ALERT_ROOT_WARN_FREE_KB"
require_non_negative_int "WOLO_ALERT_ROOT_FAIL_FREE_KB" "$WOLO_ALERT_ROOT_FAIL_FREE_KB"
require_non_negative_int "WOLO_ALERT_EXTRA_WARN_FREE_KB" "$WOLO_ALERT_EXTRA_WARN_FREE_KB"
require_non_negative_int "WOLO_ALERT_EXTRA_FAIL_FREE_KB" "$WOLO_ALERT_EXTRA_FAIL_FREE_KB"

if (( WOLO_ALERT_ROOT_FAIL_FREE_KB > WOLO_ALERT_ROOT_WARN_FREE_KB )); then
  fail "WOLO_ALERT_ROOT_FAIL_FREE_KB must be less than or equal to WOLO_ALERT_ROOT_WARN_FREE_KB"
fi
if (( WOLO_ALERT_EXTRA_FAIL_FREE_KB > WOLO_ALERT_EXTRA_WARN_FREE_KB )); then
  fail "WOLO_ALERT_EXTRA_FAIL_FREE_KB must be less than or equal to WOLO_ALERT_EXTRA_WARN_FREE_KB"
fi

health_code="000"
health_rc=1
if health_code="$(http_request GET "$SETTLEMENT_BASE_URL/settlement/v1/health" "$tmpdir/health.json")"; then
  health_rc=0
fi
strip_known_noise_file "$tmpdir/health.json"
strip_known_noise_file "$tmpdir/health.json.stderr"

doctor_rc=0
doctor_skipped=0
if [[ "$HAS_INTENDED_CONFIG" -eq 1 ]]; then
  if run_wolochaind settlement doctor >"$tmpdir/doctor.json" 2>"$tmpdir/doctor.stderr"; then
    doctor_rc=0
  else
    doctor_rc=$?
  fi
else
  doctor_skipped=1
  printf '{}\n' >"$tmpdir/doctor.json"
  : >"$tmpdir/doctor.stderr"
fi
strip_known_noise_file "$tmpdir/doctor.json"
strip_known_noise_file "$tmpdir/doctor.stderr"

payout_key_rc=0
if key_address "$WOLO_SETTLEMENT_PAYOUT_KEY_NAME" >"$tmpdir/payout-key.txt" 2>"$tmpdir/payout-key.stderr"; then
  payout_key_rc=0
else
  payout_key_rc=$?
fi

escrow_key_rc=0
if key_address "$WOLO_SETTLEMENT_ESCROW_KEY_NAME" >"$tmpdir/escrow-key.txt" 2>"$tmpdir/escrow-key.stderr"; then
  escrow_key_rc=0
else
  escrow_key_rc=$?
fi

payout_address="$(sed -n 's/.*"payout_address":[[:space:]]*"\([^"]*\)".*/\1/p' "$tmpdir/health.json" | head -n 1)"
if [[ -z "$payout_address" ]]; then
  payout_address="${WOLO_SETTLEMENT_PAYOUT_ADDRESS:-}"
fi

run_body="$tmpdir/run.json"
cat >"$run_body" <<EOF
{
  "settlement_run_id": "settlement-health-probe-alert",
  "source_app": "settlement-health-probe",
  "source_event_id": "health-probe-alert-check",
  "note": "health probe only; dry-run route validation",
  "memo": "health_probe_alert",
  "payouts": [
    {
      "to_address": "$payout_address",
      "amount_uwolo": "1"
    }
  ]
}
EOF

grouped_code="000"
grouped_rc=1
if grouped_code="$(http_request POST "$SETTLEMENT_BASE_URL/settlement/v1/runs/validate" "$tmpdir/grouped.json" -H 'content-type: application/json' --data @"$run_body")"; then
  grouped_rc=0
fi

escrow_recent_code="000"
escrow_recent_rc=1
if escrow_recent_code="$(http_request GET "$SETTLEMENT_BASE_URL/settlement/v1/escrow/deposits?limit=1" "$tmpdir/escrow-recent.json")"; then
  escrow_recent_rc=0
fi

escrow_verify_code="000"
escrow_verify_rc=1
if escrow_verify_code="$(http_request GET "$SETTLEMENT_BASE_URL/settlement/v1/escrow/txs/not-a-real-hash" "$tmpdir/escrow-verify.json")"; then
  escrow_verify_rc=0
fi

export SETTLEMENT_BASE_URL
export WOLOCHAIND_BIN
export WOLOCHAIND_SUDO_USER
export WOLO_SETTLEMENT_HOME
export WOLO_SETTLEMENT_STATE_DIR
export WOLO_SETTLEMENT_KEYRING_BACKEND
export WOLO_SETTLEMENT_KEYRING_DIR
export WOLO_SETTLEMENT_KEYRING_PASSPHRASE_FILE
export WOLO_SETTLEMENT_PAYOUT_KEY_NAME
export WOLO_SETTLEMENT_ESCROW_KEY_NAME
export WOLO_SETTLEMENT_PAYOUT_ADDRESS
export WOLO_SETTLEMENT_ESCROW_ADDRESS
export WOLO_SETTLEMENT_MIN_ESCROW_BALANCE_UWOLO
export WOLO_SETTLEMENT_ESCROW_FEE_HEADROOM_UWOLO
export CONFIG_SOURCE
export HAS_INTENDED_CONFIG
export WOLO_ALERT_ROOT_PATH
export WOLO_ALERT_ROOT_WARN_FREE_KB
export WOLO_ALERT_ROOT_FAIL_FREE_KB
export WOLO_ALERT_EXTRA_PATH
export WOLO_ALERT_EXTRA_WARN_FREE_KB
export WOLO_ALERT_EXTRA_FAIL_FREE_KB
export HEALTH_CODE="$health_code"
export HEALTH_RC="$health_rc"
export DOCTOR_RC="$doctor_rc"
export DOCTOR_SKIPPED="$doctor_skipped"
export PAYOUT_KEY_RC="$payout_key_rc"
export ESCROW_KEY_RC="$escrow_key_rc"
export GROUPED_CODE="$grouped_code"
export GROUPED_RC="$grouped_rc"
export ESCROW_RECENT_CODE="$escrow_recent_code"
export ESCROW_RECENT_RC="$escrow_recent_rc"
export ESCROW_VERIFY_CODE="$escrow_verify_code"
export ESCROW_VERIFY_RC="$escrow_verify_rc"
export TMPDIR_ALERTS="$tmpdir"

python3 - <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

tmpdir = Path(os.environ["TMPDIR_ALERTS"])

def load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None

def load_text(path: Path):
    try:
        return path.read_text().strip()
    except Exception:
        return ""

def strip_known_noise(text: str):
    lines = []
    for line in (text or "").splitlines():
        if line.startswith("WARNING: sonic/ast only supports ") and "fallback to encoding/json" in line:
            continue
        lines.append(line)
    return "\n".join(lines).strip()

def summarize_cli_error(text: str):
    cleaned = strip_known_noise(text)
    if not cleaned:
        return ""
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[-1]

def parse_u64(value):
    try:
        if value is None:
            return None
        text = str(value).strip()
        if text == "":
            return None
        return int(text)
    except Exception:
        return None

def collect_filesystem(path_text: str, warn_kb: int, fail_kb: int):
    info = {
        "path": path_text,
        "warn_below_kb": warn_kb,
        "fail_below_kb": fail_kb,
    }
    try:
        stats = os.statvfs(path_text)
    except OSError as exc:
        info["status"] = "error"
        info["available_kb"] = None
        info["total_kb"] = None
        detail = f"path={path_text} unavailable: {exc}"
        return info, False, detail, "alert"

    total_kb = (stats.f_frsize * stats.f_blocks) // 1024
    available_kb = (stats.f_frsize * stats.f_bavail) // 1024
    info["available_kb"] = available_kb
    info["total_kb"] = total_kb

    if available_kb < fail_kb:
        info["status"] = "alert"
        ok = False
        severity = "alert"
    elif available_kb < warn_kb:
        info["status"] = "warn"
        ok = False
        severity = "warn"
    else:
        info["status"] = "ok"
        ok = True
        severity = "alert"

    detail = (
        f"path={path_text} available_kb={available_kb} total_kb={total_kb} "
        f"warn_below_kb={warn_kb} fail_below_kb={fail_kb}"
    )
    return info, ok, detail, severity

health = load_json(tmpdir / "health.json") or {}
doctor = load_json(tmpdir / "doctor.json") or {}

payout_key_address = load_text(tmpdir / "payout-key.txt")
escrow_key_address = load_text(tmpdir / "escrow-key.txt")
payout_key_error = summarize_cli_error(load_text(tmpdir / "payout-key.stderr"))
escrow_key_error = summarize_cli_error(load_text(tmpdir / "escrow-key.stderr"))
doctor_error = strip_known_noise(load_text(tmpdir / "doctor.stderr"))
health_error = strip_known_noise(load_text(tmpdir / "health.json.stderr"))
grouped_error = strip_known_noise(load_text(tmpdir / "grouped.json.stderr"))
escrow_recent_error = strip_known_noise(load_text(tmpdir / "escrow-recent.json.stderr"))
escrow_verify_error = strip_known_noise(load_text(tmpdir / "escrow-verify.json.stderr"))

def make_check(ok, detail, severity="alert", scope="live"):
    return {
        "ok": bool(ok),
        "severity": severity,
        "scope": scope,
        "detail": detail,
    }


def is_key_access_limited(detail: str) -> bool:
    text = (detail or "").lower()
    return (
        "permission denied" in text
        or "password is required" in text
        or "current user/sudo setup" in text
    )

checks = {}

health_code = os.environ["HEALTH_CODE"]
health_rc = int(os.environ["HEALTH_RC"])
grouped_code = os.environ["GROUPED_CODE"]
grouped_rc = int(os.environ["GROUPED_RC"])
escrow_recent_code = os.environ["ESCROW_RECENT_CODE"]
escrow_recent_rc = int(os.environ["ESCROW_RECENT_RC"])
escrow_verify_code = os.environ["ESCROW_VERIFY_CODE"]
escrow_verify_rc = int(os.environ["ESCROW_VERIFY_RC"])
doctor_rc = int(os.environ["DOCTOR_RC"])
doctor_skipped = os.environ["DOCTOR_SKIPPED"] == "1"
payout_key_rc = int(os.environ["PAYOUT_KEY_RC"])
escrow_key_rc = int(os.environ["ESCROW_KEY_RC"])
root_fs, root_fs_ok, root_fs_detail, root_fs_severity = collect_filesystem(
    os.environ["WOLO_ALERT_ROOT_PATH"],
    int(os.environ["WOLO_ALERT_ROOT_WARN_FREE_KB"]),
    int(os.environ["WOLO_ALERT_ROOT_FAIL_FREE_KB"]),
)
extra_fs, extra_fs_ok, extra_fs_detail, extra_fs_severity = collect_filesystem(
    os.environ["WOLO_ALERT_EXTRA_PATH"],
    int(os.environ["WOLO_ALERT_EXTRA_WARN_FREE_KB"]),
    int(os.environ["WOLO_ALERT_EXTRA_FAIL_FREE_KB"]),
)

service_reachable = health_rc == 0 and health_code != "000"
service_healthy = service_reachable and health_code == "200" and health.get("ok") is True

checks["service_reachable"] = make_check(
    service_reachable,
    (
        f"GET /settlement/v1/health returned HTTP {health_code}"
        + (f"; {health_error}" if health_rc != 0 and health_error else "")
    ),
    scope="live",
)

checks["service_healthy"] = make_check(
    service_healthy,
    (
        f"health ok={health.get('ok')} http={health_code}"
        + (
            f"; {health.get('failure_code')}: {health.get('detail')}"
            if health.get("detail")
            else ""
        )
        + (f"; {health_error}" if health_rc != 0 and health_error else "")
    ),
    scope="live",
)

checks["root_free_space"] = make_check(
    root_fs_ok,
    root_fs_detail,
    severity=root_fs_severity,
    scope="storage",
)

checks["extra_volume_free_space"] = make_check(
    extra_fs_ok,
    extra_fs_detail,
    severity=extra_fs_severity,
    scope="storage",
)

doctor_ok = doctor.get("ok") is True
doctor_detail = doctor.get("detail") or doctor_error or f"doctor rc={doctor_rc}"
if not doctor_skipped:
    checks["doctor_ok"] = make_check(doctor_ok, doctor_detail, scope="local")
    if doctor_ok:
        checks["doctor_ok"]["detail"] = "settlement doctor returned ok=true"

auth_enabled = doctor.get("auth_token_set") is True or health.get("auth_token_set") is True
checks["auth_enabled"] = make_check(
    auth_enabled,
    "auth_token_set=true" if auth_enabled else "settlement auth is off on the target service",
    scope="live",
)

payout_key_detail = payout_key_address if payout_key_rc == 0 and payout_key_address.startswith("wolo1") else (
    payout_key_error or (payout_key_address if payout_key_address else f"payout key lookup returned no usable address (rc={payout_key_rc})")
)
escrow_key_detail = escrow_key_address if escrow_key_rc == 0 and escrow_key_address.startswith("wolo1") else (
    escrow_key_error or (escrow_key_address if escrow_key_address else f"escrow key lookup returned no usable address (rc={escrow_key_rc})")
)

checks["payout_key_present"] = make_check(
    payout_key_rc == 0 and payout_key_address.startswith("wolo1"),
    payout_key_detail,
    severity="warn" if is_key_access_limited(payout_key_detail) else "alert",
    scope="operator",
)

checks["escrow_key_present"] = make_check(
    escrow_key_rc == 0 and escrow_key_address.startswith("wolo1"),
    escrow_key_detail,
    severity="warn" if is_key_access_limited(escrow_key_detail) else "alert",
    scope="operator",
)

payout_address = (health.get("payout_address") or doctor.get("payout_address") or os.environ.get("WOLO_SETTLEMENT_PAYOUT_ADDRESS") or "").strip()
escrow_address = (health.get("escrow_address") or doctor.get("escrow_address") or os.environ.get("WOLO_SETTLEMENT_ESCROW_ADDRESS") or "").strip()
distinct = bool(payout_address and escrow_address and payout_address != escrow_address)
checks["payout_escrow_distinct"] = make_check(
    distinct,
    "payout and escrow are distinct" if distinct else f"payout={payout_address or '<unset>'}, escrow={escrow_address or '<unset>'}",
    scope="live",
)

public_rest_url = (health.get("public_rest_url") or doctor.get("public_rest_url") or "").strip()
checks["public_proof_url_set"] = make_check(
    bool(public_rest_url),
    public_rest_url if public_rest_url else "WOLO_SETTLEMENT_PUBLIC_REST_URL is empty",
    scope="live",
)

balance = parse_u64(health.get("payout_balance_uwolo") or doctor.get("payout_balance_uwolo"))
reserve = parse_u64(health.get("min_payout_balance_uwolo") or doctor.get("min_payout_balance_uwolo"))
balance_ok = balance is not None and reserve is not None and balance >= reserve
balance_detail = "payout balance or reserve floor unavailable"
if balance is not None and reserve is not None:
    balance_detail = f"payout_balance_uwolo={balance}, min_payout_balance_uwolo={reserve}"
checks["payout_balance_meets_reserve"] = make_check(balance_ok, balance_detail, scope="live")

grouped_present = grouped_code in {"200", "400", "401", "409", "503"}
checks["grouped_routes_present"] = make_check(
    grouped_present,
    f"POST /settlement/v1/runs/validate returned HTTP {grouped_code}" + (f"; {grouped_error}" if grouped_rc != 0 and grouped_error else ""),
    scope="live",
)

escrow_recent_present = escrow_recent_code in {"200", "400", "409", "503"}
escrow_verify_present = escrow_verify_code in {"400", "503"}
checks["escrow_routes_present"] = make_check(
    escrow_recent_present and escrow_verify_present,
    f"recent={escrow_recent_code}, verify={escrow_verify_code}" + (
        f"; {escrow_recent_error or escrow_verify_error}".rstrip()
        if (escrow_recent_rc != 0 or escrow_verify_rc != 0) and (escrow_recent_error or escrow_verify_error)
        else ""
    ),
    scope="live",
)

warnings = doctor.get("warnings") or []

failures = [name for name, check in checks.items() if not check["ok"] and check["severity"] == "alert"]
warnings_only = [name for name, check in checks.items() if not check["ok"] and check["severity"] == "warn"]
failures_by_scope = {}
warnings_by_scope = {}
for name in failures:
    failures_by_scope.setdefault(checks[name]["scope"], []).append(name)
for name in warnings_only:
    warnings_by_scope.setdefault(checks[name]["scope"], []).append(name)
result = {
    "ok": len(failures) == 0,
    "status": "healthy" if len(failures) == 0 else "alert",
    "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "service_url": os.environ["SETTLEMENT_BASE_URL"],
    "config_source": os.environ["CONFIG_SOURCE"],
    "failure_count": len(failures),
    "warning_count": len(warnings_only),
    "failed_checks": failures,
    "warn_checks": warnings_only,
    "failed_checks_by_scope": failures_by_scope,
    "warn_checks_by_scope": warnings_by_scope,
    "checks": checks,
    "live_service": {
        "reachable": service_reachable,
        "healthy": service_healthy,
        "http_code": health_code,
        "ok": health.get("ok"),
        "failure_code": health.get("failure_code"),
        "detail": health.get("detail") or health_error or None,
    },
    "local_cli": {
        "checked": not doctor_skipped,
        "config_available": os.environ["HAS_INTENDED_CONFIG"] == "1",
        "doctor_rc": None if doctor_skipped else doctor_rc,
        "doctor_ok": None if doctor_skipped else doctor_ok,
        "detail": (
            "settlement doctor skipped because intended config is unavailable"
            if doctor_skipped
            else (doctor.get("detail") or doctor_error or None)
        ),
    },
    "doctor": {
        "ok": doctor.get("ok"),
        "failure_code": doctor.get("failure_code"),
        "detail": doctor.get("detail"),
        "chain_id": doctor.get("chain_id"),
        "runtime_chain_id": doctor.get("runtime_chain_id"),
        "payout_address": payout_address or None,
        "escrow_address": escrow_address or None,
        "public_rest_url": public_rest_url or None,
        "payout_balance_uwolo": health.get("payout_balance_uwolo") or doctor.get("payout_balance_uwolo"),
        "min_payout_balance_uwolo": health.get("min_payout_balance_uwolo") or doctor.get("min_payout_balance_uwolo"),
        "fee_headroom_uwolo": health.get("fee_headroom_uwolo") or doctor.get("fee_headroom_uwolo"),
        "escrow_signer_address": health.get("escrow_signer_address") or doctor.get("escrow_signer_address"),
        "escrow_balance_uwolo": health.get("escrow_balance_uwolo") or doctor.get("escrow_balance_uwolo"),
        "min_escrow_balance_uwolo": health.get("min_escrow_balance_uwolo") or doctor.get("min_escrow_balance_uwolo"),
        "escrow_fee_headroom_uwolo": health.get("escrow_fee_headroom_uwolo") or doctor.get("escrow_fee_headroom_uwolo"),
        "warnings": warnings,
        "warning_count": len(warnings),
    },
    "routes": {
        "health_code": health_code,
        "grouped_validate_code": grouped_code,
        "escrow_recent_code": escrow_recent_code,
        "escrow_verify_code": escrow_verify_code,
    },
    "storage": {
        "root": root_fs,
        "extra_volume": extra_fs,
    },
    "keys": {
        "payout_key_name": os.environ["WOLO_SETTLEMENT_PAYOUT_KEY_NAME"],
        "payout_key_address": payout_key_address or None,
        "escrow_key_name": os.environ["WOLO_SETTLEMENT_ESCROW_KEY_NAME"],
        "escrow_key_address": escrow_key_address or None,
    },
}

json.dump(result, sys.stdout, indent=2, sort_keys=True)
sys.stdout.write("\n")
sys.exit(0 if result["ok"] else 1)
PY
