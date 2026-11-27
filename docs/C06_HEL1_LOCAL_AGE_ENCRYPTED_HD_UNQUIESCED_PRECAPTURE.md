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
reviewed_at: "2026-11-27"
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

## November 19, 2026 — limited authority and dated evidence review

An AI source examiner acting through the sole owner's existing connected source workspace checked this document's 21 original body lines for repository-source links, gate-authorization claims, older governance conditions and current-versus-historical language; 0 referenced local source paths were resolved. This is a **scope and safety review**, not an independent human signature or a fresh validation of each historical physical claim. Original observations remain dated and unmodified.

**Topic-specific reconciliation (encrypted backup):** C06 is OPEN. Synthetic/partial/unquiesced captures do not establish a synchronized accepted encrypted off-host financial backup.

**Current controlling decision:** WoloChain issue #239 and reviewed code head `70a95e8f9cb0facbec314063e9deafe7e15aa550`. C04 and C08 CLOSED; C01/C02/C03/C05/C06/C07/C09 OPEN; funding DENIED. The original test/source facts remain evidence only and may not authorize live SQL, HBA, custody, funds, backups or a canary. Live acceptance requires exact source, legitimate protected owner authority and independent physical readback.

## Current applicability — 2026-11-27

Exact source and dated-evidence scope review only: this document was byte-identical to the November 19 reviewed version before this renewal. Its earlier observations, commands and receipts remain historical; they do not authorize live execution. Current gate precedence: [#239](https://github.com/Emaren/wolochain/issues/239), C04/C08 closed, seven gates open, no funded operation authorized. No new custody, reserve, backup, writer-fence or funded-canary certification. See `docs/WE1_SOURCE_SCOPE_REVIEW_20261127.md` for preserved preimage hashes and review limitations.
