"""Adversarial one-use Lobby-only P256 root packet contract. No live DB/funds."""
import base64
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import c03_lobby_hd_v1_root_executor as e

def req(clock,nonce='a'*64):
    r={'schema':e.SCHEMA,'action':e.ACTION,'phase':'install',
       'source_head':e.HEAD,'host':'HEL1','database':'aoe2hd_db',
       'owner_public_sha256':e.PUBLIC_SHA,'root_executor_sha256':e.sha(Path(e.__file__).read_bytes()),
       'sql_install_sha256':e.SQL_INSTALL,'sql_inverse_sha256':e.SQL_INVERSE,
       'source_contract_sha256':e.CONTRACT,
       'social_installed_receipt_sha256':e.SOCIAL_INSTALLED_SHA,
       'hba_sha256':e.HBA_SHA,'financial_authorized':False,
       'funding_authorized':False,'de_database_authorized':False,
       'raw_event_grants_authorized':False,'hba_mutation_authorized':False,
       'nonce':nonce,'not_before':(clock-timedelta(seconds=5)).strftime('%Y-%m-%dT%H:%M:%SZ'),
       'expires_at':(clock+timedelta(minutes=10)).strftime('%Y-%m-%dT%H:%M:%SZ')}
    return r

class LobbySignedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='we1-lobby-key-test-')
        cls.dir=Path(cls.tmp.name)
        subprocess.run(['/usr/bin/openssl','ecparam','-name','prime256v1','-genkey','-noout',
                        '-out',str(cls.dir/'private.pem')],check=True,capture_output=True)
        subprocess.run(['/usr/bin/openssl','pkey','-in',str(cls.dir/'private.pem'),'-pubout',
            '-outform','DER','-out',str(cls.dir/'public.der')],check=True,capture_output=True)
        cls.public=(cls.dir/'public.der').read_bytes()[-65:]
        assert len(cls.public)==65 and cls.public[0]==4
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def sign(self,request,purpose=e.DOMAIN):
        message=self.dir/'message'
        message.write_bytes(purpose+e.canonical(request))
        cp=subprocess.run(['/usr/bin/openssl','dgst','-sha256','-sign',str(self.dir/'private.pem'),
                           '-out',str(self.dir/'signature.der'),str(message)],capture_output=True)
        self.assertEqual(cp.returncode,0)
        packet={'schema':e.PACKET_SCHEMA,'request':request,
                'signature_der_b64':base64.b64encode((self.dir/'signature.der').read_bytes()).decode()}
        return e.canonical(packet)+b'\n'

    def signed(self,request,purpose=e.DOMAIN,now=None):
        with patch.object(e,'PUBLIC_SHA',e.sha(self.public)):
            r=dict(request)
            r['owner_public_sha256']=e.PUBLIC_SHA
            return e.signed(self.sign(r,purpose),self.public,r['phase'],now=now)

    def test_valid_real_ecdsa_p256(self):
        now=datetime.now(timezone.utc)
        result=self.signed(req(now),now=now)
        self.assertEqual(result['nonce'],'a'*64)

    def test_negative_scope_and_identity(self):
        now=datetime.now(timezone.utc)
        base=req(now)
        for changes in [
            {'source_head':'0'*40},{'database':'aoe2de_db'},
            {'financial_authorized':True},{'funding_authorized':True},
            {'de_database_authorized':True},{'hba_mutation_authorized':True},
            {'raw_event_grants_authorized':True},
            {'sql_install_sha256':'0'*64},{'sql_inverse_sha256':'0'*64},
            {'social_installed_receipt_sha256':'0'*64},
            {'hba_sha256':'0'*64},{'root_executor_sha256':'0'*64},
            {'nonce':'0'*64},{'nonce':'not-hex'},
            {'action':'SOCIAL_SQL_ONLY'},
            {'host':'OTHER_HOST'},{'unexpected':'field'}]:
            with self.subTest(changes=changes):
                altered=base|changes
                with self.assertRaises(e.Hold):
                    self.signed(altered,now=now)

    def test_no_phase_confusion(self):
        now=datetime.now(timezone.utc)
        altered=req(now)|{'phase':'inverse'}
        with patch.object(e,'PUBLIC_SHA',e.sha(self.public)):
            altered['owner_public_sha256']=e.PUBLIC_SHA
            packet=self.sign(altered)
            with self.assertRaises(e.Hold):
                e.signed(packet,self.public,'install',now=now)

    def test_wrong_purpose_and_expired_or_oversized(self):
        now=datetime.now(timezone.utc)
        with self.assertRaises(e.Hold):
            self.signed(req(now),purpose=b'AOE2WAR-WE1-CHAT-SOCIAL-HD-V2-SQL-ONLY-V1\0',now=now)
        with self.assertRaises(e.Hold):
            self.signed(req(now),now=now+timedelta(minutes=15))
        with self.assertRaises(e.Hold):
            self.signed(req(now)|{'expires_at':(now+timedelta(minutes=25)).strftime('%Y-%m-%dT%H:%M:%SZ')},now=now)

    def test_public_key_mismatch(self):
        now=datetime.now(timezone.utc)
        packet=self.sign(req(now))
        with self.assertRaises(e.Hold):e.signed(packet,self.public,'install',now=now)

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(e.Hold):e.parse(b'{"schema":"x","schema":"y"}')

    def test_journal_once_and_hold_after_attempt(self):
        with tempfile.TemporaryDirectory(prefix='lobby-journal-') as td,patch.object(e,'STATE',Path(td)):
            self.assertEqual(e.phase_expected('install'),(1,'0'*64))
            (Path(td)/'transition-00000001-a.json').write_text('{}')
            with self.assertRaises(e.Hold):e.phase_expected('install')

    def test_literal_source_scopes(self):
        source=Path(e.__file__).read_text()
        self.assertIn('financial_authorized\':False',source)
        self.assertIn('de_database_authorized\':False',source)
        self.assertIn('UNTRUSTED_FILE_',source)
        self.assertIn('owner_public_sha256',source)
        self.assertIn('O_EXCL',source)
        self.assertIn('os.setuid(postgres.pw_uid)',source)
        self.assertNotIn('shell=True',source)
        self.assertIn('PASS_WE1_PRODUCTION_LOBBY_POSTIMAGE',source)

if __name__=='__main__':unittest.main()
