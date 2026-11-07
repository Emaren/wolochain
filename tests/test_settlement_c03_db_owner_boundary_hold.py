"""Adversarial tests for source-only C03 legacy-owner observation."""
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

P=Path(__file__).resolve().parents[1]/'scripts'/'settlement_c03_db_owner_boundary_hold.py'
S=importlib.util.spec_from_file_location('c03_owner_boundary',P)
audit=importlib.util.module_from_spec(S)
S.loader.exec_module(audit)

def values(**changes):
    v=dict(zip(audit.FIELDS,[1,35,30,30,0,1,1,1,0,1,0,4,0]))
    v.update(changes)
    return '|'.join(map(str,[v[k] for k in audit.FIELDS]))+'\n'

class C03OwnerBoundaryTests(unittest.TestCase):
    def test_query_read_only_fixed_roles(self):
        for db,role in audit.TARGETS.items():
            q=audit.query(db)
            self.assertIn('REPEATABLE READ READ ONLY',q)
            self.assertIn('ROLLBACK',q)
            self.assertIn("to_regrole('"+role+"')",q)
            self.assertNotIn('ALTER TABLE ',q)
            self.assertNotIn('REVOKE ',q)
        with self.assertRaises(audit.AuditHold):audit.query('postgres')

    def test_live_owner_is_implicit_bypass(self):
        z=audit.parse(values(),'aoe2hd_db')
        self.assertEqual(z['finance_relations_owned'],30)
        self.assertTrue(z['implicit_owner_or_schema_bypass'])
        self.assertTrue(z['finance_writer_capability'])

    def test_ownership_bypass_even_zero_dml_grants(self):
        for field in ('finance_relations_owned','legacy_database_owner',
                      'legacy_public_schema_owner_or_member',
                      'legacy_can_create_in_public','superuser',
                      'member_of_other_finance_owner_roles'):
            zero=dict(finance_relations_owned=0,finance_relations_dml_capable=0,
                legacy_database_owner=0,legacy_public_schema_owner_or_member=0,
                legacy_can_create_in_public=0,superuser=0,
                member_of_other_finance_owner_roles=0)
            zero[field]=1
            self.assertTrue(audit.parse(values(**zero),'aoe2de_db')['finance_writer_capability'])

    def test_malformed_missing_and_duplicate_hold(self):
        for bad in ('','1|2', values().strip()+'\n'+values(),
                    values().replace('30|30','NaN|30'),
                    values().replace('1|35','2|35'),
                    values().replace('0|4|0','0|10000|0'), '3'*4097):
            with self.subTest(bad=bad[:20]):
                with self.assertRaises(audit.AuditHold):
                    audit.parse(bad,'aoe2hd_db')
        with self.assertRaises(audit.AuditHold):
            audit.parse(values(),'bad')
        with self.assertRaises(audit.AuditHold):
            audit.parse(values(role_exists=0),'aoe2hd_db')

    def test_never_approves_from_zero_counts(self):
        a=audit.parse(values(finance_relations_owned=0,
            finance_relations_dml_capable=0,legacy_database_owner=0,
            legacy_public_schema_owner_or_member=0,legacy_can_create_in_public=0,
            superuser=0,member_of_other_finance_owner_roles=0),'aoe2hd_db')
        b={**a,'legacy_role':'aoe2de_user'}
        result=audit.classify({'aoe2hd_db':a,'aoe2de_db':b})
        self.assertEqual(result['status'],'HOLD')
        self.assertFalse(result['financial_release_authorized'])
        self.assertFalse(result['total_producer_and_db_write_fence_proven'])
        with self.assertRaises(audit.AuditHold):
            audit.classify({'aoe2hd_db':a})

    def test_only_root_local_postgres(self):
        with patch.object(audit.os,'geteuid',return_value=1000):
            with self.assertRaises(audit.AuditHold):audit.inspect('aoe2hd_db')
        class Result:
            returncode=0
            stderr=''
            stdout=values()
        with patch.object(audit.os,'geteuid',return_value=0),\
             patch.object(audit.subprocess,'run',return_value=Result()) as run:
            self.assertEqual(audit.inspect('aoe2hd_db')['finance_relations_owned'],30)
            self.assertEqual(run.call_args.args[0][:4],['runuser','-u','postgres','--'])
        with patch.object(audit.os,'geteuid',return_value=0),\
             patch.object(audit.subprocess,'run',side_effect=OSError()):
            with self.assertRaises(OSError):audit.inspect('aoe2hd_db')

if __name__=='__main__':
    unittest.main()
