from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SPEC = importlib.util.spec_from_file_location(
    "settlement_de_producer_source_map", SCRIPTS / "settlement_de_producer_source_map.py"
)
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUDIT
SPEC.loader.exec_module(AUDIT)


def fixture(root: Path) -> None:
    grouped: dict[str, list[str]] = {}
    for file, marker, _role in AUDIT.SENTINELS:
        grouped.setdefault(file, []).append(marker)
    for relative, markers in grouped.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(markers) + "\n", encoding="utf-8")


class DeProducerSourceMapTests(unittest.TestCase):
    def test_all_candidate_edges_are_source_observations_not_financial_certificates(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture(root)
            data = AUDIT.inspect(root, {"state": "LOCAL_CLEAN_GIT_ONLY", "head": "a" * 40})
            self.assertTrue(data["known_de_source_edges_intact"])
            self.assertGreaterEqual(len(data["observations"]), 18)
            self.assertTrue(all(v["status"] == "SOURCE_OBSERVED" for v in data["observations"]))
            for flag in ("complete_financial_producer_inventory_proven", "financial_producers_fenced",
                         "independent_de_signer_exclusion_proven", "mainnet_settlement_cutover_authorized",
                         "website_release_authorized", "satchel_authorized"):
                self.assertIs(data[flag], False)
            self.assertIn("conditional_direct_signer", {v["role"] for v in data["observations"]})
            self.assertIn("public_read_trigger", {v["role"] for v in data["observations"]})

    def test_changed_source_and_missing_file_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture(root)
            path = root / "lib" / "woloBetSettlement.ts"
            path.write_text("export {}\n")
            data = AUDIT.inspect(root)
            self.assertFalse(data["known_de_source_edges_intact"])
            self.assertTrue(any(v["status"] == "SOURCE_DRIFT" for v in data["observations"]))
            self.assertFalse(data["financial_producers_fenced"])
            path.unlink()
            data = AUDIT.inspect(root)
            self.assertTrue(any(v["status"] == "UNKNOWN_SOURCE" for v in data["observations"]))
            self.assertFalse(data["mainnet_settlement_cutover_authorized"])

    def test_link_substitution_and_oversized_source_never_count_as_observed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture(root)
            original = root / "lib" / "woloBetSettlement.ts"
            original.unlink()
            target = root / "fake.ts"
            target.write_text("\n".join(marker for filename, marker, _ in AUDIT.SENTINELS
                                        if filename == "lib/woloBetSettlement.ts") + "\n")
            original.symlink_to(target)
            report = AUDIT.inspect(root)
            self.assertFalse(report["known_de_source_edges_intact"])
            self.assertTrue(any(x["status"] == "UNKNOWN_SOURCE" and x["path"] == "lib/woloBetSettlement.ts"
                                for x in report["observations"]))
            original.unlink()
            original.write_bytes(b"Q" * (AUDIT.MAX_FILE_BYTES + 1))
            report = AUDIT.inspect(root)
            self.assertFalse(report["known_de_source_edges_intact"])

    def test_missing_git_source_identity_never_infers_runtime_or_authority(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture(root)
            identity = AUDIT.source_identity(root)
            self.assertEqual(identity["state"], "SOURCE_IDENTITY_UNVERIFIED")
            data = AUDIT.inspect(root, identity)
            self.assertTrue(data["known_de_source_edges_intact"])
            self.assertFalse(data["independent_de_signer_exclusion_proven"])


if __name__ == "__main__":
    unittest.main()
