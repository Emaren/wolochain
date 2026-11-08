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

## First actual nonmutating HEL1 shadow run

On November 8 the exact V2 source, source merged auditor and modern HD/DE owner auditor were copied through owner SSH to a **separate**, root0700 source directory and manually invoked in read-only `--mode once`. The observed result was `HOLD_UNENROLLED`, **67 total / 43 source-unscoped**, with explicit financial release false. New root0700/0600 private receipt SHA256 **`85ee4b1ec620c2aed98c77c887ab11db681c8876a713dd067e9dc1c57def6e6c`**. Source binary SHA256 **`793c58385c7895c2da8464a0b14ee4ea42ea13a5610cb57e3866ddd575fa558e`**. Original live V1 source hashes and old enrollment SHA256 `67ba18c7b32fb19a3a5f5a611bd60bd3e519519d5af4ff3e4a9224f2941b595c` were checked unchanged afterwards. The original V1 hourly timer remains active.

This validates the **shadow observation**, not any production switch, re-enrollment, scoped writer-grant change, Satchel deployment or owner transaction signature.

## Separate owner-run cutover controller — reviewed admission required

A fixed, non-financial `scripts/settlement_c03_watchdog_v2_cutover_hold.py` adds two modes. Its `--mode inspect` checks the exact original service and timer file hashes, V1 source and enrollment SHA pins, three V2 source SHA pins, two private V2 67/43 observations with the same sorted-name SHA and no financial authority, current active V1 hourly timer, inactive V1 one-shot service, inactive funded services 8094/8095, protected validator PID, and a **fresh** exact read-only 67/43 source observation. It returns an intentional HOLD and modifies no existing systemd or database state.

Its separately approved `--mode apply` first writes an exclusive root-only copy of the V1 unit and the exact V2 candidate (derived from V1 by **four directory-path substitutions plus the v2 Python filename only**). It verifies the candidate through `systemd-analyze verify`, briefly pauses **only** the C03 observation timer, creates a distinct version-2 source-bound sorted-unit-name baseline with exclusive root0600 creation, atomically switches the C03 **telemetry** service file, reloads systemd, executes the new one-shot once, and requires a fresh root0600 receipt `HOLD_EXPECTED_UNCONTAINED`, 67/43, no payments, before restarting the old timer. It then rechecks 8094/8095 remain closed, the validator PID is preserved, the old enrollment and all old source hashes remain unchanged, and writes an owner-private immutable deployment receipt. The service retains `NoNewPrivileges=yes`, `ProtectSystem=strict`, `RestrictAddressFamilies=AF_UNIX`, and `SuccessExitStatus=3`; only its separate telemetry output path is writable.

On any encountered failure after the timer pause, the controller attempts to atomically restore the original exact V1 service SHA, reload systemd, reactivate the original timer, and remove only the exact newly created V2 enrollment. If the enrollment has changed unexpectedly, it refuses to destroy it and requires manual review. The controller never calls the financial producer maintenance controller, grants Postgres permissions, changes Steam/Traffic, signs, moves, mints or releases WOLO.

Fourteen dedicated tests verify the exact unit-rewrite bytes, immutable V1 source identity, current V2 source fingerprint, mandatory external identity and name-count reviews, source-only enrollment, no nonroot execution, exclusive receipts, successful rollback and deliberate tampered-enrollment denial. This remains **nonfinancial telemetry scope**, not proof that any of the 43 unreviewed services is safe.

## Deployment boundary

The first physical stage should preserve V1's live hourly timer unchanged. Only after exact-head GitHub source qualification, a source-executable dry run, repeated stable name census and review of independently pinned unit-name hash may a separate owner-only V2 enrollment be considered. Do not replace V1 with a different source in place merely because it shares the same file name. For any eventual timer switch, a rollback that restores exact original systemd unit SHA, original V1 source pins and original V1 enrollment is essential. Public Steam, Traffic and website admission are Session B's separate responsibility.

This is a **C03 operational observability improvement**, NOT C03 financial gate closure. Complete original and newly discovered financial writer containment, authenticated finance-safe web rollback, existing DB-owner permission migration, recovery and independent Chain custody/solvency requirements remain required. No funded production Satchel activation is authorized.
