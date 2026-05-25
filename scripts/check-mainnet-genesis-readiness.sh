#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ALLOCATION_JSON="build/mainnet-prep/allocation-draft.json"
REPORT_JSON="build/mainnet-prep/genesis-readiness-report.json"
STRICT=0

usage() {
  cat <<'EOF'
Usage: scripts/check-mainnet-genesis-readiness.sh [--strict] [--allocation-json PATH] [--report PATH]

Generates a read-only readiness report for a future wolo-1 genesis-generation
step. This does not create final genesis, accounts, keys, wallets, or chain
state.

By default, readiness blockers are reported in JSON while the command exits 0.
Use --strict to exit 1 when ready_for_genesis is false.
EOF
}

while (($# > 0)); do
  case "$1" in
    --strict)
      STRICT=1
      shift
      ;;
    --allocation-json)
      ALLOCATION_JSON="${2:-}"
      [[ -n "$ALLOCATION_JSON" ]] || { echo "ERROR: --allocation-json requires a path" >&2; exit 1; }
      shift 2
      ;;
    --report)
      REPORT_JSON="${2:-}"
      [[ -n "$REPORT_JSON" ]] || { echo "ERROR: --report requires a path" >&2; exit 1; }
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

case "$ALLOCATION_JSON" in
  build/*)
    ;;
  *)
    echo "ERROR: allocation JSON output must be under ignored build/: $ALLOCATION_JSON" >&2
    exit 1
    ;;
esac

case "$REPORT_JSON" in
  build/*)
    ;;
  *)
    echo "ERROR: readiness report must be under ignored build/: $REPORT_JSON" >&2
    exit 1
    ;;
esac

./scripts/render-mainnet-allocation.sh --output "$ALLOCATION_JSON"

export WOLO_MAINNET_READINESS_ROOT="$ROOT"
export WOLO_MAINNET_READINESS_ALLOCATION_JSON="$ALLOCATION_JSON"
export WOLO_MAINNET_READINESS_REPORT_JSON="$REPORT_JSON"

python3 - <<'PY'
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

EXPECTED = {
    "chain_id": "wolo-1",
    "base_denom": "uwolo",
    "display_denom": "wolo",
    "symbol": "WOLO",
    "decimals": 6,
    "prefix": "wolo",
    "total_supply_uwolo": "100000000000000",
    "total_supply_wolo": "100000000",
}

REQUIRED_BUCKETS = {
    "founder_cold": "founder cold reserve",
    "founder_operating": "founder operating wallet",
    "community_treasury": "community treasury",
    "dex_liquidity_reserve": "DEX liquidity reserve",
    "faucet_growth_reserve": "faucet growth reserve",
    "faucet_hot_wallet": "faucet hot wallet",
    "validator_ops": "validator ops",
    "ecosystem_bounties": "ecosystem bounties",
}

STALE_ENDPOINT_RE = re.compile(
    r"rpc[.]aoe2hdbets[.]com|rest[.]aoe2hdbets[.]com|explorer[.]testnet[.]aoe2hdbets[.]com",
    re.IGNORECASE,
)
TESTNET_RUNTIME_RE = re.compile(
    r"wolo-testnet|/var/lib/wolochaind-testnet|wolochaind-testnet[.]service|"
    r"wolochain-settlement[.]service|127[.]0[.]0[.]1:26656|127[.]0[.]0[.]1:26657|"
    r"127[.]0[.]0[.]1:1317|127[.]0[.]0[.]1:8091|"
    r"/mnt/HC_Volume_105319120/wolochain/settlement-state",
    re.IGNORECASE,
)


def rel(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root))


def read_text(path: Path) -> str:
    return path.read_text()


def require_text(path: Path, needle: str, label: str, blockers: list[str]) -> None:
    if needle not in read_text(path):
        blockers.append(f"missing {label}: {needle} in {path}")


def scan_file(path: Path, pattern: re.Pattern[str], label: str, blockers: list[str]) -> None:
    text = read_text(path)
    for match in pattern.finditer(text):
        blockers.append(f"{label} in {path}: {match.group(0)}")


root = Path(os.environ["WOLO_MAINNET_READINESS_ROOT"]).resolve()
allocation_json = (root / os.environ["WOLO_MAINNET_READINESS_ALLOCATION_JSON"]).resolve()
report_json = (root / os.environ["WOLO_MAINNET_READINESS_REPORT_JSON"]).resolve()

for path in (allocation_json, report_json):
    try:
        path.relative_to(root)
    except ValueError:
        raise SystemExit(f"ERROR: path escapes prep clone: {path}")

try:
    report_json.relative_to(root / "build")
except ValueError:
    raise SystemExit(f"ERROR: report path must be under build/: {report_json}")

blockers: list[str] = []
warnings: list[str] = []
checked_files: list[str] = []

required_files = [
    root / "mainnet-prep/genesis/allocation-template.csv",
    allocation_json,
    root / "mainnet-prep/config/wolo-1-values.env.example",
    root / "mainnet-prep/config/wolo-1-node.env.example",
    root / "mainnet-prep/config/wolo-1-settlement.env.example",
    root / "mainnet-prep/systemd/wolochaind-mainnet.service.example",
    root / "mainnet-prep/systemd/wolochain-mainnet-settlement.service.example",
    root / "docs/mainnet-decision-checklist.md",
    root / "docs/mainnet-services-and-ports.md",
    root / "docs/mainnet-keplr-explorer.md",
]

for path in required_files:
    if not path.is_file():
        blockers.append(f"missing required file: {rel(path, root)}")
    else:
        checked_files.append(rel(path, root))

if allocation_json.is_file():
    allocation = json.loads(allocation_json.read_text())
else:
    allocation = {}

allocations = allocation.get("allocations") or []
allocation_total_uwolo = str(allocation.get("total_supply_uwolo") or "")
allocation_total_wolo = str(allocation.get("total_supply_wolo") or "")

for key in ("chain_id", "base_denom", "display_denom", "decimals", "total_supply_uwolo", "total_supply_wolo"):
    actual = allocation.get(key)
    if actual != EXPECTED[key]:
        blockers.append(f"allocation draft {key}={actual!r}, expected {EXPECTED[key]!r}")

values_env = root / "mainnet-prep/config/wolo-1-values.env.example"
node_env = root / "mainnet-prep/config/wolo-1-node.env.example"
settlement_env = root / "mainnet-prep/config/wolo-1-settlement.env.example"
node_service = root / "mainnet-prep/systemd/wolochaind-mainnet.service.example"
settlement_service = root / "mainnet-prep/systemd/wolochain-mainnet-settlement.service.example"

if values_env.is_file():
    expected_values = {
        "chain id": "WOLO_MAINNET_CHAIN_ID=wolo-1",
        "base denom": "WOLO_MAINNET_BASE_DENOM=uwolo",
        "display denom": "WOLO_MAINNET_DISPLAY_DENOM=wolo",
        "symbol": "WOLO_MAINNET_SYMBOL=WOLO",
        "decimals": "WOLO_MAINNET_DECIMALS=6",
        "prefix": "WOLO_MAINNET_ADDRESS_PREFIX=wolo",
        "supply": "WOLO_MAINNET_TOTAL_SUPPLY_UWOLO=100000000000000",
        "node service": "WOLO_MAINNET_NODE_SERVICE=wolochaind-mainnet.service",
        "settlement service": "WOLO_MAINNET_SETTLEMENT_SERVICE=wolochain-mainnet-settlement.service",
        "p2p port": "WOLO_MAINNET_P2P_PORT=27656",
        "rpc port": "WOLO_MAINNET_RPC_PORT=27657",
        "rest port": "WOLO_MAINNET_REST_PORT=1318",
        "settlement port": "WOLO_MAINNET_SETTLEMENT_PORT=8092",
    }
    for label, needle in expected_values.items():
        require_text(values_env, needle, label, blockers)

if node_env.is_file():
    for label, needle in {
        "node chain id": "CHAIN_ID=wolo-1",
        "node home": "WOLO_HOME=/var/lib/wolochaind-mainnet",
        "p2p bind": "tcp://0.0.0.0:27656",
        "rpc bind": "tcp://127.0.0.1:27657",
        "rest bind": "tcp://127.0.0.1:1318",
    }.items():
        require_text(node_env, needle, label, blockers)

if settlement_env.is_file():
    for label, needle in {
        "settlement chain id": "WOLO_SETTLEMENT_CHAIN_ID=wolo-1",
        "settlement rpc": "WOLO_SETTLEMENT_RPC_HTTP=http://127.0.0.1:27657",
        "settlement rest": "WOLO_SETTLEMENT_REST_URL=http://127.0.0.1:1318",
        "settlement bind": "WOLO_SETTLEMENT_LISTEN_ADDR=127.0.0.1:8092",
        "settlement state": "WOLO_SETTLEMENT_STATE_DIR=/mnt/HC_Volume_105319120/wolochain-mainnet/settlement-state",
    }.items():
        require_text(settlement_env, needle, label, blockers)

if node_service.is_file():
    require_text(node_service, "ExecStart=/var/www/WoloChain-mainnet/build/wolochaind start", "mainnet node service exec", blockers)

if settlement_service.is_file():
    require_text(settlement_service, "Description=WoloChain mainnet settlement service", "mainnet settlement service description", blockers)
    require_text(settlement_service, "Requires=wolochaind-mainnet.service", "mainnet settlement service dependency", blockers)

runtime_template_files = [
    path
    for path in [
        values_env,
        node_env,
        settlement_env,
        node_service,
        settlement_service,
        root / "mainnet-prep/genesis/allocation-template.csv",
    ]
    if path.is_file()
]
for path in runtime_template_files:
    scan_file(path, STALE_ENDPOINT_RE, "stale old Wolo endpoint", blockers)
    scan_file(path, TESTNET_RUNTIME_RE, "testnet runtime reference in mainnet template", blockers)

bucket_keys = {row.get("bucket") for row in allocations}
required_present = [
    {"bucket": bucket, "label": label}
    for bucket, label in REQUIRED_BUCKETS.items()
    if bucket in bucket_keys
]
required_missing = [
    {"bucket": bucket, "label": label}
    for bucket, label in REQUIRED_BUCKETS.items()
    if bucket not in bucket_keys
]
for item in required_missing:
    blockers.append(f"missing required allocation bucket: {item['bucket']} ({item['label']})")

placeholder_count = 0
real_address_count = 0
for row in allocations:
    address = str(row.get("address_or_placeholder") or "")
    bucket = row.get("bucket") or "<unknown>"
    if not address:
        blockers.append(f"{bucket}: address is empty")
        continue
    if row.get("is_placeholder") is True:
        placeholder_count += 1
        if not re.fullmatch(r"wolo1_REPLACE(_ME)?[A-Z0-9_]*", address):
            blockers.append(f"{bucket}: placeholder is not clearly marked: {address}")
        continue
    real_address_count += 1
    if not address.startswith("wolo1"):
        blockers.append(f"{bucket}: real address does not start with wolo1: {address}")

if placeholder_count:
    blockers.append(f"{placeholder_count} allocation address placeholder(s) remain")

warnings.extend(allocation.get("validation", {}).get("warnings") or [])
if real_address_count == 0:
    warnings.append("no real mainnet allocation addresses are present yet")

ready_for_genesis = len(blockers) == 0

report = {
    "ready_for_genesis": ready_for_genesis,
    "chain_id": EXPECTED["chain_id"],
    "base_denom": EXPECTED["base_denom"],
    "display_denom": EXPECTED["display_denom"],
    "symbol": EXPECTED["symbol"],
    "decimals": EXPECTED["decimals"],
    "prefix": EXPECTED["prefix"],
    "allocation_total_uwolo": allocation_total_uwolo,
    "allocation_total_wolo": allocation_total_wolo,
    "placeholder_count": placeholder_count,
    "real_address_count": real_address_count,
    "required_buckets_present": required_present,
    "required_buckets_missing": required_missing,
    "blockers": blockers,
    "warnings": warnings,
    "checked_files": checked_files,
    "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "artifact_status": "readiness_report_only_not_genesis",
}

report_json.parent.mkdir(parents=True, exist_ok=True)
report_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

print(f"Genesis readiness: {str(ready_for_genesis).lower()}")
print(f"Report: {rel(report_json, root)}")
print(f"Allocation total: {allocation_total_uwolo}uwolo ({allocation_total_wolo} WOLO)")
print(f"Placeholders: {placeholder_count}; real addresses: {real_address_count}")
print(f"Required buckets present: {len(required_present)}; missing: {len(required_missing)}")
if blockers:
    print("Blockers:")
    for blocker in blockers:
        print(f"  - {blocker}")
else:
    print("Blockers: none")
if warnings:
    print("Warnings:")
    for warning in warnings:
        print(f"  - {warning}")
else:
    print("Warnings: none")
PY

if [[ "$STRICT" == "1" ]]; then
  export WOLO_MAINNET_READINESS_STRICT_REPORT="$REPORT_JSON"
  ready="$(python3 - <<'PY'
import json
import os
from pathlib import Path
report = json.loads(Path(os.environ["WOLO_MAINNET_READINESS_STRICT_REPORT"]).read_text())
print("1" if report.get("ready_for_genesis") else "0")
PY
)"
  if [[ "$ready" != "1" ]]; then
    exit 1
  fi
fi
