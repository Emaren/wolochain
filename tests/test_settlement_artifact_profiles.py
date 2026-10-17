"""Named profiles share one non-executing artifact proof implementation."""

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


class ComposedProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("go") or not shutil.which("git"):
            raise unittest.SkipTest("offline profile integration requires Go and Git")
        cls.temporary = tempfile.TemporaryDirectory(prefix="wolo-profile-test-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        cls.source = cls.root / "source"
        (cls.source / "cmd" / "wolosatcheld").mkdir(parents=True)
        (cls.source / "go.mod").write_text("module github.com/emaren/wolochain\n\ngo 1.24.0\n")
        (cls.source / "cmd" / "wolosatcheld" / "main.go").write_text("package main\nfunc main() {}\n")
        cls.environment = dict(os.environ, GOTOOLCHAIN="local", GOENV="off", GOWORK="off",
                               GOFLAGS="", GOEXPERIMENT="", GOFIPS140="off", CGO_ENABLED="0",
                               GOOS="linux", GOARCH="amd64", GOAMD64="v1", GOPROXY="off",
                               GOSUMDB="off", PYTHONDONTWRITEBYTECODE="1",
                               GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        cls.run_tool(["git", "init", "--quiet", str(cls.source)])
        cls.run_tool(["git", "-C", str(cls.source), "add", "."])
        cls.run_tool(["git", "-C", str(cls.source), "-c", "user.name=Offline Profile",
                      "-c", "user.email=offline@example.invalid", "-c", "core.hooksPath=" + os.devnull,
                      "commit", "--quiet", "-m", "offline composed fixture"])
        cls.revision = cls.run_tool(["git", "-C", str(cls.source), "rev-parse", "HEAD"]).stdout.strip()
        cls.replica = cls.root / "replica"
        cls.run_tool(["git", "clone", "--quiet", "--no-local", str(cls.source), str(cls.replica)])
        cls.binary = cls.root / "first" / "wolosatcheld"
        cls.rebuild = cls.root / "second" / "wolosatcheld"
        for checkout, binary in ((cls.source, cls.binary), (cls.replica, cls.rebuild)):
            binary.parent.mkdir()
            cls.run_tool(["go", "build", "-trimpath", "-buildvcs=true", "-tags=go1.27",
                          "-mod=readonly", "-ldflags=-buildid=", "-o", str(binary), "./cmd/wolosatcheld"],
                         cwd=checkout)
        specification = importlib.util.spec_from_file_location("artifact_profiles", ROOT / "scripts" / "settlement-artifact.py")
        cls.artifact = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(cls.artifact)

    @classmethod
    def run_tool(cls, arguments, cwd=None):
        return subprocess.run(arguments, cwd=cwd, env=cls.environment, text=True,
                              capture_output=True, timeout=90, check=True)

    def setUp(self):
        pin = mock.patch.object(self.artifact, "COMPOSED_SOURCE", self.revision)
        pin.start()
        self.addCleanup(pin.stop)
        self.identity = {
            "repository": "Emaren/wolochain", "builder_commit": self.revision,
            "run_id": "123456789", "run_attempt": "1", "workflow_sha": self.revision,
            "workflow_ref": "Emaren/wolochain/" + self.artifact.COMPOSED_WORKFLOW_PATH
                            + "@refs/heads/codex/satchel-authenticated-financial-bridge",
        }

    def candidate(self):
        return self.artifact.create_manifest(self.binary, self.rebuild, self.source, self.identity,
                                            profile="composed-satcheld")

    def test_real_composed_candidate_has_no_activation_authority(self):
        manifest = self.candidate()
        self.artifact.verify_manifest(manifest, self.binary, self.source, self.identity,
                                      profile="composed-satcheld")
        self.assertEqual(manifest["profile"], "composed-satcheld")
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(manifest["recipe"]["package"], "./cmd/wolosatcheld")
        self.assertEqual(manifest["binary"]["name"], "wolosatcheld")
        self.assertFalse(manifest["authority"]["satchel_activation_authorized"])
        self.assertFalse(manifest["authority"]["production_authorized"])

    def test_legacy_policy_remains_exact_and_separate(self):
        legacy = self.artifact.profile_policy("legacy526")
        self.assertEqual(legacy["source"], "526d5eb6123f6cc0394b5e78489c668e77e46106")
        self.assertEqual(legacy["binary"], "wolochaind")
        self.assertEqual(legacy["package"], "./cmd/wolochaind")
        self.assertNotEqual(legacy["workflow"], self.artifact.profile_policy("composed-satcheld")["workflow"])

    def test_unprovisioned_profile_fails_closed(self):
        with mock.patch.object(self.artifact, "COMPOSED_SOURCE", "NONACCEPTING_PENDING_REVIEWED_SOURCE"):
            with self.assertRaisesRegex(self.artifact.ArtifactError, "NONACCEPTING composed source"):
                self.artifact.profile_policy("composed-satcheld")

    def test_arbitrary_profiles_cannot_override_source(self):
        for profile in ("current", "main", self.revision, "composed-satcheld@" + self.revision, None):
            with self.subTest(profile=profile):
                with self.assertRaisesRegex(self.artifact.ArtifactError, "unknown artifact profile"):
                    self.artifact.profile_policy(profile)

    def test_legacy_workflow_cannot_attest_composed_binary(self):
        identity = dict(self.identity, workflow_ref="Emaren/wolochain/" + self.artifact.WORKFLOW_PATH
                        + "@refs/heads/codex/legacy-settlement-hardening")
        with self.assertRaisesRegex(self.artifact.ArtifactError, "workflow reference mismatch"):
            self.artifact.create_manifest(self.binary, self.rebuild, self.source, identity,
                                          profile="composed-satcheld")

    def test_composed_binary_cannot_be_relabeled_legacy(self):
        renamed = self.root / "renamed" / "wolochaind"
        renamed.parent.mkdir(exist_ok=True)
        shutil.copyfile(self.binary, renamed)
        with mock.patch.object(self.artifact, "EXPECTED_SOURCE", self.revision):
            with self.assertRaisesRegex(self.artifact.ArtifactError, "main package mismatch"):
                self.artifact.inspect_binary(renamed, profile="legacy526")

    def test_composed_cli_requires_external_receipt(self):
        path = self.root / "composed-manifest.json"
        path.write_text(json.dumps(self.candidate(), sort_keys=True) + "\n")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        arguments = ["verify", "--profile", "composed-satcheld", "--source-dir", str(self.source),
                     "--binary", str(self.binary), "--manifest", str(path)]
        for key, value in self.identity.items():
            arguments.extend(("--" + key.replace("_", "-"), value))
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.artifact.main(arguments), 2)
            self.assertEqual(self.artifact.main(arguments + ["--expected-manifest-sha256", digest]), 0)
            path.write_bytes(path.read_bytes() + b" ")
            self.assertEqual(self.artifact.main(arguments + ["--expected-manifest-sha256", digest]), 2)

    def test_metadata_only_receipt_is_retired(self):
        result = subprocess.run(["python3", str(ROOT / "scripts" / "satchel-source-artifact.py"), str(self.root)],
                                env=self.environment, text=True, capture_output=True, timeout=3)
        self.assertEqual(result.returncode, 2)
        self.assertIn("RETIRED_METADATA_ONLY_RECEIPT", result.stderr)


if __name__ == "__main__":
    unittest.main()
