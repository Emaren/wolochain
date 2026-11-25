#!/usr/bin/env python3
"""Sandbox-only, fault-injected simulation of the bdbce253 TWO-service code switch.

This has NO live operation mode, accepts NO filesystem destination argument,
uses only Python's TemporaryDirectory, never invokes systemctl, signers, RPC,
Postgres, SSH, or WoloChain. It models why both settlement processes must be
fenced and code-only recovery must leave durable payout request state intact.

Successful simulation is NOT a production rollback or watchdog certification.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import tempfile

PRIMARY = "wolochain-mainnet-settlement.service"
FOUNDER = "wolochain-founder-rewards-settlement.service"
NODE = "wolochaind-mainnet.service"
UNITS = (PRIMARY, FOUNDER)
OVERRIDE = "50-aoe2war-bdbce253-settlement-only.conf"
CANDIDATE = (
    "/mnt/HC_Volume_105319120/wolochain-mainnet/"
    "settlement-candidates/bdbce253-UNDEPLOYED/"
    "wolochaind-settlement-only-linux-amd64"
)
ORIGINAL = "/usr/local/bin/wolochaind-mainnet"
NODE_PROGRAM = "/usr/local/bin/wolochaind-mainnet-node-prewartrophy"
REVIEWED_SHA = "44d8aed5550d1b33635c734c1a359d0cb69e854093ef8c9a8a3da4f99d416ede"
ORIGINAL_SHA = "040126a2884946caf1651a50b7d8115c5a6fb2d5aa94fcbbe150694602d451a5"
NODE_SHA = "4b77f622191db7550cb87cafb8f1886a0aadebee3eb6565f9f90036f809e61d3"
# Test-only marker. It must never be interpreted as real verified financial proof.
FAKE_LEDGER = b'{"request_id":"test-only","status":"confirmed"}\n'
FAULTS = (
    "before_stop",
    "after_stop",
    "after_first_override",
    "after_second_override",
    "after_reload",
    "after_first_start",
    "after_second_start",
    "none",
)


def override_bytes() -> bytes:
    return (
        "# AOE2WAR bdbce253 two-settlement code-only; leave request/run state untouched\n"
        "[Service]\n"
        "ExecStart=\n"
        f"ExecStart={CANDIDATE} settlement serve\n"
    ).encode("utf-8")


@dataclass
class SimUnit:
    running: bool = True
    executable: str = ORIGINAL
    sha: str = ORIGINAL_SHA


class Rehearsal:
    """All path mutations are confined to a caller-created TemporaryDirectory."""

    def __init__(self, root: Path):
        if not root.is_dir():
            raise ValueError("sandbox root missing")
        self.root = root
        self.units = {name: SimUnit() for name in UNITS}
        self.consensus = (NODE, NODE_PROGRAM, NODE_SHA, 1009)
        self.payout_producers_fenced = True  # test fixture ONLY
        self.phase = "ORIGINAL"
        self.event_log: list[str] = []
        for name in UNITS:
            (root / "systemd" / f"{name}.d").mkdir(parents=True, exist_ok=False)
            state = root / "state" / name / "requests"
            state.mkdir(parents=True, exist_ok=False)
            (state / "test-only.json").write_bytes(FAKE_LEDGER)
        self.state_fingerprints = self.state_digest()
        self.consensus_start = self.consensus

    def state_digest(self) -> dict[str, str]:
        return {
            name: sha256(
                (self.root / "state" / name / "requests" / "test-only.json").read_bytes()
            ).hexdigest()
            for name in UNITS
        }

    def dropin(self, name: str) -> Path:
        if name not in UNITS:
            raise ValueError("service outside exact two-unit allowlist")
        return self.root / "systemd" / f"{name}.d" / OVERRIDE

    def assert_protected(self) -> None:
        assert self.consensus == self.consensus_start, "consensus identity modified"
        assert self.state_digest() == self.state_fingerprints, "payout request state modified"
        assert self.payout_producers_fenced, "payout producers were resumed"

    def assert_original(self) -> None:
        for name in UNITS:
            u = self.units[name]
            assert u.running and u.executable == ORIGINAL and u.sha == ORIGINAL_SHA
            assert not self.dropin(name).exists()
        self.assert_protected()

    def assert_candidate(self) -> None:
        for name in UNITS:
            u = self.units[name]
            assert u.running and u.executable == CANDIDATE and u.sha == REVIEWED_SHA
            assert self.dropin(name).read_bytes() == override_bytes()
        self.assert_protected()

    def fault(self, checkpoint: str, chosen: str) -> None:
        self.assert_protected()
        if chosen == checkpoint:
            raise RuntimeError(f"injected fault: {checkpoint}")

    def stop_both(self) -> None:
        if not self.payout_producers_fenced:
            raise RuntimeError("cannot stop settlement lanes before producer fence")
        for name in UNITS:
            self.units[name].running = False
        self.event_log.append("both_settlement_processes_stopped_test_only")

    def reload_mock(self) -> None:
        self.event_log.append("fake_systemd_reload_no_subprocess")

    def start(self, name: str, reviewed: bool) -> None:
        path = self.dropin(name)
        if reviewed:
            if path.read_bytes() != override_bytes():
                raise RuntimeError("unexpected override; do not start candidate")
            program, digest = CANDIDATE, REVIEWED_SHA
        else:
            if path.exists() or path.is_symlink():
                raise RuntimeError("override survived code-only rollback")
            program, digest = ORIGINAL, ORIGINAL_SHA
        unit = self.units[name]
        unit.running = True
        unit.executable = program
        unit.sha = digest

    def inspect_owned_overrides(self) -> None:
        for name in UNITS:
            path = self.dropin(name)
            if path.is_symlink():
                raise RuntimeError("unsafe symlink drop-in")
            if path.exists() and path.read_bytes() != override_bytes():
                raise RuntimeError("foreign override: manual review required")
        self.assert_protected()

    def recover_original(self) -> None:
        """Synthetic code-only rollback, never a live unit or bank action."""
        self.inspect_owned_overrides()
        self.stop_both()
        for name in UNITS:
            path = self.dropin(name)
            if path.exists():
                path.unlink()
        self.reload_mock()
        for name in UNITS:
            self.start(name, reviewed=False)
        self.phase = "ORIGINAL"
        self.assert_original()

    def try_promotion(self, fault_at: str = "none") -> bool:
        """Returns True for test-only candidate state; failure returns original state."""
        if fault_at not in FAULTS:
            raise ValueError("unrecognized fault injection point")
        self.assert_original()
        self.phase = "SWITCHING_TEST_ONLY"
        try:
            self.fault("before_stop", fault_at)
            self.stop_both()
            self.fault("after_stop", fault_at)
            self.dropin(PRIMARY).write_bytes(override_bytes())
            self.fault("after_first_override", fault_at)
            self.dropin(FOUNDER).write_bytes(override_bytes())
            self.fault("after_second_override", fault_at)
            self.reload_mock()
            self.fault("after_reload", fault_at)
            self.start(PRIMARY, reviewed=True)
            self.fault("after_first_start", fault_at)
            self.start(FOUNDER, reviewed=True)
            self.fault("after_second_start", fault_at)
            self.phase = "REVIEWED_TEST_ONLY"
            self.assert_candidate()
            return True
        except Exception:
            self.recover_original()
            raise


def run_all() -> dict:
    outcome = []
    for fault in FAULTS:
        with tempfile.TemporaryDirectory(prefix="wolo-bdbce253-sim-") as temp:
            sim = Rehearsal(Path(temp))
            if fault == "none":
                assert sim.try_promotion() is True
                sim.assert_candidate()
                sim.recover_original()
                sim.assert_original()
                recovered = True
            else:
                try:
                    sim.try_promotion(fault)
                except RuntimeError as exc:
                    if "injected fault:" not in str(exc):
                        raise
                else:
                    raise AssertionError(f"missing expected injection: {fault}")
                sim.assert_original()
                recovered = True
            sim.assert_protected()
            outcome.append({"scenario": fault, "recovered_test_only": recovered})
    return {
        "mode": "TEMPORARY_DIRECTORY_OFFLINE_SIMULATION",
        "simulated_scenarios": len(outcome),
        "scenario_results": outcome,
        "real_services_changed": False,
        "real_consensus_touched": False,
        "real_payout_state_touched": False,
        "live_rollback_rehearsed": False,
        "financial_drain_certified": False,
        "cutover_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulate-all", action="store_true")
    args = parser.parse_args()
    if not args.simulate_all:
        parser.error("only --simulate-all is supported; NO live action mode exists")
    print(json.dumps(run_all(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
