"""Named profiles share one non-executing artifact proof implementation."""

import contextlib
import copy
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
REVIEWED_RUNTIME_SOURCE = "72a3bca5f66aff51e1c6577b914d64403785d635"
REVIEWED_INTEGRATED_SOURCE = "88c63356b81e19dbda0dbcf7c2135ac607878ca4"
REVIEWED_C01_SOURCE = "93e51f24acdc2a88af80b1b0d3b1db808701de8e"
HISTORICAL_BACKEND_SOURCE = "99f32de617964565875ed4689bea0d688bb99147"


class BackendArtifactSourceContractTests(unittest.TestCase):
    """A builder must name the current reviewed implementation explicitly."""

    def test_replay_workflow_uses_existing_builder_with_separate_immutable_pin(self):
        specification = importlib.util.spec_from_file_location(
            "replay_artifact_source_contract", ROOT / "scripts" / "settlement-artifact.py")
        artifact = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(artifact)
        policy = artifact.profile_policy("legacy-replay")
        workflow = (ROOT / policy["workflow"]).read_text()
        self.assertEqual(re.findall(r"^\s+EXPECTED_SOURCE: ([0-9a-f]{40})$", workflow,
                                    re.MULTILINE), [policy["source"]])
        self.assertIn("--profile legacy-replay", workflow)
        self.assertIn("go-version: '1.24.6'", workflow)
        self.assertIn("ref: ${{ env.EXPECTED_SOURCE }}", workflow)
        self.assertIn("contents: read", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertIn("UNDEPLOYED", workflow)

    def test_archived_historical_binary_has_distinct_pinned_linux_artifact(self):
        specification = importlib.util.spec_from_file_location(
            "archive_artifact_source_contract", ROOT / "scripts" / "settlement-artifact.py")
        artifact = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(artifact)
        policy = artifact.profile_policy("archived-historical")
        self.assertEqual(policy["source"], "c575b175e6dc74c720479a04e41490a842032203")
        self.assertEqual(policy["binary"], "wolosatcheld")
        self.assertEqual(policy["package"], "./cmd/wolosatcheld")
        self.assertFalse(policy["purpose"].startswith("PRODUCTION"))
        workflow = (ROOT / policy["workflow"]).read_text()
        self.assertIn("branches: [codex/closure-wolo-legacy-replay]", workflow)
        self.assertIn("--profile archived-historical", workflow)
        self.assertIn("go-version: '1.24.6'", workflow)
        self.assertIn("ref: ${{ env.EXPECTED_SOURCE }}", workflow)
        self.assertIn("contents: read", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertIn("UNDEPLOYED", workflow)
        self.assertEqual(re.findall(r"^\s+EXPECTED_SOURCE: ([0-9a-f]{40})$", workflow,
                                    re.MULTILINE), [policy["source"]])
        self.assertEqual(artifact.profile_policy("legacy-replay")["source"],
                         "cb24cb2546392c981da8dcac18a04d1df4241330")

    def test_runtime_workflow_has_new_pin_and_preserves_frozen_backend_profile(self):
        specification = importlib.util.spec_from_file_location(
            "backend_artifact_source_contract", ROOT / "scripts" / "settlement-artifact.py")
        artifact = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(artifact)
        workflow = (ROOT / artifact.BACKEND_WORKFLOW_PATH).read_text()
        historical_job = workflow.split("\n  c01-artifact:\n", 1)[0]
        self.assertEqual(artifact.profile_policy("custody-backend")["source"],
                         REVIEWED_BACKEND_SOURCE)
        self.assertEqual(artifact.profile_policy("custody-runtime")["source"],
                         REVIEWED_RUNTIME_SOURCE)
        self.assertEqual(re.findall(r"^\s+EXPECTED_SOURCE: ([0-9a-f]{40})$", historical_job,
                                    re.MULTILINE), [REVIEWED_INTEGRATED_SOURCE])
        self.assertNotEqual(REVIEWED_RUNTIME_SOURCE, REVIEWED_BACKEND_SOURCE)
        self.assertIn("--profile integrated-custody-runtime", workflow)
        self.assertNotIn("--profile custody-backend", workflow)
        self.assertIn("'profile': 'integrated-custody-runtime'", workflow)
        self.assertIn("name: integrated-custody-runtime-${{ env.EXPECTED_SOURCE }}-linux-amd64-", workflow)
        self.assertEqual(artifact.profile_policy("integrated-custody-runtime")["source"], REVIEWED_INTEGRATED_SOURCE)
        self.assertNotEqual(REVIEWED_INTEGRATED_SOURCE, REVIEWED_RUNTIME_SOURCE)
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
            "codex/satchel-custody-authority",
            "codex/solo-owner-offline-intent-20261026",
            "codex/c01-enrolled-native-executor-20261101",
        })
        self.assertIn("ref: ${{ env.EXPECTED_SOURCE }}", workflow)
        self.assertIn("ref: ${{ env.BUILDER_COMMIT }}", workflow)
        self.assertIn("contents: read", workflow)
        self.assertNotIn("contents: write", workflow)

    def test_c01_profile_preserves_every_historical_source_and_reuses_single_builder(self):
        specification = importlib.util.spec_from_file_location("c01_profile", ROOT / "scripts/settlement-artifact.py")
        artifact = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(artifact)
        historical = {
            "legacy526": "526d5eb6123f6cc0394b5e78489c668e77e46106",
            "composed-satcheld": "155fcf67fb2127a2227de5ea785e51bdbb0155c0",
            "custody-backend": REVIEWED_BACKEND_SOURCE, "custody-runtime": REVIEWED_RUNTIME_SOURCE,
            "integrated-custody-runtime": REVIEWED_INTEGRATED_SOURCE,
            "legacy-replay": "cb24cb2546392c981da8dcac18a04d1df4241330",
            "archived-historical": "c575b175e6dc74c720479a04e41490a842032203",
        }
        self.assertEqual({name: artifact.profile_policy(name)["source"] for name in historical}, historical)
        policy = artifact.profile_policy("c01-enrolled-escrow-runtime")
        self.assertEqual(policy["source"], REVIEWED_C01_SOURCE)
        self.assertEqual(policy["binary"], "wolosatcheld")
        self.assertEqual(policy["package"], "./cmd/wolosatcheld")
        self.assertEqual(policy["workflow"], artifact.BACKEND_WORKFLOW_PATH)
        workflow = (ROOT / policy["workflow"]).read_text()
        old, c01 = workflow.split("\n  c01-artifact:\n", 1)
        self.assertIn("github.base_ref != 'codex/c01-enrolled-native-executor-20261101'", old)
        self.assertIn("inputs.profile != 'c01-enrolled-escrow-runtime'", old)
        self.assertIn("github.base_ref == 'codex/c01-enrolled-native-executor-20261101'", c01)
        self.assertIn("github.event.pull_request.number == 124", c01)
        self.assertIn("github.head_ref == 'codex/c01-executable-deadline-repair-20261101'", c01)
        self.assertIn("github.event.pull_request.head.repo.full_name == 'Emaren/wolochain'", c01)
        self.assertIn("inputs.profile == 'c01-enrolled-escrow-runtime'", c01)
        self.assertEqual(re.findall(r"^\s+EXPECTED_SOURCE: ([0-9a-f]{40})$", c01, re.MULTILINE), [REVIEWED_C01_SOURCE])
        self.assertIn("actions: read", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertIn("artifact.source_ci_receipt('c01-enrolled-escrow-runtime')", c01)
        self.assertLess(c01.index("artifact.source_ci_receipt("), c01.index("build-settlement-artifact.sh"))
        self.assertIn("--profile c01-enrolled-escrow-runtime", c01)
        self.assertNotIn("go build", c01, "one shared two-build recipe, not three role builds")
        self.assertIn("'source_ci': source_ci['source_ci']", c01)
        self.assertIn("'source_pull_request': source_ci['source_ci'][0]['pull_request']", c01)
        self.assertIn("'source_ci_receipt_sha256'", c01)
        self.assertIn("'production_authorized': False", c01)
        self.assertIn("'rebuild_sha256'", c01)
        self.assertIn("steps.c01-candidate.outputs.artifact-id", c01)
        self.assertIn("steps.c01-candidate.outputs.artifact-digest", c01)
        with mock.patch.object(artifact, "C01_ENROLLED_SOURCE", "NONACCEPTING_PENDING_CI"):
            with self.assertRaisesRegex(artifact.ArtifactError, "NONACCEPTING C01"):
                artifact.profile_policy("c01-enrolled-escrow-runtime")


class C01SourceCIGateTests(unittest.TestCase):
    """Actual read-only API boundary with bounded mocked GitHub responses."""

    def setUp(self):
        specification = importlib.util.spec_from_file_location("c01_ci_gate", ROOT / "scripts/settlement-artifact.py")
        self.artifact = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(self.artifact)
        self.responses = {}
        self.requests = []
        for n, workflow in enumerate(("ci.yml", "epoch-escrow-v3.yml"), 1):
            self.responses[workflow] = {"id": n, "path": ".github/workflows/"+workflow, "state": "active"}
            self.responses[workflow+"/runs"] = {"workflow_runs": [{
                "id": n+100, "workflow_id": n, "head_sha": REVIEWED_C01_SOURCE,
                "event": "pull_request", "path": ".github/workflows/"+workflow,
                "repository": {"full_name": "Emaren/wolochain", "id": 990989676}, "status": "completed",
                "head_repository": {"full_name": "Emaren/wolochain", "id": 990989676},
                "head_branch": "codex/c01-executable-deadline-repair-20261101",
                "pull_requests": [{
                    "number": 124, "id": 5112667912,
                    "url": "https://api.github.com/repos/Emaren/wolochain/pulls/124",
                    "head": {"ref": "codex/c01-executable-deadline-repair-20261101", "sha": REVIEWED_C01_SOURCE,
                             "repo": {"id": 990989676, "url": "https://api.github.com/repos/Emaren/wolochain", "name": "wolochain"}},
                    "base": {"ref": "codex/c01-enrolled-native-executor-20261101", "sha": "75743d4ef6574226d5b6244ad45150ccd92d4171",
                             "repo": {"id": 990989676, "url": "https://api.github.com/repos/Emaren/wolochain", "name": "wolochain"}},
                }],
                "conclusion": "success", "run_attempt": 1,
                "html_url": f"https://github.com/Emaren/wolochain/actions/runs/{n+100}",
            }]}
        self.token = hashlib.sha256(self.id().encode()).hexdigest()

    def run_gate(self):
        outer = self

        class Opener:
            def open(self, request, timeout):
                outer.requests.append(request)
                url = outer.artifact.urllib.parse.urlsplit(request.full_url)
                outer.assertEqual(url.scheme, "https")
                outer.assertEqual(url.netloc, "api.github.com")
                prefix = "/repos/Emaren/wolochain/actions/workflows/"
                comparison = "/repos/Emaren/wolochain/compare/"
                outer.assertTrue(url.path.startswith(prefix) or url.path.startswith(comparison))
                outer.assertEqual(request.get_method(), "GET")
                outer.assertEqual(request.get_header("Authorization"), "Bearer "+outer.token)
                outer.assertLessEqual(timeout, 8)
                key = url.path[len(prefix):] if url.path.startswith(prefix) else url.path
                if key.endswith("/runs"):
                    outer.assertEqual(outer.artifact.urllib.parse.parse_qs(url.query), {
                        "head_sha": [REVIEWED_C01_SOURCE], "event": ["pull_request"], "per_page": ["50"],
                    })
                body = outer.responses[key]
                if isinstance(body, Exception):
                    raise body
                response = io.BytesIO(body if type(body) is bytes else json.dumps(body).encode())
                response.status = 200
                return response

        with mock.patch.dict(os.environ, {"C01_GITHUB_READ_TOKEN": self.token}), \
                mock.patch.object(self.artifact.urllib.request, "build_opener", return_value=Opener()) as factory:
            result = self.artifact.source_ci_receipt("c01-enrolled-escrow-runtime")
            self.assertEqual(factory.call_args.args[0].proxies, {})
            redirect = factory.call_args.args[1]
            self.assertIsNone(redirect.redirect_request(None, None, 302, "", {}, "https://other.invalid"))
            return result

    def test_both_real_workflow_receipts_are_exact_and_non_authorizing(self):
        result = self.run_gate()
        self.assertEqual(len(self.requests), 4)
        self.assertEqual(result["source_commit"], REVIEWED_C01_SOURCE)
        self.assertEqual([row["run_id"] for row in result["source_ci"]], [101, 102])
        self.assertTrue(all(row["head_sha"] == REVIEWED_C01_SOURCE for row in result["source_ci"]))
        self.assertTrue(all(row["pull_request"]["number"] == 124 and row["pull_request"]["head_sha"] == REVIEWED_C01_SOURCE
                            and row["pull_request"]["base_ref"] == "codex/c01-enrolled-native-executor-20261101"
                            for row in result["source_ci"]))
        self.assertFalse(result["production_authorized"])

    def test_moving_live_pr_head_requires_authenticated_exact_builder_ancestry(self):
        builder = "d" * 40
        key = "/repos/Emaren/wolochain/compare/"+REVIEWED_C01_SOURCE+"..."+builder
        comparison = {"status": "ahead", "ahead_by": 1, "behind_by": 0, "total_commits": 1,
                      "base_commit": {"sha": REVIEWED_C01_SOURCE}, "merge_base_commit": {"sha": REVIEWED_C01_SOURCE},
                      "commits": [{"sha": builder}]}
        self.responses[key] = comparison
        for workflow in ("ci.yml/runs", "epoch-escrow-v3.yml/runs"):
            self.responses[workflow]["workflow_runs"][0]["pull_requests"][0]["head"]["sha"] = builder
        with mock.patch.dict(os.environ, {"BUILDER_COMMIT": builder}):
            result = self.run_gate()
            self.assertEqual(len(self.requests), 5)
            self.assertEqual(result["builder_ancestry"]["builder_commit"], builder)
            self.assertTrue(all(r["head_sha"] == REVIEWED_C01_SOURCE and r["pull_request"]["head_sha"] == builder
                                for r in result["source_ci"]))
            for field, value in (("status", "diverged"), ("behind_by", 1), ("total_commits", 0),
                                 ("base_commit", {"sha": REVIEWED_INTEGRATED_SOURCE}),
                                 ("merge_base_commit", {"sha": REVIEWED_INTEGRATED_SOURCE}),
                                 ("commits", [{"sha": REVIEWED_INTEGRATED_SOURCE}])):
                with self.subTest(field=field):
                    self.responses[key] = dict(comparison, **{field: value})
                    with self.assertRaisesRegex(self.artifact.ArtifactError, "SOURCE_CI_HOLD"):
                        self.run_gate()
            self.responses[key] = comparison
            self.responses["epoch-escrow-v3.yml/runs"]["workflow_runs"][0]["pull_requests"][0]["head"]["sha"] = REVIEWED_C01_SOURCE
            with self.assertRaisesRegex(self.artifact.ArtifactError, "SOURCE_CI_HOLD changing PR context"):
                self.run_gate()
            self.responses["epoch-escrow-v3.yml/runs"]["workflow_runs"][0]["pull_requests"][0]["head"]["sha"] = builder
        with mock.patch.dict(os.environ, {"BUILDER_COMMIT": "e"*40}):
            with self.assertRaisesRegex(self.artifact.ArtifactError, "SOURCE_CI_HOLD live PR/builder mismatch"):
                self.run_gate()

    def test_reviewed_source_pr_identity_must_match_without_other_context_fallback(self):
        original = self.responses["ci.yml/runs"]
        for name, change in (
                ("missing", lambda r: r.pop("pull_requests")),
                ("ambiguous", lambda r: r["pull_requests"].append(copy.deepcopy(r["pull_requests"][0]))),
                ("number", lambda r: r["pull_requests"][0].update(number=123)),
                ("id", lambda r: r["pull_requests"][0].update(id=1)),
                ("url", lambda r: r["pull_requests"][0].update(url="https://api.github.com/repos/other/wolochain/pulls/124")),
                ("head_ref", lambda r: r["pull_requests"][0]["head"].update(ref="unreviewed")),
                ("head_sha", lambda r: r["pull_requests"][0]["head"].update(sha=REVIEWED_INTEGRATED_SOURCE)),
                ("base_ref", lambda r: r["pull_requests"][0]["base"].update(ref="main")),
                ("base_sha", lambda r: r["pull_requests"][0]["base"].update(sha=REVIEWED_INTEGRATED_SOURCE)),
                ("head_repository", lambda r: r["head_repository"].update(full_name="fork/wolochain")),
                ("head_repository_id", lambda r: r["head_repository"].update(id=1)),
                ("head_repo_id", lambda r: r["pull_requests"][0]["head"]["repo"].update(id=1)),
                ("head_repo_url", lambda r: r["pull_requests"][0]["head"]["repo"].update(url="https://api.github.com/repos/fork/wolochain")),
                ("base_repo_id", lambda r: r["pull_requests"][0]["base"]["repo"].update(id=1)),
                ("base_repo_url", lambda r: r["pull_requests"][0]["base"]["repo"].update(url="https://api.github.com/repos/fork/wolochain")),
                ("head_branch", lambda r: r.update(head_branch="unreviewed")),
        ):
            with self.subTest(name=name):
                changed = copy.deepcopy(original["workflow_runs"][0])
                changed["id"] = 900
                changed["html_url"] = "https://github.com/Emaren/wolochain/actions/runs/900"
                change(changed)
                self.responses["ci.yml/runs"] = {"workflow_runs": [original["workflow_runs"][0], changed]}
                try:
                    with self.assertRaisesRegex(self.artifact.ArtifactError, "SOURCE_CI_HOLD"):
                        self.run_gate()
                finally:
                    self.responses["ci.yml/runs"] = original

    def test_missing_pending_failed_wrong_context_and_old_success_hold(self):
        for field, value in (("status", "in_progress"), ("conclusion", "failure"), ("conclusion", "skipped"),
                             ("head_sha", REVIEWED_INTEGRATED_SOURCE), ("workflow_id", 999),
                             ("path", ".github/workflows/release.yml"), ("event", "push"),
                             ("repository", {"full_name": "other/wolochain"}), ("run_attempt", 0),
                             ("html_url", "https://other.invalid/run")):
            with self.subTest(field=field, value=value):
                original = self.responses["ci.yml/runs"]
                changed = dict(original["workflow_runs"][0], **{field: value})
                self.responses["ci.yml/runs"] = {"workflow_runs": [changed]}
                try:
                    with self.assertRaisesRegex(self.artifact.ArtifactError, "SOURCE_CI_HOLD"):
                        self.run_gate()
                finally:
                    self.responses["ci.yml/runs"] = original
        self.responses["ci.yml/runs"]["workflow_runs"].append(dict(self.responses["ci.yml/runs"]["workflow_runs"][0], id=900, status="queued", conclusion=None))
        with self.assertRaisesRegex(self.artifact.ArtifactError, "SOURCE_CI_HOLD"):
            self.run_gate()  # older success cannot excuse latest unfinished run
        self.responses["ci.yml/runs"] = {"workflow_runs": []}
        with self.assertRaisesRegex(self.artifact.ArtifactError, "SOURCE_CI_HOLD"):
            self.run_gate()

    def test_invalid_run_page_cannot_fall_back_to_an_older_green(self):
        original = self.responses["ci.yml/runs"]
        for field, value in (("head_sha", REVIEWED_INTEGRATED_SOURCE), ("workflow_id", 999), ("event", "push"), ("id", None)):
            with self.subTest(field=field):
                changed = dict(original["workflow_runs"][0], **{field: value})
                self.responses["ci.yml/runs"] = {"workflow_runs": [original["workflow_runs"][0], changed]}
                try:
                    with self.assertRaisesRegex(self.artifact.ArtifactError, "SOURCE_CI_HOLD"):
                        self.run_gate()
                finally:
                    self.responses["ci.yml/runs"] = original
        self.responses["ci.yml/runs"] = {"workflow_runs": original["workflow_runs"] * 2}
        try:
            with self.assertRaisesRegex(self.artifact.ArtifactError, "SOURCE_CI_HOLD"):
                self.run_gate()
        finally:
            self.responses["ci.yml/runs"] = original

    def test_native_receipt_missing_or_api_error_remains_held_without_private_echo(self):
        for body in ({"workflow_runs": []}, b"not-json", b"x"*((2 << 20)+1), OSError("private-network-fixture")):
            self.responses["epoch-escrow-v3.yml/runs"] = body
            with self.assertRaisesRegex(self.artifact.ArtifactError, "SOURCE_CI_HOLD") as error:
                self.run_gate()
            self.assertNotIn(self.token, str(error.exception))
            self.assertNotIn("private-network-fixture", str(error.exception))
        with mock.patch.dict(os.environ, {"C01_GITHUB_READ_TOKEN": ""}), \
                mock.patch.object(self.artifact.urllib.request, "build_opener") as factory:
            with self.assertRaisesRegex(self.artifact.ArtifactError, "SOURCE_CI_HOLD"):
                self.artifact.source_ci_receipt("c01-enrolled-escrow-runtime")
            factory.assert_not_called()


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
        with mock.patch.object(self.artifact, "BACKEND_SOURCE", self.revision), \
                mock.patch.object(self.artifact, "INTEGRATED_RUNTIME_SOURCE", self.revision):
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

    def runtime_identity(self):
        return dict(self.identity, workflow_ref="Emaren/wolochain/" + self.artifact.BACKEND_WORKFLOW_PATH
                    + "@refs/heads/codex/satchel-custody-runtime-artifact")

    def test_runtime_candidate_has_distinct_profile_and_no_authority(self):
        identity = self.runtime_identity()
        with mock.patch.object(self.artifact, "RUNTIME_SOURCE", self.revision):
            manifest = self.artifact.create_manifest(self.binary, self.rebuild, self.source, identity,
                                                    profile="custody-runtime")
            self.artifact.verify_manifest(manifest, self.binary, self.source, identity,
                                          profile="custody-runtime")
            self.assertEqual(manifest["schema_version"], 2)
            self.assertEqual(manifest["profile"], "custody-runtime")
            self.assertEqual(manifest["purpose"], "UNDEPLOYED_CUSTODY_RUNTIME_CANDIDATE")
            self.assertTrue(all(value is False for value in manifest["authority"].values()))
            with self.assertRaises(self.artifact.ArtifactError):
                self.artifact.create_manifest(self.binary, self.rebuild, self.source, self.identity,
                                              profile="custody-runtime")
            with mock.patch.object(self.artifact, "RUNTIME_SOURCE", REVIEWED_BACKEND_SOURCE):
                with self.assertRaises(self.artifact.ArtifactError):
                    self.artifact.verify_manifest(manifest, self.binary, self.source, identity,
                                                  profile="custody-runtime")

    def test_c01_candidate_has_exact_source_profile_and_external_receipt_context(self):
        identity = self.runtime_identity()
        with mock.patch.object(self.artifact, "C01_ENROLLED_SOURCE", self.revision), \
                mock.patch.object(self.artifact, "INTEGRATED_RUNTIME_SOURCE", self.revision):
            profile = "c01-enrolled-escrow-runtime"
            manifest = self.artifact.create_manifest(self.binary, self.rebuild, self.source, identity, profile=profile)
            self.artifact.verify_manifest(manifest, self.binary, self.source, identity, profile=profile)
            self.assertEqual(manifest["profile"], profile)
            self.assertEqual(manifest["purpose"], "UNDEPLOYED_C01_ENROLLED_ESCROW_RUNTIME_CANDIDATE")
            self.assertTrue(all(value is False for value in manifest["authority"].values()))
            for other in ("integrated-custody-runtime", "custody-runtime", "custody-backend"):
                with self.subTest(other=other), self.assertRaises(self.artifact.ArtifactError):
                    self.artifact.verify_manifest(manifest, self.binary, self.source, identity, profile=other)
            wrong_context = dict(identity, workflow_ref="Emaren/wolochain/"+self.artifact.COMPOSED_WORKFLOW_PATH+"@refs/heads/main")
            with self.assertRaisesRegex(self.artifact.ArtifactError, "workflow reference mismatch"):
                self.artifact.create_manifest(self.binary, self.rebuild, self.source, wrong_context, profile=profile)
            metadata = self.run_tool(["go", "version", "-m", str(self.binary)]).stdout
            self.artifact._parse_go_metadata(metadata, profile=profile)
            for old, new in ((self.revision, REVIEWED_INTEGRATED_SOURCE), ("vcs.modified=false", "vcs.modified=true"),
                             ("go1.24.6", "go1.24.7"), ("GOARCH=amd64", "GOARCH=arm64"),
                             ("-tags=go1.27", "-tags=unreviewed"), ("/cmd/wolosatcheld", "/cmd/woloreviewerd")):
                with self.subTest(setting=old), self.assertRaises(self.artifact.ArtifactError):
                    self.artifact._parse_go_metadata(metadata.replace(old, new), profile=profile)
            path = self.root / "c01-manifest.json"
            path.write_text(json.dumps(manifest, sort_keys=True)+"\n")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            arguments = ["verify", "--profile", profile, "--source-dir", str(self.source), "--binary", str(self.binary), "--manifest", str(path)]
            for key, value in identity.items():
                arguments.extend(("--"+key.replace("_", "-"), value))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(self.artifact.main(arguments), 2)
                self.assertEqual(self.artifact.main(arguments+["--expected-manifest-sha256", digest]), 0)
                path.write_bytes(path.read_bytes()+b" ")
                self.assertEqual(self.artifact.main(arguments+["--expected-manifest-sha256", digest]), 2)

    def test_same_binary_manifest_cannot_be_replayed_between_backend_and_runtime_profiles(self):
        # Even identical source/bytes/workflow cannot turn an old profile receipt
        # into the new candidate. The profile and purpose are part of the proof.
        identity = self.runtime_identity()
        with mock.patch.object(self.artifact, "RUNTIME_SOURCE", self.revision), \
                mock.patch.object(self.artifact, "BACKEND_SOURCE", self.revision), \
                mock.patch.object(self.artifact, "INTEGRATED_RUNTIME_SOURCE", self.revision), \
                mock.patch.object(self.artifact, "C01_ENROLLED_SOURCE", self.revision):
            for source_profile, target_profile in (("custody-backend", "custody-runtime"),
                                                   ("custody-runtime", "custody-backend"),
                                                   ("custody-runtime", "integrated-custody-runtime"),
                                                   ("integrated-custody-runtime", "custody-runtime"),
                                                   ("integrated-custody-runtime", "c01-enrolled-escrow-runtime"),
                                                   ("c01-enrolled-escrow-runtime", "integrated-custody-runtime")):
                with self.subTest(source_profile=source_profile):
                    manifest = self.artifact.create_manifest(self.binary, self.rebuild, self.source,
                                                            identity, profile=source_profile)
                    with self.assertRaises(self.artifact.ArtifactError):
                        self.artifact.verify_manifest(manifest, self.binary, self.source, identity,
                                                      profile=target_profile)

    def test_missing_runtime_source_is_nonaccepting(self):
        with mock.patch.object(self.artifact, "RUNTIME_SOURCE", "NONACCEPTING_PENDING_REVIEWED_SOURCE"):
            with self.assertRaisesRegex(self.artifact.ArtifactError, "NONACCEPTING runtime source"):
                self.artifact.profile_policy("custody-runtime")

    def test_runtime_metadata_rejects_frozen_revision_dirty_vcs_and_wrong_configuration(self):
        metadata = self.run_tool(["go", "version", "-m", str(self.binary)]).stdout
        with mock.patch.object(self.artifact, "RUNTIME_SOURCE", self.revision):
            self.artifact._parse_go_metadata(metadata, profile="custody-runtime")
            for before, after in (
                (self.revision, REVIEWED_BACKEND_SOURCE),
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
                                                         profile="custody-runtime")

    def test_frozen_embedded_revision_cannot_be_relabeled_runtime(self):
        directory = self.root / "frozen-runtime"
        directory.mkdir(exist_ok=True)
        frozen = directory / "wolosatcheld"
        data = self.binary.read_bytes()
        self.assertGreaterEqual(data.count(self.revision.encode()), 1)
        frozen.write_bytes(data.replace(self.revision.encode(), REVIEWED_BACKEND_SOURCE.encode()))
        with mock.patch.object(self.artifact, "RUNTIME_SOURCE", self.revision):
            with self.assertRaisesRegex(self.artifact.ArtifactError, "vcs.revision"):
                self.artifact.inspect_binary(frozen, profile="custody-runtime")

    def test_runtime_cli_requires_external_receipt_and_rejects_checksum_tampering(self):
        identity = self.runtime_identity()
        with mock.patch.object(self.artifact, "RUNTIME_SOURCE", self.revision):
            manifest = self.artifact.create_manifest(self.binary, self.rebuild, self.source,
                                                    identity, profile="custody-runtime")
            path = self.root / "runtime-manifest.json"
            path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            arguments = ["verify", "--profile", "custody-runtime", "--source-dir", str(self.source),
                         "--binary", str(self.binary), "--manifest", str(path)]
            for key, value in identity.items():
                arguments.extend(("--" + key.replace("_", "-"), value))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(self.artifact.main(arguments), 2)
                self.assertEqual(self.artifact.main(arguments + ["--expected-manifest-sha256", digest]), 0)
                changed = dict(manifest, binary=dict(manifest["binary"], sha256="f" * 64))
                path.write_text(json.dumps(changed, sort_keys=True) + "\n")
                self.assertEqual(self.artifact.main(arguments + ["--expected-manifest-sha256", digest]), 2)

    def test_backend_metadata_rejects_historical_revision_dirty_vcs_and_wrong_configuration(self):
        metadata = self.run_tool(["go", "version", "-m", str(self.binary)]).stdout
        with mock.patch.object(self.artifact, "BACKEND_SOURCE", self.revision), \
                mock.patch.object(self.artifact, "INTEGRATED_RUNTIME_SOURCE", self.revision):
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
