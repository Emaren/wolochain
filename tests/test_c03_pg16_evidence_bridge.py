"""Source-only integration checks. Test keys and receipts cannot fund or fence HEL1."""
from pathlib import Path
import sys, json, os, copy, time
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from c03_durable_admission import Journal, Hold, ISSUER_ROLES, PROOF_SCHEMA, canonical, digest
from c03_pg16_evidence_bridge import (EvidenceBoundJournal, validate_receipt,
                                     EXPECTED, TEST_RUNNER_SHA256)

H='d'*64
RAW=(Path(__file__).parent/'fixtures/c03_pg16_disposable_observation.json').read_bytes()
PRIVATE={role:Ed25519PrivateKey.from_private_bytes(bytes([i])*32)
         for i,role in enumerate(ISSUER_ROLES.values(),start=1)}
TRUST={role:{'role':role,'public_key':key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)}
       for role,key in PRIVATE.items()}

def sign(j,state,event='TEST_ONLY',evidence=None,role=None):
    role=role or ISSUER_ROLES[state]
    now=int(time.time())
    body={'event_sha256':digest(event.encode('ascii')),'schema':PROOF_SCHEMA,
          'state':state,'role':role,'issuer':role,'preimage_sha256':H,
          'journal_sequence':j.seq+1,'previous_hash':j.head,
          'issued_at':now-2,'expires_at':now+120,
          'nonce_sha256':'3'*64,'evidence_sha256':evidence or 'a'*64,
          'original_preimage_sha256':H}
    return {'body':body,'signature_hex':PRIVATE[role].sign(canonical(body)).hex()}

def start(tmp_path):
    b=EvidenceBoundJournal(tmp_path/'journal',tmp_path/'evidence',TRUST)
    b.journal.write('INTENT','TEST_ONLY',H,proof=sign(b.journal,'INTENT'))
    assert b.journal.state=='INTENT'
    return b

def fence(b,raw=RAW):
    return b.append_fenced_test_claim('TEST_ONLY',H,
        sign(b.journal,'FENCED',evidence=digest(raw)),raw)

def test_actual_postgres16_receipt_fixture_shape():
    r=validate_receipt(RAW)
    assert r['case_count']==15 and tuple(r['checks'])==EXPECTED
    assert r['tcp_listening'] is False and r['postgres']=='16'
    assert len(TEST_RUNNER_SHA256)==64

def test_signed_physical_test_receipt_bind_and_restart(tmp_path):
    b=start(tmp_path);h=fence(b)
    assert h==digest(RAW) and b.state=='FENCED'
    reloaded=EvidenceBoundJournal(tmp_path/'journal',tmp_path/'evidence',TRUST)
    assert reloaded.state=='FENCED'
    record=json.loads((tmp_path/'journal'/'00000002.json').read_bytes())
    assert record['proof']['body']['evidence_sha256']==h
    assert record['state']=='FENCED'

def test_missing_archive_after_restart_is_unknown(tmp_path):
    b=start(tmp_path);h=fence(b)
    (tmp_path/'evidence'/f'{h}.json').unlink()
    assert EvidenceBoundJournal(tmp_path/'journal',tmp_path/'evidence',TRUST).state=='UNKNOWN'

def test_mutated_evidence_after_restart_is_unknown(tmp_path):
    b=start(tmp_path);h=fence(b)
    p=tmp_path/'evidence'/f'{h}.json'
    raw=p.read_bytes().replace(b'"PASS"',b'"FAIL"')
    p.write_bytes(raw)
    assert EvidenceBoundJournal(tmp_path/'journal',tmp_path/'evidence',TRUST).state=='UNKNOWN'

@pytest.mark.parametrize('bad',[
    b'{}\n',b'{"status":"PASS"}\n',RAW[:-1],
    RAW.replace(b'"PASS"',b'"FAIL"'),
    RAW.replace(b'"postgres": "16"',b'"postgres": "15"'),
    RAW.replace(b'"ephemeral_cluster": true',b'"ephemeral_cluster": false'),
    RAW.replace(b'"tcp_listening": false',b'"tcp_listening": true'),
    RAW.replace(b'"case_count": 15',b'"case_count": 12'),
    RAW.replace(b'"sequence bypass denied"',b'"sequence bypass not tested"'),
    RAW.replace(b'"hba_deny_sha256": ',b'"hba_deny_sha256": "0000", "hba_deny_sha256": '),
])
def test_bad_disposable_postgres_observation_denied(bad):
    with pytest.raises(Hold):validate_receipt(bad)

def test_mismatched_proof_evidence_digest_refused(tmp_path):
    b=start(tmp_path)
    proof=sign(b.journal,'FENCED',evidence='1'*64)
    with pytest.raises(Hold,match='EVIDENCE_NOT_BOUND'):
        b.append_fenced_test_claim('TEST_ONLY',H,proof,RAW)
    assert b.journal.state=='INTENT'
    assert not (tmp_path/'evidence').exists()

