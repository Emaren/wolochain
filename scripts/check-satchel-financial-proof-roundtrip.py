#!/usr/bin/env python3
"""Real isolated SDK execution -> portable Comet proof -> offline HD bridge.

No production sources, keyrings, wallets, database, listeners or clock overrides.
Build before exporting the short-lived proof; every verification uses real time.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent.parent


def run(command, **kwargs):
    return subprocess.run(command, cwd=ROOT, check=True, capture_output=True,
                          text=True, timeout=300, **kwargs)


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    path.chmod(0o600)


def main():
    with tempfile.TemporaryDirectory(prefix="wolo-financial-proof-") as tmp:
        directory = Path(tmp).resolve()
        binary = directory / "wolosatcheld"
        run(["go", "build", "-tags=go1.27", "-mod=readonly", "-o", str(binary),
             "./cmd/wolosatcheld"])
        environment = os.environ.copy()
        environment["SATCHEL_PROOF_FIXTURE_DIR"] = str(directory)
        run(["go", "test", "-tags=go1.27", "./internal/satchel", "-run",
             "^TestAuthenticatedProofFromIsolatedSDKExecution$", "-count=1"],
            env=environment)
        fixture = json.loads((directory / "isolated-sdk-proof.json").read_text())
        assert fixture["fixture_only"] and not fixture["mainnet_authority"]
        intent = fixture["intent"]
        observation = fixture["deposit_observation"]
        receipt = fixture["deposit_receipt"]
        signatures = json.loads((ROOT / "internal/satchelservice/testdata/financial-bridge-v1.json").read_text())
        authority = {"trust_anchor": fixture["anchor"], "vault": intent["Vault"],
                     "betting_escrow": signatures["betting_escrow"],
                     "approval_public_key_hex": signatures["approval_public_key_hex"]}
        # This is an independently expected fixture intent, not response.context.
        # Order matches FinancialProofContext's published fixed Go struct order.
        expected = {"protocol": 1, "kind": "deposit", "owner_id": intent["OwnerID"],
                    "sender": intent["Sender"], "recipient": intent["Vault"],
                    "amount_uwolo": intent["AmountUWolo"], "memo": intent["Memo"],
                    "tx_hash": observation["TxHash"], "created_at": intent["CreatedAt"],
                    "expires_at": intent["ExpiresAt"]}
        digest = hashlib.sha256(json.dumps(expected, ensure_ascii=False,
                                          separators=(",", ":")).encode()).hexdigest()
        envelope = {"protocol": 1, "chain_id": "wolo-1", "denom": "uwolo",
                    "context": expected, "context_digest": digest,
                    "tx_hash": observation["TxHash"],
                    "receipt_id": f"wolo-1:{receipt['TxHash']}:{receipt['TransferIndex']}",
                    "transfer_index": receipt["TransferIndex"], "message_index": 0,
                    "height": observation["Height"], "block_hash": observation["BlockHash"],
                    "consensus_authenticated": True, "credit_authorized": False,
                    "proof": fixture["deposit_proof"]}
        authority_path = directory / "authority.json"
        expected_path = directory / "expected.json"
        proof_path = directory / "proof.json"
        write(authority_path, authority)
        write(expected_path, expected)
        write(proof_path, envelope)
        command = [str(binary), "verify-financial-proof", "--authority", str(authority_path),
                   "--expected", str(expected_path), "--proof", str(proof_path)]
        verified = json.loads(run(command).stdout)
        assert verified["tx_hash"] == expected["tx_hash"]
        assert verified["owner_id"] == expected["owner_id"]
        assert verified["receipt_id"] == envelope["receipt_id"]
        assert verified["context_digest"] == digest and verified["credit_authorized"] is False
        # Re-verification is read-only and produces the same identity; only HD's
        # separate global durable ledger claim can consume this physical receipt.
        assert json.loads(run(command).stdout) == verified
        for case in ("wrong expected hash", "wrong expected owner", "wrong trust root", "forged REST only"):
            bad_expected, bad_authority, bad_proof = copy.deepcopy(expected), copy.deepcopy(authority), copy.deepcopy(envelope)
            if case == "wrong expected hash":
                bad_expected["tx_hash"] = "F" * 64
            elif case == "wrong expected owner":
                bad_expected["owner_id"] = "forged-owner"
            elif case == "wrong trust root":
                bad_authority["trust_anchor"]["hash"] = "F" * 64
            else:
                bad_proof["proof"]["responses"] = [{"source": "rest", "path": "/cosmos/tx/v1beta1/txs/" + expected["tx_hash"], "query": "", "body": {"tx_response": {"txhash": expected["tx_hash"], "height": str(observation["Height"]), "code": 0}}}]
            write(expected_path, bad_expected)
            write(authority_path, bad_authority)
            write(proof_path, bad_proof)
            rejected = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
            assert rejected.returncode == 2 and not rejected.stdout, case
            assert "UNVERIFIABLE" in rejected.stderr, case
        # Export AFTER the binary build and financial roundtrip so the native
        # SDK bank observation is genuinely fresh at the offline CLI boundary.
        # This continuous fixture includes actual IAVL state and Comet AppHash
        # commitments. The fixed-date bank unit fixture cannot replace it.
        environment.pop("SATCHEL_LIFECYCLE_RECIPE", None)
        environment["SATCHEL_LIFECYCLE_FIXTURE_DIR"] = str(directory)
        run(["go", "test", "-tags=go1.27", "./internal/satchel", "-run",
             "^TestAuthenticatedContinuousSDKLifecycle/full_unmatched_refund$",
             "-count=1"], env=environment)
        lifecycle = json.loads((directory / "full_unmatched_refund" /
                                "isolated-sdk-lifecycle.json").read_text())
        assert lifecycle["fixture_only"] and not lifecycle["mainnet_authority"]
        assert lifecycle["production_custody_available"] is False
        step = lifecycle["steps"][0]
        assert step["name"] == "deposit"
        bank_authority = {
            "trust_anchor": lifecycle["anchor"],
            "vault": lifecycle["roles"]["vault"],
            "betting_escrow": lifecycle["roles"]["escrow"],
            "approval_public_key_hex": signatures["approval_public_key_hex"],
        }
        bank_proof = step["vault_bank_proof"]
        bank_proof_path = directory / "bank-proof.json"
        write(authority_path, bank_authority)
        write(bank_proof_path, bank_proof)
        bank_command = [str(binary), "verify-bank-proof", "--authority",
                        str(authority_path), "--height", str(step["height"]),
                        "--proof", str(bank_proof_path)]
        bank = json.loads(run(bank_command).stdout)
        assert bank["protocol"] == 1
        assert bank["status"] == "AUTHENTICATED_BANK_NONAUTHORIZING"
        assert bank["chain_id"] == "wolo-1" and bank["denom"] == "uwolo"
        assert bank["vault"] == bank_authority["vault"]
        assert bank["balance_uwolo"] == step["vault_balance_uwolo"] == "100000100"
        assert bank["height"] == step["height"]
        assert bank["commit_height"] == step["height"] + 1
        commits = [r["body"]["result"]["signed_header"]["header"]
                   for r in bank_proof["responses"]
                   if r["path"] == "/commit" and
                   r["query"] == f"height={bank['commit_height']}"]
        assert commits and all(h["app_hash"] == bank["app_hash"] for h in commits)
        assert len(bank["block_hash"]) == len(bank["app_hash"]) == 64
        assert bank["credit_authorized"] is False
        assert bank["spending_authorized"] is False
        assert bank["solvency_authorized"] is False
        assert json.loads(run(bank_command).stdout) == bank
        for case in ("wrong bank root", "wrong bank vault", "wrong bank height",
                     "forged bank REST only"):
            bad_authority = copy.deepcopy(bank_authority)
            bad_proof = copy.deepcopy(bank_proof)
            bad_command = list(bank_command)
            if case == "wrong bank root":
                bad_authority["trust_anchor"]["hash"] = "F" * 64
            elif case == "wrong bank vault":
                bad_authority["vault"] = lifecycle["roles"]["owner"]
            elif case == "wrong bank height":
                bad_command[bad_command.index("--height") + 1] = str(step["height"] + 1)
            else:
                bad_proof["responses"] = [{
                    "source": "rest", "path": "/cosmos/bank/v1beta1/balances/" + bank_authority["vault"],
                    "query": "", "body": {"balances": [{"denom": "uwolo", "amount": "100000100"}]},
                }]
            write(authority_path, bad_authority)
            write(bank_proof_path, bad_proof)
            rejected = subprocess.run(bad_command, cwd=ROOT, capture_output=True,
                                      text=True, timeout=30)
            assert rejected.returncode == 2 and not rejected.stdout, case
            assert "UNVERIFIABLE" in rejected.stderr, case
        print("PASS: real isolated SDK execution and portable Comet financial proof; "
              "fresh native bank/IAVL AppHash proof verified at exact H/H+1; "
              "identical read-only receipts; eight forged-context/root/vault/height/REST "
              "cases rejected; no credit, spending or solvency authority")


if __name__ == "__main__":
    main()
