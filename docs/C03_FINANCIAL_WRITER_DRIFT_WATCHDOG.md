---
id: "aoe2war.wolochain.c03-financial-writer-drift-observer"
title: "C03 Financial Writer Drift Watchdog"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["developers", "operators", "ai-agents"]
source_of_truth: "git"
authority: "read-only-finance-hold-monitor-not-a-fence-or-funded-permit"
reviewed_at: "2026-11-06"
review_interval_days: 7
sensitivity: "restricted"
---

# C03 Financial Writer Drift Watchdog

## Purpose and limits

Source-only root-local `scripts/settlement_c03_observer_watchdog.py` and `deploy/c03-observer-systemd/wolo-c03-observer.{service,timer}` turn the previously merged read-only C03 systemd/DB-owner observer into a scheduled, **fail-closed** detection mechanism. It is *not* an automatic financial writer fence, a backup, a restore, a source-promotion controller, a reserve proof, a chain finality proof or a replacement for the owner's transaction-specific signing permit.

The latest physically observed C03 universe comprised 55 installed/loaded project units, 31 outside the old 18-unit maintenance controller and 11 active outside the old scope. Both legacy HD and DE runtime roles still own finance-related tables and their databases. The observer's proper state while those conditions remain true is **HOLD**, never PASS to move WOLO.

## Immutable source requirements

The exact audited source hashes are pinned in the driver:
- `settlement_c03_physical_writer_universe_hold.py` SHA256 `339540b550219b592554bbd0898447c3bf5f206f758bc8d8dea4e7500661c35b`.
- `settlement_c03_db_owner_boundary_hold.py` SHA256 `294a4427702d6fd9ab7265ea5e7e0ec1e7816f1c5194c6f37781591b1337cd87`.

The reviewed files must be deployed into a separate owner-protected root-only 0700 directory at `/usr/local/libexec/wolo-c03-observer`. They must be root-owned regular files with no write permission for group/other and exact content hashes. A source drift produces STOP, never an unattended replacement, automatic key enrollment or a finance authorization.

The watchdog itself uses root-local systemd and PostgreSQL catalogs (read-only). It rejects any audited result that does not exit **3/HOLD**, claims funds or backup authority, lacks complete two-DB owner evidence, or changes the source identity.

## Baseline governance and private receipts

The baseline is an **independently reviewed** root-owned 0600 JSON file at `/etc/wolochain-financial-maintenance/c03-observer-enrollment.json`, with exact schema `wolo.c03.observer-baseline.v1`, `unit_names_sha256` (sorted, canonical observed unit names digest), `source_hashes` (the fixed pair above), and `enabled=true`. It is **never automatically enrolled on first run**: unseen finance services could otherwise simply become the trusted baseline. An absent enrollment returns `HOLD_UNENROLLED`. A dangling symlink or malformed/suspicious enrollment returns STOP. Introducing the monitor's own systemd unit changes the discovered inventory, so a pre-install 55-unit digest must not be silently reused as the post-install baseline.

Protected records go only to `/var/lib/wolo-c03-observer/receipts`, both root-owned 0700 directories, with 0600 append-only new file names. The script checks a 256MiB free-space floor and caps receipt creation to 2,000 total files; it never deletes or overwrites old receipts automatically. Reports contain counts, source SHAs, unit-name digest, owner capability summary, explicit no-release booleans, and source status. They contain no PostgreSQL data rows, wallet keys, cookies, private credentials or signing material.

### Result taxonomy

| Observer result | Meaning | Process exit |
|---|---|---|
| `HOLD_UNENROLLED` | No reviewed baseline; read-only observation stored | 3 |
| `HOLD_EXPECTED_UNCONTAINED` | Exact enrolled installed-unit names observed; finance still not contained | 3 |
| `HOLD_UNIT_DRIFT` | Installed unit-name set changed from reviewed baseline | 2 |
| `STOP` | Source, file permissions, enrollment, PG catalog, receipt or runtime error | 2 |

There is **no automatic financial remediation**. An exit 2 is suitable for the existing host monitoring/escalation pipeline; source must separately review a real alert integration before claiming that notifications are delivered. Repeated read-only observations are idempotent, but no generated HOLD can be interpreted as a financial clearance.

## Source-reviewed deployment sequence (not yet performed)

1. Merge the exact source after full CI, tests and code review. Inspect static unit/timer files and binary hashes; do not install from an unmerged worktree or deploy a changed HEAD.
2. During a reversible, source-bound nonfinancial maintenance transaction, provision root-only `/usr/local/libexec/wolo-c03-observer` and `/var/lib/wolo-c03-observer/receipts`, preserving all pre-existing files. Stage only exact source-hashed auditor and watchdog bytes, and the exact reviewed systemd units; apply owner/mode checks.
3. Run the watchdog `--mode plan` without root: it only produces HOLD and exits3. Run `--mode once` as root after verifying source and directory identity; on first run it should record `HOLD_UNENROLLED`, not create or trust its own baseline. Confirm no financial service, live role, Nginx or validator change.
4. After manually reviewing the **new** installed activation universe and independent writer exclusions, enroll the root-only baseline via a separate, reviewed one-use source-bound operation. Do not infer that 55 old units automatically remain authoritative after installation.
5. Enable only the read-only timer (hourly with 120s jitter). Review receipts after a full interval and independently verify the timer can detect an **isolated simulated unit-digest drift** without any production unit stop.
6. If a source or enrolled unit changes, retain evidence and HOLD; do not automatically change production grants or reapprove its own baseline.

The service uses a strict read-only filesystem sandbox, root-only receipt write allowance, AF_UNIX only, `NoNewPrivileges`, no home access and no TCP egress. It never executes a funded transaction, starts 8094/8095, stops 8092/8093, changes the wolo-1 validator, or modifies the live website.

**C03, C06 and C07 physical financial gates remain HARD HOLD until the separately established producer fence and exact coordinated encrypted backup/restore proofs exist.**
