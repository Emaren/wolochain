#!/usr/bin/env python3
"""No financial calls, credentials or live backup: synthetic archival restore tests."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "settlement_archived_journal_restore_drill.py"
SPEC = importlib.util.spec_from_file_location("settlement_archived_journal_restore_drill", SOURCE)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)


def sealed_archive(t: unittest.TestCase) -> tuple[Path, Path]:
    root = Path(t.enterContext(tempfile.TemporaryDirectory()))
    archive = root / "source" / "20261023T210040Z-two-settlement-node-untouched"
    dest = root / "isolated"
    dest.mkdir()
    (archive / "proof").mkdir(parents=True)
    for lane in ("primary", "founder"):
        directory = archive / "state" / lane / "requests"
        directory.mkdir(parents=True)
        (directory / "request.json").write_bytes(
            ("{\"lane\":\""+lane+"\",\"amount_uwolo\":\"100\"}").encode()
        )
        raw = (directory / "request.json").read_bytes()
        (archive / "proof" / (lane+"-files.sha256")).write_text(
            hashlib.sha256(raw).hexdigest()+"  ./requests/request.json\n"
        )
    (archive / "config").mkdir()
    (archive / "units").mkdir()
    (archive / "config" / "primary.env").write_text("PRIVATE_SENSITIVE_CONFIG=do-not-copy")
    cfg = (archive / "config" / "primary.env").read_bytes()
    (archive / "proof" / "config-files.sha256").write_text(
        hashlib.sha256(cfg).hexdigest()+"  config/primary.env\n"
    )
    return archive, dest


class RecoveryTests(unittest.TestCase):
    def test_copy_only_protected_journals_noncrediting(self):
        archive, dest = sealed_archive(self)
        info = MOD.restore(archive, dest, production=False)
        self.assertEqual(info["status"], "HOLD")
        self.assertFalse(info["c07_closed"])
        self.assertEqual(info["counts"]["total_archived_journal_files_restored"], 2)
        restored = dest / ("archived-financial-journal-only-" + archive.name)
        self.assertTrue((restored/"primary/requests/request.json").is_file())
        self.assertTrue((restored/"founder/requests/request.json").is_file())
        self.assertFalse((restored/"config").exists())
        self.assertFalse((restored/"units").exists())
        receipt = json.loads((restored/"RESTORE-HELD-RECEIPT.json").read_text())
        self.assertTrue(receipt["journal_restore_integrity_verified"])
        for value in ("encrypted_offhost_backup_verified","snapshot_matches_current_production",
                      "live_postgresql_wal_restored","current_financial_journals_restored",
                      "config_secrets_or_custody_keys_copied","signer_or_mainnet_service_started",
                      "financial_release_authorized","c06_closed","c07_closed",
                      "live_financial_runtime_mutated"):
            self.assertFalse(receipt[value])
        self.assertTrue(receipt["isolated_recovery_storage_written"])
        with self.assertRaises(MOD.Hold):
            MOD.restore(archive, dest, production=False)

    def test_tamper_rejected_before_destination_creation(self):
        archive, dest = sealed_archive(self)
        (archive/"state"/"founder"/"requests"/"request.json").write_text("CORRUPTED")
        with self.assertRaises(MOD.Hold):
            MOD.restore(archive, dest, production=False)
        self.assertEqual(list(dest.iterdir()), [])

    def test_unmanifested_journal_file_refused(self):
        archive, dest = sealed_archive(self)
        (archive/"state"/"primary"/"requests"/"extra.json").write_text("unknown")
        with self.assertRaises(MOD.Hold):
            MOD.restore(archive, dest, production=False)
        self.assertEqual(list(dest.iterdir()), [])

    def test_symlink_journal_file_refused(self):
        archive, dest = sealed_archive(self)
        file = archive/"state"/"primary"/"requests"/"request.json"
        file.unlink()
        file.symlink_to(archive/"config"/"primary.env")
        with self.assertRaises(MOD.Hold):
            MOD.restore(archive, dest, production=False)
        self.assertEqual(list(dest.iterdir()), [])

    def test_traversal_and_duplicate_manifest_refused(self):
        for payload in ("../private.json", "./requests/../private.json",
                        "/etc/passwd", "./requests/request.json\n"+
                        ("0"*64)+"  ./requests/request.json"):
            with self.subTest(payload=payload[:30]):
                archive, dest = sealed_archive(self)
                manifest = archive/"proof"/"primary-files.sha256"
                original = manifest.read_text().split("  ",1)[0]
                if payload.startswith("./requests/request.json\n"):
                    malicious = original+"  "+payload+"\n"
                else:
                    malicious = original+"  "+payload+"\n"
                manifest.write_text(malicious)
                with self.assertRaises(MOD.Hold):
                    MOD.restore(archive, dest, production=False)

    def test_missing_or_modified_config_manifest_fails_before_copy(self):
        archive, dest = sealed_archive(self)
        (archive/"config"/"primary.env").write_text("PRIVATE_CHANGED")
        with self.assertRaises(MOD.Hold):
            MOD.restore(archive, dest, production=False)
        self.assertEqual(list(dest.iterdir()), [])

    def test_production_rejects_nonapproved_archive_and_restore_root(self):
        archive, dest = sealed_archive(self)
        with self.assertRaises(MOD.Hold):
            MOD.restore(archive, dest, production=True)
        self.assertEqual(list(dest.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
