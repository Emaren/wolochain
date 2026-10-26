#!/usr/bin/env python3
"""A read-only projection cannot turn observations, CI or private JSON into money authority."""
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import settlement_release_frontier as F
import settlement_maintenance_board as BOARD

NOW = datetime(2026, 10, 26, 20, 0, tzinfo=timezone.utc)
HEAD, BASE = "a" * 40, "b" * 40


def api_fixture(change=None):
    reads = {}
    def api(endpoint, projection, deadline):
        if endpoint.endswith("/commits/main"):
            return {"sha": BASE}
        if "/check-runs?" in endpoint:
            checks = {"total_count": 1, "checks": [{"head_sha": HEAD, "status": "completed", "conclusion": "success"}]}
            if change == "wrong_head": checks["checks"][0]["head_sha"] = BASE
            if change == "truncated": checks["total_count"] = 101
            if change == "skipped": checks["checks"][0]["conclusion"] = "skipped"
            if change == "pending": checks["checks"][0]["status"] = "in_progress"
            if change == "failed": checks["checks"][0]["conclusion"] = "failure"
            if change == "missing": checks = {}
            if change == "malformed": checks["checks"][0]["conclusion"] = []
            return checks
        reads[endpoint] = reads.get(endpoint, 0) + 1
        repo_number = endpoint.removeprefix("repos/")
        pr = {"head": HEAD, "base": BASE, "url": "https://github.com/" + repo_number.replace("/pulls/", "/pull/"), "state": "open"}
        if change == "rotated" and reads[endpoint] > 1: pr["head"] = BASE
        if change == "forged_url": pr["url"] = "https://evil.invalid/forged"
        return pr
    return api


