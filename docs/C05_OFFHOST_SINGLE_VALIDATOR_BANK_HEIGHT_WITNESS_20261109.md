---
id: "aoe2war.wolochain.c05-offhost-fixed-bank-height-20261109"
title: "C05 Offhost Fixed Bank Height: Single-Validator Source-Bound Witness"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["operators", "developers", "financial-reviewers", "ai-agents"]
source_of_truth: "git"
authority: "offhost-single-validator-historical-commit-consistency-no-funding"
reviewed_at: "2026-11-09"
review_interval_days: 7
sensitivity: "restricted"
---

# C05 Offhost Fixed Bank Height: Single-Validator Source-Bound Witness

Formal C05 is OPEN. This permanently source-pinned read-only observer provides a private owner-Mac witness that the historical 24-wallet bank census is still consistent with the historical block and recorded commit returned by the ONE existing WoloChain validator. This is not a second validator, independent quorum, independent cryptographic signature verification, a refreshed bank balance census, signer/collateral control, or payment finality.

## Source and trust boundary

Script: scripts/settlement_c05_single_validator_offhost_bank_height_witness.py. Census file SHA256 is hard-pinned as 148b9d9aa46b01eafd3804a1603d954f2bbaaffe282755e430a288dbc815159d, height 2886568 and network wolo-1. A different census requires a freshly reviewed and repinned source version; it cannot silently replace original financial evidence.

Run the script on the owner's Mac with host-key-checked SSH to HEL1. A fixed Python -I -B snippet reads ONLY the known census file and public RPC endpoints /status, /block, /commit and /validators through 127.0.0.1:27657. Nothing is written to HEL1. The local observer stores one exclusive 0600 receipt in a 0700 directory; original claim-level and wallet keys never leave HEL1. No SQL, signer, role, firewall, systemd, wallet or financial transaction changes are implemented.

Acceptance verifies source SHA, height, historical block ID, app hash, validator-set hash, exact ONE historical validator, matching one signed-commit RECORD and a current non-catching-up source. It does not independently verify Ed25519 signature bytes or establish an off-host second authoritative chain. The source is fixed-height, forensic, and does not claim indefinite future reserve solvency.

## Real physical receipt

On November 9, 2026 the historical block 2886568 was still present on HEL1. Block hash 18CDE084F52EEFC9C7039B924B2B6239308409A3AECE3BA94382EB0B13F9815C matched the source census and recorded commit. Header app hash was 0AAF127DB766916F9A002A0095DFF8F500B45EB61DF3928F309A94E533A6ED77. The running validator was one validator on network wolo-1, non-catching-up, with block height increasing. The gross 24-wallet nominal was 87,639,451.200705 WOLO but the census admits ZERO spendable collateral.

SHA256 of exact reviewed script: 1e18cfe8aa60c7658e180c93613a7211bdc6ff6e2f1294a7d0b1147db9be1ab5. Eleven offline adversarial tests pass, including wrong chain, hash mismatch, mixed block height, missing commit signature, changed validator identity, absent reserve controls and unexpected census source bytes.

Sealed private owner-Mac receipt:

~/.local/share/aoe2war-c05-fixed-height-witness/c05-bank-height-2886568-final-reviewed-20261109.json

Receipt mode 0600. SHA256 e2aa1b1d07af3db59a6237db50c6e2530f2042aaae37f76e83101d55d662f4fd. Machine classification PASS_SAME_NODE_HISTORICAL_BLOCK_COMMIT_CONSISTENCY; formal financial_gate_closed=false; funding_authorized=false; independent_consensus_verified=false; eligible_unencumbered_reserves_proven_uwolo=0.

Earlier unsigned-source-pinned observer receipt SHA e2d31705cfb57f3741e668e994841dca98ba19bc1879e7231e2873de59c2337d is superseded for source-constrained review; keep both private.

## Reproduction

On an authorized owner Mac, from the root of the checked out source:

    umask 077
    python3 -I -B tests/test_settlement_c05_single_validator_offhost_bank_height_witness.py
    python3 -I -B scripts/settlement_c05_single_validator_offhost_bank_height_witness.py --live-ssh --private-receipt "$HOME/.local/share/aoe2war-c05-fixed-height-witness/new-unique-receipt.json"

Choose a new filename for each new observation. The local output directory must exist and be private. A second run with an existing target fails closed; no bank or claim data is posted to GitHub.

## Critical consequence

PASS: off-host source-bound historical same-node block/commit consistency and eleven adversarial tests. HOLD: genuinely independent bank/chain witness, cryptographic signature verification, signer-controlled pledged reserves, historical liability disjointness, C05 solvency admission, C06/C07 recovery and C09 funds. Session A must still prove actual eligible collateral and approved claim scope at an exact bank height. This tool does not permit funding or a financial gate closure.
