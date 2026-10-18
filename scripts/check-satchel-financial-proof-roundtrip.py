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
        print("PASS: real isolated SDK bank execution and portable Comet proof verified by offline financial bridge; identical read-only receipt; four forged-context/root/REST cases rejected; no credit authority")


if __name__ == "__main__":
    main()
