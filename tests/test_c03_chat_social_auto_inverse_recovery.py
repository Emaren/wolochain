"""Adversarial full-journal recovery and real P256 signature verification.

Creates temporary files and temporary test signing keys only. Never invokes
production root/SQL/Keychain, reuses the old nonce, or changes finance.
"""
import base64
from datetime import datetime,timezone,timedelta
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
ex=load('we1_recovery_exec',ROOT/'scripts/c03_chat_social_hd_v2_exact_executor.py')
rec=load('we1_recovery_bootstrap',ROOT/'scripts/c03_chat_social_auto_inverse_recovery_v1.py')
owner=load('we1_recovery_owner',ROOT/'scripts/c03_chat_social_recovery_owner_permit_builder_v1.py')

class ImmutableRecoveryJournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='we1-social-recovery-test-')
        self.addCleanup(self.tmp.cleanup)
        self.state=Path(self.tmp.name)/'state';self.state.mkdir()
        self.root=Path(self.tmp.name)/'root';self.root.mkdir()
        self.p=patch.object(ex,'ROOT',self.root);self.p.start();self.addCleanup(self.p.stop)
        self.failed_nonce='11'*32
        self.failed_acl='a4'*32
        self.failed_pre='b5'*32
        self.failed_receipt=None
        self.recover_nonce='22'*32
        self.permit=b'SIGNED_OWNER_RECOVERY_PACKET_TEST_ONLY'
    @staticmethod
    def read(path):return path.read_bytes()
    def file(self,path,obj):
        ex.write_once(path.parent,path.name,ex.canonical(obj)+b'\n')
    def original_fail(self,status='AUTO_INVERSE_PASS_AFTER_POSTIMAGE_HOLD',pre=None,acl=None):
        nonce=self.failed_nonce
        permit_hash='77'*32
        self.file(self.state/f'transition-00000001-{nonce}.json',
              dict(sequence=1,nonce=nonce,phase='install',previous_receipt_sha256='0'*64,
                   permit_sha256=permit_hash))
        self.file(self.state/f'nonce-{nonce}.consumed',
             dict(nonce=nonce,phase='install',permit_sha256=permit_hash,
                  status='CONSUMED_BEFORE_SQL'))
        obj=dict(status=status,phase='install',nonce=nonce,sequence=1,
                 source_commit=ex.SOURCE,db='aoe2hd_db',
                 financial_authorized=False,previous_receipt_sha256='0'*64,
                 permit_sha256=permit_hash,hba_sha256=ex.HBA_SHA256,
                 preimage_stdout_sha256=self.failed_pre,
                 after_inverse_preimage_stdout_sha256=pre or self.failed_pre,
                 acl_before_sha256=self.failed_acl,
                 after_inverse_acl_sha256=acl or self.failed_acl)
        self.file(self.state/f'receipt-{nonce}.json',obj)
        self.failed_receipt=self.read(self.state/f'receipt-{nonce}.json')
        return obj
    def add_recovery(self,change=None,partial=None):
        nonce=self.recover_nonce
        prev=ex.digest(self.failed_receipt)
        hashp=ex.digest(self.permit)
        (self.root/f'signed-one-use-chat-social-auto-inverse-recovery-{nonce}.json').write_bytes(self.permit)
        self.file(self.state/f'recovery-transition-00000002-{nonce}.json',
            dict(sequence=2,nonce=nonce,phase='recovery',previous_receipt_sha256=prev,
                 failed_nonce=self.failed_nonce,failed_sequence=1,
                 failed_receipt_sha256=prev,permit_sha256=hashp))
        if partial=='intent':return None
        self.file(self.state/f'recovery-nonce-{nonce}.consumed',
             dict(nonce=nonce,phase='recovery',permit_sha256=hashp,
                  status='CONSUMED_BEFORE_RECOVERY'))
        if partial=='nonce':return None
        receipt=dict(status='AUTO_INVERSE_RECOVERY_EPOCH_PASS',phase='recovery',
             nonce=nonce,sequence=2,source_commit=ex.SOURCE,
             previous_receipt_sha256=prev,failed_nonce=self.failed_nonce,
             failed_sequence=1,failed_receipt_sha256=prev,permit_sha256=hashp,
             live_preimage_stdout_sha256=self.failed_pre,
             live_acl_sha256=self.failed_acl,
             hba_sha256=ex.HBA_SHA256,financial_authorized=False,
             funding_authorized=False,de_database_authorized=False,
             new_postimage_sha256=ex.FILES['post'][1],
             new_executor_sha256=ex.digest(Path(ex.__file__).read_bytes()),
             old_executor_sha256=rec.OLD_EXEC_SHA)
        if change:receipt.update(change)
        self.file(self.state/f'recovery-receipt-{nonce}.json',receipt)
        return self.read(self.state/f'recovery-receipt-{nonce}.json')
    def add_new_install(self,prior):
        nonce='33'*32
        permit_hash='55'*32
        self.file(self.state/f'transition-00000003-{nonce}.json',
            dict(sequence=3,nonce=nonce,phase='install',previous_receipt_sha256=prior,
                 permit_sha256=permit_hash))
        self.file(self.state/f'nonce-{nonce}.consumed',
            dict(nonce=nonce,phase='install',permit_sha256=permit_hash,
                 status='CONSUMED_BEFORE_SQL'))
        self.file(self.state/f'receipt-{nonce}.json',
            dict(status='INSTALLED_POSTIMAGE_PASS',phase='install',
                 nonce=nonce,sequence=3,source_commit=ex.SOURCE,
                 previous_receipt_sha256=prior,permit_sha256=permit_hash))
    def test_real_auto_inverse_immutable_recovery_then_fresh_install(self):
        self.assertEqual(ex.next_transition(self.state,reader=self.read),
                         ('install',1,'0'*64))
        self.original_fail()
        self.assertEqual(ex.next_transition(self.state,reader=self.read),
                         ('recovery',2,ex.digest(self.failed_receipt)))
        original=self.failed_receipt
        recovered=self.add_recovery()
        self.assertEqual(ex.next_transition(self.state,reader=self.read),
                         ('install',3,ex.digest(recovered)))
        self.add_new_install(ex.digest(recovered))
        self.assertEqual(ex.next_transition(self.state,reader=self.read)[0:2],
                         ('inverse',4))
        self.assertEqual(original,self.read(self.state/f'receipt-{self.failed_nonce}.json'))
        self.assertEqual(len(list(self.state.glob('nonce-*.consumed'))),2)
        self.assertEqual(len(list(self.state.glob('recovery-nonce-*.consumed'))),1)
    def test_crash_after_recovery_intent_or_nonce_fails_closed(self):
        for partial in ('intent','nonce'):
            with self.subTest(partial=partial):
                self.setUp()
                self.original_fail()
                self.add_recovery(partial=partial)
                with self.assertRaises(ex.Hold):ex.next_transition(self.state,reader=self.read)
    def test_wrong_hba_acl_preimage_or_phase_fails_closed(self):
        for change in ({'hba_sha256':'00'*32},
                       {'live_acl_sha256':'00'*32},
                       {'live_preimage_stdout_sha256':'00'*32},
                       {'new_postimage_sha256':'00'*32},
                       {'new_executor_sha256':'00'*32},
                       {'status':'CRITICAL_PHASE_UNCERTAIN_NO_RETRY'},
                       {'failed_receipt_sha256':'00'*32},
                       {'financial_authorized':True}):
            with self.subTest(change=change):
                self.setUp();self.original_fail();self.add_recovery(change=change)
                with self.assertRaises(ex.Hold):ex.next_transition(self.state,reader=self.read)
    def test_unproven_original_auto_inverse_denied(self):
        for bad in ({'status':'CRITICAL_MANUAL_RECOVERY_REQUIRED'},
                    {'pre':'ee'*32},{'acl':'ff'*32}):
            with self.subTest(bad=bad):
                self.setUp();self.original_fail(**bad)
                with self.assertRaises(ex.Hold):ex.next_transition(self.state,reader=self.read)
    def test_unknown_orphan_and_replay_denied(self):
        self.original_fail()
        (self.state/'recovery-malformed-file').write_bytes(b'evil')
        with self.assertRaises(ex.Hold):ex.next_transition(self.state,reader=self.read)
        (self.state/'recovery-malformed-file').unlink()
        recovered=self.add_recovery()
        self.assertTrue(recovered)
        (self.root/f'signed-one-use-chat-social-auto-inverse-recovery-{self.recover_nonce}.json').write_bytes(b'FORGED')
        with self.assertRaises(ex.Hold):ex.next_transition(self.state,reader=self.read)
    def test_duplicate_sql_and_recovery_nonce_denied(self):
        self.original_fail()
        self.recover_nonce=self.failed_nonce
        self.add_recovery()
        with self.assertRaisesRegex(ex.Hold,'REUSED_SQL_OR_RECOVERY_NONCE'):
            ex.next_transition(self.state,reader=self.read)

