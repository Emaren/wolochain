#!/usr/bin/env python3
"""Read-only inspection of founder bonus #15 request records on two existing settlement lanes.

This is an evidence lead for historical app claim #889, NOT a payment, payout
absence, or release certificate. Run only inside the mainnet VPS as root.
No environment files, keys, network calls, writes or payment execution.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

ROOTS = (
    Path("/mnt/HC_Volume_105319120/wolochain-mainnet/settlement-state"),
    Path("/mnt/HC_Volume_105319120/wolochain-mainnet/founder-rewards-settlement-state"),
)
NAME = re.compile(r"aoe2-founder-15-[a-z0-9-]{1,110}\.json$")
HASH = re.compile(r"[0-9a-fA-F]{64}$")
PREFIX = "AoE2 Founder payout · bonus 15 · "
MAX_BYTES = 1024 * 1024
MAX_RECORDS = 128


def read_records(roots: tuple[Path, ...]) -> dict:
    records = []
    for lane, root in enumerate(roots):
        if not root.is_dir() or root.is_symlink():
            raise ValueError("settlement state lane is absent or a symlink")
        directory = root / "requests"
        if directory.is_symlink():
            raise ValueError("requests directory is a symlink")
        if not directory.is_dir():
            # The engine may have no request records; never treat that as proof of no payout.
            continue
        for entry in sorted(directory.iterdir()):
            if not NAME.fullmatch(entry.name):
                continue
            if len(records) >= MAX_RECORDS:
                raise ValueError("founder state exceeds bounded scan")
            info = entry.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                raise ValueError("unsafe founder state file")
            # Open read-only, reject symlinks if swapped between check and open.
            fd = os.open(entry, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                observed = os.fstat(fd)
                if not stat.S_ISREG(observed.st_mode) or observed.st_size > MAX_BYTES:
                    raise ValueError("unsafe opened founder state")
                with os.fdopen(fd, "rb", closefd=False) as handle:
                    data = handle.read(MAX_BYTES + 1)
            finally:
                os.close(fd)
            if len(data) > MAX_BYTES:
                raise ValueError("oversized founder state")
            record = json.loads(data)
            request = record.get("request")
            response = record.get("response")
            if not isinstance(request, dict) or not isinstance(response, dict):
                raise ValueError("malformed founder settlement record")
            request_id = request.get("request_id")
            if not isinstance(request_id, str) or entry.stem != request_id:
                raise ValueError("founder settlement request identity mismatch")
            memo = request.get("memo")
            tx_hash = response.get("tx_hash")
            if tx_hash and (not isinstance(tx_hash, str) or not HASH.fullmatch(tx_hash)):
                raise ValueError("invalid founder settlement transaction hash")
            status = str(response.get("status") or "")
            failure = str(response.get("failure_code") or "")
            records.append({
                "lane": "primary" if lane == 0 else "founder_rewards",
                "requestFingerprint": hashlib.sha256(request_id.encode()).hexdigest()[:16],
                "isFounderBonus15Memo": isinstance(memo, str) and memo.startswith(PREFIX),
                "hasReportedTxHash": bool(tx_hash),
                "reportedPublicTxHash": tx_hash.upper() if tx_hash else None,
                "status": status if status in ("failed", "confirmed", "accepted") else "other_or_unknown",
                "hasFailureCode": bool(failure),
                "recordedRequestIsChainProof": False,
                "recipientOrSignerAuthorityCertified": False,
            })
    return {
        "mode": "root_private_durable_founder15_request_inspection",
        "stateRootsChecked": len(roots),
        "requestRecordsFound": len(records),
        "records": records,
        "allHistoricalPayoutPathsCovered": False,
        "claim889Reconciled": False,
        "financialDrained": False,
        "payoutOrRetryAuthorized": False,
        "productionPromotionAuthorized": False,
        "databaseWrites": False,
        "filesystemWrites": False,
        "chainBroadcasts": False,
        "verdict": "REQUIRES_INDEPENDENT_CHAIN_AND_CLAIM_RECONCILIATION",
    }


def main() -> int:
    if os.geteuid() != 0 or sys.argv[1:] not in ([], ["--inspect"]):
        print("BLOCKED: root-only read-only --inspect mode required", file=sys.stderr)
        return 2
    try:
        result = read_records(ROOTS)
    except (ValueError, OSError, UnicodeError, json.JSONDecodeError):
        print("BLOCKED: settlement state invalid, unavailable or unsafe", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    # An inspection is never a maintenance authorization, even if empty.
    return 3


if __name__ == "__main__":
    sys.exit(main())
