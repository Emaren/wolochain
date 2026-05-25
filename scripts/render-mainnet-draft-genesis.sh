#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ALLOC_JSON="build/mainnet-prep/allocation-draft.json"
OUT_JSON="build/mainnet-prep/genesis-allocation.draft.json"
REPORT_JSON="build/mainnet-prep/genesis-allocation-draft-report.json"

./scripts/render-mainnet-allocation.sh --output "$ALLOC_JSON"
./scripts/check-mainnet-genesis-readiness.sh >/dev/null

python3 - <<'PY'
import json
from pathlib import Path
from datetime import datetime, timezone

root = Path(".").resolve()
alloc_path = root / "build/mainnet-prep/allocation-draft.json"
out_path = root / "build/mainnet-prep/genesis-allocation.draft.json"
report_path = root / "build/mainnet-prep/genesis-allocation-draft-report.json"

allocation = json.loads(alloc_path.read_text())
rows = allocation["allocations"]

expected_total = 100_000_000_000_000
total = sum(int(row["amount_uwolo"]) for row in rows)

errors = []
if allocation.get("chain_id") != "wolo-1":
    errors.append(f"chain_id is {allocation.get('chain_id')}, expected wolo-1")
if allocation.get("base_denom") != "uwolo":
    errors.append(f"base_denom is {allocation.get('base_denom')}, expected uwolo")
if str(allocation.get("total_supply_uwolo")) != str(expected_total):
    errors.append(f"allocation total_supply_uwolo is {allocation.get('total_supply_uwolo')}, expected {expected_total}")
if total != expected_total:
    errors.append(f"row sum is {total}, expected {expected_total}")

seen = set()
balances = []
for row in rows:
    bucket = row["bucket"]
    address = row.get("address") or row.get("address_or_placeholder")
    amount = str(row["amount_uwolo"])

    if not address:
        errors.append(f"{bucket}: missing address")
        continue
    if not address.startswith("wolo1"):
        errors.append(f"{bucket}: address does not start with wolo1: {address}")
    if "REPLACE" in address:
        errors.append(f"{bucket}: placeholder address remains: {address}")
    if address in seen:
        errors.append(f"{bucket}: duplicate address: {address}")
    seen.add(address)

    balances.append({
        "bucket": bucket,
        "label": row.get("label") or row.get("name") or bucket,
        "address": address,
        "coins": [{"denom": "uwolo", "amount": amount}],
        "amount_wolo": str(row.get("amount_wolo") or ""),
        "custody": row.get("custody") or "",
        "genesis": row.get("genesis") or "",
        "notes": row.get("notes") or "",
    })

draft = {
    "artifact_status": "draft_allocation_only_not_final_genesis",
    "warning": "This is NOT final genesis. It contains allocation/bank-balance intent only. It does not include validator gentx, final app_state, node keys, or launch installation.",
    "chain_id": "wolo-1",
    "base_denom": "uwolo",
    "display_denom": "wolo",
    "symbol": "WOLO",
    "decimals": 6,
    "address_prefix": "wolo",
    "total_supply_uwolo": str(expected_total),
    "total_supply_wolo": "100000000",
    "denom_metadata": {
        "description": "WOLO is the fixed-supply native token of WoloChain.",
        "denom_units": [
            {"denom": "uwolo", "exponent": 0, "aliases": ["microWOLO"]},
            {"denom": "wolo", "exponent": 6},
        ],
        "base": "uwolo",
        "display": "wolo",
        "name": "WOLO",
        "symbol": "WOLO",
    },
    "staking": {"bond_denom": "uwolo"},
    "mint": {
        "mint_denom": "uwolo",
        "inflation": "0.000000000000000000",
        "annual_provisions": "0.000000000000000000",
    },
    "balances": balances,
    "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
}

report = {
    "ok": not errors,
    "errors": errors,
    "balance_count": len(balances),
    "unique_address_count": len(seen),
    "total_uwolo": str(total),
    "total_wolo": str(total // 1_000_000),
    "draft_path": str(out_path.relative_to(root)),
    "artifact_status": "report_only_not_final_genesis",
    "generated_at": draft["generated_at"],
}

out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(draft, indent=2, sort_keys=True) + "\n")
report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

print(f"Wrote draft allocation genesis: {out_path.relative_to(root)}")
print(f"Wrote report: {report_path.relative_to(root)}")
print(f"OK: {report['ok']}")
print(f"Balances: {report['balance_count']}")
print(f"Unique addresses: {report['unique_address_count']}")
print(f"Total: {report['total_uwolo']}uwolo ({report['total_wolo']} WOLO)")

if errors:
    print("Errors:")
    for err in errors:
        print(f"  - {err}")
    raise SystemExit(1)
PY
