#!/usr/bin/env python3
"""Hermetic C08 public notice 24h fail-closed tests. No GitHub/network needed."""
import contextlib
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "scripts/settlement_solo_owner_public_notice_hold.py"
spec = importlib.util.spec_from_file_location("c08_notice_source", SRC)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
CREATED = datetime(2026,11,7,10,22,33,tzinfo=timezone.utc)
EXPIRY = CREATED + timedelta(seconds=86400)

def sample():
    body = "PUBLIC CENTRALIZED WOLO ONE HUMAN OWNER SAFETY NOTICE. " * 28
    issue = {"number":184,"html_url":m.ISSUE_URL,"state":"open","closed_at":None,
             "created_at":m.CREATED_UTC,"user":{"login":"Emaren"},"body":body}
    repo = {"full_name":"Emaren/wolochain","visibility":"public","has_issues":True}
    return issue,repo,hashlib.sha256(body.encode()).hexdigest()

class PublicNoticeHold(unittest.TestCase):
    def setUp(self):
        self.issue,self.repo,bodysha=sample()
        self.patcher=patch.object(m,"EXACT_PUBLIC_BODY_SHA256",bodysha)
        self.patcher.start();self.addCleanup(self.patcher.stop)
    def inspect(self,clock=CREATED):
        return m.inspect_notice(self.issue,self.repo,now=clock)
    def stop(self,reason,clock=CREATED):
        with self.assertRaisesRegex(m.NoticeStop,reason):
            self.inspect(clock)
    def test_before_notice_complete_stays_hard_hold(self):
        a=self.inspect(CREATED+timedelta(hours=23))
        self.assertEqual(a["status"],"HOLD_PUBLIC_NOTICE_24H_STILL_RUNNING")
        for k in ("financial_release_authorized","source_policy_ratified",
                  "owner_transaction_signature_present","all_c01_to_c09_financial_gates_passed",
                  "public_notice_confers_spending_authority","verified_bank_solvency_attested",
                  "independent_human_reviewer_claimed","production_mutated"):
            self.assertIs(a[k],False)
    def test_one_second_before_expiry_does_not_pass(self):
        self.assertTrue(self.inspect(EXPIRY-timedelta(seconds=1))["status"].startswith("HOLD"))
    def test_exact_expiry_is_time_only_not_release(self):
        a=self.inspect(EXPIRY)
        self.assertEqual(a["status"],"PASS_NOTICE_TIME_ONLY_ALL_FINANCIAL_GATES_HOLD")
        self.assertFalse(a["financial_release_authorized"])
        self.assertFalse(a["source_policy_ratified"])
    def test_after_expiry_keeps_financial_authority_false(self):
        self.assertFalse(self.inspect(EXPIRY+timedelta(days=100))["financial_release_authorized"])
    def test_wrong_author_rejected(self):
        self.issue["user"]["login"]="other"
        self.stop("NOTICE_AUTHOR_WRONG")
    def test_relocated_or_number_changed_issue_rejected(self):
        self.issue["number"]=185
        self.stop("NOTICE_ISSUE_OR_STATE_UNTRUSTED")
    def test_closed_issue_rejected(self):
        self.issue["state"]="closed"
        self.stop("NOTICE_ISSUE_OR_STATE_UNTRUSTED")
    def test_pull_request_substitution_rejected(self):
        self.issue["pull_request"]={}
        self.stop("NOTICE_ISSUE_OR_STATE_UNTRUSTED")
    def test_repo_private_rejected(self):
        self.repo["visibility"]="private"
        self.stop("NOTICE_MUST_BE_ON_PUBLIC_REPOSITORY")
    def test_edited_public_notice_sha_stops(self):
        self.issue["body"]+=" changed after publication"
        self.stop("PUBLIC_NOTICE_BODY_SHA256_CHANGED")
    def test_published_utc_changed_rejected(self):
        self.issue["created_at"]="2026-11-07T11:22:33Z"
        self.stop("NOTICE_PUBLICATION_TIMESTAMP_CHANGED")
    def test_short_or_missing_body_rejected(self):
        self.issue["body"]="x"
        self.stop("NOTICE_BODY_INVALID")
    def test_clock_before_original_publication_rejected(self):
        self.stop("NOTICE_CLOCK_BEFORE_PUBLICATION",CREATED-timedelta(seconds=1))
    def test_naive_local_clock_rejected(self):
        with self.assertRaisesRegex(m.NoticeStop,"TRUSTED_LOCAL_UTC_REQUIRED"):
            self.inspect(datetime(2026,11,7,10,22,33))
    def test_duplicate_json_keys_stop(self):
        malformed=b'{"a":1,"a":2}'
        with self.assertRaises(m.NoticeStop):
            m.parse_document(malformed)
    def test_live_cli_verified_notice_returns_three_never_funded_pass(self):
        with (patch.object(m,"live_fetch",return_value=(self.issue,self.repo)),
              patch.object(m,"inspect_notice",wraps=m.inspect_notice)):
            out=io.StringIO()
            with contextlib.redirect_stdout(out):
                # Under any actual current date the normal notice state is HOLD or TIME_ONLY.
                status=m.main(["--inspect"])
        self.assertEqual(status,3)
        self.assertIn('"financial_release_authorized": false',out.getvalue())
    def test_live_cli_wrong_publication_stops(self):
        self.issue["body"]="FORGED"
        with patch.object(m,"live_fetch",return_value=(self.issue,self.repo)):
            out=io.StringIO()
            with contextlib.redirect_stdout(out):
                status=m.main(["--inspect"])
        self.assertEqual(status,2)
        self.assertIn("STOP_PUBLIC_NOTICE_UNVERIFIED",out.getvalue())

if __name__=="__main__":
    unittest.main()
