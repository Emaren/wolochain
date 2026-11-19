#!/usr/bin/env python3
"""Source-only negative tests for the four exact HD website SQL blobs."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/c03_web_database_admission_manifest_check.py"
spec = importlib.util.spec_from_file_location("c03_webdb_checker", SCRIPT)
assert spec is not None and spec.loader is not None
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def manifest() -> dict:
    return json.loads(checker.MANIFEST.read_text())


class AdmissionManifestTests(unittest.TestCase):
    def assert_hold(self, candidate: dict) -> None:
        with self.assertRaises(checker.SourceHold):
            checker.check_manifest(candidate)

    def test_real_source_hashes_and_permits_are_held(self):
        r = checker.verify()
        self.assertEqual(r["sql_files_verified"], 4)
        self.assertFalse(r["installation_authorized"])
        self.assertFalse(r["financial_authorized"])
        self.assertFalse(r["actual_HBA_verified"])
        self.assertFalse(r["live_privacy_verified"])
        self.assertEqual(r["gate_C03"], "OPEN")

    def test_de_database_forgery_denied(self):
        m = manifest()
        m["target_database"] = "aoe2de_db"
        self.assert_hold(m)

    def test_funded_or_live_install_forgery_denied(self):
        for k, v in (("production_install_authorized", True),
                     ("finance_funding", "AUTHORIZED")):
            m = manifest()
            m[k] = v
            self.assert_hold(m)

    def test_missing_maintenance_permit_denied(self):
        for index in range(2):
            m = manifest()
            c = m["contracts"][index]
            c["prerequisite_physical"] = [
                x for x in c["prerequisite_physical"]
                if "permit" not in x
            ]
            self.assert_hold(m)

    def test_unsigned_installed_status_denied(self):
        m = manifest()
        m["contracts"][0]["installed"] = True
        self.assert_hold(m)

    def test_forged_source_sha_denied(self):
        m = manifest()
        m["contracts"][0]["install"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "manifest.json"
            p.write_text(json.dumps(m))
            with self.assertRaises(checker.SourceHold):
                checker.verify(manifest=p)

    def test_forged_source_git_blob_denied(self):
        m = manifest()
        m["contracts"][1]["inverse"]["git_blob"] = "0" * 40
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "manifest.json"
            p.write_text(json.dumps(m))
            with self.assertRaises(checker.SourceHold):
                checker.verify(manifest=p)

    def test_actual_file_byte_tamper_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for relative in checker.EXPECTED_SHA256:
                dst = root / relative
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, dst)
            relative = "scripts/c03_library_public_projection_candidate.sql"
            f = root / relative
            f.write_bytes(f.read_bytes() + b"-- suspicious trailing SQL\n")
            with self.assertRaises(checker.SourceHold):
                checker.verify(root=root)

    def test_missing_file_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(checker.SourceHold):
                checker.verify(root=Path(tmp))

    def test_duplicate_or_reordered_sql_contract_denied(self):
        m = manifest()
        m["contracts"] = list(reversed(m["contracts"]))
        self.assert_hold(m)

    def test_no_execute_cli_exists(self):
        p = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--execute"],
            capture_output=True, text=True, check=False
        )
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("unrecognized arguments", p.stderr)

    def test_only_nonauthorizing_plan_cli(self):
        p = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--plan"],
            capture_output=True, text=True, check=False
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('"installation_authorized": false', p.stdout)
        self.assertIn("C03_WEB_DB_SOURCE_ONLY_NOT_ROOT_OR_SQL_PERMIT", p.stdout)


if __name__ == "__main__":
    unittest.main()
