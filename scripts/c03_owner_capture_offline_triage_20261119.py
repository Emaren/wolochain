#!/usr/bin/env python3
"""WE1 source-pinned LOCAL read-only HD/DE catalog triage.

Only reads existing privately captured catalog output. No database access,
network, subprocess, privileged commands, mutations or production ACCEPT.
Reports category-level findings; never displays original private SQL rows.

Source-only. This is not an authenticated root/systemd/PG writer fence.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import stat

EXPECTED = {
    "aoe2hd_db": "2da50447f5dcf53834f309b51f8f7ec1e5e61b6d9b4e5aff4e94b024a600e894",
    "aoe2de_db": "76c5de13c1f1a6b35411454166ee5852dff30f5903c9f8f81349d951fc198bd5",
}
TABLES = frozenset({
    "users", "clans", "clan_members", "clan_messages",
    "direct_conversations", "direct_conversation_participants",
    "direct_messages", "direct_message_drafts",
})
SEQUENCES = frozenset({
    "clan_messages_id_seq", "direct_conversations_id_seq",
    "direct_conversation_participants_id_seq", "direct_messages_id_seq",
})
FINANCIAL_PREFIXES = ("bet_", "trophy_payout", "staking_", "warrior_claim",
                      "bounty_claim", "financial_", "reserve_", "payout_")
ERROR = "C03_CATALOG_CAPTURE_HOLD"


def parse_capture(content: bytes, expected_name: str) -> dict:
    sections = defaultdict(list)
    for index, line in enumerate(content.decode("utf-8").splitlines(), 1):
        if not line:
            continue
        if "|" not in line:
            raise ValueError(f"{ERROR}_INVALID_LINE_{index}")
        section, payload = line.split("|", 1)
        try:
            item = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{ERROR}_INVALID_JSON_{index}") from exc
        sections[section].append(item)
    for name in ("AUDIT_META", "ROLE_PRESENCE", "FINAL_NONAUTHORIZATION"):
        if len(sections[name]) != 1:
            raise ValueError(f"{ERROR}_MISSING_{name}")
    meta = sections["AUDIT_META"][0]
    final = sections["FINAL_NONAUTHORIZATION"][0]
    if (meta.get("db") != expected_name or
            meta.get("transaction_read_only") != "on" or
            meta.get("admission") != "HOLD_SOURCE_ONLY" or
            final.get("admitted_financial_writer_exclusion") is not False or
            final.get("social_writer_install_authorized") is not False):
        raise ValueError(f"{ERROR}_AUTHORITY_OR_DB_MISMATCH")
    roles = {v["rolname"]: v for v in sections["ROLE_PREIMAGE"]}
    presence = sections["ROLE_PRESENCE"][0]
    if presence.get("social_writer_absent") is not True:
        raise ValueError(f"{ERROR}_SOCIAL_ROLE_PRESENT")
    if not presence.get("web_prod_present") or "aoe2war_web_prod" not in roles:
        raise ValueError(f"{ERROR}_WEB_IDENTITY_MISSING")
    if roles["aoe2war_web_prod"].get("rolinherit") is not False:
        raise ValueError(f"{ERROR}_WEB_ROLE_INHERITS")
    relations = {v["relname"]: v for v in sections["NAMED_RELATION_RAW_PREIMAGE"]}
    if set(relations) != TABLES | SEQUENCES:
        raise ValueError(f"{ERROR}_RELATION_SET_DRIFT")
    for v in relations.values():
        if v.get("oid") is not None and v.get("relkind") not in ("r", "p", "S"):
            raise ValueError(f"{ERROR}_UNEXPECTED_RELKIND")
    actual_tables = sorted(k for k in TABLES if relations[k].get("oid") is not None)
    actual_sequences = sorted(k for k in SEQUENCES if relations[k].get("oid") is not None)
    present = actual_tables + actual_sequences
    missing = sorted((TABLES | SEQUENCES) - set(present))
    owners = sorted({relations[k].get("owner") for k in present})
    raw_null = sorted(k for k in present if relations[k].get("raw_nullable_acl") is None)
    raw_explicit = sorted(k for k in present if relations[k].get("raw_nullable_acl") is not None)
    trigger_rows = sections["TRIGGER_OWNER_AND_FUNCTION"]
    enabled_user_triggers = [
        v["tgname"] for v in trigger_rows
        if v.get("tgisinternal") is False and v.get("tgenabled") in ("O", "A", "R")
    ]
    fk_rows = sections["FOREIGN_KEY_DESCENDANT"]
    finance_fk_cascade = [
        {"source": v["source_relation"], "referenced": v["referenced_relation"],
         "constraint": v["conname"]}
        for v in fk_rows
        if v.get("confdeltype") == "c" and
           any(str(v.get("source_relation", "")).startswith(pre)
               for pre in FINANCIAL_PREFIXES)
    ]
    public_definers = [v.get("function_identity") for v in sections["NON_SYSTEM_SECURITY_DEFINER"]
                       if v.get("public_execute") is True]
    flags = [
        "HOLD_OWNER_TRANSITIVE_FINANCE_AUTHORITY_NOT_CAPTURED",
        "HOLD_WE3_SOURCE_DEFINER_INSTALL_OWNER_UNPINNED",
        "HOLD_REQUIRES_MATCHED_SCHEMA_AND_EXACT_INVERSE",
        "HOLD_REQUIRES_SIGNED_PHYSICAL_WITNESS_AND_ONE_USE_PERMIT",
    ]
    if missing:
        flags.append("HOLD_MISSING_SOCIAL_OBJECTS_IN_THIS_DATABASE")
    if enabled_user_triggers:
        flags.append("HOLD_ENABLED_NONINTERNAL_SOCIAL_TRIGGER")
    if finance_fk_cascade:
        flags.append("HOLD_REAL_FK_CASCADE_PATH_FROM_USERS_TO_FINANCIAL_TABLES")
    if public_definers:
        flags.append("HOLD_PUBLIC_SECURITY_DEFINER_EXECUTE")
    return {
        "db": expected_name,
        "captured_pg_version": meta["pg_version"],
        "web_prod_noinherit": True,
        "social_writer_absent": True,
        "present_tables": actual_tables,
        "present_sequences": actual_sequences,
        "missing": missing,
        "owner_principals": owners,
        "raw_null_acl_objects": raw_null,
        "raw_explicit_acl_objects": raw_explicit,
        "enabled_noninternal_trigger_count": len(enabled_user_triggers),
        "internal_trigger_count": sum(bool(v.get("tgisinternal")) for v in trigger_rows),
        "security_definer_count": len(sections["NON_SYSTEM_SECURITY_DEFINER"]),
        "public_execute_definers": public_definers,
        "financial_on_delete_cascade_from_users": finance_fk_cascade,
        "fk_total": len(fk_rows),
        "result": "HOLD_SOURCE_ONLY_NOT_SQL_ADMISSION",
        "holds": flags,
    }


def read_private_capture(root: Path, database: str, expected_hash: str) -> dict:
    p = root / f"{database}.catalog.txt"
    if p.is_symlink() or not p.is_file():
        raise ValueError(f"{ERROR}_MISSING_OR_SYMLINK_{database}")
    mode = p.stat().st_mode
    if stat.S_IMODE(mode) != 0o600 or p.stat().st_nlink != 1:
        raise ValueError(f"{ERROR}_PRIVACY_OR_LINK_COUNT_{database}")
    raw = p.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_hash:
        raise ValueError(f"{ERROR}_SHA256_MISMATCH_{database}")
    result = parse_capture(raw, database)
    result["capture_sha256"] = expected_hash
    return result


def synthetic_tests():
    # Construct two small, entirely synthetic fixture receipts. NEVER use live
    # catalog dumps in repository tests or workflow artifacts.
    def make(db):
        values = {
            "AUDIT_META": {"db": db, "transaction_read_only": "on",
                           "admission": "HOLD_SOURCE_ONLY", "pg_version": "16.synthetic"},
            "FINAL_NONAUTHORIZATION": {"admitted_financial_writer_exclusion": False,
                                        "social_writer_install_authorized": False},
            "ROLE_PRESENCE": {"social_writer_absent": True, "web_prod_present": True},
            "ROLE_PREIMAGE": {"rolname": "aoe2war_web_prod", "rolinherit": False},
        }
        out = [f"{k}|{json.dumps(v)}" for k,v in values.items()]
        out.extend("NAMED_RELATION_RAW_PREIMAGE|" + json.dumps({
            "relname": k, "oid": str(i), "owner": "fixture_owner",
            "relkind": "S" if k in SEQUENCES else "r",
            "raw_nullable_acl": None}) for i,k in enumerate(sorted(TABLES|SEQUENCES), 1))
        return ("\n".join(out)+"\n").encode()
    x = parse_capture(make("aoe2hd_db"), "aoe2hd_db")
    assert x["result"].startswith("HOLD_") and len(x["present_tables"]) == 8
    assert x["financial_on_delete_cascade_from_users"] == []
    bad = make("aoe2hd_db").replace(b'HOLD_SOURCE_ONLY', b'FENCED', 1)
    try:
        parse_capture(bad, "aoe2hd_db")
    except ValueError: pass
    else: raise AssertionError("fail-open on authority substitution")
    try:
        parse_capture(make("aoe2hd_db"), "aoe2de_db")
    except ValueError: pass
    else: raise AssertionError("fail-open on database substitution")
    with __import__("tempfile").TemporaryDirectory() as d:
        root = Path(d)
        for db in EXPECTED:
            p = root / f"{db}.catalog.txt"
            p.write_bytes(make(db))
            p.chmod(0o600)
        for db in EXPECTED:
            x = read_private_capture(root, db, hashlib.sha256(make(db)).hexdigest())
            assert x["result"].startswith("HOLD_")
        try:
            read_private_capture(root, "aoe2hd_db", "0"*64)
        except ValueError: pass
        else: raise AssertionError("fail-open on tampered content hash")
        (root / "aoe2hd_db.catalog.txt").chmod(0o644)
        try:
            read_private_capture(root, "aoe2hd_db", hashlib.sha256(make("aoe2hd_db")).hexdigest())
        except ValueError: pass
        else: raise AssertionError("fail-open on privacy mode")
    return {"status": "PASS", "checks": 8,
            "production_access": False, "source_only": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--capture-directory", type=Path)
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(synthetic_tests(), sort_keys=True))
        return
    if args.capture_directory is None or os.geteuid() == 0:
        raise SystemExit("HOLD: requires explicit private capture path and nonroot identity")
    root = args.capture_directory
    if root.is_symlink() or not root.is_dir() or (root.stat().st_mode & 0o077):
        raise SystemExit("HOLD: capture directory must be non-symlink owner-private")
    summary = [read_private_capture(root, db, sha) for db,sha in EXPECTED.items()]
    # Never echo raw private catalog dumps; this report contains only
    # object names/owners and aggregate technical risk findings.
    print(json.dumps({"status": "HOLD_PRODUCTION_SQL",
                      "source": "two externally owner-captured read-only catalogs",
                      "hashes_match": True, "databases": summary}, sort_keys=True))


if __name__ == "__main__":
    main()
