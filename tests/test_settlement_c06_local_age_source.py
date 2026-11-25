"""Static negative gates for the exact nonfunded HEL1 locally encrypted source."""
from pathlib import Path
import hashlib
import subprocess
import unittest

SOURCE=Path(__file__).resolve().parents[1]/'scripts/settlement_c06_hel1_local_age_hd_precapture_hold.sh'
PIN='e8f83a39f7638b917791d274bd95aa6b7afa3455f5528458db02b7003774a2e8'
class TestExactLocalAgeHD(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw=SOURCE.read_bytes()
        cls.code=cls.raw.decode('utf-8')
    def test_real_physical_used_byte_sha_unchanged(self):
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(),PIN)
    def test_shell_parse_without_running_host_command(self):
        c=subprocess.run(['bash','-n',str(SOURCE)],capture_output=True,timeout=5)
        self.assertEqual(c.returncode,0,c.stderr)
    def test_literal_allowlisted_readonly_db_and_public_key_encryption(self):
        for needle in [
            'set -o pipefail','umask 077',
            '/usr/lib/postgresql/16/bin/pg_dump',
            '-Fc -Z3 --lock-wait-timeout=5000 -d aoe2hd_db',
            'm1-recipient.pub','intel-recipient.pub',
            '/usr/bin/age -R "$m1" -R "$intel" -o "$partial"',
            'sha256','os.O_EXCL','os.O_NOFOLLOW','os.fsync',
            'writer_quiesced','False','cross_database_atomic','offhost_readback_verified',
            'c06_closed','c07_closed','financial_release_authorized',
        ]:
            self.assertIn(needle,self.code)
    def test_no_private_key_or_legacy_payment_lifecycle(self):
        for banned in ['mnemonic','keyring','--identity','age -d','8092','8094',
            'systemctl restart','systemctl start','DROP TABLE','ALTER ROLE',
            'UPDATE pending_wolo_claims','DELETE FROM','COPY TO PROGRAM',
            'wolochaind tx','--no-password']:
            self.assertNotIn(banned,self.code)
    def test_fail_closed_no_overwrite_or_unfunded_disclosure(self):
        for needle in ['HOLD_EXISTING_OUTPUT','HOLD_C06_PUBLIC_RECIPIENT_DRIFT',
            'HOLD_PGDUMP_OR_AGE_FAILED','HOLD_FINAL_EXISTS_OR_SYMLINK',
            "writer_quiesced':False", "c06_closed':False",
            "c07_closed':False", "financial_release_authorized':False"]:
            self.assertIn(needle,self.code)
if __name__=='__main__':unittest.main()
