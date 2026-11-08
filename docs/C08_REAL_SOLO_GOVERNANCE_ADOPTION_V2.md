---
id: "aoe2war.wolochain.c08-real-solo-owner-governance-adoption-v2"
title: "C08 Genuine One-Owner Governance Adoption V2 — Signed Policy, Zero Financial Permission"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2hdbets", "aoe2dewarwagers"]
audience: ["operators", "developers", "financial-reviewers", "ai-agents"]
source_of_truth: "git"
authority: "versioned-nonfunded-owner-governance-adoption-only"
reviewed_at: "2026-11-08"
review_interval_days: 7
sensitivity: "restricted"
---

# C08 Genuine One-Owner Governance Adoption V2 — Signed Policy, Zero Financial Permission

## What this actually completes

Unlike the earlier C08 reviewer, whose successful signature review was **always an intentional HOLD**, this v2 software implements a permanent, source-versioned policy adoption decision. A real owner Ed25519 signature is required, with the previously verified historical owner **public key DER SHA-256** (`00d08c27271cf484f684059e83478d9522765c374101d5c4e8ed29e266e500ed`) used as an **independently code-pinned trust anchor**. This is the same owner key used for November 7's signed, nonfinancial governance direction, but is a completely different, never-reusable signature domain.

The standalone policy source is `docs/settlement-contracts/solo-owner-governance-adoption-v2.json`, exact byte SHA-256 `602f1078a2979d7f467e2ac4e055f6364bff8c4baf8d111fb1e10a227eb86e03`. It adopts one human controlling custody, reserve reviews and release decisions, with **no claim of independent human review**. Technical custody keys, reviewer keys, on-device governance identity and recovery key must remain separate even when controlled by that one person.

**Adopting governance is not activating funded finance.** The adopted v2 policy explicitly fixes the current funded allowance to **zero uwolo**; C09 still needs a *distinct*, freshly signed exact transfer with accepted C01–C07 physical proof, an authenticated Chain bank height and single-use off-host nonce. Old five-human permissions do not convert; no 8092 legacy fallback; no missing-hash payout can be silently retried, declared paid, deleted or waived. C08 can therefore be adopted before the other financial gates, but does not declare them passed.

## Mechanism actually implemented

`scripts/settlement_c08_governance_adoption_v2.py` supports:

- `prepare`: require a clean, complete source Git commit and exact policy object in that commit; inspect independently source-pinned owner public DER; create a random nonce and short-lived signed source+policy+notice request in a **0700 owner-only directory**. No signer invoked.
- `sign`: require the owner to run locally with the **existing 0600 ENCRYPTED private Ed25519 PEM**. OpenSSL requests its passphrase interactively. No passphrase, decrypted private key, raw PEM or wallet seed appears in ChatGPT, GitHub, shell argv or receipts. Sign canonical request under `AOE2WAR-WOLO-C08-REAL-GOVERNANCE-ADOPTION-V2\0`; write an owner-private signed packet.
- `adopt`: independently verify the real signature, historic externally pinned public DER key, exact versioned source commit and policy JSON SHA, GitHub public notice issue #184, author/publication/body identity and elapsed 24-hour period, no financial/independent-review escape fields, signed window 30 minutes maximum. Under an exclusive local lock, persist **one owner-signed adopted-policy receipt**, never rewrite it or accept a second packet. Status becomes `PASS_C08_OWNER_GOVERNANCE_POLICY_ADOPTED_NO_FUNDS`.
- `status`: re-verify the original signed packet, exact Git commit policy and code, notice, authorized owner identity, signed original adoption time, persistent receipt and zero financial allowance. A later normal source update cannot forge a new ratification from the old packet.

The test suite uses **disposable Ed25519 keys** and a synthetic mature public notice. It tests a real successful adoption, historical receipt verification after signature expiration, replay denial, forged signatures, owner key substitution, false independent human reviewer, funded quota, transaction permission smuggling, legacy 8092, unknown liability waiver, extra JSON fields, duplicate JSON fields, source and policy drift, encrypted-key enforcement, expiry and wrong permissions.

## Owner hardware/software boundary

The real device already holds a mode0600 encrypted owner governance PEM and matching public key at:
`~/.wolo-owner-authority/solo-governance-adoption-keychain-v2`.

**Do not sign until this PR has passed exact-head GitHub CI and been merged**, the source Git commit was fetched in the correct isolated worktree and a physical operator verifies it. This release intentionally does **not** attempt an automated private-Keychain extraction or ask the owner to paste a passphrase. A production adoption requires an actual local human passphrase entry; a unit-test signature or previously signed *direction* cannot replace it.

Example one-block **owner-local** command, only AFTER exact-source CI/merge and live source check:

```bash
cd "$HOME/.cache/aoe2war/chain-c08-adoption-20261108"
git fetch origin fix/c01-producer-review-20261104
git merge --ff-only origin/fix/c01-producer-review-20261104
OWNER_ROOT="$HOME/.wolo-owner-authority/c08-actual-policy-adoption-v2"
OWNER_KEY_ROOT="$HOME/.wolo-owner-authority/solo-governance-adoption-keychain-v2"
python3 -B scripts/settlement_c08_governance_adoption_v2.py prepare --root "$OWNER_ROOT" --public-key "$OWNER_KEY_ROOT/governance-ed25519-public.pem"
python3 -B scripts/settlement_c08_governance_adoption_v2.py sign --root "$OWNER_ROOT" --public-key "$OWNER_KEY_ROOT/governance-ed25519-public.pem" --encrypted-private-key "$OWNER_KEY_ROOT/governance-ed25519-encrypted.pem"
python3 -B scripts/settlement_c08_governance_adoption_v2.py adopt --root "$OWNER_ROOT" --public-key "$OWNER_KEY_ROOT/governance-ed25519-public.pem"
python3 -B scripts/settlement_c08_governance_adoption_v2.py status --root "$OWNER_ROOT" --public-key "$OWNER_KEY_ROOT/governance-ed25519-public.pem"
```

If owner signing prompts are unavailable, the `prepare` output can be inspected, and adoption remains unaccepted without bypassing it.

## Release acceptance — no false closure

Source success alone is **not** C08 CLOSED. Exact-head 10/10 GitHub checks; real owner local signature and persisted adoption receipt; independently re-verified policy/status; and retained immutable source/signing proof must all PASS. Exported sealed owner receipt must be enrolled into the new Satchel's permission controller and off-host recovery before allowing even an eventual separately signed funded C09 action. If this enrollment is not yet physically accepted, mark C08 `POLICY_ADOPTED_FUNDING_BOUNDARY_NOT_ENROLLED` rather than claim money can move.

C01/C02/C03/C04/C05/C06/C07 and C09 have independent acceptance criteria. No legacy claims, websites, traffic series, native consensus state, financial permissions, services or WOLO balances are changed by C08 policy adoption.
