"""C07 physically executed SQL source pins and offline-only negative ACL tests."""
from pathlib import Path
import importlib.util, hashlib, json, subprocess, sys, tempfile, unittest

ROOT=Path(__file__).resolve().parents[1]
CHECK=ROOT/"scripts/settlement_c07_compare_recovered_role_grants_v1.py"
PARSER=ROOT/"scripts/settlement_c07_extract_pgdump_acl_sections.py"
SOURCES={
"settlement_c07_real_owner_parity_live_and_restore.sql":"802e949c2d5ba62b9d788538b4035d1835b19d470821a6039aade8ba7b0d7fa7",
"settlement_c07_real_effective_acl_parity_live_and_restore.sql":"c330afb20903b2c01fac0a4a9bdb319cc01af698096d4a22bd05f9007248ed65",
"settlement_c07_real_hd_owner_map_generator.sql":"bb40c43a1dce07320e9216597d47c44cc3600c410361014f27002a6be98551fd",
"settlement_c07_real_de_owner_map_generator.sql":"ff7599d5913edf072f861cf95a1172774028ef72ff74a0db750bd9438d56b6b3",
"settlement_c07_extract_pgdump_acl_sections.py":"ab169558ae038b4654153a60ad395e7434979ee478f793afc429ddf61c621e44"}
spec=importlib.util.spec_from_file_location("c07",CHECK)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def fixture(scope,kind):
    h="a"*32
    if kind=="owner":
        values={"ROLE_COUNT":"24","MEMBER_COUNT":"3",**m.SCOPES[scope],
                "REL_OWNER_SHA":h,"FUNC_OWNER_SHA":h if scope=="hd" else "",
                "SCHEMA_OWNER_SHA":h,"ROLE_FLAG_SHA":h,"MEMBER_SHA":h}
        return "".join(f"{k}|{v}\n" for k,v in values.items()).encode()
    types=m.TYPES if scope=="hd" else m.TYPES[:-1]
    return "".join(f"{t}|{role}|{h}\n" for t in types for role in m.ROLES).encode()

class C07SourceAndFailClosed(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        base=Path(self.temp.name)
        self.live,self.restored=base/"live",base/"restored"
        for folder in (self.live,self.restored):
            folder.mkdir(mode=0o700)
            for scope in ("hd","de"):
                for kind in ("owner","effective"):
                    p=folder/f"{scope}.{kind}.txt"
                    p.write_bytes(fixture(scope,kind))
                    p.chmod(0o600)
        self.out=base/"receipt.json"
    def tearDown(self):self.temp.cleanup()

    def test_exact_original_physically_exercised_source_hashes(self):
        for filename,digest in SOURCES.items():
            with self.subTest(filename=filename):
                self.assertEqual(hashlib.sha256((ROOT/"scripts"/filename).read_bytes()).hexdigest(),digest)
        self.assertIn("BEGIN TRANSACTION READ ONLY;",(ROOT/"scripts/settlement_c07_real_owner_parity_live_and_restore.sql").read_text())
        self.assertIn("has_function_privilege",(ROOT/"scripts/settlement_c07_real_effective_acl_parity_live_and_restore.sql").read_text())

    def test_positive_rehearsal_can_never_close_financial_release(self):
        x=subprocess.run([sys.executable,str(CHECK),"--live-dir",str(self.live),
          "--restored-dir",str(self.restored),"--out",str(self.out)],
          capture_output=True,text=True,timeout=10)
        self.assertEqual(x.returncode,0,x.stderr)
        r=json.loads(self.out.read_text())
        self.assertEqual(len(r["verified"]),2)
        self.assertFalse(r["c06_formally_closed"])
        self.assertFalse(r["c07_formally_closed"])
        self.assertFalse(r["financial_release_authorized"])
        self.assertFalse(r["password_verifiers_restored"])

    def test_drift_in_one_effective_grant_denies(self):
        p=self.restored/"hd.effective.txt"
        p.write_bytes(p.read_bytes().replace(b"a"*32,b"b"*32,1))
        with self.assertRaisesRegex(ValueError,"LIVE_RESTORED_MISMATCH_HD_EFFECTIVE"):
            m.compare(self.live,self.restored)
        self.assertFalse(self.out.exists())

    def test_role_scope_drift_and_acl_source_symlink_denied(self):
        p=self.restored/"hd.owner.txt"
        p.write_bytes(p.read_bytes().replace(b"USER_REL_COUNT|401",b"USER_REL_COUNT|400"))
        with self.assertRaisesRegex(ValueError,"ORIGINAL_SCOPE_DRIFT"):
            m.compare(self.live,self.restored)
        # Restore the HD fixture so the second negative reaches the DE symlink.
        hd=self.restored/"hd.owner.txt"
        hd.write_bytes(fixture("hd","owner"))
        hd.chmod(0o600)
        p=self.restored/"de.owner.txt"
        p.unlink()
        p.symlink_to(self.live/"de.owner.txt")
        with self.assertRaisesRegex(ValueError,"SOURCE_NOT_REGULAR_FILE"):
            m.compare(self.live,self.restored)

    def test_reused_input_directory_and_receipt_overwrite_denied(self):
        with self.assertRaisesRegex(ValueError,"LIVE_AND_RESTORED_INPUT_IDENTICAL"):
            m.main(["--live-dir",str(self.live),"--restored-dir",str(self.live),"--out",str(self.out)])
        self.out.write_text("EXISTING")
        self.out.chmod(0o600)
        with self.assertRaisesRegex(ValueError,"NO_OVERWRITE_RECEIPT"):
            m.main(["--live-dir",str(self.live),"--restored-dir",str(self.restored),"--out",str(self.out)])
        self.assertEqual(self.out.read_text(),"EXISTING")

    def test_future_capture_reference_does_not_make_c07_pass(self):
        m.main(["--live-dir",str(self.live),"--restored-dir",str(self.restored),
                "--out",str(self.out),"--c06-capture-sha256","f"*64])
        r=json.loads(self.out.read_text())
        self.assertFalse(r["c07_formally_closed"])
        self.assertFalse(r["consensus_and_journal_same_checkpoint_proven"])

    def test_acl_extraction_valid_and_multiline_denied(self):
        head="-- Name: users; Type: ACL; Schema: public; Owner: postgres\n"
        sample=head+("GRANT SELECT ON TABLE public.users TO aoe2war_web_prod;\n"*10)
        x=subprocess.run([sys.executable,str(PARSER)],input=sample,
            capture_output=True,text=True,timeout=10)
        self.assertEqual(x.returncode,0,x.stderr)
        self.assertEqual(x.stdout.count("GRANT SELECT"),10)
        bad=subprocess.run([sys.executable,str(PARSER)],
            input=head+("GRANT SELECT ON TABLE public.users\n"*10),
            capture_output=True,text=True,timeout=10)
        self.assertNotEqual(bad.returncode,0)
        self.assertIn("HOLD_PGDUMP_MULTILINE_ACL_UNSUPPORTED",bad.stderr)
if __name__=="__main__":unittest.main()
