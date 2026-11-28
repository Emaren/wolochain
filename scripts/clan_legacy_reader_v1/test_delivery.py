import os,tempfile,pathlib,hashlib,unittest
from delivery import copy_qualified,shape,DIR
class Delivery(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name);self.source=self.root/'src';self.dest=self.root/'dst';self.source.mkdir(mode=0o750);self.dest.mkdir(mode=0o750)
        self.name='12345678-1234-1234-1234-123456789abc.png';self.file=self.source/'2026'/'11'/self.name;self.file.parent.mkdir(parents=True);self.raw=b'fixture bytes';self.file.write_bytes(self.raw)
        self.sf=os.open(self.source,DIR);self.df=os.open(self.dest,DIR);self.addCleanup(os.close,self.sf);self.addCleanup(os.close,self.df)
        a=self.file.stat();self.ident={'device':a.st_dev,'inode':a.st_ino,'bytes':a.st_size,'mtime_ns':a.st_mtime_ns,'ctime_ns':a.st_ctime_ns};self.ref='file:v1:clan-'+'a'*32+'.png';self.row={'attachment_id':1,'message_id':2,'storage_ref':'file:v1:clan-hall/2026/11/'+self.name,'mime_type':'image/png','size_bytes':len(self.raw)};self.plans=[]
    def run_copy(self,**over):
        args=dict(row=self.row,identity=self.ident,digest=hashlib.sha256(self.raw).hexdigest(),protected_ref=self.ref,source_uid=os.getuid(),target_identity=shape(os.fstat(self.df)),reserve=0,prepared=self.plans.append);args.update(over);return copy_qualified(self.sf,self.df,**args)
    def test_copy_preserves_original(self):
        r=self.run_copy();self.assertEqual(r['status'],'PRIVATE_COPY_VERIFIED_NOT_ADMITTED');self.assertEqual(self.file.read_bytes(),self.raw);self.assertEqual((self.dest/self.ref[8:]).read_bytes(),self.raw);self.assertEqual(len(self.plans),1)
    def test_collision_no_overwrite(self):
        p=self.dest/self.ref[8:];p.write_bytes(b'existing');self.assertRaises(FileExistsError,self.run_copy);self.assertEqual(p.read_bytes(),b'existing')
    def test_wrong_hash(self):
        self.assertRaises(ValueError,self.run_copy,digest='0'*64);self.assertFalse(self.plans);self.assertFalse(list(self.dest.iterdir()))
    def test_changed_source(self):
        self.file.write_bytes(b'changed bytes');self.assertRaises(ValueError,self.run_copy)
    def test_traversal(self):
        self.row['storage_ref']='file:v1:clan-hall/2026/11/../../x.png';self.assertRaises(ValueError,self.run_copy)
    def test_symlink(self):
        self.file.unlink();self.file.symlink_to('/dev/null');self.assertRaises(OSError,self.run_copy)
    def test_reserve(self):self.assertRaises(ValueError,self.run_copy,reserve=10**18)
    def test_receipt_failure_no_write(self):
        def hold(p):raise RuntimeError('receipt failed')
        self.assertRaises(RuntimeError,self.run_copy,prepared=hold);self.assertFalse(list(self.dest.iterdir()))
if __name__=='__main__':unittest.main()
