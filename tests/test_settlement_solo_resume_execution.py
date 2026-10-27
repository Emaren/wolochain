"""Signed resume boundary regressions; disposable mocks, never live authority."""
from pathlib import Path
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
import sys
import tempfile
import signal
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import settlement_financial_maintenance as m
import settlement_solo_resume as r
import settlement_solo_runtime as runtime

NOW = datetime(2026, 10, 26, 23, tzinfo=timezone.utc)
ISO = lambda t: t.strftime('%Y-%m-%dT%H:%M:%SZ')


class SoloResumeBoundaryTests(unittest.TestCase):
    def test_legacy_fence_without_pre_hold_identity_seal_can_never_resume(self):
        with patch.object(m, 'private_json', return_value=({'schema':m.FENCE_SCHEMA},'a'*64)), \
             patch.object(m, 'run') as command:
            with self.assertRaisesRegex(m.MaintenanceError, 'RESUME_CAPTURE_IDENTITIES_MISSING'):
                m.verify_resume_state(Path('/root/fence'), Path('/root/backup'),
                                      Path('/root/backup/restore.json'), {}, runner=command)
            command.assert_not_called()

    def test_resume_requires_a_fresh_separate_phase_before_systemd_or_hold_changes(self):
        for phase in ('live_capture','offline_verify','funded_activate',None):
            with self.subTest(phase=phase), patch.object(m,'run') as command:
                with self.assertRaisesRegex(m.MaintenanceError, 'RESUME_PHASE_ONLY'):
                    m.resume_existing(Path('/root/fence'), Path('/root/backup'),
                                      phase_window={'phase':phase},runner=command)
                command.assert_not_called()


