---
id: "aoe2war.wolochain.c08-dedicated-witness-command-source-review-hold"
title: "C08 Dedicated Intel Witness: Exact Forced Command and Source-Pin Admission Review"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["operators", "developers", "financial-reviewers", "ai-agents"]
source_of_truth: "git"
authority: "source-only-offhost-nonce-witness-command-review-no-live-activation-or-finance-permit"
reviewed_at: "2026-11-08"
review_interval_days: 7
sensitivity: "restricted"
---

# C08 Dedicated Intel Witness: Exact Forced Command and Source-Pin Admission Review

## Physical November 8 baseline

The separate C08 owner/witness enrollment is physically present as mode0600 files on HEL1 and the Intel Mac, with an Intel mode0700 nonce directory. Both local config-vs-enrollment hashes passed read-only checks. The HEL1 solo-owner runtime config is pinned to an earlier source `b35f294d619e6bf5d07b337cea46095f2eea9f76`, not the current HELD Chain integration head; this is **not** safe to re-enroll silently.

Two distinct Intel-to-HEL1 paths must never be conflated:

- C06 off-host recovery transfer, HEL1 `127.0.0.1:22996`: authenticated M1 relay to Intel verified with the existing source-enrolled host key and 8192-byte synthetic SHA receipt. This is *not* the C08 witness.
- C08 single-use nonce witness, HEL1 `127.0.0.1:22995`: **not listening**. Existing Intel dedicated witness SSHD intentionally uses `ForceCommand /usr/bin/false`, with a second deny-only key-level forced command. Its source controller previously set `REVIEWED_WITNESS_EXEC_COMMAND=None` and therefore required HOLD. No transport or credential failure was inferred from the intentionally denied port.

A dedicated witness executable already exists on Intel at `~/.wolo-owner-authority/witness-runtime/source/settlement_solo_runtime.py`, owner mode0600, actual SHA256 `b8cd22ab3df7a4b3385bd5ed0c9886638f737adf538e236875df3b807d1404fb`. This is the same SHA256 pinned by the original enrolled witness configuration. Its `--witness-stdin` entrypoint validates enrolled owner Ed25519 source/host/operation, bounded time and off-host nonce semantics, and exits HOLD on malformed or unverified packets.

## Source-only review

`scripts/settlement_c08_intel_reverse_tunnel_hold.py` now explicitly knows only the exact candidate SSH key forced command:

`/usr/local/bin/python3.13 -B /Users/tonyblum/.wolo-owner-authority/witness-runtime/source/settlement_solo_runtime.py --witness-stdin`

**This source is NOT a permit to remove existing `/usr/bin/false` or start a listener.** Positive source acceptance additionally requires exact command equality (not a substring, shell wrapper or environment expansion), SHA256 of the *actual on-disk* owner-private witness source, exact separate original witness enrollment SHA, matching enrolled source commit, finite dedicated Intel loopback listener and existing SSH identities/allowlists/denials. The source never inspects the private SSH key bytes, changes normal SSH port 22, or routes to 8092/8093/8094/8095.

The original deny-only profile continues to classify `dedicated_backend_admitted=false`; even if someone updates the key command but leaves `ForceCommand /usr/bin/false`, no active witness is admitted. Existing source-pinned backup-port 22996 remains untouched.

## Tests and physical acceptance required

The fixture suite now includes positive **synthetic** exact-source admission and negative source mutation, group-readable source, enrolled source-commit substitution, and preserved global deny `ForceCommand`. It also preserves all prior TLS/SSH pin, host key, restricted authorized key, exact launchd plist, source SHA, rollback, arbitrary-binary, port substitution and broad-forwarding denials.

Before any active C08 witness transition, a separate human-reviewed *physical* plan is mandatory: validate exact current source and enrolled root/Intel identities, install only a dedicated key-level forced command and narrowly configured dedicated localhost SSHD with its own rollback, perform real negative rejection of invalid/expired/foreign/duplicate owner packets, and validate one-use off-host receipt with real signer identity under fresh owner consent. Do not consume or fabricate a real customer release nonce just to make a test green. A fresh separately enrolled source-version update will be necessary before current-source solo maintenance. None of this authorizes funding.

This remains **source-only / financial HARD HOLD**. The formal C08 gate and C01–C09 all remain open. No on-chain transaction, database DDL, unit restart, wallet, customer funds or Session B service changes are authorized by this patch.
