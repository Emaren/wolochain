import dataclasses, json, os, copy, stat, time
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pathlib import Path
import pytest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from c03_durable_admission import (Preimage, Witness, Journal, Hold, plan,
    verify_inverse, verify_transition_proof, REQUIRED_STEPS, canonical, digest,
    ORIGINAL_BARRIER_SHA256, ISSUER_ROLES, PROOF_SCHEMA)

# These keys are deliberately PUBLIC TEST FIXTURES, NEVER production trust.
TEST_PRIVATE={role:Ed25519PrivateKey.from_private_bytes(bytes([idx])*32)
              for idx,role in enumerate(ISSUER_ROLES.values(),start=1)}
TRUST={role:{'role':role,'public_key':key.public_key().public_bytes(
    serialization.Encoding.Raw,serialization.PublicFormat.Raw)}
       for role,key in TEST_PRIVATE.items()}

def J(path, trust=None):
    return Journal(path, TRUST if trust is None else trust)

def signed(j, state, h, *, event=None, issuer=None, role=None, seq=None, prev=None,
           exp=None, issued=None, nonce=None, original=None, evidence=None):
    use_role=role or ISSUER_ROLES.get(state,'owner-outage')
    use_issuer=issuer or use_role
    now=int(time.time())
    issued=issued if issued is not None else now-5
    exp=exp if exp is not None else now+120
    event=event if event is not None else 'PREPARE'
    body={'event_sha256':digest(event.encode('ascii')),'schema':PROOF_SCHEMA,'state':state,'role':use_role,'issuer':use_issuer,
          'preimage_sha256':h,'journal_sequence':seq if seq is not None else j.seq+1,
          'previous_hash':prev if prev is not None else j.head,
          'issued_at':issued,'expires_at':exp,'nonce_sha256':nonce or 'f'*64,
          'evidence_sha256':evidence or 'e'*64,
          'original_preimage_sha256':original or h}
    return {'body':body,'signature_hex':TEST_PRIVATE[use_role].sign(canonical(body)).hex()}

def adv(j,state,event,h,**kwargs):
    return j.write(state,event,h,proof=signed(j,state,h,event=event,**kwargs))

H='a'*64

def pre(**changes):
    fields={f.name:(ORIGINAL_BARRIER_SHA256 if f.name=='offline_barrier_sha256' else H)
            for f in dataclasses.fields(Preimage) if f.name.endswith('_sha256')}
    fields.update(cluster_name='16/main', cluster_device=2049,cluster_inode=781,
                  data_path='/var/lib/postgresql/16/main')
    fields.update(changes)
    return Preimage(**fields)

def wit(**changes):
    fields={f.name:True for f in dataclasses.fields(Witness)}
    fields.update(changes)
    return Witness(**fields)

def test_good_source_only_no_executor():
    p=plan(pre(),wit(),REQUIRED_STEPS)
    assert p['status']=='SOURCE_ONLY_NO_ACTUATOR' and p['financial_gate']=='C03_OPEN'

@pytest.mark.parametrize('bad', [
    {'cluster_name':'15/main'}, {'cluster_device':0}, {'cluster_inode':0},
    {'data_path':'/'}, {'data_path':'/var/lib/postgresql'},
    {'data_path':'/var/lib/postgresql/../other'},
    {'offline_barrier_sha256':H}, {'auto_conf_sha256':'x'},
    {'sequences_manifest_sha256':''}, {'poolers_manifest_sha256':'!'},
])
def test_wrong_identity_or_unpinned_source(bad):
    with pytest.raises(Hold): plan(pre(**bad),wit(),REQUIRED_STEPS)

@pytest.mark.parametrize('missing', [f.name for f in dataclasses.fields(Witness)])
def test_each_omitted_fence_predicate_blocks(missing):
    with pytest.raises(Hold,match='UNACCEPTED_PHYSICAL_PREDICATES'):
        plan(pre(),wit(**{missing:False}),REQUIRED_STEPS)

@pytest.mark.parametrize('order',[
    REQUIRED_STEPS[:-1], tuple(reversed(REQUIRED_STEPS)),
    REQUIRED_STEPS+('funding',), ('startup_mask',),
])
def test_incomplete_or_reordered_startup_is_refused(order):
    with pytest.raises(Hold,match='C03_STEP_ORDER_OR_COVERAGE_DRIFT'):
        plan(pre(),wit(),order)

def test_intent_crash_fails_closed(tmp_path):
    d=tmp_path/'journal';j=J(d);assert j.state=='HOLD'
    adv(j,'INTENT','PREPARE',H)
    assert J(d).state=='UNKNOWN'
    with pytest.raises(Hold,match='UNKNOWN_REQUIRES_EXTERNAL_HUMAN_RECOVERY'):
        adv(J(d),'FENCED','REPLAY_AFTER_CRASH',H)

