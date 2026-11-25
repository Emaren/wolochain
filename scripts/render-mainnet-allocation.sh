#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

INPUT="mainnet-prep/genesis/allocation-template.csv"
OUTPUT="build/mainnet-prep/allocation-draft.json"
CHECK_ONLY=0

usage() {
  cat <<'EOF'
Usage: scripts/render-mainnet-allocation.sh [--check] [--input PATH] [--output PATH]

Validates the wolo-1 allocation CSV and, unless --check is set, writes a
draft allocation JSON under ignored build/ output.

This does not create final genesis, accounts, keys, wallets, or chain state.
EOF
}

while (($# > 0)); do
  case "$1" in
    --check)
      CHECK_ONLY=1
      shift
      ;;
    --input)
      INPUT="${2:-}"
      [[ -n "$INPUT" ]] || { echo "ERROR: --input requires a path" >&2; exit 1; }
      shift 2
      ;;
    --output)
      OUTPUT="${2:-}"
      [[ -n "$OUTPUT" ]] || { echo "ERROR: --output requires a path" >&2; exit 1; }
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

export WOLO_MAINNET_ALLOCATION_INPUT="$INPUT"
export WOLO_MAINNET_ALLOCATION_OUTPUT="$OUTPUT"
export WOLO_MAINNET_ALLOCATION_CHECK_ONLY="$CHECK_ONLY"
export WOLO_MAINNET_ALLOCATION_ROOT="$ROOT"

python3 - <<'PY'
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

CHAIN_ID = "wolo-1"
BASE_DENOM = "uwolo"
DISPLAY_DENOM = "wolo"
DECIMALS = 6
EXPECTED_SUPPLY_UWOLO = 100_000_000_000_000
EXPECTED_SUPPLY_WOLO = Decimal(EXPECTED_SUPPLY_UWOLO) / Decimal(10**DECIMALS)
REQUIRED_COLUMNS = {
    "bucket",
    "label",
    "address",
    "amount_wolo",
    "amount_uwolo",
    "custody",
    "genesis",
    "notes",
}
TESTNET_LEAK_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"wolo-testnet",
        r"wolochaind-testnet",
        r"/var/lib/wolochaind-testnet",
        r"wolochain-settlement[.]service",
        r"/mnt/HC_Volume_105319120/wolochain/settlement-state",
        r"rpc[.]aoe2hdbets[.]com",
        r"rest[.]aoe2hdbets[.]com",
        r"explorer[.]testnet[.]aoe2hdbets[.]com",
        r"\bfaucetgrowth\b",
        r"\bfoundercold\b",
        r"\bfounderoperating\b",
        r"\bvalidatorops\b",
        r"\bdexliquidity\b",
        r"\becosystembounties\b",
    ]
]


