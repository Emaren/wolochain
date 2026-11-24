#!/usr/bin/env python3
"""New executor composition only; do not repeat the prior 56 media checks."""
import base64
from datetime import datetime,timezone,timedelta
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
S=ROOT/'scripts'
spec=importlib.util.spec_from_file_location('media_executor',S/'c03_hd_direct_media_native_executor.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
PG=Path(os.environ.get('PG16_BIN','/usr/lib/postgresql/16/bin'))
def run(*argv,success=True,**kw):
    p=subprocess.run([str(x) for x in argv],capture_output=True,timeout=30,**kw)
    assert (p.returncode==0)==success,(argv,p.stderr[-2000:])
    return p.stdout
def main():
    assert os.environ.get('C03_DISPOSABLE_FIXED_GATEWAY_ONLY')=='1' and os.geteuid()!=0
    assert b'16.' in run(PG/'postgres','--version')
    count=0
    def check(ok,label):
        nonlocal count
        assert ok,label
        count+=1;print('PASS',label,flush=True)
    def deny(f,label):
        try:f()
        except (m.Hold,ValueError,KeyError,AssertionError):check(True,label)
        else:raise AssertionError(label)
    data={k:(S/n).read_bytes() for k,(n,_) in m.FILES.items()}
    with tempfile.TemporaryDirectory(prefix='media-native-delta-') as tmp:
        root=Path(tmp);db=root/'db';sock=root/'s';sock.mkdir(mode=0o700)
        run(PG/'initdb','-D',db,'--auth-local=trust','--auth-host=reject')
        port=42000+os.getpid()%10000
        run(PG/'pg_ctl','-D',db,'-o',f"-h '' -k {sock} -p {port}",'-w','-l',root/'log','start')
        try:
            def sql(q,database='aoe2hd_db',success=True):
                if isinstance(q,str):q=q.encode()
                return run(PG/'psql','-X','-qAt','-v','ON_ERROR_STOP=1','-h',sock,'-p',port,'-d',database,success=success,input=q)
            sql('CREATE DATABASE aoe2hd_db; CREATE DATABASE aoe2de_db;', 'postgres')
            prior=(S/'c03_hd_gateway_v2_physical_rehearsal.py').read_text()
            fixture='CREATE ROLE aoe2hd_user'+prior.split('sql("""\nCREATE ROLE aoe2hd_user',1)[1].split('""")',1)[0]
            sql(fixture)
            sql('ALTER TABLE public.direct_messages ADD attachment_kind varchar(20), ADD attachment_name varchar(255), ADD attachment_mime_type varchar(120), ADD attachment_data_url text, ADD shared_lobby_message_id integer, ADD delivered_at timestamp(6)')
            sql((S/'c03_hd_gateway_v2_restricted_install_candidate.sql').read_bytes())
            def runner(q,database,readonly):
                return sql(q,database)
            hd=m.witness(data,'aoe2hd_db',runner);de=m.witness(data,'aoe2de_db',runner)
            check(hd['media_functions']==0 and hd['media_relations']==0 and de['media_functions']==0,'catalog-only HD/DE preimage')
            check(hd==m.witness(data,'aoe2hd_db',runner),'catalog digest stable on repeat')
            # Actual disposable P256 signature, never a real owner key.
            key=root/'key';pub=root/'pub';sig=root/'sig';message=root/'message'
            run('/usr/bin/openssl','ecparam','-name','prime256v1','-genkey','-noout','-out',key)
            run('/usr/bin/openssl','ec','-in',key,'-pubout','-outform','DER','-out',pub)
            public=pub.read_bytes()[-65:]
            review={'source_commit':m.SOURCE,'executor_sha256':m.digest((S/'c03_hd_direct_media_native_executor.py').read_bytes()),'file_sha256':m.file_pins(),'host_id_sha256':'a'*64,'hba_sha256':'b'*64,'owner_public_sha256':m.digest(public)}
            now=datetime.now(timezone.utc).replace(microsecond=0)
            r={**review,'schema':'wolo.we1.hd-direct-media-permit.v1','action':'HD_DIRECT_MEDIA_SQL_ONLY','database':'aoe2hd_db','phase':'install','nonce':'c'*64,'not_before':now.strftime('%Y-%m-%dT%H:%M:%SZ'),'expires_at':(now+timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%SZ'),'hd_full_sha256':hd['full_sha256'],'hd_invariant_sha256':hd['invariant_sha256'],'de_full_sha256':de['full_sha256'],**{x:False for x in m.FLAGS}}
            def packet(req):
                message.write_bytes(m.DOMAIN+m.canonical(req))
                run('/usr/bin/openssl','dgst','-sha256','-sign',key,'-out',sig,message)
                return m.canonical({'request':req,'signature_der_b64':base64.b64encode(sig.read_bytes()).decode()})
            raw=packet(r)
            check(m.verify_packet(raw,public,review,'install','c'*64,now)==r,'actual P256 exact permit verifies')
            for change,label in [({'database':'aoe2de_db'},'DE mutation denied'),({'funding_authorized':True},'funding denied'),({'source_commit':'x'},'source mismatch denied'),({'expires_at':(now+timedelta(minutes=11)).strftime('%Y-%m-%dT%H:%M:%SZ')},'oversize lifetime denied'),({'nonce':'d'*64},'nonce mismatch denied')]:
                deny(lambda:m.verify_packet(packet({**r,**change}),public,review,'install','c'*64,now),label)
            deny(lambda:m.verify_packet(raw,public,review,'install','c'*64,now+timedelta(minutes=6)),'expired signature denied')
            altered=json.loads(raw);altered['request']['hd_full_sha256']='f'*64
            deny(lambda:m.verify_packet(m.canonical(altered),public,review,'install','c'*64,now),'altered preimage invalidates real signature')
            deny(lambda:m.build_transaction({**data,'install':data['install']+b' '},r),'modified SQL bytes denied')
            sql('GRANT SELECT ON public.financial_test_escrow TO aoe2war_social_writer')
            check(m.witness(data,'aoe2hd_db',runner)['full_sha256']!=hd['full_sha256'],'financial ACL drift detectable')
            sql(m.build_transaction(data,r),success=False)
            check(m.witness(data,'aoe2hd_db',runner)['media_functions']==0,'stale signed preimage aborts before DDL')
            sql('REVOKE SELECT ON public.financial_test_escrow FROM aoe2war_social_writer')
            # GRANT/REVOKE may change raw NULL ACL to explicit owner ACL: sign actual new fixture state.
            hd=m.witness(data,'aoe2hd_db',runner)
            r.update(hd_full_sha256=hd['full_sha256'],hd_invariant_sha256=hd['invariant_sha256'])
            result=m.parse_witness(sql(m.build_transaction(data,r)),'aoe2hd_db')
            check(result['media_functions']==4 and result['media_relations']==5,'actual exact wrapped install')
            check(result['invariant_sha256']==hd['invariant_sha256'],'all original catalog invariant preserved')
            check(result==m.witness(data,'aoe2hd_db',runner),'postcommit HD readback matches')
            check(de==m.witness(data,'aoe2de_db',runner),'DE full catalog unchanged')
            inverse={**r,'phase':'inverse','hd_full_sha256':result['full_sha256'],'nonce':'e'*64}
            sql(m.build_transaction(data,inverse,'f'*64),success=False)
            check(result==m.witness(data,'aoe2hd_db',runner),'incorrect original inverse digest aborts entire inverse')
            final=m.parse_witness(sql(m.build_transaction(data,inverse,hd['full_sha256'])),'aoe2hd_db')
            check(final==hd,'actual unused inverse restores exact complete HD digest')
            check(de==m.witness(data,'aoe2de_db',runner),'DE unchanged after inverse')
            # Root file protection remains a native admission requirement. Exercise
            # journal state logic with fixture-only reader on private temporary state.
            m.STATE=root/'state';m.STATE.mkdir(mode=0o700)
            m.secure_file=lambda path,limit=131072:path.read_bytes()
            check(m.phase_state()==('install',None),'empty epoch install only')
            nonce='c'*64
            info={'phase':'install','nonce':nonce,'permit_sha256':m.digest(raw)}
            m.write_once(m.STATE/('nonce-'+nonce+'.json'),m.canonical(info))
            deny(m.phase_state,'consumed nonce without receipt blocks retry')
            receipt={**info,'status':'INSTALLED_POSTIMAGE_PASS','source_commit':m.SOURCE,'financial_authorized':False,'hd_before':hd,'hd_after':result,'de_before':de,'de_after':de}
            m.write_once(m.STATE/('receipt-'+nonce+'.json'),m.canonical(receipt))
            check(m.phase_state()==('inverse',receipt),'successful immutable install permits only inverse')
            (m.STATE/'unexpected').write_text('hold')
            deny(m.phase_state,'unknown state evidence blocks transition')
        finally:run(PG/'pg_ctl','-D',db,'-m','fast','-w','stop')
    print('NATIVE_EXECUTOR_DELTA_PASS',count,'FIXTURE_REMOVED',flush=True)
if __name__=='__main__':main()
