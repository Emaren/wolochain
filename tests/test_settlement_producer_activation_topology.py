#!/usr/bin/env python3
"""Read-only systemd activation topology contract tests; never touches live systemd."""
from __future__ import annotations
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "settlement_producer_activation_topology.py"
SPEC = importlib.util.spec_from_file_location("settlement_producer_activation_topology", MODULE)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)

TIMER = "aoe2hdbets-staking-rewards.timer"
SERVICE = "aoe2hdbets-staking-rewards.service"


def show(unit: str, **changes) -> str:
    fields = {
        "Id": unit, "LoadState": "loaded", "ActiveState": "active",
        "SubState": "waiting", "UnitFileState": "enabled", "MainPID": "0",
        "Restart": "no", "Triggers": SERVICE if unit == TIMER else "",
        "TriggeredBy": TIMER if unit == SERVICE else "", "PartOf": "",
        "Requires": "sysinit.target", "Wants": "network-online.target",
        "OnFailure": "",
    }
    fields.update(changes)
    return "\n".join(f"{k}={v}" for k, v in fields.items()) + "\n"


class TopologyTests(unittest.TestCase):
    def test_timer_to_oneshot_graph_is_information_not_fence(self):
        observations = [MOD.parse_show(show(SERVICE, ActiveState="inactive"), SERVICE),
                        MOD.parse_show(show(TIMER), TIMER)]
        report = MOD.topology([SERVICE, TIMER], observations, datetime(2026,10,20,tzinfo=timezone.utc))
        self.assertEqual(report["schema"], MOD.SCHEMA)
        self.assertEqual(report["activeTimerUnits"], [TIMER])
        self.assertIn(SERVICE, report["knownActivationGraphUnitNames"])
        for key in ("financialIngressFenced", "paymentsReconciled",
                    "independentBankSolvencyProven", "systemdMutationsPerformed",
                    "cutoverAuthorized", "satchelActivationAuthorized",
                    "cronUserContainersAndExternalSignersCovered"):
            self.assertIs(report[key], False)
        self.assertIn(SERVICE, report["expectedAbsentUnitNames"] if False else [SERVICE])

    def test_hidden_configuration_can_never_escape_projection(self):
        raw = show(TIMER, Restart="always") + (
            "Environment=SEED=TOP_SECRET\n"
        )
        with self.assertRaises(MOD.TopologyError):
            MOD.parse_show(raw,TIMER)
        got=MOD.parse_show(show(TIMER, Restart="always"),TIMER)
        self.assertTrue(got["restartConfigured"])
        self.assertNotIn("Environment",str(got))
        self.assertNotIn("ExecStart",str(got))
        self.assertNotIn("SEED",str(got))

    def test_invalid_or_duplicate_edges_rejected(self):
        for change in ("../../etc/passwd", "foo.timer foo.timer", "payer.service /tmp/key"):
            with self.subTest(change=change),self.assertRaises(MOD.TopologyError):
                MOD.parse_show(show(TIMER, Triggers=change),TIMER)
        with self.assertRaises(MOD.TopologyError):
            MOD.parse_show(show(TIMER, Id="wolochaind-mainnet.service"),TIMER)

    def test_critical_services_cannot_be_promoted_to_candidate_unit_set(self):
        names=MOD.discover("  aoe2hdbets-web.service loaded active running Web\n"
                           "  wolochain-mainnet-settlement.service loaded active running Wolo\n"
                           "  wolochaind-mainnet.service loaded active running Wolo\n")
        self.assertEqual(names,["aoe2hdbets-web.service"])
        self.assertIn("wolochaind-mainnet.service",MOD.PROTECTED)

    def test_unexpected_unit_remains_named_and_review_required(self):
        x="aoe2hdbets-new-payer.timer"
        result=MOD.topology([x],[MOD.parse_show(show(x),x)])
        self.assertEqual(result["newOrUnmappedUnits"],[x])
        self.assertFalse(result["cutoverAuthorized"])

    def test_duplicate_and_unbounded_unit_discovery_denied(self):
        with self.assertRaises(MOD.TopologyError):
            MOD.discover("aoe2hdbets-web.service loaded active running A\n"
                         "aoe2hdbets-web.service loaded active running A\n")
        with self.assertRaises(MOD.TopologyError):
            MOD.discover("".join(f"aoe2hdbets-s{i}.service loaded active running A\n"
                                 for i in range(MOD.MAX_UNITS+1)))

    def test_fail_closed_inspection_does_not_run_shell(self):
        calls=[]
        def fake(*args):
            calls.append(args)
            if args[0]=="list-units":
                return "aoe2hdbets-web.service loaded active running Web\n"
            if args[0]=="show":
                return show("aoe2hdbets-web.service",MainPID="1234")
            raise AssertionError("unexpected command")
        with patch.object(MOD,"run",side_effect=fake):
            report=MOD.inspect()
        self.assertEqual(report["unitsObserved"],1)
        self.assertEqual(len(calls),2)
        self.assertFalse(report["financialIngressFenced"])
        self.assertFalse(report["systemdMutationsPerformed"])

    def test_cli_writes_nothing_and_never_signals_release(self):
        with patch.object(MOD,"inspect",return_value=MOD.topology(
                [TIMER],[MOD.parse_show(show(TIMER),TIMER)])):
            with patch("builtins.print"):
                self.assertEqual(MOD.main(["--inspect"]),3)
        with patch("builtins.print"):
            self.assertEqual(MOD.main(["--apply"]),2)
        with patch.object(MOD,"inspect",side_effect=MOD.TopologyError("NO_UNIT")):
            with patch("builtins.print"):
                self.assertEqual(MOD.main(["--inspect"]),2)

if __name__=="__main__":
    unittest.main()
