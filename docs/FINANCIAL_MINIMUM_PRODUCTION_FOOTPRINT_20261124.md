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

# Financial minimum production footprint: native storage classification

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

## Exact image disposition decision — Nov24 follow-up

Preserve the entire original image by default. Its root directory names
were captured in the prior read-only debugfs listing, not fresh heavy IO:

| Exact image-relative directory | Preservation requirement |
| --- | --- |
| online-mvcc-rehearsal-20261105 | Original fixture/capture inputs, outputs, manifest, comparisons and failure evidence |
| offline-pg16-rehearsal-20261105 | Original physical PG16 recovery data and control/role/ACL/parity evidence |
| archived-financial-journal-only-20261023T210040Z-two-settlement-node-untouched | Both original journal trees and RESTORE-HELD-RECEIPT.json (1014 B observed), without invoking settlement |
| online-mvcc-age-offhost-20261105 | Original age/offhost recovery artifacts and transport receipts |
| online-mvcc-age-v2-20261105 | Distinct v2 lineage; do not deduplicate against earlier version by name |
| nonquiesced-settlement-journals-v2-20261105 | Original nonquiesced provenance, journal state and any incomplete/failure evidence; not a C06 checkpoint |

These are preservation classes based on the observed names and earlier
root listing, not assertions that any specific uninspected nested file
exists. Keep the complete contents including hidden files, lost+found,
filesystem journal, superblock/UUID, allocation metadata, deleted/free
blocks and all unknowns. No historical receipt is to be rewritten, nor
an old rehearsal relabeled as gate closure.

### Full image vs content-only archive

Full raw-image age ciphertext, optionally with reviewed lossless
compression before encryption, followed by exact byte reconstruction and
independent SHA256 comparison, preserves the whole image. Source identity
is dev2049/inode2431572, root:root mode0600, size42949672960 B,
allocated 42949709824 B (83886152 512-byte blocks), wrapper 42949718016 B.
Use a fresh exact preimage including device/inode/link count/mtime/ctime,
logical length and allocation when WE2 admits IO. No hash is known yet.
Full image may include historical secrets and deleted material; encrypt
to the existing approved financial recovery recipients, prohibit public
upload, M1 plaintext staging, arbitrary SSH or SITE_RUNTIME-purpose grant.
No plaintext temporary copy on HEL1 DATA: its measured free space is below
the original image length. Use only a reviewed existing financial
recovery transport with separately admitted exact object/class and byte
limit; WE2/WE4 must establish that it supports this large object and
direct streaming. No implied extension of #188/#191.

Content-only archival can preserve named logical file content and explicit
metadata (uid/gid, mode, ACL, xattrs, nanosecond times, symlinks/hardlinks,
special entries, sparse extents, inode flags, filesystem parameters and
all original provenance) but does not reproduce the original image bytes,
inode layout, journal, free-block history or deleted evidence. It cannot
substitute unless the owner explicitly changes the preservation contract
after full evidence/consumer review and independently proven reconstruction.
A 3.27GB used-block estimate is not an archive upper bound. Until such
approval, use full-image exact recovery; no content-only retirement.

### Sequential Intel capacity and legacy dependency

WE4 #63 comment7134935702 reports Intel free219106541568 B with the
unchanged 60GiB/64424509440 B reserve. No new direct Intel shell evidence
was obtained this turn. Conservative no-compression age planning bound
42992664576 B = 42949672960 + ceil(42949672960/1024) + 1048576.
One retained ciphertext plus one fully allocated exact reconstruction =
85942337536 B; remaining free133164204032 B, of which 68739694592 B is
above reserve BEFORE VM filesystem overhead, guest base, scratch and
other pending campaigns. This is arithmetic feasibility, not admission.
Require measured actual Intel guest-backed disk capacity and physical
allocation, not APFS sparse logical size, before opening the exclusive
window. Budget retained ciphertext separately even after temporary
reconstruction cleanup. The C06 capture and C07 independent restore
need their own exact manifest, encrypted archive and fully allocated
working-set budget, no compression credit, no overlap with SITE_RUNTIME
or Traffic acquisition, no reuse of a stale size estimate as a permit.

Legacy local restore source requires the precise full-allocation
root-backed loop ext4 and 8GiB ROOT available AFTER allocation; do not
weaken it or pretend a remote path satisfies it. The retirement decision
must preserve a tested on-demand rehydration option (exact image restored
to a fresh owner-approved ROOT path, exact byte verification, original
wrapper, mount identity and guard checks before legacy use), or formally
supersede the legacy operation through reviewed independently qualified
C06/C07. No active dependency may point to a retired path without a
reviewed cold-recovery procedure. Current native C06 source remains
fixture-gated, so the legacy dependency is NOT yet resolved physically.
After exclusive admission, qualify exact reconstruction in isolated Intel
Linux, no replay/mutation of historical DBs, read-only no-journal-replay
inspection; record raw SHA equality, filesystem geometry, all six
directories, root entries, metadata and original receipt hashes.
WE4 supplies independent authenticated receiver/restore receipt;
WE2 validates authoritative exact object, quiescence, replacement
recovery, approved retirement and measured before/after delta. Preserve
original until all prerequisites hold. No image IO initiated this turn.

### Native C06 engineering increment

