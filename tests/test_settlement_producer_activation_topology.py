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
        self.assertFalse(report["cutoverAuthorized"])

    def test_timer_without_service_specific_pid_or_restart_properties_is_still_live(self):
        # systemd timer types can omit these service-only fields completely.
        raw="\n".join(line for line in show(TIMER).splitlines()
                      if not line.startswith(("MainPID=", "Restart=")))+"\n"
        got=MOD.parse_show(raw,TIMER)
        self.assertTrue(got["activeObserved"])
        self.assertFalse(got["mainPidPresent"])
        self.assertFalse(got["restartConfigured"])
        self.assertIn(SERVICE,got["relations"]["Triggers"])
        self.assertFalse(got["safeToStop"])

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

    def test_installed_native_financial_successors_are_not_invisible(self):
        custody="wolo-satchel-c01.service"
        reviewer="wolo-reviewer-c01.service"
        raw=(f"{reviewer} loaded inactive dead Reviewer\n"
             f"{custody} loaded inactive dead Custody\n"
             "wolochaind-mainnet.service loaded active running Protected\n")
        names=MOD.discover(raw)
        self.assertEqual(names,sorted([custody,reviewer]))
        installed=MOD.discover_installed(
            f"{custody} static -\n{reviewer} static -\n"
            "wolochaind-mainnet.service enabled enabled\n")
        self.assertEqual(installed,names)
        observations=[MOD.parse_show(show(name,ActiveState="inactive",
                          UnitFileState="static",MainPID="0"),name)
                      for name in names]
        report=MOD.topology(names,observations,installed=installed)
        self.assertEqual(report["nativeCustodyReviewerSuccessorsObserved"], names)
        self.assertEqual(report["nativeSuccessorsInstalledButNotLoaded"],[])
        self.assertEqual(report["newOrUnmappedUnits"],[])
        self.assertEqual(report["installedButNotLoadedExpectedUnitNames"],[])
        self.assertEqual(report["notInstalledExpectedUnitNames"],
                         sorted(MOD.EXPECTED-set(names)))
        self.assertTrue(all(x["owner"] in ("WOLO_CUSTODY","WOLO_REVIEWER")
                            for x in report["units"]))
        self.assertFalse(report["nativeSuccessorsAreFinancialWritersExcluded"])
        self.assertFalse(report["financialIngressFenced"])
        self.assertFalse(report["satchelActivationAuthorized"])

    def test_new_web_and_release_observers_are_known_not_fenced(self):
        units = sorted([
            "aoe2hdbets-web-prod.service",
            "aoe2hdbets-web-r24.service",
            "aoe2war-estate-observe.service",
            "aoe2war-release-readiness-observer.service",
            "aoe2war-release-readiness-observer.timer",
            "aoe2war-steam-egress-refresh.service",
            "aoe2war-steam-egress-refresh.timer",
        ])
        self.assertTrue(set(units).issubset(MOD.EXPECTED))
        observations = [MOD.parse_show(show(name, MainPID="123" if
                        name.endswith(".service") else "0"), name)
                        for name in units]
        report = MOD.topology(units, observations, installed=units)
        self.assertEqual(report["newOrUnmappedUnits"], [])
        self.assertFalse(report["financialIngressFenced"])
        self.assertFalse(report["cutoverAuthorized"])
        self.assertFalse(report["satchelActivationAuthorized"])
        self.assertTrue(all(
            not u["safeToStop"] and not u["paymentCapabilityExcluded"]
            and not u["sourceRuntimeParityProven"]
            for u in report["units"]))

    def test_unloaded_native_successor_is_not_silently_excluded(self):
        report=MOD.topology([TIMER],[MOD.parse_show(show(TIMER),TIMER)],
                            installed=sorted([TIMER,"wolo-reviewer-c01.service"]))
        self.assertIn("wolo-reviewer-c01.service",
                      report["installedButNotLoadedExpectedUnitNames"])
        self.assertEqual(report["nativeSuccessorsInstalledButNotLoaded"],
                         ["wolo-reviewer-c01.service"])
        self.assertIn("wolo-satchel-c01.service",
                      report["notInstalledExpectedUnitNames"])
        self.assertFalse(report["nativeSuccessorsAreFinancialWritersExcluded"])
        self.assertEqual(report["status"],"HOLD")

    def test_unexpected_unit_remains_named_and_review_required(self):
        x="aoe2hdbets-new-payer.timer"
        result=MOD.topology([x],[MOD.parse_show(show(x),x)])
        self.assertEqual(result["newOrUnmappedUnits"],[x])
        self.assertFalse(result["cutoverAuthorized"])

    def test_installed_static_unit_is_not_missing_service_file(self):
        loaded=[TIMER]
        observations=[MOD.parse_show(show(TIMER),TIMER)]
        static="aoe2hdbets-bet-stake-reconcile-plan.service"
        installed=sorted([TIMER,static])
        report=MOD.topology(loaded,observations,installed=installed)
        self.assertTrue(report["installedUnitFileInventoryObserved"])
        self.assertIn(static,report["expectedAbsentUnitNames"])
        self.assertIn(static,report["installedButNotLoadedExpectedUnitNames"])
        self.assertNotIn(static,report["notInstalledExpectedUnitNames"])
        self.assertIn(static,report["installedUnitFilesNotLoaded"])
        self.assertIs(report["systemdUnitAndUnitFileInventoryAtomic"],False)
        self.assertIs(report["financialIngressFenced"],False)
        self.assertIs(report["cutoverAuthorized"],False)

    def test_uninstalled_expected_is_distinct_from_installed_but_unloaded(self):
        report=MOD.topology([TIMER],[MOD.parse_show(show(TIMER),TIMER)],
                            installed=[TIMER])
        self.assertEqual(report["installedButNotLoadedExpectedUnitNames"],[])
        self.assertIn("aoe2hdbets-bet-stake-reconcile-plan.service",
                      report["notInstalledExpectedUnitNames"])
        self.assertEqual(report["status"],"HOLD")

    def test_unit_file_parser_rejects_secret_paths_and_duplicate_or_unsafe_state(self):
        raw=("aoe2hdbets-web.service enabled enabled\n"
             "aoe2hdbets-bet-stake-reconcile-plan.service static -\n"
             "wolochaind-mainnet.service enabled enabled\n")
        installed=MOD.discover_installed(raw)
        self.assertEqual(installed,[
            "aoe2hdbets-bet-stake-reconcile-plan.service",
            "aoe2hdbets-web.service",
        ])
        for item in (
            "aoe2hdbets-web.service unknown-magic -\n",
            "aoe2hdbets-web.service enabled -\n"
            "aoe2hdbets-web.service enabled -\n",
            "aoe2hdbets-web.service /tmp/private.env -\n",
            "aoe2hdbets-../../etc/passwd.service static -\n",
        ):
            with self.subTest(item=item),self.assertRaises(MOD.TopologyError):
                MOD.discover_installed(item)

    def test_new_unmapped_unit_stays_visible_even_if_installed(self):
        unknown="aoe2hdbets-new-payer.timer"
        report=MOD.topology([unknown],[MOD.parse_show(show(unknown),unknown)],
                            installed=[unknown])
        self.assertEqual(report["newOrUnmappedUnits"],[unknown])
        self.assertFalse(report["satchelActivationAuthorized"])
        self.assertFalse(report["paymentsReconciled"])

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
            if args[0]=="list-unit-files":
                return ("aoe2hdbets-web.service enabled enabled\n"
                        "aoe2hdbets-bet-stake-reconcile-plan.service static -\n")
            raise AssertionError("unexpected command")
        with patch.object(MOD,"run",side_effect=fake):
            report=MOD.inspect()
        self.assertEqual(report["unitsObserved"],1)
        self.assertEqual(len(calls),3)
        self.assertEqual(calls[-1][0],"list-unit-files")
        self.assertIn("aoe2hdbets-bet-stake-reconcile-plan.service",
                      report["installedButNotLoadedExpectedUnitNames"])
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
