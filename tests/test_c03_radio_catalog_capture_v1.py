import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

path = Path(__file__).resolve().parents[1] / "scripts/c03_radio_catalog_capture_v1.py"
spec = importlib.util.spec_from_file_location("radio_capture", path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def sample(db="aoe2hd_db"):
    return {
        "RADIO_CATALOG_META": {"database": db, "session_user": "postgres",
            "current_user": "postgres", "read_only": "on", "server_version": "16.10",
            "snapshot": "1:2:", "captured_at": "2026-11-25T00:00:00Z"},
        "RADIO_CATALOG": {"relations": [{"schema_name": a, "relation_name": b}
                                      for a,b in sorted(m.TARGETS)]},
        "FINAL_NONAUTHORIZATION": {"metadata_only": True, "mutations": False,
            "production_admitted": False, "dynamic_dependency_proof": False,
            "rights_proven": False, "funding": "DENIED"},
    }

def encode(rows):
    return ("\n".join(k + "\t" + json.dumps(v) for k,v in rows.items()) + "\n").encode()

class RadioCaptureTests(unittest.TestCase):
    def test_exact(self):
        for db in m.DATABASES:
            self.assertEqual(m.validate(encode(sample(db)),db), sample(db))
    def test_wrong_db(self):
        with self.assertRaises(ValueError): m.validate(encode(sample()),"aoe2de_db")
    def test_writable(self):
        d=sample();d["RADIO_CATALOG_META"]["read_only"]="off"
        with self.assertRaises(ValueError): m.validate(encode(d),"aoe2hd_db")
    def test_over_budget(self):
        d=sample();d["RADIO_CATALOG_OVER_BUDGET"]=d.pop("RADIO_CATALOG")
        with self.assertRaises(ValueError): m.validate(encode(d),"aoe2hd_db")
    def test_missing(self):
        d=sample();d["RADIO_CATALOG"]["relations"].pop()
        with self.assertRaises(ValueError): m.validate(encode(d),"aoe2hd_db")
    def test_finance(self):
        d=sample();d["FINAL_NONAUTHORIZATION"]["funding"]="ALLOWED"
        with self.assertRaises(ValueError): m.validate(encode(d),"aoe2hd_db")
    def test_duplicate(self):
        d=encode(sample()).replace(b'"database":',b'"database":"wrong","database":',1)
        with self.assertRaises(ValueError): m.validate(d,"aoe2hd_db")
    def test_bounded(self):
        p=subprocess.Popen([sys.executable,"-c","print('x'*10000)"],stdout=subprocess.PIPE,start_new_session=True)
        with self.assertRaises(ValueError): m.bounded_stdout(p,cap=100,seconds=3)
    def test_timeout(self):
        p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(5)"],stdout=subprocess.PIPE,start_new_session=True)
        with self.assertRaises(ValueError): m.bounded_stdout(p,seconds=.1)
    def test_exit(self):
        p=subprocess.Popen([sys.executable,"-c","raise SystemExit(1)"],stdout=subprocess.PIPE,start_new_session=True)
        with self.assertRaises(ValueError): m.bounded_stdout(p,seconds=3)
if __name__=="__main__":
    unittest.main()