def test_unfinished_restore_crash_fails_closed(tmp_path):
    d=tmp_path/'journal';j=J(d)
    adv(j,'INTENT','PREPARE',H);adv(j,'FENCED','SOURCE_ONLY_WITNESS',H)
    adv(j,'RESTORE_INTENT','OWNER_REQUEST_ONLY',H)
    assert J(d).state=='UNKNOWN'
    with pytest.raises(Hold):adv(J(d),'RESTORED','UNSAFE_RESTART',H)

def test_append_only_survives_restart_and_no_auto_release(tmp_path):
    d=tmp_path/'journal';j=J(d)
    adv(j,'INTENT','PREPARE',H);adv(j,'FENCED','WITNESS_ACCEPTED',H)
    j2=J(d);assert j2.state=='FENCED' and j2.seq==2
    with pytest.raises(Hold):adv(j2,'RESTORED','SKIP_SIGNED_INVERSE',H)
    assert sorted(p.name for p in d.iterdir())==['00000001.json','00000002.json']
    adv(j2,'RESTORE_INTENT','OWNER_INTENT_ONLY',H)
    adv(j2,'RESTORED','EXTERNAL_INVERSE_WITNESSED',H)
    assert J(d).state=='RESTORED'

@pytest.mark.parametrize('tamper', ['hash','prev','number','extra','deleted'])
def test_journal_tamper_refused(tmp_path,tamper):
    d=tmp_path/'journal';j=J(d)
    adv(j,'INTENT','PREPARE',H);adv(j,'FENCED','WITNESS',H)
    f=d/'00000002.json'
    if tamper=='extra':(d/'stuff').write_text('no')
    elif tamper=='deleted':(d/'00000001.json').unlink()
    else:
        record=json.loads(f.read_text())
        record[tamper]='b'*64 if tamper!='number' else 99
        f.write_bytes(canonical(record))
    assert J(d).state=='UNKNOWN'

@pytest.mark.parametrize('mode', [0o755,0o777])
def test_insecure_journal_directory_denied(tmp_path,mode):
    d=tmp_path/'journal';d.mkdir();d.chmod(mode)
    with pytest.raises(Hold,match='DIRECTORY_PERMISSIONS'):J(d)

def test_duplicate_transition_cannot_replay(tmp_path):
    j=J(tmp_path/'journal');adv(j,'INTENT','PREPARE',H)
    with pytest.raises(Hold):adv(j,'INTENT','DUPLICATE',H)
    with pytest.raises(FileExistsError):
        # No overwrite even if a caller bypasses state checks in the process.
        os.open(j.directory/'00000001.json',os.O_CREAT|os.O_EXCL|os.O_WRONLY)

def test_inverse_requires_independent_authority_and_exact_preimage():
    old=pre();cur=pre(roles_acl_manifest_sha256='b'*64)
    with pytest.raises(Hold,match='SIGNED_INVERSE'):verify_inverse(old,cur,old,False,True)
    with pytest.raises(Hold,match='WRITERS_NOT_EXCLUDED'):verify_inverse(old,cur,old,True,False)
    with pytest.raises(Hold,match='INVERSE_NOT_EXACT_PREIMAGE'):
        verify_inverse(old,cur,pre(auto_conf_sha256='b'*64),True,True)
    assert verify_inverse(old,cur,old,True,True).startswith('SOURCE_ONLY_')


def test_no_live_executor_exported():
    import inspect, c03_durable_admission as c
    source=inspect.getsource(c)
    for token in ('subprocess','os.system','os.exec','psycopg','psql','systemctl','PGPASSWORD'):
        assert token not in source
    assert c.main.__name__=='main'


def test_same_run_cannot_change_preimage_at_fence(tmp_path):
    j=J(tmp_path/'journal')
    adv(j,'INTENT','PREPARE',H)
    with pytest.raises(Hold,match='PREIMAGE_IDENTITY_CHANGED'):
        adv(j,'FENCED','WRONG_PREIMAGE','b'*64)
    assert J(j.directory).state=='UNKNOWN'


def test_restart_detects_valid_rehashed_illegal_transition(tmp_path):
    j=J(tmp_path/'journal');adv(j,'INTENT','PREPARE',H)
    f=j.directory/'00000001.json';record=json.loads(f.read_text())
    record['state']='RESTORED'
    record['hash']=digest(canonical({k:v for k,v in record.items() if k!='hash'}))
    f.write_bytes(canonical(record))
    assert J(j.directory).state=='UNKNOWN'


