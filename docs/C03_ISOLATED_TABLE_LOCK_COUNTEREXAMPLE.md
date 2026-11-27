---
id: "aoe2war.wolochain.c03-isolated-table-lock-counterexample"
title: "C03 Isolated PostgreSQL Table Lock Counterexample"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["developers", "operators", "ai-agents"]
source_of_truth: "git"
authority: "source-only-negative-lock-rehearsal-not-a-financial-fence"
reviewed_at: "2026-11-27"
review_interval_days: 7
sensitivity: "restricted"
---

# C03 Isolated PostgreSQL Table Lock Counterexample

This source provides a **negative financial isolation test**. It proves why a normal PostgreSQL `SHARE MODE` lock on a finance table cannot, by itself, certify a globally quiesced financial backup.

## Independent physical rehearsal

The actual 2026-11-06 Mac-local PostgreSQL 14 ephemeral Unix-only cluster executed an unprivileged, throwaway fixture table `financial_shadow`. No HEL1, live HD/DE database, wallet, signer, real stake, credential, network listener or owner permit was involved. The source used a temporary private data directory/socket under `~/.cache/aoe2war`, `listen_addresses=''`, `unix_socket_permissions=0700`, and explicit start/stop with postmaster output redirected into the disposable temporary directory. All fixture data and PG processes were verified gone after the run.

Held an explicit `BEGIN; LOCK TABLE public.financial_shadow IN SHARE MODE` while a separate connection attempted operations. The following assertions passed in the physical run:

| Operation | Physical observation |
|---|---|
| Existing-table SELECT | succeeds |
| INSERT into locked table | times out on the conflicting table lock |
| ALTER same table | times out on the conflicting table lock |
| `nextval()` on the table's owned sequence | **succeeds independently** |
| `CREATE TABLE` elsewhere in the same schema | **succeeds independently** |
| Separate INSERT queued during lock, then barrier releases | **executes after lock release** |

Original exploratory v4 receipt SHA256: `1478bcc8f30788fc9780bc332272a2002d07c487780cbd06f36438b77e0e84f2`. Earlier timed-out exploratory runs reflected a local launcher file-descriptor inheritance defect, not a PostgreSQL assertion; the daemon was restarted with its own log file, tests reran, and temporary processes and directories were confirmed cleaned. Preserve failed logs as counterevidence rather than rewriting history.

The canonical source `scripts/settlement_c03_isolated_lock_counterexample.py` adds explicit, strict boolean invariants and negative proofs. Nine hermetic unit tests verify exact proof requirements, unknown/malformed observations, integer-vs-boolean confusion, local-only paths and root/non-Mac refusal.

## Consequence for C03/C06/C07 acceptance

**A share lock is not an admitted global finance fence.** The owned sequence `nextval` and unrelated schema CREATE operations bypass a table-only lock. More importantly, a pending legacy write that was blocked rather than permanently denied can execute when the lock releases. Locks in two distinct PostgreSQL databases are not a single cross-database atomic transaction; blockchain signing and settlement journals have their own concurrency. The legacy runtime roles are still the owners of the live HD/DE finance tables and databases.

A safe financial maintenance controller must verify all producer admissions and deactivation paths (including Traffic forward ledger, cron, systemd unit activators, API ingress, database reconnect and any in-flight write queue); it must then admit an effective nonowner/NOLOGIN finance permission design rehearsed against a C07 isolated restore. Backup capture requires **proof of no delayed write resumption** and full coordinated source/journal/authority state, not merely a series of table locks.

A genuine C06 encrypted offhost snapshot and C07 exact same-snapshot isolated restoration have not yet occurred. These gates remain HARD HOLD. Never use this test or its PASS result as authority to stop the validator, change grants, resume uncertain payments, alter production ownership, move WOLO or start Satchel 8094/8095.

## Safe isolated replay

On the owner **Mac M1 only**, with Homebrew PostgreSQL 14 binaries at `/opt/homebrew/bin` and no root privileges, run `python3 -B scripts/settlement_c03_isolated_lock_counterexample.py`. The script refuses root and other platforms, creates a throwaway Unix-only cluster, records only boolean outcomes, and exits 0 only for the fully demonstrated **counterexample**. It cleans up the isolated cluster. Run `python3 -B -m unittest discover -s tests -p 'test_settlement_c03_isolated_lock_counterexample.py' -v` for hermetic tests.

Running this command **does not fix C03, certify a freeze, establish a backup, or prove chain finality**.

## November 19, 2026 — limited authority and dated evidence review

An AI source examiner acting through the sole owner's existing connected source workspace checked this document's 37 original body lines for repository-source links, gate-authorization claims, older governance conditions and current-versus-historical language; 1 referenced local source paths were resolved. This is a **scope and safety review**, not an independent human signature or a fresh validation of each historical physical claim. Original observations remain dated and unmodified.

**Topic-specific reconciliation (financial writer exclusion):** C03 is OPEN. HD/DE original owner roles retain financial write capabilities. Restricted social V2 and Library filtered views are separate additive nonfinancial application contracts, not a global writer fence.

**Current controlling decision:** WoloChain issue #239 and reviewed code head `70a95e8f9cb0facbec314063e9deafe7e15aa550`. C04 and C08 CLOSED; C01/C02/C03/C05/C06/C07/C09 OPEN; funding DENIED. The original test/source facts remain evidence only and may not authorize live SQL, HBA, custody, funds, backups or a canary. Live acceptance requires exact source, legitimate protected owner authority and independent physical readback.

## Current applicability — 2026-11-27

Exact source and dated-evidence scope review only: this document was byte-identical to the November 19 reviewed version before this renewal. Its earlier observations, commands and receipts remain historical; they do not authorize live execution. Current gate precedence: [#239](https://github.com/Emaren/wolochain/issues/239), C04/C08 closed, seven gates open, no funded operation authorized. No new custody, reserve, backup, writer-fence or funded-canary certification. See `docs/WE1_SOURCE_SCOPE_REVIEW_20261127.md` for preserved preimage hashes and review limitations.
