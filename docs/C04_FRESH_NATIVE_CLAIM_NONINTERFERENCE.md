---
id: "aoe2war.wolochain.c04-fresh-native-claim-noninterference"
title: "C04 Forward-Only Native Return Claim Identity and Legacy Liability Non-Interference"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["operators", "developers", "financial-reviewers", "ai-agents"]
source_of_truth: "git"
authority: "source-held-no-live-legacy-liability-release"
reviewed_at: "2026-11-08"
review_interval_days: 7
sensitivity: "restricted"
---

# C04 Forward-Only Native Return Claim Identity and Legacy Liability Non-Interference

## Exact cross-repository contract

The App C02 merge source `cf06cd6a55b3d3062db1c25dc9652ee3f2b15b01`
implements `war_satchel_native_claim_id_seq`, a new PostgreSQL BIGINT sequence
with inclusive bounds **900000000001 through 999999999999**, as well as a
one-time authenticated original funding and credit ledger with separate
legacy and new physical identities.

The Chain v2 `ReturnApproval` validator previously accepted ANY 1–12 digit
nonzero ID except `889`. That permitted a malicious or misconfigured
signed native approval to reuse claim `9645` or another old
`pending_wolo_claims` identity even though App's own client rejected it.
The Chain independent authorization perimeter must never rely on App
TypeScript validation alone.

This contract now enforces the App's **exact same native claim namespace** in
both the original owner's v2 return approval and **every** entitlement
in its independently signed allocation. Historic numeric claim identities
`889`, `9645`, `101`, `102`, `103`, and all IDs below
900000000001 are denied, as are zero, overflow, leading zeros,
nondecimal encodings and noncanonical variants. Maximum 999999999999 passes.

The generic `claimIDs` parser remains deliberately unchanged for unrelated
historic ticket and market IDs: an existing market's numeric identifier must
NOT be silently recast as a new native payout authorization.

## Positive and negative regression

The executable Go `TestC04NativeClaimNamespaceDisjoint` proves:
- Positive lower and upper bounds of the App-generated namespace.
- Negative ancient claim IDs, `889`, `9645`, wrong length and syntax.
- A fully cryptographically signed v2 legacy claimant's request remains
  refused, even with an independently signed matching funding allocation.
- A signed original native claim is accepted with a fresh 12-digit ID.
- Attempting to smuggle a legacy entitlement into an otherwise fresh
  signed allocation is refused.

Existing escrow-return fixture claim IDs are updated to the dedicated native
sequence without modifying historic transaction bytes or actual user records.

## Physical / economic boundary

This is a candidate source-hardening contribution to C04 and C02, not
formal C04 acceptance. The old 69 hashless claimed records and 948 pending
records are NOT deleted, credited, status-flipped, forgiven, or paid. No new
customer wallet may be used to settle an old ambiguous liability. The
historical source/candidate attribution still requires authoritative original
journal and independent bank proof or explicit immutable quarantine.

C04 remains OPEN until original legacy obligations are physically isolated
from an actually protected financial production writer and real native
8094 execution, with preserved liabilities, restored data and replay denials.
C03 C05 C06 C07 and a fresh C09 signature remain separate prerequisites.

No 8092 fallback, financial grants, funded keys, live deployments or owner
signing are authorized by this source check.
