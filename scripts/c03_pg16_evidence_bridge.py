#!/usr/bin/env python3
"""C03 source-only evidence binder; NO producer, PG executor, signer or release authority.

A *disposable*, witnessed PG16 rehearsal can be cryptographically bound to an
independent test-only transition proof. On restart missing/different receipt
bytes yield UNKNOWN even when the Ed25519 journal record verifies correctly.

This remains a model: self-reported PG stdout is not an independently trusted
production witness, and the host owner could replace both receipts and tests.
"""
from __future__ import annotations
from pathlib import Path
import hashlib
import json
import os
import re
import stat

from c03_durable_admission import Hold, Journal, canonical, digest, verify_transition_proof

# The exact test assertions exercised on the user's disposable PG16 instance.
EXPECTED = (
    'PG16 private initdb/version',
    'HBA live reload denies new clients',
    'existing writer survives all-reject HBA reload',
    'existing writer persists after NOLOGIN',
    'new writer denied NOLOGIN',
    'definer bypass exists before revocation',
    'synthetic ACL revocation denies preconnected writer',
    'sequence bypass denied',
    'SECURITY DEFINER denied',
    'reader SELECT survives',
    'all-client HBA persisted over two restarts',
    'no auth release after restart',
    'HBA byte-exact rollback',
    'role+ACL preimage byte parity',
    'isolated inverse returns initial writer rights',
)
RECEIPT_FIELDS = {'case_count','checks','ephemeral_cluster','hba_deny_sha256',
                  'hba_original_sha256','postgres','status','tcp_listening'}
# Source byte identity of the FINANCIAL PR #248 rehearsal, not an approval of it.
TEST_RUNNER_SHA256 = '874e470e25bab8203055898df4ed1fbdd2bdd967805818afed5cff45f5f5edda'
# A recorded source-only test fixture, NOT a cryptographically witnessed live observation.
PINNED_DISPOSABLE_RECEIPT_SHA256 = '300d19f126eaa42e48c75666ed52b3ea169f05903ef14840bf622486f9fa809c'


def _no_duplicates(pairs):
    result={}
    for key,val in pairs:
        if key in result:
            raise Hold('C03_EVIDENCE_DUPLICATE_KEY')
        result[key]=val
    return result


def validate_receipt(raw: bytes) -> dict:
    """Validation of a bounded *test* result, not of a trusted physical probe."""
    if not isinstance(raw, bytes) or len(raw)>8192 or not raw.endswith(b'\n'):
        raise Hold('C03_EVIDENCE_NOT_CANONICAL_TEST_RECEIPT')
    try:
        obj=json.loads(raw, object_pairs_hook=_no_duplicates)
    except (ValueError,TypeError,UnicodeDecodeError) as e:
        raise Hold('C03_EVIDENCE_INVALID_JSON') from e
    if (not isinstance(obj,dict) or set(obj)!=RECEIPT_FIELDS or
        obj.get('case_count') != len(EXPECTED) or
        type(obj.get('case_count')) is not int or
        obj.get('checks')!=list(EXPECTED) or
        obj.get('postgres')!='16' or obj.get('status')!='PASS' or
        obj.get('ephemeral_cluster') is not True or
        obj.get('tcp_listening') is not False):
        raise Hold('C03_EVIDENCE_NOT_ALL_DISPOSABLE_PG16_ASSERTIONS')
    for k in ('hba_deny_sha256','hba_original_sha256'):
        if not isinstance(obj[k],str) or not re.fullmatch(r'[0-9a-f]{64}',obj[k]):
            raise Hold('C03_EVIDENCE_INVALID_HBA_DIGEST')
    if obj['hba_deny_sha256']==obj['hba_original_sha256']:
        raise Hold('C03_EVIDENCE_HBA_NOT_CHANGED')
    # Historical fixture is fixed byte-for-byte; a newly synthesized PASS JSON
    # cannot masquerade as this earlier disposable test receipt. This still
    # does NOT authenticate the actual SQL runner, cluster or physical fence.
    if digest(raw)!=PINNED_DISPOSABLE_RECEIPT_SHA256:
        raise Hold('C03_EVIDENCE_NOT_PINNED_DISPOSABLE_RECEIPT')
    return obj


