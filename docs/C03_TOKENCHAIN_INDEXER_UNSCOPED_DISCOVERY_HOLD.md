---
id: "aoe2war.wolochain.c03-tokenchain-indexer-unscoped-discovery-hold"
title: "C03 TokenChain Indexer: Previously Omitted Service Discovery and Financial Writer HOLD"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2hdbets", "tokenchain"]
audience: ["operators", "developers", "financial-reviewers", "ai-agents"]
source_of_truth: "git"
authority: "read-only-discovery-only-no-maintenance-unit-change"
reviewed_at: "2026-11-08"
review_interval_days: 7
sensitivity: "internal"
---

# C03 TokenChain Indexer: Previously Omitted Service Discovery and Financial Writer HOLD

## Physical discovery

Live HEL1 runs `tokenchain-indexer.service` under the unprivileged `tokenchain` Linux account with process PID 985 at the November 8 observation. Its systemd unit SHA256 is `4984e6698058f29ff3ec53614d0b71161a04af9a042347eb47326a90643f6eea`. It was **not included** in the source's original eight prefix families, so the 57-unit financial writer-universe census omitted it entirely rather than classifying its database and indirect execution reachability.

No PostgreSQL DATABASE_URL or PGUSER was found in its direct /proc process environment. It does have a systemd EnvironmentFile, which is not by itself proof of missing SQL access, harmlessness, or financial writer capability. Neither its source, indirect API access, DB roles, file descriptors, nor external service authority has yet been fully classified. **Do not stop it, grant privileges, or assert financial isolation based on an absent direct environment variable.**

A separate live source proof confirms `aoe2-wolo-transfer-heartbeat.service` is **a genuine HD financial indexing writer**, not just a monitoring timer: the unit invokes `scripts/backfill-wolo-mainnet-transfers.mjs`; the App source calls `prisma.woloIndexedTransfer.update/create`; the effective selected database role username is **`aoe2hd_user`**, which still owns and directly writes all 190 HD public tables. Its original C03 controller source family is already enumerated, but an enumerated service is **not** a proven quiesced writer.

## Source change and failure boundary

`scripts/settlement_c03_physical_writer_universe_hold.py` now explicitly discovers service and timer names beginning with `tokenchain-`. All such units are **UNSCOPED_REVIEW_REQUIRED**, never automatically stoppable, deemed safe, authorized or counted as an accepted financial fence. It also exposes `tokenchain_indexer_direct_and_indirect_database_writers` as an unresolved evidence domain.

The six hermetic regression cases verify a real `tokenchain-indexer.service` entry cannot disappear, that active and dormant timer/service entries remain unscoped, an unexpected `tokenchain-ledger-repair.service` is not silently skipped, invalid unit names STOP, and the external review domain remains explicit. Existing core eight observer tests also pass. The dedicated suite is enrolled in GitHub Foundation CI.

**Critical source/runtime version boundary:** The previously installed, root-only C03 topology watchdog pins a **57-unit frozen census SHA**, described in `docs/C03_TOPOLOGY_ONLY_WATCHDOG_ENROLLMENT.md`. Adding any new discovered unit changes the census digest and unit count; it is **NOT** authorized to auto-enroll or overwrite the watchdog's old permit or source hash. This PR is source-side only. A subsequent independent physical HEL1 read-only census and explicitly reviewed root-only topology baseline migration are required before installing this source under the active C03 timer. The old watchdog must remain unchanged until that enrollment is approved and rollback checked.

**C03 remains HARD HOLD:** 3031 restricted website fallback lacks Steam/session SECURITY DEFINER EXECUTE and non-equivalent auth cookies, as Session B is repairing; Traffic protected scope also requires review. No running indexer, heartbeat timer, website, validator, DB role, protected C01 unit, financial journal, or asset was modified by this source patch. No WOLO funding or C09 permit is authorized.
