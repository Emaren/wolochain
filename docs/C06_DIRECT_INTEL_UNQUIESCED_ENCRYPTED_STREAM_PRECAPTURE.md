---
id: "aoe2war.wolochain.c06-direct-intel-unquiesced-precapture"
title: "C06 Direct HEL1 to Intel Encrypted Financial Precapture — Nonfunded Rehearsal"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["operators", "developers", "financial-reviewers", "ai-agents"]
source_of_truth: "git"
authority: "read-only-unquiesced-backup-rehearsal-hold-not-c06-acceptance"
reviewed_at: "2026-11-09"
review_interval_days: 7
sensitivity: "restricted"
---

# C06 Direct HEL1 to Intel Encrypted Financial Precapture — Nonfunded Rehearsal

The real owner-M1 source SHA256 **1c011f8676b9ff9c6c70178a404942b610d4a620951b931bcae565f44c979ded** was physically executed November 9 UTC from a separate private owner directory. This file is a byte-identical Git source copy, not a replacement binary, signed permit or new runtime. Unlike the first precapture script, it avoids the M1 16 GiB temporary-dump floor entirely: PostgreSQL custom compressed output from root-authenticated HEL1 pg_dump is piped through locally installed age encryption on M1 into a separately pinned Intel destination over a host-key-verified SSH reverse tunnel. No cleartext database dump exists on M1, Intel or the HEL1 filesystem.

The two age recipients are the original M1 recovery public identity and the separate **Intel FileVault-backed C06-only** identity. Intel's SSH host key is pinned by SHA256, not accepted from an unauthenticated keyscan. The Intel destination uses exclusive .part creation and a 12 GiB ciphertext maximum; all three source/age/offhost pipeline return codes must succeed. Intel ciphertext is hashed from disk, staged, atomically finalized without overwrite, and independently rehashed from disk before the owner M1 writes a private physical receipt.

## Physically proven DE path (November 9)

- Real HEL1 DE pg_dump 16, no writer migration, service change or chain transfer.
- Intel encrypted ciphertext length **349608 bytes**, SHA256 **6d7b63d94e1e9fcbea07cadc482e1c8914eb90ceb7b31ade19efcd8a580aa4bc**.
- Owner-only physical capture receipt SHA256 **324a6618dd03581674b49dc2c9f9db49264e940a8909a955190fbbd3366bfe27**.
- Separately tested Intel-only original DE ciphertext decryption authenticates the entire age stream, cleartext PgCustom SHA256 **af22c5e031a70af0e0bee5dad31e7fdff7ce8efa95b9bbdc608717f694ce7bcf**.
- Real isolated Intel Pg16 restore (no TCP, private Unix socket, no owner grants) yielded **52 public tables, 50 sequences, TCP listening disabled**; restored catalog SHA256 **de808a07113f7c40f0f2ac3fd651866f365ba752fd2f79c4d63880af09542f29**. Database stopped cleanly.
- HD direct streaming was still in progress at this document's first authored time. Never infer completion without a new verified exact private HD receipt and Intel readback.

## Trust limitations

This source implements a **nonquiesced / non-atomic** physical rehearsal, not an accepted C06 or C07 financial capture. It does not stop all existing financial writers, capture synchronized HD/DE MVCC snapshot coordinates or a trusted Comet bank root, WAL and settlement journals at the same boundary. A successful isolated DB restore is genuine recovery evidence but does not establish funds finality, source role ownership fidelity, nonce/journal consistency or a funded execution permit.

The public web 3032 and protected rollback 3030 must be preserved, and legacy 8092/8093 not confused with native 8094/8095. Do not use the script to certify C06/C07. Continue until: B proves authenticated Steam admin/nonadmin and a finance-safe rollback; A enforces temporary writer quiescence; full same-boundary encrypted HD/DE/chain/journal manifests are captured and restored on Intel; a freshly approved C09 exact canary executes once.