class SignedRecoveryPacketTests(unittest.TestCase):
    def test_distinct_action_domain_and_hash_pins(self):
        self.assertIn(b'AUTO-INVERSE-RECOVERY-ONLY',rec.RECOVERY_DOMAIN)
        self.assertNotEqual(rec.RECOVERY_DOMAIN,owner.SQL_DOMAIN)
        self.assertNotEqual(rec.RECOVERY_ACTION,owner.SQL_ACTION)
        self.assertEqual(rec.NEW_POST_SHA,ex.FILES['post'][1])
        self.assertEqual(rec.NEW_EXEC_SHA,ex.digest(Path(ex.__file__).read_bytes()))
        self.assertEqual(owner.NEW_EXEC_SHA,rec.NEW_EXEC_SHA)
        self.assertEqual(owner.ROOT_RECOVERY_SHA,ex.digest(Path(rec.__file__).read_bytes()))
        self.assertEqual(owner.FAIL_RECEIPT_SHA,rec.FAIL_RECEIPT_SHA)
    def test_actual_openssl_ecdsa_p256_signature_and_negatives(self):
        with tempfile.TemporaryDirectory(prefix='we1-recovery-signature-') as temp:
            d=Path(temp)
            def go(*args):
                return subprocess.run(['/usr/bin/openssl',*map(str,args)],
                         capture_output=True,check=True)
            go('ecparam','-name','prime256v1','-genkey','-noout',
               '-out',d/'test-private.pem')
            go('pkey','-in',d/'test-private.pem','-pubout','-outform','DER',
               '-out',d/'test-public.der')
            public=(d/'test-public.der').read_bytes()[-65:]
            self.assertEqual(public[0],4)
            now=datetime(2026,11,20,12,0,tzinfo=timezone.utc)
            req=owner.request('recover',now,'cc'*32)
            req['owner_public_sha256']=ex.digest(public)
            with patch.object(rec,'PUBLIC_SHA',ex.digest(public)):
                def packet(q):
                    (d/'message').write_bytes(rec.RECOVERY_DOMAIN+rec.canonical(q))
                    go('dgst','-sha256','-sign',d/'test-private.pem',
                       '-out',d/'signature.der',d/'message')
                    return rec.canonical(dict(schema=rec.RECOVERY_PACKET,
                        request=q,signature_der_b64=base64.b64encode(
                              (d/'signature.der').read_bytes()).decode()))+b'\n'
                good=packet(req)
                self.assertEqual(rec.signed_recovery(good,public,now),req)
                with self.assertRaisesRegex(rec.Hold,'EXPIRED'):
                    rec.signed_recovery(good,public,now+timedelta(minutes=30))
                for update in ({'nonce':rec.FAIL_NONCE},
                               {'failed_receipt_sha256':'00'*32},
                               {'original_acl_sha256':'00'*32},
                               {'financial_authorized':True},
                               {'new_executor_sha256':'00'*32},
                               {'recovery_bootstrap_sha256':'00'*32}):
                    with self.subTest(update=update):
                        changed={**req,**update}
                        with self.assertRaises(rec.Hold):
                            rec.signed_recovery(packet(changed),public,now)
                forged=dict(json.loads(good),signature_der_b64=base64.b64encode(b'0'+b'A'*69).decode())
                with self.assertRaises(rec.Hold):
                    rec.signed_recovery(rec.canonical(forged),public,now)