class ResumeExecutionTests(unittest.TestCase):
    """Real irreversible-boundary order; only privileged systemd/I/O are fake."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).resolve()
        self.hold = self.folder / 'HOLD'
        self.hold_bytes = m.canonical({'scope_sha256':'a'*64,'permit_sha256':'b'*64})
        self.hold.write_bytes(self.hold_bytes)
        self.phase = {'schema':runtime.SCHEMA,'chain_id':'wolo-1','phase':'resume_existing',
            'operation':runtime.OPS['resume_existing'],'source_commit':'a'*40,
            'host_identity_sha256':'b'*64,'scope_sha256':'c'*64,'procedure_sha256':'d'*64,
            'nonce':'e'*32,'not_before':ISO(NOW-timedelta(seconds=1)),
            'expires_at':ISO(NOW+timedelta(minutes=20)), 'previous_phase_receipt_sha256':'f'*64,
            'resume_actions_allowed':True,'resume_sealed':{'path':'/root/plan','sha256':'f'*64},
            '_admission_guard':lambda:None}
        self.observed = {'originally_active_apps':['app1.service','app2.service'],
                         'originally_active_timers':['a.timer'],
                         'plan':{'source_commit':'a'*40},
                         'fence':{'hold_sha256':m.digest(self.hold_bytes),'permit_sha256':'b'*64}}
        self.events = []
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for obj,name,value in ((m,'HOLD',self.hold),(m,'clock',lambda:NOW),
                               (m.os,'geteuid',lambda:0),(m,'scope_digest',lambda:'a'*64),
                               (m,'TIMERS',('a.timer',)),(m,'ONESHOTS',('a.service',)),
                               (m,'APPS',('app1.service','app2.service')),
                               (m,'private_read',lambda p,**kw:Path(p).read_bytes()),
                               (m,'no_jobs',lambda runner:self.events.append('no_jobs')),
                               (m,'inactive_observation',lambda runner:None),
                               (m,'show',lambda unit,runner:{'ActiveState':'active'}),
                               (r,'verify_state',lambda *a,**kw:deepcopy(self.observed)),
                               (m,'write_new',self.write)):
            self.stack.enter_context(patch.object(obj,name,value))

    def write(self,path,raw):
        self.events.append('write:'+Path(path).name)
        with open(path,'xb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())

    def command(self,args,**kwargs):
        self.events.append(tuple(args))

    def execute(self,runner=None):
        return m.resume_existing(self.folder/'fence', self.folder,
                                 phase_window=self.phase, runner=runner or self.command)

    def test_commit_is_durable_before_hold_unlink_and_apps_precede_timers(self):
        original=r.unlink_owned_hold
        def unlink(expected):
            self.assertTrue((self.folder/r.JOURNAL).exists())
            self.assertFalse(any(isinstance(e,tuple) for e in self.events))
            self.events.append('unlink');original(expected)
        with patch.object(r,'unlink_owned_hold',side_effect=unlink):
            result=self.execute()
        self.assertFalse(result['financial_release_authorized'])
        self.assertEqual([e[-1] for e in self.events if isinstance(e,tuple)],
                         ['app1.service','app2.service','a.timer'])
        self.assertFalse(self.hold.exists())
        self.assertTrue((self.folder/'RESUME_COMPLETED.json').exists())
        self.assertLess(self.events.index('write:'+r.JOURNAL),self.events.index('unlink'))

    def test_second_request_never_starts_or_unlinks_again(self):
        self.execute();self.events=[]
        with self.assertRaisesRegex(m.MaintenanceError,'RESUME_ALREADY_COMMITTED'):
            self.execute()
        self.assertEqual(self.events,[])

    def test_wrong_source_has_no_side_effect(self):
        self.observed['plan']['source_commit']='b'*40
        with self.assertRaisesRegex(m.MaintenanceError,'RESUME_SOURCE_MISMATCH'):
            self.execute()
        self.assertTrue(self.hold.exists());self.assertEqual(self.events,[])

    def test_expiry_during_long_census_preserves_hold_and_has_no_commit(self):
        def verify(*a,**kw):
            m.clock=lambda:NOW+timedelta(hours=1)
            return self.observed
        with patch.object(r,'verify_state',side_effect=verify), \
             self.assertRaisesRegex(ValueError,'SOLO_RUNTIME_WINDOW_INVALID'):
            self.execute()
        self.assertTrue(self.hold.exists());self.assertEqual(self.events,[])

    def test_start_failure_reasserts_exact_hold_and_stops_only_scope(self):
        def command(args,**kwargs):
            self.command(args,**kwargs)
            if args[1]=='start' and args[-1]=='app2.service':
                raise m.MaintenanceError('synthetic start failure')
        with self.assertRaisesRegex(m.MaintenanceError,'PARTIAL_RESUME_FENCED'):
            self.execute(command)
        self.assertEqual(self.hold.read_bytes(),self.hold_bytes)
        self.assertTrue((self.folder/r.JOURNAL).exists())
        self.assertFalse((self.folder/'RESUME_COMPLETED.json').exists())
        stops=[e[-1] for e in self.events if isinstance(e,tuple) and e[1]=='stop']
        self.assertEqual(stops,['a.timer','a.service','app1.service','app2.service'])
        self.assertNotIn(('systemctl','start','--','a.service'),self.events)

    def test_partial_containment_attempts_every_stop_and_reports_uncertain(self):
        def command(args,**kw):
            self.command(args,**kw)
            if args[-1] in ('app1.service','a.timer'):
                raise m.MaintenanceError('synthetic failure')
        with self.assertRaisesRegex(m.MaintenanceError,'PARTIAL_RESUME_CONTAINMENT_UNCERTAIN'):
            self.execute(command)
        self.assertEqual(len([e for e in self.events if isinstance(e,tuple) and e[1]=='stop']),4)
        self.assertTrue(self.hold.exists())

    def test_enospc_reasserting_hold_never_skips_containment_stops(self):
        original=self.write
        def write(path,raw):
            if Path(path)==self.hold:raise OSError('synthetic ENOSPC')
            original(path,raw)
        def command(args,**kw):
            self.command(args,**kw)
            if args[1]=='start' and args[-1]=='app2.service':raise m.MaintenanceError('synthetic start failure')
        with patch.object(m,'write_new',side_effect=write), \
             self.assertRaisesRegex(m.MaintenanceError,'PARTIAL_RESUME_CONTAINMENT_UNCERTAIN'):
            self.execute(command)
        self.assertEqual(len([e for e in self.events if isinstance(e,tuple) and e[1]=='stop']),4)
        self.assertFalse((self.folder/'RESUME_COMPLETED.json').exists())

    def test_sigkill_after_commit_before_unlink_is_never_replayed(self):
        with patch.object(r,'unlink_owned_hold',side_effect=KeyboardInterrupt), \
             self.assertRaises(KeyboardInterrupt):
            self.execute()
        self.assertTrue(self.hold.exists())
        with self.assertRaisesRegex(m.MaintenanceError,'RESUME_ALREADY_COMMITTED'):
            self.execute()

    def test_sigkill_after_unlink_is_explicit_partial_return_without_fake_cleanup(self):
        def killed(*a,**kw):raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):self.execute(killed)
        self.assertFalse(self.hold.exists())
        self.assertTrue((self.folder/r.JOURNAL).exists())
        with self.assertRaisesRegex(m.MaintenanceError,'RESUME_ALREADY_COMMITTED'):
            self.execute()

    def test_journal_write_failure_never_removes_hold(self):
        with patch.object(m,'write_new',side_effect=OSError('disk full')),self.assertRaises(OSError):
            self.execute()
        self.assertTrue(self.hold.exists())
        self.assertFalse(any(isinstance(e,tuple) for e in self.events))

    def test_enrollment_revocation_between_census_and_commit_has_no_side_effect(self):
        calls=[]
        def guard():
            calls.append(1)
            if len(calls)==2:raise ValueError('SOLO_RUNTIME_ENROLLMENT_CHANGED')
        self.phase['_admission_guard']=guard
        with self.assertRaisesRegex(ValueError,'SOLO_RUNTIME_ENROLLMENT_CHANGED'):self.execute()
        self.assertTrue(self.hold.exists());self.assertFalse((self.folder/r.JOURNAL).exists())

    def test_bare_fresh_json_is_not_authenticated_admission(self):
        del self.phase['_admission_guard']
        with self.assertRaisesRegex(m.MaintenanceError,'RESUME_AUTHENTIC_ADMISSION_REQUIRED'):self.execute()
        self.assertEqual(self.events,[])

    @unittest.skipUnless(hasattr(os,'fork'),'POSIX-only process-kill test')
    def test_actual_sigkill_after_commit_before_unlink_preserves_hold_and_nonce_boundary(self):
        pid=os.fork()
        if pid==0:
            r.unlink_owned_hold=lambda expected:os.kill(os.getpid(),signal.SIGKILL)
            self.execute()
            os._exit(99)
        _,status=os.waitpid(pid,0)
        self.assertTrue(os.WIFSIGNALED(status));self.assertEqual(os.WTERMSIG(status),signal.SIGKILL)
        self.assertTrue(self.hold.exists());self.assertTrue((self.folder/r.JOURNAL).exists())
        with self.assertRaisesRegex(m.MaintenanceError,'RESUME_ALREADY_COMMITTED'):self.execute()

    @unittest.skipUnless(hasattr(os,'fork'),'POSIX-only process-kill test')
    def test_actual_sigkill_after_unlink_records_partial_return_without_automatic_replay(self):
        pid=os.fork()
        if pid==0:
            self.execute(lambda *a,**kw:os.kill(os.getpid(),signal.SIGKILL))
            os._exit(99)
        _,status=os.waitpid(pid,0)
        self.assertTrue(os.WIFSIGNALED(status));self.assertEqual(os.WTERMSIG(status),signal.SIGKILL)
        self.assertFalse(self.hold.exists());self.assertTrue((self.folder/r.JOURNAL).exists())
        with self.assertRaisesRegex(m.MaintenanceError,'RESUME_ALREADY_COMMITTED'):self.execute()


class ResumeEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.fence_path=Path('/root/fence')
        self.backup=Path('/root/backups/capture')
        self.restore=self.backup/'restore.json'
        self.spec={'path':'/root/resume-plan','sha256':'a'*64}
        self.plan={'schema':r.PLAN_SCHEMA,'source_commit':'a'*40,'fence_receipt_sha256':'b'*64,
                   'backup_manifest_sha256':'c'*64,'restore_receipt_sha256':'d'*64,
                   'timer_qualifications':{}}
        self.fence={'schema':r.FENCE_SCHEMA,'capture_seal':{'path':'/root/capture','sha256':'e'*64},
                    'prestate':dict.fromkeys(m.UNITS,{'ActiveState':'inactive'})}
        self.capture={'producer_identities':{'units':{u:{'originally_active':False} for u in m.UNITS}}}
        self.manifest={'financial_censuses':{'hd':{'actual':'hd'},'de':{'actual':'de'}},
                       'settlement_snapshot':'/root/snapshot'}
        self.permit={'databases':{'hd':{'lane':'hd'},'de':{'lane':'de'}},'max_total_bytes':1<<20}
        self.files={self.fence_path:(self.fence,'b'*64),self.backup/'backup.json':(self.manifest,'c'*64),
                    self.restore:({},'d'*64),Path('/root/resume-plan'):(self.plan,'a'*64)}
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.commands=[]
        for obj,name,value in ((m,'private_json',lambda p:self.files[Path(p)]),
           (m,'verify_retained_fence',lambda *a,**kw:{'permit':self.permit}),
           (m,'verify_current_backup',lambda *a,**kw:{'restore_receipt_sha256':'d'*64,'backup_manifest_sha256':'c'*64}),
           (r,'verify_capture',lambda *a,**kw:(self.capture,{'originally_active_apps':[], 'originally_active_timers':[]})),
           (m,'pg_environment',lambda c:c),
           (m,'financial_census',lambda c,e,runner:self.manifest['financial_censuses'][c['lane']]),
           (m,'settlement_states_unchanged',lambda *a:None), (m,'no_jobs',lambda runner:None)):
            self.stack.enter_context(patch.object(obj,name,value))

    def verify(self):return m.verify_resume_state(self.fence_path,self.backup,self.restore,self.spec,runner=lambda *a,**kw:None)

    def test_current_sealed_unchanged_pair_accepted_as_evidence_only(self):
        result=self.verify()
        self.assertFalse(result['resume_authorized']);self.assertFalse(result['financial_release_authorized'])

    def test_replaced_plan_fails_on_actual_parse_digest(self):
        self.files[Path('/root/resume-plan')]=(self.plan,'f'*64)
        with self.assertRaisesRegex(m.MaintenanceError,'SIGNED_RESUME_PLAN_CHANGED'):self.verify()

    def test_replaced_manifest_fails_on_actual_parse_digest(self):
        self.files[self.backup/'backup.json']=(self.manifest,'f'*64)
        with self.assertRaisesRegex(m.MaintenanceError,'SIGNED_MANIFEST_CHANGED_AT_USE'):self.verify()

    def test_partial_hd_de_restore_never_resumes(self):
        with patch.object(m,'verify_current_backup',side_effect=m.MaintenanceError('ISOLATED_BACKUP_AUTHORITY_UNVERIFIED')), \
             self.assertRaisesRegex(m.MaintenanceError,'ISOLATED_BACKUP_AUTHORITY_UNVERIFIED'):self.verify()

    def test_changed_census_in_either_lane_never_resumes(self):
        for lane in ('hd','de'):
            def census(c,e,runner):return {} if c['lane']==lane else self.manifest['financial_censuses'][c['lane']]
            with self.subTest(lane=lane),patch.object(m,'financial_census',side_effect=census), \
                 self.assertRaisesRegex(m.MaintenanceError,'FINANCIAL_DATABASE_CHANGED_BEFORE_RESUME'):self.verify()

    def test_prestate_cannot_be_rewritten_to_activate_previously_inactive_unit(self):
        self.fence['prestate'][m.APPS[0]]={'ActiveState':'active'}
        with self.assertRaisesRegex(m.MaintenanceError,'FENCE_PRESTATE_IDENTITY_MISMATCH'):self.verify()

    def test_old_receipt_and_unqualified_catchup_are_not_owner_signature_substitutes(self):
        with self.assertRaisesRegex(m.MaintenanceError,'PERSISTENT_TIMER_CATCHUP_NOT_QUALIFIED'):
            r.verify_timers(self.plan,self.capture,[m.TIMERS[0]])

    def test_exact_timer_and_both_real_reviewed_test_receipts_required(self):
        timer=m.TIMERS[0];service=m.ONESHOTS[0]
        capture={'producer_identities':{'units':{timer:{'configuration_sha256':'1'*64},
                                               service:{'configuration_sha256':'2'*64}}},
                 'producer_sources':{service:{'sha256':'3'*64}}}
        qualification={'schema':r.TIMER_SCHEMA,'timer':timer,'service':service,
            'timer_configuration_sha256':'1'*64,'service_configuration_sha256':'2'*64,
            'producer_source_manifest_sha256':'3'*64,
            'idempotence_test':{'path':'/root/idempotence','sha256':'4'*64},
            'uncertainty_test':{'path':'/root/uncertainty','sha256':'5'*64}}
        receipts={Path('/root/qualification'):(qualification,'6'*64)}
        for key,digest in (('idempotence_test','4'),('uncertainty_test','5')):
            receipts[Path(qualification[key]['path'])]=({'source_manifest_sha256':'3'*64,
                'test_contract':key,'result':'PASS','ci_run_url':'https://github.com/Emaren/app-prodn/actions/runs/1'},digest*64)
        plan={'timer_qualifications':{timer:{'path':'/root/qualification','sha256':'6'*64}}}
        with patch.object(m,'private_json',side_effect=lambda p:receipts[Path(p)]):
            r.verify_timers(plan,capture,[timer])
            receipts[Path('/root/uncertainty')][0]['result']='UNKNOWN'
            with self.assertRaisesRegex(m.MaintenanceError,'TIMER_TEST_EVIDENCE_UNAVAILABLE'):
                r.verify_timers(plan,capture,[timer])
            qualification['service']='outside.service'
            with self.assertRaisesRegex(m.MaintenanceError,'PERSISTENT_TIMER_CATCHUP_NOT_QUALIFIED'):
                r.verify_timers(plan,capture,[timer])

    def test_runtime_old_enrollment_cannot_omit_new_resume_source(self):
        self.assertIn('settlement_solo_resume.py',runtime.SOURCES)
        self.assertIn('settlement_resume_producer_identities.py',runtime.SOURCES)

    def test_build_manifest_cannot_use_interpreter_hash_as_application_identity(self):
        unit=m.APPS[0]
        manifest={'schema':r.SOURCE_SCHEMA,'unit':unit,'source_commit':'a'*40,'uid':1000,
                  'files':[{'path':'/bin/node','sha256':'e'*64,'kind':'executable'},
                           {'path':'/opt/BUILD_ID','sha256':'e'*64,'kind':'build_metadata'}]}
        with patch.object(m,'APPS',(unit,)),patch.object(m,'ONESHOTS',()), \
             patch.object(r,'read_sealed',return_value=manifest),patch.object(r,'source_file_sha',return_value=('e'*64,1)), \
             self.assertRaisesRegex(m.MaintenanceError,'PRODUCER_BUILD_AND_ENTRYPOINT_REQUIRED'):
            r.verify_sources({unit:{}},lambda *a:None)

    def test_mutable_runtime_owned_source_is_refused_before_read(self):
        with self.assertRaisesRegex(m.MaintenanceError,'RESUME_PRODUCER_SOURCE_MUST_BE_ROOT_CONTROLLED'):
            r.source_file_sha('/root/never-read',1000)

    def test_auxiliary_interpreter_cannot_hide_relative_entrypoint_behind_later_argument(self):
        unit=m.APPS[0]
        paths={'/bin/bash':'executable','/usr/bin/node':'executable',
               '/app/main.js':'entrypoint','/app/BUILD_ID':'build_metadata'}
        manifest={'schema':r.SOURCE_SCHEMA,'unit':unit,'source_commit':'a'*40,'uid':0,
                  'files':[{'path':p,'kind':k,'sha256':'e'*64} for p,k in paths.items()]}
        native={'ExecStart':[['/usr/bin/node',['/usr/bin/node','/app/main.js'],False]],
                'ExecStartPre':[['/bin/bash',['/bin/bash','unhashed.sh','/app/main.js'],False]]}
        with patch.object(m,'APPS',(unit,)),patch.object(m,'ONESHOTS',()), \
             patch.object(r,'read_sealed',return_value=manifest),patch.object(r,'source_file_sha',return_value=('e'*64,1)), \
             patch.object(r.identities,'read_properties',return_value={}), \
             patch.object(r.identities,'native_execution_configuration',return_value=native), \
             self.assertRaisesRegex(m.MaintenanceError,'PRODUCER_INTERPRETER_INPUT_NOT_SEALED'):
            r.verify_sources({unit:{}},lambda *a:None)


if __name__=='__main__':
    unittest.main()
