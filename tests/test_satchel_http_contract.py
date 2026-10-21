"""Offline HTTP ABI/authority drift checks; runtime money tests live in Go.

The document uses standard OpenAPI 3.1 / JSON Schema. These tests deliberately
check its correspondence with the actual wire structs and routes, rather than
implementing a second protocol parser or claiming schema validation proves money.
"""
from pathlib import Path
import json
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'docs/settlement-contracts/war-satchel-http-v1.openapi.json'


class SatchelHTTPContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(PATH.read_text())
        cls.schemas = cls.doc['components']['schemas']

    def test_exact_private_transport_and_finite_limits(self):
        self.assertEqual(self.doc['openapi'], '3.1.0')
        self.assertEqual(self.doc['info']['version'], '1.0.0')
        self.assertEqual(self.doc['servers'], [{'url': 'http://127.0.0.1:8094'}])
        self.assertEqual(self.doc['security'], [{'PrivateBearer': []}])
        transport = self.doc['x-transport']
        self.assertFalse(transport['automatic_financial_retries'])
        self.assertEqual(transport['max_request_bytes'], 16 << 10)
        self.assertEqual(transport['max_portable_proof_bytes'], (14 << 20) + (128 << 10))
        self.assertEqual(transport['max_financial_proof_bytes'], (14 << 20) + (192 << 10))
        source = (ROOT / 'internal/satchelservice/http.go').read_text()
        self.assertIn('HTTPMaxBodyBytes = 16 << 10', source)
        for marker in ('len(r.Header.Values("Origin")) != 0', 'len(r.Header.Values("Authorization")) != 1', 'ip.IsLoopback()', 'r.URL.RawQuery != ""', 'r.URL.RawPath != ""'):
            self.assertIn(marker, source)

    def test_every_implemented_route_has_one_documented_method(self):
        source = (ROOT / 'internal/satchelservice/http.go').read_text()
        paths = set(re.findall(r'"(/(?:satchel|v1/satchel)/[^" ]+)"', source))
        # Prefix route uses a path parameter, not a second route convention.
        paths = {path for path in paths if not path.endswith('/')}
        paths.add('/satchel/v1/operations/{operation_id}')
        self.assertEqual(paths, set(self.doc['paths']))
        for path, methods in self.doc['paths'].items():
            self.assertEqual(list(methods), ['get' if path.endswith('/health') or path.endswith('/custody/journal') or '{operation_id}' in path else 'post'])
            for method in methods.values():
                self.assertIn('200', method['responses'])
                self.assertIn('401', method['responses'])
                self.assertIn('503', method['responses'])

    def test_named_schema_fields_match_exact_go_json_spelling(self):
        count = 0
        for name, schema in self.schemas.items():
            if 'x-go-type' not in schema:
                continue
            filename, go_type = schema['x-go-type'].split(':')
            text = (ROOT / filename).read_text()
            body = re.search(r'type ' + go_type + r' struct \{(.*?)\n\}', text, re.S)[1]
            tags = re.findall(r'`json:"([^",]+)(?:,[^"]*)?"`', body)
            self.assertEqual(set(tags), set(schema['properties']), name)
            self.assertFalse(schema['additionalProperties'], name)
            count += 1
        self.assertGreaterEqual(count, 20)

    def test_new_wager_requires_owner_reservation_and_legacy_is_replay_only(self):
        schema = self.schemas['ReservedWagerRequest']
        source = (ROOT / 'internal/satchelservice/http.go').read_text()
        body = re.search(r'func decodeReservedWagerHTTP.*?var input struct \{(.*?)\n\t\}', source, re.S)[1]
        self.assertEqual(set(re.findall(r'`json:"([^",]+)(?:,[^"]*)?"`', body)), set(schema['properties']))
        self.assertEqual(schema['properties']['protocol'], {'const': 2})
        self.assertIn('owner_id', schema['required'])
        self.assertIn('reservation', schema['required'])
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(self.doc['paths']['/satchel/v1/one-shot']['post']['x-financial-effect'], 'legacy-replay-only')
        self.assertEqual(self.schemas['WagerReservation']['properties']['version'], {'const': 1})
        self.assertIn('fee_uwolo', self.schemas['WagerReservation']['required'])

    def test_all_references_resolve_without_network_or_external_schema(self):
        def walk(value):
            if isinstance(value, dict):
                if '$ref' in value:
                    target = value['$ref']
                    self.assertTrue(target.startswith('#/components/'), target)
                    node = self.doc
                    for segment in target[2:].split('/'):
                        node = node[segment]
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(self.doc)

    def test_proof_and_prepared_return_never_authorize_credit_or_execution(self):
        for name in ('FinancialProof', 'ReturnReceipt', 'ReturnPrepared', 'ProofFailure'):
            self.assertEqual(self.schemas[name]['properties']['credit_authorized'], {'const': False}, name)
        self.assertEqual(self.schemas['ReturnPrepared']['properties']['execution_authorized'], {'const': False})
        self.assertEqual(self.schemas['FinancialProof']['properties']['message_index'], {'const': 0})
        self.assertEqual(self.schemas['PortableProof']['properties']['responses']['maxItems'], 80)
        self.assertEqual(set(self.schemas['PortableProof']['properties']), {'version', 'chain_id', 'kind', 'tx_hash', 'responses'})
        for name in ('ReturnApproval', 'ReturnEntitlement', 'ReturnReceipt', 'ReturnIdentity'):
            self.assertEqual(self.schemas[name]['properties']['claim_id']['not'], {'const': '889'})
        for name in ('ReturnApproval', 'ReturnEntitlement', 'ReturnReceipt'):
            self.assertEqual(set(self.schemas[name]['properties']['claim_kind']['enum']), {'bet_refund', 'bet_payout'})

    def test_custody_checkpoint_is_not_bank_or_customer_ledger_authority(self):
        schema = self.schemas['CustodyJournal']
        props = schema['properties']
        for field in ('bank_balance_authenticated', 'credit_authorized', 'solvency_authorized'):
            self.assertEqual(props[field], {'const': False})
        self.assertEqual(props['custody_capability'], {'const': 'UNAVAILABLE'})
        self.assertEqual(props['kind'], {'const': 'execution_journal_checkpoint'})
        self.assertEqual(props['bytes_read']['maximum'], 8 << 20)
        self.assertEqual(props['records_read']['maximum'], 100000)
        self.assertEqual(set(props['operation_status_counts']['properties']), set(self.doc['x-state-semantics']))
        self.assertEqual(self.doc['paths']['/satchel/v1/custody/journal']['get']['x-financial-effect'], 'observe')
        source = (ROOT / 'internal/satchelservice/custody_journal.go').read_text()
        self.assertIn('e.db.View(', source)
        self.assertNotIn('e.db.Update(', source)
        self.assertNotRegex(source, r'\.backend\.(Sign|Broadcast|Confirm)\(')

    def test_uncertain_broadcast_and_read_recovery_are_distinct(self):
        statuses = self.schemas['OperationResult']['properties']['status']['enum']
        self.assertEqual(set(statuses), {'ACCEPTED', 'UNKNOWN', 'FAILED', 'OBSERVED_NONCREDITING', 'CONFIRMED', 'REFUSED'})
        self.assertEqual(set(statuses), set(self.doc['x-state-semantics']))
        for path in ('/satchel/v1/reconcile', '/satchel/v1/returns/reconcile'):
            self.assertEqual(self.doc['paths'][path]['post']['x-financial-effect'], 'reconcile-journal')
        for kind in ('deposit', 'operation', 'return'):
            self.assertEqual(self.doc['paths']['/satchel/v1/proofs/' + kind]['post']['x-financial-effect'], 'observe')
        self.assertIn('not', self.schemas['ReturnIdentity']['properties']['claim_id'])


if __name__ == '__main__':
    unittest.main()
