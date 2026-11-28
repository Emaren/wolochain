"""Source-review-only campaign assembly; no live CLI or DB connection.
Separate native owner admission is mandatory for any actual protected copy.
"""
import csv,hashlib,io,json,os,re,stat,uuid
from delivery import copy_qualified,free,need,shape

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def digest(value):return hashlib.sha256(value).hexdigest()
def plan_campaign(census_raw,qualified_raw,*,census_pin,qualified_pin,target_identity,reserve):
    need(digest(census_raw)==census_pin and digest(qualified_raw)==qualified_pin,'RECEIPT_PIN')
    census=json.loads(census_raw);qualified=json.loads(qualified_raw)
    need(census['schema']=='aoe2war.clan.legacy-census.v1' and census['database']=='aoe2hd_db' and census['read_only'] is True,'CENSUS_SCOPE')
    need(qualified['schema']=='aoe2war.clan.legacy-content-qualification.v1' and qualified['census_sha256']==census_pin and qualified['media_copies'] is False and qualified['database_mutation'] is False,'QUALIFICATION_SCOPE')
    rows={x['row']['attachment_id']:x for x in census['rows'] if x['outcome']=='metadata_and_magic_match'}
    need(len(rows)==625 and len(qualified['results'])==625 and len({x['attachment_id'] for x in qualified['results']})==625,'CANDIDATE_COUNT')
    items=[]
    for q in qualified['results']:
        x=rows[q['attachment_id']];r=x['row']
        if q['outcome']!='CONTENT_QUALIFIED':continue
        need(q['file_identity']==x['file_identity'] and q['bytes']==r['size_bytes'] and re.fullmatch('[0-9a-f]{64}',q['sha256']) is not None,'CONTENT_BINDING')
        ext={'image/png':'png','image/jpeg':'jpg','image/webp':'webp'}[r['mime_type']]
        items.append({'row':r,'identity':q['file_identity'],'digest':q['sha256'],'protected_ref':'file:v1:clan-'+uuid.uuid4().hex+'.'+ext})
    need(len(items)==624 and sum(x['row']['size_bytes'] for x in items)==642902575,'QUALIFIED_COHORT')
    need(len({x['protected_ref'] for x in items})==624 and len({x['row']['message_id'] for x in items})==624,'PLAN_COLLISION')
    return {'schema':'aoe2war.clan.legacy-delivery-plan.v1','census_sha256':census_pin,'qualified_sha256':qualified_pin,'target_identity':list(target_identity),'reserve':reserve,'items':items,'production_admitted':False}

def durable_new(directory_fd,name,content):
    need(re.fullmatch(r'[A-Za-z0-9.-]{1,100}',name) is not None and name not in ('.','..'),'RECEIPT_NAME')
    fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory_fd)
    with os.fdopen(fd,'wb') as f:f.write(canonical(content));f.flush();os.fsync(f.fileno())
    os.fsync(directory_fd)

def copy_campaign(plan,source_fd,target_fd,journal_fd,*,source_uid,check_admitted_scope):
    """Caller supplies an actual native admission verifier; no default or CLI.
    On partial failure, leave every durable plan/prepared/verified receipt and
    file intact; never retry this fresh-only campaign or guess commit outcome.
    """
    need(plan['schema']=='aoe2war.clan.legacy-delivery-plan.v1' and plan['production_admitted'] is False,'PLAN_SCOPE')
    pin=digest(canonical(plan));check_admitted_scope(pin)
    j=os.fstat(journal_fd);need(stat.S_ISDIR(j.st_mode) and stat.S_IMODE(j.st_mode)==0o700 and j.st_uid==os.geteuid(),'PRIVATE_JOURNAL')
    items=plan['items'];need(len(items)==624 and sum(x['row']['size_bytes'] for x in items)==642902575,'EXACT_CAMPAIGN')
    need(shape(os.fstat(target_fd))==tuple(plan['target_identity']),'TARGET_IDENTITY')
    need(free(target_fd)>=plan['reserve']+sum(x['row']['size_bytes']+65536 for x in items),'FULL_CAMPAIGN_RESERVE')
    durable_new(journal_fd,'plan.json',plan);results=[]
    for item in items:
        aid=item['row']['attachment_id'];check_admitted_scope(pin)
        receipt=copy_qualified(source_fd,target_fd,**item,source_uid=source_uid,target_identity=tuple(plan['target_identity']),reserve=plan['reserve'],prepared=lambda p:durable_new(journal_fd,f'{aid}.prepared.json',p))
        durable_new(journal_fd,f'{aid}.verified.json',receipt);results.append(receipt)
    done={'schema':'aoe2war.clan.legacy-delivery-receipts.v1','plan_sha256':pin,'receipts':results,'database_admitted':False}
    durable_new(journal_fd,'copies-verified.json',done);return done

def batch_csv(plan,delivery):
    """Return CSV data for fixed COPY pg_temp.clan_legacy_batch FROM STDIN.
    Never interpolate media values into SQL. Native controller must re-read
    filesystem inode/hash/ownership and reconcile the journal before use.
    """
    need(delivery['schema']=='aoe2war.clan.legacy-delivery-receipts.v1' and delivery['plan_sha256']==digest(canonical(plan)) and delivery['database_admitted'] is False,'DELIVERY_PIN')
    items=plan['items'];receipts=delivery['receipts'];need(len(items)==len(receipts)==624,'DELIVERY_COUNT')
    stream=io.StringIO(newline='');writer=csv.writer(stream,lineterminator='\n')
    for x,r in zip(items,receipts):
        row=x['row'];expected=(row['attachment_id'],row['message_id'],row['storage_ref'],x['protected_ref'],row['mime_type'],row['size_bytes'],x['digest'])
        actual=tuple(r[k] for k in ('attachment_id','message_id','original_ref','protected_ref','mime','size_bytes','content_sha256'))
        need(actual==expected and r['status']=='PRIVATE_COPY_VERIFIED_NOT_ADMITTED' and r['source_identity']==x['identity'],'DELIVERY_PARITY')
        writer.writerow(expected)
    return stream.getvalue()
