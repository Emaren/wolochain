---
id: "aoe2war.wolochain.c08-native-keychain-governance-admission"
title: "C08 Native Custody Admission — Verified Owner P-256 Receipt"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["operators", "developers", "financial-reviewers", "ai-agents"]
source_of_truth: "git"
authority: "zero-funded-governance-prerequisite-only"
reviewed_at: "2026-11-08"
review_interval_days: 7
sensitivity: "restricted"
---

# C08 Native Custody Admission — Verified Owner P-256 Receipt

## Exact current trust and scope

The one-human Keychain P-256 governance adoption was physically signed and
independently verified on the owner's M1 on November 8, 2026. Its zero-funded
policy original source commit is `ecdeded047610119e57012b095ad8cb5f8019114`;
receipt SHA-256 is
`edcdf664259b0eeec0ae2ed71919bbe5745183864abc2c3b221aa50e83570d19`.
The signature does **not** authorize any WOLO transfer, custody unlock,
transaction broadcast, financial table mutation, old 8092 fallback,
historical debt waiver, or claim retry. It caps a separate possible future
C09 exact canary at 1,000,000 uwolo **including network fee**.

Original Ed25519 owner encryption could not be unlocked and was **not**
used. The new signing key is a software-backed macOS login-Keychain P-256
identity, not a Secure Enclave-attested key; FileVault was OFF on the
owner M1 when enrolled. The exact public X9.63 bytes fingerprint is
`f9f76deb8ba61b8f4b4f8e5b434acc11fa95630ccb19306a71e8bff0dc6fb826`.
The exact original adopted-receipt SHA-256 is additionally hard-pinned in
production verifier source, so a newly signed replacement cannot silently
be substituted. The public notice and enrollment comment identities are pinned in
`internal/satchelservice/c08_governance_admission.go`; the owner-private
receipt itself must never be committed to Git.

## Source/runtime enforcement

The native Go verifier `VerifyC08KeychainV3Receipt` validates exact
signed receipt and request schemas, canonical Ed25519-to-P-256 migration
provenance, ECDSA-SHA256 signature, original 20-minute issuance window,
source and public identity, no second human, no legacy 8092,
no historical liability waiver, *zero* standing allowance, no C09 permit,
and a 1 WOLO future ceiling. Mutated, forged, expired-at-issuance,
missing, noncanonical or extra-field receipts are denied.

`wolosatcheld` requires the following **operator-managed,
non-default** fields in its protected config:

- `c08_governance_receipt_file`: absolute canonical path to service-owned
  mode0600 original adopted governance receipt
- `c08_governance_owner_public_file`: absolute canonical path to the
  enrolled service-owned mode0600 P-256 public X9.63 bytes
- `c08_governance_receipt_sha256`: exact SHA-256 of the original receipt

All three are required for financial admission. Legacy configs remain
parseable for inspection, but **fail** the live authorization check.
Both C08 cryptographic verification and the independent existing
binary/config-bound execution permit are required at startup and
re-checked at each backend authorization decision. Missing or
mutated governance source fails closed. Synthetic tests prove valid
legacy execution permits cannot substitute for owner governance.

## Read-only physical admission on HEL1

The exact *production* Go signer now has a separate
`verify-c08-governance` action, which accepts only the owner-protected
original signed C08 receipt and enrolled P-256 public bytes. It validates
all the same compile-time production key, source, notice, policy, signature,
zero-funding and receipt SHA constraints as the execution path; successful
status is `PASS_C08_NATIVE_OWNER_GOVERNANCE_ADOPTED_ZERO_FINANCIAL_AUTHORIZATION`.
The probe never loads an execution config, Cosmos keyring, vault passphrase,
RPC/REST/bank connection, nonce backend or HTTP listener.

Example after source-qualified native Linux build and root-only installation:

```bash
wolosatcheld verify-c08-governance --receipt /root/<protected-private-c08-original-receipt.json> --owner-public /root/<protected-private-c08-original-public.bin>
```

Do not expose full paths, original signed packet, nonce, signatures or public
key material in GitHub, CI or website telemetry. These files must retain
root ownership, mode0600, no symlinks and exact original SHA. A successful
zero-money governance probe **does not** qualify C01 custody/reviewer
enrollment, C03 financial writers, C05 solvency, C06/C07 recovery, or
the separate C09 one-use transaction permit. The signer must still be
inactive on HEL1 until those independent controls pass.

## Non-interference and remaining gates

This is a **source-only candidate until exact-head CI, review, merge and
independent live production controller acceptance**. It does not create
an escrow address, unlock a native signer or start ports 8094/8095.
Do not install this code or any new permit on HEL1 until all accepted
C01–C07 custody, C02 App, C03 writers, C04 quarantine, C05 reserve,
C06 offhost and C07 exact restore evidence exists.

The existing generic execution permit is **not** an exact C09
transaction-specific owner signature. A separate hard fail-closed
C09 transaction/nonce/amount/recipient/fee authorization must be
wired before funded release. C08 cannot by itself imply C09 or a
positive `CustodyCapability`.

## Fully isolated real-executable regression

The original C01 subprocess test executes an actual Go signer and SDK bank
proof over a disposable 127.0.0.1-only chain. To preserve that test after
C08 governance admission became mandatory, CI uses an **explicit build-tagged
simulation-only signer**. It receives a freshly signed disposable P-256
adoption receipt from the test fixture, verifies its ECDSA signature and
schema, and requires the exact simulated source label and numeric loopback
RPC, REST and witness endpoints. The separate reviewer and CLI remain their
ordinary real binaries. The physical owner C08 signed receipt is never
published to CI, and the synthetic identity cannot match the production
SHA-256 trust pin.

The **production signer is always built without**
`satchel_c08_ci_simulation`. Its public source anchors are compile-time
constants in `c08_governance_trust_prod.go`; runtime environment variables
cannot replace owner identity or original receipt. The test-only source is
excluded from production by Go build constraints. Never stage or deploy the
isolated CI signer as a funded release candidate.

## Reproduction

Run the synthetic negative suite in a disposable checkout:

```bash
go test ./internal/satchelservice -run '^TestC08V3' -count=1
go test ./cmd/wolosatcheld -run 'TestStaticCheckDeniesValidExecutionPermitWithoutOwnerGovernance' -count=1
```

The owner-only physical positive evidence uses the original protected
receipt, never fixtures:

```bash
AOE2WAR_C08_OWNER_RECEIPT_ROOT="$HOME/.wolo-owner-authority/c08-keychain-policy-v3" \
  go test ./internal/satchelservice -run '^TestC08V3OwnerPhysicalReceiptWhenRequested$' -count=1 -v
```

Never publish receipt bytes, private keys, authentication tokens or
Keychain passwords in CI, issue comments or chat. A passing source test
is a source qualification, not a production financial release certificate.
