---
id: "aoe2war.wolochain.c08-signed-solo-owner-ratification-intent-hold"
title: "C08 Real Owner-Signed Ratification Intent: Public Notice and Policy-Bound HOLD"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war", "aoe2dewarwagers"]
audience: ["operators", "developers", "financial-reviewers", "ai-agents"]
source_of_truth: "git"
authority: "source-only-cryptographic-ratification-intent-review-no-governance-adoption-or-woLo-funding"
reviewed_at: "2026-11-08"
review_interval_days: 7
sensitivity: "restricted"
---

# C08 Real Owner-Signed Ratification Intent: Public Notice and Policy-Bound HOLD

## Why the existing 24-hour public notice is not governance activation

The canonical public notice in Emaren/wolochain Issue #184 reached the
minimum 86,400-second publication age on **2026-11-08 10:22:33 UTC**.
That is only a verified publication period, not evidence that the current
five-person production constitution has been replaced or that the current
8094/8095 custody and review runtime supports a one-human permission model.

The canonical *proposed*, not adopted, source policy is
`docs/settlement-contracts/solo-owner-governance-proposal-20261106.json`.
It explicitly describes **one human** acting in the custody/reviewer/
release approval roles, and acknowledges this is NOT independent human
review. Distinct operator devices or AI systems are not additional humans.

Previously two reviewed read-only observers separately checked the public
notice source and the fixed policy proposal. A separate offline real
single-owner Ed25519 phase-intent verifier also existed. This new
source-only observer ties all three statements together without assuming
that one of them proves another.

## Exact ratification-review contract

`scripts/settlement_c08_signed_ratification_intent_hold.py`:

1. Validates the exact full machine-readable **PROPOSED_NOT_RATIFIED**
   policy using the canonical existing C08 proposal checker.
2. Revalidates the actual issue and public GitHub repository, including
   the pinned original notice content SHA256, source author, unchanged
   creation UTC and attained 24-hour maturity. Edited/closed/relocated
   notices fail.
3. Verifies a **fresh domain-separated Ed25519 signature**, with the
   existing real owner-enrollment and public DER fingerprint checking
   mechanism, on the exact policy source SHA256, original notice digest,
   URL and expiry. The domain is
   `AOE2WAR-WOLO-C08-OWNER-RATIFICATION-INTENT-V1\0`.
4. Requires exact `chain_id=wolo-1`, a pinned 40-character source SHA,
   a distinct nonzero 128-bit nonce, signed `not_before` at or after
   the original notice maturity and a short **maximum 120-second
   signature window**. All unknown fields fail.
5. Requires a precise scope of **reviewing** a centralized one-human
   governance proposal, with no claimed independent human reviewer,
   no legacy 8092 fallback, no historical liability waiver, new
   permission version required, zero funded transfer limit and no C09
   transaction permit asserted.

A verified signature emits
`HOLD_C08_SIGNATURE_VALID_RUNTIME_AND_AUTHORITY_NOT_RATIFIED` with exit 3.
Missing, changed, expired, malformed or untrusted evidence emits
`STOP_C08_RATIFICATION_INTENT_UNVERIFIED` with exit 2. There is
**no successful funded release status**, no signer invocation, no
private-key operation and no transaction creation in this controller.

This is intentionally NOT a ratification ceremony or on-chain governance
write. The observer cannot prove the provided owner public-key enrollment
or the signed source-commit pin were independently authenticated; the result
explicitly reports both as false. Source-only approval by an automated
assistant or a disposable test key cannot become owner consent or custody
authority.

## Operator workflow and original human signing boundary

The script accepts `--owner-enrollment`,
`--owner-ratification-packet`,
`--pinned-enrollment-sha256` and
`--pinned-owner-der-sha256`, requiring root/owner mode0600 packets in
private mode0700 directories. Never commit or paste private enrollment
or transaction packets into GitHub, chat, logs or documentation.

An actual owner-signing ceremony would require a separately reviewed
operator document, clear nonfunded text and an enrolled owner-controlled
public identity; this script **does not generate, request or fabricate**
any owner signature. The existing five-human funded runtime rules remain
in force until a new versioned, technically enforced, independently
reviewed and properly owner-approved implementation is admitted. Even
then, a distinct fresh C09 transaction-specific signed permit is needed
for any funded operation.

## Tests and scope of physical acceptance

The hermetic test suite generates an **ephemeral disposable** Ed25519
keypair and verifies a real signature with OpenSSL, together with
mutated signatures, wrong owner identity, revoked enrollment,
pre-maturity notice, altered GitHub source, short/long signing windows,
missing nonce, unknown fields, improper paid allowance, old 8092
fallback, historical liability waiver, and false independent human
review. It never accesses live payment keys or funding.

The real public notice passed its separate live GitHub 24-hour observer
at approximately 11:56 UTC November 8, receipt SHA256
`abf9dd5c96898cffeee22a2e0e167741ac49777ca138323010ee12a1323d7f7a`.
**No real owner-signed C08 ratification packet exists in this review.**
No claim of a physical owner ratification is made.

Still required: actual owner public-key enrollment anchored independently
of a CLI argument, reviewed versioned runtime policy implementation with
separate technical credentials, safe 8094/8095 contract, C03 all-writer
negative proof, C04/C05 externally authenticated settlement/solvency,
same-capture C06/C07 encrypted backup and restore, and a separately
signed exact C09 transaction permit. No C01–C09 financial gate is
closed by this documentation, source test or notice-age pass.
