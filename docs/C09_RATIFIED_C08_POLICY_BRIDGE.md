---
id: "aoe2war.wolochain.c09-ratified-c08-policy-bridge"
title: "C09 Ratified C08 Governance Bridge — Signed Canary Ceiling and No Spending"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["developers", "operators", "financial-reviewers", "ai-agents"]
source_of_truth: "git"
authority: "authenticated-C08-governance-preflight-only-no-spending-permit"
reviewed_at: "2026-11-08"
review_interval_days: 7
sensitivity: "restricted"
---

# C09 Ratified C08 Governance Bridge — Signed Canary Ceiling and No Spending

## Correct the missing governance-to-canary link

The earlier C09 reviewer authenticates a real one-human Ed25519 signature on an
exact proposed recipient, amount, fee, fresh claim ID, chain height, code,
binary and receipts, and intentionally returns HOLD. However it originally
accepted a caller-provided `governance_ratification_sha256` as syntax-only:
without verifying that an adopted policy receipt with that hash actually
exists or was signed by the historical owner.

After the source-qualified C08 one-human adoption V2 (WoloChain PR #215,
merge commit `2ca1d4d5090b129c7bf5b7326fba311d0d8c7532`),
`scripts/settlement_c09_exact_canary_intent_review_hold.py` now has a
**strict opt-in adoption-bound** `review_with_adopted_governance()` path.

It first independently verifies the real C09 one-transfer signed request
and its existing private, pinned, unrevoked owner enrollment. It requires
the same code-pinned owner public DER for C08, verifies the C08 adopted
receipt's original signature and SHA, checks the exact Git source-policy
identity from its original source commit, public notice and its 24-hour
maturity, and requires the **actual exact receipt SHA-256** to equal
the hash the C09 owner signed. No supplied JSON true/false flag can
substitute for the physical adopted receipt.

It then reads the source-pinned adopted policy, verifies the total of
**C09 amount + chain fee <= 1,000,000 uwolo (1 WOLO)**, and retains zero
standing financial permission, zero automatic retry and zero legacy 8092
fallback. A signed C09 request for more than this amount/fee ceiling,
a borrowed C08 receipt from another public key, forged source/public
notice, altered original C08 signature, bad owner directory modes or
different governance hash returns STOP. The existing signature-only
C09 observer stays available for read-only legacy diagnostics but
**is not a funding permit**.

## Operator input contract

The strict path takes existing original owner-signed C09 intent and enrollment
plus two additional pointers: `--c08-adopted-owner-root` and
`--c08-owner-public-key`. The former points to the original owner-only
C08 0700 root containing `adopted-governance-v2.json` (mode0600);
the latter points to the previous original owner PEM (mode0600). Both are
required together or neither. The complete C09 signed intent must carry
the exact SHA of the adopted receipt in `governance_ratification_sha256`;
C08's old nonfinancial direction and any unsigned proposal never qualify.

C08 currently has no automatic financial execution permission. This
preflight does **not** create or renew C01 custody permits, a reserve
review, signed Cosmos transaction, an off-host consumed nonce or any
HTTP/DB/website service. It does not assert that C01–C07 have passed,
that C09 recipient addresses are independently chain-checksummed, or
that bank roots and provenance are independently proved.

The eventual C09 **funded executor** must make this adopted C08
verification a **mandatory prerequisite**, not a caller-opted feature.
That executor remains separate from this non-authorizing review script.
Do not activate 8094/8095 based on this bridge alone.

## Test and release admission

`tests/test_settlement_c09_adopted_governance_binding.py` builds a
fresh original owner-like C08 adoption receipt using a disposable
real Ed25519 key and a source-controlled test notice, then signs a
**distinct** exact C09 canary request. It passes valid 700,000 uwolo
plus 1,000 fee, valid exactly 1,000,000 inclusive of zero fee, and
the original review HOLD with C08 absent. It rejects missing/altered/
replayed-source receipt, bad owner, changed public notice, mismatched
governance SHA, forged C09 transaction signature, over-ceiling amount,
over-ceiling fee, bad filesystem permissions and old claim IDs.

The separate owner-only command
`~/.wolo-owner-authority/run-c08-governance-adoption-v2.sh`
must complete a real encrypted-key owner signature and adopted receipt
before claiming that **C08** itself is complete. No test-only key or
simulated adoption may serve as production acceptance; never paste or
publish owner signed raw private packets, private keys or any passphrase.
