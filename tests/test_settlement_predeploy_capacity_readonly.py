"""Offline bounded capacity gate tests; no VPS mounts, secrets, wallets, or writes."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "settlement-predeploy-capacity-readonly.py"


def load_script():
    spec = importlib.util.spec_from_file_location("wolo_predeploy_capacity", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ReleaseCapacityContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = load_script()

    def simulation(self, root_gib: float, wolo_gib: float,
                   *, mounted=True, same_device=False, linked=False):
        s = self.s
        def stat_path(path):
            device = 1 if path == s.ROOT else (1 if same_device else 2)
            return SimpleNamespace(st_dev=device)
        def statvfs_path(path):
            free = root_gib if path == s.ROOT else wolo_gib
            return SimpleNamespace(f_bavail=int(free * 128), f_frsize=s.GIB // 128)
        with patch.object(Path, "is_symlink", return_value=linked), \
             patch.object(Path, "is_dir", return_value=True), \
             patch.object(Path, "stat", new=stat_path), \
             patch.object(s.os.path, "ismount", return_value=mounted), \
             patch.object(s.os, "statvfs", side_effect=statvfs_path):
            return s.inspect()

    def test_both_filesystems_must_clear_independent_policy_floors(self):
        result = self.simulation(9, 26)
        self.assertEqual(result["status"], "CAPACITY_POLICY_FLOOR_PASS_NOT_RELEASE_APPROVAL")
        self.assertTrue(result["root"]["minimumHeadroomPresent"])
        self.assertTrue(result["woloStateVolume"]["minimumHeadroomPresent"])
        self.assertFalse(result["productionAuthorized"])
        self.assertFalse(result["financialDrainCertified"])
        self.assertFalse(result["rollbackCertified"])
        self.assertFalse(result["filesystemMutations"])

    def test_low_root_blocks_even_when_wolo_disk_has_space(self):
        result = self.simulation(4.5, 50)
        self.assertEqual(result["status"], "BLOCKED_INSUFFICIENT_PREDEPLOY_HEADROOM")
        self.assertFalse(result["root"]["minimumHeadroomPresent"])
        self.assertTrue(result["woloStateVolume"]["minimumHeadroomPresent"])

    def test_low_wolo_volume_blocks_even_when_root_has_space(self):
        result = self.simulation(20, 7)
        self.assertEqual(result["status"], "BLOCKED_INSUFFICIENT_PREDEPLOY_HEADROOM")
        self.assertFalse(result["woloStateVolume"]["minimumHeadroomPresent"])

    def test_unmounted_or_root_fallback_refused(self):
        for variation in ({"mounted": False}, {"same_device": True}, {"linked": True}):
            with self.subTest(variation=variation):
                with self.assertRaises(ValueError):
                    self.simulation(100, 100, **variation)

    def test_exact_boundaries(self):
        result = self.simulation(self.s.MIN_ROOT_FREE_GIB, self.s.MIN_WOLO_FREE_GIB)
        self.assertEqual(result["status"], "CAPACITY_POLICY_FLOOR_PASS_NOT_RELEASE_APPROVAL")

    def test_mutating_modes_rejected(self):
        for mode in ("--prune", "--backup", "--install", "--deploy", "--fix", "--mount"):
            with self.subTest(mode=mode):
                p = subprocess.run(
                    [sys.executable, str(SCRIPT), mode],
                    capture_output=True, text=True, timeout=5, check=False,
                )
                self.assertEqual(p.returncode, 2)
                self.assertIn("only --inspect", p.stderr)

    def test_no_subprocess_or_storage_change_primitives(self):
        source = SCRIPT.read_text()
        for forbidden in (
            "import subprocess", "from subprocess", "os.system(",
            "subprocess.run(", "os.unlink(", "os.remove(", "shutil.rmtree(",
            "os.chmod(", "os.chown(", "os.rename(", "write_text(", "write_bytes(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        self.assertIn("Never prune chain data", source)


if __name__ == "__main__":
    unittest.main()
