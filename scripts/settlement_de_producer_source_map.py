#!/usr/bin/env python3
"""Read-only DE source capability map for WoloChain's first financial release HOLD control.

This is a bounded, operator-local code fingerprint audit, NOT signer isolation,
a complete call graph, an active runtime inventory, or permission to release.
The independent HD source census belongs to app-prodn. Never read .env or keys.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

MAX_FILE_BYTES = 512_000
SHA = re.compile(r"[0-9a-f]{40}\Z")
SENTINELS = (
    ("app/api/lobby/route.ts", "export async function GET(", "public_read_trigger"),
    ("app/api/lobby/route.ts", "loadLobbySnapshot(", "public_read_trigger"),
    ("lib/lobbySnapshot.ts", "await ensureBetMarkets(prisma);", "read_to_financial_work"),
    ("lib/bets.ts", "await settleResolvedMarketWagers(prisma);", "financial_reconciliation"),
    ("lib/bets.ts", "await settleFounderBonuses(prisma);", "financial_reconciliation"),
    ("app/api/wolo/faucet/claim/route.ts", "export async function POST(", "public_wallet_ingress"),
    ("app/api/wolo/faucet/claim/route.ts", "const txhash = await sendFaucetTransfer(address);", "cli_keyring_send"),
    ("app/api/wolo/faucet/claim/route.ts", "await execFileAsync(FAUCET_CLI, txArgs,", "cli_keyring_send"),
    ("app/api/user/wolo-claims/claim/route.ts", "export async function POST(", "claim_ingress"),
    ("app/api/admin/wolochain/scheduled-settlements/[id]/execute/route.ts",
     "executeScheduledMatchSettlement(", "admin_payment_ingress"),
    ("app/api/admin/wolochain/staking-treasury-payouts/[id]/execute/route.ts",
     "executeStakingTreasuryPayout(", "admin_payment_ingress"),
    ("lib/woloBetSettlement.ts", "WOLO_LOCAL_PAYOUT_SIGNER_FALLBACK_ENABLED", "conditional_direct_signer"),
    ("lib/woloBetSettlement.ts", "DirectSecp256k1HdWallet.fromMnemonic(", "conditional_direct_signer"),
    ("lib/woloBetSettlement.ts", "await client.sendTokens(", "conditional_direct_signer"),
    ("lib/woloStakingUnstake.ts", "WOLO_STAKING_ALLOW_PAYOUT_MNEMONIC_FALLBACK", "conditional_staking_signer"),
    ("lib/woloStakingUnstake.ts", "DirectSecp256k1HdWallet.fromMnemonic(", "conditional_staking_signer"),
    ("lib/woloStakingUnstake.ts", "await client.sendTokens(", "conditional_staking_signer"),
    ("app/api/staking/unstake/route.ts", "export async function POST(", "stake_ingress"),
)

UNPROVEN = (
    "Exact DE deployed code, service process and imported dotenv provenance",
    "Conditional fallback and direct mnemonic/keyring signer enablement",
    "HTTP, cron, manual, callback, timer, container and external producers",
    "HD/DE treasury and settlement journal transfer finality",
    "Complete producer fence, in-flight drain, owner approval and solvency",
)


def _read_bounded(root: Path, relative: str) -> tuple[list[str], str] | None:
    """Reject link-substituted directories/files, oversized or non-UTF-8 source."""
    parent = root
    try:
        if not root.is_dir() or root.is_symlink():
            return None
        for part in Path(relative).parts:
            if part in ("", ".", ".."):
                return None
            parent = parent / part
            info = parent.lstat()
            if stat.S_ISLNK(info.st_mode):
                return None
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
            return None
        # O_NOFOLLOW prevents leaf substitution between lstat and open.
        fd = os.open(parent, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_FILE_BYTES:
                return None
            with os.fdopen(fd, "rb", closefd=False) as stream:
                data = stream.read(MAX_FILE_BYTES + 1)
            after = os.fstat(fd)
            if len(data) > MAX_FILE_BYTES or before.st_ino != after.st_ino or before.st_size != len(data):
                return None
        finally:
            os.close(fd)
        return data.decode("utf-8").splitlines(), hashlib.sha256(data).hexdigest()
    except (OSError, UnicodeError, ValueError):
        return None


def source_identity(root: Path) -> dict:
    """A local source identity; neither VPS revision nor deployed executable."""
    def run(*args: str) -> str:
        p = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                           text=True, timeout=7, check=False)
        if p.returncode:
            raise ValueError("local git unavailable")
        return p.stdout.strip()
    try:
        top = Path(run("rev-parse", "--show-toplevel"))
        head = run("rev-parse", "HEAD")
        clean = not run("status", "--porcelain=v1", "--untracked-files=all")
        if top.resolve() != root.resolve() or not SHA.fullmatch(head) or not clean:
            raise ValueError("unclean or unexpected git identity")
        return {"state": "LOCAL_CLEAN_GIT_ONLY", "head": head}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"state": "SOURCE_IDENTITY_UNVERIFIED", "head": None}


def inspect(root: Path, identity: dict | None = None) -> dict:
    identity = identity or {"state": "SOURCE_IDENTITY_UNVERIFIED", "head": None}
    cache = {}
    entries = []
    for relative, needle, role in SENTINELS:
        if relative not in cache:
            cache[relative] = _read_bounded(root, relative)
        found = cache[relative]
        lines, digest = found if found is not None else ([], None)
        matches = [index for index, line in enumerate(lines, 1) if needle in line]
        entries.append({
            "path": relative, "role": role,
            "status": "SOURCE_OBSERVED" if matches else (
                "SOURCE_DRIFT" if found is not None else "UNKNOWN_SOURCE"),
            "line": matches[0] if matches else None,
            "sha256": digest,
        })
    all_present = all(v["status"] == "SOURCE_OBSERVED" for v in entries)
    return {
        "schema": "wolo.financial.de-producer-source-map.v1",
        "mode": "READ_ONLY_NONAUTHORIZING",
        "local_source": identity,
        "known_de_source_edges_intact": all_present,
        "complete_financial_producer_inventory_proven": False,
        "financial_producers_fenced": False,
        "independent_de_signer_exclusion_proven": False,
        "mainnet_settlement_cutover_authorized": False,
        "website_release_authorized": False,
        "satchel_authorized": False,
        "required_independent_evidence": list(UNPROVEN),
        "observations": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--de-root", type=Path, required=True,
                        help="Exact local checkout root of aoe2dewarwagers-web; never read production secrets")
    parser.add_argument("--check", action="store_true", help="Require known edges + local clean Git, NOT finance readiness")
    args = parser.parse_args()
    root = args.de_root
    evidence = inspect(root, source_identity(root))
    print(json.dumps(evidence, indent=2, sort_keys=True))
    if args.check and (not evidence["known_de_source_edges_intact"] or
                       evidence["local_source"]["state"] != "LOCAL_CLEAN_GIT_ONLY"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
