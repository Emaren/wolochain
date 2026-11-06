---
id: "aoe2war.wolochain.c03-synthetic-nologin-owner-rehearsal"
title: "C03 Synthetic NOLOGIN Owner Partition Rehearsal"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["developers", "operators", "ai-agents"]
source_of_truth: "git"
authority: "source-only-nologin-permission-rehearsal-not-live-ddl-approval"
reviewed_at: "2026-11-06"
review_interval_days: 7
sensitivity: "restricted"
---

# C03 Synthetic NOLOGIN Owner Partition Rehearsal

## What this source actually proves

The Mac-local `scripts/settlement_c03_isolated_nologin_owner_rehearsal.py` creates a brand-new synthetic PostgreSQL14 Unix-only cluster, with two **fake** roles:
`c03_legacy LOGIN` and `c03_finance_owner NOLOGIN`. The first begins as database/schema owner and owns a finance-like serial table, trigger function and unrelated profile table. The code then partitions database/schema/finance table/sequence/function ownership to the neutral NOLOGIN role, explicitly revokes public schema CREATE, grants the former runtime role **SELECT only** on finance while preserving its unrelated profile-table DML, tests the denial boundary, and rolls back the fake owners in isolation to prove reversal.

At 2026-11-06 the exact source bound rehearsal returned `PASS_SYNTHETIC_MIGRATION_AND_ROLLBACK_HOLD_FOR_LIVE` (exit 0). It witnessed nine independently defined assertions:

1. Legacy finance-table INSERT, UPDATE, DELETE and TRUNCATE were denied.
2. `nextval` and `setval` against the owned finance sequence were denied.
3. ALTER TABLE finance was denied.
4. CREATE TABLE in public and CREATE SCHEMA in the database were denied.
5. `SET ROLE` escalation into the neutral owner was denied.
6. Neutral finance owner with NOLOGIN could not authenticate directly.
7. Existing finance-table SELECT as the legacy runtime role succeeded.
8. A separate unrelated profile table remained writable by the legacy role.
9. Exact synthetic owner rollback restored the prior role's finance write capability.

The pre-existing exploratory source receipt and the exact-source committed replay share SHA256 `d430462417a408d0f30ca1259145036d401e7106223613274e82b9ea1ececb0a`, due to deterministic JSON fields. The source includes strict boolean/exact-count qualification and no production connection. The fixture PostgreSQL server, private temporary files and Unix socket were torn down after execution. Eight hermetic source tests PASS, including false-vs-integer, missing/extra assertions, root/non-Mac refusal and no HEL1/HD/DE target.

## Why this is not physical C03 closure

This is **a synthetic model of the proposed privilege domain**. It is not a rehearsal against an actual C07 restoration of the same new coordinated C06 snapshot. The real HD database has 24 finance-named public tables, 23 attached sequences, 12 external triggers and seven dependent postgres-owned views; DE has 10 tables and ten sequences. The finance-name heuristic is not a complete writer-universe attestation, and the two legacy DB owner roles still hold physical production authority. This source neither stops Traffic/legacy settlement nor revokes live grants.

The next required stage is a verified complete C03 producer-maintenance fence, one new coordinated off-host encrypted C06 snapshot, and C07 restoration of **that exact snapshot**. Only then can an independently reviewed ownership map/rollback plan safely apply the NOLOGIN model to the real schema. Every finance INSERT/UPDATE/DELETE/TRUNCATE, sequence function, schema CREATE, role membership, SECURITY DEFINER, default privilege and independent service write path must be denied by the real restricted credentials while public Steam and unrelated HD/DE operations remain healthy.

Do not deploy this synthetic script to HEL1 as a migration controller. Do not reinterpret a PASS as financial authority, automatic refund finality, reserve coverage or a license to start ports 8094/8095.

## Safe owner-Mac replay

On macOS ARM with Homebrew PostgreSQL14 installed under `/opt/homebrew/bin`, run `python3 -B scripts/settlement_c03_isolated_nologin_owner_rehearsal.py`. It refuses root and non-Mac environments, and starts its test cluster only under `~/.cache/aoe2war` with no TCP listener. The accompanying focused unit command is `python3 -B -m unittest discover -s tests -p 'test_settlement_c03_isolated_nologin_owner_rehearsal.py' -v`.

**No financial gate closes based on this synthetic rehearsal.**
