import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import settlement_c06_native_pg_checkpoint as p
from settlement_c06_checkpoint_rehearsal import Hold

RAW=b"""Database system identifier: 73123456789
Database cluster state: shut down
Latest checkpoint location: 0/2000028
Latest checkpoint's REDO location: 0/2000028
Latest checkpoint's REDO WAL file: 000000010000000000000002
Latest checkpoint's TimeLineID: 1
Bytes per WAL segment: 16777216
"""
class NativePg(unittest.TestCase):
    def control(self):return p.parse_control(RAW,"73123456789")
    def test_control(self):
        self.assertEqual(self.control()["redo_wal"],"000000010000000000000002")
    def test_drift(self):
        for raw in (RAW.replace(b"shut down",b"in production"),
                    RAW.replace(b"000000002",b"000000003"),
                    RAW+b"Database cluster state: shut down\n",
                    RAW.replace(b"16777216",b"17"),
                    RAW.replace(b"73123456789",b"73123456780")):
            with self.subTest(raw=raw),self.assertRaises(Hold):
                p.parse_control(raw,"73123456789")
    def test_tree(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/"PG_VERSION").write_text("16\n")
            for n in ("pg_tblspc","pg_twophase","global","pg_wal"):(root/n).mkdir()
            (root/"global/pg_control").write_bytes(b"synthetic")
            w=root/"pg_wal"/self.control()["redo_wal"]
            with w.open("wb") as f:f.truncate(16777216)
            fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
            try:
                self.assertEqual(len(p.inspect_tree(fd,self.control())),64)
                for n in ("postmaster.pid","pg_twophase/prepared","pg_tblspc/link"):
                    f=root/n;f.touch()
                    with self.assertRaises(Hold):p.inspect_tree(fd,self.control())
                    f.unlink()
                w.unlink();w.symlink_to(root/"global/pg_control")
                with self.assertRaises(Hold):p.inspect_tree(fd,self.control())
            finally:os.close(fd)
if __name__=="__main__":unittest.main()
