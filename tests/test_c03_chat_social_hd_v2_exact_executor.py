"""Pure offline adversarial boundaries for Social-only exact SQL executor.

No live database, root admission, HBA edit or owner private-key access.
"""
import base64
from datetime import datetime, timezone, timedelta
import importlib.util
import json
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/c03_chat_social_hd_v2_exact_executor.py'
spec = importlib.util.spec_from_file_location('chat_social_executor', SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class SocialExactExecutorTests(unittest.TestCase):
    def request(self, **overrides):
        now = datetime(2026, 11, 20, 1, 1, tzinfo=timezone.utc)
        q = dict(schema=m.SCHEMA, action=m.ACTION, phase='install',
                 host='HEL1', database='aoe2hd_db', source_commit=m.SOURCE,
                 file_sha256={k: d for k, (_, d) in m.FILES.items()},
                 owner_public_sha256='ab'*32, hba_sha256=m.HBA_SHA256,
                 nonce='1a'*32,
                 not_before=(now-timedelta(seconds=5)).strftime('%Y-%m-%dT%H:%M:%SZ'),
                 expires_at=(now+timedelta(seconds=300)).strftime('%Y-%m-%dT%H:%M:%SZ'),
                 financial_authorized=False, funding_authorized=False,
                 hba_mutation_authorized=False, de_database_authorized=False,
                 raw_event_grants_authorized=False)
        q.update(overrides)
        return q, now

    def test_exact_purpose_and_dedicated_trust_path(self):
        self.assertEqual(m.ACTION, 'CHAT_SOCIAL_HD_V2_SQL_ONLY')
        self.assertIn(b'CHAT-SOCIAL-HD-V2', m.DOMAIN)
        self.assertNotIn(b'LIBRARY', m.DOMAIN)
        self.assertNotIn('library', str(m.ROOT))
        self.assertIn('chat-social', str(m.STATE))

    def test_source_pin_and_five_files(self):
        self.assertEqual(m.SOURCE, '5cf4f223a7b187f6596b6a9caac26aec7afd6e94')
        self.assertEqual(m.FILES['install'][1], '9793ff39ca80d646a89041f0174f42bb717ae3e649e49f8d68d6f102792f5c51')
        self.assertEqual(m.FILES['inverse'][1], '84114bac7b3e15f4cadaf3a566f705440eeb9cf8ba63f3be97249652d5f25449')
        self.assertEqual(len(m.FILES), 5)

    def test_exact_request(self):
        q,now=self.request()
        self.assertEqual(m.verify_scope(q,q['owner_public_sha256'],now,'install'),q)

    def test_reject_wrong_phase(self):
        q,now=self.request()
        with self.assertRaises(m.Hold):m.verify_scope(q,q['owner_public_sha256'],now,'inverse')

    def test_reject_wrong_db(self):
        q,now=self.request(database='aoe2de_db')
        with self.assertRaises(m.Hold):m.verify_scope(q,q['owner_public_sha256'],now,'install')

    def test_reject_wrong_action(self):
        q,now=self.request(action='LIBRARY_HD_PROJECTIONS_ONLY')
        with self.assertRaises(m.Hold):m.verify_scope(q,q['owner_public_sha256'],now,'install')

    def test_reject_wrong_source(self):
        q,now=self.request(source_commit='1804cef797ba6f0bbd7a7153afc20d1f0e2b67a8')
        with self.assertRaises(m.Hold):m.verify_scope(q,q['owner_public_sha256'],now,'install')

    def test_reject_wrong_sql_bytes(self):
        q,now=self.request()
        q['file_sha256']['install']='00'*32
        with self.assertRaises(m.Hold):m.verify_scope(q,q['owner_public_sha256'],now,'install')

    def test_reject_hba_drift(self):
        q,now=self.request(hba_sha256='11'*32)
        with self.assertRaises(m.Hold):m.verify_scope(q,q['owner_public_sha256'],now,'install')

    def test_reject_funding_flag(self):
        q,now=self.request(funding_authorized=True)
        with self.assertRaises(m.Hold):m.verify_scope(q,q['owner_public_sha256'],now,'install')

    def test_reject_financial_flag(self):
        q,now=self.request(financial_authorized=True)
        with self.assertRaises(m.Hold):m.verify_scope(q,q['owner_public_sha256'],now,'install')

    def test_reject_de_flag(self):
        q,now=self.request(de_database_authorized=True)
        with self.assertRaises(m.Hold):m.verify_scope(q,q['owner_public_sha256'],now,'install')

    def test_reject_hba_mutation_flag(self):
        q,now=self.request(hba_mutation_authorized=True)
        with self.assertRaises(m.Hold):m.verify_scope(q,q['owner_public_sha256'],now,'install')

    def test_reject_raw_grant_flag(self):
        q,now=self.request(raw_event_grants_authorized=True)
        with self.assertRaises(m.Hold):m.verify_scope(q,q['owner_public_sha256'],now,'install')

    def test_reject_nonce_zero(self):
        q,now=self.request(nonce='0'*64)
        with self.assertRaises(m.Hold):m.verify_scope(q,q['owner_public_sha256'],now,'install')

    def test_reject_extra_json_key(self):
        q,now=self.request(unexpected=True)
        with self.assertRaises(m.Hold):m.verify_scope(q,q['owner_public_sha256'],now,'install')

    def test_reject_expired(self):
        q,now=self.request()
        q['expires_at']=(now-timedelta(seconds=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
        with self.assertRaises(m.Hold):m.verify_scope(q,q['owner_public_sha256'],now,'install')

    def test_reject_oversized_time_window(self):
        q,now=self.request()
        q['expires_at']=(now+timedelta(seconds=901)).strftime('%Y-%m-%dT%H:%M:%SZ')
        with self.assertRaises(m.Hold):m.verify_scope(q,q['owner_public_sha256'],now,'install')

    def test_reject_duplicate_keys(self):
        with self.assertRaises(m.Hold):
            m.strict_json(b'{"schema":"x","schema":"y"}')

    def test_reject_unordered_json(self):
        with self.assertRaises(m.Hold):
            m.strict_json(b'{"z":1,"a":2}')

    def test_signed_packet_domain_separation(self):
        q,now=self.request(owner_public_sha256=m.digest(b'\x04'+b'A'*64))
        public=b'\x04'+b'A'*64
        captured=[]
        packet={'schema':m.PACKET_SCHEMA,'request':q,
                'signature_der_b64':base64.b64encode(b'\x30'+b'A'*69).decode()}
        raw=m.canonical(packet)+b'\n'
        m.verify_signed_packet(raw,public,now,'install',
             verifier=lambda message,sig,key:(captured.append(message),True)[1])
        self.assertEqual(captured,[m.DOMAIN+m.canonical(q)])

    def test_wrong_packet_scope(self):
        q,now=self.request(owner_public_sha256=m.digest(b'\x04'+b'A'*64))
        packet={'schema':'library.packet','request':q,
                'signature_der_b64':base64.b64encode(b'\x30'+b'A'*69).decode()}
        with self.assertRaises(m.Hold):
            m.verify_signed_packet(m.canonical(packet),b'\x04'+b'A'*64,now,'install',verifier=lambda *x:True)

    def test_signature_rejected(self):
        q,now=self.request(owner_public_sha256=m.digest(b'\x04'+b'A'*64))
        packet={'schema':m.PACKET_SCHEMA,'request':q,
                'signature_der_b64':base64.b64encode(b'\x30'+b'A'*69).decode()}
        with self.assertRaises(m.Hold):
            m.verify_signed_packet(m.canonical(packet),b'\x04'+b'A'*64,now,'install',verifier=lambda *x:False)

    def test_install_order_and_acl_comparison(self):
        history=[]
        data={x:x.encode() for x in m.FILES}
        def runner(sql,readonly=False):
            name=sql.decode()
            history.append((name,readonly))
            return 'same-acl' if name=='acl' else name
        r=m.run_transaction(data,'install',runner)
        self.assertEqual(r['status'],'INSTALLED_POSTIMAGE_PASS')
        self.assertEqual(history,[('pre',True),('acl',True),('install',False),('post',True),('acl',True)])

    def test_postimage_failure_runs_inverse(self):
        history=[]
        data={x:x.encode() for x in m.FILES}
        def runner(sql,readonly=False):
            name=sql.decode()
            history.append(name)
            if name=='post': raise m.Hold('POST_BAD')
            return 'acl-ok' if name=='acl' else name
        r=m.run_transaction(data,'install',runner)
        self.assertEqual(r['status'],'AUTO_INVERSE_PASS_AFTER_POSTIMAGE_HOLD')
        self.assertEqual(history,['pre','acl','install','post','inverse','pre','acl'])

    def test_failed_inverse_is_critical(self):
        data={x:x.encode() for x in m.FILES}
        def runner(sql,readonly=False):
            if sql in (b'post',b'inverse'):raise m.Hold('BAD')
            return 'acl-ok' if sql==b'acl' else 'ok'
        self.assertEqual(m.run_transaction(data,'install',runner)['status'],'CRITICAL_MANUAL_RECOVERY_REQUIRED')

    def test_inverse_order(self):
        history=[]
        data={x:x.encode() for x in m.FILES}
        def runner(sql,readonly=False):
            history.append(sql.decode())
            return 'acl-ok' if sql==b'acl' else 'ok'
        self.assertEqual(m.run_transaction(data,'inverse',runner)['status'],'INVERSE_PREIMAGE_PASS')
        self.assertEqual(history,['post','acl','inverse','pre','acl'])

    def test_inverse_acl_drift_holds(self):
        acl_calls=[]
        data={x:x.encode() for x in m.FILES}
        def runner(sql,readonly=False):
            if sql==b'acl':
                acl_calls.append(1)
                return str(len(acl_calls))
            return 'ok'
        self.assertEqual(m.run_transaction(data,'inverse',runner)['status'],'CRITICAL_PHASE_UNCERTAIN_NO_RETRY')

    def test_no_arbitrary_sql_cli(self):
        self.assertEqual(m.ACTION,'CHAT_SOCIAL_HD_V2_SQL_ONLY')
        self.assertNotIn('shell=True',SOURCE.read_text())
        self.assertNotIn('os.system(',SOURCE.read_text())


class SocialDurablePermitLifecycleTests(unittest.TestCase):
    @staticmethod
    def reader(path):
        return path.read_bytes()

    def test_signed_delivery_contract_is_phase_dynamic_and_immutable(self):
        bootstrap=(SOURCE.parent/'c03_chat_social_root_enroll_v1.py').read_text()
        self.assertIn("phase=packet['request'].get('phase')",bootstrap)
        self.assertIn("module.verify_signed_packet(data,root_file(PUBLIC,128),datetime.now(timezone.utc),phase)",bootstrap)
        self.assertIn('module.next_transition(STATE,reader=root_file)',bootstrap)
        self.assertIn('module.no_pending_permit(ROOT,STATE)',bootstrap)
        self.assertIn('module.permit_path(phase,nonce)',bootstrap)
        self.assertNotIn("verify_signed_packet(data,root_file(PUBLIC,128),datetime.now(timezone.utc),'install')",bootstrap)
        self.assertIn('newfile(target,data)',bootstrap)

    def test_actual_journal_install_inverse_repeat_install_rehearsal(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root'
            state=Path(tmp)/'state'
            root.mkdir();state.mkdir()
            db={'installed':False}
            initial,number,prior=m.next_transition(state,reader=self.reader)
            self.assertEqual((initial,number,prior),('install',1,'0'*64))
            sql={name:name.encode() for name in m.FILES}
            def postgres_shadow(sql_bytes,readonly=False):
                name=sql_bytes.decode()
                if name=='pre':
                    if db['installed']:raise m.Hold('PREIMAGE_MISMATCH')
                elif name=='post':
                    if not db['installed']:raise m.Hold('POSTIMAGE_MISMATCH')
                elif name=='install':
                    if db['installed']:raise m.Hold('DOUBLE_INSTALL')
                    db['installed']=True
                elif name=='inverse':
                    if not db['installed']:raise m.Hold('DOUBLE_INVERSE')
                    db['installed']=False
                return 'unchanged-legacy-acl' if name=='acl' else name
            with patch.object(m,'ROOT',root):
                for expected_number,(phase,nonce) in enumerate([
                        ('install','11'*32),('inverse','22'*32),
                        ('install','33'*32)],1):
                    expected,sequence,previous=m.next_transition(state,reader=self.reader)
                    self.assertEqual((expected,sequence),(phase,expected_number))
                    permit=m.permit_path(phase,nonce)
                    permit.write_bytes(('SIGNED_PACKET_'+phase+'_'+nonce).encode())
                    with self.assertRaisesRegex(m.Hold,'UNCONSUMED_PERMIT'):
                        m.no_pending_permit(root,state,reader=self.reader)
                    permit_hash=m.digest(permit.read_bytes())
                    m.write_once(state,f'transition-{sequence:08d}-{nonce}.json',
                        m.canonical({'sequence':sequence,'nonce':nonce,
                                     'phase':phase,'previous_receipt_sha256':previous,
                                     'permit_sha256':permit_hash})+b'\n')
                    with self.assertRaises((m.Hold,OSError)):
                        m.next_transition(state,reader=self.reader)
                    m.write_once(state,'nonce-'+nonce+'.consumed',
                        m.canonical({'nonce':nonce,'phase':phase,
                                     'permit_sha256':permit_hash,
                                     'status':'CONSUMED_BEFORE_SQL'})+b'\n')
                    evidence=m.run_transaction(sql,phase,postgres_shadow)
                    wanted='INSTALLED_POSTIMAGE_PASS' if phase=='install' else 'INVERSE_PREIMAGE_PASS'
                    self.assertEqual(evidence['status'],wanted)
                    receipt={'status':wanted,'phase':phase,'nonce':nonce,
                             'sequence':sequence,'previous_receipt_sha256':previous,
                             'permit_sha256':permit_hash,'source_commit':m.SOURCE}
                    m.write_once(state,f'receipt-{nonce}.json',m.canonical(receipt)+b'\n')
                    m.no_pending_permit(root,state,reader=self.reader)
                    expected_next='inverse' if phase=='install' else 'install'
                    self.assertEqual(m.next_transition(state,reader=self.reader)[0],expected_next)
                self.assertTrue(db['installed'])
                self.assertEqual(len(list(state.glob('receipt-*.json'))),3)
                self.assertEqual(len(list(root.glob(m.PERMIT_PREFIX+'-*.json'))),3)

    def test_nonce_reuse_and_unconsumed_permit_denied(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root';state=Path(tmp)/'state'
            root.mkdir();state.mkdir()
            with patch.object(m,'ROOT',root):
                path=m.permit_path('install','ad'*32)
                path.write_bytes(b'fake-packet')
                with self.assertRaises(m.Hold):
                    m.no_pending_permit(root,state,reader=self.reader)
                self.assertEqual(m.permit_path('install','ad'*32),path)
                with self.assertRaises(m.Hold):m.permit_path('inverse','0'*64)
                with self.assertRaises(m.Hold):m.permit_path('install','AD'*32)
                with self.assertRaises(m.Hold):m.permit_path('library','ad'*32)

    def test_orphan_and_unknown_durable_evidence_denied(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            state=Path(tmp)
            (state/('nonce-'+'aa'*32+'.consumed')).write_text('{}')
            with self.assertRaises(m.Hold):
                m.next_transition(state,reader=self.reader)
            (state/('nonce-'+'aa'*32+'.consumed')).unlink()
            (state/'transition-forged.json').write_text('{}')
            with self.assertRaises(m.Hold):
                m.next_transition(state,reader=self.reader)

    def test_bad_receipt_blocks_next_action(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            state=Path(tmp);nonce='cd'*32
            h='ef'*32
            m.write_once(state,f'transition-00000001-{nonce}.json',
                m.canonical({'sequence':1,'nonce':nonce,'phase':'install',
                             'previous_receipt_sha256':'0'*64,'permit_sha256':h})+b'\n')
            m.write_once(state,f'nonce-{nonce}.consumed',
                m.canonical({'nonce':nonce,'phase':'install',
                             'status':'CONSUMED_BEFORE_SQL','permit_sha256':h})+b'\n')
            m.write_once(state,f'receipt-{nonce}.json',
                m.canonical({'sequence':1,'nonce':nonce,'phase':'install',
                             'status':'CRITICAL_MANUAL_RECOVERY_REQUIRED',
                             'previous_receipt_sha256':'0'*64,
                             'permit_sha256':h,'source_commit':m.SOURCE})+b'\n')
            with self.assertRaisesRegex(m.Hold,'INCOMPLETE_OR_FAILED_SQL_TRANSITION'):
                m.next_transition(state,reader=self.reader)

if __name__=='__main__':unittest.main()
