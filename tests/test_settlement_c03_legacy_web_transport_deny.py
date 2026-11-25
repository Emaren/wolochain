"""C03 deny-only legacy 3030 transport guard: fail-closed source tests."""
from __future__ import annotations
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,call
import unittest
P=Path(__file__).resolve().parents[1]/'scripts/settlement_c03_legacy_web_transport_deny.py'
spec=importlib.util.spec_from_file_location('c03_3030_deny',P)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class LegacyTransportDenyTests(unittest.TestCase):
 def test_exact_versioned_legacy_r25_origins_and_ports(self):
  self.assertEqual((m.ORIGIN_PID,m.R25_PID),(2625090,1766058))
  self.assertEqual((m.OLD_UID,m.R25_UID),(1000,990))
  self.assertEqual(m.OLD_CGROUP,'/system.slice/aoe2hdbets-web.service')
  self.assertEqual(len(m.FILES),3)
  self.assertTrue(all(len(v)==64 for v in m.FILES.values()))
  self.assertEqual(m.TABLE,'aoe2war_c03_legacy_finance_deny')

 def test_kernel_rule_reject_only_two_loopback_legacy_ports(self):
  s=m.NFT
  self.assertIn('type filter hook output priority -12; policy accept;',s)
  self.assertIn('meta skuid 1000 ip daddr 127.0.0.1 tcp dport { 8092, 8093 } counter reject with tcp reset',s)
  self.assertNotIn('meta skuid 990',s)
  self.assertEqual(s.count('reject with tcp reset'),1)
  self.assertNotIn('drop',s)
  self.assertEqual(s.count('chain output'),1)

 def test_source_only_two_local_urls_fail_closed(self):
  m.endpoint({b'WOLO_SETTLEMENT_URL':b'http://127.0.0.1:8092'},
      'WOLO_SETTLEMENT_URL',8092)
  m.endpoint({b'WOLO_FOUNDER_SETTLEMENT_URL':b'http://127.0.0.1:8093'},
      'WOLO_FOUNDER_SETTLEMENT_URL',8093)
  for value in (b'',b'http://localhost:8092',b'https://127.0.0.1:8092',
                b'http://127.0.0.1:8093',b'http://10.10.10.10:8092',
                b'http://127.0.0.1:8092?anything=x'):
   with self.subTest(value=value),self.assertRaises(m.Hold):
    m.endpoint({b'WOLO_SETTLEMENT_URL':value},'WOLO_SETTLEMENT_URL',8092)

 def test_rule_verifier_rejects_drift(self):
  normal='''table inet aoe2war_c03_legacy_finance_deny {
  chain output {
    type filter hook output priority -12; policy accept;
    meta skuid 1000 ip daddr 127.0.0.1 tcp dport { 8092, 8093 } counter packets 0 bytes 0 reject with tcp reset # handle 3
  }
}'''
  with patch.object(m,'run',return_value=SimpleNamespace(stdout=normal)):
   m.verify_rule()
  for bad in (normal.replace('skuid 1000','skuid 990'),
              normal.replace('8092, 8093','8092, 8094'),
              normal.replace('priority -12','priority 2'),
              normal.replace('policy accept','policy drop'),
              normal+'meta skuid 1000'):
   with self.subTest(bad=bad[-70:]),patch.object(m,'run',return_value=SimpleNamespace(stdout=bad)):
    with self.assertRaises(m.Hold):m.verify_rule()

 def test_readonly_inspect_never_installs(self):
  with patch.object(m,'identity'),patch.object(m,'websites'),\
       patch.object(m,'no_table'),patch.object(m,'connect_probe',return_value=True),\
       patch.object(m,'run',return_value=SimpleNamespace(returncode=0,stdout='')) as r:
   result=m.audit('inspect')
   self.assertEqual(result['status'],'PASS_C03_LEGACY_TWO_PORT_DENY_PREFLIGHT_NOT_INSTALLED')
   self.assertEqual(r.call_count,1)
   self.assertEqual(r.call_args.args[0][:2],['/usr/sbin/nft','-c'])

 def test_verify_fails_if_old_user_reaches_service(self):
  def probe(port,*,actor='root'):return True
  with patch.object(m,'identity'),patch.object(m,'websites'),\
       patch.object(m,'verify_rule'),patch.object(m,'connect_probe',side_effect=probe):
   with self.assertRaises(m.Hold):m.audit('verify')

 def test_verify_passes_root_preserved_and_old_uid_denied(self):
  with patch.object(m,'identity'),patch.object(m,'websites'),\
       patch.object(m,'verify_rule'),\
       patch.object(m,'connect_probe',side_effect=lambda port,actor='root':actor=='root'):
   r=m.audit('verify')
   self.assertIn('NOT_GLOBAL_FINANCE_FENCE',r['status'])

 def test_source_cannot_authorize_finance_or_remove_denial(self):
  s=P.read_text()
  for exact in ('"financial_scope_complete":False',
                '"direct_chain_rpc_cli_and_signer_fenced":False',
                '"all_database_writers_fenced":False',
                '"live_c03_gate_accepted":False',
                '"coordinated_c06_capture_authorized":False',
                '"funded_release_authorized":False'):
   self.assertIn(exact,s)
  for unsafe in ('--mode=rollback','systemctl stop','systemctl restart',
                 'pg_terminate_backend','ALTER TABLE','WOLO_SETTLEMENT_AUTH_TOKEN='+chr(34)):
   self.assertNotIn(unsafe,s)
  self.assertIn('OLD_UID_ALREADY_BLOCKED_UNRELATED_DENIAL',s)
  self.assertIn('run(["/usr/sbin/nft","delete","table","inet",TABLE],check=False)',s)

if __name__=='__main__':unittest.main()
