#!/usr/bin/env python3
"""Fresh real SDK/Comet fixture -> held native v3 policy/journal acceptance.

Build before exporting proofs. Only disposable in-memory chain state and test
keys are used; no production keyring, network, database or signing authority.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
EPOCH = "test_epoch_20261026"
ENTITLEMENT = f"satchel:e3:{EPOCH}:entitlement:77:200:11"
VOID_ENTITLEMENT = f"satchel:e3:{EPOCH}:entitlement:78:200:12"


def run(command, environment):
    result = subprocess.run(command, cwd=ROOT, env=environment, text=True,
                            capture_output=True, timeout=300, check=False)
    if result.returncode:
        # Go test output contains test diagnostics, never fixture key contents.
        raise RuntimeError(result.stdout + result.stderr)
    return result


def main():
    with tempfile.TemporaryDirectory(prefix="wolo-epoch-native-v3-") as tmp:
        directory = Path(tmp).resolve()
        environment = os.environ.copy()
        if not environment.get("WOLO_EPOCH_SOURCE_COMMIT"):
            environment["WOLO_EPOCH_SOURCE_COMMIT"] = run(
                ["git", "rev-parse", "HEAD"], environment).stdout.strip()
        binary = directory / "epoch-v3.test"
        run(["go", "test", "-tags=go1.27", "-mod=readonly", "-c", "-o",
             str(binary), "./internal/epochescrow"], environment)
        recipe = {"version": 1, "scenario": "native_epoch_v3", "steps": [
            {"name": "deposit", "sender_role": "owner", "recipient_role": "vault",
             "amount_uwolo": "100000000", "memo": "disposable-epoch-v3-deposit"},
            {"name": "opponent_deposit", "sender_role": "opponent", "recipient_role": "vault",
             "amount_uwolo": "40000000", "memo": "disposable-epoch-v3-opponent-deposit"},
            {"name": "funding_one", "sender_role": "vault", "recipient_role": "escrow",
             "amount_uwolo": "100000000", "memo": f"aoe2war/satchel/epoch-v3/{EPOCH}/ticket/200"},
            {"name": "funding_two", "sender_role": "vault", "recipient_role": "escrow",
             "amount_uwolo": "40000000", "memo": f"aoe2war/satchel/epoch-v3/{EPOCH}/ticket/300"},
            {"name": "epoch_return", "sender_role": "escrow", "recipient_role": "vault",
             "amount_uwolo": "78000000", "memo": f"aoe2war/satchel/epoch-v3/{EPOCH}/return/{ENTITLEMENT}"},
            {"name": "epoch_fee", "sender_role": "escrow", "recipient_role": "fee_recipient",
             "amount_uwolo": "2000000", "memo": f"aoe2war/satchel/epoch-v3/{EPOCH}/fee/{ENTITLEMENT}"},
            {"name": "epoch_void_return", "sender_role": "escrow", "recipient_role": "vault",
             "amount_uwolo": "60000000", "memo": f"aoe2war/satchel/epoch-v3/{EPOCH}/return/{VOID_ENTITLEMENT}"},
        ]}
        recipe_path = directory / "recipe.json"
        recipe_path.write_text(json.dumps(recipe))
        recipe_path.chmod(0o600)
        environment["SATCHEL_LIFECYCLE_RECIPE"] = str(recipe_path)
        environment["SATCHEL_LIFECYCLE_FIXTURE_DIR"] = str(directory)
        run(["go", "test", "-tags=go1.27", "-mod=readonly", "./internal/satchel",
             "-run", "^TestAuthenticatedContinuousSDKLifecycle$", "-count=1"], environment)
        environment["WOLO_EPOCH_NATIVE_FIXTURE"] = str(
            directory / "native_epoch_v3" / "isolated-sdk-lifecycle.json")
        result = run([str(binary), "-test.run=^TestNativeV3FeePayingProofPreparationAndObservation$",
                      "-test.v"], environment)
        print(result.stdout, end="")
        print("PASS: one original 100-WOLO ticket conserves 40+60 market legs; matched return78/fee2 and void return60 use genuine MsgSend0; legacy event1 unchanged; production execution HELD")


if __name__ == "__main__":
    main()