New native offline PG16 checkpoint component uses exact PG16 binary and
system-identifier binding, clean shutdown, actual REDO WAL name and segment
size, pg_control digest, rejects postmaster PID, nonempty tablespace or
prepared-transaction directories, symlink WAL and external mount. Reads
the control result twice and rechecks identity. No service mutation; the
caller must supply genuine complete producer and reconnect exclusion,
authenticated lease, frozen Comet/journal observations and archive driver.
The expanded witness source-pin set now includes this component. New
focused tests and existing native witness tests PASS; the existing
disposable PG16 CI case additionally exercises the actual native parser
and descriptor-relative tree check, rather than another standalone
rehearsal. No live C06 call, no enrolled witness or gate closure.

### Transfer phase telemetry — Nov24

WE4 owns Transfer OS performance integration under VPSSentry #63. The
financial stream primitive now returns wolo.financial.transfer-phase.v1:
monotonic nanoseconds, exact byte counts, age binary hash, producer wall,
plaintext pipe write, pipeline wall, ciphertext pipe read, destination
write/fsync/readback and publication. The exact-image descriptor reader
separately measures source read and sink write, compares pre/post inode
metadata, all logical bytes and optional source hash. Independent
reconstruction readback validates exact length and SHA256. No new
transport endpoint, admission mechanism or retention controller.

Pipeline spans overlap; do not add them or interpret pipe waiting as
encryption CPU or network latency. The local stream cannot observe remote
transport, authenticated ACK, encryption CPU, or independent restore:
these fields remain null, not zero. WE4 must map corresponding measured
remote receiver and restore phase receipts to the existing canonical
private telemetry contract, correlate by exact campaign/object/ciphertext
identity and preserve provenance. The local component does not issue ACKs.
Production metrics require actual approved route/campaign receipts; no
extra heavy scan or benchmark during active work.

One small single-host M1 synthetic regression physically exercised age
dual-recipient encryption and exact reconstructed bytes (106496 plaintext,
106810 ciphertext), source read 26417ns, pipeline wall 12546542ns,
destination write 67291ns, fsync 85625ns, readback 115458ns,
restore 10119416ns, restore verification 80542ns. These are one fixture
sample, not route throughput, independent Intel evidence or a basis to
extrapolate the 40GiB transfer. No source image IO occurred.

Prior observed C089 616404482 ciphertext bytes /2795.63s (~220488 B/s)
is historical end-to-end baseline only. At that observed rate a 40GiB
image alone would take about 54 hours, before reconstruction. Existing
bounded local stream timeout max 14400s and historical unquiesced SQL
transport max 12GiB/1800s are not qualified for this object. Do not
reuse or extend those limits silently. WE2/WE4 must review a real
financial-purpose route, exact byte/time capacity, authenticated progress
and failure/reconciliation semantics within a compatible exclusive
window, without weakening current constraints. No route claim, image
archive or actual retirement admission from the new primitives.

### Exact-head CI, coordinator witness seam and historical M1 evidence

Foundation run45420617318 job138538782741 at 826f43c failed three
C08 fixture cases because they depended on actual /usr/bin/false
metadata on the Ubuntu runner. Test-only explicit simulated OS
metadata and socket state now exercise the unchanged production trust
predicate, including missing/symlink/non-root/group-writable/world-
writable refusal before subprocess execution. 13/13 local PASS;
native OS trust and deny-only runtime unchanged. Full fresh CI required.

Native coordinator witness binding now loads only pre-existing
root-private exact-plan phase packets from the protected authority
directory, uses the existing pinned NativeWitnessClient, checks the
locked local journal against phase and previous tip, and anchors the
actual durable journal record rather than caller-supplied record bytes.
An uncertain consume/anchor is not retried. Native witness tests 4/4
local PASS, not physical enrollment. The coordinator still refuses
live execution; remaining external per-effect anchoring, genuine WE2
lease, full producer/reconnect exclusion, native chain/checkpoint and
capture/restore/restart composition are required. No owner packet or
trust setting created, no old protocol replaced.

Historical M1 exact path metadata at Nov24 15:12-15:15Z:
owner-private c06-full-precapture-20261108 HD unquiesced ciphertext
872018705 logical B, 872022016 allocated B, nlink1; existing source
receipt records expected SHA b011a0a7949199a8b124650f9d16e3280264cca70380a789438fbe4221e504a4
(see C06_HEL1_LOCAL_AGE_ENCRYPTED_HD_UNQUIESCED_PRECAPTURE.md).
Adjacent historical LAN transfer log final line records 872018705
bytes, 100%, 6.46MB/s, 00:02:08. That is a historical sender-side
display, not authenticated destination readback or same-campaign
independent restore evidence. C07_INTEL_SOURCE_PINNED_UNQUIESCED_DATABASE_RECOVERY_HOLD.md
proves DE only; do not infer HD independent recovery. The separate
encrypted global-roles file is 2441 logical/4096 allocated B. Keep both,
and original logs, pending WE4 exact existing Intel receipt match.
No new full hash, transfer, decryption, deletion or capacity credit.
Candidate is distinct from the 40GiB image and from the new
whole-cluster C06/C07 archive.

WE4 passive receiver-window samples 449446 and 513050 B/s, median
481248 B/s, imply about 24.8h for 40GiB before extra phases; 4h
requires about 2.98MB/s before overhead. These are different scope
and boundary from the historic LAN rsync display and C089 operator
wall. No controlled optimization claim. For the existing WE4
resumable design, bind the owner-approved financial purpose, original
exact image identity/length, ordered immutable ciphertext chunk
digests and lengths, authenticated durable checkpoint, continuation
scope and final exact original raw SHA. Preserve encrypted-only
staging, independent Intel verification and full restoration,
legacy rehydration requirement, 60GiB reserve, all six historical
directories, one-use authority and no retirement from partial ACK.
WE2 controls exclusive IO; WE4 owns route/policy engineering.