class ReleaseFrontierTests(unittest.TestCase):
    def test_default_is_offline_and_does_not_freshen_historical_runtime(self):
        with patch.object(F, "github_sources", side_effect=AssertionError("network forbidden")), patch.object(F.subprocess, "Popen", side_effect=AssertionError("child forbidden")):
            report = F.frontier(ROOT, now=NOW)
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(len(report["controls"]), 6)
        self.assertEqual(report["github"], {"status": "NOT_REFRESHED"})
        self.assertEqual(report["recorded_runtime"][-1]["hd_build_id"], "s5lkg31SfI18yR-eQN8iT")
        for observation in report["recorded_runtime"]:
            self.assertEqual(observation["provenance"], "HISTORICAL")
            self.assertEqual(observation["freshness"], "STALE")
            self.assertFalse(observation["current_runtime_verified"])
        self.assertFalse(report["financial_release_authorized"])
        self.assertFalse(report["website_release_authorized"])
        self.assertTrue(all(v is None for v in report["financial_totals"].values()))
        encoded = json.dumps(report)
        self.assertNotIn("raw_private_receipt_sha256", encoded)
        self.assertNotIn("environment", encoded)
        self.assertNotIn("993289", encoded)

    def test_clock_skew_old_and_future_observations_never_become_current(self):
        for delta, expected in ((-901, "STALE"), (-900, "RECENT_RECORDED"), (6, "CLOCK_INVALID")):
            row = F.age((NOW + timedelta(seconds=delta)).isoformat(), NOW)
            self.assertEqual(row["freshness"], expected)
            self.assertFalse(row["current_runtime_verified"])
        for stamp in ("2026-10-26", "2026-10-26T20:00:00+01:00", "broken"):
            with self.subTest(stamp=stamp), self.assertRaises(F.FrontierFailure): F.age(stamp, NOW)

    def test_exact_head_public_ci_is_source_observation_not_authority(self):
        report = F.github_sources(NOW, api_fixture())
        for label, _, _ in F.TARGETS:
            self.assertEqual(report[label]["head"], HEAD)
            self.assertEqual(report[label]["source_ci"], "PASS")
            self.assertEqual(report[label]["required_check_completeness"], "NOT_EVALUATED")
            self.assertEqual(report[label]["scope"], "REQUESTED_PR_CHECKS_NOT_PRODUCTION_HEALTH_OR_RELEASE_BLOCKER")
            self.assertEqual(report[label]["provenance"], "TOOL_OBSERVED")
        with patch.object(F, "github_sources", return_value=report): result = F.frontier(ROOT, refresh_github=True, now=NOW)
        self.assertEqual(result["global_solvency"], "UNKNOWN")
        self.assertEqual(result["custody_capability"], "UNAVAILABLE")
        self.assertFalse(result["financial_release_authorized"])

    def test_wrong_head_forged_rotating_missing_and_incomplete_checks_are_unknown(self):
        for change in ("wrong_head", "truncated", "missing", "rotated", "forged_url", "malformed"):
            with self.subTest(change=change):
                result = F.github_sources(NOW, api_fixture(change))
                self.assertTrue(all(result[label]["status"] == "UNKNOWN" for label, _, _ in F.TARGETS))
        for change, expected in (("skipped", "UNKNOWN"), ("pending", "PENDING"), ("failed", "FAIL")):
            result = F.github_sources(NOW, api_fixture(change))
            self.assertTrue(all(result[label]["source_ci"] == expected for label, _, _ in F.TARGETS))

    def test_unavailable_api_never_leaks_diagnostics_or_funds(self):
        def broken(*args): raise OSError("SECRET_PRIVATE_ENV")
        encoded = json.dumps(F.github_sources(NOW, broken))
        self.assertNotIn("SECRET_PRIVATE_ENV", encoded)
        self.assertNotIn("PASS", encoded)

    def operator_packet(self, temp, **changes):
        p = Path(temp).resolve() / "operator.json"
        packet = {"schema": F.OPERATOR_SCHEMA, "observed_at_utc": NOW.isoformat(),
                  "custody": {"service_state": "ACTIVE", "private_8094_listener": True}}
        packet.update(changes)
        p.write_text(json.dumps(packet))
        p.chmod(0o600)
        return p

    def test_private_operator_active_custody_is_only_reported_and_still_held(self):
        with tempfile.TemporaryDirectory() as temp:
            p = self.operator_packet(temp)
            result = F.frontier(ROOT, operator_observation=p, now=NOW)
        self.assertEqual(result["operator_observation"]["provenance"], "OPERATOR_REPORTED")
        self.assertFalse(result["operator_observation"]["current_runtime_verified"])
        self.assertEqual(result["custody_capability"], "UNAVAILABLE")
        self.assertFalse(result["financial_release_authorized"])

    def test_operator_forgery_sensitive_fields_wrong_modes_links_and_unbounded_json_denied(self):
        for field, value in (("provenance", "TOOL_OBSERVED"), ("financial_release_authorized", True),
                             ("bank_assets", 999), ("secret", "PRIVATE"),
                             ("custody", {"service_state": [], "private_8094_listener": True}),
                             ("producer_counts", {"scoped_units": 22, "active_apps": 4, "armed_timers": 7, "inactive_oneshots": 7}),
                             ("website", {"source_sha": HEAD, "build_id": "\nSECRET", "compiled_version": "v1"})):
            with tempfile.TemporaryDirectory() as temp:
                p = self.operator_packet(temp, **{field: value})
                with self.subTest(field=field), self.assertRaises(F.FrontierFailure): F.private_operator_packet(p)
        with tempfile.TemporaryDirectory() as temp:
            p = self.operator_packet(temp)
            p.chmod(0o644)
            with self.assertRaises(F.FrontierFailure): F.private_operator_packet(p)
            p.chmod(0o600)
            link = Path(temp) / "link.json"
            link.symlink_to(p)
            with self.assertRaises(F.FrontierFailure): F.private_operator_packet(link)
            link.unlink()
            os.link(p, link)
            with self.assertRaises(F.FrontierFailure): F.private_operator_packet(p)
            link.unlink()
            p.write_bytes(b" " * (F.MAX_BYTES + 1))
            with self.assertRaises(F.FrontierFailure): F.private_operator_packet(p)

    def test_index_or_evidence_rotation_between_audit_and_parse_denied(self):
        original = F.safe_read
        reads = 0
        def rotated(root, relative):
            nonlocal reads
            raw = original(root, relative)
            if relative == F.INDEX:
                reads += 1
                if reads > 1: return raw + b" "
            return raw
        with patch.object(F, "safe_read", side_effect=rotated), self.assertRaisesRegex(F.FrontierFailure, "CHECKLIST_CHANGED"):
            F.frontier(ROOT, now=NOW)
        def corrupt(root, relative):
            raw = original(root, relative)
            return raw + b" " if "runtime-observation" in relative else raw
        with patch.object(F, "safe_read", side_effect=corrupt), self.assertRaisesRegex(F.FrontierFailure, "EVIDENCE_CHANGED"):
            F.frontier(ROOT, now=NOW)

    def test_missing_canonical_hold_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises((F.AuditFailure, OSError)): F.frontier(Path(temp), now=NOW)
        with patch.object(F, "audit", side_effect=F.AuditFailure("RELEASE_HOLD_REMOVED")), self.assertRaises(F.AuditFailure):
            F.frontier(ROOT, now=NOW)

    def test_bounded_source_runner_times_out_and_reaps_process_group(self):
        children = []
        real = subprocess.Popen
        def track(*args, **kwargs):
            process = real(*args, **kwargs)
            children.append(process)
            return process
        with patch.object(F.subprocess, "Popen", side_effect=track):
            with self.assertRaisesRegex(F.FrontierFailure, "TIMEOUT"):
                F.bounded_command([sys.executable, "-c", "import time; time.sleep(10)"], time.monotonic() + .1)
            with self.assertRaisesRegex(F.FrontierFailure, "SIZE_LIMIT"):
                F.bounded_command([sys.executable, "-c", "print('x' * 300000)"], time.monotonic() + 2)
        self.assertTrue(all(process.poll() is not None for process in children))

    def test_bounded_source_runner_rejects_failed_invalid_and_duplicate_json(self):
        for code in ("raise SystemExit(1)", "print('{}{}')", "print('{\"a\":1,\"a\":2}')"):
            with self.subTest(code=code), self.assertRaises((F.FrontierFailure, F.AuditFailure)):
                F.bounded_command([sys.executable, "-c", code], time.monotonic() + 2)
        self.assertEqual(F.bounded_command([sys.executable, "-c", "print('{}')"], time.monotonic() + 2), {})

    def test_cli_success_is_hold_exit_three_and_no_mutations(self):
        stream = io.StringIO()
        with redirect_stdout(stream): code = BOARD.main(["--root", str(ROOT), "--frontier"])
        self.assertEqual(code, 3)
        report = json.loads(stream.getvalue())
        for flag in ("financial_release_authorized", "website_release_authorized", "production_mutated", "wallet_accessed", "nonce_consumed"):
            self.assertIs(report[flag], False)


if __name__ == "__main__":
    unittest.main()