class VersionedRootRecoveryCeremonyTests(unittest.TestCase):
    def test_rehearsed_one_shot_root_recovery_preserves_old_receipts(self):
        # This exercises root code and real immutable filesystem writes in a
        # nonroot disposable sandbox. Signature and real PG16 were proven in
        # separate tests; NEVER claims production admission.
        from contextlib import ExitStack
        import shutil
        with tempfile.TemporaryDirectory(prefix='we1-social-root-rehearsal-') as tmp:
            d=Path(tmp)
            root=d/'root';root.mkdir(mode=0o700)
            state=d/'state';state.mkdir(mode=0o700)
            stage=d/'stage';stage.mkdir(mode=0o700)
            lib=d/'lib';lib.mkdir(mode=0o700)
            old_sql=lib/'sql';old_sql.mkdir(mode=0o700)
            new=lib/'recovery-v1';new_sql=new/'sql'
            prior_nonce='11'*32
            original_acl='a4'*32
            original_pre='b5'*32
            original_receipt=dict(
                status='AUTO_INVERSE_PASS_AFTER_POSTIMAGE_HOLD',
                phase='install',nonce=prior_nonce,sequence=1,
                source_commit=ex.SOURCE,db='aoe2hd_db',financial_authorized=False,
                hba_sha256=ex.HBA_SHA256,
                preimage_stdout_sha256=original_pre,
                after_inverse_preimage_stdout_sha256=original_pre,
                acl_before_sha256=original_acl,
                after_inverse_acl_sha256=original_acl,
                previous_receipt_sha256='0'*64,permit_sha256='55'*32)
            failed_raw=ex.canonical(original_receipt)+b'\n'
            failhash=ex.digest(failed_raw)
            old_receipt=state/f'receipt-{prior_nonce}.json'
            old_receipt.write_bytes(failed_raw)
            (state/f'transition-00000001-{prior_nonce}.json').write_bytes(
               ex.canonical(dict(sequence=1,nonce=prior_nonce,
                   phase='install',previous_receipt_sha256='0'*64,
                   permit_sha256='55'*32))+b'\n')
            (state/f'nonce-{prior_nonce}.consumed').write_bytes(
               ex.canonical(dict(nonce=prior_nonce,phase='install',
                    permit_sha256='55'*32,status='CONSUMED_BEFORE_SQL'))+b'\n')
            # Current source bytes only, no alternate SQL or code.
            for role,(name,sha) in rec.NEW_SQL_PIN.items():
                content=(ROOT/'scripts'/name).read_bytes()
                self.assertEqual(ex.digest(content),sha)
                (stage/name).write_bytes(content)
            executor=(ROOT/'scripts/c03_chat_social_hd_v2_exact_executor.py').read_bytes()
            self.assertEqual(ex.digest(executor),rec.NEW_EXEC_SHA)
            (stage/'c03_chat_social_hd_v2_exact_executor.py').write_bytes(executor)
            for role in ('pre','acl'):
                name=rec.ORIGINAL_SQL[role][0]
                (old_sql/name).write_bytes((ROOT/'scripts'/name).read_bytes())
            (root/'owner-chat-social-p256-public-x963.bin').write_bytes(b'\x04'+b'A'*64)
            fresh_nonce='cc'*32
            (stage/rec.STAGED_RECOVERY).write_bytes(b'TEST_ONLY_FAKE_SIGNED_PACKET')
            class ExistingRoot:
                Hold=rec.Hold
                def verify_hba(self):return rec.HBA_SHA
                def no_pending_permit(self,*args,**kw):return None
                def next_transition(self,*args,**kw):
                    raise rec.Hold('INCOMPLETE_OR_FAILED_SQL_TRANSITION')
                def psql(self,data,readonly=False):
                    assert readonly
                    return original_pre if b'PASS_WE1_SOCIAL_HD_PREIMAGE' in data else original_acl
            original_loader=rec.open_module
            def trusted_loader(path,sha):
                if path==rec.OLD_EXEC:return ExistingRoot()
                module=original_loader(path,sha)
                module.ROOT=root
                return module
            with ExitStack() as st:
                for key,value in (
                    ('ROOT',root),('STATE',state),('STAGE',stage),('LIB',lib),
                    ('OLD_SQL',old_sql),('OLD_EXEC',lib/'c03_chat_social_hd_v2_exact_executor.py'),
                    ('NEW',new),('NEW_SQL',new_sql),
                    ('NEW_EXEC',new/'c03_chat_social_hd_v2_exact_executor.py'),
                    ('PUBLIC',root/'owner-chat-social-p256-public-x963.bin'),
                    ('FAIL_NONCE',prior_nonce),('FAIL_RECEIPT_SHA',failhash),
                    ('PREIMAGE_SHA',original_pre),('ACL_SHA',original_acl)):
                    st.enter_context(patch.object(rec,key,value))
                st.enter_context(patch.object(rec,'common',return_value=ExistingRoot()))
                st.enter_context(patch.object(rec,'stage',side_effect=lambda name,limit=32768:(stage/name).read_bytes()))
                st.enter_context(patch.object(rec,'root',side_effect=lambda path,limit=32768:path.read_bytes()))
                st.enter_context(patch.object(rec,'verify_dir',return_value=None))
                st.enter_context(patch.object(rec,'open_module',side_effect=trusted_loader))
                st.enter_context(patch.object(rec,'signed_recovery',return_value={'nonce':fresh_nonce}))
                result=rec.recover()
                self.assertEqual(result['status'],'PASS_SIGNED_AUTO_INVERSE_RECOVERY_NO_SQL')
                self.assertEqual(result['sequence'],2)
                self.assertEqual(old_receipt.read_bytes(),failed_raw)
                self.assertEqual((new/'c03_chat_social_hd_v2_exact_executor.py').read_bytes(),executor)
                self.assertEqual(len(list(state.glob('recovery-receipt-*.json'))),1)
                self.assertTrue((state/f'recovery-nonce-{fresh_nonce}.consumed').exists())
                self.assertTrue((root/f'signed-one-use-chat-social-auto-inverse-recovery-{fresh_nonce}.json').exists())
                with self.assertRaises(rec.Hold):
                    rec.recover()

if __name__=='__main__':unittest.main()
