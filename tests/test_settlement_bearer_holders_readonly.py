"""Offline exact-bearer observation: metadata never certifies a producer fence."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('bearer_observer', ROOT/'scripts/settlement-bearer-holders-readonly.py')
inv = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inv)
FIRST = b'private-fixture-primary-bearer'
SECOND = b'private-fixture-founder-bearer'


class ExactBearerObservation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.addCleanup(patch.stopall)
        patch.object(inv, 'PROC', self.root).start()
        self.state = {'primary': (1,b'100',FIRST), 'founder': (2,b'200',SECOND)}
        patch.object(inv, 'targets', return_value=self.state).start()

    def proc(self, pid=1, values=None, unit='aoe2hdbets-web.service'):
        d = self.root/str(pid);d.mkdir(exist_ok=True)
        (d/'environ').write_bytes(values or b'')
        (d/'stat').write_bytes(str(pid).encode()+b' (comm with spaces) S '+b'0 '*18+b'100 0')
        (d/'cgroup').write_text('0::/system.slice/'+unit+'\n')
        return d

    def test_exact_value_in_any_key_identifies_both_lanes_without_secret_or_digest(self):
        self.proc(values=b'ALIAS='+FIRST+b'\0OTHER='+SECOND+b'\0')
        report=inv.inspect();row=report['holders'][0]
        self.assertEqual(row['exact_value_matches'], {'OTHER_ENVIRONMENT_KEY_WITHHELD':['founder','primary']})
        raw=json.dumps(report)
        for secret in (FIRST,SECOND):
            self.assertNotIn(secret.decode(),raw)
            self.assertNotIn(inv.hashlib.sha256(secret).hexdigest(),raw)
        self.assertFalse(report['financial_producers_fenced'])
        self.assertFalse(report['complete_producer_inventory'])
        self.assertFalse(report['release_authorized'])
        self.assertFalse(report['production_mutated'])

    def test_duplicate_keys_union_authority_and_labels_cannot_disclose_credentials(self):
        self.proc(values=b'ALIAS='+FIRST+b'\0ALIAS='+SECOND+b'\0')
        report=inv.inspect()
        self.assertEqual(report['holders'][0]['exact_value_matches']['OTHER_ENVIRONMENT_KEY_WITHHELD'],['founder','primary'])
        self.proc(values=FIRST+b'='+FIRST,unit='aoe2war-'+FIRST.decode()+'.service')
        raw=json.dumps(inv.inspect())
        self.assertNotIn(FIRST.decode(),raw)
        self.assertNotIn(inv.hashlib.sha256(FIRST).hexdigest(),raw)
        self.assertIn('WITHHELD_CREDENTIAL_BEARING_LABEL',raw)

    def test_presence_of_named_key_or_token_substring_is_not_exact_authority(self):
        self.proc(values=b'WOLO_SETTLEMENT_AUTH_TOKEN=unrelated\0URL=prefix'+FIRST+b'\0')
        self.assertEqual(inv.inspect()['holders'],[])

    def test_same_bearer_reports_both_lanes_without_invented_separation(self):
        self.state['founder']=(2,b'200',FIRST)
        self.proc(values=b'TOKEN='+FIRST+b'\0')
        report=inv.inspect()
        self.assertFalse(report['bearer_lanes_distinct'])
        self.assertEqual(report['holders'][0]['exact_value_matches']['OTHER_ENVIRONMENT_KEY_WITHHELD'],['founder','primary'])

    def test_unapproved_cgroup_name_is_fingerprinted(self):
        self.proc(values=b'TOKEN='+FIRST,unit='private-other.service')
        row=inv.inspect()['holders'][0]
        self.assertNotIn('private-other',json.dumps(row))
        self.assertIn('name_sha256',row['units'][0])

    def test_generation_change_and_unreadable_process_are_explicit_gaps(self):
        self.proc(values=b'TOKEN='+FIRST)
        with patch.object(inv,'generation',side_effect=[b'100',b'101']):
            report=inv.inspect()
        self.assertFalse(report['all_listed_processes_observed'])
        self.assertEqual(report['holders'],[])
        self.assertEqual(report['processes_unavailable_or_changed'],1)

    def test_rotation_or_target_restart_cannot_return_stable_observation(self):
        self.proc()
        changed={'primary':(3,b'300',FIRST),'founder':self.state['founder']}
        with patch.object(inv,'targets',side_effect=[self.state,changed]):
            with self.assertRaises(ValueError):inv.inspect()

    def test_deadline_expiring_during_final_target_io_cannot_pass(self):
        with patch.object(inv.time,'monotonic',side_effect=[0,1,31]):
            with self.assertRaises(ValueError):inv.inspect()

    def test_process_and_total_byte_limits_refuse(self):
        self.proc(1);self.proc(2)
        with patch.object(inv,'MAX_PIDS',1):
            with self.assertRaises(ValueError):inv.inspect()
        (self.root/'1/environ').write_bytes(b'X=123456')
        with patch.object(inv,'MAX_TOTAL',8):
            with self.assertRaises(ValueError):inv.inspect()

    def test_failed_oversized_reads_also_consume_global_budget(self):
        self.proc(1,values=b'A'*20);self.proc(2,values=b'B'*20)
        with patch.object(inv,'MAX_ENV',4),patch.object(inv,'MAX_TOTAL',8):
            with self.assertRaises(inv.BudgetExceeded):inv.inspect()

    def test_oversized_file_and_symlink_cannot_be_read_as_evidence(self):
        d=self.proc(values=b'A'*20)
        with self.assertRaises(ValueError):inv.read_proc(1,'environ',4)
        (d/'environ').unlink();(d/'environ').symlink_to(d/'stat')
        with self.assertRaises(OSError):inv.read_proc(1,'environ',1000)

    def test_invalid_or_traversal_process_reference_refuses(self):
        for pid in ('../1',0,-1):
            with self.assertRaises(ValueError):inv.read_proc(pid,'environ',100)
        with self.assertRaises(ValueError):inv.read_proc(1,'../../secret',100)

    def test_stable_target_requires_exactly_one_nonempty_bearer_and_generation(self):
        d=self.proc(values=b'WOLO_SETTLEMENT_AUTH_TOKEN='+FIRST)
        patch.stopall()
        with patch.object(inv,'PROC',self.root),patch.object(inv,'target_pid',return_value=1):
            result=inv.targets(inv.time.monotonic()+10)
            self.assertEqual(result['primary'][2],FIRST)
            (d/'environ').write_bytes(b'WOLO_SETTLEMENT_AUTH_TOKEN='+FIRST+b'\0WOLO_SETTLEMENT_AUTH_TOKEN='+SECOND)
            with self.assertRaises(ValueError):inv.targets(inv.time.monotonic()+10)

    def test_cli_error_is_sanitized_and_mutating_args_never_run(self):
        with patch.object(inv.sys,'argv',['tool','--stop']),patch.object(inv.os,'geteuid',return_value=0),patch.object(inv,'inspect')as run,contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(inv.main(),2);run.assert_not_called()
        with patch.object(inv.sys,'argv',['tool']),patch.object(inv.os,'geteuid',return_value=0),patch.object(inv,'inspect',side_effect=ValueError(FIRST.decode())),contextlib.redirect_stderr(io.StringIO())as err:
            self.assertEqual(inv.main(),2)
        self.assertNotIn(FIRST.decode(),err.getvalue())


if __name__=='__main__':unittest.main()
