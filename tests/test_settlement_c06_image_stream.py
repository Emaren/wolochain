import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import settlement_c06_image_stream as im
from settlement_c06_checkpoint_rehearsal import Hold,digest

class ImageStream(unittest.TestCase):
    def test_exact_reconstruction_and_metric(self):
        with tempfile.NamedTemporaryFile() as f,tempfile.NamedTemporaryFile() as g:
            raw=b"synthetic-image-only"+bytes(im.BLOCK+7)
            f.write(raw);f.flush()
            pre=im.identity(f.fileno())
            out=io.BytesIO()
            receipt=im.stream_exact(f.fileno(),pre,out,expected_sha=digest(raw))
            self.assertEqual(out.getvalue(),raw)
            self.assertEqual(receipt["sha256"],digest(raw))
            self.assertGreater(receipt["source_read_ns"],0)
            self.assertFalse(receipt["retirement_authorized"])
            g.write(out.getvalue());g.flush()
            self.assertEqual(im.verify_reconstruction(g.fileno(),digest(raw),len(raw))["sha256"],digest(raw))
            g.seek(0);g.write(b"X");g.flush()
            with self.assertRaises(Hold):im.verify_reconstruction(g.fileno(),digest(raw),len(raw))
    def test_short_sink_and_drift(self):
        with tempfile.NamedTemporaryFile() as f:
            f.write(b"test");f.flush();pre=im.identity(f.fileno())
            class Short:
                def write(self,b):return len(b)-1
            with self.assertRaises(Hold):im.stream_exact(f.fileno(),pre,Short())
            with self.assertRaises(Hold):im.stream_exact(f.fileno(),pre,io.BytesIO(),expected_sha="f"*64)
            f.write(b"x");f.flush()
            with self.assertRaises(Hold):im.stream_exact(f.fileno(),pre,io.BytesIO())
    def test_financial_manifest_and_reconstructed_order(self):
        from settlement_c06_checkpoint_rehearsal import canonical
        import copy
        with tempfile.NamedTemporaryFile() as f:
            raw=b"abcdef"
            f.write(raw);f.flush()
            source={**im.identity(f.fileno()),"uid":0,"gid":0,"mode":0o600}
            plan=digest(b"plan")
            chunks=[{"index":i,"offset":i*3,"plain_bytes":3,"cipher_bytes":19,
                     "plain_sha256":digest(raw[i*3:i*3+3]),
                     "cipher_sha256":digest(bytes([i]))} for i in range(2)]
            m={"schema":"wolo.financial.image-continuation.v1","purpose":im.PURPOSE,
               "plan_sha256":plan,"source":source,"source_sha256":digest(raw),"chunks":chunks}
            def kwargs(x):
                return dict(expected_plan=plan,expected_source=source,
                    expected_manifest_sha=digest(canonical(x)),max_chunk_bytes=3)
            proof=im.verify_financial_reconstruction(f.fileno(),m,**kwargs(m))
            self.assertEqual(proof["sha256"],digest(raw))
            self.assertFalse(proof["independent_host_authenticated"])
            self.assertFalse(proof["retirement_authorized"])
            for key,value in (("offset",2),("index",False),("plain_bytes",4)):
                bad=copy.deepcopy(m);bad["chunks"][1][key]=value
                with self.assertRaises(Hold):im.financial_manifest(bad,**kwargs(bad))
            bad=copy.deepcopy(m);bad["chunks"].pop()
            with self.assertRaises(Hold):im.financial_manifest(bad,**kwargs(bad))
            bad=copy.deepcopy(m);bad["purpose"]="SITE_RUNTIME"
            with self.assertRaises(Hold):im.financial_manifest(bad,**kwargs(bad))
            bad=copy.deepcopy(m);bad["source"]["inode"]+=1
            with self.assertRaises(Hold):im.financial_manifest(bad,**kwargs(bad))
            bad=copy.deepcopy(m);bad["source_sha256"]=digest(b"other")
            with self.assertRaises(Hold):im.verify_financial_reconstruction(f.fileno(),bad,**kwargs(bad))
            bad=copy.deepcopy(m);bad["chunks"][0]["plain_sha256"]=digest(b"def")
            with self.assertRaises(Hold):im.verify_financial_reconstruction(f.fileno(),bad,**kwargs(bad))
            f.seek(0);f.write(b"defabc");f.flush()
            with self.assertRaises(Hold):im.verify_financial_reconstruction(f.fileno(),m,**kwargs(m))
    def test_financial_receipt_correlation_requires_exact_native_domain(self):
        import json
        from settlement_c06_checkpoint_rehearsal import canonical
        source=dict(device=1,inode=2,uid=0,gid=0,mode=0o600,bytes=3,
                    allocated_bytes=512,mtime_ns=1,ctime_ns=1)
        h=digest(b"abc");plan=digest(b"plan");receiver=digest(b"intel")
        chunk=dict(index=0,offset=0,plain_bytes=3,cipher_bytes=19,
                   plain_sha256=h,cipher_sha256=digest(b"cipher"))
        m=dict(schema="wolo.financial.image-continuation.v1",purpose=im.PURPOSE,
               plan_sha256=plan,source=source,source_sha256=h,chunks=[chunk])
        mh=digest(canonical(m))
        receipt=dict(schema="wolo.financial.image-chunk-ack.v1",purpose=im.PURPOSE,
            plan_sha256=plan,manifest_sha256=mh,source_sha256=h,
            receiver_identity_sha256=receiver,index=0,offset=0,
            ciphertext_sha256=chunk["cipher_sha256"],ciphertext_bytes=19,
            status="CIPHERTEXT_DURABLE_READBACK_VERIFIED_NOT_RESTORED",
            retirement_authorized=False)
        def check(r,verifier=json.loads):
            raw=canonical(r)
            return im.financial_chunk_receipt(raw,m,expected_plan=plan,
                expected_source=source,expected_manifest_sha=mh,max_chunk_bytes=3,
                expected_index=0,expected_receipt_sha=digest(raw),
                expected_receiver=receiver,verify_native_receipt=verifier)
        proof=check(receipt)
        self.assertFalse(proof["resume_authorized"])
        self.assertFalse(proof["independent_restore"])
        for key,value in (("purpose","SITE_RUNTIME"),("index",False),
                ("manifest_sha256",h),("retirement_authorized",True),
                ("ciphertext_sha256",h),("receiver_identity_sha256",h)):
            with self.assertRaises(Hold):check(dict(receipt,**{key:value}))
        with self.assertRaises(Hold):check(receipt,lambda raw:None)
if __name__=="__main__":unittest.main()
