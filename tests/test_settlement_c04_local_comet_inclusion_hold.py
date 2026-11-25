import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from scripts import settlement_c04_local_comet_inclusion_hold as c

def fake():
    tx=b"synthetic-unsigned-test-tx-not-production"
    body=base64.b64encode(tx).decode()
    sha=hashlib.sha256(tx).digest()
    leaf=hashlib.sha256(bytes([0])+sha).digest()
    addr="wolo1"+"a"*38
    cand={"query_sha256":"b"*64,
          "candidate":{"claim_id":1,"kind":"bet_payout","nominal_wolo":3,
          "candidate_tx_hash":sha.hex().upper(),"candidate_height":123,
          "candidate_amount_uwolo":3000000,"candidate_recipient":addr}}
    rpc={"tx":body,"hash":sha.hex().upper(),"height":"123",
         "tx_result":{"code":0,"events":[
            {"type":"transfer","attributes":[
                {"key":"recipient","value":addr},
                {"key":"amount","value":"3000000uwolo"}]}]},
         "proof":{"data":body,"root_hash":leaf.hex().upper(),
            "proof":{"total":"1","index":"0",
            "leaf_hash":base64.b64encode(leaf).decode(),"aunts":[]}}}
    block={"block":{"header":{"chain_id":"wolo-1","height":"123",
                              "data_hash":leaf.hex().upper()},
                    "data":{"txs":[body]}},
           "block_id":{"hash":"d"*64}}
    return cand,rpc,block

class LocalMerkleTests(unittest.TestCase):
    def setUp(self):self.c,self.tx,self.b=fake()

    def held(self):
        with self.assertRaises(c.Hold):c.validate(self.c,self.tx,self.b)

    def test_valid_synthetic_proof_is_still_financial_hold(self):
        out=c.validate(self.c,self.tx,self.b)
        self.assertEqual(out["status"],
            "HOLD_C04_LOCAL_MERKLE_INCLUSION_NOT_INDEPENDENT_PAYMENT_FINALITY")
        self.assertTrue(out["merkle_root_equals_local_block_data_hash"])
        self.assertFalse(out["independent_checkpoint_authenticated"])
        self.assertFalse(out["claim_economic_payout_purpose_authenticated"])
        self.assertFalse(out["claim_discharge_authorized"])
        self.assertFalse(out["financial_release_authorized"])

    def test_changed_transaction_bytes_denied(self):
        self.tx["tx"]=base64.b64encode(b"another-tx").decode();self.held()

    def test_changed_index_hash_denied(self):
        self.c["candidate"]["candidate_tx_hash"]="0"*64;self.held()

    def test_changed_claim_amount_denied(self):
        self.c["candidate"]["nominal_wolo"]=4;self.held()

    def test_changed_chain_height_denied(self):
        self.b["block"]["header"]["height"]="124";self.held()

    def test_changed_chain_id_denied(self):
        self.b["block"]["header"]["chain_id"]="not-wolo-1";self.held()

    def test_nonzero_execution_code_denied(self):
        self.tx["tx_result"]["code"]=11;self.held()

    def test_missing_transfer_event_denied(self):
        self.tx["tx_result"]["events"]=[];self.held()

    def test_wrong_transfer_recipient_denied(self):
        self.tx["tx_result"]["events"][0]["attributes"][0]["value"]="wolo1"+"b"*38
        self.held()

    def test_wrong_native_uwolo_amount_denied(self):
        self.tx["tx_result"]["events"][0]["attributes"][1]["value"]="3uwolo";self.held()

    def test_duplicate_transfer_attribute_denied(self):
        self.tx["tx_result"]["events"][0]["attributes"].append({"key":"amount","value":"3000000uwolo"})
        self.held()

    def test_root_or_leaf_forgery_denied(self):
        self.tx["proof"]["root_hash"]="0"*64;self.held()
        self.c,self.tx,self.b=fake()
        self.tx["proof"]["proof"]["leaf_hash"]=base64.b64encode(b"x"*32).decode()
        self.held()

    def test_fake_merkle_aunt_denied(self):
        self.tx["proof"]["proof"]["aunts"]=[base64.b64encode(b"z"*32).decode()]
        self.held()

    def test_missing_block_tx_denied(self):
        self.b["block"]["data"]["txs"]=[];self.held()

    def test_only_one_operator_source_does_not_claim_independent_consensus(self):
        out=c.validate(self.c,self.tx,self.b)
        self.assertTrue(out["single_operator_rpc_source_only"])
        self.assertFalse(out["payer_custody_signer_authenticated"])

    def test_malformed_input_cannot_call_financial_pass(self):
        self.c["query_sha256"]=None;self.held()

    def test_merkle_two_leaf_roundtrip_and_tamper_denial(self):
        tx=b"synthetic-unsigned-test-tx-not-production"
        sha=hashlib.sha256(tx).digest()
        leaf0=hashlib.sha256(bytes([0])+sha).digest()
        leaf1=hashlib.sha256(bytes([0])+hashlib.sha256(b"other-tx").digest()).digest()
        root=hashlib.sha256(bytes([1])+leaf0+leaf1).digest()
        self.tx["proof"]["proof"].update(
            total="2",index="0",aunts=[base64.b64encode(leaf1).decode()])
        self.tx["proof"]["root_hash"]=root.hex().upper()
        self.b["block"]["header"]["data_hash"]=root.hex().upper()
        self.b["block"]["data"]["txs"].append(base64.b64encode(b"other-tx").decode())
        self.assertTrue(c.validate(self.c,self.tx,self.b)["merkle_root_equals_local_block_data_hash"])
        self.tx["proof"]["proof"]["aunts"]=[base64.b64encode(b"x"*32).decode()]
        self.held()

    def test_private_receipt_enforces_digest_and_0600(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"candidate.json"
            p.write_text(json.dumps(self.c))
            good=hashlib.sha256(p.read_bytes()).hexdigest()
            p.chmod(0o644)
            with self.assertRaises(c.Hold):c.private_json(p,good)
            p.chmod(0o600)
            self.assertEqual(c.private_json(p,good),self.c)
            with self.assertRaises(c.Hold):c.private_json(p,"0"*64)
            q=Path(tmp)/"sym";q.symlink_to(p)
            with self.assertRaises(c.Hold):c.private_json(q,good)

    def test_local_malformed_raw_never_exposes_private_data_in_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            hashes={}
            paths={}
            for name,value in (("candidate",self.c),("tx",self.tx),("block",self.b)):
                p=Path(tmp)/(name+".json");p.write_text(json.dumps(value));p.chmod(0o600)
                paths[name]=p;hashes[name]=hashlib.sha256(p.read_bytes()).hexdigest()
            argv=sum(([f"--{x}",str(paths[x]),f"--{x}-sha256",hashes[x]]
                      for x in ("candidate","tx","block")),[])
            out=io.StringIO()
            with redirect_stdout(out):rc=c.main(argv)
            self.assertEqual(rc,3)
            self.assertFalse(json.loads(out.getvalue())["claim_discharge_authorized"])
            self.b["block"]["header"]["data_hash"]="0"*64
            paths["block"].write_text(json.dumps(self.b))
            hashes["block"]=hashlib.sha256(paths["block"].read_bytes()).hexdigest()
            argv=sum(([f"--{x}",str(paths[x]),f"--{x}-sha256",hashes[x]]
                      for x in ("candidate","tx","block")),[])
            with redirect_stdout(out:=io.StringIO()):rc=c.main(argv)
            self.assertEqual(rc,2)
            self.assertFalse(json.loads(out.getvalue())["financial_release_authorized"])

if __name__=="__main__":unittest.main()
