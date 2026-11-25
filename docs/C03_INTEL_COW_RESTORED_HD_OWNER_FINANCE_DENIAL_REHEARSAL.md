---
id: "aoe2war.wolochain.c03-intel-cow-restored-hd-owner-finance-denial-rehearsal"
title: "C03 Intel COW Restored HD Owner Finance Denial Rehearsal"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["operators", "developers", "financial-reviewers", "ai-agents"]
source_of_truth: "git"
authority: "nonfunded-real-restored-hd-partial-owner-migration-not-c03-closure"
reviewed_at: "2026-11-09"
review_interval_days: 7
sensitivity: "restricted"
---

# C03 Intel COW Restored HD Owner Finance Denial Rehearsal

The genuine nonfunded recovery has restored original HD on Intel FileVault ON:
190 public tables, 180 public sequences, no TCP. C07 original HD physical
receipt SHA256 7a8d495b4259c5316f0f38ff060667d6b81f1243f77e1656daf2765da3603305.

## Physical C03 isolation and owner tests

The recovered C07 database was stopped. An APFS copy-on-write CLONE of
its approximately 11 GiB database directory was made in four seconds.
The original accepted C07 recovery was not modified. Intel source SHA256
c6739f4f2676efacb18cdbf19657f41b8d3fccc77629c31c7ef6ae34d08cf6cb
then physically recreated original aoe2hd_user LOGIN NOINHERIT ownership
on the 190 tables and 180 sequences in the cloned isolated PostgreSQL16
database. It migrated EXACTLY 29 identified finance candidate tables
and 28 associated sequences to NOLOGIN NOINHERIT aoe2war_finance_owner.

To test sticky original ACL grants, the old owner was explicitly granted
ALL DML before transfer, then permissions were explicitly revoked.
Actual PostgreSQL has_table_privilege and has_sequence_privilege
showed old role INSERT/UPDATE/DELETE/TRUNCATE denied on all 29 tables,
and USAGE/UPDATE denied on all 28 sequences. A real DELETE FROM
public.pending_wolo_claims WHERE false as the old role was denied.
The private Unix-socket-only instance shut down cleanly.

Original Intel physical private C03 receipt SHA256
4aca50949a54d4999eb60a4e1f66b24a8f16960007bc874627b3825da9ed7120.

## Strict limitations — C03 remains OPEN

The original HD database was restored with no-owner/no-ACL flags,
so the recreated roles are a simulation and do NOT fully reproduce live
PostgreSQL role membership or grants. The 29 candidates are NOT a proven
complete real financial writer graph. Original users table is still
writable by legacy role in this sandbox. Existing active sessions,
Steam authentication, all mixed-purpose table columns and safe rollback
after migration remain unaccepted.

HEL1 original aoe2hd_user still owns 190 production tables and aoe2de_user
still owns 52 original DE tables. No live change occurred. Legacy 3030
finance-writable website cannot be reused as C03-safe rollback. Session B
must prove authenticated admin and ordinary-user continuity and restricted
R25 rollback before any production owner transition. Follow that with the
coordinated same-boundary C06 capture and Intel C07 restore. Financial
release remains ZERO and C01-C07/C09 remain OPEN. This is a real partial
owner-migration result, not formal C03 acceptance.
