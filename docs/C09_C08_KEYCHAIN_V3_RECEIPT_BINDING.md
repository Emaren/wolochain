---
id: "aoe2war.wolochain.c09-c08-keychain-v3-receipt-binding"
title: "C09 Exact Canary Requires Genuine Keychain C08 V3 Receipt"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["operators", "developers", "financial-reviewers"]
source_of_truth: "git"
authority: "nonfunding-C08-policy-preflight-only"
reviewed_at: "2026-11-08"
review_interval_days: 7
sensitivity: "restricted"
---

# C09 Exact Canary Requires Genuine Keychain C08 V3 Receipt

The previous C09 cross-gate checker could only recognize the original
unratified C08 Ed25519 V2 key. That private key failed to decrypt during
the owner's November 8 signing attempt. It is preserved; it cannot be
silently replaced with an ECDSA signature or claimed to have signed the
new policy.

The owner instead authorized a **new login-Keychain software ECDSA P-256
owner governance signer**, with public X9.63 digest
`f9f76deb8ba61b8f4b4f8e5b434acc11fa95630ccb19306a71e8bff0dc6fb826`.
The new key identity and limitations are disclosed in GitHub issue #184,
comment 6727529299. The original owner governance key is historical,
*not* cryptographically cross-signed to the new identity.

`scripts/settlement_c09_exact_canary_intent_review_hold.py` now
provides `qualify_c09_request_against_keychain_governance_v3()`.
It independently verifies the original committed, owner-private
`adopted-governance-v3.json` under
`~/.wolo-owner-authority/c08-keychain-policy-v3` through the exact
v3 source/policy/public-notice/GitHub-enrollment/ECDSA verifier,
checks that the current standing financial allowance is **zero**,
and requires the exact adopted receipt SHA-256 inside the C09
transaction-specific request. Even a real transaction-specific
signature cannot replace a missing C08 receipt.

The signed canary amount **plus fee** must be within the source-fixed
1,000,000 uwolo (1 WOLO) prospective first-canary ceiling. The
original C09 syntax checks still reject old claim IDs, malformed
fresh IDs, 8092 fallback, retry on UNKNOWN, false independent reviewers
and source/bank/backup/fence proof hash omissions.

`review_with_keychain_governance_v3` is a convenience for the old
read-only *Ed25519* C09 exact-intent reviewer, but it must **not** be
mistaken for C09 final execution: the future C09 transaction-specific
signing key must be independently enrolled and may use another
algorithm. The new pure v3 governance qualifier does not itself prove
a C09 transaction-specific signature, a Cosmos address checksum, actual
funded escrow, off-host one-use nonce consumption, C01–C07 acceptance,
or final native chain execution.

CLI inputs `--c08-keychain-v3-owner-root` and
`--c08-keychain-v3-owner-public-x963` activate strict v3 proof
when using the old read-only signed-C09 reviewer. Both are required
together; combining v2 and v3 signer paths is rejected. No legacy
unsigned-C09 `governance_ratification_sha256` can become an accepted
funded permit on its own.

Thirteen disposable P-256 ECDSA and fake C09 intent tests prove
real receipt success, missing/altered signature detection, wrong
GitHub author, wrong receipt SHA, amount and fee > 1 WOLO denial,
old claim refusal, no legacy 8092, no UNKNOWN retry, and repeated
confirmation that **C09 financial_release_authorized=false**.
The original C08 v2 tests and original C09 signed-intent tests remain.
Nothing in this source activates 8094/8095 or moves WOLO.

A C09 funded executor must enforce this proof **and** a separate
current exact owner transaction-signature enrollment, original
trusted bank/consensus proof, accepted C01–C07 real physical receipts,
and the off-host consumed nonce before any payment authorization.