def test_restart_detects_valid_rehashed_preimage_change(tmp_path):
    j=J(tmp_path/'journal')
    adv(j,'INTENT','PREPARE',H)
    adv(j,'FENCED','ACCEPTED_WITNESS',H)
    f=j.directory/'00000002.json';r=json.loads(f.read_text())
    r['preimage_sha256']='b'*64
    r['hash']=digest(canonical({k:v for k,v in r.items() if k!='hash'}))
    f.write_bytes(canonical(r))
    assert J(j.directory).state=='UNKNOWN'


def test_restart_rejects_world_readable_record(tmp_path):
    j=J(tmp_path/'journal');adv(j,'INTENT','PREPARE',H)
    (j.directory/'00000001.json').chmod(0o644)
    assert J(j.directory).state=='UNKNOWN'


def test_restart_rejects_foreign_schema_even_rehashed(tmp_path):
    j=J(tmp_path/'journal');adv(j,'INTENT','PREPARE',H)
    f=j.directory/'00000001.json';r=json.loads(f.read_text())
    r['schema']='attacker.schema';r['hash']=digest(canonical({k:v for k,v in r.items() if k!='hash'}))
    f.write_bytes(canonical(r))
    assert J(j.directory).state=='UNKNOWN'

# V2 independent signature / restart hardening. All keys are synthetic fixtures.

def test_unsigned_transition_is_rejected_before_creating_record(tmp_path):
    j=J(tmp_path/'journal')
    with pytest.raises(Hold,match='SIGNED_TRANSITION_REQUIRED'):
        j.write('INTENT','PREPARE',H)
    assert list(j.directory.iterdir())==[]


def test_signed_fence_without_independent_witness_is_rejected(tmp_path):
    j=J(tmp_path/'journal');adv(j,'INTENT','PREPARE',H)
    with pytest.raises(Hold,match='SIGNED_TRANSITION_REQUIRED'):
        j.write('FENCED','WITNESS',H)
    assert J(j.directory).state == 'UNKNOWN' # incomplete INTENT remains held


@pytest.mark.parametrize('field',[
    'state','role','preimage_sha256','journal_sequence', 'previous_hash',
    'evidence_sha256','nonce_sha256','original_preimage_sha256',
    'expires_at','issuer','schema','event_sha256'
])
def test_signature_body_mutation_is_denied_before_commit(tmp_path,field):
    j=J(tmp_path/'journal')
    proof=signed(j,'INTENT',H,event='PREPARE')
    if field in ('expires_at','journal_sequence'):
        proof['body'][field]+=1
    else:
        proof['body'][field] = 'b'*64
    with pytest.raises(Hold):
        j.write('INTENT','PREPARE',H,proof=proof)
    assert J(j.directory).state == 'HOLD'


def test_cross_role_witness_issuer_rejected(tmp_path):
    j=J(tmp_path/'journal');adv(j,'INTENT','PREPARE',H)
    proof=signed(j,'FENCED',H,event='WITNESS',role='owner-outage')
    with pytest.raises(Hold,match='WRONG_DOMAIN_OR_ROLE'):
        j.write('FENCED','WITNESS',H,proof=proof)


def test_same_public_key_cannot_be_owner_and_independent_reviewer(tmp_path):
    trust=copy.deepcopy(TRUST)
    trust['independent-fence-witness']['public_key']=trust['owner-outage']['public_key']
    j=J(tmp_path/'journal',trust)
    proof=signed(j,'INTENT',H,event='PREPARE')
    with pytest.raises(Hold,match='OWNER_WITNESS_KEY_NOT_INDEPENDENT'):
        j.write('INTENT','PREPARE',H,proof=proof)


def test_signed_proof_is_invalid_with_changed_trust_anchor(tmp_path):
    trust=copy.deepcopy(TRUST)
    trust['owner-outage']['public_key']=Ed25519PrivateKey.from_private_bytes(bytes([8])*32).public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    j=J(tmp_path/'journal',trust)
    proof=signed(j,'INTENT',H,event='PREPARE')
    with pytest.raises(Hold,match='SIGNATURE_NOT_VERIFIED'):
        j.write('INTENT','PREPARE',H,proof=proof)


@pytest.mark.parametrize('seconds',[-7200,7200])
def test_expired_or_future_signed_claim_denied(tmp_path,seconds):
    j=J(tmp_path/'journal')
    now=int(time.time())
    proof=signed(j,'INTENT',H,event='PREPARE',issued=now+seconds,exp=now+seconds+100)
    with pytest.raises(Hold,match='EXPIRED_OR_UNBOUNDED'):
        j.write('INTENT','PREPARE',H,proof=proof)


