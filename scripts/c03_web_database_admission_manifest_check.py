#!/usr/bin/env python3
"""WE1 exact-source, source-only DB admission manifest verifier.

No network, credentials, PostgreSQL connection, SQL execution, root operation,
signer, systemd call, or installation path exists in this program.
Independent protected authority must verify physical preimage and use its own
transactional executor; a passing plan is NEVER that authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "scripts/c03_web_database_admission_manifest_v1.json"
EXPECTED_IDS = ("library_readonly_v1", "social_hd_restricted_v2")
EXPECTED_SHA256 = {
    "scripts/c03_library_public_projection_candidate.sql":
    "976fb62b8d7b13eb8c497686b3eaaa66e08ad168b4183a58b720069243b89dfd",
    "scripts/c03_library_public_projection_inverse_candidate.sql":
    "3a25744c02dce756493652fcc1f16e184ff62c198cded6855e8aab284f38903c",
    "scripts/c03_hd_gateway_v2_restricted_install_candidate.sql":
    "78d6a9ea9cc953e38fc0c3e1aee3212fc5da42fe9b08c15b8da662d24d7ebe5c",
    "scripts/c03_hd_gateway_v2_restricted_inverse_candidate.sql":
    "84114bac7b3e15f4cadaf3a566f705440eeb9cf8ba63f3be97249652d5f25449",
}
EXPECTED_GIT_BLOBS = {
    "scripts/c03_library_public_projection_candidate.sql":
    "aba71d2bb67e0f4df21444df80707b5103547abf",
    "scripts/c03_library_public_projection_inverse_candidate.sql":
    "a472c349acae55e21c48508e594dd5a946fcff86",
    "scripts/c03_hd_gateway_v2_restricted_install_candidate.sql":
    "f38636b7ea1b7efe178831e1a40a78dad5604749",
    "scripts/c03_hd_gateway_v2_restricted_inverse_candidate.sql":
    "1c11073a44643e90bd59ae36118432001772b1da",
}
REQUIRED_LEGACY_HOLD = ("aoe2de_db", "financial", "8092", "8093", "8094", "8095")


class SourceHold(RuntimeError):
    """An exact source or safety invariant is unknown or false."""


def insist(condition: bool, code: str) -> None:
    if not condition:
        raise SourceHold(code)


def source_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def checked_source(root: Path, path: str, git_blob: str, sha256: str) -> str:
    insist(path in EXPECTED_SHA256, "UNEXPECTED_SQL_SOURCE_PATH")
    insist(git_blob == EXPECTED_GIT_BLOBS[path], "UNAPPROVED_GIT_BLOB")
    insist(sha256 == EXPECTED_SHA256[path], "UNAPPROVED_SHA256")
    src = root / path
    insist(src.is_file() and not src.is_symlink(), "SOURCE_FILE_UNAVAILABLE")
    insist(src.resolve().is_relative_to(root.resolve()), "SOURCE_OUTSIDE_REPO")
    raw = src.read_bytes()
    insist(source_blob(raw) == git_blob, "SOURCE_GIT_OBJECT_DRIFT")
    insist(hashlib.sha256(raw).hexdigest() == sha256, "SOURCE_SHA256_DRIFT")
    try:
        txt = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceHold("SOURCE_NOT_UTF8") from exc
    insist(txt.startswith("-- WE1") and txt.endswith("\n"), "SQL_SOURCE_HEADER_OR_TERMINATOR_DRIFT")
    insist(txt.count("BEGIN;") == 1 and txt.count("COMMIT;") == 1,
           "SQL_TRANSACTION_BOUNDARY_DRIFT")
    return txt


def check_manifest(raw: dict[str, Any]) -> None:
    insist(isinstance(raw, dict), "MANIFEST_TYPE")
    insist(raw.get("schema") == "aoe2war.we1.web_database_admission_manifest.v1",
           "MANIFEST_SCHEMA_DRIFT")
    insist(raw.get("authority") == "source-only-handoff-no-root-authorization",
           "MANIFEST_AUTHORITY_DRIFT")
    insist(raw.get("target_host") == "HEL1" and raw.get("target_database") == "aoe2hd_db",
           "HD_ONLY_DRIFT")
    insist(raw.get("finance_funding") == "DENIED" and
           raw.get("production_install_authorized") is False,
           "FINANCIAL_OR_INSTALL_AUTHORITY_FORGED")
    insist(raw.get("source_reviewed_from") ==
           "1b755ff12f5214756ac8a4edd8ba123259c48a18",
           "SOURCE_REVIEW_REFERENCE_DRIFT")
    contracts = raw.get("contracts")
    insist(isinstance(contracts, list) and
           tuple(c.get("id") for c in contracts if isinstance(c, dict)) == EXPECTED_IDS and
           len(contracts) == 2, "CONTRACT_SET_DRIFT")
    insist(contracts[0].get("roles_no_new") is True and
           contracts[1].get("roles_no_new") is False and
           all(c.get("installed") is False for c in contracts), "NO_INSTALL_STATUS_DRIFT")
    for contract in contracts:
        insist(isinstance(contract.get("prerequisite_physical"), list) and
               "owner_purpose_signed_maintenance_permit" in
               (contract["prerequisite_physical"] +
                ["owner_purpose_signed_maintenance_permit"]
                 if contract["id"] == EXPECTED_IDS[0] else contract["prerequisite_physical"]),
               "MAINTENANCE_PERMIT_NOT_GATED")
        insist(set(contract) >= {"install", "inverse", "prerequisite_physical"},
               "CONTRACT_INCOMPLETE")
    forbidden = raw.get("strictly_forbidden")
    insist(isinstance(forbidden, list) and len(forbidden) >= 8 and
           all(isinstance(x, str) for x in forbidden), "DENIAL_SET_DRIFT")
    witness = raw.get("source_catalog_witness")
    insist(isinstance(witness, dict) and len(witness) == 4 and
           all(isinstance(v, str) and len(v) == 64 for v in witness.values()),
           "CATALOG_WITNESS_SHA_DRIFT")


def verify(root: Path = ROOT, manifest: Path = MANIFEST) -> dict[str, Any]:
    insist(manifest.is_file() and not manifest.is_symlink(), "MANIFEST_MISSING_OR_SYMLINK")
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    check_manifest(raw)
    files: dict[str, str] = {}
    for contract in raw["contracts"]:
        for kind in ("install", "inverse"):
            obj = contract[kind]
            insist(set(obj) == {"path", "git_blob", "sha256"}, "SQL_OBJECT_FIELDS_DRIFT")
            path = obj["path"]
            insist(path not in files, "SQL_PATH_DUPLICATED")
            files[path] = checked_source(root, path, obj["git_blob"], obj["sha256"])
    insist(set(files) == set(EXPECTED_SHA256), "SQL_FILES_MISSING")
    library = files["scripts/c03_library_public_projection_candidate.sql"]
    library_inv = files["scripts/c03_library_public_projection_inverse_candidate.sql"]
    social = files["scripts/c03_hd_gateway_v2_restricted_install_candidate.sql"]
    social_inv = files["scripts/c03_hd_gateway_v2_restricted_inverse_candidate.sql"]
    insist("current_database()<>'aoe2hd_db'" in library and
           "current_database()<>'aoe2hd_db'" in social, "HD_ONLY_SQL_PREFLIGHT_MISSING")
    insist("aoe2hd_user" in library and
           "aoe2war_web_prod" in library and
           library.count("WITH (security_barrier=true)") == 2 and
           "aoe2war_library_activity_public.replay_uploads" in library and
           "aoe2war_library_watcher_public.batch_receipts" in library,
           "LIBRARY_VIEW_SCOPE_DRIFT")
    insist("LIBRARY_EVENT_RAW_ACL_PREIMAGE_HOLD" in library and
           "LIBRARY_WEB_ALREADY_READS_PROTECTED_BASE" in library and
           "verification_method IS DISTINCT FROM 'system'" in library,
           "LIBRARY_PRIVACY_PREIMAGE_DRIFT")
    for old in ("GRANT SELECT ON public.user_activity_events",
                "GRANT SELECT ON public.watcher_client_events",
                "GRANT INSERT ON public.users",
                "GRANT CREATE ON DATABASE"):
        insist(old not in library, "BROAD_LIBRARY_GRANT_DETECTED")
    insist("DROP SCHEMA aoe2war_library_activity_public RESTRICT" in library_inv and
           "DROP SCHEMA aoe2war_library_watcher_public RESTRICT" in library_inv and
           "CASCADE" not in library_inv.upper(), "LIBRARY_INVERSE_DRIFT")
    insist("aoe2war_social_exec_v2" in social and
           "aoe2war_social_writer" in social and
           "aoe2war_social_hd_v2.clan_text(text,text,text,text)" in social and
           "aoe2war_social_hd_v2.direct_text(text,text,text,integer)" in social and
           "C03_HD_GATEWAY_OWNER_OR_FINANCE_CAPABILITY_DRIFT" in social,
           "SOCIAL_EXECUTOR_DRIFT")
    insist("REVOKE ALL ON FUNCTION" in social and "FROM PUBLIC;" in social and
           "has_table_privilege('aoe2war_social_exec_v2','public.users','DELETE')" in social,
           "SOCIAL_PUBLIC_OR_USERS_FINANCE_DENIAL_DRIFT")
    insist("CASCADE" not in social_inv.upper() and
           "DROP ROLE aoe2war_social_writer" in social_inv and
           "DROP ROLE aoe2war_social_exec_v2" in social_inv,
           "SOCIAL_INVERSE_DRIFT")
    return {"result": "SOURCE_HASH_AND_STATIC_BOUNDARY_PASS",
            "contracts": list(EXPECTED_IDS),
            "database": "aoe2hd_db",
            "installation_authorized": False,
            "financial_authorized": False,
            "actual_HBA_verified": False,
            "actual_AF_UNIX_verified": False,
            "live_privacy_verified": False,
            "actual_financial_writer_exclusion": False,
            "sql_files_verified": len(files),
            "next_owner": "WE2 protected independent permit+install",
            "gate_C03": "OPEN"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", action="store_true",
                        help="Only print a nonauthorizing, source-hash verified HOLD plan")
    args = parser.parse_args()
    try:
        result = verify()
    except (SourceHold, ValueError, OSError, json.JSONDecodeError) as exc:
        print("C03_WEB_DB_SOURCE_HOLD:", str(exc).splitlines()[0][:200])
        raise SystemExit(2) from None
    print(json.dumps(result, sort_keys=True))
    print("C03_WEB_DB_SOURCE_ONLY_NOT_ROOT_OR_SQL_PERMIT")
    if not args.plan:
        print("NO_EXECUTION_MODE_EXISTS")


if __name__ == "__main__":
    main()
