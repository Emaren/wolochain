---
id: "aoe2war.wolochain.c03-real-production-schema-owner-rehearsal"
title: "C03 Real Production Schema Isolated NOLOGIN Ownership Rehearsal"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["developers", "operators", "ai-agents"]
source_of_truth: "git"
authority: "source-only-isolated-negative-proof-never-a-production-DDL-permit"
reviewed_at: "2026-11-06"
review_interval_days: 7
sensitivity: "restricted"
---

# C03 Real Production Schema Isolated NOLOGIN Ownership Rehearsal

## Boundary and purpose

This controller tests actual HD and DE **schema definitions** (tables, attached sequences, triggers and views), from source-hash-verified *schema-only* dumps of the current HEL1 PostgreSQL databases, against a temporary PostgreSQL 16.15 instance on the Intel recovery Mac. It does not import customer rows, retain a production database connection, copy signing keys, permit payments or authorize any live DDL.

Exact pinned inputs obtained from HEL1 via `pg_dump -Fc --schema-only` and delivered using preexisting host-pinned SSH:

- HD `aoe2hd_db.schema.dump`: SHA256 `f70f244080296a46b92722d331fc3087fcf75e68629092e9b72d5f00603b6228`; 1,200,773 bytes.
- DE `aoe2de_db.schema.dump`: SHA256 `54e79f002c0d6691633e7616e4ca992b52bd67d2f17509357c69dad98c31de89`; 222,033 bytes.

These are **not C06 backups**. They represent only schema state, not a consistent coordinated financial capture or isolated C07 restore of balances, claims and journals.

## Real-schema physical rehearsal

On Intel `MacBookPro11,3`, macOS 11.7.4, Intel architecture `x86_64`, owner-only PG16.15 binaries at `~/.local/aoe2war-pg16-16.15/bin`: an ephemeral private Unix-socket-only PostgreSQL cluster was initialized with no network listener and removed after verification. Both production schemas restored from the exact archives.

The isolated physical run then created disposable legacy LOGIN roles and NOLOGIN financial owner roles, simulated the original legacy ownership of identified finance tables/database/schema, and migrated actual finance relation ownership to the new NOLOGIN roles.

| Check | HD | DE |
| --- | ---: | ---: |
| Restored finance-named base tables | 24 | 10 |
| Attached sequences changed to neutral ownership | 23 | 10 |
| Modeled incumbent owner DML initially allowed | PASS | PASS |
| All finance-named table INSERT/UPDATE/DELETE/TRUNCATE catalog privileges denied after separation | PASS | PASS |
| Physical TRUNCATE finance table denied to legacy role | PASS | PASS |
| Physical ALTER TABLE finance table denied | PASS | PASS |
| Public schema CREATE denied | PASS | PASS |
| Runtime `SET ROLE` to neutral owner denied | PASS | PASS |
| Finance SELECT preserved through explicit grant | PASS | PASS |
| Ownership and DML restored in same disposable schema | PASS | PASS |

Result: `PASS_REAL_PRODUCTION_SCHEMA_ISOLATED_FINANCE_OWNER_REHEARSAL`.

This is a bounded **heuristic starting set**, not an exhaustive financial writer inventory. The exact 24/10 regex-named tables and their 23/10 attached sequences are not a proof that all tables, functions, grants, ownership/membership paths, service accounts, user timers, cron, Traffic and external signing authorities are contained. Existing triggers and dependent views require additional review before live SQL. The earlier `NOLOGIN` synthetic existing-backend counterexample proves that NOLOGIN alone does not revoke privileges from already-connected database clients. The live migration must separately terminate/drain forbidden sessions, prevent reconnect/SET ROLE/escalation and verify role-specific denial while preserving public Steam access.

## Execution and limitations

Source: `scripts/settlement_c03_intel_real_schema_nologin_owner_rehearsal.py`

- `--mode inspect` verifies Intel macOS x86_64 nonroot environment, pinned and privately owned PostgreSQL archives, toolchain presence and exact SHA256; it produces a synthetic HOLD report, without starting a database.
- `--mode run-isolated` starts an owner-private temporary local PG16 instance with Unix socket only, restores the SHA-pinned HD/DE schema archives, exercises role ownership, sequence owners, negative financial writes, positive allowed reads, membership and rollback, then stops and removes the temporary cluster.
- On wrong host, any changed source archive, changed table census, an unexpected allowed financial write, unexpected row-dependent error or cleanup failure: **HOLD/exit2**. No code path connects to HEL1.
- Tests exercise host admission, exact pins, safe SQL identifier parsing, bounded catalog output, no production connection/ports, and explicit HOLD behavior.

Do not use this report to issue a permit or apply DDL to live HD/DE. The required path remains: discover all writer-capable actors → source-reviewed reversible C03 temporary freeze → single coordinated encrypted C06 snapshot with full journals/authority metadata → C07 restore of **that same snapshot** → production-role and ownership migration tested on the C07 restore → separate reviewed physical C03-B live change. Formal C01–C09 remain HARD HOLD until independently accepted.

## Recovery evidence provenance

Source-only GitHub PR and current HEL1/Intel source receipts are separate artifacts. Final acceptance is only through the WoloChain #5 register with exact source SHAs and physical receipts; a merged branch is not a physical financial gate closure.
