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
            m={"schema":"wolo.financial.image-source-manifest.v1","purpose":im.PURPOSE,
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
        m=dict(schema="wolo.financial.image-source-manifest.v1",purpose=im.PURPOSE,
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
    def test_incremental_prefix_and_exact_transfer_seal(self):
        from settlement_c06_checkpoint_rehearsal import canonical
        import hmac
        # Disposable fixture authentication; no production key or route.
        def mac(raw):return hmac.digest(b"fixture-only-key",raw,"sha256")
        def sha(v):return digest(canonical(v))
        initial=dict(schema="wolo.financial.image-prefix-identity.v1",purpose=im.PURPOSE,
            campaign="fixture",plan_sha256=digest(b"plan"),
            source=dict(device=1,inode=2,uid=0,gid=0,mode=0o600,bytes=6,
                        allocated_bytes=512,mtime_ns=1,ctime_ns=1),
            max_chunk_bytes=3,recipient_sha256=digest(b"recipient"),
            receiver_identity_sha256=digest(b"receiver"))
        ih=sha(initial);signed={canonical(initial):mac(canonical(initial))}
        def verify(raw):return raw in signed and hmac.compare_digest(signed[raw],mac(raw))
        def sign(v):signed[canonical(v)]=mac(canonical(v))
        receipts=[];tip=ih
        for i,data in enumerate((b"abc",b"def")):
            c=dict(index=i,offset=3*i,plain_bytes=3,cipher_bytes=19,
                   plain_sha256=digest(data),cipher_sha256=digest(b"cipher"+data))
            r=dict(schema="wolo.financial.image-prefix-readback.v1",initial_sha256=ih,
                   previous=tip,receiver_identity_sha256=initial["receiver_identity_sha256"],
                   chunk=c,status="CIPHERTEXT_DURABLE_READBACK_VERIFIED_NOT_RESTORED",
                   retirement_authorized=False)
            sign(r);receipts.append(r);tip=sha(r)
        kw=dict(expected_initial_sha=ih,verify_initial=verify,verify_receipt=verify)
        self.assertEqual(im.financial_prefix(initial,[],**kw)["verified_plain_bytes"],0)
        self.assertEqual(im.financial_prefix(initial,receipts[:1],**kw)["verified_plain_bytes"],3)
        p=im.financial_prefix(initial,receipts,**kw)
        self.assertTrue(p["coverage_complete"]);self.assertFalse(p["resume_authorized"])
        for bad in ([receipts[1]], [receipts[0],receipts[0]],
                    [receipts[0],dict(receipts[1],retirement_authorized=True)]):
            with self.assertRaises(Hold):im.financial_prefix(initial,bad,**kw)
        bad=dict(receipts[1],chunk=dict(receipts[1]["chunk"],cipher_sha256=digest(b"other")))
        with self.assertRaises(Hold):im.financial_prefix(initial,[receipts[0],bad],**kw)
        source_sha=digest(b"abcdef")
        expected=dict(schema="wolo.financial.image-continuation.v1",
            identity=dict(purpose="FULL_IMAGE_EXACT",campaign="fixture",
                plan_sha256=initial["plan_sha256"],source_identity_sha256=sha(initial["source"]),
                source_sha256=source_sha,source_bytes=6,max_chunk_bytes=3,
                recipient_sha256=initial["recipient_sha256"]),chunks=p["chunks"])
        seal=dict(schema="wolo.financial.image-prefix-seal.v1",initial_sha256=ih,
                  tip_sha256=tip,manifest_sha256=sha(expected),source_sha256=source_sha)
        sign(seal)
        args=dict(**kw,source_sha256=source_sha,expected_seal_sha=sha(seal),verify_seal=verify)
        result=im.seal_transfer_manifest(initial,receipts,**args)
        self.assertEqual(result["manifest"],expected)
        self.assertFalse(result["independent_restore"])
        with self.assertRaises(Hold):im.seal_transfer_manifest(initial,receipts[:1],**args)
        with self.assertRaises(Hold):im.seal_transfer_manifest(initial,receipts,**(args|{"source_sha256":digest(b"wrong")}))
    def test_single_target_reconstruction_and_failed_decrypt(self):
        from settlement_c06_checkpoint_rehearsal import canonical
        from contextlib import contextmanager
        pieces=[b"a"*(im.BLOCK+7),b"tail"]
        source=dict(device=1,inode=2,uid=0,gid=0,mode=0o600,
            bytes=sum(map(len,pieces)),allocated_bytes=2*im.BLOCK,mtime_ns=1,ctime_ns=1)
        plan=digest(b"plan");offset=0;chunks=[]
        for i,piece in enumerate(pieces):
            chunks.append(dict(index=i,offset=offset,plain_bytes=len(piece),
                cipher_bytes=len(piece)+100,plain_sha256=digest(piece),
                cipher_sha256=digest(b"cipher"+piece)))
            offset+=len(piece)
        m=dict(schema="wolo.financial.image-source-manifest.v1",purpose=im.PURPOSE,
               plan_sha256=plan,source=source,source_sha256=digest(b"".join(pieces)),
               chunks=chunks)
        kw=dict(expected_plan=plan,expected_source=source,
                expected_manifest_sha=digest(canonical(m)),max_chunk_bytes=im.BLOCK+7)
        @contextmanager
        def open_chunk(c):
            yield io.BytesIO(pieces[c["index"]])
        with tempfile.NamedTemporaryFile() as target:
            proof=im.reconstruct_financial_image(target.fileno(),m,
                open_verified_plaintext=open_chunk,**kw)
            self.assertEqual(proof["sha256"],m["source_sha256"])
            self.assertTrue(proof["single_target"])
            self.assertFalse(proof["independent_host_authenticated"])
            with self.assertRaises(Hold):im.reconstruct_financial_image(
                target.fileno(),m,open_verified_plaintext=open_chunk,**kw)
        @contextmanager
        def failed_tag(c):
            yield io.BytesIO(pieces[c["index"]])
            raise Hold("fixture decrypt authentication failed")
        with tempfile.NamedTemporaryFile() as target:
            with self.assertRaises(Hold):im.reconstruct_financial_image(
                target.fileno(),m,open_verified_plaintext=failed_tag,**kw)
            self.assertEqual(os.fstat(target.fileno()).st_size,len(pieces[0]))
            with self.assertRaises(Hold):im.reconstruct_financial_image(
                target.fileno(),m,open_verified_plaintext=open_chunk,**kw)
        @contextmanager
        def trailing(c):
            yield io.BytesIO(pieces[c["index"]]+b"extra")
        with tempfile.NamedTemporaryFile() as target:
            with self.assertRaises(Hold):im.reconstruct_financial_image(
                target.fileno(),m,open_verified_plaintext=trailing,**kw)
    def test_sealed_recovery_composition_requires_exact_native_admission(self):
        from settlement_c06_checkpoint_rehearsal import canonical
        from contextlib import contextmanager
        import hmac
        key=b"disposable-fixture-only"
        def sha(x):return digest(canonical(x))
        signed={}
        def sign(x):signed[canonical(x)]=hmac.digest(key,canonical(x),"sha256")
        def verify(raw):
            return raw in signed and hmac.compare_digest(signed[raw],hmac.digest(key,raw,"sha256"))
        data=[b"abc",b"def"];source=dict(device=1,inode=2,uid=0,gid=0,
            mode=0o600,bytes=6,allocated_bytes=512,mtime_ns=1,ctime_ns=1)
        initial=dict(schema="wolo.financial.image-prefix-identity.v1",purpose=im.PURPOSE,
            campaign="fixture-sealed",plan_sha256=digest(b"plan"),source=source,
            max_chunk_bytes=3,recipient_sha256=digest(b"recipient"),
            receiver_identity_sha256=digest(b"receiver"))
        sign(initial);ih=sha(initial);tip=ih;receipts=[];chunks=[]
        for i,piece in enumerate(data):
            c=dict(index=i,offset=i*3,plain_bytes=3,cipher_bytes=19,
                plain_sha256=digest(piece),cipher_sha256=digest(b"cipher"+piece))
            r=dict(schema="wolo.financial.image-prefix-readback.v1",initial_sha256=ih,
                previous=tip,receiver_identity_sha256=initial["receiver_identity_sha256"],
                chunk=c,status="CIPHERTEXT_DURABLE_READBACK_VERIFIED_NOT_RESTORED",
                retirement_authorized=False)
            sign(r);tip=sha(r);receipts.append(r);chunks.append(c)
        manifest=dict(schema="wolo.financial.image-continuation.v1",
            identity=dict(purpose="FULL_IMAGE_EXACT",campaign=initial["campaign"],
                plan_sha256=initial["plan_sha256"],source_identity_sha256=sha(source),
                source_sha256=digest(b"".join(data)),source_bytes=6,max_chunk_bytes=3,
                recipient_sha256=initial["recipient_sha256"]),chunks=chunks)
        seal=dict(schema="wolo.financial.image-prefix-seal.v1",initial_sha256=ih,
            tip_sha256=tip,manifest_sha256=sha(manifest),
            source_sha256=manifest["identity"]["source_sha256"])
        sign(seal);calls=[];opened=[]
        @contextmanager
        def open_chunk(c):
            opened.append(c["index"]);yield io.BytesIO(data[c["index"]])
        def admit(raw,fd):
            self.assertEqual(os.fstat(fd).st_size,0)
            calls.append(raw);return True
        kw=dict(expected_initial_sha=ih,expected_seal_sha=sha(seal),
            expected_plan=initial["plan_sha256"],expected_source=source,
            expected_receiver=initial["receiver_identity_sha256"],
            expected_recipient=initial["recipient_sha256"],verify_initial=verify,
            verify_receipt=verify,verify_seal=verify,verify_reconstruction_admission=admit,
            verify_lease=lambda:True,open_verified_plaintext=open_chunk)
        with tempfile.NamedTemporaryFile() as f:
            proof=im.reconstruct_sealed_financial_image(f.fileno(),initial,receipts,manifest,seal,**kw)
            self.assertEqual(proof["sha256"],seal["source_sha256"])
            self.assertEqual(proof["sealed_binding"]["wire_manifest_sha256"],sha(manifest))
            self.assertEqual(proof["sealed_binding"]["seal_sha256"],sha(seal))
            self.assertEqual(calls,[canonical(proof["sealed_binding"])])
            self.assertEqual(opened,[0,1]);self.assertFalse(proof["independent_host_authenticated"])
        for changes in ({"verify_reconstruction_admission":lambda *_:None},
                        {"verify_lease":lambda:False},
                        {"expected_receiver":digest(b"wrong receiver")},
                        {"verify_seal":lambda _:False}):
            with tempfile.NamedTemporaryFile() as f:
                with self.assertRaises(Hold):im.reconstruct_sealed_financial_image(
                    f.fileno(),initial,receipts,manifest,seal,**(kw|changes))
                self.assertEqual(os.fstat(f.fileno()).st_size,0)
        with tempfile.NamedTemporaryFile() as f:
            with self.assertRaises(Hold):im.reconstruct_sealed_financial_image(
                f.fileno(),initial,receipts,dict(manifest,chunks=list(reversed(chunks))),seal,**kw)
            self.assertEqual(os.fstat(f.fileno()).st_size,0)
        self.assertEqual(opened,[0,1])
if __name__=="__main__":unittest.main()
