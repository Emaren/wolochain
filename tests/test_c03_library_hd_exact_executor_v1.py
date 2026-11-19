"""Pure policy negatives; no live database or root admission."""
import base64
from datetime import datetime,timedelta,timezone
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path
import unittest

P=Path(__file__).resolve().parents[1]/'scripts/c03_library_hd_exact_executor_v1.py'
spec=importlib.util.spec_from_file_location('libexec',P)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
NOW=datetime(2026,11,19,20,0,0,tzinfo=timezone.utc)
PUB=b'\x04'+bytes(range(1,65))

def request(phase='install'):
    return dict(schema=m.SCHEMA,action=m.ACTION,phase=phase,host='HEL1',database='aoe2hd_db',source_commit=m.SOURCE,
                file_sha256={k:s for k,(_,s) in m.FILES.items()},owner_public_sha256=m.digest(PUB),nonce='a'*64,
                not_before='2026-11-19T19:59:00Z',expires_at='2026-11-19T20:10:00Z',
                financial_authorized=False,funding_authorized=False,hba_mutation_authorized=False,
                de_database_authorized=False,raw_event_grants_authorized=False)

def packet(r=None):
    return m.canonical({'schema':m.PACKET_SCHEMA,'request':r or request(),
                        'signature_der_b64':base64.b64encode(b'\x30'+b'Z'*68).decode()})

