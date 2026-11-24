"""Focused source-only tests; never contact native DB, credentials or root."""
from pathlib import Path
import importlib.util
import unittest
from unittest import mock

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/c03_hd_direct_media_protected_delivery.py'
spec=importlib.util.spec_from_file_location('protected_delivery',SCRIPT)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class DeliveryTests(unittest.TestCase):
    def test_exact_last_file_last_line_wins(self):
        first=b'DATABASE_URL=postgresql://aoe2hd_user:fixture@127.0.0.1:5432/aoe2hd_db'
        second=b'DATABASE_URL="postgresql+asyncpg://aoe2war_social_writer:p%40ss@127.0.0.1:5432/aoe2hd_db"'
        self.assertEqual(m.connection_fields(m.selected_url([first,b'X=1\n'+first+b'\n'+second,None])),
                         ('aoe2war_social_writer','aoe2hd_db','p@ss'))
    def test_nonmatching_prefix_is_not_selected(self):
        self.assertEqual(m.selected_url([b'DATABASE_URL=fixture',b'export DATABASE_URL=wrong\n DATABASE_URL=wrong']),b'fixture')
    def test_duplicate_values_same_file_last_wins(self):
        self.assertEqual(m.selected_url([b'DATABASE_URL=first\nDATABASE_URL=second']),b'second')
    def test_missing_and_binary_hold(self):
        for inputs in ([b'OTHER=1'],[b'DATABASE_URL=fixture\x00']):
            with self.subTest(inputs=inputs),self.assertRaises(m.Hold):
                m.selected_url(inputs)
    def test_invalid_urls_fail_closed(self):
        for url in (
            b'postgresql://aoe2hd_user:x@localhost:5432/aoe2hd_db',
            b'postgresql://aoe2hd_user:x@127.0.0.1:5433/aoe2hd_db',
            b'postgresql://aoe2hd_user:x@127.0.0.1:5432/aoe2hd_db?user=postgres',
            b'postgresql://aoe2hd_user:x@127.0.0.1:5432/aoe2hd_db?host=elsewhere',
            b'postgresql://aoe2hd_user:x@127.0.0.1:5432/aoe2hd_db?sslmode=require',
            b'postgresql://unknown:x@127.0.0.1:5432/aoe2hd_db',
            b'postgresql://aoe2hd_user:x@127.0.0.1:5432/unapproved',
            b'postgresql://aoe2hd_user:x%ZZ@127.0.0.1:5432/aoe2hd_db',
            b'postgresql://aoe2hd_user:x%0A@127.0.0.1:5432/aoe2hd_db',
            b'postgresql://aoe2hd_user:x@y@127.0.0.1:5432/aoe2hd_db',
        ):
            with self.subTest(url=url),self.assertRaises(m.Hold):
                m.connection_fields(url)
    def test_stage_pin_mismatch_refused_before_native_read(self):
        data={k:b'fixture' for k in m.PACKAGE}
        with mock.patch.object(m,'read_fixed') as read,self.assertRaisesRegex(m.Hold,'PACKAGE_PIN_DRIFT'):
            m.review_pins(data)
        read.assert_not_called()
    def test_trust_only_fixed_targets_no_state_receipt(self):
        data={k:b'fixture' for k in m.PACKAGE}
        with mock.patch.object(m,'stage_read',return_value=data),mock.patch.object(m,'review_pins'),\
             mock.patch.object(m.os.path,'lexists',return_value=False),mock.patch.object(m,'new_dir') as mkdir,\
             mock.patch.object(m,'write_once') as write,mock.patch.object(m.subprocess,'run') as run:
            out=m.deliver_trust()
        self.assertEqual(out['status'],'ROOT_TRUST_DELIVERED_NO_SQL')
        self.assertEqual([x.args[0] for x in mkdir.call_args_list],[m.STATE,m.ROOT,m.CODE])
        paths={x.args[0] for x in write.call_args_list}
        self.assertEqual(paths,{m.CODE/n for n in m.PACKAGE if n.endswith(('.py','.sql'))}
                         | {m.ROOT/m.PUBLIC,m.ROOT/'review.json',m.ROOT/'root-trust-delivery-receipt.json'})
        run.assert_not_called()
    def test_partial_root_delivery_never_overwritten(self):
        with mock.patch.object(m,'stage_read'),mock.patch.object(m,'review_pins'),\
             mock.patch.object(m.os.path,'lexists',return_value=True),mock.patch.object(m,'new_dir') as mkdir,\
             mock.patch.object(m,'write_once') as write,self.assertRaisesRegex(m.Hold,'ROOT_TARGET_EXISTS_HOLD'):
            m.deliver_trust()
        mkdir.assert_not_called();write.assert_not_called()
    def test_role_result_holds_owner_capability(self):
        fixture=b'DATABASE_URL=postgresql://aoe2hd_user:fixture@127.0.0.1:5432/aoe2hd_db'
        with mock.patch.object(m,'verify_heartbeat_source'),mock.patch.object(m,'read_fixed',side_effect=[fixture,None,None]*2),\
             mock.patch.object(m.subprocess,'run',return_value=mock.Mock(returncode=0,stdout=b'aoe2hd_user|aoe2hd_user|aoe2hd_db|owner_capable\n')) as run:
            out=m.attest_role()
        self.assertEqual(out['status'],'HOLD_HEARTBEAT_OWNER_CAPABLE')
        self.assertFalse(out['maintenance_admitted'])
        self.assertNotIn('fixture',str(out))
        self.assertNotIn('fixture',str(run.call_args.args))
        self.assertEqual(run.call_args.kwargs['env']['PGPASSWORD'],'fixture')
    def test_config_drift_rejected_after_readonly_query(self):
        fixture=b'DATABASE_URL=postgresql://aoe2hd_user:fixture@127.0.0.1:5432/aoe2hd_db'
        with mock.patch.object(m,'verify_heartbeat_source'),mock.patch.object(m,'read_fixed',side_effect=[fixture,None,None,fixture+b'x',None,None]),\
             mock.patch.object(m.subprocess,'run',return_value=mock.Mock(returncode=0,stdout=b'')),self.assertRaisesRegex(m.Hold,'CONFIG_DRIFT'):
            m.attest_role()
    def test_nonce_invalid_before_any_stage_read(self):
        with mock.patch.object(m,'stage_read') as read,self.assertRaisesRegex(m.Hold,'NONCE_INVALID'):
            m.deliver_permit('../other')
        read.assert_not_called()

if __name__=='__main__':
    unittest.main()
