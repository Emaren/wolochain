---
id: "aoe2war.wolochain.c08-existing-owner-device-direction-hold"
title: "C08 Verified Owner Device Direction: Historical Ed25519 Signature Is Not Governance Ratification"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war", "aoe2dewarwagers"]
audience: ["operators", "developers", "financial-reviewers", "ai-agents"]
source_of_truth: "git"
authority: "historical-owner-device-signature-readonly-evidence-only-no-funding"
reviewed_at: "2026-11-08"
review_interval_days: 7
sensitivity: "restricted"
---

# C08 Verified Owner Device Direction: Historical Ed25519 Signature Is Not Governance Ratification

## Problem and scope

On November 7, 2026 the owner signed a real Ed25519 **nonfinancial governance direction**, source-bound to the earlier single-human proposal. Its meaning is **centralized direction only**, not custody, governance runtime ratification, fresh financial transaction signing, or a waiver of C01–C09.

C08's existing newly merged `settlement_c08_signed_ratification_intent_hold.py` has a **different** domain and a 120-second window. That script correctly returns HOLD even when a real signature verifies: it does not implement the new runtime or independently pin a funded owner identity. C09 has still another domain and requires exact recipient, amount, bank/chain heights and 11 independent proof hashes from already accepted gates.

It would be unsafe to use any historic owner signature to infer a current C08 ratification or C09 funded permit. It would also be wasteful to request a 120-second owner-signed C09 canary before C03–C07 and C08 are accepted.

## What the new verifier actually does

`scripts/settlement_c08_existing_owner_direction_hold.py`:

- Parses the existing **root/owner-private mode0600** direction packet read-only; checks SHA256 against the review-time pinned physical artifact digest. No packet, signature bytes, public key or address is logged or uploaded.
- Requires exact signature domain `AOE2WAR-WOLO-SINGLE-HUMAN-NONFINANCIAL-GOVERNANCE-V2\0`, canonical request, real OpenSSL Ed25519 public-key verification and independently code-pinned public DER fingerprint. A self-attested `device_signature_verified` bit alone is never trusted.
- Requires source pin `e4cbd15d40f750f50cd92aeb71e78d69ddad2c6a`, owner-issued UTC November 7 10:10:27Z, full field allowlist and the SHA-pinned current proposal file.
- Explicitly refuses new financial authority, any funded amount, old 8092 fallback, fake independent-human assertions, a claim that owner performed new C09 transaction approval, changed policy text, missing/extra signed fields, substituted PEM/signature or spoofed ratification.
- Uses only disposable temporary public key/message/signature verification files; no Keychain access, private-key read, signer invocation, database or chain RPC, HTTP or financial service operation.

The physical M1 proof against the real owner-signed file must return exit **3**:
`HOLD_C08_VERIFIED_20261107_OWNER_DIRECTION_NOT_POLICY_RATIFICATION`.
A mismatched source/packet/signature returns **STOP exit 2**. Neither response is a funded permit.

### Exact private operator command (M1 only)

```bash
cd "$HOME/.cache/aoe2war/chain-c08-physical-owner-direction-20261108"
python3 -B scripts/settlement_c08_existing_owner_direction_hold.py \
  --owner-direction "$HOME/.wolo-owner-authority/solo-governance-adoption-keychain-v2/governance-direction-signed-device-v2.json"
```

Do not post or paste the original packet, public PEM or private Keychain labels into a public issue. Report only non-sensitive receipt digest, version and explicit HOLD flags. This read-only check never marks C08 accepted.

## Owner action: the *correct* next signature

The owner has authorized future legitimate financial governance adoption and an eventual C09 transaction-specific signature. Before asking for another signing ceremony, engineering must deliver a separately versioned **implemented and tested** one-human governance runtime policy, check real custody/reviewer technical role separation (not invented independent humans), confirm C03 writer isolation, C04 native claim finality, C05 solvency, C06+C07 exact restored capture, and independently enroll the owner signing fingerprint/off-host nonce witness. Public notice age alone is insufficient.

After those prerequisites, the human owner must inspect and sign the **exact new current-source C08 ratification** with a fresh nonce, and only later explicitly approve **one C09 recipient, amount, fee, bank height, digest bundle and 120-second expiry**. Do not generate or sign that transaction packet prematurely, invent a recipient, reuse a signature/nonce or authorize legacy 8092 fallback.

## Tests and production disposition

15 dedicated disposable real-Ed25519 positive/negative contract tests cover historical direction, changed unsigned source digest, malicious but validly signed money permission, duplicate provenance, fake independent reviewer, changed source, signature tampering, substituted public key, fake ratification and unknown fields. The physical original signature verification is separately executed under the owner-controlled M1, not in CI.

This is a **historical evidence closure** but **NOT formal C08 closure**. C01–C09 remain HARD HOLD; funded 8094/8095 stay closed, original 8092/8093 validator and all Session B website/Steam services are unaffected.
