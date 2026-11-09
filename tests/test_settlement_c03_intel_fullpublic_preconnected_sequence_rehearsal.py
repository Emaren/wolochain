"""Guard exact physical C03 HD/DE rehearsal sources: proof, NOT release."""
from pathlib import Path
import hashlib
import unittest

ROOT = Path(__file__).resolve().parents[1]
CASES = (
    ("hd", 190, 180,
     "settlement_c03_intel_hd_fullpublic_preconnected_sequence_rehearsal.py",
     "897b673692e6b2310b4a8f2cbf6590480c747679952893865dc23f42d2b86398",
     "7a8d495b4259c5316f0f38ff060667d6b81f1243f77e1656daf2765da3603305"),
    ("de", 52, 50,
     "settlement_c03_intel_de_fullpublic_preconnected_sequence_rehearsal.py",
     "fa9a93ed7ba10b1282b6410873b86cd010cdf47ca71ee7e044f6cbbe99ba3e8d",
     "df21fa2e67319e606a530af501c5b108831178c27fb98c79b31e02bb166a5bb7"),
)

class C03FullPublicSourceIntegrityTest(unittest.TestCase):
    def test_physically_executed_exact_source_and_original_restore_pins(self):
        for scope, tables, seqs, name, expected, restore in CASES:
            with self.subTest(scope=scope):
                path = ROOT / "scripts" / name
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)
                text = path.read_text()
                self.assertIn(restore, text)
                self.assertIn(f"len(tables)=={tables}", text)
                self.assertIn(f"len(seqs)=={seqs}", text)

    def test_ssh_production_and_public_tcp_cannot_be_part_of_rehearsal(self):
        for scope, tables, seqs, name, expected, restore in CASES:
            with self.subTest(scope=scope):
                t = (ROOT / "scripts" / name).read_text()
                for guard in (
                    "INTEL_ONLY_UNPRIVILEGED", "SINGLE_SHOT_NO_OVERWRITE",
                    "REAL_C07_RECOVERY_SHA_DRIFT", "RESTORED_SOURCE_MUST_BE_STOPPED",
                    "RESTORED_SOURCE_NOT_CLEANLY_STOPPED",
                    "listen_addresses=''", "UNIX_SOCKET_PATH_TOO_LONG",
                    "C03_ALL_", "PRECONNECTED_TABLE_USERS_SEQUENCE_DENIAL_NOT_EXACT",
                    "FRESH_USERS_DML_DENIAL_NOT_PROVEN",
                    "FRESH_SEQ_NEXTVAL_DENIAL_NOT_PROVEN",
                    '"production_hd_de_postgres_mutated":False',
                    '"funded_activation_authorized":False',
                    '"production_c03_fence_complete":False',
                    "HOLD_C03_LIVE_WRITER_GRAPH_STEAM_ACCEPTANCE_AND_C06_C07_ATOMIC_BOUNDARY",
                ):
                    self.assertIn(guard, t, f"{scope}: missing {guard}")
                for forbidden in ("http://", "https://", "requests.post("):
                    self.assertNotIn(forbidden, t)
                self.assertIn("UPDATE public.users SET last_seen=last_seen WHERE false", t)
                self.assertIn("SELECT nextval('public.users_id_seq')", t)
                self.assertIn("has_sequence_privilege", t)
                self.assertIn("REVOKE ALL ON SEQUENCE ", t)
                self.assertIn("NOLOGIN", t)

if __name__ == "__main__":
    unittest.main()
