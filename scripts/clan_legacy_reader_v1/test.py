"""Disposable PG16 only; no production connection or data."""
import os,subprocess,tempfile,pathlib,json
root=pathlib.Path(__file__).resolve().parents[1]
pg=pathlib.Path(os.environ.get('CLAN_FIXTURE_PG_BIN','/opt/homebrew/opt/postgresql@16/bin'))
assert os.geteuid()!=0
assert '16.' in subprocess.check_output([pg/'postgres','--version'],text=True)
env={k:v for k,v in os.environ.items() if not k.upper().startswith('PG')}
def run(*args,check=True):
 p=subprocess.run([str(x) for x in args],capture_output=True,text=True,timeout=45,env=env)
 if check and p.returncode:raise RuntimeError(p.stderr[-3000:])
 return p
with tempfile.TemporaryDirectory(prefix='clan-legacy-fixture-',dir='/tmp') as tmp:
 t=pathlib.Path(tmp);sock=t/'s';sock.mkdir(mode=0o700);data=t/'data';port=45000+os.getpid()%10000
 run(pg/'initdb','-D',data,'-U','postgres','--auth-local=trust','--auth-host=reject');started=False
 try:
  run(pg/'pg_ctl','-D',data,'-o',f"-h '' -k {sock} -p {port}",'-l',t/'log','-w','start');started=True
  def psql(sql=None,file=None,role='postgres',db='aoe2hd_db',check=True):
   args=[pg/'psql','-X','-qAt','-v','ON_ERROR_STOP=1','-h',sock,'-p',port,'-d',db,'-U',role]
   return run(*args,*(['-f',file] if file else ['-c',sql]),check=check)
  psql(file=root/'clan_hall_reader_v1/fixture.sql',db='postgres');psql(file=root/'c03_hd_clan_image_v1_install_candidate.sql');psql(file=root/'clan_hall_reader_v1/install.sql')
  ref='file:v1:clan-hall/2026/11/12345678-1234-1234-1234-123456789abc.png';protected='file:v1:clan-'+'b'*32+'.png'
  psql(f"UPDATE clan_message_attachments SET storage_ref='{ref}' WHERE id=2; INSERT INTO aoe2war_clan_image_hd_v1.request_keys VALUES(1,'fixture',1,'{'a'*64}','file:v1:clan-{'a'*32}.png','x.png','image/png',123,85,1)")
  def ok(label,b):assert b,label;print('PASS',label,flush=True)
  def read(actor='alice',slug='alpha',aid=2):
   raw=psql(f"SELECT aoe2war_clan_image_hd_v1.read_image('{actor}','{slug}',{aid})",role='aoe2war_social_writer').stdout.strip();return json.loads(raw) if raw else None
  def hall(actor='alice',slug='alpha'):
   raw=psql(f"SELECT aoe2war_clan_read_hd_v1.read_hall('{actor}','{slug}',NULL,86)",role='aoe2war_social_writer').stdout.strip();return json.loads(raw) if raw else None
  snap="SELECT md5(string_agg(row_to_json(a)::text,',' ORDER BY id)) FROM public.clan_message_attachments a"
  before=psql(snap).stdout
  ok('native catalog preflight', 'PASS_NATIVE_CLAN_LEGACY_CATALOG_PREFLIGHT_READ_ONLY' in psql(file=root/'clan_legacy_reader_v1/native-preflight.sql').stdout)
  psql('GRANT SELECT ON public.clan_message_attachments TO aoe2war_social_writer');ok('preflight rejects raw grant',psql(file=root/'clan_legacy_reader_v1/native-preflight.sql',check=False).returncode!=0);psql('REVOKE SELECT ON public.clan_message_attachments FROM aoe2war_social_writer')
  psql('ALTER FUNCTION aoe2war_clan_image_hd_v1.read_image(text,text,integer) RESET search_path');ok('preflight rejects search path drift',psql(file=root/'clan_legacy_reader_v1/native-preflight.sql',check=False).returncode!=0);psql('ALTER FUNCTION aoe2war_clan_image_hd_v1.read_image(text,text,integer) SET search_path=pg_catalog,pg_temp')
  ok('original legacy denied',read() is None and hall()['messages'][0]['unsupportedAttachment'])
  ok('wrong database rejected',psql(file=root/'clan_legacy_reader_v1/install.sql',db='postgres',check=False).returncode!=0)
  psql(file=root/'clan_legacy_reader_v1/install.sql')
  ok('empty admission no legacy expansion',read() is None and hall()['messages'][0]['unsupportedAttachment'])
  ok('new upload receipt preserved',read(aid=1)['name']=='x.png')
  psql(file=root/'clan_legacy_reader_v1/inverse-empty.sql');ok('empty inverse restores original',read() is None and psql(snap).stdout==before)
  psql(file=root/'clan_legacy_reader_v1/install.sql')
  psql(f"INSERT INTO aoe2war_clan_legacy_hd_v1.admitted VALUES(2,86,'{ref}','{protected}','image/png','old.png',123,'{'c'*64}')")
  ok('mapped image exact private ref',read()=={'storageRef':protected,'mimeType':'image/png','name':'old.png','sizeBytes':123})
  message=hall()['messages'][0];ok('history shows metadata only',message['attachments']==[{'id':2,'name':'old.png','mimeType':'image/png','sizeBytes':123}] and not message['unsupportedAttachment'] and 'file:v1:' not in json.dumps(message))
  ok('outsider and system denied',read('eve') is None and read('bot') is None and hall('eve') is None)
  ok('wrong clan denied',read('alice','beta') is None)
  ok('other active member admitted',read('bob') is not None)
  psql("UPDATE clan_members SET status='inactive' WHERE user_id=2");ok('membership revoked',read('bob') is None)
  psql("UPDATE clan_messages SET audience='public' WHERE id=86");ok('audience drift fails closed',read() is None and hall()['messages'][0]['unsupportedAttachment']);psql("UPDATE clan_messages SET audience='clan' WHERE id=86")
  psql("UPDATE clan_message_attachments SET size_bytes=124 WHERE id=2");ok('metadata drift fails closed',read() is None);psql("UPDATE clan_message_attachments SET size_bytes=123 WHERE id=2")
  for role in ('aoe2war_social_writer','aoe2war_web_prod','aoe2war_clan_image_exec_v1'):
   ok('raw map denied '+role,psql('SELECT * FROM aoe2war_clan_legacy_hd_v1.admitted',role=role,check=False).returncode!=0)
  ok('raw legacy helper denied to social caller',psql("SELECT aoe2war_clan_legacy_hd_v1.read_mapped('alice','alpha',2)",role='aoe2war_social_writer',check=False).returncode!=0)
  ok('populated inverse refuses',psql(file=root/'clan_legacy_reader_v1/inverse-empty.sql',check=False).returncode!=0 and read() is not None)
  ok('original records untouched',psql(snap).stdout==before)
 finally:
  if started:run(pg/'pg_ctl','-D',data,'-m','fast','-w','stop')
print('ISOLATED_PG16_STOPPED_REMOVED')
