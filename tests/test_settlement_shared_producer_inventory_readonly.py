"""Offline fail-closed HD+DE WOLO producer candidate inventory contracts."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/settlement-shared-producer-inventory-readonly.py"


def load_module():
    spec = importlib.util.spec_from_file_location("wolo_hd_de_inventory", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SharedHdDeProducerInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inv = load_module()

    def test_all_protected_wolo_services_excluded(self):
        for name in self.inv.PROTECTED_WOLO:
            self.assertFalse(self.inv.relevant(name))

    def test_app_service_and_timer_discovery_includes_unloaded_default(self):
        def fake(args):
            if args[0] == "list-units":
                return (
                    "aoe2hdbets-web.service loaded active running -\n"
                    "aoe2dewarwagers-sync.timer loaded active waiting -\n"
                    "wolochaind-mainnet.service loaded active running -\n"
                )
            if args[0] == "list-unit-files":
                return (
                    "aoe2hdbets-financial-worker.service enabled -\n"
                    "aoe2dewarwagers-api.service enabled -\n"
                )
            raise AssertionError(args)

        with patch.object(self.inv, "run_systemctl", side_effect=fake):
            names = self.inv.discover_units()
        self.assertIn("aoe2hdbets-financial-worker.service", names)
        self.assertIn("aoe2dewarwagers-sync.timer", names)
        self.assertIn("aoe2hdbets-web.service", names)
        self.assertIn("aoe2dewarwagers-api.service", names)
        self.assertNotIn("wolochaind-mainnet.service", names)

    def test_only_allowlisted_key_names_pass_through(self):
        fields = b"DATABASE_URL=postgres://a:SECRET@db/s\0" + (
            b"WOLO_SETTLEMENT_AUTH_TOKEN=VERY_SECRET\0"
            b"WOLO_INTERNAL_RPC_URL=http://private-node\0"
            b"PASSWORD=hidden\0"
        )
        class FakeFile:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self, limit): return fields

        with patch.object(Path, "open", return_value=FakeFile()):
            ok, keys = self.inv.process_keys("123")
        self.assertTrue(ok)
        self.assertEqual(keys, [
            "DATABASE_URL", "WOLO_INTERNAL_RPC_URL", "WOLO_SETTLEMENT_AUTH_TOKEN"
        ])
        self.assertNotIn("SECRET", json.dumps(keys))
        self.assertNotIn("PASSWORD", json.dumps(keys))

    def test_incomplete_or_unknown_proc_never_certifies_finance(self):
        with patch.object(self.inv, "discover_units", return_value=["aoe2hdbets-web.service"]):
            with patch.object(self.inv, "info", return_value={
                "unit": "aoe2hdbets-web.service",
                "active": True,
                "isCandidateForExplicitMaintenanceReview": True,
            }):
                report = self.inv.inspect()
        self.assertFalse(report["financialProducersFenced"])
        self.assertFalse(report["financialDrainCertified"])
        self.assertFalse(report["productionCutoverAuthorized"])
        self.assertFalse(report["commandsMutatedServices"])
        self.assertIn("aoe2hdbets-web.service", report["activeCandidateUnitsToReview"])

    def test_mutating_modes_rejected_before_root_access(self):
        for value in ("--stop", "--freeze", "--apply", "--resume", "--restart"):
            with self.subTest(flag=value):
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), value],
                    check=False, capture_output=True, text=True, timeout=5
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn("only read-only", result.stderr)

    def test_source_disallows_systemd_or_wallet_mutation(self):
        source = SCRIPT.read_text()
        import re
        for pattern in (
            r"\bsystemctl\s+(?:stop|start|restart|reload|disable|enable|daemon-reload)\b",
            r"\b(?:rm|mv|cp|chmod|chown|install|kill|pkill)\s+",
            r"\b(?:wolochaind|psql|prisma)\s+",
        ):
            self.assertNotRegex(source, pattern)

    def test_refuses_incomplete_unit_list(self):
        with patch.object(self.inv, "run_systemctl", side_effect=[
            "aoe2hdbets-worker.service loaded active running\n" * (self.inv.MAX_UNITS + 1),
            "",
        ]):
            with self.assertRaisesRegex(ValueError, "bounded limit"):
                self.inv.discover_units()


if __name__ == "__main__":
    unittest.main()