def as_root_path(root: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def display_wolo(amount_uwolo: int) -> str:
    value = Decimal(amount_uwolo) / Decimal(10**DECIMALS)
    return format(value.normalize(), "f")


def parse_amount_uwolo(raw: str, row_label: str, errors: list[str]) -> int:
    value = raw.strip()
    if not re.fullmatch(r"[0-9]+", value):
        errors.append(f"{row_label}: amount_uwolo must be a non-negative integer string")
        return 0
    return int(value)


def validate_amount_wolo(raw: str, amount_uwolo: int, row_label: str, errors: list[str]) -> str:
    value = raw.strip()
    if value == "":
        errors.append(f"{row_label}: amount_wolo is required")
        return ""
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        errors.append(f"{row_label}: amount_wolo is not numeric")
        return value
    if parsed < 0:
        errors.append(f"{row_label}: amount_wolo must not be negative")
    expected = Decimal(amount_uwolo) / Decimal(10**DECIMALS)
    if parsed != expected:
        errors.append(f"{row_label}: amount_wolo {value} does not match amount_uwolo {amount_uwolo}")
    return value


def is_placeholder(address: str) -> bool:
    return "REPLACE" in address.upper() or "_" in address


def validate_address(address: str, row_label: str, errors: list[str], warnings: list[str]) -> bool:
    if not address:
        errors.append(f"{row_label}: address placeholder or real wolo1 address is required")
        return False
    if is_placeholder(address):
        if not re.fullmatch(r"wolo1_REPLACE(_ME)?[A-Z0-9_]*", address):
            errors.append(f"{row_label}: placeholder must be clearly marked like wolo1_REPLACE_ME_BUCKET")
        warnings.append(f"{row_label}: address is a placeholder, not a real mainnet address")
        return True
    if not address.startswith("wolo1"):
        errors.append(f"{row_label}: real address must start with wolo1")
        return False
    if address != address.lower():
        errors.append(f"{row_label}: real bech32 address must be lowercase")
    return False


def scan_testnet_leaks(row: dict[str, str], row_label: str, errors: list[str]) -> None:
    text = " ".join(str(value) for value in row.values())
    for pattern in TESTNET_LEAK_PATTERNS:
        if pattern.search(text):
            errors.append(f"{row_label}: contains testnet-only name/path/service/endpoint matching {pattern.pattern}")


root = Path(os.environ["WOLO_MAINNET_ALLOCATION_ROOT"]).resolve()
input_path = as_root_path(root, os.environ["WOLO_MAINNET_ALLOCATION_INPUT"])
output_path = as_root_path(root, os.environ["WOLO_MAINNET_ALLOCATION_OUTPUT"])
check_only = os.environ["WOLO_MAINNET_ALLOCATION_CHECK_ONLY"] == "1"

try:
    input_path.relative_to(root)
except ValueError:
    raise SystemExit(f"ERROR: input path must be inside prep clone: {input_path}")

if not input_path.is_file():
    raise SystemExit(f"ERROR: allocation CSV does not exist: {input_path}")

if not check_only:
    try:
        output_path.relative_to(root / "build")
    except ValueError:
        raise SystemExit(f"ERROR: output path must be under ignored build/: {output_path}")

errors: list[str] = []
warnings: list[str] = []

with input_path.open(newline="") as handle:
    reader = csv.DictReader(handle)
    fieldnames = set(reader.fieldnames or [])
    missing = sorted(REQUIRED_COLUMNS - fieldnames)
    if missing:
        errors.append(f"allocation CSV missing required columns: {', '.join(missing)}")
    rows = list(reader)

if not rows:
    errors.append("allocation CSV is empty")

seen_buckets: set[str] = set()
allocations = []
total_rows = []
total_uwolo = 0

for index, row in enumerate(rows, start=2):
    bucket = (row.get("bucket") or "").strip()
    row_label = bucket or f"line {index}"
    if not bucket:
        errors.append(f"line {index}: bucket is required")
        continue
    if bucket in seen_buckets:
        errors.append(f"{row_label}: duplicate bucket")
    seen_buckets.add(bucket)

    label = (row.get("label") or "").strip()
    notes = (row.get("notes") or "").strip()
    address = (row.get("address") or "").strip()
    custody = (row.get("custody") or "").strip()
    genesis = (row.get("genesis") or "").strip().lower()

    amount_uwolo = parse_amount_uwolo(row.get("amount_uwolo") or "", row_label, errors)
    amount_wolo = validate_amount_wolo(row.get("amount_wolo") or "", amount_uwolo, row_label, errors)

    if not label:
        errors.append(f"{row_label}: label/name is required")
    if not notes:
        errors.append(f"{row_label}: notes are required")
    if genesis not in {"yes", "no"}:
        errors.append(f"{row_label}: genesis must be yes or no")
    scan_testnet_leaks(row, row_label, errors)

    if bucket == "TOTAL":
        total_rows.append(row)
        if address:
            warnings.append("TOTAL: address is ignored for summary rows")
        continue

    if not custody:
        errors.append(f"{row_label}: custody is required")
    placeholder = validate_address(address, row_label, errors, warnings)
    total_uwolo += amount_uwolo
    allocations.append(
        {
            "bucket": bucket,
            "name": label,
            "address_or_placeholder": address,
            "is_placeholder": placeholder,
            "amount_uwolo": str(amount_uwolo),
            "amount_wolo": amount_wolo or display_wolo(amount_uwolo),
            "custody": custody,
            "genesis": genesis == "yes",
            "notes": notes,
        }
    )

if len(total_rows) != 1:
    errors.append("allocation CSV must include exactly one TOTAL row")
else:
    declared = parse_amount_uwolo(total_rows[0].get("amount_uwolo") or "", "TOTAL", errors)
    if declared != EXPECTED_SUPPLY_UWOLO:
        errors.append(f"TOTAL row amount_uwolo {declared} does not match expected {EXPECTED_SUPPLY_UWOLO}")

if total_uwolo != EXPECTED_SUPPLY_UWOLO:
    errors.append(f"allocation rows sum to {total_uwolo}, expected {EXPECTED_SUPPLY_UWOLO}")

if errors:
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    raise SystemExit(1)

status = "ok_with_warnings" if warnings else "ok"
payload = {
    "chain_id": CHAIN_ID,
    "base_denom": BASE_DENOM,
    "display_denom": DISPLAY_DENOM,
    "decimals": DECIMALS,
    "total_supply_uwolo": str(EXPECTED_SUPPLY_UWOLO),
    "total_supply_wolo": display_wolo(EXPECTED_SUPPLY_UWOLO),
    "source_csv": str(input_path.relative_to(root)),
    "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "artifact_status": "draft_only_not_genesis",
    "validation": {
        "status": status,
        "errors": [],
        "warnings": warnings,
    },
    "allocations": allocations,
}

if check_only:
    print(
        f"OK: allocation template valid; total={EXPECTED_SUPPLY_UWOLO}uwolo; "
        f"rows={len(allocations)}; warnings={len(warnings)}"
    )
else:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote draft allocation JSON: {output_path.relative_to(root)}")
    print(f"Total allocation: {EXPECTED_SUPPLY_UWOLO}uwolo ({display_wolo(EXPECTED_SUPPLY_UWOLO)} WOLO)")
    if warnings:
        print(f"Warnings: {len(warnings)} placeholder/review warning(s)")
PY
