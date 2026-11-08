---
id: "aoe2war.wolochain.c06-unquiesced-mvcc-dual-recipient-intel-precapture"
title: "C06 Preparatory Live-MVCC Full-Data Exports: Dual-Recipient Encrypted Intel Retention"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2hdbets", "aoe2dewarwagers"]
audience: ["operators", "developers", "financial-reviewers", "ai-agents"]
source_of_truth: "git"
authority: "prebackup-only-no-writer-fence-no-live-financial-release"
reviewed_at: "2026-11-08"
review_interval_days: 7
sensitivity: "restricted"
---

# C06 Preparatory Live-MVCC Full-Data Exports: Dual-Recipient Encrypted Intel Retention

## The obstacle

Formal financial C06/C07 require **writer-quiesced, complete, exact-epoch HD+DE+Wolo WAL/journal/account-state backup**, independently anchored off host, plus a destructive isolated restoration of that exact capture under witnessed control. Merely importing a preexisting schema or copying a live PG dump is NOT sufficient. C03 still has live legacy financial writers and an unresolved 33-unit source-unscoped systemd universe, and legacy 3030 is not a proven finance-safe rollback. Those gates are not bypassed here.

The source-held native C06 controller currently targets a HEL1 mounted volume for combined dumps and settlement snapshots. On Nov 8 16:18 UTC the *actual* read-only HEL1 controller reports:
- `aoe2hd_db` PostgreSQL logical size **11,171,027,991 bytes**, `aoe2de_db` **15,309,847 bytes**;
- HC capture volume free **18,519,453,696 bytes** and a separate mandatory 1-GiB controller reserve; an upper bound of **17,445,711,872 bytes** for a *separately approved* snapshot budget, **not** a guaranteed dump size;
- existing backup staging root is empty, and both dump/snapshot roots are on the same HC volume; legacy financial producers active;
- result **exit3 HOLD**, not capture authorization or C06 financial acceptance.

The Intel off-host Mac had **313,771,765,760 bytes available** and the M1 **23,204,847,616 bytes available** when independently checked. A separate off-host path can rehearse full-data transport without expanding the crowded HEL1 volume and without reading private recovery keys.

## Exact owner-only bounded operator tool

`scripts/settlement_c06_unquiesced_offhost_mvcc_precapture.py`, run *only* from the enrolled nonroot arm64 M1, defaults to the nonmutating `--mode inspect`. It explicitly supports only:

```bash
python3 -B scripts/settlement_c06_unquiesced_offhost_mvcc_precapture.py --mode inspect
python3 -B scripts/settlement_c06_unquiesced_offhost_mvcc_precapture.py --mode capture --db aoe2de_db
python3 -B scripts/settlement_c06_unquiesced_offhost_mvcc_precapture.py --mode capture --db aoe2hd_db
```

The capture commands are fixed and contain no caller-supplied SQL, shell destination or arbitrary flags: `runuser -u postgres -- nice -n 15 ionice -c3 /usr/lib/postgresql/16/bin/pg_dump -F c -Z 3 --lock-wait-timeout=5000 -d <exact db>`. Each PostgreSQL dump uses its own MVCC read snapshot, under low CPU/I/O priority. **No cross-database atomicity, WAL, independent Wolo Comet block evidence or writer quiescence is claimed**. A Pg16 dump can be used in a later isolated nonfinancial restore rehearsal, but is not alone evidence that older unconfirmed payouts were safely settled.

For each database, plain compressed `pg_dump` bytes flow via authenticated HEL1 SSH to `age` encryption on the owner's M1. The only local disk file is **ciphertext** in a mode0700 temporary owner folder; an age file-size resource limit prevents unbounded growth beyond 12 GiB. The ciphertext is encrypted against two *separately fingerprint-verified* existing owner recovery public keys:

- M1 owner public recipient: `SHA256:MfpOL/mXaiHhlPqSaB8ClcVSAUONefzrj2qtPHlsRyU`;
- Intel offhost recovery recipient: `SHA256:I2ho/SRV9RhQFtUSY3qBEC9Gsr0YsPvbr7t8do18G0I`;
- independent Intel SSH reverse-host key: `SHA256:bU10Y1SlXTa8YCm5lphUYsMrxMSdP8D0VIQJ0C2zeEg`, reached through *preexisting distinct C06* HEL1 localhost 22996;
- requires a 16-GiB M1 free floor and a 20-GiB Intel free floor before capture.

The owner-streamed encrypted bytes are retained only on Intel under an exclusive-create mode0700 directory and 0600 file, with a bounded receiver. No existing accepted ciphertext can be overwritten. Sender SHA256 and byte size must match the actual receiver SHA, then a *second independent authenticated Intel readback* must return the same SHA and size. Temp ciphertext on M1 is removed only after verified off-host retention. No secrets, keys, plaintext SQL rows, addresses or cookies appear in public logs or source commits. Owner-private digest/metadata receipt is mode0600 under `~/.wolo-owner-authority/c06-unquiesced-mvcc-precapture-20261108/`. Each database is separate, idempotent and individually failure-closed.

## Actual November 8 physical execution evidence

Source SHA256 at first physical execution: `6c4b1aa13780f8575810219790ebdf4f0fc29208b7d58040f2e291ffb70d8cd1`.

The native M1 `--mode inspect` passed both recovery recipient identities, exact SSH host fingerprint and Intel capacity; returns intentional `HOLD_C06_UNQUIESCED_OFFHOST_CAPTURE_READY`, exit3.

The much smaller **DE full-data** export was physically completed as a real PostgreSQL 16 custom-format read-only dump, age-encrypted to both existing public recovery keys, transported via authenticated C06 Intel route, independently SHA/length verified after retention, and the owner-private M1 receipt sealed:

- DE retained ciphertext size **349,608 bytes**;
- Intel retained ciphertext SHA256 `74415af50807ca01f113f3771eb1daf5f0a2d2ea0058ba9044315870e1bc987e`;
- owner-private DE receipt SHA256 `b488938b7ab701111ab4e624d769823c61441c89c1cceb80193478cd5bf51df8`;
- exact report status `PASS_UNQUIESCED_MVCC_OFFHOST_CAPTURE_HOLD`, `c06_formal_backup_gate_closed=false`, `financial_release_authorized=false`.

The much larger HD export must be assessed separately from its own fresh owner-private receipt; do not presume success from an ongoing transfer, a successful DE capture, or a prior code-level CI test. No HD/DE wallet transfer, database mutation, systemd restart, private key unlock or C08 witness nonce was used.

## Quality and acceptance boundary

The dedicated hermetic test suite covers exact Pg16 low-priority allowlisted commands, no arbitrary SQL, safe dual-key/host fingerprint checks, bounded private-file/age-only behavior, Python3.8 Intel readback compatibility, **real receiver code executed on synthetic encrypted bytes**, independent readback, hostile packet SHA mismatch with partial-file cleanup, replay rejection with original file intact, nonallowlisted DB refusal and 0600 owner receipt idempotence. No confidential production data is ever used inside CI tests.

**Formal C01–C09 still HARD HOLD.** This changes only the available *preparatory* off-host full-data evidence. A qualifying C06 still demands real C03 writer fences, same-window exact B-safe rollback, externally anchored immutable WAL/journals, source/current-owner signed backup permit, authenticated same-state capture, decryption and a physical isolated HD+DE restore with no counter reset or WOLO movement. Do not mistake this standby ciphertext for a funded recovery release.
