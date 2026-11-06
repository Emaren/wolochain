# C03 Financial Writer Containment — Physical Release Acceptance Protocol

Status: **HARD HOLD — design and acceptance contract, not a migration permit**. Last observed: 2026-11-06 UTC. Scope: legacy HD/DE PostgreSQL and all wallet/settlement/Traffic writer paths. This document must not be used to bypass the signed financial maintenance controller.

## Non-negotiable invariants

- Public R25 website on 3032, six Nginx selectors, its preserved 3030 rollback PID, and authenticated Steam sessions remain healthy. Native wolo-1 validator and legacy 8092/8093 services remain preserved; new Satchel 8094/reviewer 8095 remain inactive until full financial admission.
- A GitHub merge, test PASS or catalog count never closes C03 or authorizes a WOLO movement.
- No stale, unknown or hashless historical payment is automatically retried, refunded, credited, signed or rebroadcast.
- The sole actual human owner may approve a reviewed reversible maintenance operation; a funded transfer requires its **own fresh transaction-specific signed permit**, not a general maintenance approval.
- Every failed phase retains protected evidence and MUST NOT silently resume/rollback a real payment or invent a PASS receipt.

## Source-backed physical baselines

1. C03 unit universe: `settlement_c03_physical_writer_universe_hold.py`. Nov 6 live HEL1 receipt SHA256 `6b1aabed8d4f28ba980e6387cbc8487ce4337fa44d52fd79cbbbcaf646199d73`: 55 relevant loaded/installed units, 31 outside the existing 18-unit controller scope, 11 active outside it. In particular, Traffic's forward-ledger timer is outside the controller's owned set. **Unscoped means needs classification, not necessarily capable of financial writes.**
2. C03 DB role/owner: `settlement_c03_db_owner_boundary_hold.py`. Live receipt `32fffb3c89ab432e66da90b93294cac68925377b3a9080d48dc6ab773a69df52`: the HD legacy runtime role owns 24/24 finance-named public tables and its whole database; DE role owns 10/10 and its database. Both can CREATE in `public`. REVOKE on those same owners is ineffective.
3. Exact dependent-object observation: `settlement_c03_finance_dependency_hold.py`. Live receipt SHA256 `7e384519bd4d6d7523e08f3f8c0e26252f37e8de87558c16abdd0e1f7fe9669e`. HD 24 finance tables, 23 attached sequences, 12 non-internal triggers, 7 dependent view objects, 323 OTHER legacy-owned public relations. DE 10 tables, 10 attached sequences, 0 external triggers, 0 dependent views, 82 OTHER legacy-owned relations. All 12 HD trigger functions are legacy-owned but none SECURITY DEFINER; the seven HD dependent views are postgres-owned. **Finance-name heuristics are only a starting discovery set, never a complete financial-universe attestation.**
4. C06 current capacity observation: read-only `settlement_c06_capture_capacity_hold.py`, receipt SHA256 `c60e2bfbbc7ec41009b7546a33dde42cfabb46cfdf6e8b87237a3bc54fc16f5c`. Backup staging volume 17.568 GiB free, HD DB logical size 10.394 GiB, DE 0.014 GiB; physical dump size cannot be deduced from logical size. No quiescence or verified offhost encryption.
5. C07 isolated restore storage: `settlement_financial_maintenance.py --mode inspect-storage` observed a 40GiB backing image with 34.938GiB available (receipt `489799b0fc24c88b8f08d362937411ceddad196aecba40ebf4732bd667216acf`). This is NOT a restored current C06 backup.
6. Offhost Intel recovery reverse tunnel HEL1 loopback 22995 observed **ABSENT** at 2026-11-06 19:24 UTC. Do not claim offhost transfer readiness based on prior receipts.

## Required staged closure sequence

### C03-A — Production writer graph and reversible temporary finance freeze

