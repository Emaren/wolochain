import unittest,json,hashlib,tempfile,os,pathlib,csv,io
from campaign import plan_campaign,batch_csv,canonical,digest,durable_new
class Campaign(unittest.TestCase):
    def setup_fixture(self):
        rows=[];q=[]
        for i in range(625):
            size=1030000 if i<623 else 642902575-623*1030000 if i==623 else 1291246
            identity={'device':1,'inode':i+1,'bytes':size,'mtime_ns':2,'ctime_ns':3}
            r={'attachment_id':i+1,'message_id':i+1000,'storage_ref':f'file:v1:clan-hall/2026/11/{i:08x}-1234-1234-1234-123456789abc.png','mime_type':'image/png','size_bytes':size}
            rows.append({'row':r,'outcome':'metadata_and_magic_match','file_identity':identity})
            q.append({'attachment_id':i+1,'outcome':'CONTENT_QUALIFIED' if i<624 else 'HOLD','bytes':size,'file_identity':identity,'sha256':'a'*64})
        self.census=canonical({'schema':'aoe2war.clan.legacy-census.v1','database':'aoe2hd_db','read_only':True,'rows':rows})
        self.qualified=canonical({'schema':'aoe2war.clan.legacy-content-qualification.v1','census_sha256':digest(self.census),'media_copies':False,'database_mutation':False,'results':q})
    def plan(self,**over):
        args={'census_pin':digest(self.census),'qualified_pin':digest(self.qualified),'target_identity':(1,2,3,4,0o750),'reserve':30000000000};args.update(over);return plan_campaign(self.census,self.qualified,**args)
    def setUp(self):self.setup_fixture()
    def delivery(self,p):
        rs=[]
        for x in p['items']:
            r=x['row'];rs.append({'attachment_id':r['attachment_id'],'message_id':r['message_id'],'original_ref':r['storage_ref'],'protected_ref':x['protected_ref'],'mime':r['mime_type'],'size_bytes':r['size_bytes'],'content_sha256':x['digest'],'source_identity':x['identity'],'status':'PRIVATE_COPY_VERIFIED_NOT_ADMITTED'})
        return {'schema':'aoe2war.clan.legacy-delivery-receipts.v1','plan_sha256':digest(canonical(p)),'receipts':rs,'database_admitted':False}
    def test_exact_plan(self):
        p=self.plan();self.assertEqual(len(p['items']),624);self.assertEqual(sum(x['row']['size_bytes'] for x in p['items']),642902575);self.assertFalse(p['production_admitted'])
    def test_receipt_pin(self):self.assertRaises(ValueError,self.plan,qualified_pin='0'*64)
    def test_batch_csv(self):
        p=self.plan();d=self.delivery(p);self.assertEqual(len(list(csv.reader(io.StringIO(batch_csv(p,d))))),624)
    def test_changed_receipt(self):
        p=self.plan();d=self.delivery(p);d['receipts'][0]['content_sha256']='0'*64;self.assertRaises(ValueError,batch_csv,p,d)
    def test_incomplete_receipt(self):
        p=self.plan();d=self.delivery(p);d['receipts'].pop();self.assertRaises(ValueError,batch_csv,p,d)
    def test_durable_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY)
            try:
                durable_new(fd,'fixture.json',{'x':1});self.assertRaises(FileExistsError,durable_new,fd,'fixture.json',{'x':2});self.assertEqual(json.loads((pathlib.Path(d)/'fixture.json').read_text()),{'x':1})
            finally:os.close(fd)
if __name__=='__main__':unittest.main()
