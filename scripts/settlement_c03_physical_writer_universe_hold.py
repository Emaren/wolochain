#!/usr/bin/env python3
"""C03 exact-host financial writer universe observation. Always HOLD, never fence.

Read-only cross-plane admission preflight for the *existing* financial
maintenance controller. It proves neither quiescence nor grant containment,
and does not carry permits or authorize payments. Root-local on HEL1 only.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
import re
import subprocess
import sys

import settlement_c03_db_owner_boundary_hold as owner

SCHEMA = "wolo.c03.physical-writer-universe-hold.v1"
UNIT = re.compile(r"[A-Za-z0-9_.@:-]{1,120}\.(?:service|timer)\Z")
PREFIXES = (
    "aoe2hdbets-", "aoe2dewarwagers-", "aoe2war-", "aoe2-wolo-",
    "traffic-", "wolochain-", "wolo-",
)
MAX_LIST = 131072
MAX_UNITS = 500
MAX_SINGLE = 4096
PUBLIC_PROTECTED = frozenset((
    "aoe2hdbets-web-prod.service", "aoe2hdbets-web.service",
    "aoe2hdbets-web-r24.service", "aoe2war-steam-egress-refresh.timer",
    "wolochaind-mainnet.service",
    "wolochain-mainnet-settlement.service",
    "wolochain-founder-rewards-settlement.service",
))
# These are not all producer paths. They are the known 18-unit controller
# scope. Other discoveries must be separately reviewed and explicitly fenced.
FAMILIES = (
    "aoe2hdbets-bet-stake-reconcile",
    "aoe2hdbets-challenge-reconcile",
    "aoe2hdbets-replay-auto-recovery",
    "aoe2hdbets-staking-rewards",
    "aoe2hdbets-trophy-tributes",
    "aoe2war-prewarm",
    "aoe2-wolo-transfer-heartbeat",
)
OWNED = frozenset((
    "aoe2hdbets-web.service", "aoe2hdbets-api.service",
    "aoe2dewarwagers-web.service", "aoe2dewarwagers-api.service",
) + tuple(x + ext for x in FAMILIES for ext in (".service", ".timer")))
ANCHORS = frozenset((
    "aoe2hdbets-web-prod.service", "wolochaind-mainnet.service",
    "wolochain-mainnet-settlement.service",
))
CRITICAL_EXTERNAL = frozenset((
    "traffic-v2-forward-ledger-aoe2hdbets.timer",
    "traffic-v2-forward-ledger-aoe2hdbets.service",
))
UNPROVEN_DOMAINS = (
    "cron_and_per_user_systemd", "docker_and_orchestrated_containers",
    "traffic_api_and_external_writer_ingress", "postgres_database_schema_owner",
    "postgres_security_definer_and_triggers", "session_reconnect",
    "settlement_and_signer_file_journals",
)

class ObservationError(ValueError):
    pass

def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ObservationError(reason)

def run(argv: list[str]) -> str:
    require(os.geteuid() == 0, "HEL1_ROOT_REQUIRED")
    p = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True, timeout=15, check=False)
    require(p.returncode == 0 and not p.stderr.strip() and
            0 < len(p.stdout.encode()) <= MAX_LIST,
            "ROOT_SYSTEMD_OBSERVATION_UNAVAILABLE")
    return p.stdout

def names_from_listing(raw: str) -> set[str]:
    require(isinstance(raw, str) and len(raw.encode()) <= MAX_LIST,
            "UNBOUNDED_UNIT_LISTING")
    found = set()
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("UNIT ") or line.startswith("0 unit"):
            continue
        fields = line.lstrip("●").split()
        if not fields:
            continue
        unit = fields[0]
        if not unit.startswith(PREFIXES):
            continue
        require(UNIT.fullmatch(unit), "FINANCIAL_UNIT_NAME_INVALID")
        require(unit not in found, "DUPLICATE_FINANCIAL_UNIT_NAME")
        found.add(unit)
        require(len(found) <= MAX_UNITS, "TOO_MANY_FINANCIAL_UNITS")
    return found

def parse_properties(raw: str, name: str) -> dict:
    require(UNIT.fullmatch(name) and isinstance(raw, str) and
            len(raw.encode()) <= MAX_SINGLE, "UNIT_PROPERTIES_SIZE_OR_NAME")
    out = {}
    for line in raw.splitlines():
        require("=" in line, "MALFORMED_SYSTEMD_PROPERTY")
        k, v = line.split("=", 1)
        require(k not in out, "DUPLICATE_SYSTEMD_PROPERTY")
        out[k] = v
    expected = {"Id", "LoadState", "ActiveState", "UnitFileState",
                "MainPID", "FragmentPath", "Triggers", "TriggeredBy"}
    require(expected.issubset(out) and out["Id"] == name and
            out["LoadState"] in ("loaded", "masked") and
            out["ActiveState"] in ("active", "inactive", "failed", "activating",
                                    "deactivating", "reloading") and
            out["MainPID"].isdigit() and
            len(out["FragmentPath"]) < 512,
            "UNQUALIFIED_EFFECTIVE_UNIT_PROPERTIES")
    return {k: out[k] for k in sorted(expected)}

def classify(name: str, props: dict) -> dict:
    require(UNIT.fullmatch(name), "UNIT_IDENTITY_INVALID")
    if name in PUBLIC_PROTECTED:
        category = "PROTECTED_INCUMBENT_NO_AUTOMATED_STOP"
    elif name in OWNED:
        category = "EXISTING_SOURCE_FENCE_SCOPE_NOT_PROVEN_EFFECTIVE"
    else:
        category = "UNSCOPED_REVIEW_REQUIRED"
    return {"unit": name, "category": category,
            "active": props["ActiveState"] != "inactive",
            "timer": name.endswith(".timer"),
            "properties": props}

def observe() -> dict:
    require(os.geteuid() == 0, "HEL1_ROOT_REQUIRED")
    lists = (
        run(["systemctl", "--no-pager", "list-units", "--all",
             "--type=service", "--type=timer", "--no-legend", "--plain"]),
        run(["systemctl", "--no-pager", "list-unit-files", "--type=service",
             "--type=timer", "--no-legend", "--plain"]),
    )
    names = names_from_listing(lists[0]) | names_from_listing(lists[1])
    require(ANCHORS.issubset(names), "PROTECTED_PRODUCTION_ANCHOR_MISSING")
    require(len(names) <= MAX_UNITS, "TOO_MANY_FINANCIAL_UNITS")
    rows = []
    for name in sorted(names):
        raw = run(["systemctl", "--no-pager", "show",
                   "--property=Id,LoadState,ActiveState,UnitFileState,MainPID,"
                   "FragmentPath,Triggers,TriggeredBy", "--", name])
        require(len(raw.encode()) <= MAX_SINGLE, "UNIT_PROPERTIES_OVERSIZED")
        rows.append(classify(name, parse_properties(raw, name)))
    assert len(rows) == len(names)
    db = {name: owner.inspect(name) for name in owner.TARGETS}
    require(all(result["implicit_owner_or_schema_bypass"] for result in db.values()),
            "OWNER_BYPASS_OBSERVATION_CHANGED_REQUIRE_REVIEW")
    unscope = [r["unit"] for r in rows
               if r["category"] == "UNSCOPED_REVIEW_REQUIRED"]
    active_unscope = [r["unit"] for r in rows if
                      r["category"] == "UNSCOPED_REVIEW_REQUIRED" and r["active"]]
    require(CRITICAL_EXTERNAL.issubset(names),
            "KNOWN_TRAFFIC_WRITER_UNIT_DISAPPEARED")
    census = {"systemdUnits": rows, "legacyDbOwner": db}
    digest = hashlib.sha256(json.dumps(census, sort_keys=True,
                                      separators=(",", ":")).encode()).hexdigest()
    return {
        "schema": SCHEMA, "utc": datetime.now(timezone.utc).isoformat(),
        "status": "HOLD", "classification": "REQUIRES_PRODUCER_EXCLUSION_REVIEW",
        "sourceScopeUnitCount": len(OWNED),
        "discoveredUnitCount": len(rows),
        "unscopedUnitCount": len(unscope), "unscopedUnits": unscope,
        "activeUnscopedUnits": active_unscope,
        "protectedIncumbents": sorted(PUBLIC_PROTECTED & names),
        "unprovenDomains": list(UNPROVEN_DOMAINS),
        "censusSha256": digest,
        "census": census,
        "databaseOwnershipChanged": False, "unitsModified": False,
        "fenceAndQuiescenceProven": False, "backupAuthorized": False,
        "paymentAuthorized": False,
    }

def main() -> int:
    try:
        result = observe()
    except (ObservationError, OSError, UnicodeError, ValueError,
            subprocess.SubprocessError) as exc:
        reason = str(exc) if isinstance(exc, ObservationError) else "OBSERVATION_UNAVAILABLE"
        print(json.dumps({"schema": SCHEMA, "status": "STOP", "reason": reason,
                          "paymentAuthorized": False}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 3

if __name__ == "__main__":
    sys.exit(main())