- Enumerate and source-bind **every** writer-capable HD/DE API/worker/Next process, systemd service/timer/socket/path, root and user cron, Docker, Traffic ingestion/forward ledger, PostgreSQL role/pool/reconnect, trigger/SECURITY DEFINER execution, chain signer and journal writer.
- For every unit from the observer report, classify one of: *producer needing fence*, *essential protected runtime proven finance-read-only*, *unrelated with objective denial evidence*, or *UNKNOWN/HOLD*. Never interpret inactivity or an absent MainPID as an immutable fence.
- The current 18-unit finance controller includes the legacy 3030 rollback service. **It cannot be executed unchanged** if preservation of that rollback is required. Build a new reviewed source-bound controller that preserves the old PID while proving the original role's finance mutation path is denied; do not simply exempt an untested public service.
- Every external fence must have exact owner, source, configuration, PID and timed negative writer admission proof, plus a tested rollback path and a bounded expiry. Do not grant capability by a boolean self-assertion alone.
- Confirm no in-flight or UNKNOWN signing or database transactions, and preserve journal identities. Fence all ingress and newly activated jobs, not just running process PIDs. Run repeated systemd inventory and fresh PostgreSQL denied-write probes in the exact runtime role before concluding quiescence.

### C06 — One coordinated encrypted recovery capture

- Require an admitted, still-current C03-A temporary global finance fence and verified offhost receiver reachable by **host-key authenticated transport**.
- Capture mutually consistent HD and DE PostgreSQL state, settlement journals, native chain context, authority and recovery manifests (NO plaintext private keys in user chats), source SHAs and WAL evidence. Use a signed bounded phase/window and protected filesystem destinations.
- Record exact file hashes, identities, row counts and journal states before and after. Offhost ciphertext receipt and separately tested decryption must match the source manifest. A non-quiesced old rehearsal or a locally staged tarball does NOT pass.
- On failure, retain explicit INCOMPLETE and all prior good recovery points. Never consume or overwrite them as a convenience.

### C07 — Isolated proof of the exact C06 capture

- Restore **the same** newly accepted C06 ciphertext into a separate no-network/loopback-only environment, never over live HD/DE. Compare all finance table counts and key claim states, source hash, native journals, required authority metadata, and rollback readiness.
- A successful old Intel PostgreSQL16 restoration is a mechanics rehearsal only. Test a negative/corrupt or incomplete restore and confirm it returns HOLD with no live writes.

### C03-B — Permanent permission-domain migration (only after C06/C07)

- Rehearse on the verified C07 restore: dedicated NOLOGIN database/schema/finance-table owners, then remove ownership and CREATE privileges from the HD/DE legacy runtime roles. Include the **23 HD / 10 DE sequences**, 12 HD external triggers and their functions, seven postgres-owned dependent views, and all other finance-related objects discovered from references, grants and code paths. Preserve the 323 HD / 82 DE unrelated legacy-owned relations unless explicitly reviewed.
- Do not rely on REVOKE against a relation owner or on role flags alone. Verify no privilege regain via role membership, SET ROLE, schema ownership, new object creation, SECURITY DEFINER, triggers, default privileges, reconnect or elevated service account.
- Prove with real restricted runtime roles: INSERT/UPDATE/DELETE/TRUNCATE and DDL against each finance table/sequence fail; sanctioned SELECT and public Steam authentication pass; unrelated HD/DE nonfinance behavior passes. Verify 3032 and 3030 rollback health and available recovery.
- Capture a complete reversible SQL/membership ownership map and test the rollback **on the same isolated restore** before approving a separately source-bound live migration. Do not auto-run any generated SQL on production.

## Self-healing behavior and formal acceptance

A protocol-level observer should detect drift automatically and emit a protected, source-bound HOLD reason; suspend *new Satchel admission* on unexplained writer permission, new unit or backup hash drift, while preserving legacy operating services. It may retry only idempotent read-only observations and bounded nonfinancial transport with strong identity. It must not auto-rebroadcast uncertain money, self-sign an owner's funded permit or silently mutate another application's roles.

Formal C03 acceptance requires **physical denial** of all unauthorized finance write paths, not just source merge. Formal C06 acceptance requires an actual coordinated, encrypted, validated offhost snapshot. Formal C07 acceptance requires restored equality of that exact snapshot plus recovery proof. All three are OPEN until independently recorded in the canonical WoloChain #5 register.
