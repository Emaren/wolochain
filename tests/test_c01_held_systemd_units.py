"""C01 systemd units are source-staged HOLD templates, not permission to activate money."""
from __future__ import annotations

import configparser
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "deploy" / "systemd"
PIN = "f7b5a74928e041a6a90ac983d87649e0484677a4"
ROLES = (
    ("wolo-satchel-c01.service", "wolo-satchel", "custody", "wolosatcheld"),
    ("wolo-reviewer-c01.service", "wolo-reviewer", "reviewer", "woloreviewerd"),
)

def load(filename: str):
    raw = (DIR / filename).read_text()
    c = configparser.ConfigParser(interpolation=None, strict=True)
    c.read_string(raw)
    return raw, c

class C01HeldUnitTests(unittest.TestCase):
    def test_two_distinct_static_constrained_units(self):
        self.assertEqual(set(p.name for p in DIR.glob("*.service")), {x[0] for x in ROLES})
        users = set()
        for filename, user, role, binary in ROLES:
            with self.subTest(filename=filename):
                raw, c = load(filename)
                self.assertEqual(c.sections(), ["Unit", "Service"])
                self.assertFalse(c.has_section("Install"))
                self.assertEqual(c["Unit"]["conditionpathexists"],
                                 f"/etc/wolo-financial-c01/{role}.json")
                self.assertEqual(c["Service"]["user"], user)
                self.assertEqual(c["Service"]["group"], user)
                self.assertEqual(c["Service"]["restart"], "no")
                self.assertEqual(c["Service"]["umask"], "0077")
                self.assertEqual(c["Service"]["workingdirectory"],
                                 f"/var/lib/wolo-financial-role-state/v1/{role}")
                self.assertEqual(c["Service"]["readwritepaths"],
                                 c["Service"]["workingdirectory"])
                self.assertEqual(c["Service"]["execstart"],
                                 f"/usr/local/libexec/wolo-c01/{PIN}/{binary} "
                                 f"--config /etc/wolo-financial-c01/{role}.json")
                users.add(user)
                for required in ("nonewprivileges", "privatetmp", "privatedevices",
                                 "protecthome", "protectsystem", "restrictnamespaces",
                                 "lockpersonality", "memorymax", "tasksmax",
                                 "restrictaddressfamilies", "ipaddressdeny",
                                 "ipaddressallow"):
                    self.assertIn(required, c["Service"])
                self.assertEqual(c["Service"]["protectsystem"], "strict")
                self.assertEqual(c["Service"]["ipaddressdeny"], "any")
                self.assertEqual(c["Service"]["ipaddressallow"], "localhost")
                self.assertEqual(c["Service"]["capabilityboundingset"], "")
                self.assertEqual(c["Service"]["ambientcapabilities"], "")
                self.assertNotIn("environment", c["Service"])
                self.assertNotIn("environmentfile", c["Service"])
                self.assertNotIn("execstartpre", c["Service"])
                self.assertNotIn("execstoppost", c["Service"])
                self.assertNotIn("8092", raw)
                self.assertNotIn("8093", raw)
                self.assertNotIn("wolochaind-mainnet", raw)
        self.assertEqual(len(users), 2)

    def test_source_templates_are_not_financial_authorizations(self):
        for filename, _, _, _ in ROLES:
            raw, c = load(filename)
            self.assertIn("NOT an activation permit", raw)
            self.assertFalse(c.has_section("Install"))
            self.assertEqual(c["Unit"]["startlimitburst"], "1")
            self.assertEqual(c["Unit"]["startlimitintervalsec"], "300s")
            self.assertEqual(c["Service"]["type"], "simple")

if __name__ == "__main__":
    unittest.main()
