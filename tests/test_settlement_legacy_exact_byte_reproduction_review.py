"""Negative-only contracts for historic byte reproduction — never a GO permit."""
import importlib.util
import pathlib
import unittest

SOURCE = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "settlement_legacy_exact_byte_reproduction_review.py"
spec = importlib.util.spec_from_file_location("wolo_legacy_repro", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class HistoricalByteReproductionTests(unittest.TestCase):
    def good(self, **changes):
        kwargs = dict(source=mod.OLD_SOURCE, tree_clean=True,
                      toolchain="go1.26.0", vcs_revision=mod.OLD_SOURCE,
                      vcs_modified="false",
                      build_settings=dict(mod.EXPECTED_BUILD_SETTINGS),
                      built_sha256=mod.OLD_SETTLEMENT_SHA256)
        kwargs.update(changes)
        return mod.assess(**kwargs)

    def assert_hold(self, **changes):
        value = self.good(**changes)
        self.assertEqual(value["status"], "REPRODUCTION_NOT_ESTABLISHED_HOLD")
        self.assertFalse(value["website_release_authorized"])
        self.assertFalse(value["financial_release_authorized"])
        self.assertFalse(value["semantic_171_commit_p1_resolved"])

    def test_byte_match_is_not_build_deployment_provenance_or_website_go(self):
        value = self.good()
        self.assertEqual(value["status"], "EXACT_BYTE_MATCH_NONAUTHORIZING")
        self.assertTrue(all(value["checks"].values()))
        for field in ("original_builder_identity_independently_verified",
                      "original_deployment_custody_verified",
                      "consensus_dirty_tree_source_reconstructed",
                      "semantic_171_commit_p1_resolved",
                      "independent_human_approval_obtained",
                      "website_release_authorized",
                      "financial_release_authorized",
                      "production_binary_change_authorized"):
            self.assertIs(value[field], False, field)

    def test_wrong_binary_hash_refuses(self):
        self.assert_hold(built_sha256="a" * 64)

    def test_wrong_source_commit_refuses(self):
        self.assert_hold(source="b" * 40)

    def test_dirty_worktree_refuses(self):
        self.assert_hold(tree_clean=False)

    def test_other_toolchain_refuses(self):
        self.assert_hold(toolchain="go1.24.0")

    def test_without_trimpath_refuses(self):
        flags = dict(mod.EXPECTED_BUILD_SETTINGS)
        flags["-trimpath"] = "false"
        self.assert_hold(build_settings=flags)

    def test_without_cgo_refuses(self):
        flags = dict(mod.EXPECTED_BUILD_SETTINGS)
        flags["CGO_ENABLED"] = "0"
        self.assert_hold(build_settings=flags)

    def test_wrong_cpu_version_refuses(self):
        flags = dict(mod.EXPECTED_BUILD_SETTINGS)
        flags["GOAMD64"] = "v3"
        self.assert_hold(build_settings=flags)

    def test_no_build_metadata_refuses(self):
        self.assert_hold(build_settings=None)

    def test_wrong_embedded_source_refuses(self):
        self.assert_hold(vcs_revision="c" * 40)

    def test_modified_build_refuses(self):
        self.assert_hold(vcs_modified="true")

    def test_unknown_or_malformed_hash_refuses(self):
        self.assert_hold(built_sha256="unknown")

    def test_wrong_original_expected_reference_refuses(self):
        self.assert_hold(expected_sha256="d" * 64)


if __name__ == "__main__":
    unittest.main()
