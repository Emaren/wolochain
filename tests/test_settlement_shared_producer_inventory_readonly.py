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

    def test_legacy_transfer_heartbeat_and_bare_app_timers_included(self):
        # Historical controlled-promotion PROD producer list includes this
        # exact finance timer, which lacks the usual app-name prefixes.
        for unit in (
            "aoe2-wolo-transfer-heartbeat.timer",
            "aoe2-wolo-transfer-heartbeat.service",
            "aoe2hdbets.timer",
            "aoe2hdbets.service",
            "aoe2war.timer",
            "aoe2war.service",
        ):
            with self.subTest(unit=unit):
                self.assertTrue(self.inv.relevant(unit))
        self.assertFalse(self.inv.relevant("wolochaind-mainnet.service"))
        self.assertFalse(self.inv.relevant("wolochain-mainnet-settlement.service"))

    def test_template_definitions_do_not_block_but_real_instances_do(self):
        fake_files = (
            "aoe2war-build@.service disabled -\n"
            "aoe2war-deps@.service disabled -\n"
            "aoe2war-speedos-cloudflare@.service disabled -\n"
            "aoe2war-build@job42.service enabled -\n"
            "aoe2war-build@.job42.service enabled -\n"
            "aoe2hdbets-web.service enabled -\n"
        )
        def fake(args):
            if args[0] == "list-units":
                return "aoe2hdbets-web.service loaded active running -\n"
            if args[0] == "list-unit-files":
                return fake_files
            raise AssertionError(args)
        with patch.object(self.inv, "run_systemctl", side_effect=fake):
            units, templates = self.inv.discover_inventory()
        self.assertEqual(templates, [
            "aoe2war-build@.service",
            "aoe2war-deps@.service",
            "aoe2war-speedos-cloudflare@.service",
        ])
        self.assertIn("aoe2war-build@job42.service", units)
        self.assertIn("aoe2war-build@.job42.service", units)
        self.assertNotIn("aoe2war-build@.service", units)

        with patch.object(self.inv, "discover_inventory",
                          return_value=(units, templates)):
            with patch.object(self.inv, "info", side_effect=lambda unit: (
                {"unit": unit, "active": True,
                 "isCandidateForExplicitMaintenanceReview": True}
                if unit != "aoe2war-build@job42.service"
                else (_ for _ in ()).throw(subprocess.CalledProcessError(
                    1, ["systemctl", "show"]))
            )):
                report = self.inv.inspect()
        self.assertEqual(
            report["templateDefinitionsNotServiceInstances"], templates)
        self.assertIn("aoe2war-build@job42.service",
                      report["unitsWithIncompleteInspection"])
        self.assertFalse(report["inventoryCompleteForDiscoveredUnits"])
        self.assertFalse(report["financialProducersFenced"])

    def test_template_only_is_informational_and_never_a_release_approval(self):
        templates = ["aoe2war-deps@.service"]
        with patch.object(self.inv, "discover_inventory",
                          return_value=([], templates)):
            report = self.inv.inspect()
        self.assertEqual(report["unitsWithIncompleteInspection"], [])
        self.assertTrue(report["inventoryCompleteForDiscoveredUnits"])
        self.assertEqual(report["templateDefinitionsNotServiceInstances"],
                         templates)
        self.assertFalse(report["productionCutoverAuthorized"])
        self.assertFalse(report["financialProducersFenced"])

    def test_uninstalled_expected_units_not_invented_or_show_queried(self):
        def fake(args):
            if args[0] == "list-units":
                return "aoe2hdbets-web.service loaded active running -\\n"
            if args[0] == "list-unit-files":
                return "aoe2-wolo-transfer-heartbeat.timer enabled -\\n"
            raise AssertionError("no absent exact-unit query expected")
        with patch.object(self.inv, "run_systemctl", side_effect=fake):
            names = self.inv.discover_units()
        self.assertEqual(names, [
            "aoe2-wolo-transfer-heartbeat.timer",
            "aoe2hdbets-web.service",
        ])
        self.assertNotIn("aoe2hdbets-api.service", names)

    def test_uninspectable_installed_unit_is_visible_and_fail_closed(self):
        actual = {
            "unit": "aoe2hdbets-web.service",
            "active": True,
            "isCandidateForExplicitMaintenanceReview": True,
        }
        with patch.object(self.inv, "discover_inventory", return_value=([
            "aoe2-wolo-transfer-heartbeat.timer", "aoe2hdbets-web.service",
        ], [])):
            def fake_info(name):
                if name.endswith(".timer"):
                    raise subprocess.CalledProcessError(1, ["systemctl", "show"])
                return actual
            with patch.object(self.inv, "info", side_effect=fake_info):
                report = self.inv.inspect()
        self.assertEqual(report["unitsWithIncompleteInspection"], [
            "aoe2-wolo-transfer-heartbeat.timer"
        ])
        self.assertFalse(report["inventoryCompleteForDiscoveredUnits"])
        self.assertIn("aoe2hdbets-web.service", report["activeCandidateUnitsToReview"])
        self.assertFalse(report["financialProducersFenced"])
        self.assertIn("aoe2hdbets-api.service", report["expectedNamedUnitsNotFound"])

    def test_fully_inspected_inventory_still_does_not_certify_freeze(self):
        with patch.object(self.inv, "discover_inventory", return_value=(["aoe2hdbets-web.service"], [])):
            with patch.object(self.inv, "info", return_value={
                "unit": "aoe2hdbets-web.service",
                "active": True,
                "isCandidateForExplicitMaintenanceReview": True,
            }):
                report = self.inv.inspect()
        self.assertTrue(report["inventoryCompleteForDiscoveredUnits"])
        self.assertEqual(report["unitsWithIncompleteInspection"], [])
        self.assertFalse(report["financialProducersFenced"])
        self.assertFalse(report["productionCutoverAuthorized"])

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
        with patch.object(self.inv, "discover_inventory", return_value=(["aoe2hdbets-web.service"], [])):
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
