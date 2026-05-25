#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BIN="$ROOT/build/wolochaind"
HOME_DIR="$ROOT/build/mainnet-prep/wolo-1-home"
ALLOC_JSON="$ROOT/build/mainnet-prep/allocation-draft.json"
GENESIS="$HOME_DIR/config/genesis.json"
REPORT="$ROOT/build/mainnet-prep/wolo-1-draft-home-report.json"

CHAIN_ID="wolo-1"
MONIKER="wolo-mainnet-draft"
EXPECTED_SUPPLY="100000000000000"

PATH="/opt/homebrew/opt/go@1.24/bin:$PATH"

echo "== build binary =="
go build -o "$BIN" ./cmd/wolochaind

echo
echo "== verify allocation readiness =="
./scripts/render-mainnet-allocation.sh --output "$ALLOC_JSON"
./scripts/check-mainnet-genesis-readiness.sh --strict

echo
echo "== reset draft home under build only =="
case "$HOME_DIR" in
  "$ROOT"/build/*) ;;
  *) echo "STOP: HOME_DIR must be under build/: $HOME_DIR" >&2; exit 1 ;;
esac
rm -rf "$HOME_DIR"
mkdir -p "$HOME_DIR"

echo
echo "== init draft chain home =="
"$BIN" init "$MONIKER" --chain-id "$CHAIN_ID" --home "$HOME_DIR" >/dev/null

echo
echo "== patch draft genesis params =="
export GENESIS
python3 - <<'PY'
import json
from pathlib import Path
import os

genesis = Path(os.environ["GENESIS"])
g = json.loads(genesis.read_text())

g["chain_id"] = "wolo-1"
app = g["app_state"]

if "staking" in app and "params" in app["staking"]:
    app["staking"]["params"]["bond_denom"] = "uwolo"

if "mint" in app:
    params = app["mint"].setdefault("params", {})
    params["mint_denom"] = "uwolo"
    for k in ("inflation_rate_change", "inflation_max", "inflation_min"):
        if k in params:
            params[k] = "0.000000000000000000"
    minter = app["mint"].setdefault("minter", {})
    for k in ("inflation", "annual_provisions"):
        if k in minter:
            minter[k] = "0.000000000000000000"

if "crisis" in app and "constant_fee" in app["crisis"]:
    app["crisis"]["constant_fee"]["denom"] = "uwolo"

if "gov" in app and "params" in app["gov"]:
    gp = app["gov"]["params"]
    for key in ("min_deposit", "expedited_min_deposit"):
        if isinstance(gp.get(key), list):
            for coin in gp[key]:
                if isinstance(coin, dict) and "denom" in coin:
                    coin["denom"] = "uwolo"
    for key in (
        "burn_vote_quorum",
        "burn_proposal_deposit_prevote",
        "burn_vote_veto",
    ):
        if key in gp:
            gp[key] = False

bank = app.setdefault("bank", {})
bank["denom_metadata"] = [
    {
        "description": "WOLO is the fixed-supply native token of WoloChain.",
        "denom_units": [
            {"denom": "uwolo", "exponent": 0, "aliases": ["microWOLO"]},
            {"denom": "wolo", "exponent": 6},
        ],
        "base": "uwolo",
        "display": "wolo",
        "name": "WOLO",
        "symbol": "WOLO",
    }
]

genesis.write_text(json.dumps(g, indent=2, sort_keys=True) + "\n")
print(f"patched {genesis}")
PY

echo
echo "== add genesis accounts by address =="
export ALLOC_JSON
python3 - <<'PY' | while IFS=$'\t' read -r address amount bucket; do
import json
from pathlib import Path
import os

alloc = json.loads(Path(os.environ["ALLOC_JSON"]).read_text())
for row in alloc["allocations"]:
    address = row.get("address") or row.get("address_or_placeholder")
    amount = row["amount_uwolo"]
    bucket = row["bucket"]
    if not address.startswith("wolo1"):
        raise SystemExit(f"bad address for {bucket}: {address}")
    print(f"{address}\t{amount}\t{bucket}")
PY
  echo "adding $bucket -> ${amount}uwolo"
  "$BIN" genesis add-genesis-account "$address" "${amount}uwolo" --home "$HOME_DIR" >/dev/null
done

echo
echo "== validate draft genesis =="
"$BIN" genesis validate --home "$HOME_DIR"

echo
echo "== write draft report =="
export GENESIS REPORT EXPECTED_SUPPLY HOME_DIR CHAIN_ID
python3 - <<'PY'
import json
import os
from pathlib import Path
from datetime import datetime, timezone

genesis = Path(os.environ["GENESIS"])
report = Path(os.environ["REPORT"])
expected = int(os.environ["EXPECTED_SUPPLY"])

g = json.loads(genesis.read_text())
app = g["app_state"]
bank = app["bank"]

balances = bank.get("balances", [])
supply_items = bank.get("supply", [])

supply = 0
for coin in supply_items:
    if coin.get("denom") == "uwolo":
        supply += int(coin["amount"])

balance_total = 0
for bal in balances:
    for coin in bal.get("coins", []):
        if coin.get("denom") == "uwolo":
            balance_total += int(coin["amount"])

errors = []
if g.get("chain_id") != "wolo-1":
    errors.append(f"chain_id={g.get('chain_id')}")
if supply != expected:
    errors.append(f"supply={supply}, expected={expected}")
if balance_total != expected:
    errors.append(f"balance_total={balance_total}, expected={expected}")
if len(balances) != 8:
    errors.append(f"balance_count={len(balances)}, expected=8")

metadata = bank.get("denom_metadata", [])
if not any(m.get("base") == "uwolo" and m.get("display") == "wolo" and m.get("symbol") == "WOLO" for m in metadata):
    errors.append("missing WOLO denom metadata")

staking = app.get("staking", {}).get("params", {})
if staking.get("bond_denom") != "uwolo":
    errors.append(f"bond_denom={staking.get('bond_denom')}")

mint = app.get("mint", {})
mint_params = mint.get("params", {})
minter = mint.get("minter", {})
if mint_params.get("mint_denom") != "uwolo":
    errors.append(f"mint_denom={mint_params.get('mint_denom')}")
if minter.get("inflation") not in (None, "0.000000000000000000"):
    errors.append(f"inflation={minter.get('inflation')}")

text = genesis.read_text()
for forbidden in ("wolo-testnet", "/var/lib/wolochaind-testnet", "aoe2hdbets.com", "wolo1_REPLACE"):
    if forbidden in text:
        errors.append(f"forbidden text in genesis: {forbidden}")

out = {
    "ok": not errors,
    "errors": errors,
    "chain_id": g.get("chain_id"),
    "home": str(Path(os.environ["HOME_DIR"])),
    "genesis_path": str(genesis),
    "balance_count": len(balances),
    "supply_uwolo": str(supply),
    "balance_total_uwolo": str(balance_total),
    "supply_wolo": str(supply // 1_000_000),
    "artifact_status": "draft_chain_home_only_not_launched",
    "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
}
report.parent.mkdir(parents=True, exist_ok=True)
report.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")

print(json.dumps(out, indent=2, sort_keys=True))
if errors:
    raise SystemExit(1)
PY

echo
echo "Draft home ready:"
echo "  home:    $HOME_DIR"
echo "  genesis: $GENESIS"
echo "  report:  $REPORT"
