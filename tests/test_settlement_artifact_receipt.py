"""The unsigned manifest must remain bound to an authenticated external receipt."""

import contextlib
import copy
import hashlib
import io
import json
import unittest
from unittest import mock

import test_settlement_artifact as fixture_module


class ArtifactReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Reuse the real, offline Go/ELF setup without rediscovering its tests.
        cls.fixture_type = type("ReceiptFixture", (fixture_module.ArtifactFixture,), {})
        cls.fixture_type.setUpClass()
        cls.addClassCleanup(cls.fixture_type.doClassCleanups)

    def setUp(self):
        self.fixture = self.fixture_type("test_real_clean_candidate_verifies")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.artifact = self.fixture.artifact
        self.identity = dict(self.fixture.identity)
        self.identity["workflow_ref"] = (
            "Emaren/wolochain/" + self.artifact.WORKFLOW_PATH
            + "@refs/heads/codex/exact-settlement-artifact"
        )
        self.manifest = self.artifact.create_manifest(
            self.fixture.binary, self.fixture.rebuild, self.fixture.source, self.identity
        )
        self.path = self.fixture.root / "receipt-manifest.json"
        self.path.write_text(json.dumps(self.manifest, sort_keys=True) + "\n", encoding="utf-8")
        self.trusted_digest = hashlib.sha256(self.path.read_bytes()).hexdigest()

    def arguments(self, command="verify", binary=None):
        result = [
            command, "--source-dir", str(self.fixture.source),
            "--binary", str(binary or self.fixture.binary), "--manifest", str(self.path),
        ]
        for key, value in self.identity.items():
            result.extend(("--" + key.replace("_", "-"), value))
        return result

    def run_cli(self, arguments):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            result = self.artifact.main(arguments)
        return result, output.getvalue()

    def test_verify_requires_independently_supplied_manifest_digest(self):
        result, output = self.run_cli(self.arguments())
        self.assertEqual(result, 2)
        self.assertIn("requires --expected-manifest-sha256", output)

    def test_valid_receipt_binds_exact_manifest_and_binary(self):
        result, output = self.run_cli(
            self.arguments() + ["--expected-manifest-sha256", self.trusted_digest]
        )
        self.assertEqual(result, 0, output)

    def test_retargeted_binary_and_manifest_cannot_reuse_ci_receipt(self):
        forged_binary = self.fixture.changed_binary(
            "receipt-retargeted", self.fixture.binary.read_bytes() + b"unreviewed trailer"
        )
        observed = self.artifact.inspect_binary(forged_binary)
        self.assertEqual(observed["go"], self.manifest["binary"]["go"])
        self.assertNotEqual(observed["sha256"], self.manifest["binary"]["sha256"])
        forged = copy.deepcopy(self.manifest)
        forged["binary"] = observed
        forged["reproducibility"]["second_sha256"] = observed["sha256"]
        # Metadata consistency alone cannot authenticate a self-issued manifest.
        self.artifact.verify_manifest(
            forged, forged_binary, self.fixture.source, self.identity
        )
        self.path.write_text(json.dumps(forged, sort_keys=True) + "\n", encoding="utf-8")
        result, output = self.run_cli(
            self.arguments(binary=forged_binary)
            + ["--expected-manifest-sha256", self.trusted_digest]
        )
        self.assertEqual(result, 2)
        self.assertIn("manifest receipt SHA-256 mismatch", output)

    def test_receipt_hashes_raw_bytes_before_parsing(self):
        self.path.write_bytes(b"\xff invalid JSON")
        with self.assertRaisesRegex(self.artifact.ArtifactError, "receipt SHA-256 mismatch"):
            self.artifact.load_manifest(self.path, self.trusted_digest)

    def test_semantically_identical_reencoded_manifest_has_different_receipt(self):
        self.path.write_text(json.dumps(self.manifest, indent=2) + "\n", encoding="utf-8")
        result, output = self.run_cli(
            self.arguments() + ["--expected-manifest-sha256", self.trusted_digest]
        )
        self.assertEqual(result, 2)
        self.assertIn("manifest receipt SHA-256 mismatch", output)

    def test_create_cannot_accept_an_expected_receipt(self):
        with mock.patch.object(self.artifact, "create_manifest") as create:
            result, output = self.run_cli(
                self.arguments(command="create")
                + ["--rebuild", str(self.fixture.rebuild),
                   "--expected-manifest-sha256", self.trusted_digest]
            )
        self.assertEqual(result, 2)
        self.assertIn("create does not accept --expected-manifest-sha256", output)
        create.assert_not_called()

    def test_invalid_external_digest_is_rejected(self):
        for digest in ("", "A" * 64, "a" * 63, "a" * 65, "0" * 63 + "x"):
            with self.subTest(digest=digest):
                result, output = self.run_cli(
                    self.arguments() + ["--expected-manifest-sha256", digest]
                )
                self.assertEqual(result, 2)
                self.assertIn("invalid expected manifest SHA-256", output)


if __name__ == "__main__":
    unittest.main()
