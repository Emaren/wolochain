---
id: "aoe2war.wolochain.c08-automated-keychain-governance-v3"
title: "C08 Keychain Software P-256 One-Human Governance — Real Passwordless Adoption"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["operators", "developers", "financial-reviewers", "ai-agents"]
source_of_truth: "git"
authority: "one-human-nonfunded-governance-only"
reviewed_at: "2026-11-08"
review_interval_days: 7
sensitivity: "restricted"
---

# C08 Keychain Software P-256 One-Human Governance — Real Passwordless Adoption

## Why replace the encrypted interactive Ed25519 signer?

The original owner-installed encrypted Ed25519 governance key under
`~/.wolo-owner-authority/solo-governance-adoption-keychain-v2` did **not**
decrypt under the owner's supplied unlock attempt on November 8. No source
code or authority can truthfully convert that failed decryption into a valid
original-owner Ed25519 signature. The original key, matching historical
`direction-only` signature, v2 policy sources and interrupted unsigned
request are retained unchanged for forensics. No brute force, copied secret,
Keychain secret extraction, signature forging or password-guessing is involved.

The owner explicitly authorized automatic nonfunded governance adoption.
The new trust anchor is therefore **a separate identity** rather than an
invented signature by the historical key. A public source-backed Keychain
owner-enrollment disclosure was posted on the original, matured single-owner
public notice issue #184 in authenticated GitHub comment
`6727529299`. The comment's body SHA-256 is exact-pinned
`bde91d30f97aaf53650122d33128790187a809b3760210a9e08822ece2395b48`,
with author `Emaren` and the original public notice binding re-verified
during the later signing ceremony.

## New key identity and limitations

The new key lives in the owner's ordinary **macOS login Keychain** and is
P-256, ECDSA-SHA256. It is **software-backed**, *not* a Secure Enclave key,
because Secure Enclave key generation returned the OS missing-entitlement
status `-34018` from the connected shell. The laptop also had **FileVault
OFF** at the time of enrollment. Login Keychain encryption is not whole-disk
encryption. The key is not deliberately exported in any command or receipt,
but it must NOT be described as physically non-exportable/attested. Hardening
with FileVault and recovery-proven signing custody remains an explicit
follow-on item.

Local Keychain key application tag:
`aoe2war-c08-owner-policy-only-keychain-p256-v3-20261108`.
The public X9.63 uncompressed EC key is 65 bytes, enrollment SHA-256
`f9f76deb8ba61b8f4b4f8e5b434acc11fa95630ccb19306a71e8bff0dc6fb826`.
Owner-only mode0700 root:
`~/.wolo-owner-authority/c08-keychain-policy-v3`;
mode0600 public enrollment:
`public-owner-key-x963.bin`.

`scripts/c08_keychain_governance_v3.swift` is the Apple Security.framework
bridge. It supports idempotent `enroll` (creates key only when absent),
`public` (identity only) and `sign` (accepts only the exact nonfunded
C08 V3 signature domain), and never exports the private key or asks for a
passphrase. One disposable real macOS login-Keychain key was successfully
created/reopened/signed/verified/deleted before the real persistent
governance-only key was enrolled. The actual real Keychain public
identity was independently verified using OpenSSL P-256 DER reconstruction
and a disposable C08-domain *test message*, then the test signature
was destroyed without an adoption receipt.

## Exact-source nonfinancial policy adoption

`scripts/settlement_c08_keychain_policy_adoption_v3.py` implements
`adopt` and `status`. Source admission checks the exact reviewed
Git commit and byte-for-byte identities of its Python source, Keychain
Swift source, and unchanged v2 one-human governance policy
`docs/settlement-contracts/solo-owner-governance-adoption-v2.json`,
SHA-256 `50910864e6d24236ac3ea98cda1456bedee8d9bf2f9365a8441c6d1e29b41806`.

The prospective adoption request contains:
- source commit and policy SHA, public Keychain X9.63 SHA, old Ed25519
  public digest **for historical comparison ONLY** (explicitly
  `historical_owner_key_signed_this_request=false`)
- GitHub issue #184 original 24-hour public notice body and exact
  new public enrollment comment author+body+identity
- one real human, no independent human review, no legacy 8092 fallback,
  no historical liability waiver or automatic payout retry
- **zero standing funded authorization** and a **1 WOLO maximum future
  C09 one-shot amount inclusive of gas**, subject to an entirely
  separate freshly approved transaction-specific signature
- fresh random nonce, 20-minute short-lived source-specific envelope.

The Keychain software key signs:
`AOE2WAR-WOLO-C08-KEYCHAIN-GOVERNANCE-ADOPTION-V3\0`
plus canonical request bytes. Independent verification reconstructs
the P-256 SubjectPublicKeyInfo from the owner X9.63 public key and uses
OpenSSL ECDSA-SHA256. No Keychain private material is read back.
An exclusive local lock and `O_EXCL` mode0600 policy receipt
prevent a second adoption, nonce replay, state replacement or
silently overwriting signed history. Historic adoption remains
checkable after its 20-minute signature window by verifying the
original adoption timestamp.

## Execute only after exact-head checks and merge

The **owner has already approved passwordless nonfunded governance**.
No private key, wallet seed, typing phrase or passphrase is required.
After the exact-head PR source is green and merged, use the verified,
clean merged worktree and original private owner root:

```bash
cd "$HOME/.cache/aoe2war/chain-c08-keychain-v3-20261108"
python3 -B scripts/settlement_c08_keychain_policy_adoption_v3.py adopt \
  --owner-root "$HOME/.wolo-owner-authority/c08-keychain-policy-v3"
python3 -B scripts/settlement_c08_keychain_policy_adoption_v3.py status \
  --owner-root "$HOME/.wolo-owner-authority/c08-keychain-policy-v3"
```

C08 closure must additionally check source-bound accepted real owner
public key, real native Keychain ECDSA verification, one and only one
immutable signed governance receipt, original public GitHub enrolled
fingerprint and notice, retention of old Ed25519 source, physical
offhost recovery of that signed receipt, no owner namespace conflicts,
and strict **no financial permission granted**. This uses a new
owner authority identity; it is not claimed as old-key cryptographic
continuity.

**C08 adoption itself does NOT activate any Satchel service, C01 custody
signer, native bank transfer, reserve review, 8094/8095 port, legacy payout
retry, financial PostgreSQL permission or C09 signed transaction.**
The later C09 transaction authority must source-verify this exact new
C08 V3 receipt (not accidentally accept only v2 Ed25519 receipts),
plus independently accepted C01–C07 evidence, exact payee/amount/gas,
a unique consumed offhost nonce, and native finality.

## Evidence and acceptance

The hermetic Foundation suite creates disposable P-256 keys and performs
real OpenSSL ECDSA sign/verify. It tests actual zero-fund adoption,
receipt verification after expiry, replay refusal, fake independent
reviewer, increased amount cap, 8092 fallback, historical liability
waiver, forged old-key continuity, wrong source, altered notice/comment,
wrong GitHub author, altered/forged receipt, wrong private file mode,
expired or overlong signing windows and no chain-financial write path.
The macOS Keychain smoke test is separate physical M1 evidence, not a
CI fixture. Only exact source merges and real owner-local Keychain
adoption count toward closure.