def test_bad_or_unsigned_proof_refused_before_receipt_written(tmp_path):
    b=start(tmp_path)
    proof=sign(b.journal,'FENCED',evidence=digest(RAW))
    proof['signature_hex']='0'*128
    with pytest.raises(Hold,match='SIGNATURE_NOT_VERIFIED'):
        b.append_fenced_test_claim('TEST_ONLY',H,proof,RAW)
    assert not (tmp_path/'evidence').exists()

def test_event_relabel_while_signature_valid_refused(tmp_path):
    b=start(tmp_path)
    proof=sign(b.journal,'FENCED',evidence=digest(RAW))
    with pytest.raises(Hold,match='PROOF_EVENT_NOT_BOUND'):
        b.append_fenced_test_claim('FAKE_ACCEPT',H,proof,RAW)
    assert not (tmp_path/'evidence').exists()

def test_wrong_issuer_role_refused(tmp_path):
    b=start(tmp_path)
    proof=sign(b.journal,'FENCED',evidence=digest(RAW),role='owner-outage')
    with pytest.raises(Hold,match='WRONG_DOMAIN_OR_ROLE'):
        b.append_fenced_test_claim('TEST_ONLY',H,proof,RAW)

def test_no_signed_intent_refuses_fence(tmp_path):
    b=EvidenceBoundJournal(tmp_path/'journal',tmp_path/'evidence',TRUST)
    with pytest.raises(Hold,match='PRIOR_SIGNED_INTENT'):
        fence(b)

def test_incomplete_intent_restart_is_unknown(tmp_path):
    start(tmp_path)
    assert EvidenceBoundJournal(tmp_path/'journal',tmp_path/'evidence',TRUST).state=='UNKNOWN'

def test_no_supported_exact_inverse_evidence_fails_closed(tmp_path):
    b=start(tmp_path);fence(b)
    b.journal.write('RESTORE_INTENT','TEST_ONLY',H,
        proof=sign(b.journal,'RESTORE_INTENT'))
    b.journal.write('RESTORED','TEST_ONLY',H,
        proof=sign(b.journal,'RESTORED'))
    # Even a valid signed source-only RESTORED label cannot be promoted to
    # physically restored without a separate exact-inverse PG16 readback.
    assert EvidenceBoundJournal(tmp_path/'journal',tmp_path/'evidence',TRUST).state=='UNKNOWN'

def test_receipt_archive_permissions_insecure_refused(tmp_path):
    b=start(tmp_path);h=fence(b)
    (tmp_path/'evidence'/f'{h}.json').chmod(0o644)
    assert EvidenceBoundJournal(tmp_path/'journal',tmp_path/'evidence',TRUST).state=='UNKNOWN'

def test_no_execution_entrypoint():
    from c03_pg16_evidence_bridge import main
    with pytest.raises(SystemExit,match='SOURCE_ONLY_NO_FINANCIAL_PG_EXECUTOR'):main()


def test_in_memory_signed_journal_removed_after_fence_is_unknown(tmp_path):
    b=start(tmp_path);fence(b)
    assert b.state=='FENCED'
    (tmp_path/'journal'/'00000002.json').unlink()
    assert b.state=='UNKNOWN'


def test_in_memory_signed_record_rehashed_but_proof_invalid_is_unknown(tmp_path):
    b=start(tmp_path);fence(b)
    assert b.state=='FENCED'
    p=tmp_path/'journal'/'00000002.json'
    obj=json.loads(p.read_bytes())
    obj['proof']['body']['evidence_sha256']='a'*64
    obj['proof_sha256']=digest(canonical(obj['proof']))
    obj['hash']=digest(canonical({k:v for k,v in obj.items() if k!='hash'}))
    p.write_bytes(canonical(obj))
    assert b.state=='UNKNOWN'  # cannot trust cached signed FENCED state
    assert EvidenceBoundJournal(tmp_path/'journal',tmp_path/'evidence',TRUST).state=='UNKNOWN'


def test_evidence_archive_replaced_by_symlink_unknown(tmp_path):
    b=start(tmp_path);h=fence(b)
    assert b.state=='FENCED'
    archive=tmp_path/'evidence'
    moved=tmp_path/'evidence-moved'
    archive.rename(moved)
    archive.symlink_to(moved, target_is_directory=True)
    assert b.state=='UNKNOWN'


def test_hash_file_replaced_with_symlink_unknown(tmp_path):
    b=start(tmp_path);h=fence(b)
    p=tmp_path/'evidence'/f'{h}.json'
    renamed=tmp_path/'saved.json'
    p.rename(renamed)
    p.symlink_to(renamed)
    assert b.state=='UNKNOWN'


@pytest.mark.parametrize('mutation',[ 
    lambda b: b.replace(b'"PASS"',b'"FAIL"'),
    lambda b: b.replace(b'"postgres": "16"',b'"postgres": "15"'),
    lambda b: b.replace(b'"case_count": 15',b'"case_count": 14'),
    lambda b: b.replace(b'"tcp_listening": false',b'"tcp_listening": true'),
    lambda b: b.replace(b'"hba_deny_sha256": "',b'"hba_deny_sha256": "0',1),
    lambda b: b.replace(b'"status": "PASS"', b'"status" : "PASS"'),
])
def test_pinned_disposable_fixture_cannot_be_minted_afresh(mutation):
    corrupted=mutation(RAW)
    assert corrupted!=RAW
    with pytest.raises(Hold):
        validate_receipt(corrupted)


