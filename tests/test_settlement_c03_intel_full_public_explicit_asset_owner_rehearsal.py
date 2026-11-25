"""Fail-closed source contract for offhost HD/DE PG16 60/21 full-data rehearsal.

Static tests do not decrypt a backup, write PostgreSQL or mutate production.
The physical run is independently pinned to the immutable executed SHA256.
"""
from __future__ import annotations
import importlib.util
from pathlib import Path
from unittest.mock import patch
import unittest
P=Path(__file__).resolve().parents[1]/'scripts/settlement_c03_intel_full_public_explicit_asset_owner_rehearsal.py'
spec=importlib.util.spec_from_file_location('intel_public_v5',P)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class IntelFullPublicOwnerV5Tests(unittest.TestCase):
 def test_60_21_and_old_source_expansion(self):
  self.assertEqual(m.PINS['hd'][3:],(190,60,58))
  self.assertEqual(m.PINS['de'][3:],(52,21,21))
  self.assertEqual(m.BASE_NAME_FINANCE,{'hd':54,'de':20})
  self.assertEqual(m.BASE_NAME_SEQUENCES,{'hd':52,'de':20})
  self.assertEqual(m.EXTRA_ASSET_SEQUENCES,{'hd':6,'de':1})
  self.assertEqual(m.EXPECTED_SEQUENCES,{'hd':180,'de':50})
  self.assertEqual(m.EXPECTED_PUBLIC_FUNCTIONS,{'hd':39,'de':0})
  self.assertEqual(m.EXPECTED_SCHEMA_OWNER,{'hd':'pg_database_owner','de':'c03_de_legacy'})

 def test_all_explicit_asset_surfaces_in_source(self):
  self.assertEqual(set(m.EXTRA_ASSET_TABLES['hd']),{
   'public.championship_challenge_participants',
   'public.championship_custody_seats',
   'public.oracle_market_proposals',
   'public.oracle_paper_positions',
   'public.user_gifts',
   'public.war_graph_watcher_attestations',
  })
  self.assertEqual(m.EXTRA_ASSET_TABLES['de'],('public.user_gifts',))
  self.assertEqual(len(set(m.EXTRA_ASSET_TABLES['hd'])),6)
  self.assertEqual(len(set(m.EXTRA_ASSET_TABLES['de'])),1)
  for names in m.EXTRA_ASSET_TABLES.values():
   for name in names:self.assertRegex(name,r'^public\.[a-z_]+$')

 def test_real_restore_provenance_source_only(self):
  s=P.read_text()
  for token in (
      'PASS_COMPLETE_HD_DE_CIPHERTEXT_AUTHENTICATION',
      'PRIVATE_FULL_PG16_RESTORE',
      'FULL_PUBLIC_TABLE_OWNER_MODEL_MISSING',
      'FULL_PUBLIC_SEQUENCE_OWNER_MODEL_MISSING',
      'FULL_PUBLIC_FUNCTION_OWNER_MODEL_MISSING',
      'MISSING_EXTRA','UNEXPECTED_EXPLICIT_ASSET_TABLE_SCOPE',
      'EXPLICIT_ASSET_SEQUENCE_SCOPE_DRIFT',
      'ASSET_WRITE_WAS_NOT_FENCED','ASSET_INSERT_WAS_NOT_FENCED',
      'LEGITIMATE_UNPROTECTED_APP_OWNER_WRITES_LOST',
      'LEGACY_USERS_NOOP_UPDATE_DENIED',
      'LEGACY_USERS_NOOP_INSERT_DENIED',
      'LEGACY_USERS_NOOP_DELETE_DENIED',
      'REAL_PUBLIC_SCHEMA_OWNER_ROLLBACK_DRIFT',
      '"formal_c03_c06_c07_gates_accepted":False',
      '"funded_release_authorized":False',
      '"production_changed":False'):
   if token=='MISSING_EXTRA':continue
   self.assertIn(token,s)
  self.assertIn('listen_addresses=',s)
  self.assertIn('unix_socket_permissions=0700',s)
  self.assertNotIn('root@hel1',s)
  self.assertNotIn('pg_terminate_backend',s)
  self.assertNotIn('systemctl start',s)
  self.assertNotIn('Authorization: Bearer',s)
  self.assertIn('other_161_unclassified_public_tables_still_not_finance_classified',s)

 def test_protected_legacy_finance_and_operational_dml_preserved(self):
  s=P.read_text()
  self.assertIn('REVOKE CREATE ON SCHEMA public FROM PUBLIC, ',s)
  self.assertIn('GRANT SELECT ON TABLE ',s)
  self.assertIn('ALTER SEQUENCE ',s)
  self.assertIn('ALTER TABLE ',s)
  self.assertIn('UPDATE public.users SET id=id WHERE false',s)
  self.assertIn('INSERT INTO public.users SELECT * FROM public.users WHERE false',s)
  self.assertIn('DELETE FROM public.users WHERE false',s)
  self.assertIn('UPDATE "+protected+" SET id=id WHERE false',s)
  self.assertIn('INSERT INTO "+protected+" SELECT * FROM "+protected+" WHERE false',s)
  self.assertIn('len(unprotected)==total-expected_finance',s)
  self.assertIn('EXTRA_ASSET_TABLES[lane]',s)

 def test_intel_darwin_only_source_gate(self):
  with patch.object(m.sys,'platform','linux'):
   with self.assertRaises(RuntimeError):m.main()
  with patch.object(m.platform,'machine',return_value='arm64'):
   with self.assertRaises(RuntimeError):m.main()
  with patch.object(m.os,'geteuid',return_value=0):
   with self.assertRaises(RuntimeError):m.main()

 def test_strict_preexisting_archive_and_result_pin(self):
  self.assertEqual(len(m.PROOF),2)
  self.assertEqual(len(m.PINS),2)
  for lane in ('hd','de'):
   self.assertEqual(len(m.PINS[lane][1]),64)
   self.assertGreater(m.PINS[lane][2],0)
   self.assertEqual(len(m.PROOF[lane][1]),64)
  self.assertIn('NO_REPLAY_OF_PREVIOUS_RECEIPT',P.read_text())
  self.assertTrue(m.RESULT.name.endswith('20261107.json'))

if __name__=='__main__':unittest.main()
