# C07 real HD/DE owner and ACL recovery: physical rehearsal and reusable comparator

**Scope:** C07 recovery preparation only, zero new funded release authority.

## Physically exercised on Nov 9, 2026

On separate APFS copy-on-write Intel PostgreSQL 16.15 clones of the stopped genuine C07 HD and DE restores, imported authentic HEL1 global roles via streamed pg_dumpall --globals-only --no-role-passwords. This reconstructed 24 production roles and 3 memberships, excluding password verifiers. Replayed 459 real HD and 104 DE catalog ownership statements, including database and schema owners. These changes affected only disposable Unix-socket-only Intel restored clusters.

The original C07 data restoration had lost original PostgreSQL global-role identities and grants. On HD, extracted and replayed the **351 genuine GRANT/REVOKE statements** from live HEL1 pg_dump --schema-only; DE had zero explicit ACL statements. This repaired mismatched effective Steam, rollback and public view permissions in the isolated restored HD.

Verified all 401 HD application relations, 42 functions and 15 schemas; and 102 DE relations, zero functions and one schema. Four independent full-output comparisons of HD/DE **owners and effective grants** matched live HEL1 exactly for the five critical database, web and auth roles. Restricted Steam read_user worked under a genuine simulated session_user identity; directly updating the user wallet column was denied. Both Intel copies were stopped afterward; original C07 recovery source receipts were unchanged.

Physical private Intel receipt SHA-256:
cd1c2d24739534f14b6ce7e452b9a0e2ec9287bf9a5b0dc8f3dc49186179db6a

Exact executed private M1 SSH orchestrator SHA-256:
682ccc86a5e1d3c354c2715d3ef11bf51892c38179bd6d4038285b21a95d385f

Original C07 HD receipt:
7a8d495b4259c5316f0f38ff060667d6b81f1243f77e1656daf2765da3603305

Original C07 DE receipt:
df21fa2e67319e606a530af501c5b108831178c27fb98c79b31e02bb166a5bb7

The exact private SSH orchestrator was not published because it embeds host-routing details. The byte-identical **physically executed catalog SQL, owner DDL generators and ACL parser** are preserved under scripts/ with SHA-pinned tests.

## Portable read-only C07 verification

The new script scripts/settlement_c07_compare_recovered_role_grants_v1.py has no network and executes no SQL. It accepts separate private live and restored input directories containing four catalog files each:

- hd.owner.txt and de.owner.txt: output from scripts/settlement_c07_real_owner_parity_live_and_restore.sql
- hd.effective.txt and de.effective.txt: output from scripts/settlement_c07_real_effective_acl_parity_live_and_restore.sql

These are **read-only SQL queries**. The HD and DE source owner-map generator SQL also queries catalog metadata only, but emits DDL text for separately authorized import **solely inside isolated restoration**, never against production.

Both input directories must be distinct mode0700, with mode0600 non-symlinked source files. Call the comparator from a trusted machine with an unused receipt destination:

    python3 scripts/settlement_c07_compare_recovered_role_grants_v1.py --live-dir /private/live-readonly-catalog --restored-dir /private/isolated-restored-catalog --out /private/c07-role-acl-receipt.json

A match produces a new exclusive mode0600 receipt and a **nonfunded rehearsal pass**. Scope drift, bad mode, symlink, missing role, grant mismatch and overwriting a receipt all fail closed. Even if a future C06 receipt SHA is attached, the comparator always marks C06/C07 formally OPEN.

## Formal gate prerequisites still HOLD

A finance-only production writer freeze is needed, coordinated with Session B's authenticated finance-safe website rollback. C06 must capture the same consistent financial checkpoint across HD+DE, global roles including secure password-verifier treatment, exact Wolo ledger, journals, nonce/permit and WAL, plus all large replay tables. Only C07 restoration of that **same C06 package**, genuine negative replay tests and new owner source-bound acceptance can close C07.

No production financial services were started or modified by this rehearsal; no historical payout was released. C04+C08 remain closed; C01/C02/C03/C05/C06/C07/C09 remain formally OPEN.
