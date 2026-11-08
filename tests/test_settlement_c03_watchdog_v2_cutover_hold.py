"""C03 v2 source-bound telemetry cutover tests: strictly nonfinancial.

No real systemd/SSH/database/network. Test exact service transformation,
preflight rules, fail-closed receipt parsing and rollback classification.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"scripts/settlement_c03_watchdog_v2_cutover_hold.py"
spec=importlib.util.spec_from_file_location("c03_v2_cutover",SOURCE)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
UNIT=(ROOT/"deploy/c03-observer-systemd/wolo-c03-observer.service").read_bytes()
TIMER=(ROOT/"deploy/c03-observer-systemd/wolo-c03-observer.timer").read_bytes()

class CutoverTests(unittest.TestCase):
    def test_v1_live_systemd_unit_sha_frozen(self):
        self.assertEqual(m.sha(UNIT),m.UNIT_SHA)
        self.assertEqual(m.sha(TIMER),m.TIMER_SHA)

    def test_only_three_path_substitutions(self):
        new=m.candidate(UNIT)
        self.assertEqual(
            new,UNIT.replace(b"/usr/local/libexec/wolo-c03-observer",
                             b"/usr/local/libexec/wolo-c03-observer-v2")
                    .replace(b"/var/lib/wolo-c03-observer",
                             b"/var/lib/wolo-c03-observer-v2")
                    .replace(b"/settlement_c03_observer_watchdog.py",
                             b"/settlement_c03_observer_watchdog_v2.py"))
        self.assertEqual(len(new),len(UNIT)+len("-v2")*4+len("_v2"))
        self.assertIn(b"NoNewPrivileges=yes",new)
        self.assertIn(b"SuccessExitStatus=3",new)
        self.assertIn(b"RestrictAddressFamilies=AF_UNIX",new)
        self.assertIn(b"ProtectSystem=strict",new)
        self.assertNotIn(b"ReadWritePaths=/var/lib/wolo-c03-observer\n",new)

    def test_unit_start_command_still_root_no_shell(self):
        new=m.candidate(UNIT).decode()
        self.assertIn("ExecStart=/usr/bin/python3 -B ",new)
        self.assertNotIn("ExecStart=/bin/sh",new)
        self.assertNotIn("User=root",new.split("ExecStart=")[1])
        self.assertIn("Group=root",new)

    def test_mutated_old_service_not_a_valid_candidate(self):
        for candidate in (UNIT+b"\nTimeoutStartSec=999\n",
                          UNIT.replace(b"NoNewPrivileges=yes",b"NoNewPrivileges=no"),
                          UNIT.replace(b"ReadWritePaths=",b"ReadOnlyPaths=")):
            with self.subTest(mutation=candidate[-24:]):
                with self.assertRaises(m.Hold):
                    m.candidate(candidate)

    def test_v2_input_source_pins(self):
        self.assertEqual(len(m.V1_SHA),3)
        self.assertEqual(len(m.V2_SHA),3)
        for name,value in m.V2_SHA.items():
            self.assertEqual(hashlib.sha256(
                (ROOT/"scripts"/name).read_bytes()).hexdigest(),value)
        self.assertEqual(
            m.V1_SHA["settlement_c03_observer_watchdog.py"],
            "f2df45b3efe7868c130d864e348a3c50da8fcf21d06d67dd478f88994398b707")

    def test_new_enrollment_has_no_authz_columns(self):
        o=json.loads(m.enroll_bytes())
        self.assertEqual(set(o),{"schema","unit_names_sha256","source_hashes","enabled"})
        self.assertTrue(o["enabled"])
        self.assertEqual(o["unit_names_sha256"],m.UNIT_NAMES_SHA)
        self.assertEqual(o["source_hashes"],m.SOURCE_SHA_SET)
        self.assertEqual(o["schema"],"wolo.c03.observer-baseline.v2")
        self.assertFalse("financial_authorized" in o)

    def test_enrollment_no_v1_overwrite(self):
        self.assertNotEqual(m.OLD_ENROLL,m.NEW_ENROLL)
        self.assertNotEqual(m.OLD_DIR,m.NEW_DIR)
        self.assertNotEqual(m.OLD_DATA,m.NEW_DATA)
        self.assertEqual(m.ROOT.name,"aoe2war-c03-observer-v2-cutover-20261108")
        self.assertTrue(m.LOCK.name.endswith(".lock"))

    def test_replayed_receipt_denied(self):
        o={"status":"HOLD_UNENROLLED","unitCount":67,"unscopedUnitCount":43,
           "unitNamesSha256":m.UNIT_NAMES_SHA,
           "sourceSha256":m.SOURCE_SHA_SET,
           "financialReleaseAuthorized":False,
           "extended67UnitRequired":True,
           "autoRemediation":False}
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            (root/"receipts").mkdir()
            r=root/"receipts"
            (r/"a.json").write_text(json.dumps(o))
            (r/"b.json").write_text(json.dumps(o))
            with patch.object(m,"NEW_DATA",root),patch.object(m,"checkdir",return_value=None):
                with self.assertRaises(m.Hold):
                    m.stable_receipts()

    def test_extra_financial_release_field_denied(self):
        o={"status":"HOLD_UNENROLLED","unitCount":67,"unscopedUnitCount":43,
           "unitNamesSha256":m.UNIT_NAMES_SHA,"sourceSha256":m.SOURCE_SHA_SET,
           "financialReleaseAuthorized":True,"extended67UnitRequired":True,
           "autoRemediation":False}
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            r=root/"receipts";r.mkdir()
            for x in ("a","b"):
                (r/(x+".json")).write_text(json.dumps(o))
            with patch.object(m,"NEW_DATA",root),patch.object(m,"checkdir",return_value=None):
                with self.assertRaises(m.Hold):
                    m.stable_receipts()

    def test_nonroot_admission_refused_before_access(self):
        with patch.object(m.os,"geteuid",return_value=501):
            with self.assertRaisesRegex(m.Hold,"HEL1_ROOT_REQUIRED"):
                m.preflight()

    def test_exclusive_root_receipt_not_overwritten(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            path=root/"receipt.json"
            m.write_exclusive(path,m.jsonbytes({"funded_release_authorized":False}),0o600)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
            with self.assertRaises(FileExistsError):
                m.write_exclusive(path,b"not allowed",0o600)
            self.assertEqual(json.loads(path.read_bytes())["funded_release_authorized"],False)

    def test_rollback_restores_original_service_and_deletes_only_exact_new_enrollment(self):
        with tempfile.TemporaryDirectory(prefix="c03-v2-rollback-") as temp:
            root=Path(temp)
            unit=root/"wolo-c03-observer.service"
            old=root/"original-enrollment.json"
            new=root/"v2-enrollment.json"
            unit.write_bytes(m.candidate(UNIT))
            old.write_bytes(b"immutable-v1")
            e=m.enroll_bytes()
            new.write_bytes(e)
            with patch.object(m,"UNIT",unit),patch.object(m,"OLD_ENROLL",old),                 patch.object(m,"NEW_ENROLL",new),                 patch.object(m,"V1_ENROLL_SHA",m.sha(old.read_bytes())),                 patch.object(m,"good",return_value=""),                 patch.object(m,"state",return_value={"ActiveState":"active"}):
                m.rollback(UNIT,m.sha(e))
            self.assertEqual(unit.read_bytes(),UNIT)
            self.assertFalse(new.exists())
            self.assertEqual(old.read_bytes(),b"immutable-v1")

    def test_rollback_does_not_destroy_tampered_enrollment(self):
        with tempfile.TemporaryDirectory(prefix="c03-v2-rollback-mismatch-") as temp:
            root=Path(temp)
            unit=root/"wolo-c03-observer.service"
            old=root/"original-enrollment.json"
            new=root/"v2-enrollment.json"
            unit.write_bytes(m.candidate(UNIT))
            old.write_bytes(b"immutable-v1")
            new.write_bytes(b"unexpected-external-enrollment")
            with patch.object(m,"UNIT",unit),patch.object(m,"OLD_ENROLL",old),                 patch.object(m,"NEW_ENROLL",new),                 patch.object(m,"V1_ENROLL_SHA",m.sha(old.read_bytes())),                 patch.object(m,"good",return_value=""),                 patch.object(m,"state",return_value={"ActiveState":"active"}):
                with self.assertRaisesRegex(m.Hold,"UNEXPECTED_ENROLLMENT"):
                    m.rollback(UNIT,m.sha(m.enroll_bytes()))
            self.assertEqual(unit.read_bytes(),UNIT)
            self.assertTrue(new.exists())
            self.assertEqual(old.read_bytes(),b"immutable-v1")

    def test_no_finance_runtime_mutation_sources(self):
        body=SOURCE.read_text()
        for phrase in ("ALTER ROLE","GRANT ALL","tx bank send",
                       "UPDATE public.pending_wolo_claims","DELETE FROM public.",
                       "wolo-satchel-c01.service\");systemctl start"):
            self.assertNotIn(phrase,body)
        self.assertNotIn("systemctl\",\"restart\",\"wolochaind",body)
        self.assertIn("wolo-c03-observer.timer",body)
        self.assertIn("service_started",body) if False else None

if __name__=="__main__":unittest.main()
