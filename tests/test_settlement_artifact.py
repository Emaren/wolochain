"""Offline exact-source artifact checks; never execute the candidate binary."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "settlement-artifact.py"


class ArtifactFixture(unittest.TestCase):
    """A tiny real ELF/Go build avoids network access and financial code."""

    @classmethod
    def setUpClass(cls):
        if not shutil.which("go") or not shutil.which("git"):
            raise unittest.SkipTest("offline artifact integration requires Go and Git")
        cls.temp = tempfile.TemporaryDirectory(prefix="wolo-artifact-test-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.source = cls.root / "source"
        (cls.source / "cmd" / "wolochaind").mkdir(parents=True)
        (cls.source / "go.mod").write_text(
            "module github.com/emaren/wolochain\n\ngo 1.24.0\n", encoding="utf-8"
        )
        (cls.source / ".gitignore").write_text("ignored-build/\n", encoding="utf-8")
        (cls.source / "cmd" / "wolochaind" / "main.go").write_text(
            'package main\nimport "fmt"\nfunc main() { fmt.Println("offline test fixture") }\n',
            encoding="utf-8",
        )
        cls.env = dict(os.environ)
        cls.env.update({
            "CGO_ENABLED": "0", "GOOS": "linux", "GOARCH": "amd64",
            "GOAMD64": "v1", "GOEXPERIMENT": "",
            "GOTOOLCHAIN": "local", "GOENV": "off", "GOFLAGS": "",
            "GOWORK": "off", "GOPROXY": "off", "GOSUMDB": "off",
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
        })
        cls.run_tool(["git", "init", "--quiet", str(cls.source)])
        cls.run_tool(["git", "-C", str(cls.source), "add", "."])
        cls.run_tool([
            "git", "-C", str(cls.source), "-c", "user.name=Offline Test",
            "-c", "user.email=offline@example.invalid", "-c", "core.hooksPath=" + os.devnull,
            "commit", "--quiet", "-m", "offline fixture",
        ])
        cls.revision = cls.run_tool([
            "git", "-C", str(cls.source), "rev-parse", "HEAD"
        ]).stdout.strip()
        (cls.root / "first").mkdir()
        cls.binary = cls.root / "first" / "wolochaind"
        cls.run_tool([
            "go", "build", "-trimpath", "-buildvcs=true", "-tags=go1.27", "-ldflags=-buildid=",
            "-o", str(cls.binary), "./cmd/wolochaind",
        ], cwd=cls.source)
        cls.replica = cls.root / "replica"
        cls.run_tool(["git", "clone", "--quiet", "--no-hardlinks", str(cls.source), str(cls.replica)])
        (cls.root / "second").mkdir()
        cls.rebuild = cls.root / "second" / "wolochaind"
        cls.run_tool([
            "go", "build", "-trimpath", "-buildvcs=true", "-tags=go1.27", "-ldflags=-buildid=",
            "-o", str(cls.rebuild), "./cmd/wolochaind",
        ], cwd=cls.replica)
        source_file = cls.source / "cmd" / "wolochaind" / "main.go"
        original = source_file.read_bytes()
        try:
            source_file.write_bytes(original + b"// deliberately dirty fixture\n")
            (cls.root / "dirty").mkdir()
            cls.dirty_binary = cls.root / "dirty" / "wolochaind"
            cls.run_tool([
                "go", "build", "-trimpath", "-buildvcs=true", "-tags=go1.27", "-ldflags=-buildid=",
                "-o", str(cls.dirty_binary), "./cmd/wolochaind",
            ], cwd=cls.source)
        finally:
            source_file.write_bytes(original)
        replica_file = cls.replica / "cmd" / "wolochaind" / "main.go"
        replica_file.write_bytes(original + b"// another committed implementation\n")
        cls.run_tool(["git", "-C", str(cls.replica), "add", "."])
        cls.run_tool([
            "git", "-C", str(cls.replica), "-c", "user.name=Offline Test",
            "-c", "user.email=offline@example.invalid", "-c", "core.hooksPath=" + os.devnull,
            "commit", "--quiet", "-m", "different offline source",
        ])
        (cls.root / "divergent").mkdir()
        cls.divergent_binary = cls.root / "divergent" / "wolochaind"
        cls.run_tool([
            "go", "build", "-trimpath", "-buildvcs=true", "-tags=go1.27", "-ldflags=-buildid=",
            "-o", str(cls.divergent_binary), "./cmd/wolochaind",
        ], cwd=cls.replica)
        spec = importlib.util.spec_from_file_location("settlement_artifact", SCRIPT)
        cls.artifact = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.artifact)
        cls.production_source = cls.artifact.EXPECTED_SOURCE

    @classmethod
    def run_tool(cls, args, cwd=None):
        result = subprocess.run(
            args, cwd=cwd, env=cls.env, text=True, capture_output=True,
            timeout=90, check=False,
        )
        if result.returncode:
            raise AssertionError(f"offline fixture command failed: {args!r}: {result.stderr}")
        return result

    def setUp(self):
        pin = mock.patch.object(self.artifact, "EXPECTED_SOURCE", self.revision)
        pin.start()
        self.addCleanup(pin.stop)
        self.identity = {
            "repository": "Emaren/wolochain", "builder_commit": self.revision,
            "run_id": "123456789", "run_attempt": "1",
            "workflow_ref": "Emaren/wolochain/.github/workflows/legacy-settlement-exact-526d5-artifact.yml@refs/heads/codex/exact-settlement-artifact",
            "workflow_sha": self.revision,
        }

    def candidate(self):
        return self.artifact.create_manifest(
            self.binary, self.rebuild, self.source, self.identity
        )

    def verify(self, manifest, binary=None, identity=None):
        return self.artifact.verify_manifest(
            manifest, binary or self.binary, self.source, identity or self.identity
        )

    def changed_binary(self, label, data):
        directory = self.root / label
        directory.mkdir(exist_ok=True)
        binary = directory / "wolochaind"
        binary.write_bytes(data)
        return binary

    def test_production_pin_is_exact_reviewed_implementation(self):
        self.assertEqual(self.production_source, "526d5eb6123f6cc0394b5e78489c668e77e46106")

    def test_real_clean_candidate_verifies(self):
        self.verify(self.candidate())

    def test_legacy_replay_profile_is_pinned_and_cannot_relabel_historical_source(self):
        profile = "legacy-replay"
        policy = self.artifact.profile_policy(profile)
        self.assertEqual(policy["source"], "cb24cb2546392c981da8dcac18a04d1df4241330")
        self.assertNotEqual(policy["source"], self.production_source)
        identity = dict(self.identity, workflow_ref="Emaren/wolochain/"
                        + self.artifact.LEGACY_REPLAY_WORKFLOW_PATH
                        + "@refs/heads/codex/closure-wolo-legacy-replay")
        # The tiny fixture exercises the same strict binary/source verifier;
        # it is never presented as a Wolo binary or financial authority.
        with mock.patch.object(self.artifact, "LEGACY_REPLAY_SOURCE", self.revision):
            manifest = self.artifact.create_manifest(self.binary, self.rebuild,
                                                     self.source, identity, profile=profile)
            self.artifact.verify_manifest(manifest, self.binary, self.source,
                                          identity, profile=profile)
            self.assertTrue(all(value is False for value in manifest["authority"].values()))
            with self.assertRaises(self.artifact.ArtifactError):
                self.artifact.verify_manifest(manifest, self.binary, self.source,
                                              self.identity, profile="legacy526")
            with mock.patch.object(self.artifact, "LEGACY_REPLAY_SOURCE", "f" * 40):
                with self.assertRaises(self.artifact.ArtifactError):
                    self.artifact.verify_manifest(manifest, self.binary, self.source,
                                                  identity, profile=profile)
        with mock.patch.object(self.artifact, "LEGACY_REPLAY_SOURCE", "UNAVAILABLE"):
            with self.assertRaisesRegex(self.artifact.ArtifactError, "NONACCEPTING"):
                self.artifact.profile_policy(profile)

    def test_binary_checksum_mismatch_is_rejected(self):
        manifest = self.candidate()
        changed = self.changed_binary("changed-binary", self.binary.read_bytes() + b"unexpected trailer")
        with self.assertRaisesRegex(self.artifact.ArtifactError, "manifest mismatch"):
            self.verify(manifest, binary=changed)

    def test_nonidentical_rebuild_is_rejected(self):
        changed = self.changed_binary("changed-rebuild", self.rebuild.read_bytes() + b"different compilation")
        with self.assertRaisesRegex(self.artifact.ArtifactError, "build bytes or metadata disagree"):
            self.artifact.create_manifest(
                self.binary, changed, self.source, self.identity
            )

    def test_dirty_source_is_rejected(self):
        manifest = self.candidate()
        source_file = self.source / "cmd" / "wolochaind" / "main.go"
        original = source_file.read_bytes()
        try:
            source_file.write_bytes(original + b"// unpublished source change\n")
            with self.assertRaisesRegex(self.artifact.ArtifactError, "dirty source tree"):
                self.verify(manifest)
        finally:
            source_file.write_bytes(original)

    def test_untracked_source_is_rejected(self):
        manifest = self.candidate()
        untracked = self.source / "unreviewed.go"
        try:
            untracked.write_text("package main\n", encoding="utf-8")
            with self.assertRaisesRegex(self.artifact.ArtifactError, "dirty source tree"):
                self.verify(manifest)
        finally:
            untracked.unlink()

    def test_ignored_source_is_rejected(self):
        manifest = self.candidate()
        ignored = self.source / "ignored-build"
        ignored.mkdir()
        try:
            (ignored / "unreviewed.go").write_text("package main\n", encoding="utf-8")
            with self.assertRaisesRegex(self.artifact.ArtifactError, "dirty source tree"):
                self.verify(manifest)
        finally:
            shutil.rmtree(ignored)

    def test_git_index_flags_cannot_hide_source_drift(self):
        source_file = self.source / "cmd" / "wolochaind" / "main.go"
        original = source_file.read_bytes()
        for flag in ("assume-unchanged", "skip-worktree"):
            with self.subTest(flag=flag):
                self.run_tool([
                    "git", "-C", str(self.source), "update-index", "--" + flag,
                    "cmd/wolochaind/main.go",
                ])
                try:
                    source_file.write_bytes(original + b"// hidden unreviewed change\n")
                    status = self.run_tool([
                        "git", "-C", str(self.source), "status", "--porcelain"
                    ]).stdout
                    self.assertEqual(status, "", "fixture must demonstrate status-only blind spot")
                    with self.assertRaises(self.artifact.ArtifactError):
                        self.artifact.source_identity(self.source)
                finally:
                    source_file.write_bytes(original)
                    self.run_tool([
                        "git", "-C", str(self.source), "update-index", "--no-" + flag,
                        "cmd/wolochaind/main.go",
                    ])

    def test_real_dirty_embedded_vcs_is_rejected(self):
        self.artifact.source_identity(self.source)
        with self.assertRaisesRegex(self.artifact.ArtifactError, "vcs.modified"):
            self.artifact.inspect_binary(self.dirty_binary)

    def test_real_different_embedded_revision_is_rejected(self):
        self.artifact.source_identity(self.source)
        with self.assertRaisesRegex(self.artifact.ArtifactError, "vcs.revision"):
            self.artifact.inspect_binary(self.divergent_binary)

    def test_source_revision_drift_is_rejected(self):
        with mock.patch.object(self.artifact, "EXPECTED_SOURCE", "1" * 40):
            with self.assertRaisesRegex(self.artifact.ArtifactError, "source drift"):
                self.artifact.source_identity(self.source)

    def test_external_ci_identity_must_match(self):
        manifest = self.candidate()
        for key, value in (
            ("repository", "attacker/wolochain"), ("builder_commit", "2" * 40),
            ("workflow_sha", "3" * 40), ("run_id", "987654321"),
            ("run_attempt", "2"),
            ("workflow_ref", "Emaren/wolochain/.github/workflows/unreviewed.yml@refs/heads/main"),
        ):
            with self.subTest(field=key):
                changed = dict(self.identity, **{key: value})
                with self.assertRaises(self.artifact.ArtifactError):
                    self.verify(manifest, identity=changed)

    def test_unknown_manifest_fields_are_rejected(self):
        manifest = self.candidate()
        manifest["production_ready"] = True
        with self.assertRaisesRegex(self.artifact.ArtifactError, "manifest mismatch"):
            self.verify(manifest)

    def test_required_manifest_fields_cannot_be_removed(self):
        manifest = self.candidate()
        for key in manifest:
            with self.subTest(field=key):
                changed = copy.deepcopy(manifest)
                del changed[key]
                with self.assertRaisesRegex(self.artifact.ArtifactError, "manifest mismatch"):
                    self.verify(changed)

    def test_manifest_values_are_strictly_bound(self):
        manifest = self.candidate()
        changes = (
            (("schema_version",), True),
            (("source", "dirty"), 0),
            (("source", "commit"), "bdbce253c524d6faac14f61cd129ac5072287c3f"),
            (("source", "tree"), "0" * 40),
            (("binary", "sha256"), "0" * 64),
            (("binary", "go", "version"), "go1.24.7"),
            (("binary", "go", "build_settings", "vcs.modified"), "true"),
            (("binary", "go", "build_settings", "vcs.revision"), "0" * 40),
            (("recipe", "build_flags"), ["-buildvcs=false"]),
            (("recipe", "environment", "CGO_ENABLED"), "1"),
            (("reproducibility", "builds"), 1),
            (("authority", "production_authorized"), True),
        )
        for path, value in changes:
            with self.subTest(path=path):
                changed = copy.deepcopy(manifest)
                parent = changed
                for key in path[:-1]:
                    parent = parent[key]
                parent[path[-1]] = value
                with self.assertRaisesRegex(self.artifact.ArtifactError, "manifest mismatch"):
                    self.verify(changed)

    def test_invalid_ci_identity_cannot_create_a_manifest(self):
        for key, value in (
            ("run_id", "0"), ("run_id", True), ("run_attempt", "-1"),
            ("builder_commit", "a" * 39), ("workflow_sha", "A" * 40),
            ("workflow_ref", "Emaren/wolochain/.github/workflows/legacy-settlement-exact-526d5-artifact.yml@refs/heads/test\nforged"),
        ):
            with self.subTest(field=key, value=value):
                changed = dict(self.identity, **{key: value})
                with self.assertRaises(self.artifact.ArtifactError):
                    self.artifact.create_manifest(self.binary, self.rebuild, self.source, changed)

    def test_malformed_or_ambiguous_manifest_json_is_rejected(self):
        examples = (
            b'{"schema_version":1,"schema_version":1}',
            b'{"source":{"commit":"a","commit":"b"}}',
            b'{"value":NaN}', b'{} {}', b'{', b'null', b'[]', b'\xff',
            b" " * (self.artifact.MAX_MANIFEST_BYTES + 1),
        )
        path = self.root / "malformed-manifest.json"
        for data in examples:
            with self.subTest(data=data[:80]):
                path.write_bytes(data)
                with self.assertRaises(self.artifact.ArtifactError):
                    self.artifact.load_manifest(path)

    def test_go_metadata_must_match_the_exact_compiler_and_build_flags(self):
        metadata = self.run_tool(["go", "version", "-m", str(self.binary)]).stdout
        for before, after in (
            ("go1.24.6", "go1.24.7"),
            ("-trimpath=true", "-trimpath=false"),
            ("-tags=go1.27", "-tags=anything"),
            ("CGO_ENABLED=0", "CGO_ENABLED=1"),
            ("GOOS=linux", "GOOS=darwin"),
            ("GOARCH=amd64", "GOARCH=arm64"),
        ):
            with self.subTest(setting=before):
                self.assertIn(before, metadata)
                with self.assertRaises(self.artifact.ArtifactError):
                    self.artifact._parse_go_metadata(metadata.replace(before, after))

    def test_duplicate_go_build_settings_are_rejected(self):
        metadata = self.run_tool(["go", "version", "-m", str(self.binary)]).stdout
        with self.assertRaisesRegex(self.artifact.ArtifactError, "duplicate Go build setting"):
            self.artifact._parse_go_metadata(metadata + "\tbuild\tGOOS=linux\n")

    def test_same_file_is_not_an_independent_rebuild(self):
        with self.assertRaisesRegex(self.artifact.ArtifactError, "distinct build files"):
            self.artifact.create_manifest(self.binary, self.binary, self.source, self.identity)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires local FIFO support")
    def test_special_files_fail_without_blocking(self):
        # Exercise a child process so a regression cannot hang the test runner.
        code = (
            "import importlib.util,sys; "
            "s=importlib.util.spec_from_file_location('artifact',sys.argv[1]); "
            "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
            "getattr(m,sys.argv[2])(sys.argv[3])"
        )
        for function in ("inspect_binary", "load_manifest"):
            with self.subTest(function=function):
                directory = self.root / ("fifo-" + function)
                directory.mkdir()
                fifo = directory / "wolochaind"
                os.mkfifo(fifo)
                result = subprocess.run(
                    [sys.executable, "-c", code, str(SCRIPT), function, str(fifo)],
                    text=True, capture_output=True, timeout=3, check=False,
                    env=dict(self.env, PYTHONDONTWRITEBYTECODE="1"),
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ArtifactError", result.stderr)

    def test_symlink_candidate_is_rejected(self):
        directory = self.root / "symlink-candidate"
        directory.mkdir()
        linked = directory / "wolochaind"
        linked.symlink_to(self.binary)
        with self.assertRaises((self.artifact.ArtifactError, OSError)):
            self.artifact.inspect_binary(linked)

    def test_real_elf_and_embedded_go_identity(self):
        observed = self.artifact.inspect_binary(self.binary)
        self.assertEqual(observed["format"], "ELF64-little-linux-amd64")
        self.assertEqual(observed["go"]["path"], "github.com/emaren/wolochain/cmd/wolochaind")
        settings = observed["go"]["build_settings"]
        self.assertEqual(settings["vcs.revision"], self.revision)
        self.assertEqual(settings["vcs.modified"], "false")
        self.assertEqual(settings["GOOS"], "linux")
        self.assertEqual(settings["GOARCH"], "amd64")
        self.assertEqual(settings["CGO_ENABLED"], "0")
        self.assertEqual(observed["build_id"], "")

    def test_real_build_is_reproducible(self):
        self.assertEqual(self.binary.read_bytes(), self.rebuild.read_bytes())

    def test_wrong_elf_machine_is_rejected(self):
        raw = bytearray(self.binary.read_bytes())
        raw[18:20] = (183).to_bytes(2, "little")
        forged = self.changed_binary("forged-aarch64", raw)
        with self.assertRaisesRegex(self.artifact.ArtifactError, "ELF architecture"):
            self.artifact.inspect_binary(forged)

    def test_non_elf_binary_is_rejected(self):
        forged = self.changed_binary("forged-not-elf", b"#!/bin/sh\nexit 0\n" + b" " * 64)
        with self.assertRaisesRegex(self.artifact.ArtifactError, "ELF64"):
            self.artifact.inspect_binary(forged)


if __name__ == "__main__":
    unittest.main()
