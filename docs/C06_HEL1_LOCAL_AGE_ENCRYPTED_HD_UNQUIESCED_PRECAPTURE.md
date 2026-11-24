---
id: "aoe2war.wolochain.c06-hel1-local-age-hd-unquiesced-precapture"
title: "C06 HEL1 Local Age Encrypted HD Unquiesced Precapture"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["operators", "developers", "financial-reviewers", "ai-agents"]
source_of_truth: "git"
authority: "inert-readonly-unquiesced-capture-not-c06-release"
reviewed_at: "2026-11-24"
review_interval_days: 7
sensitivity: "restricted"
---

# C06 HEL1 Local Age Encrypted HD Unquiesced Precapture

This is **the exact production-used physical source**, NOT a proposed future implementation. Its SHELL source SHA256 is **e8f83a39f7638b917791d274bd95aa6b7afa3455f5528458db02b7003774a2e8**. It executed on HEL1 at **2026-11-09 00:57:27 UTC** as root, on the fixed existing HC volume path, and finished after **67 seconds**. It neither opened 8094/8095 nor modified financial tables or original chain settlement.

## Precisely observed read-only capture result

- Native PostgreSQL16 original aoe2hd_db custom dump with compression -Z3, nice +15, ionice idle, a bounded DDL lock-wait.
- Standard Ubuntu-packaged /usr/bin/age v1.1.1 with its installed signed Ubuntu package source. It encrypted custom PgDump bytes as a stream using **only two pre-pinned public SSH Ed25519 recovery recipients**. No private recovery key, mnemonic, encrypted keyring or passphrase is copied to HEL1.
- The output was written exclusively as root mode0600 ciphertext under an existing root0700 HC volume directory; no database plaintext file is staged.
- Same-filesystem rename to a new final ciphertext path (no overwrite), file and parent directory fsync, SHA-256 readback, immutable JSON receipt mode0600.
- Resulting real HD ciphertext: **872018705 bytes**, SHA256 **b011a0a7949199a8b124650f9d16e3280264cca70380a789438fbe4221e504a4**. Root-only exact receipt SHA256 **36fc7ec035cefd7689ab26607564aa56037303da71a860c817f607a5b950a896**.
- A separate root-to-M1 resumable encrypted-ciphertext transfer began afterward. This is not yet evidence of Intel copy or restore.

This closes the prior **capture-time** bottleneck caused by HEL1-to-M1 wide-area bandwidth (~16 MiB in 54 seconds) and the old SSH pipeline ClientWrite/pipe_write backpressure. It permits an eventual short, bounded writer-fenced physical capture, then asynchronous offhost ciphertext transfer, provided that any final release boundary and WAN transfer are separately accepted.

## Hard limits and still-open acceptance

**C06 and C07 remain OPEN.** The physical HD snapshot above was UNQUIESCED and is only one database. It was not synchronized with DE, original financial SQL writers, durable financial journals, PostgreSQL WAL, validator-consensus header or independently anchored bank root. It cannot be treated as accepted offhost redundancy until the exact ciphertext is copied, hash-matched, decrypted and independently restored from Intel. It does not authorize C01 signer enrollment, C03 owner migration, C05 collateral or a C09 canary.

C08 remains formally closed (zero funded permission). Preserve the legacy chain, 8092/8093 and both 3030/3032 website profiles. Do not claim C06 from this successful script alone.

## Current applicability — reviewed 2026-11-24

The 67-second HD logical dump does not bound physical checkpoint downtime or full encrypted archive size. The 872,018,705-byte historical object remains a separate recovery point, never a substitute for the whole PostgreSQL cluster including WAL, closed chain state and journals.

Current execution boundary: C04 and C08 are closed; C03, C06 and C07 remain open. Temporary complete producer/reconnect and chain quiescence is required for C06, followed by independently verified C07 recovery before permanent C03 writer exclusion. Financial listeners 8092–8095 remain closed; PostgreSQL remains loopback-only; preserve the 3030 rollback and 3033 emergency runtimes. Shared website/other PostgreSQL dependencies require authenticated B PREPARE and a reviewed maintenance/restoration window; WE2 must admit exact capacity and noncompeting workload priority. No production outage, signing or financial activation is authorized by this review. Funding DENIED.

Evidence: [coordinated checkpoint PR #258](https://github.com/Emaren/wolochain/pull/258), [physical receiver receipt](https://github.com/Emaren/wolochain/issues/239#issuecomment-7131784934), [native recovery and coordinator evidence](https://github.com/Emaren/wolochain/pull/258#issuecomment-7132828076). Historical observations above are retained as dated evidence, not current runtime claims.
