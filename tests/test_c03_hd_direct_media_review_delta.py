#!/usr/bin/env python3
"""Only WE2 review regressions: validated-byte capture and SQL clock guards."""
import importlib.util
from datetime import datetime,timedelta,timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

S=Path(__file__).resolve().parents[1]/'scripts'
def load(name):
    spec=importlib.util.spec_from_file_location(name,S/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
c=load('c03_hd_direct_media_owner_preimage')
m=load('c03_hd_direct_media_native_executor')
PG=Path(os.environ.get('PG16_BIN','/usr/lib/postgresql/16/bin'))
count=0
def check(ok,label):
    global count
    assert ok,label
    count+=1;print('PASS',label,flush=True)
def deny(fn,label):
    try:fn()
    except (c.Hold,m.Hold,OSError,ValueError):check(True,label)
    else:raise AssertionError(label)
def owner_capture_delta(root):
    stage=root/'stage';stage.mkdir(mode=0o700)
    for name in c.PINS:
        p=stage/name;p.write_bytes((S/name).read_bytes());p.chmod(0o600)
    data=c.load_sources(stage)
    w,a=c.sql_inputs(data)
    check(w==c.PREFIX+(S/'c03_hd_direct_media_catalog_witness.sql').read_bytes()+c.SUFFIX and a==(S/'c03_social_writer_catalog_readonly.sql').read_bytes(),'exact validated witness and audit bytes')
    for name in c.PINS:
        p=stage/name;replacement=stage/(name+'.replacement')
        replacement.write_bytes(b'SELECT 1; -- unreviewed replacement');replacement.chmod(0o600);replacement.replace(p)
    out=root/'capture';out.mkdir(mode=0o700);calls=[]
    def runner(db,sql,target):
        calls.append((db,sql))
        if target.name.endswith('witness.incomplete'):
            target.write_text(json.dumps({'database':db,'pg_version':'160010','enabled_event_triggers':0,'hba_parse_errors':0}))
        else:target.write_bytes(b'FINAL_NONAUTHORIZATION|{}\n')
    c.capture(out,data,runner)
    check(calls==[(db,sql) for db in c.DBS for sql in (w,a)],'replacement after check cannot change executed SQL across HD/DE')
    deny(lambda:c.load_sources(stage),'replacement hash denied on new capture')
    for name in c.PINS:
        p=stage/name;p.write_bytes((S/name).read_bytes());p.chmod(0o600)
    first=stage/next(iter(c.PINS))
    first.chmod(0o644);deny(lambda:c.load_sources(stage),'world-readable source denied');first.chmod(0o600)
    original=first.read_bytes();first.unlink();first.symlink_to(S/first.name)
    deny(lambda:c.load_sources(stage),'symlink source denied')
    first.unlink();first.write_bytes(original);first.chmod(0o600)
    # Swap the checked pathname during its descriptor read, not merely before open.
    real_read=os.read;done=False
    def swap(fd,n):
        nonlocal done
        b=real_read(fd,n)
        if not done and b:
            done=True
            repl=stage/'swap';repl.write_bytes(original);repl.chmod(0o600);repl.replace(first)
        return b
    with patch.object(c.os,'read',side_effect=swap):
        deny(lambda:c.load_sources(stage),'descriptor/path identity mismatch during read denied')
    check(done,'actual replacement occurred during descriptor read')
def run(*argv,success=True,reason=None,**kw):
    x=subprocess.run([str(a) for a in argv],capture_output=True,timeout=30,**kw)
    assert (x.returncode==0)==success,(argv,x.stderr[-1000:])
    if reason:assert reason.encode() in x.stderr,x.stderr[-1000:]
    return x.stdout
def pg_delta(root):
    data={k:(S/n).read_bytes() for k,(n,_) in m.FILES.items()}
    db=root/'db';sock=root/'sock';sock.mkdir(mode=0o700)
    run(PG/'initdb','-D',db,'--auth-local=trust','--auth-host=reject')
    port=44000+os.getpid()%9000
    run(PG/'pg_ctl','-D',db,'-o',f"-h '' -k {sock} -p {port}",'-w','-l',root/'log','start')
    try:
        def sql(q,database='aoe2hd_db',success=True,reason=None):
            return run(PG/'psql','-X','-qAt','-v','ON_ERROR_STOP=1','-h',sock,'-p',port,'-d',database,success=success,reason=reason,input=q.encode() if isinstance(q,str) else q)
        sql('CREATE DATABASE aoe2hd_db; CREATE DATABASE aoe2de_db;', 'postgres')
        prior=(S/'c03_hd_gateway_v2_physical_rehearsal.py').read_text()
        fixture='CREATE ROLE aoe2hd_user'+prior.split('sql("""\nCREATE ROLE aoe2hd_user',1)[1].split('""")',1)[0]
        sql(fixture)
        sql('ALTER TABLE public.direct_messages ADD attachment_kind varchar(20), ADD attachment_name varchar(255), ADD attachment_mime_type varchar(120), ADD attachment_data_url text, ADD shared_lobby_message_id integer, ADD delivered_at timestamp(6)')
        sql((S/'c03_hd_gateway_v2_restricted_install_candidate.sql').read_bytes())
        runner=lambda q,d,readonly:sql(q,d)
        hd=m.witness(data,'aoe2hd_db',runner);de=m.witness(data,'aoe2de_db',runner)
        base={'phase':'install','hd_full_sha256':hd['full_sha256'],'hd_invariant_sha256':hd['invariant_sha256']}
        fmt=lambda x:x.strftime('%Y-%m-%dT%H:%M:%SZ')
        now=datetime.now(timezone.utc).replace(microsecond=0)
        r={**base,'not_before':fmt(now-timedelta(seconds=5)),'expires_at':fmt(now-timedelta(seconds=1))}
        deny(lambda:m.require_live_permit(r,now),'last Python clock check rejects spent window')
        sql(m.build_transaction(data,r),success=False,reason='PERMIT_EXPIRED_AT_SQL_ENTRY')
        check(hd==m.witness(data,'aoe2hd_db',runner),'actual expired SQL entry leaves HD catalog unchanged')
        future={**base,'not_before':fmt(now+timedelta(seconds=60)),'expires_at':fmt(now+timedelta(seconds=120))}
        sql(m.build_transaction(data,future),success=False,reason='PERMIT_EXPIRED_AT_SQL_ENTRY')
        check(hd==m.witness(data,'aoe2hd_db',runner),'actual not-yet-valid SQL entry denied')
        # Introduce a test-only delay AFTER the reviewed DDL and before the final
        # unmodified expiry guard, proving the transaction rolls back, not retries.
        now=datetime.now(timezone.utc).replace(microsecond=0)
        short={**base,'not_before':fmt(now-timedelta(seconds=1)),'expires_at':fmt(now+timedelta(seconds=5))}
        txn=m.build_transaction(data,short)
        mark=b"DO $media_guard$ BEGIN IF (clock_timestamp()"
        idx=txn.rfind(mark)
        assert idx>txn.find(mark)
        sql(txn[:idx]+b'SELECT pg_sleep(6);\n'+txn[idx:],success=False,reason='PERMIT_EXPIRED_BEFORE_COMMIT')
        check(hd==m.witness(data,'aoe2hd_db',runner),'expiry after DDL rolls back all media objects')
        check(de==m.witness(data,'aoe2de_db',runner),'DE catalog unchanged through all expiry refusals')
        # The live window guard must not prevent normal valid execution.
        now=datetime.now(timezone.utc).replace(microsecond=0)
        live={**base,'not_before':fmt(now-timedelta(seconds=1)),'expires_at':fmt(now+timedelta(minutes=3))}
        result=m.parse_witness(sql(m.build_transaction(data,live)),'aoe2hd_db')
        check(result['media_functions']==4 and result['invariant_sha256']==hd['invariant_sha256'],'fresh permit window executes exact wrapped install')
    finally:run(PG/'pg_ctl','-D',db,'-m','fast','-w','stop')
def main():
    assert os.environ.get('C03_DISPOSABLE_FIXED_GATEWAY_ONLY')=='1' and os.geteuid()!=0
    assert b'16.' in run(PG/'postgres','--version')
    with tempfile.TemporaryDirectory(prefix='media-review-delta-') as tmp:
        root=Path(tmp);owner_capture_delta(root);pg_delta(root)
    print('REVIEW_DELTA_PASS',count,'FIXTURE_REMOVED',flush=True)
if __name__=='__main__':main()
