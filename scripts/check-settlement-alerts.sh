#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
WOLOCHAIND_BIN="${WOLOCHAIND_BIN:-$ROOT_DIR/build/wolochaind}"
SETTLEMENT_ENV_FILE="${SETTLEMENT_ENV_FILE:-}"
SETTLEMENT_BASE_URL="${SETTLEMENT_BASE_URL:-http://127.0.0.1:8091}"
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
WOLO_SETTLEMENT_AUTH_TOKEN="${WOLO_SETTLEMENT_AUTH_TOKEN:-}"

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

have() {
  command -v "$1" >/dev/null 2>&1
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
      WOLO_SETTLEMENT_AUTH_TOKEN="$WOLO_SETTLEMENT_AUTH_TOKEN" \
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
    WOLO_SETTLEMENT_AUTH_TOKEN="$WOLO_SETTLEMENT_AUTH_TOKEN" \
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

health_code="000"
health_rc=1
if health_code="$(http_request GET "$SETTLEMENT_BASE_URL/settlement/v1/health" "$tmpdir/health.json")"; then
  health_rc=0
fi

doctor_rc=0
if ! run_wolochaind settlement doctor >"$tmpdir/doctor.json" 2>"$tmpdir/doctor.stderr"; then
  doctor_rc=$?
fi

payout_key_rc=0
if ! key_address "$WOLO_SETTLEMENT_PAYOUT_KEY_NAME" >"$tmpdir/payout-key.txt" 2>"$tmpdir/payout-key.stderr"; then
  payout_key_rc=$?
fi

escrow_key_rc=0
if ! key_address "$WOLO_SETTLEMENT_ESCROW_KEY_NAME" >"$tmpdir/escrow-key.txt" 2>"$tmpdir/escrow-key.stderr"; then
  escrow_key_rc=$?
fi

payout_address="$(sed -n 's/.*"payout_address":[[:space:]]*"\([^"]*\)".*/\1/p' "$tmpdir/health.json" | head -n 1)"
if [[ -z "$payout_address" ]]; then
  payout_address="${WOLO_SETTLEMENT_PAYOUT_ADDRESS:-wolo1jx4n3n2ey6uzfq28kplkmpd2am98xsmcn0nerx}"
fi

run_body="$tmpdir/run.json"
cat >"$run_body" <<EOF
{
  "settlement_run_id": "alert-check-run",
  "source_app": "settlement-alert-check",
  "source_event_id": "alert-check",
  "note": "dry-run only",
  "memo": "dry-run alert",
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
export WOLO_SETTLEMENT_PAYOUT_KEY_NAME
export WOLO_SETTLEMENT_ESCROW_KEY_NAME
export WOLO_SETTLEMENT_PAYOUT_ADDRESS
export WOLO_SETTLEMENT_ESCROW_ADDRESS
export HEALTH_CODE="$health_code"
export HEALTH_RC="$health_rc"
export DOCTOR_RC="$doctor_rc"
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

health = load_json(tmpdir / "health.json") or {}
doctor = load_json(tmpdir / "doctor.json") or {}

payout_key_address = load_text(tmpdir / "payout-key.txt")
escrow_key_address = load_text(tmpdir / "escrow-key.txt")
payout_key_error = load_text(tmpdir / "payout-key.stderr")
escrow_key_error = load_text(tmpdir / "escrow-key.stderr")
doctor_error = load_text(tmpdir / "doctor.stderr")
health_error = load_text(tmpdir / "health.json.stderr")
grouped_error = load_text(tmpdir / "grouped.json.stderr")
escrow_recent_error = load_text(tmpdir / "escrow-recent.json.stderr")
escrow_verify_error = load_text(tmpdir / "escrow-verify.json.stderr")

def make_check(ok, detail, severity="alert"):
    return {"ok": bool(ok), "severity": severity, "detail": detail}


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
payout_key_rc = int(os.environ["PAYOUT_KEY_RC"])
escrow_key_rc = int(os.environ["ESCROW_KEY_RC"])

checks["service_reachable"] = make_check(
    health_code == "200",
    f"GET /settlement/v1/health returned HTTP {health_code}" + (f"; {health_error}" if health_rc != 0 and health_error else ""),
)

doctor_ok = doctor.get("ok") is True
doctor_detail = doctor.get("detail") or doctor_error or f"doctor rc={doctor_rc}"
checks["doctor_ok"] = make_check(doctor_ok, doctor_detail)
if doctor_ok:
    checks["doctor_ok"]["detail"] = "settlement doctor returned ok=true"

auth_enabled = doctor.get("auth_token_set") is True or health.get("auth_token_set") is True
checks["auth_enabled"] = make_check(
    auth_enabled,
    "auth_token_set=true" if auth_enabled else "settlement auth is off on the target service",
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
)

checks["escrow_key_present"] = make_check(
    escrow_key_rc == 0 and escrow_key_address.startswith("wolo1"),
    escrow_key_detail,
    severity="warn" if is_key_access_limited(escrow_key_detail) else "alert",
)

payout_address = (health.get("payout_address") or doctor.get("payout_address") or os.environ.get("WOLO_SETTLEMENT_PAYOUT_ADDRESS") or "").strip()
escrow_address = (health.get("escrow_address") or doctor.get("escrow_address") or os.environ.get("WOLO_SETTLEMENT_ESCROW_ADDRESS") or "").strip()
distinct = bool(payout_address and escrow_address and payout_address != escrow_address)
checks["payout_escrow_distinct"] = make_check(
    distinct,
    "payout and escrow are distinct" if distinct else f"payout={payout_address or '<unset>'}, escrow={escrow_address or '<unset>'}",
)

public_rest_url = (health.get("public_rest_url") or doctor.get("public_rest_url") or "").strip()
checks["public_proof_url_set"] = make_check(
    bool(public_rest_url),
    public_rest_url if public_rest_url else "WOLO_SETTLEMENT_PUBLIC_REST_URL is empty",
)

balance = parse_u64(health.get("payout_balance_uwolo") or doctor.get("payout_balance_uwolo"))
reserve = parse_u64(health.get("min_payout_balance_uwolo") or doctor.get("min_payout_balance_uwolo"))
balance_ok = balance is not None and reserve is not None and balance >= reserve
balance_detail = "payout balance or reserve floor unavailable"
if balance is not None and reserve is not None:
    balance_detail = f"payout_balance_uwolo={balance}, min_payout_balance_uwolo={reserve}"
checks["payout_balance_meets_reserve"] = make_check(balance_ok, balance_detail)

grouped_present = grouped_code in {"200", "400", "401", "409"}
checks["grouped_routes_present"] = make_check(
    grouped_present,
    f"POST /settlement/v1/runs/validate returned HTTP {grouped_code}" + (f"; {grouped_error}" if grouped_rc != 0 and grouped_error else ""),
)

escrow_recent_present = escrow_recent_code in {"200", "400", "409", "503"}
escrow_verify_present = escrow_verify_code == "400"
checks["escrow_routes_present"] = make_check(
    escrow_recent_present and escrow_verify_present,
    f"recent={escrow_recent_code}, verify={escrow_verify_code}" + (
        f"; {escrow_recent_error or escrow_verify_error}".rstrip()
        if (escrow_recent_rc != 0 or escrow_verify_rc != 0) and (escrow_recent_error or escrow_verify_error)
        else ""
    ),
)

warnings = doctor.get("warnings") or []
checks["warning_free"] = make_check(
    len(warnings) == 0,
    "no doctor warnings" if not warnings else "; ".join(str(w) for w in warnings),
    severity="warn",
)

failures = [name for name, check in checks.items() if not check["ok"] and check["severity"] == "alert"]
warnings_only = [name for name, check in checks.items() if not check["ok"] and check["severity"] == "warn"]
result = {
    "ok": len(failures) == 0,
    "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "service_url": os.environ["SETTLEMENT_BASE_URL"],
    "failure_count": len(failures),
    "warning_count": len(warnings_only),
    "failed_checks": failures,
    "warn_checks": warnings_only,
    "checks": checks,
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
        "warnings": warnings,
    },
    "routes": {
        "health_code": health_code,
        "grouped_validate_code": grouped_code,
        "escrow_recent_code": escrow_recent_code,
        "escrow_verify_code": escrow_verify_code,
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