def test_forged_body_after_rehashing_entire_journal_is_detected(tmp_path):
    j=J(tmp_path/'journal');adv(j,'INTENT','PREPARE',H)
    recordfile=j.directory/'00000001.json';rec=json.loads(recordfile.read_text())
    rec['proof']['body']['evidence_sha256']='b'*64
    rec['proof_sha256']=digest(canonical(rec['proof']))
    rec['hash']=digest(canonical({k:v for k,v in rec.items() if k!='hash'}))
    recordfile.write_bytes(canonical(rec))
    assert J(j.directory).state=='UNKNOWN' # signature cannot be recreated from hash alone


def test_unsigned_event_relabel_with_rehashed_journal_is_detected(tmp_path):
    j=J(tmp_path/'journal');adv(j,'INTENT','PREPARE',H)
    recordfile=j.directory/'00000001.json';rec=json.loads(recordfile.read_text())
    rec['event']='ACTIVATE_FUNDS'
    rec['hash']=digest(canonical({k:v for k,v in rec.items() if k!='hash'}))
    recordfile.write_bytes(canonical(rec))
    assert J(j.directory).state=='UNKNOWN' # event bound to proof signature


def test_stale_other_instance_cannot_append_after_intent(tmp_path):
    d=tmp_path/'journal';a=J(d);b=J(d)
    adv(a,'INTENT','PREPARE',H)
    with pytest.raises(Hold,match='JOURNAL_STALE_OR_INTERRUPTED'):
        adv(b,'INTENT','PREPARE',H)
    assert J(d).state=='UNKNOWN'


def test_forked_process_cannot_use_inherited_in_memory_intent(tmp_path,monkeypatch):
    j=J(tmp_path/'journal');adv(j,'INTENT','PREPARE',H)
    original=os.getpid()
    monkeypatch.setattr(os,'getpid',lambda:original+42)
    with pytest.raises(Hold,match='FORKED_CONTROLLER_CANNOT_CONTINUE'):
        adv(j,'FENCED','WITNESS',H)


def test_replay_rejects_missing_signature_and_rehashed_record(tmp_path):
    j=J(tmp_path/'journal');adv(j,'INTENT','PREPARE',H)
    f=j.directory/'00000001.json';r=json.loads(f.read_text());del r['proof']['signature_hex']
    r['proof_sha256']=digest(canonical(r['proof']))
    r['hash']=digest(canonical({k:v for k,v in r.items() if k!='hash'}))
    f.write_bytes(canonical(r))
    assert J(j.directory).state=='UNKNOWN'


def test_replay_missing_trust_cannot_accept_signed_record(tmp_path):
    j=J(tmp_path/'journal');adv(j,'INTENT','PREPARE',H)
    # Without the root-admitted public trust source, the log is not evidence.
    assert J(j.directory,{}).state=='UNKNOWN'


def test_replay_checks_intent_and_fence_signatures(tmp_path):
    j=J(tmp_path/'journal');adv(j,'INTENT','PREPARE',H);adv(j,'FENCED','WITNESS',H)
    assert J(j.directory).state=='FENCED'
    f=j.directory/'00000002.json';r=json.loads(f.read_text())
    r['proof']['signature_hex']='0'*128
    r['proof_sha256']=digest(canonical(r['proof']))
    r['hash']=digest(canonical({k:v for k,v in r.items() if k!='hash'}))
    f.write_bytes(canonical(r))
    assert J(j.directory).state=='UNKNOWN'


def test_cannot_skip_signed_owner_inverse(tmp_path):
    j=J(tmp_path/'journal');adv(j,'INTENT','PREPARE',H);adv(j,'FENCED','WITNESS',H)
    fake=signed(j,'RESTORE_INTENT',H,event='OWNER_INTENT',role='independent-fence-witness')
    with pytest.raises(Hold,match='WRONG_DOMAIN_OR_ROLE'):
        j.write('RESTORE_INTENT','OWNER_INTENT',H,proof=fake)
    assert J(j.directory).state=='FENCED'


def test_explicit_complete_cycle_keeps_restored_state_nonrepeatable(tmp_path):
    j=J(tmp_path/'journal')
    for state,event in [('INTENT','PREPARE'),('FENCED','WITNESS'),
                        ('RESTORE_INTENT','OWNER_INTENT'),('RESTORED','EXACT_INVERSE')]:
        adv(j,state,event,H)
    assert J(j.directory).state=='RESTORED'
    with pytest.raises(Hold,match='UNADMITTED_STATE_TRANSITION'):
        adv(j,'INTENT','RESTART_CAMPAIGN',H)