class EvidenceBoundJournal:
    """Source-only, test-receipt-bound wrapper for signed v2 journal.

    Existence of this wrapper cannot authorize PostgreSQL or systemd changes.
    It can only refuse a signed FENCED journal claim when the exact evidence
    file itself is absent, altered, mispermissioned or not accepted as a test.
    """
    def __init__(self, journal_path: Path, archive: Path, trust: dict):
        self.journal=Journal(journal_path, trust=trust)
        self.archive=Path(archive)

    @property
    def state(self):
        # A cached FENCED label is never enough: a long-lived process must
        # independently replay every signed on-disk transition on each read.
        # A removed/replaced/rehashed journal record downgrades to UNKNOWN.
        current = self.journal._replay(allow_incomplete=True)
        expected = (self.journal.state, self.journal.head,
                    self.journal.seq, self.journal.bound_preimage)
        if current != expected:
            return 'UNKNOWN'
        if self.journal.state == 'RESTORED':
            # No independent exact-inverse PG16 evidence binder exists yet.
            return 'UNKNOWN'
        if self.journal.state != 'FENCED':
            return self.journal.state
        receipt_hash=None
        try:
            # Read the verified head as an anchored, no-follow journal entry.
            # The previous Path.read_bytes followed an attacker-swapped symlink.
            jdfd=os.open(self.journal.directory,
                os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:
                dstat=os.fstat(jdfd)
                if (not stat.S_ISDIR(dstat.st_mode) or dstat.st_mode&0o077 or
                    dstat.st_uid!=os.geteuid()):
                    return 'UNKNOWN'
                jfd=os.open(f'{self.journal.seq:08d}.json',
                    os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK, dir_fd=jdfd)
                try:
                    fst=os.fstat(jfd)
                    if (not stat.S_ISREG(fst.st_mode) or fst.st_mode&0o077
                        or fst.st_nlink!=1 or fst.st_uid!=os.geteuid()
                        or not (0 < fst.st_size <= 8192)):
                        return 'UNKNOWN'
                    jraw=os.read(jfd,8193)
                    if len(jraw)!=fst.st_size:
                        return 'UNKNOWN'
                finally:
                    os.close(jfd)
            finally:
                os.close(jdfd)
            record=json.loads(jraw)
            if (record.get('hash')!=self.journal.head or
                canonical(record)!=jraw or record.get('state')!='FENCED'):
                return 'UNKNOWN'
            receipt_hash=record['proof']['body']['evidence_sha256']
            if not re.fullmatch('[0-9a-f]{64}',receipt_hash):
                return 'UNKNOWN'
            # Directory-relative O_NOFOLLOW opens anchor the hash-named file
            # against symlink substitution between metadata check and read.
            directory_fd=os.open(self.archive, os.O_DIRECTORY|os.O_RDONLY|os.O_NOFOLLOW)
            try:
                directory=os.fstat(directory_fd)
                if (not stat.S_ISDIR(directory.st_mode) or directory.st_mode&0o077
                    or directory.st_uid!=os.geteuid()):
                    return 'UNKNOWN'
                receipt_fd=os.open(receipt_hash+'.json',
                    os.O_RDONLY|os.O_NOFOLLOW, dir_fd=directory_fd)
                try:
                    fstat=os.fstat(receipt_fd)
                    if (not stat.S_ISREG(fstat.st_mode) or fstat.st_mode&0o077
                        or fstat.st_nlink!=1 or fstat.st_uid!=os.geteuid()
                        or fstat.st_size>8192):
                        return 'UNKNOWN'
                    raw=os.read(receipt_fd,8193)
                    if len(raw)!=fstat.st_size:
                        return 'UNKNOWN'
                finally:
                    os.close(receipt_fd)
            finally:
                os.close(directory_fd)
            validate_receipt(raw)
            if digest(raw)!=receipt_hash:
                return 'UNKNOWN'
        except (OSError,ValueError,KeyError,TypeError,Hold):
            return 'UNKNOWN'
        return 'FENCED'

    def require_production_fence(self):
        # This implementation has no enrolled independent root/PG/systemd
        # process attestor; even a valid signed test receipt is NOT a fence.
        raise Hold('C03_NO_INDEPENDENT_PRODUCTION_PHYSICAL_WITNESS')

    def append_fenced_test_claim(self, event: str, preimage: str, proof: dict, raw: bytes):
        if self.journal.state!='INTENT' or self.state=='UNKNOWN':
            raise Hold('C03_EVIDENCE_REQUIRES_PRIOR_SIGNED_INTENT')
        validate_receipt(raw)
        if not isinstance(proof,dict) or not isinstance(proof.get('body'),dict):
            raise Hold('C03_EVIDENCE_PROOF_REQUIRED')
        h=digest(raw)
        if proof['body'].get('evidence_sha256')!=h or proof['body'].get('state')!='FENCED':
            raise Hold('C03_EVIDENCE_NOT_BOUND_TO_WITNESS_SIGNATURE')
        verify_transition_proof(proof, self.journal.trust, state='FENCED',
            preimage_hash=preimage, sequence=self.journal.seq,
            previous_hash=self.journal.head, now=__import__('time').time_ns()//1000000000,
            event=event, expected_original_hash=preimage)
        if not self.archive.exists():
            self.archive.mkdir(mode=0o700)
        # Use a directory fd for both the source validation and the new file.
        # Never check one path then write through a path re-resolved later.
        dfd=os.open(self.archive, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            st=os.fstat(dfd)
            if (not stat.S_ISDIR(st.st_mode) or st.st_uid!=os.geteuid()
                or st.st_mode&0o077):
                raise Hold('C03_EVIDENCE_ARCHIVE_OWNER_OR_MODE')
            fd=os.open(h+'.json', os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,
                       0o600, dir_fd=dfd)
            with os.fdopen(fd,'wb') as f:
                f.write(raw);f.flush();os.fsync(f.fileno())
            os.fsync(dfd)
        finally:
            os.close(dfd)
        # The underlying Journal verifies the *separately signed* proof,
        # exact journal preimage + previous hash, sequence and signer role.
        self.journal.write('FENCED',event,preimage,proof=proof)
        if self.state!='FENCED':
            raise Hold('C03_EVIDENCE_POSTWRITE_NOT_DURABLY_ACCEPTED')
        return h


def main():
    raise SystemExit('C03_SOURCE_ONLY_NO_FINANCIAL_PG_EXECUTOR')

if __name__=='__main__': main()
