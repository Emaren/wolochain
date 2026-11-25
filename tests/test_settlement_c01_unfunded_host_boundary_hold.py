"""Hermetic C01 host-stage observer adversarial tests; never admit custody or funds."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "settlement_c01_unfunded_host_boundary_hold.py"
spec = importlib.util.spec_from_file_location("c01_unfunded_observer", SOURCE)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def fixture():
    units = {}
    binaries = {}
    for name, spec in tool.SPECS.items():
        path = str(tool.ROOT / spec["binary"])
        units[name] = {
            "LoadState": "loaded", "ActiveState": "inactive",
            "MainPID": "0", "User": spec["user"], "Group": spec["user"],
            "ExecStart": "{ path=" + path + " ; argv[]=" + path + " ; }",
        }
        binaries[name] = {
            "bytes": spec["bytes"], "sha256": spec["sha256"],
            "uid": 0, "mode": 0o555,
        }
    return {"units": units, "binaries": binaries,
            "financial_service_listener_present": False,
            "configs": {"custody.json": "ABSENT", "reviewer.json": "ABSENT"}}


class C01UnfundedTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()
        self.satchel = "wolo-satchel-c01.service"
        self.reviewer = "wolo-reviewer-c01.service"

    def denied(self, error):
        with self.assertRaisesRegex(tool.Stop, "^" + error + "$"):
            tool.classify(self.data)

    def test_staged_observation_is_always_unfunded_hold(self):
        report = tool.classify(self.data)
        self.assertEqual(report["status"], "HOLD")
        self.assertFalse(report["c01_physically_admitted"])
        self.assertFalse(report["custody_keys_enrolled_or_verified"])
        self.assertFalse(report["reviewer_independent_human_identity_verified"])
        self.assertFalse(report["funded_canary_authorized"])
        self.assertFalse(report["financial_release_authorized"])
        self.assertFalse(report["production_mutated"])
        self.assertEqual(set(report["configuration_presence_only"]), {"custody.json", "reviewer.json"})

    def test_even_present_configs_do_not_grant_admission(self):
        self.data["configs"] = {"custody.json": "PRESENT_UNREAD",
                                "reviewer.json": "PRESENT_UNREAD"}
        result = tool.classify(self.data)
        self.assertEqual(result["status"], "HOLD")
        self.assertFalse(result["configuration_contents_reviewed"])
        self.assertFalse(result["c01_physically_admitted"])

    def test_active_service_is_stop(self):
        self.data["units"][self.satchel]["ActiveState"] = "active"
        self.denied("STAGED_UNIT_NOT_INACTIVE")

    def test_nonzero_pid_is_stop(self):
        self.data["units"][self.reviewer]["MainPID"] = "44"
        self.denied("STAGED_UNIT_NOT_INACTIVE")

    def test_identity_cannot_collapse_roles(self):
        self.data["units"][self.reviewer]["User"] = "wolo-satchel"
        self.denied("STAGED_SERVICE_IDENTITY_DRIFT")

    def test_exec_path_cannot_redirect_to_legacy_binary(self):
        self.data["units"][self.satchel]["ExecStart"] = "{ path=/usr/local/bin/wolochaind-mainnet ; }"
        self.denied("STAGED_EXECUTABLE_PATH_DRIFT")

    def test_binary_sha_mismatch(self):
        self.data["binaries"][self.satchel]["sha256"] = "0" * 64
        self.denied("STAGED_BINARY_BYTES_DRIFT")

    def test_binary_size_mismatch(self):
        self.data["binaries"][self.reviewer]["bytes"] += 1
        self.denied("STAGED_BINARY_BYTES_DRIFT")

    def test_binary_owner_or_mode_mismatch(self):
        self.data["binaries"][self.reviewer]["mode"] = 0o777
        self.denied("STAGED_BINARY_BYTES_DRIFT")

    def test_unauthorized_financial_listener(self):
        self.data["financial_service_listener_present"] = True
        self.denied("UNAUTHORIZED_FINANCIAL_LISTENER")

    def test_missing_config_observer_must_not_claim_enrollment(self):
        del self.data["configs"]["reviewer.json"]
        self.denied("CUSTODY_CONFIG_COVERAGE_INVALID")

    def test_extra_service_is_scope_drift(self):
        self.data["units"]["attacker.service"] = copy.deepcopy(self.data["units"][self.satchel])
        self.denied("STAGED_UNIT_COVERAGE_INVALID")

    def test_invalid_snapshot_is_stop(self):
        self.data["financial_service_listener_present"] = 0
        self.denied("UNAUTHORIZED_FINANCIAL_LISTENER")

    def test_parser_rejects_duplicates_unknown_and_missing(self):
        good = ["LoadState=loaded", "ActiveState=inactive", "MainPID=0",
                "User=wolo-satchel", "Group=wolo-satchel",
                "ExecStart={ path=/usr/bin/example ; }"]
        self.assertEqual(set(tool.unit_fields("\n".join(good))), tool.UNIT_KEYS)
        for lines in (good + ["User=admin"], good[:-1], good + ["Environment=secret"]):
            with self.assertRaises(tool.Stop):
                tool.unit_fields("\n".join(lines))

    def test_nonroot_cli_never_inspects(self):
        with mock.patch.object(tool.os, "geteuid", return_value=501):
            with mock.patch.object(tool, "collect", side_effect=AssertionError("must not inspect")):
                self.assertEqual(tool.main(["--inspect"]), 2)

    def test_unrequested_cli_never_inspects(self):
        with mock.patch.object(tool.os, "geteuid", return_value=0):
            with mock.patch.object(tool, "collect", side_effect=AssertionError("must not inspect")):
                self.assertEqual(tool.main(["--execute"]), 2)

    def test_symlinked_binary_refused_without_read(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "real"
            p.write_bytes(b"hello")
            alias = Path(folder) / "alias"
            alias.symlink_to(p)
            with self.assertRaisesRegex(tool.Stop, "^BINARY_SYMLINK_PATH$"):
                tool.hash_root_binary(alias)

    def test_observed_service_group_ids_are_not_assumed_equal_to_uids(self):
        self.assertEqual((tool.SPECS[self.satchel]["uid"], tool.SPECS[self.satchel]["gid"]), (988, 983))
        self.assertEqual((tool.SPECS[self.reviewer]["uid"], tool.SPECS[self.reviewer]["gid"]), (987, 982))

    def test_config_symlink_is_rejected_without_reading_contents(self):
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder)
            (d / "custody.json").symlink_to("/etc/hosts")
            with mock.patch.object(tool, "CONFIG_ROOT", d):
                with self.assertRaisesRegex(tool.Stop, "^CONFIG_TYPE_OR_MODE_DRIFT$"):
                    tool.config_mode("custody.json")

    def test_no_secret_or_financial_permit_leaks_in_observation(self):
        report = tool.classify(self.data)
        raw = json.dumps(report).lower()
        self.assertNotIn("private_key", raw)
        self.assertNotIn("mnemonic", raw)
        self.assertNotIn("token=", raw)
        self.assertNotIn("wallet_address", raw)
        self.assertNotIn("permit_signature", raw)


if __name__ == "__main__":
    unittest.main()
