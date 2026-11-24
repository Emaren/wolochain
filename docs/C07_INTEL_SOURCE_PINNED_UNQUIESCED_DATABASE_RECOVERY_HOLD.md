---
id: "aoe2war.wolochain.c07-intel-source-pinned-unquiesced-database-recovery-hold"
title: "C07 Intel Source-Pinned Unquiesced Database Recovery HOLD"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["operators", "developers", "financial-reviewers", "ai-agents"]
source_of_truth: "git"
authority: "nonfunded-real-offhost-recovery-rehearsal-not-gate-closure"
reviewed_at: "2026-11-24"
review_interval_days: 7
sensitivity: "restricted"
---

# C07 Intel Source-Pinned Unquiesced Database Recovery HOLD

## Actual physical source and replay

The owner M1 source SHA256 **1b1a4412bf2f08e61fd4524472c2a17b8d946f832924c6bc62c1aa387891a3ab** was copied byte-for-byte to the FileVault-enabled independent Intel recovery machine and physically executed as the unprivileged local owner. It does not run on Linux HEL1, on the arm64 M1, or as root. The Intel source path is owner-private under the local C07 source-tools directory; no private recovery key material leaves Intel.

On November 9 UTC the program authenticated the actual original encrypted DE backup with exact ciphertext SHA256 **6d7b63d94e1e9fcbea07cadc482e1c8914eb90ceb7b31ade19efcd8a580aa4bc** (349,608 bytes), checked the mode0600 ciphertext, mode0600 locally stored Intel recovery identity, pinned recovery public key SHA-256 and FileVault ON, and used local age to decrypt the entire stream directly to isolated native PostgreSQL16 pg_restore with --exit-on-error. No plaintext archive was written.

The new isolated PG16 instance used only a temporary owner-private Unix socket and an empty TCP listen_addresses. The actual restored DE database contained **52 public tables and 50 public sequences**; the socket-only server stopped cleanly. The new original source-bound Intel physical restoration receipt SHA256 is **df21fa2e67319e606a530af501c5b108831178c27fb98c79b31e02bb166a5bb7**. This is an independent repeated, reproducible DE restoration, not merely archive listing or transport checksum.

The program also pins the separately captured full HD **872,018,705-byte** locally age-encrypted ciphertext SHA256 **b011a0a7949199a8b124650f9d16e3280264cca70380a789438fbe4221e504a4** and its expected 190 public tables and 180 public sequences. At the first source review, this HD ciphertext was still in resumable encrypted-only transit from HEL1, so the HD Intel restore is NOT claimed.

## Financial integrity limits

**C06 and C07 remain OPEN.** The two real captures were UNQUIESCED, taken at different moments; the exact accepted cross-system financial writer freeze, original transaction journals, PostgreSQL WAL, synchronized HD+DE snapshot, authenticated consensus/bank checkpoint and final live recovery/rollback are not yet physically proved. Do not equate an isolated DE recovery with custody solvency, exact payment finality, a writer grant or C09 approval. No financial roles, original 8092/8093, 3030/3032, 8094/8095 or wallet funds are altered by this script.

## Current applicability — reviewed 2026-11-24

The November 9 DE recovery is historical and remains valuable; do not repeat it or infer HD completion. PR #258 separately qualifies physical PG16 and CometBFT/SDK LevelDB restoration on disposable M1/Linux fixtures. C07 requires the exact newly admitted coordinated C06 ciphertext, independent isolated recovery and original checkpoint parity, not a new unrelated archive. Physical PostgreSQL recovery requires a compatible isolated Linux PG16 target and exact shared-cluster scope.

Current execution boundary: C04 and C08 are closed; C03, C06 and C07 remain open. Temporary complete producer/reconnect and chain quiescence is required for C06, followed by independently verified C07 recovery before permanent C03 writer exclusion. Financial listeners 8092–8095 remain closed; PostgreSQL remains loopback-only; preserve the 3030 rollback and 3033 emergency runtimes. Shared website/other PostgreSQL dependencies require authenticated B PREPARE and a reviewed maintenance/restoration window; WE2 must admit exact capacity and noncompeting workload priority. No production outage, signing or financial activation is authorized by this review. Funding DENIED.

Evidence: [coordinated checkpoint PR #258](https://github.com/Emaren/wolochain/pull/258), [physical receiver receipt](https://github.com/Emaren/wolochain/issues/239#issuecomment-7131784934), [native recovery and coordinator evidence](https://github.com/Emaren/wolochain/pull/258#issuecomment-7132828076). Historical observations above are retained as dated evidence, not current runtime claims.
