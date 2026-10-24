"""Disposable filesystem durability and concurrency tests, not real-human approvals."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("nonce_store",ROOT/"scripts/settlement_maintenance_nonce_store.py")
mod=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=mod
spec.loader.exec_module(mod)
NONCE="a"*32
PACKET="b"*64


class DisposableNonceStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.folder=Path(self.temp.name)/"nonce"
        self.folder.mkdir(mode=0o700)

    def tearDown(self):
        self.temp.cleanup()

    def test_single_use_retained_across_new_calls(self):
        result=mod.reserve_once(self.folder,NONCE,PACKET,"live_capture")
        self.assertTrue(result["nonce_reserved"])
        self.assertFalse(result["production_operation_authorized"])
        self.assertFalse(result["human_enrollment_proven"])
        self.assertFalse(result["independent_rollback_witness_verified"])
        with self.assertRaisesRegex(mod.ReservationRefused,"NONCE_ALREADY_RESERVED"):
            mod.reserve_once(self.folder,NONCE,PACKET,"live_capture")

    def test_atomic_racing_reservation_only_one_wins(self):
        def contender(_):
            try:
                mod.reserve_once(self.folder,NONCE,PACKET,"live_capture")
                return True
            except mod.ReservationRefused:
                return False
        with ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(contender,range(12)))
        self.assertEqual(sum(results),1)

    def test_phase_change_cannot_reuse_nonce(self):
        mod.reserve_once(self.folder,NONCE,PACKET,"live_capture")
        with self.assertRaisesRegex(mod.ReservationRefused,"NONCE_ALREADY_RESERVED"):
            mod.reserve_once(self.folder,NONCE,"c"*64,"offline_verify")

    def test_corrupted_existing_record_blocks_new_reservation(self):
        mod.reserve_once(self.folder,NONCE,PACKET,"live_capture")
        entry=next(self.folder.glob("nonce-*.json"))
        entry.write_text("{}")
        with self.assertRaises(mod.ReservationRefused):
            mod.reserve_once(self.folder,"c"*32,PACKET,"offline_verify")

    def test_foreign_entry_and_symlink_refused(self):
        (self.folder/"unexpected").write_text("forbidden")
        with self.assertRaisesRegex(mod.ReservationRefused,"FOREIGN_NONCE_DIRECTORY_ENTRY"):
            mod.reserve_once(self.folder,NONCE,PACKET,"live_capture")
        (self.folder/"unexpected").unlink()
        with tempfile.TemporaryDirectory() as other:
            link=Path(other)/"link"
            link.symlink_to(self.folder,target_is_directory=True)
            with self.assertRaises(OSError):
                mod.reserve_once(link,NONCE,PACKET,"live_capture")

    def test_untrusted_directory_mode_refused(self):
        self.folder.chmod(0o777)
        with self.assertRaisesRegex(mod.ReservationRefused,"NONCE_DIRECTORY_OWNERSHIP_UNSAFE"):
            mod.reserve_once(self.folder,NONCE,PACKET,"live_capture")

    def test_bad_nonce_digest_budget_rejected_without_record(self):
        for nonce,packet,phase in (
            ("0"*32,PACKET,"live_capture"),
            ("Z"*32,PACKET,"live_capture"),
            (NONCE,"no","live_capture"),
            (NONCE,PACKET,"financial_release")):
            with self.assertRaises(mod.ReservationRefused):
                mod.reserve_once(self.folder,nonce,packet,phase)
        self.assertFalse(list(self.folder.iterdir()))

    def test_record_is_mode_0600_and_canonical(self):
        mod.reserve_once(self.folder,NONCE,PACKET,"live_capture")
        path=next(self.folder.glob("nonce-*.json"))
        self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
        self.assertEqual(path.read_bytes(),mod.canonical(json.loads(path.read_bytes())))

    def test_root_rollback_not_prevented_by_local_disk_alone(self):
        # Positive demonstration of an OPEN security dependency, not an authority test:
        # a privileged adversary can delete local records. Only an independent,
        # monotonic witness/checkpoint can certify no ledger rollback.
        mod.reserve_once(self.folder,NONCE,PACKET,"live_capture")
        next(self.folder.glob("nonce-*.json")).unlink()
        result=mod.reserve_once(self.folder,NONCE,PACKET,"live_capture")
        self.assertFalse(result["independent_rollback_witness_verified"])
        self.assertFalse(result["production_operation_authorized"])


if __name__=="__main__":
    unittest.main()
