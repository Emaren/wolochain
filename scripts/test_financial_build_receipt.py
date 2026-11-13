"""Targeted negatives for the non-authorizing CI artifact receipt."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("financial-build-receipt.py")
spec = importlib.util.spec_from_file_location("receipt", SCRIPT)
receipt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(receipt)


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        def git(*args):
            return subprocess.check_output(["git", "-C", str(self.root), *args], text=True).strip()
        self.git = git
        git("init", "-q")
        (self.root / ".gitignore").write_text("build/\n")
        (self.root / "source.go").write_text("package main\n")
        git("add", ".")
        git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
            "commit", "-qm", "fixture")
        self.sha = git("rev-parse", "HEAD")
        (self.root / "build").mkdir()
        header = bytearray(64)
        header[:6] = b"\x7fELF\x02\x01"
        header[18:20] = (62).to_bytes(2, "little")
        self.artifact = self.root / "build/wolochaind"
        self.artifact.write_bytes(header + b"fixture-not-executed")

    def test_identity_never_confers_authority(self):
        result = receipt.candidate(self.root, self.sha, "build/wolochaind")
        self.assertEqual(result["state"], "QUARANTINED")
        self.assertFalse(result["deployment_authorized"])
        self.assertEqual(result["funded_operations"], "DENIED")
        self.assertIsNone(result["previous_production_release"])

    def test_wrong_source_and_dirty_source_are_denied(self):
        with self.assertRaisesRegex(receipt.Hold, "SOURCE_SHA_MISMATCH"):
            receipt.candidate(self.root, "0" * 40, "build/wolochaind")
        (self.root / "source.go").write_text("changed")
        with self.assertRaisesRegex(receipt.Hold, "SOURCE_NOT_CLEAN"):
            receipt.candidate(self.root, self.sha, "build/wolochaind")

    def test_untracked_source_is_denied(self):
        (self.root / "extra.go").write_text("package main")
        with self.assertRaisesRegex(receipt.Hold, "SOURCE_NOT_CLEAN"):
            receipt.candidate(self.root, self.sha, "build/wolochaind")

    def test_symlink_and_traversal_are_denied(self):
        self.artifact.unlink()
        self.artifact.symlink_to(self.root / "source.go")
        with self.assertRaisesRegex(receipt.Hold, "SYMLINK_ARTIFACT_PATH"):
            receipt.candidate(self.root, self.sha, "build/wolochaind")
        with self.assertRaisesRegex(receipt.Hold, "UNSAFE_ARTIFACT_PATH"):
            receipt.candidate(self.root, self.sha, "../source.go")

    def test_nonbinary_and_wrong_architecture_are_denied(self):
        self.artifact.write_bytes(b"not an executable")
        with self.assertRaisesRegex(receipt.Hold, "LINUX_AMD64_ELF_REQUIRED"):
            receipt.candidate(self.root, self.sha, "build/wolochaind")
        self.artifact.write_bytes(b"\x7fELF\x02\x01" + b"\0" * 58)
        with self.assertRaisesRegex(receipt.Hold, "LINUX_AMD64_ELF_REQUIRED"):
            receipt.candidate(self.root, self.sha, "build/wolochaind")

    def test_cli_preserves_existing_receipt_and_refuses_deploy(self):
        args = ["python3", str(SCRIPT), "--repo", str(self.root), "--source-sha", self.sha]
        first = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stdout)
        old = (self.root / "build/financial-build-candidate.json").read_bytes()
        again = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(again.returncode, 2)
        self.assertFalse(json.loads(again.stdout)["deployment_authorized"])
        self.assertEqual((self.root / "build/financial-build-candidate.json").read_bytes(), old)
        denied = subprocess.run(args + ["--deploy"], capture_output=True, text=True)
        self.assertNotEqual(denied.returncode, 0)


if __name__ == "__main__":
    unittest.main()
