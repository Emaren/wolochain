---
id: "aoe2war.wolochain.c09-filevault-intel-transaction-key-enrollment-hold"
title: "C09 Distinct Intel FileVault P-256 Transaction Key: Physical Enrollment HOLD"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["operators", "developers", "financial-reviewers", "ai-agents"]
source_of_truth: "git"
authority: "owner-only-unfunded-filevault-keychain-enrollment-not-a-payment-permit"
reviewed_at: "2026-11-09"
review_interval_days: 7
sensitivity: "restricted"
---

# C09 Distinct Intel FileVault P-256 Transaction Key: Physical Enrollment HOLD

The adopted C08 governance identity is a POLICY-ONLY P-256 software Keychain key
on the M1 and has zero standing funded allowance. Do NOT reuse it as the C09
transaction signer or claim the old ununlockable Ed25519 owner key approved C09.

A separate C09 transaction-only P-256 Keychain key is proposed for the **Intel
MacBookPro11,3, macOS11.7.4, x86_64, FileVault ON** recovery host. Its
application tag is uniquely namespaced as
aoe2war-c09-transaction-only-intel-filevault-p256-v1-20261109;
it is NOT a Cosmos signing key, cannot broadcast, and has a different
signature domain than governance. It exports only the 65-byte X9.63
public point; never a private key, mnemonic, login password, token or
financial transaction.

## Actual owner machine result at Nov 9 UTC

Exact submitted Swift source SHA256
**592f3a21c2b2726f36b8bb67fa6b93941cab161c3cb5171a30b4cefbd1a5b159**
was byte-verified on Intel and compiled there with the installed,
version-consistent Swift 5.4 compiler using MacOSX11.3 SDK. The compiled
native x86_64 executable SHA256 is
**250ef8d31c5cb744907de631615b2837ada627d320770ceca23faceca3344424**,
mode 0500, inside its own FileVault owner-private directory.

The first harmless PUBLIC query returned the correct
HOLD_C09_INTEL_KEYCHAIN_TRANSACTION_KEY_NOT_ENROLLED (exit 3).
An ENROLL attempt returned HOLD_C09_INTEL_KEYCHAIN_KEY_CREATION_FAILED,
exit 3. Read-only system security subsequently confirmed
SecKeychainCopySettings: **User interaction is not allowed**
for the login Keychain from the remote SSH session. No public
enrollment file was created. No private key was exported or copied to
HEL1/M1. No C09 signature or financial permit was created.

**Next real dependency: the owner must locally unlock the Intel login Keychain
in an interactive user session** (without sharing a password in chat or in
command arguments) before reattempting only this exact SHA-pinned enrollment.
The command also enforces FileVault ON, the Intel x86_64 host, nonroot owner,
exclusive output files and a strict C09-only message domain. If this
cannot succeed, keep C09 HOLD; do not fallback to the M1 governance key.

Even after enrollment, a real C09 owner-specific fresh transaction signature
bound to exact App native claim, recipient, amount+fee <=1 WOLO, bank
root, C01-C07 accepted evidence, exact idempotent original operation and
offhost one-use nonce remains mandatory. There must be NO credit, native
broadcast or 8092 fallback from this enrollment alone. C09 remains OPEN.
