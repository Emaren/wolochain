---
id: "aoe2war.wolochain.c03-topology-only-baseline-review"
title: "C03 Topology-Only Watchdog Baseline Enrollment"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["developers", "operators", "ai-agents"]
source_of_truth: "git"
authority: "topology-only-no-financial-writer-fence-or-financial-permit"
reviewed_at: "2026-11-06"
review_interval_days: 7
sensitivity: "restricted"
---

# C03 Topology-Only Watchdog Baseline Enrollment

## Intent and non-authority

The hourly C03 observer is successfully installed on HEL1, but it currently always records `HOLD_UNENROLLED`. That prevents unattended unit-name drift identification. One independently reviewed, *knowingly unconstrained* list of currently present systemd service/timer names may be enrolled without declaring those services financially safe. **This is not a C03 gate pass.**

The exact baseline reviewed on November 6, 2026 is **57 installed/loaded project units**, with canonical sorted-name SHA256:

`83f15ae92e7420822f0c10ce3ad0d9e39eef2b913f6697bd750c36a91f80a1de`

The baseline explicitly includes **33 unscoped services/timers**: this means they remain subject to financial-writer classification and possible containment. The SHA pins only the *names*, NOT whether their code, privileges or grants are safe. Runtime financial services, current PID identities, source pinning, PostgreSQL owner bypass, unauthenticated external writers and historical claim UNKNOWN remain on HOLD.

Current root-private receipt evidence included two independent post-install observations, at 21:57:28 and 21:57:32 UTC, with equal 57-unit names SHA and explicit `HOLD_UNENROLLED` / no payment authority. A fresh 22:55 UTC root-local auditor census independently observed the same 57 names and hash. The separate auxiliary census receipt `fd796e5d03bd07d1626f30624d6150c9d81c13320dddb0dbf4b85826ba7f94d9` separately describes cron, user-systemd and Docker activation. **None of those other activation classes are included in this unit-name baseline.**

## One-use, source-bound controller

`scripts/settlement_c03_reviewed_topology_baseline_enrollment.py` has two modes:

- `--mode inspect` verifies the HEL1 root identity, exact unit and source file SHA pins, owner-only modes, current public/validator/legacy settlement PIDs, six public Nginx upstreams to 3032, 8094/8095 inactive, active C03 timer, absent enrollment and the last two original `HOLD_UNENROLLED` receipts. It then independently runs the exact root-local source auditor and requires the fixed 57-unit SHA. It does not write.
- `--mode apply` repeats the same admission, creates only one root 0600 `/etc/wolochain-financial-maintenance/c03-observer-enrollment.json` via exclusive `O_NOFOLLOW` creation, then starts the already reviewed root-local read-only watchdog once. It requires exactly one new private 0600 receipt showing `HOLD_EXPECTED_UNCONTAINED`, `enrolled=true`, `driftDetected=false`, `financialReleaseAuthorized=false`, `backupCertified=false`, `autoRemediation=false`. It preserves the original five service PIDs and writes a root-private 0600 admission manifest. On failure it removes only the exact newly created baseline, never any recovery key or existing receipt.

The enrollment file schema remains the watchdog's fixed `wolo.c03.observer-baseline.v1`, with only `schema`, `unit_names_sha256`, `source_hashes` and `enabled`. Do not add a fraudulent `approved_writers` or `financial_release` property. The schema is not a payment authority.

All code paths return `HOLD` for non-HEL1 users, changed source, changed PID, changed DB auditor, new unit, candidate financial port or absent private receipts. The controller does not grant/revoke PostgreSQL permissions, stop a live process, modify another app's service, provision keys, create a new user or touch a funded transfer.

## After admission

After exact-head independent GitHub CI and source merge, run the exact source-bound code with `--mode inspect` first. Only when PASS, perform the one-use `--mode apply` and independently verify a subsequent scheduled hourly observation returns `HOLD_EXPECTED_UNCONTAINED`. A simulated in-memory changed name must produce `HOLD_UNIT_DRIFT` / exit2 without creating any real systemd unit.

**A baseline name change is never auto-enrolled.** Require a new audited one-use source change, new review evidence, and the same explicit fail-closed process. No automatic drift repair is allowed to alter a production writer or move money.

C03 still needs complete real writer/queue/signature containment, C06 a coordinated encrypted offhost backup and C07 exact restore. C08 independent witness and C09 funded transfer have separate cryptographic controls.
