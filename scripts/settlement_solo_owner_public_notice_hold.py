#!/usr/bin/env python3
"""C08: source-pin public single-human governance notice; NEVER grant funds.

Read-only authenticated GitHub CLI fetch of a publicly visible notice and
repo visibility. Before 24h -> HOLD_NOTICE_WINDOW; afterward -> HOLD_OTHER_GATES.
No wallet, key, signer, DB, on-chain send, release API, private-path read or
financial authorization. Static source matches published version only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import subprocess
import sys

OWNER = "Emaren"
REPO = "wolochain"
ISSUE = 184
ISSUE_URL = "https://github.com/Emaren/wolochain/issues/184"
CREATED_UTC = "2026-11-07T10:22:33Z"
EARLIEST_UTC = "2026-11-08T10:22:33Z"
EXACT_PUBLIC_BODY_SHA256 = "b17206bc8b693b1777cd4a3ceef53f81f62f18668a6ebd2c2b8d793bd3146223"
NOTICE_MIN_SECONDS = 86400
SCHEMA = "wolo.solo-owner-public-notice-24h-finance-hard-hold.v1"

class NoticeStop(ValueError):
    pass

def require(ok, reason):
    if not ok:
        raise NoticeStop(reason)

def unique_pairs(pairs):
    d = {}
    for k, v in pairs:
        require(k not in d, "DUPLICATE_JSON_KEY")
        d[k] = v
    return d

def parse_document(raw):
    require(type(raw) is bytes and 0 < len(raw) < 1_000_000, "UNTRUSTED_API_BYTES")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs,
            parse_constant=lambda _: require(False, "NONFINITE_JSON"))
    except (UnicodeError, ValueError, RecursionError):
        raise NoticeStop("INVALID_API_JSON") from None

def utc(stamp):
    require(type(stamp) is str and re.fullmatch(
        r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", stamp),
        "NOTICE_UTC_TIMESTAMP_INVALID")
    try:
        return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        raise NoticeStop("NOTICE_UTC_TIMESTAMP_INVALID") from None

def inspect_notice(issue, repository, *, now=None):
    require(type(issue) is dict and type(repository) is dict,
            "PUBLICATION_API_OBJECTS_REQUIRED")
    require(repository.get("full_name") == OWNER + "/" + REPO
            and repository.get("visibility") == "public"
            and repository.get("has_issues") is True,
            "NOTICE_MUST_BE_ON_PUBLIC_REPOSITORY")
    require(issue.get("number") == ISSUE and type(issue.get("number")) is int
            and issue.get("html_url") == ISSUE_URL
            and issue.get("state") == "open" and issue.get("closed_at") is None
            and "pull_request" not in issue,
            "NOTICE_ISSUE_OR_STATE_UNTRUSTED")
    owner = issue.get("user")
    require(type(owner) is dict and owner.get("login") == OWNER,
            "NOTICE_AUTHOR_WRONG")
    created = utc(issue.get("created_at"))
    require(issue["created_at"] == CREATED_UTC, "NOTICE_PUBLICATION_TIMESTAMP_CHANGED")
    expiry = created + timedelta(seconds=NOTICE_MIN_SECONDS)
    require(expiry == utc(EARLIEST_UTC), "NOTICE_MINIMUM_24H_CHANGED")
    body = issue.get("body")
    require(type(body) is str and 1000 <= len(body) <= 15000,
            "NOTICE_BODY_INVALID")
    require(hashlib.sha256(body.encode("utf-8")).hexdigest() ==
            EXACT_PUBLIC_BODY_SHA256, "PUBLIC_NOTICE_BODY_SHA256_CHANGED")
    current = now if now is not None else datetime.now(timezone.utc)
    require(isinstance(current, datetime) and current.tzinfo is not None,
            "TRUSTED_LOCAL_UTC_REQUIRED")
    current = current.astimezone(timezone.utc)
    require(current >= created, "NOTICE_CLOCK_BEFORE_PUBLICATION")
    status = ("HOLD_PUBLIC_NOTICE_24H_STILL_RUNNING"
              if current < expiry else
              "PASS_NOTICE_TIME_ONLY_ALL_FINANCIAL_GATES_HOLD")
    return {
        "schema": SCHEMA,
        "status": status,
        "public_url": ISSUE_URL,
        "public_body_sha256": EXACT_PUBLIC_BODY_SHA256,
        "publication_utc": CREATED_UTC,
        "not_before_utc": EARLIEST_UTC,
        "min_notice_seconds": NOTICE_MIN_SECONDS,
        "one_human_operator": True,
        "independent_human_reviewer_claimed": False,
        "source_policy_ratified": False,
        "notice_body_edited_or_replaced": False,
        "all_c01_to_c09_financial_gates_passed": False,
        "verified_bank_solvency_attested": False,
        "owner_transaction_signature_present": False,
        "public_notice_confers_spending_authority": False,
        "financial_release_authorized": False,
        "production_mutated": False
    }

def live_fetch():
    def gh(path):
        p = subprocess.run(["gh", "api", path], capture_output=True, timeout=18)
        require(p.returncode == 0, "PUBLIC_GITHUB_API_UNAVAILABLE")
        return parse_document(p.stdout)
    return (
        gh("repos/Emaren/wolochain/issues/184"),
        gh("repos/Emaren/wolochain")
    )

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inspect", action="store_true", required=True)
    a = p.parse_args(argv)
    try:
        data = inspect_notice(*live_fetch())
        print(json.dumps(data, sort_keys=True, indent=2))
        return 3  # even after expiry: never a funded PASS
    except (NoticeStop, OSError, subprocess.TimeoutExpired) as e:
        print(json.dumps({
            "schema": SCHEMA,
            "status":"STOP_PUBLIC_NOTICE_UNVERIFIED",
            "reason":str(e),
            "financial_release_authorized":False,
            "production_mutated":False
        }, sort_keys=True))
        return 2

if __name__ == "__main__":
    sys.exit(main())
