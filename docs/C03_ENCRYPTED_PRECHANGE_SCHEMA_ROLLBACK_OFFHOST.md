---
id: "aoe2war.wolochain.c03-encrypted-prechange-schema-rollback-offhost"
title: "C03 Owner-Only Encrypted Off-Host Schema and Role Pre-Migration Rollback"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war", "aoe2dewarwagers"]
audience: ["operators", "developers", "financial-reviewers", "ai-agents"]
source_of_truth: "git"
authority: "pre-migration-source-metadata-insurance-only-not-full-financial-backup-or-writer-fence"
reviewed_at: "2026-11-08"
review_interval_days: 7
sensitivity: "restricted"
---

# C03 Owner-Only Encrypted Off-Host Schema and Role Pre-Migration Rollback

## Why it exists

C03 physical finance-owner containment requires changing the effective HD/DE PostgreSQL ownership and runtime role capabilities, while preserving signed-in R25 application authentication and its rollback. A safe role transition must retain the existing DB schema/grant/role state for independently reviewed rollback. This metadata backup is NOT the C06 full customer-state capture or C07 isolated restore.

The capture is allowed **while finance writers are still live**, since it is a **read-only pre-migration snapshot of metadata only**, not a synchronized financial state or any authorization to apply DDL. Actual C03 changes require a separate current-source approved and rehearsed reversible DDL, exact protected 3030 finance-safe rollback and complete writer quarantine; C06 must later capture all HD+DE row data/WAL/journals after the real fence.

## Physical procedure

The M1 owner-only controller `scripts/settlement_c03_prechange_encrypted_schema_recovery.py` executes only three fixed `pg_dump`/ `pg_dumpall` read-only commands through authenticated HEL1 SSH:

1. PostgreSQL 16 `pg_dumpall --globals-only --no-role-passwords` to preserve role/permission definitions without export of stored password hashes.
2. PostgreSQL 16 `pg_dump --schema-only --dbname=aoe2hd_db`.
3. PostgreSQL 16 `pg_dump --schema-only --dbname=aoe2de_db`.

Plaintext streams directly into age v1.3.2 encryption on M1 memory pipes; **no cleartext SQL files are created on disk**. The ciphertext is encrypted to exactly two existing fingerprint-checked independent SSH ED25519 recovery public identities: M1 `SHA256:MfpOL/mXaiHhlPqSaB8ClcVSAUONefzrj2qtPHlsRyU` and Intel `SHA256:I2ho/SRV9RhQFtUSY3qBEC9Gsr0YsPvbr7t8do18G0I`. The Intel SSH transport is separately pinned to `SHA256:bU10Y1SlXTa8YCm5lphUYsMrxMSdP8D0VIQJ0C2zeEg`.

The owner M1 transfers ciphertext via SSH proxy to the enrolled Intel through HEL1 loopback port 22996. File operations demand mode0700 private parent, exclusive-create 0600 final file, bounded cipher size, SHA256 and byte length. Each ciphertext is checked again by a second authenticated Intel readback. M1's encrypted transient bytes are removed after success; no private decryption key is read or copied and no owner password/passphrase is exposed.

## Physical November 8 execution

The owner M1 ran `--mode inspect` first; both recipient fingerprints and Intel transport identity PASS. The original `--mode capture` saved the encrypted **globals** file but its separate readback failed, specifically because Intel's default `python3` is **3.8**, which does not support `hashlib.file_digest` (introduced in 3.11). The controller failed closed; no success receipt was issued. The original encrypted globals object was preserved with independent SHA256 `26d31d0b3a77980823dbab65f413a87df1d51b003e3fab012f54b6e022` and exactly **2443 bytes**.

Code was changed to stream hashes using Python3.8-compatible `hashlib.sha256().update`. A new, narrow `--mode resume-globals` requires the exact existing globals ciphertext SHA/length and independently re-checks it before separately exporting HD and DE. No pre-existing private file is overwritten or deleted.

The full three-file **schema-only** source-bound capture then physically returned:

`PASS_C03_PRECHANGE_OFFHOST_ENCRYPTED_ROLLBACK_SCHEMA_ONLY`

Owner-private receipt is mode0600 on M1 under `~/.wolo-owner-authority/c03-prechange-schema-20261108/schema-prechange-encrypted-receipt.json`, SHA256:

`710275915a7ededb45a8344c03815ab68f88d272d474389e78bdfd8fed0409c4`

All three encrypted artifacts remain owner-private on Intel under `~/.wolo-owner-authority/c03-prechange-schema-20261108/`; no plaintext row data, bank state, wallet secrets or keys exported. No HEL1 unit/DB role/permission changed, no customer WOLO moved. The receipt explicitly denies source-consistent joint HD/DE data, chain height, C06 full backup, C07 restoration, financial release and funded activation.

## Key recovery check still required

A ciphertext SHA and original recipient key match prove storage/transfer integrity, but do **not** prove that the owner can presently decrypt or restore those files. The owner should eventually run a *locally reviewed, passphrase-prompted, no-plaintext-disk decryption test* with the separately controlled recovery private key, reporting only decryption success and checksum. This source deliberately cannot unlock owner credentials from chat, macOS Keychain or a synthetic signer.

## Acceptance and tests

The dedicated source-only test suite checks allowlisted three Pg16 metadata-only commands, strict recipient SSH identity parsing, two-recipient binding, remote O_EXCL/NOFOLLOW, original globals resume integrity, remote SHA/length negative cases, source defaults, owner0600 receipt idempotence and every false funded/backup/restore flag. CI shall run these fixtures; live owner receipt does not belong in GitHub.

**Formal finance status: C01–C09 HARD HOLD, 8094/8095 closed**. This closes only a technical rollback-preparation subtask; the live C03 writer fence and complete C06/C07 have NOT been executed.
