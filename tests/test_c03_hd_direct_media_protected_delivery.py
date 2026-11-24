"""Focused source-only tests; never contact native DB, credentials or root."""
from pathlib import Path
import importlib.util
import unittest
import stat
from types import SimpleNamespace
from unittest import mock

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/c03_hd_direct_media_protected_delivery.py'
spec=importlib.util.spec_from_file_location('protected_delivery',SCRIPT)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class DeliveryTests(unittest.TestCase):
    def test_exact_native_heartbeat_directories_only(self):
        for path, (dev, ino, uid, gid, mode) in m.HEARTBEAT_DIR_PINS.items():
            s=SimpleNamespace(st_dev=dev,st_ino=ino,st_uid=uid,st_gid=gid,st_mode=stat.S_IFDIR|mode)
            m.check_directory(path,s,(0,),heartbeat=True)
            for key in ('st_dev','st_ino','st_uid','st_gid','st_mode'):
                changed=SimpleNamespace(**vars(s))
                setattr(changed,key,getattr(changed,key)^1)
                with self.subTest(path=path,key=key),self.assertRaises(m.Hold):
                    m.check_directory(path,changed,(0,),heartbeat=True)
            with self.assertRaises(m.Hold):
                m.check_directory(path,s,(0,),heartbeat=False)
    def test_unlisted_writable_directory_never_exempt(self):
        s=SimpleNamespace(st_uid=0,st_mode=stat.S_IFDIR|0o775)
        with self.assertRaises(m.Hold):
            m.check_directory(m.ROOT,s,(0,),heartbeat=True)
    def test_only_exact_heartbeat_files_use_native_exception(self):
        with mock.patch.object(m,'open_dir',return_value=9) as op, mock.patch.object(m,'read_at'),mock.patch.object(m.os,'close'):
            for p in m.HEARTBEAT_APP_FILES:
                m.read_fixed(p)
                op.assert_called_with(p.parent,heartbeat=True)
            for p in (m.CODE/m.EXECUTOR,m.ROOT/'review.json',m.ROOT/'permit-example.json',m.APP/'unlisted'):
                m.read_fixed(p)
                op.assert_called_with(p.parent)
    def test_hba_only_accepts_postgres_owned_ancestors(self):
        with mock.patch.object(m,'open_dir',return_value=9) as op, mock.patch.object(m,'read_at'),mock.patch.object(m.os,'close'),mock.patch.object(m.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=108)):
            m.read_fixed(m.HBA,owners=(108,))
            op.assert_called_with(m.HBA.parent,owners=(0,108))

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
