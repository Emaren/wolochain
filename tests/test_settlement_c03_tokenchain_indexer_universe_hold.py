"""C03 external TokenChain indexer financial-writer classification remains HOLD."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

S=Path(__file__).resolve().parents[1]/"scripts"
sys.path.insert(0,str(S))
sp=importlib.util.spec_from_file_location(
    "c03_universe_tokenchain",S/"settlement_c03_physical_writer_universe_hold.py")
module=importlib.util.module_from_spec(sp);sp.loader.exec_module(module)

class TokenChainUnscopedTests(unittest.TestCase):
    def test_real_indexer_is_discovered(self):
        names=module.names_from_listing(
            "tokenchain-indexer.service loaded active running TokenChain Indexer API\n")
        self.assertEqual(names,{"tokenchain-indexer.service"})

    def test_indexer_is_not_auto_fenced_or_classified_safe(self):
        source={"ActiveState":"active","MainPID":"985"}
        item=module.classify("tokenchain-indexer.service",source)
        self.assertEqual(item["category"],"UNSCOPED_REVIEW_REQUIRED")
        self.assertTrue(item["active"])
        self.assertNotIn(item["unit"],module.OWNED)
        self.assertNotIn(item["unit"],module.PUBLIC_PROTECTED)

    def test_unreviewed_tokenchain_timers_also_discovered(self):
        names=module.names_from_listing(
            "tokenchain-indexer.timer enabled enabled\n"
            "tokenchain-indexer.service enabled enabled\n")
        self.assertEqual(len(names),2)
        item=module.classify("tokenchain-indexer.timer",{"ActiveState":"active"})
        self.assertEqual(item["category"],"UNSCOPED_REVIEW_REQUIRED")
        self.assertTrue(item["timer"])

    def test_extra_indexer_cannot_be_ignored(self):
        names=module.names_from_listing(
            "tokenchain-ledger-repair.service loaded active running service\n")
        self.assertEqual(names,{"tokenchain-ledger-repair.service"})
        self.assertEqual(module.classify(next(iter(names)),{"ActiveState":"inactive"})
                         ["category"],"UNSCOPED_REVIEW_REQUIRED")

    def test_invalid_tokenchain_service_fails_closed(self):
        with self.assertRaises(module.ObservationError):
            module.names_from_listing("tokenchain-indexer.service;rm -rf / loaded active\n")

    def test_extra_writer_domain_requires_explicit_review(self):
        self.assertIn("tokenchain_indexer_direct_and_indirect_database_writers",
                      module.UNPROVEN_DOMAINS)
        self.assertTrue("tokenchain-" in module.PREFIXES)
        self.assertNotIn("tokenchain-indexer.service",module.FAMILIES)

if __name__=="__main__":unittest.main()
