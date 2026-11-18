#!/usr/bin/env python3
"""C03 OFFLINE SOURCE-ONLY durable admission contract. NO production executor.

This module deliberately contains NO command runner, PostgreSQL client, SQL
executor, systemd API, credentials, signer, or financial release entry point.
It models the fixed-cluster admission and crash/rollback proof contract only.
Protected FINANCIAL source owners must independently review, integrate, and
supply an explicitly authorized executor. Do not use this as an outage permit.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib, json, os, re, stat, time
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SCHEMA = 'wolo.c03.durable-exclusion.source-only.v1'
ORIGINAL_BARRIER_SHA256 = '54679c80ed76146d7aa3f643b3fda9f228b99b95e5c32ec9329c4f800db354de'
FINANCIAL_PORTS = (8092, 8093, 8094, 8095)
REQUIRED_STEPS = ('startup_mask', 'all_reject_hba', 'postmaster_offline',
                  'isolated_pg_exclusion', 'definer_and_sequence_denials',
                  'reader_and_pooler_denials', 'recovery_checkpoint')
ALLOWED = ('HOLD', 'INTENT', 'UNKNOWN', 'FENCED', 'RESTORE_INTENT', 'RESTORED')
PROOF_SCHEMA = 'wolo.c03.transition-proof.source-only.v2'
ISSUER_ROLES = {'INTENT':'owner-outage', 'FENCED':'independent-fence-witness',
                'RESTORE_INTENT':'owner-exact-inverse',
                'RESTORED':'independent-inverse-witness'}


class Hold(RuntimeError):
    pass


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(payload: dict) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=True) + '\n').encode('ascii')


def fixed_hex(value: str) -> bool:
    return bool(re.fullmatch(r'[0-9a-f]{64}', value))


@dataclass(frozen=True)
class Preimage:
    """Non-sensitive immutable IDs captured by a separately admitted reader."""
    cluster_name: str
    cluster_device: int
    cluster_inode: int
    data_path: str
    postgres_binary_sha256: str
    offline_barrier_sha256: str
    postgresql_unit_sha256: str
    pg_config_sha256: str
    auto_conf_sha256: str
    includes_manifest_sha256: str
    hba_sha256: str
    startup_units_manifest_sha256: str
    roles_acl_manifest_sha256: str
    ddl_definers_manifest_sha256: str
    sequences_manifest_sha256: str
    poolers_manifest_sha256: str
    source_scope_sha256: str

    def validate(self) -> None:
        if self.cluster_name != '16/main' or self.cluster_device <= 0 or self.cluster_inode <= 0:
            raise Hold('C03_WRONG_CLUSTER')
        if not self.data_path.startswith('/') or '..' in Path(self.data_path).parts:
            raise Hold('C03_UNSAFE_DATA_PATH')
        if self.data_path in ('/', '/var', '/var/lib', '/var/lib/postgresql'):
            raise Hold('C03_OVERBROAD_DATA_PATH')
        for key, val in asdict(self).items():
            if key.endswith('_sha256') and not fixed_hex(val):
                raise Hold('C03_UNPINNED_' + key.upper())
        if self.offline_barrier_sha256 != ORIGINAL_BARRIER_SHA256:
            raise Hold('C03_SOURCE_BARRIER_DRIFT')


@dataclass(frozen=True)
class Witness:
    """Explicit bounded findings from independently sourced checks.

    Every field is REQUIRED; no unknown or partial witness is accepted. This is
    NOT a substitute for real PG/systemd/role audits or signed provenance.
    """
    matching_preimage: bool
    config_and_include_closure: bool
    auto_conf_bound: bool
    parent_and_child_mask_persistent: bool
    restart_after_crash_denied: bool
    hba_all_clients_denied: bool
    postmaster_offline_exact_pid: bool
    no_active_pooler_or_preconnected_backend: bool
    no_other_pg_instance_targeted: bool
    no_background_or_prepared_xact: bool
    authenticated_reader_only: bool
    legacy_writer_dml_denied: bool
    acl_owner_default_and_membership_denied: bool
    security_definer_transitive_write_denied: bool
    sequences_usage_update_denied: bool
    dynamic_sql_and_triggers_denied: bool
    external_financial_publishers_denied: bool
    financial_ports_closed: bool
    independent_recovery_checkpoint_accepted: bool

    def missing(self) -> tuple[str, ...]:
        return tuple(k for k,v in asdict(self).items() if v is not True)


def verify_transition_proof(proof: dict, trust: dict, *, state: str,
                            preimage_hash: str, sequence: int, previous_hash: str,
                            now: int, event: str, expected_original_hash: str | None = None) -> str:
    """Source-only detached Ed25519 transition proof verification.

    Trusted public keys and independent role assignments MUST come from a
    separately root-admitted authority; these inputs do not imply any approval.
    The proof can only license a SOURCE-ONLY journal state change, never SQL or
    systemd operations. No secret key, permit issuer or financial executor here.
    """
    if state not in ISSUER_ROLES or not isinstance(proof,dict) or not isinstance(trust,dict):
        raise Hold('C03_SIGNED_TRANSITION_REQUIRED')
    if set(proof) != {'body','signature_hex'} or not isinstance(proof['body'],dict):
        raise Hold('C03_MALFORMED_PROOF')
    body=proof['body']
    keys={'schema','state','role','issuer','preimage_sha256','journal_sequence',
          'previous_hash','issued_at','expires_at','nonce_sha256','evidence_sha256',
          'event_sha256',
          'original_preimage_sha256'}
    if set(body) != keys:
        raise Hold('C03_PROOF_FIELDS_NOT_EXACT')
    if body['schema'] != PROOF_SCHEMA or body['state'] != state or body['role'] != ISSUER_ROLES[state]:
        raise Hold('C03_PROOF_WRONG_DOMAIN_OR_ROLE')
    if type(body['journal_sequence']) is not int or body['journal_sequence'] != sequence+1:
        raise Hold('C03_PROOF_SEQUENCE_REPLAY_OR_DRIFT')
    if not isinstance(event,str) or not re.fullmatch(r'[A-Za-z0-9_:-]{1,96}',event):
        raise Hold('C03_INVALID_EVENT')
    if body['event_sha256'] != digest(event.encode('ascii')):
        raise Hold('C03_PROOF_EVENT_NOT_BOUND')
    if body['previous_hash'] != previous_hash or body['preimage_sha256'] != preimage_hash:
        raise Hold('C03_PROOF_WRONG_PREIMAGE_OR_PARENT')
    if not all(isinstance(body[k],str) and fixed_hex(body[k]) for k in
               ('nonce_sha256','evidence_sha256','original_preimage_sha256','event_sha256')):
        raise Hold('C03_PROOF_UNPINNED_EVIDENCE')
    if expected_original_hash is not None and body['original_preimage_sha256'] != expected_original_hash:
        raise Hold('C03_INVERSE_WRONG_ORIGINAL_PREIMAGE')
    if body['original_preimage_sha256'] != preimage_hash:
        raise Hold('C03_PROOF_ORIGINAL_PREIMAGE_MISMATCH')
    if type(now) is not int or type(body['issued_at']) is not int or type(body['expires_at']) is not int:
        raise Hold('C03_PROOF_INVALID_TIME')
    if not (body['issued_at'] <= now < body['expires_at'] and
            0 < body['expires_at']-body['issued_at'] <= 3600 and
            now-body['issued_at'] <= 3600):
        raise Hold('C03_PROOF_EXPIRED_OR_UNBOUNDED')
    issuer=body['issuer']
    if not isinstance(issuer,str) or issuer not in trust:
        raise Hold('C03_PROOF_UNTRUSTED_ISSUER')
    # Owner and independent witness must not resolve to a single Ed25519 key.
    seen_keys={}
    for entry in trust.values():
        if isinstance(entry,dict) and isinstance(entry.get('public_key'),bytes) and isinstance(entry.get('role'),str):
            key=entry['public_key']
            if key in seen_keys and seen_keys[key]!=entry['role']:
                raise Hold('C03_OWNER_WITNESS_KEY_NOT_INDEPENDENT')
            seen_keys[key]=entry['role']
    attestation=trust[issuer]
    if not isinstance(attestation,dict) or set(attestation) != {'role','public_key'}:
        raise Hold('C03_TRUST_ENTRY_INVALID')
    if attestation['role'] != body['role'] or not isinstance(attestation['public_key'],bytes):
        raise Hold('C03_PROOF_ISSUER_ROLE_NOT_ADMITTED')
    if len(attestation['public_key'])!=32:
        raise Hold('C03_ISSUER_KEY_LENGTH_INVALID')
    sig=proof['signature_hex']
    if not isinstance(sig,str) or not re.fullmatch(r'[0-9a-f]{128}',sig):
        raise Hold('C03_PROOF_SIGNATURE_FORMAT')
    try:
        Ed25519PublicKey.from_public_bytes(attestation['public_key']).verify(bytes.fromhex(sig),canonical(body))
    except (InvalidSignature,ValueError,TypeError) as exc:
        raise Hold('C03_PROOF_SIGNATURE_NOT_VERIFIED') from exc
    return digest(canonical(body))


class Journal:
    """Durable append-only state with optimistic parent hash, no execution.

    Each record is written to a new O_EXCL file, fsynced and directory-fsynced.
    An incomplete INTENT is NEVER resumed automatically. An incomplete or
    inconsistent chain is UNKNOWN. Never overwrites earlier evidence.
    """
    def __init__(self, directory: Path, trust: dict | None = None):
        self.directory = Path(directory)
        self.trust = trust or {}
        self.creator_pid = os.getpid()
        if self.directory.exists():
            st = self.directory.lstat()
            if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode) or st.st_mode & 0o077:
                raise Hold('C03_JOURNAL_DIRECTORY_PERMISSIONS')
        else:
            self.directory.mkdir(mode=0o700, parents=False)
        self.state, self.head, self.seq, self.bound_preimage = self._replay()

    def _replay(self, *, allow_incomplete: bool = False):
        # Anchor every record open to one directory fd. A separate pathname
        # lstat followed by Path.read_bytes can be swapped to a symlink after
        # its metadata check and incorrectly attest FENCED.
        seq = 0; prev = '0'*64; state = 'HOLD'; bound_preimage = None
        try:
            dfd = os.open(self.directory, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        except OSError:
            return 'UNKNOWN', prev, seq, bound_preimage
        try:
            dst = os.fstat(dfd)
            if (not stat.S_ISDIR(dst.st_mode) or dst.st_mode&0o077 or
                dst.st_uid != os.geteuid()):
                return 'UNKNOWN', prev, seq, bound_preimage
            paths = sorted(os.listdir(dfd))
            for name in paths:
                if not re.fullmatch(r'[0-9]{8}\.json', name):
                    return 'UNKNOWN', prev, seq, bound_preimage
                try:
                    fd = os.open(name, os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,
                                 dir_fd=dfd)
                    try:
                        st = os.fstat(fd)
                        if (not stat.S_ISREG(st.st_mode) or st.st_mode&0o077
                            or st.st_nlink!=1 or st.st_uid!=os.geteuid()
                            or not (0 < st.st_size <= 8192)):
                            return 'UNKNOWN', prev, seq, bound_preimage
                        raw = os.read(fd, 8193)
                        if len(raw) != st.st_size:
                            return 'UNKNOWN', prev, seq, bound_preimage
                    finally:
                        os.close(fd)
                    obj = json.loads(raw); number = obj['number']
                    if number != seq+1 or name != f'{number:08d}.json':
                        return 'UNKNOWN', prev, seq, bound_preimage
                    if obj['prev'] != prev or obj['state'] not in ALLOWED:
                        return 'UNKNOWN', prev, seq, bound_preimage
                    if (obj['schema'] != SCHEMA or not fixed_hex(obj['preimage_sha256'])
                        or not fixed_hex(obj.get('proof_sha256','')) or
                        set(obj) != {'schema','number','prev','state','event','preimage_sha256','proof_sha256','proof','hash'}):
                        return 'UNKNOWN', prev, seq, bound_preimage
                    if bound_preimage is None:bound_preimage=obj['preimage_sha256']
                    if obj['preimage_sha256'] != bound_preimage:
                        return 'UNKNOWN', prev, seq, bound_preimage
                    permitted={
                        'HOLD':('INTENT',), 'INTENT':('FENCED','UNKNOWN'),
                        'FENCED':('RESTORE_INTENT',),
                        'RESTORE_INTENT':('RESTORED','UNKNOWN'),
                        'RESTORED':(), 'UNKNOWN':()
                    }
                    if obj['state'] not in permitted[state]:
                        return 'UNKNOWN', prev, seq, bound_preimage
                    canonical_raw = canonical({k:v for k,v in obj.items() if k!='hash'})
                    if digest(canonical_raw) != obj['hash'] or canonical(obj) != raw:
                        return 'UNKNOWN', prev, seq, bound_preimage
                    if digest(canonical(obj['proof'])) != obj['proof_sha256']:
                        return 'UNKNOWN', prev, seq, bound_preimage
                    verify_transition_proof(obj['proof'], self.trust, state=obj['state'],
                        preimage_hash=obj['preimage_sha256'], sequence=seq,
                        previous_hash=prev, now=obj['proof']['body']['issued_at'],
                        event=obj['event'], expected_original_hash=bound_preimage)
                    seq = number; prev = obj['hash']; state = obj['state']
                except (OSError, ValueError, KeyError, TypeError, Hold):
                    return 'UNKNOWN', prev, seq, bound_preimage
        finally:
            os.close(dfd)
        if state in ('INTENT', 'RESTORE_INTENT') and not allow_incomplete:
            return 'UNKNOWN', prev, seq, bound_preimage
        return state, prev, seq, bound_preimage

    def write(self, new_state: str, event: str, preimage_hash: str, *,
              proof: dict | None = None):
        if os.getpid() != self.creator_pid:
            raise Hold('C03_FORKED_CONTROLLER_CANNOT_CONTINUE')
        if self.state == 'UNKNOWN':
            raise Hold('C03_UNKNOWN_REQUIRES_EXTERNAL_HUMAN_RECOVERY')
        if new_state not in ALLOWED or not fixed_hex(preimage_hash):
            raise Hold('C03_INVALID_STATE_OR_PREIMAGE')
        if self.bound_preimage is not None and preimage_hash != self.bound_preimage:
            raise Hold('C03_PREIMAGE_IDENTITY_CHANGED')
        transitions = {
            'HOLD': ('INTENT',),
            'INTENT': ('FENCED', 'UNKNOWN'),
            'FENCED': ('RESTORE_INTENT',),
            'RESTORE_INTENT': ('RESTORED', 'UNKNOWN'),
            'RESTORED': (),
        }
        if new_state not in transitions.get(self.state, ()):
            raise Hold('C03_UNADMITTED_STATE_TRANSITION')
        if new_state == 'UNKNOWN':
            raise Hold('C03_UNKNOWN_WRITE_REQUIRES_SEPARATE_RECOVERY_ADMISSION')
        # Treat a stale in-memory instance as UNKNOWN for safety: never append
        # against a journal that advanced on disk after its first read.
        disk_state,disk_head,disk_seq,disk_preimage = self._replay(allow_incomplete=True)
        if (disk_state,disk_head,disk_seq,disk_preimage) != (
            self.state,self.head,self.seq,self.bound_preimage):
            raise Hold('C03_JOURNAL_STALE_OR_INTERRUPTED')
        now=int(time.time())  # no caller-controlled clock in journal admission
        proof_digest = verify_transition_proof(proof, self.trust, state=new_state,
            preimage_hash=preimage_hash, sequence=self.seq, previous_hash=self.head, now=now,
            event=event,
            expected_original_hash=preimage_hash)
        record={'schema': SCHEMA, 'number': self.seq+1, 'prev':self.head,
                'state':new_state, 'event':event, 'preimage_sha256':preimage_hash,
                'proof_sha256':digest(canonical(proof)), 'proof':proof}
        record['hash']=digest(canonical(record))
        # The write and directory sync share an anchored, no-follow directory
        # fd. Never re-resolve the parent path between validation and append.
        dirfd=os.open(self.directory, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            dst=os.fstat(dirfd)
            if (not stat.S_ISDIR(dst.st_mode) or dst.st_mode&0o077 or
                dst.st_uid!=os.geteuid()):
                raise Hold('C03_JOURNAL_DIRECTORY_DRIFT')
            fd=os.open(f'{self.seq+1:08d}.json',
                os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,
                0o600, dir_fd=dirfd)
            with os.fdopen(fd,'wb') as f:
                f.write(canonical(record));f.flush();os.fsync(f.fileno())
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
        self.state,self.head,self.seq = new_state, record['hash'],self.seq+1
        if self.bound_preimage is None:self.bound_preimage=preimage_hash


def plan(preimage: Preimage, witness: Witness, proposed_steps: tuple[str,...]):
    """Non-executable plan verifier; fail-closed and full coverage only."""
    preimage.validate()
    if proposed_steps != REQUIRED_STEPS:
        raise Hold('C03_STEP_ORDER_OR_COVERAGE_DRIFT')
    missing=witness.missing()
    if missing:
        raise Hold('C03_UNACCEPTED_PHYSICAL_PREDICATES:'+','.join(missing))
    return {'schema':SCHEMA,'status':'SOURCE_ONLY_NO_ACTUATOR',
            'preimage_sha256':digest(canonical(asdict(preimage))),
            'covered_steps':list(REQUIRED_STEPS),'funding':'DENIED',
            'financial_gate':'C03_OPEN'}


def verify_inverse(original: Preimage, current: Preimage, after: Preimage,
                   externally_authorized: bool, all_writers_still_denied: bool) -> str:
    """Validate an exact inverse receipt; does not execute an inverse."""
    original.validate();current.validate();after.validate()
    if not externally_authorized:
        raise Hold('C03_SIGNED_INVERSE_ADMISSION_MISSING')
    if not all_writers_still_denied:
        raise Hold('C03_CANNOT_RELEASE_WHILE_WRITERS_NOT_EXCLUDED')
    if (original.cluster_name, original.cluster_device, original.cluster_inode) != (
            current.cluster_name,current.cluster_device,current.cluster_inode):
        raise Hold('C03_TARGET_IDENTITY_DRIFT')
    if asdict(after) != asdict(original):
        raise Hold('C03_INVERSE_NOT_EXACT_PREIMAGE')
    return 'SOURCE_ONLY_INVERSE_SHAPE_QUALIFIED_NOT_EXECUTED'


def main():
    raise SystemExit('C03_SOURCE_ONLY_NO_PRODUCTION_ACTUATOR')

if __name__ == '__main__':main()