class ExecutorBoundary(unittest.TestCase):
    def test_purpose_positive_mock_verifier(self):
        self.assertEqual(m.verify_signed_packet(packet(),PUB,NOW,'install',verifier=lambda a,b,c:True)['database'],'aoe2hd_db')
    def test_wrong_database(self):
        r=request();r['database']='aoe2de_db';self.bad(r)
    def test_wrong_role_or_action(self):
        r=request();r['action']='C03_FINANCIAL';self.bad(r)
    def test_wrong_phase(self):
        self.bad(request('inverse'))
    def test_wrong_source(self):
        r=request();r['source_commit']='0'*40;self.bad(r)
    def test_modified_install_sql(self):
        r=request();r['file_sha256']['install']='0'*64;self.bad(r)
    def test_modified_inverse_sql(self):
        r=request();r['file_sha256']['inverse']='0'*64;self.bad(r)
    def test_modified_witness(self):
        r=request();r['file_sha256']['pre']='0'*64;self.bad(r)
    def test_financial_authorization(self):
        r=request();r['financial_authorized']=True;self.bad(r)
    def test_hba_change(self):
        r=request();r['hba_mutation_authorized']=True;self.bad(r)
    def test_raw_grant(self):
        r=request();r['raw_event_grants_authorized']=True;self.bad(r)
    def test_wrong_public_key(self):
        self.bad(request(),b'\x04'+b'1'*64)
    def test_fake_signature(self):
        with self.assertRaises(m.Hold):m.verify_signed_packet(packet(),PUB,NOW,'install',verifier=lambda a,b,c:False)
    def test_unknown_schema_key(self):
        r=request();r['sql']='select arbitrary';self.bad(r)
    def test_expired(self):
        with self.assertRaises(m.Hold):m.verify_scope(request(),m.digest(PUB),NOW+timedelta(hours=1),'install')
    def test_oversize_window(self):
        r=request();r['expires_at']='2026-11-19T20:20:00Z';self.bad(r)
    def test_nonce_wrong(self):
        r=request();r['nonce']='0'*64;self.bad(r)
    def test_dedup_json_keys(self):
        with self.assertRaises(m.Hold):m.strict_json(b'{"a":1,"a":2}')
    def test_noncanonical(self):
        with self.assertRaises(m.Hold):m.strict_json(b'{"b":2, "a":1}')
    def test_rollback_fresh_phase(self):
        r=request('inverse');self.assertEqual(m.verify_signed_packet(packet(r),PUB,NOW,'inverse',verifier=lambda a,b,c:True)['phase'],'inverse')
    def test_rollback_cannot_reuse_install_permit(self):
        r=request('install');self.bad(r,phase='inverse')
    def test_runner_rejects_nonroot(self):
        original=m.os.geteuid
        try:
            m.os.geteuid=lambda:501
            with self.assertRaises(m.Hold):m.execute('install')
        finally:m.os.geteuid=original
    def test_nonce_replay_is_denied(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)
            m.write_once(path,'nonce-'+('a'*64)+'.consumed',b'consumed')
            with self.assertRaises(FileExistsError):m.write_once(path,'nonce-'+('a'*64)+'.consumed',b'replayed')
    def test_postimage_failure_invokes_inverse(self):
        calls=[]
        def runner(raw,readonly=False):
            calls.append(raw)
            if raw==b'post':raise m.Hold('POST_IMAGE_FAILURE')
            return m.digest(raw)
        result=m.run_transaction({'pre':b'pre','install':b'install','post':b'post','inverse':b'inverse'},'install',runner)
        self.assertEqual(result['status'],'AUTO_INVERSE_PASS_AFTER_POSTIMAGE_HOLD')
        self.assertEqual(calls,[b'pre',b'install',b'post',b'inverse',b'pre'])
    def test_inverse_failure_produces_recovery_hold(self):
        calls=[]
        def runner(raw,readonly=False):
            calls.append(raw)
            if raw in (b'post',b'inverse'):raise m.Hold('FAILURE')
            return m.digest(raw)
        result=m.run_transaction({'pre':b'pre','install':b'install','post':b'post','inverse':b'inverse'},'install',runner)
        self.assertEqual(result['status'],'CRITICAL_MANUAL_RECOVERY_REQUIRED')
        self.assertEqual(calls,[b'pre',b'install',b'post',b'inverse'])
    def test_preimage_failure_no_install(self):
        calls=[]
        def runner(raw,readonly=False):
            calls.append(raw);raise m.Hold('PRE_IMAGE_DENIED')
        result=m.run_transaction({'pre':b'pre','install':b'install','post':b'post','inverse':b'inverse'},'install',runner)
        self.assertEqual(result['status'],'CRITICAL_PHASE_UNCERTAIN_NO_RETRY')
        self.assertEqual(calls,[b'pre'])
    def test_ecdsa_real_p256_signature(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            priv=root/'priv.pem';pub=root/'pub.der';msg=root/'msg';sig=root/'sig.der'
            subprocess.run(['openssl','ecparam','-name','prime256v1','-genkey','-noout','-out',str(priv)],capture_output=True,check=True)
            subprocess.run(['openssl','pkey','-in',str(priv),'-pubout','-outform','DER','-out',str(pub)],capture_output=True,check=True)
            raw=pub.read_bytes();self.assertTrue(raw.startswith(m.SPKI))
            x963=raw[len(m.SPKI):]
            req=request();req['owner_public_sha256']=m.digest(x963)
            msg.write_bytes(m.DOMAIN+m.canonical(req))
            subprocess.run(['openssl','dgst','-sha256','-sign',str(priv),'-out',str(sig),str(msg)],capture_output=True,check=True)
            packet=m.canonical({'schema':m.PACKET_SCHEMA,'request':req,'signature_der_b64':base64.b64encode(sig.read_bytes()).decode()})
            self.assertEqual(m.verify_signed_packet(packet,x963,NOW,'install')['nonce'],'a'*64)
            tampered=json.loads(packet);tampered['request']['nonce']='b'*64
            with self.assertRaises(m.Hold):m.verify_signed_packet(m.canonical(tampered),x963,NOW,'install')
    def bad(self,r,pub=PUB,phase='install'):
        with self.assertRaises(m.Hold):m.verify_signed_packet(packet(r),pub,NOW,phase,verifier=lambda a,b,c:True)
if __name__=='__main__':unittest.main()
