---
id: "aoe2war.wolochain.financial-minimum-production-footprint-20261124"
title: "Financial minimum production footprint: native storage classification"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["operators","developers","ai-agents"]
source_of_truth: "git"
authority: "read-only-storage-classification-no-retire"
reviewed_at: "2026-11-24"
review_interval_days: 7
sensitivity: "internal"
---

# Financial minimum production footprint

WE1 source-owned contribution to VPSSentry #63 and financial authority #239.
These are native read-only observations from November 24 14:44–14:47Z,
not an irreducible minimum, an atomic checkpoint, a retirement permit or
a permanent reserve reduction. No database, log, chain, mount or live service
changed. Financial quarantine remains in force.

## Measured non-overlapping allocation by filesystem

| Filesystem | Category | Allocated bytes | Disposition |
| --- | --- | ---: | --- |
| ROOT | Whole shared PG16 cluster | 11789783040 | Required live; includes WAL, tables, indexes, globals |
| ROOT | Live wolo-1 data | 9249005568 | Required live; includes consensus WAL and indexes |
| ROOT | PostgreSQL logs | 1446760448 | Active and rotated evidence; retention review only |
| ROOT | Financial restore image wrapper | 42949718016 | Historical recovery and preallocated working set; conditional retirement candidate |
| ROOT | Financial maintenance source/staging | 224436224 | Preserve exact active/held source and evidence; classify older stages |
| ROOT | Legacy settlement local home | 151552 | Protected configuration and custody; do not inspect contents |
| ROOT | Pre-portfix chain home | 106496 | Historical, small, retain pending recovery/dependency classification |
| DATA | Primary settlement journal | 8015872 | Protected current state |
| DATA | Founder settlement journal | 2818048 | Protected current state |
| DATA | Historical settlement backups | 691220480 | Four dated sets; require recovery and dependencies |
| DATA | Financial-maintenance backup directory | 4096 | Empty allocation at observation |
| DATA | C06 public-age stage | 872054784 | Prior unquiesced encrypted evidence; preserve pending exact receipt review |
| DATA | Two C04 evidence sets | 3923968 | Closed quarantine evidence, retain |
| DATA | Placeholder chain home backups | 16384 | Historical, retain pending classification |

ROOT available 10933174272 B; DATA available 31255379968 B at 14:44Z.
The listed allocations are not whole-filesystem totals or guaranteed net
reclamation. Do not add nested rows or count the same data as both PG logical
and physical sizes.

Whole-cluster PG16 base allocation 11692965888 B; pg_wal 83914752 B;
max_wal_size 1024 MiB (soft), min_wal_size 80 MiB, wal_keep_size 0,
archive_mode off, zero replication slots at observation. HD application
relations 192: table bytes 9525092352, index bytes 1728339968.
DE 52: table bytes 2301952, index bytes 3375104.
TokenChain Callisto 54: table bytes 136495104, index bytes 190218240.
These catalog sizes are nested within PG16, not additional filesystem
allocation. No live relation/index removal, vacuum-full, WAL removal or
unreviewed compaction.

Chain data suballocation: blockstore 3065757696 B, application
2443145216 B, transaction index 1609068544 B, state 1063915520 B,
consensus WAL 1066815488 B, snapshots 262144 B, evidence 32768 B.
Do not prune chain history or consensus WAL on the basis of size. Establish
actual growth/compaction peaks and recovery performance before changing
retention. Logs currently weekly rotate 10, copytruncate, compress with
delaycompress. Active PG log logical size 547928528 B; retain and diagnose
growth before reviewing retention. No log truncation.

## Major candidate: bounded.ext4

Native 14:45–14:46Z root-only metadata: path
/var/lib/wolo-financial-restore/bounded.ext4, device 2049 inode 2431572,
root:root mode0600, logical 42949672960 B, 83886152 512-byte allocated
blocks, mtime Nov14 22:44:35Z. No associated loop attachment, no open fuser
result, child mountpoint unmounted. Ext4 clean, 10485760 blocks of 4096 B,
9687181 free blocks, approximately 3.27 GB used including filesystem
metadata. This is NOT an empty disposable image. Read-only debugfs root
listing identified six historical recovery/evidence directories (online
MVCC, offline PG16, archived October23 financial journals, online MVCC age
offhost and v2, nonquiesced settlement journals v2). Preserve all.

The legacy maintenance controller explicitly requires the root-backed
preallocated 8–64 GiB isolated ext4 child for its local restore path.
This is a real source dependency, not a stale-path guess. New coordinated
C06/C07 must separately qualify independent Intel Linux restoration of the
identical ciphertext, with measured recovery working set. Do not remove,
shrink, format, mount, hash the whole image or copy it while the existing
SITE_RUNTIME campaign has exclusive IO. WE2 owns exact retirement admission.
Only after separate approved archival of its evidence, independent restore,
dependency disposition and replacement recovery admission may the existing
recovery policy consider retirement. Gross allocation about 42.95 GB is not
reclaimed space. Even an empty image would require replacement working
capacity before removal.

## Recovery working set and next dispositions

Current PG16 + chain + both journals totals 21049622528 allocated bytes,
before pgconfig, nonce state, logical vs allocated drift, exact tar manifest,
age overhead and working/compaction peaks. This is an observation, not
a ciphertext budget or permit. The existing C06 archive budget uses no
compression credit and separate DATA/Intel reserve and restore allocations.
Do not relax the 1 GiB DATA guard, the independent Intel reserve or any
WE2 production guard; require exact source-bound upper bounds and exclusive
IO/capacity lease.

Historical DATA backups, older staged binaries and image-internal evidence
are pending exact recovery IDs/receipts. The first priority is the 40 GiB
image disposition under the canonical WE2 queue; no parallel retirement
controller. M1: one additional clean redundant C01 source worktree retired
without force, remote and local commit e8364be7f3bb4652c6cbd03d1dc7c263eb9adbd2
verified, only two reproducible Python bytecode files removed first, no
open-file/process references observed. Previous gross allocation 9818112 B,
not net filesystem delta. Other source worktrees preserved pending unique
evidence review (including one inconsistent GitHub API lookup and current
C03 development).

Current formal gates C04/C08 closed, C01/C02/C03/C05/C06/C07/C09 open.
Funding DENIED; custody inactive. No C06/C07/C03 closure from this document.
