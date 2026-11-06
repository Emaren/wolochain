---
id: "aoe2war.wolochain.c03-nologin-existing-backend-counterexample"
title: "C03 NOLOGIN Existing Backend Counterexample"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["developers", "operators", "ai-agents"]
source_of_truth: "git"
authority: "source-only-isolated-nologin-counterexample-not-live-financial-fence"
reviewed_at: "2026-11-06"
review_interval_days: 7
sensitivity: "restricted"
---

# C03 NOLOGIN Existing Backend Counterexample

## The risk exposed

**PostgreSQL `ALTER ROLE legacy NOLOGIN` denies new logins, but it does NOT revoke already-authenticated sessions or their financial table owner privileges.** A legacy in-flight connection can complete an INSERT after the role loses LOGIN. Combining NOLOGIN with global quiescence requires exact identity-bound session drain/termination, activation denial, retry/queue fencing, settlement journal/signing containment and proof that financial writers do not reconnect or resume. These observations do not authorize a live grant change.

## Verified disposable PostgreSQL14 physical experiment

`scripts/settlement_c03_nologin_existing_backend_rehearsal.py` creates a fresh local-only Unix-socket private PostgreSQL14 cluster on the nonroot M1 Mac. No HEL1, real HD/DE tables, credentials, network listener or WOLO transfer is accessed. It creates two **synthetic** LOGIN identities: a legacy writer and an independent public reader. The original legacy connection begins `pg_sleep`, and root-local synthetic administration sets legacy `NOLOGIN` while that connection is alive.

**Five exact assertions PASSED:**

- The changed legacy role cannot establish any new login.
- The already-connected legacy session still successfully writes after NOLOGIN.
- The independent public role still reads successfully during the freeze.
- After a fresh legacy session begins a delayed INSERT, the test identifies **exactly one target backend PID**, verifies the PID identity, and issues one scalar `SELECT pg_terminate_backend(<verified_pid>)`. Its delayed write does NOT commit.
- Restoring `LOGIN` to the fake role restores a normal write.

Original physical receipt SHA256 `bbe8470b4116a4156398e118bdbe999baa14dc1ead7198f11d3db8318cadea54`; the exact source-bound replay produced the same deterministic five-assertion result. **Eight focused hermetic source tests**, all PASS, rejecting missing/extra/false/integer proof values, non-Mac/root execution, nonexistent scratch path, unsafe ambiguous termination, and production host references. The ephemeral PG postmaster, socket and temporary data are stopped and destroyed after the test.

An earlier exploratory fixture failed and was retained: it used `SELECT count(*) FROM pg_stat_activity WHERE ... AND pg_terminate_backend(pid)` to target a legacy connection. The SQL optimizer is not required to evaluate that conjunction in order; the test connection closed unexpectedly. Corrected test first obtains the **unique target PID** using a read-only catalog query, then invokes `pg_terminate_backend` only with the bounded, verified integer PID. The corrected fixture passed five real assertions. **Never use an aggregate WHERE expression containing `pg_terminate_backend` as a safe targeted termination mechanism.**

## Impact on actual production

At the 2026-11-06 21:xx UTC read-only HEL1 census, seven legacy HD connections, three public R25 database connections, and two legacy DE connections existed. HD legacy owned 24/24 identified financial tables and 23/23 attached sequences with full DML/update privileges; DE legacy owned 10/10 tables and 10/10 sequences. The public R25 web role showed 0/24 and 0/10 finance-table writes. The 18-unit historical maintenance controller does not cover the entire live writer/activator universe and must NOT run.

A genuine C03 admission must enumerate all sessions by exact role/database PID and application identity, halt each relevant producer admission surface, protect legitimate public Steam/rollback routes, verify no active transactions, then apply the reviewed fence and explicitly prove no queued or resumed writer. The finance DB owners are still implicit grant holders; a simple REVOKE or NOLOGIN without completed session quiescence is insufficient.

Before any permanent financial owner migration, produce a **new coordinated encrypted offhost C06 backup** and **restore precisely the same artifact in isolated C07**. The synthetic NOLOGIN test does not close C03, C06, C07 or grant C09 financial authority. Preserve old 3030 rollback, public 3032, validator, legacy settlement, custody keyrings and inactive 8094/8095.

## Safe replay

On the Mac M1 only, with Homebrew PostgreSQL14 at `/opt/homebrew/bin` and an existing `~/.cache/aoe2war` scratch directory, run:

```bash
python3 -B -m unittest discover -s tests -p 'test_settlement_c03_nologin_existing_backend_rehearsal.py' -v
python3 -B scripts/settlement_c03_nologin_existing_backend_rehearsal.py
```

**Never deploy this synthetic test as a real financial-fence controller.**
