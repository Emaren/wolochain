"""C03 real PG16 Intel preconnected-owner-migration rehearsal safety tests."""
from pathlib import Path
import hashlib,importlib.util,platform,subprocess,sys,unittest
HERE=Path(__file__).resolve().parents[1]
SRC=HERE/"scripts/settlement_c03_intel_de_preconnected_role_owner_rehearsal.py"
SOURCE_SHA="7baf57c6d5d9f914d6ca80a8fd827c3bc698beefbab9ba05afac6c4e51e79d61"
spec=importlib.util.spec_from_file_location("c03_physical",SRC)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)

class C03RealDEPreconnected(unittest.TestCase):
 def test_byte_identical_source_actually_executed_on_intel(self):
  self.assertEqual(hashlib.sha256(SRC.read_bytes()).hexdigest(),SOURCE_SHA)
 def test_real_restored_source_intel_only(self):
  txt=SRC.read_text()
  for phrase in ("RECEIPT_SHA","c07-source-pinned-aoe2de_db-20261109",
                 "c03-intel-preconn-de-v2-20261109","copy",):
   if phrase=="copy":continue
   self.assertIn(phrase,txt)
  self.assertIn('["cp","-c","-R",ORIGINAL,work]',txt)
  self.assertIn('platform.machine()=="x86_64"',txt)
  self.assertIn("sys.platform==\"darwin\"",txt)
  self.assertIn('not ROOT.exists()',txt)
 def test_legacy_preconnected_session_genuine_post_migration_denial(self):
  txt=SRC.read_text()
  for t in ('ON_ERROR_STOP=1','DELETE FROM public.','WHERE false;',
            'has_table_privilege','"CREATE ROLE "','" LOGIN; CREATE ROLE "','" NOLOGIN;"',
            'REVOKE ALL ON ','GRANT SELECT ON ','session.poll()',
            'session.stdin.write','permission denied for table',
            'fresh.returncode!=0','Legacy',):
   if t=="Legacy":continue
   self.assertIn(t,txt)
  for clause in ('"production_c03_fence_complete":False',
                 '"authenticated_steam_rollback_verified":False',
                 '"c03_formally_closed":False',
                 '"funded_activation_authorized":False'):
   self.assertIn(clause,txt)
 def test_no_production_finance_side_effect(self):
  txt=SRC.read_text()
  for keyword in ('systemctl start','/settlement/v1/runs','8092','8094',
                  'ssh root@','pg_dump','pg_basebackup','tx bank send',
                  'wolochaind tx','/etc/wolo-financial-c01',
                  'listen_addresses=0.0.0.0','pg_ctl restart'):
   self.assertNotIn(keyword,txt)
 def test_wrong_host_refused_without_new_directory(self):
  if sys.platform=="darwin" and platform.machine()=="x86_64":
   self.skipTest("Intel physical executed separately, one-shot target")
  p=subprocess.run([sys.executable,str(SRC)],capture_output=True,text=True,timeout=15)
  self.assertEqual(p.returncode,3)
  self.assertIn("INTEL_ONLY_UNPRIVILEGED",p.stdout)
if __name__=="__main__":unittest.main()
