"""C03 physical writer-universe observation: fail-closed tests."""
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

S = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(S))
spec = importlib.util.spec_from_file_location("c03_universe", S / "settlement_c03_physical_writer_universe_hold.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

def props(name):
    return "\n".join((
        "Id=" + name, "LoadState=loaded", "ActiveState=active",
        "UnitFileState=enabled", "MainPID=42",
        "FragmentPath=/etc/systemd/system/mock.service",
        "Triggers=", "TriggeredBy=", "",
    ))

class UniverseTests(unittest.TestCase):
    def test_source_scope_incomplete(self):
        self.assertEqual(len(audit.OWNED), 18)
        self.assertNotIn("traffic-v2-forward-ledger-aoe2hdbets.timer", audit.OWNED)

    def test_listing_detects_traffic(self):
        x = "traffic-v2-forward-ledger-aoe2hdbets.timer loaded active\n"
        self.assertIn("traffic-v2-forward-ledger-aoe2hdbets.timer", audit.names_from_listing(x))
        with self.assertRaises(audit.ObservationError):
            audit.names_from_listing(x + x)
        with self.assertRaises(audit.ObservationError):
            audit.names_from_listing("traffic-!bad.timer loaded active\n")

    def test_properties_fail_on_invalid_identity(self):
        n = "aoe2hdbets-api.service"
        self.assertEqual(audit.parse_properties(props(n), n)["MainPID"], "42")
        with self.assertRaises(audit.ObservationError):
            audit.parse_properties(props(n), "aoe2hdbets-web.service")
        with self.assertRaises(audit.ObservationError):
            audit.parse_properties(props(n) + "Id=duplicate\n", n)

    def test_protected_incumbents(self):
        cases = (
            ("aoe2hdbets-web-prod.service", "PROTECTED_INCUMBENT_NO_AUTOMATED_STOP"),
            ("aoe2hdbets-api.service", "EXISTING_SOURCE_FENCE_SCOPE_NOT_PROVEN_EFFECTIVE"),
            ("traffic-v2-forward-ledger-aoe2hdbets.timer", "UNSCOPED_REVIEW_REQUIRED"),
        )
        for name, category in cases:
            self.assertEqual(audit.classify(name, audit.parse_properties(props(name), name))["category"], category)

    def test_root_required(self):
        with patch.object(audit.os, "geteuid", return_value=501):
            with self.assertRaises(audit.ObservationError):
                audit.observe()

    def test_realistic_mock_remains_hold(self):
        listing = "\n".join(n + " loaded active running" for n in (audit.ANCHORS | audit.CRITICAL_EXTERNAL))
        def fake_run(argv):
            return props(argv[-1]) if "show" in argv else listing
        def fake_db(name):
            return {"legacy_role": audit.owner.TARGETS[name], "implicit_owner_or_schema_bypass": True}
        with patch.object(audit.os, "geteuid", return_value=0), \
                patch.object(audit, "run", side_effect=fake_run), \
                patch.object(audit.owner, "inspect", side_effect=fake_db):
            result = audit.observe()
        self.assertEqual(result["status"], "HOLD")
        self.assertFalse(result["paymentAuthorized"])
        self.assertFalse(result["backupAuthorized"])
        self.assertFalse(result["fenceAndQuiescenceProven"])
        self.assertIn("traffic-v2-forward-ledger-aoe2hdbets.timer", result["unscopedUnits"])

    def test_active_timer_without_mainpid_is_still_active(self):
        name = "traffic-v2-forward-ledger-aoe2hdbets.timer"
        no_pid = props(name).replace("MainPID=42\n", "")
        row = audit.classify(name, audit.parse_properties(no_pid, name))
        self.assertTrue(row["active"])
        self.assertEqual(row["properties"]["MainPID"], "NOT_APPLICABLE_TIMER")
        self.assertEqual(row["category"], "UNSCOPED_REVIEW_REQUIRED")

    def test_dormant_template_is_retained_as_unscoped(self):
        template = "aoe2war-build@.service"
        listing = "\n".join(n + " loaded active running" for n in
                            (audit.ANCHORS | audit.CRITICAL_EXTERNAL | {template}))
        def fake_run(argv):
            if "show" in argv:
                self.assertNotEqual(argv[-1], template)
                return props(argv[-1])
            return listing
        def fake_db(name):
            return {"legacy_role":audit.owner.TARGETS[name],
                    "implicit_owner_or_schema_bypass":True}
        with patch.object(audit.os, "geteuid", return_value=0), \
                patch.object(audit, "run", side_effect=fake_run), \
                patch.object(audit.owner, "inspect", side_effect=fake_db):
            result = audit.observe()
        matches=[row for row in result["census"]["systemdUnits"] if row["unit"]==template]
        self.assertEqual(len(matches),1)
        self.assertEqual(matches[0]["category"],"UNSCOPED_REVIEW_REQUIRED")
        self.assertTrue(matches[0]["properties"]["InstanceReviewRequired"])
        self.assertFalse(result["backupAuthorized"])

if __name__ == "__main__":
    unittest.main()
