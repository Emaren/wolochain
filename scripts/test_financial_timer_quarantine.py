"""Isolated filesystem/systemd model and real synthetic P256 signature negatives.
No real systemctl, owner key, network, SQL or financial process is used.
"""
import base64,copy,datetime,hashlib,importlib.util,json,os,subprocess,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace

P=Path(__file__).with_name('financial_timer_quarantine.py')
spec=importlib.util.spec_from_file_location('timer_controller',P);q=importlib.util.module_from_spec(spec);spec.loader.exec_module(q)

class Model(q.Host):
 def __init__(self,root):
  super().__init__(root,os.getuid());self.calls=[];self.fail_once=None;self.hooks={};self.receipt_fail=False
  self.states={u:('active' if u in q.TIMERS else 'inactive') for u in q.UNITS}
 def systemctl(self,*args,allow_failure=False):
  self.calls.append(args)
  if self.fail_once==args[0]:self.fail_once=None;raise q.Hold('INJECTED_'+args[0])
  if args[0]=='show' and args[1]=='--property=UnitPath':return SimpleNamespace(returncode=0,stdout=q.CONTROL+' /etc/systemd/system',stderr='')
  if args[0] in ['stop','start']:
   assert set(args[1:])<=set(q.UNITS)
   for u in args[1:]:
    if args[0]=='start' and self.path(q.CONTROL+'/'+u).is_symlink():return SimpleNamespace(returncode=1,stdout='',stderr='Unit is masked')
    self.states[u]='inactive' if args[0]=='stop' else 'active'
  else:assert args[0] in ['daemon-reload','show']
  return SimpleNamespace(returncode=0,stdout='',stderr='')
 def show(self,u,*props):
  assert u in q.UNITS
  mask=self.path(q.CONTROL+'/'+u).is_symlink()
  drop='/etc/systemd/system/'+u+'.d/secret.conf'
  d={'FragmentPath':'/etc/systemd/system/'+u,'DropInPaths':drop if self.path(drop).exists() else '','UnitFileState':'masked' if mask else ('enabled' if self.links(u) else ('disabled' if u in q.TIMERS else 'static')),'ActiveState':self.states[u],'SubState':'waiting' if self.states[u]=='active' else 'dead','MainPID':'0','ControlPID':'0','RefuseManualStop':'no','LoadState':'masked' if mask else 'loaded','NextElapseUSecRealtime':'0','NextElapseUSecMonotonic':'0','SuccessAction':'none','FailureAction':'none'}
  d.update(self.hooks);return {p:d.get(p,'') for p in props}
 def protected(self):return {'aoe2hdbets-web.service':{'ActiveState':'active','MainPID':'101','StopWhenUnneeded':'no'},'wolochaind-mainnet.service':{'ActiveState':'active','MainPID':'103'},'listeners':{'3030':['101'],'3032':['102']}}
 def write(self,s,b):
  if self.receipt_fail and s.endswith('/RESTORED.json'):self.receipt_fail=False;raise OSError('injected inverse receipt failure')
  return super().write(s,b)

class TimerTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  for d in ['etc/systemd/system/timers.target.wants','etc/systemd/system.control','var/lib/wolo-financial-timer-quarantine']:(self.root/d).mkdir(parents=True,exist_ok=True)
  (self.root/'var/lib/wolo-financial-timer-quarantine').chmod(0o700)
  (self.root/'etc/machine-id').write_text('fixture-machine-id')
  for u in q.UNITS:
   (self.root/'etc/systemd/system'/u).write_text('[Unit]\nDescription=Synthetic fixture only\n')
   if u in q.TIMERS:(self.root/'etc/systemd/system/timers.target.wants'/u).symlink_to('/etc/systemd/system/'+u)
  drop=self.root/'etc/systemd/system/aoe2hdbets-bet-stake-reconcile.service.d';drop.mkdir();(drop/'secret.conf').write_text('EnvironmentFile=/root/synthetic-test-only.env\n')
  self.h=Model(self.root);self.m=q.observe(self.h);self.raw=q.canonical(self.m);self.src=hashlib.sha256(P.read_bytes()).hexdigest()
  self.fields=q.request('QUARANTINE',self.m,self.raw,self.src)
  self.journal=q.STATE+'/fixture';self.h.mkdir(self.journal,0o700)
  self.original={p: self.h.read(p) for info in self.m['units'].values() for p in [f['path'] for f in info['files']]}
 def pause(self):q.quarantine(self.h,self.m,self.journal,self.fields,{'mutation_started':False})
 def admission(self):
  x={'schema':'wolo.financial-timer-resume-admission.v1','host':'HEL1','machine_id_sha256':self.m['machine_id_sha256'],'original_manifest_sha256':q.digest(self.raw),'independent_financial_resume_authorized':True,'legacy_http_writer_boundary_physically_accepted':True,'expires_at':q.timestamp(q.utc()+datetime.timedelta(seconds=60))}
  raw=q.canonical(x);f=q.request('RESTORE',self.m,self.raw,self.src,q.digest(raw));return raw,f
 def test_four_masks_denied_manual_starts_and_original_bytes_unchanged(self):
  self.pause();q.masked(self.h);q.validate_manifest(self.m,self.h)
  self.assertEqual(sum(c[0]=='start' for c in self.h.calls),4)
  self.assertEqual(self.original,{p:self.h.read(p) for p in self.original})
  self.assertTrue((self.h.path(self.journal+'/QUARANTINED.json')).exists())
 def test_partial_quarantine_failure_recovers_only_toward_denial(self):
  self.h.fail_once='stop';phase={'mutation_started':False}
  with self.assertRaises(q.Hold):
   try:q.quarantine(self.h,self.m,self.journal,self.fields,phase)
   except Exception:
    if phase['mutation_started']:q.safe_quarantine(self.h,self.m)
    raise
  q.masked(self.h);self.assertFalse(any(c[0]=='start' for c in self.h.calls))
 def test_fresh_recovery_finishes_partial_denial_without_resuming(self):
  self.h.mask(q.UNITS[0]);item=self.m['units'][q.TIMERS[0]]['enabled_links'][0];self.h.unlink_link(item)
  fields=q.request('RECOVER',self.m,self.raw,self.src);q.quarantine(self.h,self.m,self.journal,fields,{'mutation_started':False})
  q.masked(self.h);q.validate_manifest(self.m,self.h)
 def test_expired_first_mutation_does_not_trigger_recovery_mutation(self):
  self.fields[9]=q.timestamp(q.utc()-datetime.timedelta(seconds=1));phase={'mutation_started':False}
  with self.assertRaisesRegex(q.Hold,'EXPIRED'):
   try:q.quarantine(self.h,self.m,self.journal,self.fields,phase)
   except Exception:
    if phase['mutation_started']:q.safe_quarantine(self.h,self.m)
    raise
  self.assertFalse(phase['mutation_started']);self.assertFalse(list(self.h.path(q.CONTROL).iterdir()))
  self.assertTrue(all(self.h.links(u) for u in q.TIMERS))
 def test_inverse_requires_separate_independent_financial_admission(self):
  self.pause();raw,fields=self.admission();bad=json.loads(raw);bad['legacy_http_writer_boundary_physically_accepted']=False;badraw=q.canonical(bad);fields[10]=q.digest(badraw)
  with self.assertRaisesRegex(q.Hold,'NOT_ADMITTED'):q.restore(self.h,self.m,self.journal,badraw,fields,{'mutation_started':False})
  q.masked(self.h)
 def test_inverse_restores_logical_preimage_without_rewriting_fragments(self):
  self.pause();raw,fields=self.admission();q.restore(self.h,self.m,self.journal,raw,fields,{'mutation_started':False})
  self.assertEqual(q.observe(self.h),self.m);self.assertEqual(self.original,{p:self.h.read(p) for p in self.original})
  self.assertTrue(all(c[1] in q.TIMERS for c in self.h.calls if c[0]=='start' and c[1] in q.TIMERS))
 def test_inverse_late_failure_requarantines_without_auto_resume(self):
  self.pause();raw,fields=self.admission();self.h.receipt_fail=True;phase={'mutation_started':False}
  with self.assertRaises(OSError):
   try:q.restore(self.h,self.m,self.journal,raw,fields,phase)
   except Exception:
    if phase['mutation_started']:q.safe_quarantine(self.h,self.m)
    raise
  q.masked(self.h);self.assertEqual(self.original,{p:self.h.read(p) for p in self.original})
 def test_source_drift_and_parent_symlink_are_denied(self):
  (self.root/'etc/systemd/system'/q.UNITS[0]).write_text('DRIFT')
  with self.assertRaisesRegex(q.Hold,'DRIFT'):q.validate_manifest(self.m,self.h)
  parent=self.root/'etc/systemd/system/timers.target.wants';moved=self.root/'etc/moved';parent.rename(moved);parent.symlink_to(moved)
  with self.assertRaisesRegex(q.Hold,'SYMLINK'):self.h.links(q.TIMERS[0])
  with self.assertRaisesRegex(q.Hold,'SYMLINK'):self.h.unlink_link(self.m['units'][q.TIMERS[0]]['enabled_links'][0])
 def test_stop_hooks_and_host_power_actions_are_denied(self):
  self.h.hooks={'OnSuccess':'unrelated.service'}
  with self.assertRaisesRegex(q.Hold,'SIDE_EFFECTS'):q.observe(self.h)
  self.h.hooks={'SuccessAction':'reboot'}
  with self.assertRaisesRegex(q.Hold,'POWER_ACTION'):q.observe(self.h)
 def test_nonce_is_durable_and_never_reused(self):
  p=q.consume_nonce(self.h,self.fields,{'fixture':True});self.assertTrue(self.h.path(p+'/permit.json').exists())
  with self.assertRaisesRegex(q.Hold,'NONCE_ALREADY_USED'):q.consume_nonce(self.h,self.fields,{'fixture':True})
 def test_website_auto_stop_and_public_journal_directory_are_denied(self):
  protected=self.h.protected();protected['aoe2hdbets-web.service']['StopWhenUnneeded']='yes';self.h.protected=lambda:protected
  with self.assertRaisesRegex(q.Hold,'AUTO_STOP'):q.observe(self.h)
  self.h.path(q.STATE).chmod(0o755)
  with self.assertRaisesRegex(q.Hold,'PRIVATE_DIRECTORY'):self.h.mkdir(q.STATE,0o700)
 def test_real_synthetic_p256_signature_and_scope_negatives(self):
  # Independent fixture key, never the enrolled owner key or a real authority.
  key=self.root/'test-key.pem';pub=self.root/'test-public.der';message=self.root/'test-message';sig=self.root/'test-signature'
  def openssl(*args):subprocess.run(['/usr/bin/openssl',*args],check=True,capture_output=True)
  openssl('ecparam','-name','prime256v1','-genkey','-noout','-out',str(key));openssl('pkey','-in',str(key),'-pubout','-outform','DER','-out',str(pub))
  rawpub=pub.read_bytes()[-65:];message.write_bytes(q.DOMAIN+q.canonical(self.fields));openssl('dgst','-sha256','-sign',str(key),'-out',str(sig),str(message))
  packet={'schema':q.SCHEMA,'request':self.fields,'signature_der_b64':base64.b64encode(sig.read_bytes()).decode()}
  self.assertEqual(q.verify_packet(packet,rawpub,self.m,self.raw,self.src,q.utc(),q.digest(rawpub)),self.fields)
  with self.assertRaisesRegex(q.Hold,'OWNER_PUBLIC_IDENTITY'):q.verify_packet(packet,rawpub,self.m,self.raw,self.src,q.utc())
  for field,value in [(0,'RESTORE'),(3,'0'*64),(4,'0'*64),(11,1)]:
   bad=copy.deepcopy(packet);bad['request'][field]=value
   with self.assertRaises(q.Hold):q.verify_packet(bad,rawpub,self.m,self.raw,self.src,q.utc(),q.digest(rawpub))
  bad=copy.deepcopy(packet);bad['request'][7]='a'*64
  with self.assertRaisesRegex(q.Hold,'SIGNATURE_INVALID'):q.verify_packet(bad,rawpub,self.m,self.raw,self.src,q.utc(),q.digest(rawpub))
  with self.assertRaisesRegex(q.Hold,'EXPIRED'):q.verify_packet(packet,rawpub,self.m,self.raw,self.src,q.utc()+datetime.timedelta(minutes=6),q.digest(rawpub))

if __name__=='__main__':unittest.main()
