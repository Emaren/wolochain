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
if __name__=="__main__":unittest.main()
