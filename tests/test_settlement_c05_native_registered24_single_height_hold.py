"""C05 immutable same-height bank census source; all success still financial HOLD."""
from pathlib import Path
import hashlib,importlib.util,re,subprocess,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
FILE=ROOT/"scripts/settlement_c05_native_registered24_single_height_hold.py"
SHA="2b6eb9fd6980dceee24936d9fc302403833f343b2893e5a7611e848ef4f31776"
spec=importlib.util.spec_from_file_location("c05_24_exact",FILE)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)
class RegisteredBankProof(unittest.TestCase):
 def test_source_bytes_exact_physical_sha(self):
  self.assertEqual(hashlib.sha256(FILE.read_bytes()).hexdigest(),SHA)
 def test_exact_live_docs_canonical_registered_set(self):
  text=(ROOT/"docs/mainnet-wallets.md").read_text()
  data=text[text.index("## Current Mainnet Address Labels"):text.index("## Operational Notes")]
  addrs=set(re.findall(r'wolo1[a-z0-9]{38}',data))
  self.assertEqual(len(addrs),23)
  self.assertEqual(addrs,{v for _,v in m.parse_registered_document(text)})
  self.assertNotIn(m.C01,addrs)
 def test_rigid_chain_native_height_and_liveness(self):
  source=FILE.read_text()
  for item in ('/proc/1009/exe','"wolo-1"','--height','block_id',
               'catching_up','native','127.0.0.1:27657',
               'CANONICAL_23_WALLET_DOC_INCOMPLETE','C01 not in','source_sha256',
               '"eligible_unencumbered_collateral_uwolo":"0"',
               'DOCUMENT_SHA256','O_NOFOLLOW',
               '"operator_exclusive_control_verified":False',
               '"offhost_consensus_witness_verified":False',
               '"c05_gate_closed":False',
               '"c09_transaction_authorized":False',
               'os.O_NOFOLLOW','os.O_EXCL'):
   self.assertIn(item,source)
 def test_never_authorizes_financial_spend_or_reads_credential(self):
  source=FILE.read_text()
  for bad in ('wolochaind tx','systemctl start','systemctl unmask',
              'send-transaction','/settlement/v1/runs','password',
              'passphrase','private_key','DELETE FROM',
              'INSERT INTO','UPDATE public','8092','8094'):
   self.assertNotIn(bad,source)
 def test_client_m1_execution_hard_denies(self):
  if sys.platform=="linux" and m.os.geteuid()==0:
   self.skipTest("HEL1 positive side executed independently")
  proc=subprocess.run([sys.executable,str(FILE)],capture_output=True,text=True,timeout=9)
  self.assertEqual(proc.returncode,3)
  self.assertIn('HOLD_C05_SINGLE_HEIGHT_REGISTERED_WALLET_OBSERVATION',proc.stdout)
if __name__=="__main__":unittest.main()
