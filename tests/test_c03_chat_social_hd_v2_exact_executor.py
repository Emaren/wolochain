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

if __name__=='__main__':unittest.main()