def test_signed_fixture_never_authorizes_real_production_fence(tmp_path):
    b=start(tmp_path);fence(b)
    assert b.state=='FENCED'  # only the test journal state
    with pytest.raises(Hold,match='NO_INDEPENDENT_PRODUCTION_PHYSICAL_WITNESS'):
        b.require_production_fence()


def test_production_fence_refuses_before_any_test_observation(tmp_path):
    b=EvidenceBoundJournal(tmp_path/'journal',tmp_path/'evidence',TRUST)
    with pytest.raises(Hold,match='NO_INDEPENDENT_PRODUCTION_PHYSICAL_WITNESS'):
        b.require_production_fence()


def test_production_fence_refuses_on_forged_on_disk_record(tmp_path):
    b=start(tmp_path);fence(b)
    p=tmp_path/'journal'/'00000002.json'
    o=json.loads(p.read_bytes())
    o['proof']['signature_hex']='0'*128
    o['proof_sha256']=digest(canonical(o['proof']))
    o['hash']=digest(canonical({k:v for k,v in o.items() if k!='hash'}))
    p.write_bytes(canonical(o))
    assert b.state=='UNKNOWN'
    with pytest.raises(Hold,match='NO_INDEPENDENT_PRODUCTION_PHYSICAL_WITNESS'):
        b.require_production_fence()


def test_journal_record_symlink_swap_after_lstat_must_be_unknown(tmp_path, monkeypatch):
    """Adversary swaps trusted record after lstat before its read opens path."""
    b=start(tmp_path);fence(b)
    target=tmp_path/'journal'/'00000002.json'
    external=tmp_path/'saved-00000002.json'
    original_lstat=Path.lstat
    original_open=os.open
    done=[False]

    def attack_once():
        if not done[0]:
            done[0]=True
            target.rename(external)
            target.symlink_to(external)

    def swap_after_stat(path, *args, **kwargs):
        info=original_lstat(path,*args,**kwargs)
        if path == target:
            attack_once()
        return info

    def swap_before_fd_open(path, flags, *args, **kwargs):
        if path == '00000002.json' and kwargs.get('dir_fd') is not None:
            attack_once()
        return original_open(path,flags,*args,**kwargs)

    with monkeypatch.context() as p:
        p.setattr(Path,'lstat',swap_after_stat)
        p.setattr(os,'open',swap_before_fd_open)
        result=b.state
    assert done[0], 'attack did not interleave with metadata check'
    assert result=='UNKNOWN', f'FAIL OPEN: symlink record accepted as {result}'


def test_signed_journal_directory_symlink_swap_after_replay_refuses_write(tmp_path, monkeypatch):
    """Changing the journal parent path after replay must not redirect a write."""
    b=start(tmp_path)
    legitimate=tmp_path/'journal'
    held=tmp_path/'journal-original'
    original_replay=b.journal._replay
    swapped=[False]

    def swap_dir_after_replay(*args,**kwargs):
        result=original_replay(*args,**kwargs)
        if not swapped[0]:
            swapped[0]=True
            legitimate.rename(held)
            legitimate.symlink_to(held,target_is_directory=True)
        return result

    proof=sign(b.journal,'FENCED',evidence=digest(RAW))
    with monkeypatch.context() as p:
        p.setattr(b.journal,'_replay',swap_dir_after_replay)
        with pytest.raises((OSError,Hold)):
            b.journal.write('FENCED','TEST_ONLY',H,proof=proof)
    assert swapped[0]
    assert not (held/'00000002.json').exists()


def test_journal_parent_symlink_after_fenced_replay_yields_unknown(tmp_path):
    b=start(tmp_path);fence(b)
    src=tmp_path/'journal'; moved=tmp_path/'journal-original'
    src.rename(moved)
    src.symlink_to(moved,target_is_directory=True)
    assert b.state=='UNKNOWN'


def test_evidence_journal_head_record_swap_after_valid_replay_yields_unknown(tmp_path,monkeypatch):
    """Even the second read of the verified FENCED head must not follow a link."""
    b=start(tmp_path);fence(b)
    rec=tmp_path/'journal'/'00000002.json'
    saved=tmp_path/'saved-head.json'
    replay=b.journal._replay
    swapped=[False]

    def swap_after_signed_replay(*args,**kwargs):
        answer=replay(*args,**kwargs)
        if not swapped[0]:
            swapped[0]=True
            rec.rename(saved)
            rec.symlink_to(saved)
        return answer

    with monkeypatch.context() as p:
        p.setattr(b.journal,'_replay',swap_after_signed_replay)
        result=b.state
    assert swapped[0]
    assert result=='UNKNOWN'
