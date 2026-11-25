"""Prove legacy scaffold invariant remains strict except exact observed C03 units.

Extract and execute the actual Python heredoc from the production invariant
shell, with only disposable fixture files and no Git or network access.
"""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"scripts/check-chain-invariants.sh"
START='python3 - "${TRACKED_FILES[@]}" <<\'PY_C03_LIVE_SERVICE_ALLOWLIST\'\n'
END='\nPY_C03_LIVE_SERVICE_ALLOWLIST'
SCRIPT=SOURCE.read_text()
assert SCRIPT.count(START)==1 and SCRIPT.count(END)==1
CHECKER=SCRIPT.split(START,1)[1].split(END,1)[0]
OBSERVER="scripts/settlement_c03_physical_writer_universe_hold.py"
DOC="docs/C03_TOKENCHAIN_INDEXER_UNSCOPED_DISCOVERY_HOLD.md"
REG="docs/document-registry.json"
BASE="docs/DOCUMENTATION_CONTROL_PLANE.md"
UNRELATED="app/app.go"
FIXTURES={
 OBSERVER:'    "tokenchain-",\n    "tokenchain_indexer_direct_and_indirect_database_writers",\n',
 DOC:'id: "aoe2war.wolochain.c03-tokenchain-indexer-unscoped-discovery-hold"\n'
     'systems: ["wolochain", "aoe2hdbets", "tokenchain"]\n'
     'Live HEL1 runs `tokenchain-indexer.service` under the unprivileged account.\n',
 REG:'    "id": "aoe2war.wolochain.c03-tokenchain-indexer-unscoped-discovery-hold",\n'
     '        "tokenchain"\n'
     '    "branch": "fix/c03-tokenchain-writer-universe-20261108",\n',
 BASE:'Implementation baseline: `fix/c03-tokenchain-writer-universe-20261108`'
      ' at `e6a6e9bf708e44f9aee313431790a5afa2da7e24`\n',
 UNRELATED:'Name = "WoloChain"\n',
}

class ExternalIndexerGuardTests(unittest.TestCase):
    def check_fixture(self,mutate=None):
        sources=dict(FIXTURES)
        if mutate:
            name,extra=mutate
            sources[name]=sources.get(name,"")+extra
        with tempfile.TemporaryDirectory(prefix="c03-legacy-scaffold-guard-") as raw:
            root=Path(raw)
            for name,content in sources.items():
                path=root/name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(content)
            r=subprocess.run([sys.executable,"-c",CHECKER,*sorted(sources)],
                             cwd=root,capture_output=True,text=True,timeout=6)
            return r

    def test_exact_external_service_operational_references_allowed(self):
        r=self.check_fixture()
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn("PASS:",r.stdout)

    def test_extra_scaffold_reference_in_chain_source_rejected(self):
        r=self.check_fixture((OBSERVER,'    chain_id = "tokenchain"\n'))
        self.assertEqual(r.returncode,1)
        self.assertIn("unapproved",r.stderr)

    def test_scaffold_reference_in_unrelated_chain_source_rejected(self):
        r=self.check_fixture((UNRELATED,'CHAIN_ID="tokenchain"\n'))
        self.assertEqual(r.returncode,1)
        self.assertIn("app/app.go",r.stderr)

    def test_docs_unapproved_branding_rejected(self):
        r=self.check_fixture((DOC,'Public chain: tokenchain\n'))
        self.assertEqual(r.returncode,1)
        self.assertIn("unapproved",r.stderr)

    def test_registry_extra_replacement_chain_rejected(self):
        r=self.check_fixture((REG,'  "chain_id": "tokenchain",\n'))
        self.assertEqual(r.returncode,1)

    def test_baseline_extra_scaffold_rejected(self):
        r=self.check_fixture((BASE,'Untracked historical chain: tokenchain\n'))
        self.assertEqual(r.returncode,1)

    def test_missing_required_c03_prefix_is_rejected(self):
        obs=FIXTURES[OBSERVER].replace('    "tokenchain-",\n',"")
        with tempfile.TemporaryDirectory(prefix="c03-no-external-indexer-") as raw:
            root=Path(raw)
            for name,content in {**FIXTURES,OBSERVER:obs}.items():
                path=root/name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(content)
            r=subprocess.run([sys.executable,"-c",CHECKER,*sorted(FIXTURES)],
                cwd=root,capture_output=True,text=True,timeout=6)
            self.assertEqual(r.returncode,1)
            self.assertIn("markers were removed",r.stderr)

    def test_source_scoped_literals_do_not_bypass_other_invariants(self):
        self.assertIn(
            "scan_repo_pattern 'wolo-testnet-1'",SCRIPT)
        self.assertIn(
            "scan_repo_pattern 'default_denom:[[:space:]]*stake'",SCRIPT)
        self.assertIn(
            "scan_repo_pattern '\\bcosmos(valoper|valcons)?1",SCRIPT)
        self.assertIn("required_source",CHECKER)
        self.assertNotIn("else:\n        continue\n",CHECKER)

if __name__=="__main__":
    unittest.main()
