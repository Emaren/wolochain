import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from scripts import settlement_c03_root_finance_transport_hold as guard

LISTEN = [
    'LISTEN 0 4096 127.0.0.1:8092 0.0.0.0:* users:(("wolo",pid=1012,fd=3))',
    'LISTEN 0 4096 127.0.0.1:8093 0.0.0.0:* users:(("wolo",pid=1010,fd=3))',
    'LISTEN 0 4096 127.0.0.1:1318 0.0.0.0:* users:(("wolo",pid=1009,fd=109))',
    'LISTEN 0 4096 127.0.0.1:27657 0.0.0.0:* users:(("wolo",pid=1009,fd=95))',
]
UNITS = dict(Id="wolochaind-mainnet.service", ActiveState="active", MainPID="1009")


def unit_line(d=UNITS):
    return "\n".join(k+"="+str(v) for k,v in d.items())+"\n"


class FinanceTransportHoldTests(unittest.TestCase):
    def assertHold(self, fun, *args):
        with self.assertRaises(guard.Hold):
            fun(*args)

    def test_live_current_listeners_map_to_exact_pids(self):
        got=guard.parse_ss("\n".join(LISTEN))
        self.assertEqual(got,{8092:1012,8093:1010,1318:1009,27657:1009})

    def test_unrelated_ports_are_not_authority(self):
        self.assertEqual(guard.parse_ss('LISTEN 0 4096 127.0.0.1:3032 0.0.0.0:* users:(("next",pid=20,fd=3))'),{})

    def test_funded_port_stops_not_financial_pass(self):
        self.assertHold(guard.parse_ss,
            "\n".join(LISTEN+['LISTEN 0 50 127.0.0.1:8094 0.0.0.0:* users:(("satchel",pid=20,fd=3))']))

    def test_public_bind_on_legacy_or_rpc_stops(self):
        for port in guard.PORT_UNIT:
            with self.subTest(port=port):
                self.assertHold(guard.parse_ss,
                    f'LISTEN 0 4096 0.0.0.0:{port} 0.0.0.0:* users:(("wolo",pid=44,fd=3))')

    def test_duplicate_listener_stops(self):
        self.assertHold(guard.parse_ss,"\n".join([LISTEN[0],LISTEN[0]]))

    def test_missing_listener_pid_stops(self):
        self.assertHold(guard.parse_ss,"LISTEN 0 4096 127.0.0.1:8092 0.0.0.0:*")

    def test_non_listen_ss_shape_stops(self):
        self.assertHold(guard.parse_ss,"ESTAB 0 0 127.0.0.1:8092 127.0.0.1:555")

    def test_exact_unit_schema_passes(self):
        self.assertEqual(guard.parse_units(unit_line(),"wolochaind-mainnet.service")["MainPID"],"1009")

    def test_changed_unit_id_stops(self):
        self.assertHold(guard.parse_units,unit_line(),"wolochain-mainnet-settlement.service")

    def test_extra_or_missing_unit_fields_stop(self):
        self.assertHold(guard.parse_units,unit_line()+"PrivateKey=xxxx\n","wolochaind-mainnet.service")
        self.assertHold(guard.parse_units,"Id=wolochaind-mainnet.service\n","wolochaind-mainnet.service")

    def test_duplicate_unit_properties_stop(self):
        self.assertHold(guard.parse_units,unit_line()+"MainPID=1010\n","wolochaind-mainnet.service")

    def unit_policy(self, **overrides):
        vals={"Id":"wolochain-mainnet-settlement.service","User":"",
              "NoNewPrivileges":"no","ProtectSystem":"no","PrivateTmp":"no",
              "CapabilityBoundingSet":"cap_sys_admin cap_dac_override cap_net_bind_service"}
        vals.update(overrides)
        return "\n".join(k+"="+v for k,v in vals.items())+"\n"

    def test_confinement_exact_unrestricted_root_is_observed_not_accepted(self):
        d=guard.parse_confinement(self.unit_policy(),"wolochain-mainnet-settlement.service")
        self.assertTrue(d["root_execution"])
        self.assertFalse(d["no_new_privileges"])
        self.assertFalse(d["read_only_system_protection"])
        self.assertFalse(d["private_tmp"])
        self.assertTrue(d["has_cap_sys_admin_in_bounding_set"])
        self.assertTrue(d["has_cap_dac_override_in_bounding_set"])
        self.assertEqual(d["capability_bounding_set_entries"],3)

    def test_validator_confinement_distinct_from_legacy(self):
        raw=self.unit_policy(Id="wolochaind-mainnet.service",User="root",
            NoNewPrivileges="yes",ProtectSystem="full",PrivateTmp="yes",
            CapabilityBoundingSet="cap_net_bind_service")
        d=guard.parse_confinement(raw,"wolochaind-mainnet.service")
        self.assertTrue(d["no_new_privileges"])
        self.assertTrue(d["read_only_system_protection"])
        self.assertTrue(d["private_tmp"])
        self.assertFalse(d["has_cap_sys_admin_in_bounding_set"])

    def test_confinement_secret_field_stops(self):
        self.assertHold(guard.parse_confinement,
            self.unit_policy()+"Environment=SECRET\n",
            "wolochain-mainnet-settlement.service")

    def test_confinement_missing_and_duplicate_fields_stop(self):
        raw=self.unit_policy()
        self.assertHold(guard.parse_confinement,
            raw.replace("NoNewPrivileges=no\n",""),
            "wolochain-mainnet-settlement.service")
        self.assertHold(guard.parse_confinement,raw+"User=tony\n",
            "wolochain-mainnet-settlement.service")

    def test_confinement_nonroot_and_forged_capability_tokens_stop(self):
        self.assertHold(guard.parse_confinement,self.unit_policy(User="tony"),
            "wolochain-mainnet-settlement.service")
        self.assertHold(guard.parse_confinement,
            self.unit_policy(CapabilityBoundingSet="cap_sys_admin BAD@CAP"),
            "wolochain-mainnet-settlement.service")

    def test_uid0_is_determined_from_live_proc(self):
        self.assertEqual(guard.parse_uid("Name:\twolo\nUid:\t0\t0\t0\t0\n"),(0,0,0,0))
        self.assertEqual(guard.parse_uid("Uid:\t1000\t1000\t1000\t1000\n")[1],1000)
        self.assertHold(guard.parse_uid,"Name:whatever")

    def test_financial_connect_only_allowlist(self):
        self.assertHold(guard.net_connect,8094,"root")
        self.assertHold(guard.net_connect,8092,"missinguser")
        with patch.object(guard,"run",return_value="1\n") as call:
            self.assertTrue(guard.net_connect(8092,"tony"))
            args=call.call_args.args[0]
            self.assertEqual(args[:5],["/usr/sbin/runuser","-u","tony","--","/usr/bin/python3"])
            self.assertIn("connect_ex",args[-2])
            self.assertNotIn(".send",args[-2])
        with patch.object(guard,"run",return_value="0\n"):
            self.assertFalse(guard.net_connect(27657,"root"))

    def test_transport_witness_never_passes_release(self):
        with patch.object(guard,"observe",return_value={"status":"HOLD","financial_release_authorized":False}):
            out=io.StringIO()
            with redirect_stdout(out):
                code=guard.main()
            self.assertEqual(code,3)
            self.assertFalse(json.loads(out.getvalue())["financial_release_authorized"])

    def test_fail_closed_stops(self):
        with patch.object(guard,"observe",side_effect=guard.Hold("HOST_MISMATCH")):
            out=io.StringIO()
            with redirect_stdout(out):
                code=guard.main()
            self.assertEqual(code,2)
            self.assertEqual(json.loads(out.getvalue())["status"],"STOP")

    def test_only_readonly_service_observation_and_connect(self):
        from pathlib import Path
        source=Path(guard.__file__).read_text()
        self.assertIn("financial_release_authorized",source)
        self.assertIn("bytes_sent_to_financial_services",source)
        self.assertIn("socket",source)
        self.assertIn("/usr/sbin/nft",source)
        self.assertIn("--no-pager",source)
        for forbidden in ("pg_terminate_backend(", "systemctl stop", "systemctl restart",
                          "ALTER ROLE ", "BEGIN PRIVATE KEY", "broadcast_tx_sync",
                          "eth_sendRawTransaction", "curl -X POST"):
            self.assertNotIn(forbidden,source)

if __name__=="__main__":
    unittest.main()
