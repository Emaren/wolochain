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
        bank_height = bank_proof["height"]
        assert bank_height == step["head_height"] - 1
        bank_proof_path = directory / "bank-proof.json"
        write(authority_path, bank_authority)
        write(bank_proof_path, bank_proof)
        bank_command = [str(binary), "verify-bank-proof", "--authority",
                        str(authority_path), "--height", str(bank_height),
                        "--proof", str(bank_proof_path)]
        bank = json.loads(run(bank_command).stdout)
        assert bank["protocol"] == 1
        assert bank["status"] == "AUTHENTICATED_BANK_NONAUTHORIZING"
        assert bank["chain_id"] == "wolo-1" and bank["denom"] == "uwolo"
        assert bank["vault"] == bank_authority["vault"]
        assert bank["balance_uwolo"] == step["vault_balance_uwolo"] == "100000100"
        assert bank["height"] == bank_height
        assert bank["commit_height"] == bank_height + 1 == step["head_height"]
        assert bank["head_height"] == step["head_height"]
        assert bank["height"] == bank["head_height"] - 1
        assert bank["head_time"] == step["observation"]["Head"]["BlockTime"]
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
                bad_command[bad_command.index("--height") + 1] = str(bank_height + 1)
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
        # The Go fixture signs the production domain-separated reservation with
        # an isolated reviewer key, independently from withdrawal/return review.
        # It first exercises VerifyFinancialProof itself, then exports public
        # inputs for a second pass through the actual offline executable.
        environment["SATCHEL_WAGER_SDK_FIXTURE"] = str(
            directory / "full_unmatched_refund" / "isolated-sdk-lifecycle.json")
        environment["SATCHEL_WAGER_ROUNDTRIP_DIR"] = str(directory)
        run(["go", "test", "-tags=go1.27", "./internal/satchelservice", "-run",
             "^TestOfflineFinancialWagerProofFromCommittedSDKFixture$",
             "-count=1"], env=environment)
        wager_authority_path = directory / "wager-authority.json"
        wager_expected_path = directory / "wager-expected.json"
        wager_proof_path = directory / "wager-proof.json"
        wager_expected = json.loads(wager_expected_path.read_text())
        wager_proof = json.loads(wager_proof_path.read_text())
        wager_authority = json.loads(wager_authority_path.read_text())
        assert wager_authority["wager_approval_public_key_hex"] != wager_authority["approval_public_key_hex"]
        # Execution identity and canonical ticket identity are deliberately
        # distinct; they are exactly bound by the independently signed grant.
        assert wager_expected["operation_id"] == "satchel:ticket:777"
        assert wager_expected["memo"] == "AoE2HDBets bet ticket v1 · ticket 1"
        wager_command = [str(binary), "verify-financial-proof", "--authority",
                         str(wager_authority_path), "--expected",
                         str(wager_expected_path), "--proof", str(wager_proof_path)]
        wager = json.loads(run(wager_command).stdout)
        assert wager["kind"] == "wager" and wager["credit_authorized"] is False
        assert wager["operation_id"] == wager_expected["operation_id"]
        assert wager["owner_id"] == wager_expected["owner_id"]
        assert wager["tx_hash"] == wager_expected["tx_hash"]
        assert wager["receipt_id"] == wager_proof["receipt_id"]
        assert wager["context_digest"] == wager_proof["context_digest"]
        assert json.loads(run(wager_command).stdout) == wager
        wager_cases = json.loads((directory / "wager-negative-cases.json").read_text())
        assert len(wager_cases) == 10
        assert {c["name"] for c in wager_cases} == {
            "missing_wager_key", "wrong_wager_key", "withdrawal_key_in_wager_role",
            "colliding_approval_keys", "withdrawal_signature_is_not_wager_approval",
            "wrong_owner", "wrong_signed_fee", "wrong_signed_ticket_memo",
            "wrong_signed_amount", "wrong_trust_root",
        }
        for case in wager_cases:
            write(wager_authority_path, case["authority"])
            write(wager_expected_path, case["expected"])
            write(wager_proof_path, case["proof"])
            rejected = subprocess.run(wager_command, cwd=ROOT, capture_output=True,
                                      text=True, timeout=30)
            assert rejected.returncode == 2 and not rejected.stdout, case["name"]
            assert "UNVERIFIABLE" in rejected.stderr, case["name"]
        print("PASS: real isolated SDK deposit and independently approved wager "
              "verified through native financial verifier and offline CLI; "
              "fresh native bank/IAVL AppHash proof verified at exact H/H+1; "
              "identical read-only receipts; eighteen forged-role/context/fee/memo/root/vault/height/REST "
              "cases rejected; no credit, spending or solvency authority")


if __name__ == "__main__":
    main()
