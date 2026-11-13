#!/usr/bin/python3 -I
"""Exact four-unit financial timer quarantine. Root staging + fresh owner permit.
No SQL, HTTP, wallet, validator or website mutation. Never auto-resume on error.
The inverse requires a DIFFERENT signed scope and independent root admission.
Invoke with /usr/bin/python3 -I from an immutable root-owned staging directory.
"""
from __future__ import annotations
import argparse,base64,datetime,fcntl,hashlib,json,os,re,stat,subprocess,sys,tempfile
from pathlib import Path

UNITS=tuple(sorted(['aoe2hdbets-bet-stake-reconcile.timer','aoe2hdbets-bet-stake-reconcile.service','aoe2hdbets-staking-rewards.timer','aoe2hdbets-staking-rewards.service']))
TIMERS=tuple(x for x in UNITS if x.endswith('.timer'))
CONTROL='/etc/systemd/system.control'
STATE='/var/lib/wolo-financial-timer-quarantine'
OWNER_SHA='f9f76deb8ba61b8f4b4f8e5b434acc11fa95630ccb19306a71e8bff0dc6fb826'
POLICY_SHA='50910864e6d24236ac3ea98cda1456bedee8d9bf2f9365a8441c6d1e29b41806'
GOV_SHA='edcdf664259b0eeec0ae2ed71919bbe5745183864abc2c3b221aa50e83570d19'
DOMAIN=b'AOE2WAR-FINANCIAL-TIMER-MAINTENANCE-V1\0'
SCHEMA='wolo.financial-timer-maintenance-permit.v1'
ZERO='0'*64
ENV={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LC_ALL':'C'}

class Hold(ValueError):pass

def need(condition,reason):
 if not condition:raise Hold(reason)

def digest(b):return hashlib.sha256(b).hexdigest()
def canonical(x):return json.dumps(x,separators=(',',':'),ensure_ascii=True).encode()
def utc():return datetime.datetime.now(datetime.timezone.utc)
def timestamp(t):return t.strftime('%Y-%m-%dT%H:%M:%SZ')
def date(s):
 t=datetime.datetime.strptime(s,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=datetime.timezone.utc)
 need(timestamp(t)==s,'NONCANONICAL_TIME');return t

def unique(pairs):
 d={}
 for k,v in pairs:need(k not in d,'DUPLICATE_JSON_KEY');d[k]=v
 return d

def decode(b):return json.loads(b,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(Hold('NONFINITE_JSON')))

class Host:
 def __init__(self,root=Path('/'),owner=0):self.root=root;self.owner=owner
 def path(self,s):
  need(s.startswith('/') and '..' not in Path(s).parts,'UNSAFE_PATH');return self.root/s.lstrip('/')
 def safe(self,s,regular=True):
  p=self.path(s)
  for q in [*reversed(p.parents),p]:
   if q==self.root.parent:continue
   if not q.is_relative_to(self.root):continue
   st=q.lstat();need(not stat.S_ISLNK(st.st_mode),'SYMLINK_SOURCE');need(st.st_uid==self.owner and not(st.st_mode&0o022),'UNTRUSTED_SOURCE_METADATA')
  st=p.lstat()
  if regular:need(stat.S_ISREG(st.st_mode) and st.st_nlink==1 and st.st_size<=2*1024*1024,'SOURCE_NOT_REGULAR')
  return st
 def read(self,s):
  self.safe(s);p=self.path(s);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
  with os.fdopen(fd,'rb') as f:
   a=os.fstat(f.fileno());b=f.read(2*1024*1024+1);z=os.fstat(f.fileno())
  need((a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)==(z.st_dev,z.st_ino,z.st_size,z.st_mtime_ns,z.st_ctime_ns) and len(b)==a.st_size,'SOURCE_CHANGED_DURING_READ');return b
 def mkdir(self,s,mode):
  p=self.path(s)
  if not p.exists():p.mkdir(mode=mode)
  self.safe(s,False);need(p.is_dir(),'DIRECTORY_REQUIRED')
  if mode==0o700:need(stat.S_IMODE(p.stat().st_mode)==0o700,'PRIVATE_DIRECTORY_REQUIRED')
 def syncdir(self,s):
  fd=os.open(self.path(s),os.O_RDONLY);os.fsync(fd);os.close(fd)
 def write(self,s,b):
  self.safe(str(Path(s).parent),False);fd=os.open(self.path(s),os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
  with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())
  self.syncdir(str(Path(s).parent))
 def systemctl(self,*args,allow_failure=False):
  r=subprocess.run(['/usr/bin/systemctl',*args],capture_output=True,text=True,env=ENV,timeout=30)
  if not allow_failure:need(r.returncode==0,'SYSTEMCTL_FAILED_'+args[0])
  return r
 def show(self,u,*props):
  r=self.systemctl('show',u,'--no-pager',*[f'--property={x}' for x in props]);return dict(x.split('=',1) for x in r.stdout.splitlines() if '=' in x)
 def protected(self):
  out={u:self.show(u,'ActiveState','MainPID','ExecMainStartTimestamp','StopWhenUnneeded') for u in ['aoe2hdbets-web.service','wolochaind-mainnet.service']}
  r=subprocess.run(['/usr/bin/ss','-H','-ltnp','sport = :3030 or sport = :3032'],capture_output=True,text=True,env=ENV,check=True,timeout=8)
  out['listeners']={str(p):sorted(set(re.findall(r'pid=(\d+)', '\n'.join(x for x in r.stdout.splitlines() if f':{p} ' in x)))) for p in [3030,3032]}
  return out
 def metadata(self,s):
  st=self.safe(s);b=self.read(s);return {'path':s,'sha256':digest(b),'bytes':len(b),'uid':st.st_uid,'gid':st.st_gid,'mode':stat.S_IMODE(st.st_mode),'mtime_ns':st.st_mtime_ns}
 def machine(self):return digest(self.read('/etc/machine-id'))
 def links(self,u):
  found=[]
  for p in sorted(self.path('/etc/systemd/system').glob('*.*/'+u)):
   if not(p.parent.name.endswith('.wants') or p.parent.name.endswith('.requires')):continue
   self.safe('/'+str(p.parent.relative_to(self.root)),False)
   need(p.is_symlink(),'ENABLE_LINK_NOT_SYMLINK');st=p.lstat();need(st.st_uid==self.owner,'ENABLE_LINK_OWNER')
   found.append({'path':'/'+str(p.relative_to(self.root)),'target':os.readlink(p)})
  return found
 def mask(self,u):
  need(u in UNITS,'UNIT_NOT_ALLOWED');self.safe(CONTROL,False);p=self.path(CONTROL+'/'+u)
  if os.path.lexists(p):need(p.is_symlink() and os.readlink(p)=='/dev/null' and p.lstat().st_uid==self.owner,'UNEXPECTED_MASK')
  else:os.symlink('/dev/null',p);self.syncdir(CONTROL)
 def unlink_link(self,item):
  self.safe(str(Path(item['path']).parent),False)
  p=self.path(item['path']);need(p.is_symlink() and p.lstat().st_uid==self.owner and os.readlink(p)==item['target'],'ENABLE_LINK_DRIFT');p.unlink();self.syncdir(str(Path(item['path']).parent))

def observe(h):
 paths=h.systemctl('show','--property=UnitPath','--value').stdout.split()
 need(paths and paths[0]==CONTROL,'MASK_PRECEDENCE_UNSUPPORTED')
 m={'schema':'wolo.financial-timer-original-preimage.v1','host':'HEL1','machine_id_sha256':h.machine(),'units':{},'protected':h.protected()}
 for u in UNITS:
  info=h.show(u,'FragmentPath','DropInPaths','UnitFileState','ActiveState','SubState','MainPID','ControlPID','RefuseManualStop','PropagatesStopTo','ConsistsOf','BoundBy','ExecStop','ExecStopPost','OnSuccess','OnFailure','SuccessAction','FailureAction')
  need(info['FragmentPath']=='/etc/systemd/system/'+u,'UNEXPECTED_FRAGMENT_PATH')
  need(not any(info.get(x) for x in ['PropagatesStopTo','ConsistsOf','BoundBy','ExecStop','ExecStopPost','OnSuccess','OnFailure']),'STOP_HAS_UNREVIEWED_SIDE_EFFECTS')
  need(info.get('SuccessAction')=='none' and info.get('FailureAction')=='none','UNIT_HAS_HOST_POWER_ACTION')
  need(info.get('RefuseManualStop')=='no','STOP_REFUSED')
  need(not os.path.lexists(h.path(CONTROL+'/'+u)),'PREEXISTING_CONTROL_MASK')
  if u.endswith('.service'):need(info['ActiveState']=='inactive' and info['MainPID']=='0' and info['ControlPID']=='0','SERVICE_MUST_BE_IDLE_BEFORE_APPROVAL')
  files=[h.metadata(p) for p in [info['FragmentPath'],*info.get('DropInPaths','').split()]]
  m['units'][u]={'state':{x:info.get(x,'') for x in ['UnitFileState','ActiveState','SubState']},'files':files,'enabled_links':h.links(u)}
 need(all(m['protected'][u]['ActiveState']=='active' and int(m['protected'][u]['MainPID'])>0 for u in ['aoe2hdbets-web.service','wolochaind-mainnet.service']),'PROTECTED_SERVICE_NOT_ACTIVE')
 need(m['protected']['aoe2hdbets-web.service'].get('StopWhenUnneeded')=='no','WEBSITE_DEPENDENCY_AUTO_STOP_NOT_ACCEPTED')
 need(all(m['protected']['listeners'].values()),'PROTECTED_LISTENER_ABSENT')
 return m

def validate_manifest(m,h):
 need(set(m)=={'schema','host','machine_id_sha256','units','protected'} and m['schema']=='wolo.financial-timer-original-preimage.v1' and m['host']=='HEL1' and m['machine_id_sha256']==h.machine(),'MANIFEST_TARGET')
 need(set(m['units'])==set(UNITS),'MANIFEST_UNIT_SCOPE')
 for u,info in m['units'].items():
  need(info['files'][0]['path']=='/etc/systemd/system/'+u,'MANIFEST_FRAGMENT_SCOPE')
  for f in info['files']:
   need(f['path']=='/etc/systemd/system/'+u or (f['path'].startswith('/etc/systemd/system/'+u+'.d/') and Path(f['path']).name.endswith('.conf')),'MANIFEST_FILE_SCOPE')
   need(h.metadata(f['path'])==f,'ORIGINAL_UNIT_OR_DROPIN_DRIFT')
  for item in info['enabled_links']:
   p=Path(item['path']);need(p.name==u and p.parent.parent==Path('/etc/systemd/system') and (p.parent.name.endswith('.wants') or p.parent.name.endswith('.requires')),'ENABLE_LINK_SCOPE')
   need(item['target']=='/etc/systemd/system/'+u,'ENABLE_LINK_TARGET')

def request(action,m,manifest_raw,source_sha,inverse_admission=ZERO):
 need(action in ['QUARANTINE','RECOVER','RESTORE'],'ACTION_SCOPE')
 now=utc().replace(microsecond=0)
 return [action,'HEL1',m['machine_id_sha256'],source_sha,digest(manifest_raw),POLICY_SHA,GOV_SHA,os.urandom(32).hex(),timestamp(now),timestamp(now+datetime.timedelta(seconds=300)),inverse_admission,0]

def verify_packet(packet,pub,m,manifest_raw,source_sha,now,expected_owner=OWNER_SHA):
 need(set(packet)=={'schema','request','signature_der_b64'} and packet['schema']==SCHEMA,'PERMIT_SCHEMA')
 a=packet['request'];need(isinstance(a,list) and len(a)==12 and all(isinstance(x,str) for x in a[:11]) and type(a[11]) is int and a[11]==0,'PERMIT_FIELDS')
 need(a[0] in ['QUARANTINE','RECOVER','RESTORE'] and a[1]=='HEL1' and a[2]==m['machine_id_sha256'] and a[3]==source_sha and a[4]==digest(manifest_raw) and a[5]==POLICY_SHA and a[6]==GOV_SHA,'PERMIT_SCOPE_OR_SOURCE')
 need(all(re.fullmatch('[0-9a-f]{64}',a[i]) for i in [2,3,4,5,6,7,10]) and a[7]!=ZERO,'PERMIT_DIGEST_OR_NONCE')
 start,end=date(a[8]),date(a[9]);need(start<=now<end and 0<(end-start).total_seconds()<=300,'PERMIT_EXPIRED_OR_WINDOW')
 need((a[0] in ['QUARANTINE','RECOVER'] and a[10]==ZERO) or (a[0]=='RESTORE' and a[10]!=ZERO),'INVERSE_ADMISSION_REQUIRED')
 need(len(pub)==65 and pub[0]==4 and digest(pub)==expected_owner,'OWNER_PUBLIC_IDENTITY')
 sig=base64.b64decode(packet['signature_der_b64'],validate=True);need(base64.b64encode(sig).decode()==packet['signature_der_b64'] and 64<=len(sig)<=80,'SIGNATURE_ENCODING')
 with tempfile.TemporaryDirectory(prefix='timer-permit-') as td:
  p=Path(td);(p/'pub.der').write_bytes(bytes.fromhex('3059301306072a8648ce3d020106082a8648ce3d030107034200')+pub);(p/'signature').write_bytes(sig);(p/'message').write_bytes(DOMAIN+canonical(a))
  r=subprocess.run(['/usr/bin/openssl','dgst','-sha256','-verify',str(p/'pub.der'),'-keyform','DER','-signature',str(p/'signature'),str(p/'message')],capture_output=True,env=ENV,timeout=8)
  need(r.returncode==0,'OWNER_SIGNATURE_INVALID')
 return a

def masked(h):
 for u in UNITS:
  p=h.path(CONTROL+'/'+u);need(p.is_symlink() and os.readlink(p)=='/dev/null','MASK_FILE_MISSING')
  s=h.show(u,'LoadState','ActiveState','MainPID','ControlPID','NextElapseUSecRealtime','NextElapseUSecMonotonic')
  need(s['LoadState']=='masked' and s['ActiveState']=='inactive' and s.get('MainPID','0')=='0' and s.get('ControlPID','0')=='0','UNIT_NOT_MASKED_IDLE')
  need(s.get('NextElapseUSecRealtime','') in ['', '0'] and s.get('NextElapseUSecMonotonic','') in ['', '0'],'TIMER_STILL_SCHEDULED')
  need(not h.links(u),'ENABLE_LINK_REMAINS')

def safe_quarantine(h,m):
 # Recovery only increases denial. It never unmasks, enables, or starts a unit.
 errors=[]
 for u in UNITS:
  try:h.mask(u)
  except Exception:errors.append('MASK_'+u)
 for args in [('daemon-reload',),('stop',*TIMERS),('stop',*[u for u in UNITS if u.endswith('.service')])]:
  try:h.systemctl(*args)
  except Exception:errors.append('SYSTEMCTL_'+args[0])
 for info in m['units'].values():
  for item in info['enabled_links']:
   try:
    if os.path.lexists(h.path(item['path'])):h.unlink_link(item)
   except Exception:errors.append('DISABLE_LINK')
 try:h.systemctl('daemon-reload');masked(h)
 except Exception:errors.append('POSTFLIGHT')
 need(not errors,'RECOVERY_INCOMPLETE_REQUIRES_ROOT_REVIEW')

def lease(request_fields):need(date(request_fields[9])>utc(),'PERMIT_EXPIRED_BEFORE_MUTATION')

def quarantine(h,m,journal,request_fields,phase):
 # Original files and secret drop-ins stay in place; copies stay root-private.
 for u,info in m['units'].items():
  for index,f in enumerate(info['files']):h.write(journal+'/'+u+'.'+str(index)+'.original',h.read(f['path']))
 h.write(journal+'/original-manifest.json',canonical(m))
 lease(request_fields)
 phase['mutation_started']=True
 for u in UNITS:h.mask(u)
 h.systemctl('daemon-reload')
 h.systemctl('stop',*TIMERS)
 h.systemctl('stop',*[u for u in UNITS if u.endswith('.service')])
 for info in m['units'].values():
  for item in info['enabled_links']:
   if request_fields[0]=='RECOVER' and not os.path.lexists(h.path(item['path'])):continue
   h.unlink_link(item)
 h.systemctl('daemon-reload');masked(h)
 # Only after exact masks are effective may a negative start be attempted.
 for u in UNITS:
  r=h.systemctl('start',u,allow_failure=True)
  need(r.returncode!=0 and 'masked' in (r.stderr+r.stdout).lower(),'MANUAL_START_NOT_DENIED')
 h.systemctl('daemon-reload');masked(h)
 validate_manifest(m,h);need(h.protected()==m['protected'],'PROTECTED_SERVICE_OR_LISTENER_CHANGED')
 h.write(journal+'/QUARANTINED.json',canonical({'utc':timestamp(utc()),'state':'QUARANTINED','manual_start_denied':list(UNITS),'original_files_unchanged':True,'financial_writer_fence':False,'funded_operations':'DENIED'}))

def restore(h,m,journal,admission_raw,request_fields,phase):
 # Independent root operator/Central admission is a separate input, NOT emitted
 # by this controller. Its exact digest is owner-signed for this inverse only.
 need(digest(admission_raw)==request_fields[10],'INVERSE_ADMISSION_DIGEST')
 admission=decode(admission_raw)
 need(admission.get('schema')=='wolo.financial-timer-resume-admission.v1' and admission.get('host')=='HEL1' and admission.get('machine_id_sha256')==m['machine_id_sha256'] and admission.get('original_manifest_sha256')==digest(canonical(m)) and admission.get('independent_financial_resume_authorized') is True and admission.get('legacy_http_writer_boundary_physically_accepted') is True and date(admission['expires_at'])>utc(),'INDEPENDENT_FINANCIAL_RESUME_NOT_ADMITTED')
 masked(h);validate_manifest(m,h);lease(request_fields)
 phase['mutation_started']=True
 # Original fragments/drop-ins were never replaced. Restore only exact links
 # and our four overlays; no blanket unmask, preset, enable or restart command.
 for info in m['units'].values():
  for item in info['enabled_links']:
   parent=str(Path(item['path']).parent);h.safe(parent,False);need(not os.path.lexists(h.path(item['path'])),'INVERSE_LINK_EXISTS');os.symlink(item['target'],h.path(item['path']));h.syncdir(parent)
 # Every original fragment/drop-in and enable link is complete while masks
 # still deny activation. Do not release any overlay before this equality.
 validate_manifest(m,h)
 for u,info in m['units'].items():need(h.links(u)==info['enabled_links'],'INVERSE_LINK_NOT_EXACT')
 lease(request_fields);need(date(admission['expires_at'])>utc(),'INVERSE_ADMISSION_EXPIRED')
 for u in UNITS:h.path(CONTROL+'/'+u).unlink()
 h.syncdir(CONTROL);h.systemctl('daemon-reload')
 validate_manifest(m,h)
 for u,info in m['units'].items():
  need(h.links(u)==info['enabled_links'],'INVERSE_LINK_NOT_EXACT')
  if info['state']['ActiveState']=='active':
   lease(request_fields);need(date(admission['expires_at'])>utc(),'INVERSE_ADMISSION_EXPIRED');h.systemctl('start',u)
 for u,info in m['units'].items():
  s=h.show(u,'ActiveState','UnitFileState');need(s['ActiveState']==info['state']['ActiveState'] and s['UnitFileState']==info['state']['UnitFileState'],'INVERSE_STATE_NOT_EXACT')
 need(h.protected()==m['protected'],'PROTECTED_SERVICE_OR_LISTENER_CHANGED')
 h.write(journal+'/RESTORED.json',canonical({'utc':timestamp(utc()),'state':'RESTORED_WITH_SEPARATE_FINANCIAL_AUTHORITY','logical_original_state_exact':True,'historical_trigger_and_start_timestamps_not_reversible':True}))

def consume_nonce(h,fields,packet):
 journal=STATE+'/'+fields[7];need(not h.path(journal).exists(),'NONCE_ALREADY_USED')
 h.mkdir(journal,0o700);h.write(journal+'/permit.json',canonical(packet));h.syncdir(STATE)
 return journal

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['inspect','request','apply']);p.add_argument('--manifest');p.add_argument('--action',choices=['QUARANTINE','RECOVER','RESTORE'],default='QUARANTINE');p.add_argument('--permit');p.add_argument('--owner-public');p.add_argument('--governance-receipt');p.add_argument('--inverse-admission')
 a=p.parse_args();need(sys.flags.isolated==1,'ISOLATED_INTERPRETER_REQUIRED');need(os.geteuid()==0,'ROOT_REQUIRED');h=Host()
 # A root process must not execute a source file writable by the project user.
 source=str(Path(__file__).absolute());h.safe(source);source_sha=digest(h.read(source))
 if a.mode=='inspect':print(canonical(observe(h)).decode());return
 need(a.manifest is not None,'MANIFEST_REQUIRED');raw=h.read(a.manifest);m=decode(raw);need(canonical(m)==raw,'MANIFEST_NOT_CANONICAL');validate_manifest(m,h)
 inverse_raw=h.read(a.inverse_admission) if a.inverse_admission else None
 if a.mode=='request':print(canonical(request(a.action,m,raw,source_sha,digest(inverse_raw) if inverse_raw else ZERO)).decode());return
 need(a.permit and a.owner_public and a.governance_receipt,'SIGNED_PERMIT_INPUTS_REQUIRED')
 need(digest(h.read(a.governance_receipt))==GOV_SHA,'C08_ADOPTED_RECEIPT_CHANGED')
 packet=decode(h.read(a.permit));fields=verify_packet(packet,h.read(a.owner_public),m,raw,source_sha,utc())
 need(fields[0]==a.action,'SIGNED_ACTION_DIFFERS_FROM_COMMAND')
 h.mkdir(STATE,0o700);h.mkdir(CONTROL,0o755)
 lock=os.open(h.path(STATE+'/execution.lock'),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
 try:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  # Nonce is durable BEFORE any unit operation. Errors leave denial overlays
  # in place; a failed/incomplete operation never automatically resumes writers.
  journal=consume_nonce(h,fields,packet)
  if fields[0] in ['QUARANTINE','RECOVER']:
   if fields[0]=='QUARANTINE':need(observe(h)==m,'LIVE_PREIMAGE_CHANGED_SINCE_APPROVAL')
   else:need(h.protected()==m['protected'],'RECOVERY_PROTECTED_IDENTITY_CHANGED')
   phase={'mutation_started':False}
   try:quarantine(h,m,journal,fields,phase)
   except Exception:
    if phase['mutation_started']:safe_quarantine(h,m)
    raise
  else:
   need(inverse_raw is not None,'INDEPENDENT_RESUME_ADMISSION_REQUIRED')
   phase={'mutation_started':False}
   try:restore(h,m,journal,inverse_raw,fields,phase)
   except Exception:
    if phase['mutation_started']:safe_quarantine(h,m)
    raise
  print(canonical({'state':'PASS_'+fields[0],'nonce':fields[7],'source_sha256':source_sha,'funded_operations':'DENIED','global_financial_fence':False}).decode())
 finally:os.close(lock)

if __name__=='__main__':
 try:main()
 except (Hold,OSError,ValueError,subprocess.SubprocessError) as e:
  print(canonical({'state':'HOLD','reason':str(e) if isinstance(e,Hold) else type(e).__name__,'funded_operations':'DENIED','automatic_resume':False}).decode());raise SystemExit(2)
