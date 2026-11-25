---
id: "aoe2war.wolochain.c03-intel-real-preconnected-de-owner-migration-rehearsal"
title: "C03 Intel Real Restored DE: Preconnected Legacy Owner DML Denial Rehearsal"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["operators", "developers", "financial-reviewers"]
source_of_truth: "git"
authority: "real-intel-pg16-de-restored-clone-only-not-production-writer-admission"
reviewed_at: "2026-11-09"
review_interval_days: 7
sensitivity: "restricted"
---

# C03 Intel Real Restored DE: Preconnected Legacy Owner DML Denial Rehearsal

**C03 remains formally OPEN.** This independently exercises original
DE data, not fake records, in a disposable clone of a stopped Intel
FileVault PostgreSQL 16.15 recovery cluster. It does NOT touch the
production DE sister site or production roles.

## Actual source-bounded physical DE execution

Original C07 physical whole-DE restoration receipt:
**df21fa2e67319e606a530af501c5b108831178c27fb98c79b31e02bb166a5bb7**.

The precise source script
scripts/settlement_c03_intel_de_preconnected_role_owner_rehearsal.py
SHA256 **7baf57c6d5d9f914d6ca80a8fd827c3bc698beefbab9ba05afac6c4e51e79d61**
was transferred to Intel using pinned host identity, SHA validated,
then executed natively on the actual restored data.

- Original stopped 52-table DE cluster was cloned with APFS copy-on-write,
  completely separated from the earlier C07 source; root-only Unix socket,
  PostgreSQL 16.15, no TCP, source cluster untouched.
- PostgreSQL catalog name/semantic/explicit-asset inventory exactly
  selected **21** real DE finance-risk public tables out of 52.
- Recreated legacy DE LOGIN owner and its pre-migration full table grants,
  then opened a **real persistent old-role psql session before migration**.
- Pre-migration no-op DELETE on protected trophy_payouts succeeded.
  A second independent client transaction moved all 21 protected
  tables to NOLOGIN owner, revoked old and PUBLIC DML, and restored SELECT.
- Source checked all 21 new owners and zero old-role
  INSERT/UPDATE/DELETE/TRUNCATE grants.
- The **same previously connected** old-role client issued the
  same no-op DELETE and received exact PostgreSQL permission denied.
  Its SELECT still worked; a fresh reconnected old-role client also
  received DML permission denied.
- In the sandbox only, unclassified users UPDATE privilege persisted
  to distinguish ACL transfer from a blanket account lockdown.
  This is NOT production users-table financial safety certification.

Original owner-private Intel JSON receipt
~/.wolo-owner-authority/c03-intel-preconn-de-v2-20261109/
c03-real-de-preconnected-dml-denial.json
SHA256 **1619e23794efd73f4fee80036ea3de3063037baa456b677f95261c7c268dc292**.

Independent physical readback verified full JSON SHA256, all 21/52
assertions, both original/clone PostgreSQL clusters stopped, and the
original C07 source receipt unchanged. The original HD physical
preconnected companion is in
docs/C03_INTEL_REAL_HD_PRECONNECTED_WRITER_OWNER_FENCE_REHEARSAL.md
and its receipt SHA256
c571ea1f03ab62feef505bf08453f2513f77460601bec4f19cead9eb4c80d3e6.

## What remains before a real C03 production change

This checks only the 21 DE selected finance-risk tables and their
table-owner DML denial, not all 52 DE objects, sequences, SECURITY
DEFINER paths, every active producer, in-flight open transactions,
or role memberships in HEL1. It is not a source-coherent, quiesced
cross-database C06 checkpoint or C07 restoration of that exact checkpoint.

Session B owns real Steam V10 protected refresh, authenticated
administrator/nonadministrator route acceptance and restricted
public rollback. Session A cannot migrate live HD/DE owners until
B issues physical YES and the C06/C07 financial-safe prechange
recovery barrier is accepted. The C04 persistent 8092/8093 masks
must remain; no C09 canary or funded Satchel signing is allowed.

**C04/C08 CLOSED; C01/C02/C03/C05/C06/C07/C09 OPEN. No WOLO moved.**
