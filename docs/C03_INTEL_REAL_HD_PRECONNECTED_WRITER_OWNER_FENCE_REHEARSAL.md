---
id: "aoe2war.wolochain.c03-intel-real-preconnected-hd-owner-migration-rehearsal"
title: "C03 Intel Real Restored HD: Preconnected Legacy Owner DML Denial Rehearsal"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["operators", "developers", "financial-reviewers"]
source_of_truth: "git"
authority: "physical-intel-only-restored-hd-owner-rehearsal-not-production-writer-fence"
reviewed_at: "2026-11-09"
review_interval_days: 7
sensitivity: "restricted"
---

# C03 Intel Real Restored HD: Preconnected Legacy Owner DML Denial Rehearsal

**Formal C03 remains HOLD.** This is a real physical PostgreSQL 16.15
rehearsal, not a source fixture, and changes *only* an Intel FileVault
APFS copy-on-write clone of an already stopped, source-pinned HD recovery
cluster. No HEL1 PG role or website configuration was touched.

## Exact physical source and resulting receipt

- Rehearsal source:
  scripts/settlement_c03_intel_hd_preconnected_role_owner_rehearsal.py
- Source SHA256 **89ff8a211a9b1df0f42c04c24bad75db0405fbf0694d50be16162ea6010026ab**
  (the exact script transferred to Intel, SHA verified there and executed).
- Original C07 physical HD PG16 full-data restoration receipt SHA256
  **7a8d495b4259c5316f0f38ff060667d6b81f1243f77e1656daf2765da3603305**.
- Exclusive private replay destination:
  ~/.wolo-owner-authority/c03-intel-preconn-hd-v3-20261109/.
- Original Intel mode0700 receipt, mode0600 file:
  c03-real-hd-preconnected-dml-denial.json SHA256
  **c571ea1f03ab62feef505bf08453f2513f77460601bec4f19cead9eb4c80d3e6**.

On November 9 the physical test cloned actual 11GB HD restored PGDATA
using APFS clonefile, started **PostgreSQL 16.15** inside a private
Unix-socket-only directory with no TCP listener, and verified all **190**
original HD public tables were restored. Exact name/semantic/explicit-asset
source classification selected **60** financially sensitive tables.

The test recreated an original legacy HD LOGIN owner on those protected
tables, granted the old role the original DML shape, and connected a
real persistent psql backend *before* any migration.

1. The already-connected legacy backend executed a no-op DELETE WHERE false
   under pre-migration owner privileges; success was required.
2. In a second independent authenticated PostgreSQL client, all 60
   selected tables were moved to a dedicated NOLOGIN finance owner in a
   transaction, old PUBLIC and legacy grants were revoked, and deliberate
   SELECT-only legacy access was restored.
3. Source verified all 60 original table owners changed, and zero
   original-role INSERT/UPDATE/DELETE/TRUNCATE privileges remained.
4. The **same preconnected original backend** issued the same no-op DELETE.
   PostgreSQL denied it with a permission error. Its protected SELECT
   continued to succeed.
5. A fresh newly connected legacy backend also received DML permission
   denied. The deliberately unclassified original users table retained
   the old role's UPDATE privilege *in the sandbox* to show this was not
   merely NOLOGIN or a blanket revoke.

The isolated PostgreSQL server was cleanly stopped. Both the untouched
C07 source cluster and the new rehearsal clone were subsequently verified
to be stopped. Replayed test response contains no customer records,
credentials, wallet secrets, or payment transactions.

## Limits that must remain explicit

This test checks preconnected idle-backend privilege invalidation, not
in-flight transactions/held row locks, every finance-bearing table or
every sequence. The 60-name conservative source classification is
**not proof of the complete 190-table schema writer graph**. Granting
old-role access to the sandbox users table does not establish that its
all-column production update privileges are finance-safe. Source
restoration has intentionally different original role/ACL state
from HEL1's actual production catalog and is not jointly quiesced with
the DE restore.

A real C03 release still requires: classified HD/DE object and sequence
coverage; exact active service/JWT/indexer/tokenchain and preconnected
session scope; fresh synchronized C06 backup and same exact C07 restore;
reversible production-only finance writer freeze and application-safe
ACL owner transfer; Session B **authenticated Steam** continuity and
public restricted rollback acceptance. C04 legacy 8092/8093 mask remains
intact. C09 exact signed canary authority remains independently required.

**C04 and C08 CLOSED. Seven Chain gates OPEN. No WOLO moved.**
