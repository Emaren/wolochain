---
id: "aoe2war.wolochain.c03-extended-67-unit-observer-v2-stage"
title: "C03 Separate 67-Unit Financial Writer Telemetry V2: Inert Stage and HOLD"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2hdbets", "aoe2dewarwagers"]
audience: ["operators", "developers", "financial-reviewers", "ai-agents"]
source_of_truth: "git"
authority: "separate-telemetry-only-no-financial-containment-or-execution"
reviewed_at: "2026-11-08"
review_interval_days: 7
sensitivity: "restricted"
---

# C03 Separate 67-Unit Financial Writer Telemetry V2: Inert Stage and HOLD

## Why the original hourly receipt is incomplete

The original root-only hourly C03 watchdog on HEL1 uses an intentionally frozen source SHA, first installed for a 57-unit source inventory and 33 source-unscoped service/timer names. It currently reports `HOLD_EXPECTED_UNCONTAINED`, never an accepted global financial writer fence. **That source does not discover the ten recently identified external service/timer names**, meaning a successful old receipt cannot certify that newly exposed service family.

Chain PR #213 qualified the revised read-only source observer (SHA256 `0b14bc7dc6505bef8162eed87f7cac314d2782f0b9bfe3d7660de327cc88d811`) which returned 67 observed units and 43 source-unscoped units in real HEL1 tests. The independently extracted exact sorted-unit-name digest is `96026be468a9fd2cc6a65c8119ad83c8fd915a3233ef98c247fe90a319d745f0`. These are **observation-time source names**, not classifications of who can spend WOLO or a proof of writer quiescence.

## Deliberately separate versioned observer

The proposed `scripts/settlement_c03_observer_watchdog_v2.py` uses a new schema, separate paths, and exact SHA-pinned current source dependencies:

- Root-only source directory: `/usr/local/libexec/wolo-c03-observer-v2`, 0700; source files root0600.
- Root-only output: `/var/lib/wolo-c03-observer-v2/receipts`, both directories 0700 and append-only receipt 0600.
- Enrollment: `/etc/wolochain-financial-maintenance/c03-observer-enrollment-v2.json` (separate from V1). It remains absent until an independently qualified exact source/name-baseline permit, a full scan and rollback are proven.
- New physical auditor SHA256 pinned to `0b14bc7dc6505bef8162eed87f7cac314d2782f0b9bfe3d7660de327cc88d811`; new read-only HD/DE owner boundary auditor pinned to `504b85a9002c82a8150d468bc9c627b18eb97586565323de9d26857bfddee57b`. These were already merged in the held Chain source branch; V1's distinct historical source hashes are intentionally not rewritten.
- V2 refuses unexpected observer output, any financial release flag, unknown or duplicate unit names, missing HD/DE owner bypass, a 57-unit downgrade, any census other than exactly 67 units/43 unscoped, or missing extended unproven-domain declarations. A future 68th unit must return **STOP/HOLD** until separately reviewed; enrollment must never automatically absorb it.
- V2 does not stop a systemd unit, grant/revoke Postgres permissions, issue a signed phase permit, use a financial key, enable ports 8094/8095, or mutate user balances. It runs the exact merged C03 observer via root-only local code and creates only private evidence receipts.

Eleven new hermetic adversarial tests prove the 67/43 source contract, old 57-unit refusal, source file SHAs, separate filesystem paths, baseline drift, no auto-enrollment, no finance permission, no external API, no non-root access and correct expected HOLD. The 11 original V1 tests now explicitly recognize that their pinned SHA refers to an **installed historical release**, not the newer source in Git.

## Deployment boundary

The first physical stage should preserve V1's live hourly timer unchanged. Only after exact-head GitHub source qualification, a source-executable dry run, repeated stable name census and review of independently pinned unit-name hash may a separate owner-only V2 enrollment be considered. Do not replace V1 with a different source in place merely because it shares the same file name. For any eventual timer switch, a rollback that restores exact original systemd unit SHA, original V1 source pins and original V1 enrollment is essential. Public Steam, Traffic and website admission are Session B's separate responsibility.

This is a **C03 operational observability improvement**, NOT C03 financial gate closure. Complete original and newly discovered financial writer containment, authenticated finance-safe web rollback, existing DB-owner permission migration, recovery and independent Chain custody/solvency requirements remain required. No funded production Satchel activation is authorized.
