"""Named profiles share one non-executing artifact proof implementation."""

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
REVIEWED_BACKEND_SOURCE = "8c509e8f62ca3ec60711dc2654a03b12f22b0773"
HISTORICAL_BACKEND_SOURCE = "99f32de617964565875ed4689bea0d688bb99147"


class BackendArtifactSourceContractTests(unittest.TestCase):
    """A builder must name the current reviewed implementation explicitly."""

    def test_backend_workflow_and_profile_share_exact_new_implementation_pin(self):
        specification = importlib.util.spec_from_file_location(
            "backend_artifact_source_contract", ROOT / "scripts" / "settlement-artifact.py")
        artifact = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(artifact)
        workflow = (ROOT / artifact.BACKEND_WORKFLOW_PATH).read_text()
        self.assertEqual(artifact.profile_policy("custody-backend")["source"],
                         REVIEWED_BACKEND_SOURCE)
        self.assertEqual(re.findall(r"^\s+EXPECTED_SOURCE: ([0-9a-f]{40})$", workflow,
                                    re.MULTILINE), [REVIEWED_BACKEND_SOURCE])
        self.assertNotEqual(REVIEWED_BACKEND_SOURCE, HISTORICAL_BACKEND_SOURCE)
        self.assertEqual(artifact.profile_policy("legacy526")["source"],
                         "526d5eb6123f6cc0394b5e78489c668e77e46106")
        self.assertEqual(artifact.profile_policy("composed-satcheld")["source"],
                         "155fcf67fb2127a2227de5ea785e51bdbb0155c0")

    def test_backend_artifact_trigger_includes_current_held_base(self):
        workflow = (ROOT / ".github/workflows/custody-backend-satcheld-exact-artifact.yml").read_text()
        branches = re.findall(r"^\s+branches: \[([^\]]+)\]$", workflow, re.MULTILINE)
        self.assertEqual(len(branches), 1)
        self.assertEqual({value.strip() for value in branches[0].split(",")}, {
            "integration/20261018-satchel-ops-finance-held",
            "codex/satchel-production-backend",
        })
        self.assertIn("ref: ${{ env.EXPECTED_SOURCE }}", workflow)
        self.assertIn("ref: ${{ env.BUILDER_COMMIT }}", workflow)
        self.assertIn("contents: read", workflow)
        self.assertNotIn("contents: write", workflow)


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

    def test_backend_candidate_is_separately_source_and_workflow_bound(self):
        identity = dict(self.identity, workflow_ref="Emaren/wolochain/" + self.artifact.BACKEND_WORKFLOW_PATH
                        + "@refs/heads/codex/satchel-production-backend")
        with mock.patch.object(self.artifact, "BACKEND_SOURCE", self.revision):
            manifest = self.artifact.create_manifest(self.binary, self.rebuild, self.source, identity,
                                                    profile="custody-backend")
            self.artifact.verify_manifest(manifest, self.binary, self.source, identity, profile="custody-backend")
            self.assertEqual(manifest["profile"], "custody-backend")
            self.assertFalse(manifest["authority"]["satchel_activation_authorized"])
            with self.assertRaises(self.artifact.ArtifactError):
                self.artifact.verify_manifest(manifest, self.binary, self.source, self.identity, profile="composed-satcheld")
            with self.assertRaises(self.artifact.ArtifactError):
                self.artifact.create_manifest(self.binary, self.rebuild, self.source, self.identity, profile="custody-backend")
            with mock.patch.object(self.artifact, "BACKEND_SOURCE", "f" * 40):
                with self.assertRaises(self.artifact.ArtifactError):
                    self.artifact.verify_manifest(manifest, self.binary, self.source, identity, profile="custody-backend")

    def test_missing_backend_source_is_nonaccepting(self):
        with mock.patch.object(self.artifact, "BACKEND_SOURCE", "NONACCEPTING_PENDING_REVIEWED_SOURCE"):
            with self.assertRaisesRegex(self.artifact.ArtifactError, "NONACCEPTING backend source"):
                self.artifact.profile_policy("custody-backend")

    def test_backend_metadata_rejects_historical_revision_dirty_vcs_and_wrong_configuration(self):
        metadata = self.run_tool(["go", "version", "-m", str(self.binary)]).stdout
        with mock.patch.object(self.artifact, "BACKEND_SOURCE", self.revision):
            self.artifact._parse_go_metadata(metadata, profile="custody-backend")
            for before, after in (
                (self.revision, HISTORICAL_BACKEND_SOURCE),
                ("vcs.modified=false", "vcs.modified=true"),
                ("go1.24.6", "go1.24.7"),
                ("GOARCH=amd64", "GOARCH=arm64"),
                ("CGO_ENABLED=0", "CGO_ENABLED=1"),
                ("-trimpath=true", "-trimpath=false"),
                ("-tags=go1.27", "-tags=unreviewed"),
            ):
                with self.subTest(setting=before):
                    self.assertIn(before, metadata)
                    with self.assertRaises(self.artifact.ArtifactError):
                        self.artifact._parse_go_metadata(metadata.replace(before, after),
                                                         profile="custody-backend")

    def test_historical_embedded_backend_revision_cannot_be_relabeled_current(self):
        # Alter only the fixture's embedded textual VCS revision. The actual Go
        # inspector must read and reject the historical source, even though the
        # filename, package and Linux architecture still match the new profile.
        directory = self.root / "historical-backend"
        directory.mkdir(exist_ok=True)
        historical = directory / "wolosatcheld"
        data = self.binary.read_bytes()
        self.assertGreaterEqual(data.count(self.revision.encode()), 1)
        historical.write_bytes(data.replace(self.revision.encode(),
                                           HISTORICAL_BACKEND_SOURCE.encode()))
        with self.assertRaisesRegex(self.artifact.ArtifactError, "vcs.revision"):
            self.artifact.inspect_binary(historical, profile="custody-backend")

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
