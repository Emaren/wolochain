---
id: "aoe2war.wolochain.c03-auth-definer-exact-body-reachability-hold"
title: "C03 exact Steam auth-definer body and ownership capability — HOLD"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war", "aoe2dewarwagers"]
audience: ["developers", "operators", "ai-agents"]
source_of_truth: "git"
authority: "source-only-c03-catalog-audit-not-financial-release"
reviewed_at: "2026-11-08"
review_interval_days: 7
sensitivity: "restricted"
---

# C03 exact Steam auth-definer body and ownership capability — HOLD

## Source and trust scope

The restricted R25 website uses three narrowly scoped
PostgreSQL SECURITY DEFINER functions for Steam authentication.
Their owners, SQL body digests, execution permissions, search path,
auth-owner writable relations and columns, delete/truncate scope,
trigger inventory, role escalation and schema CREATE rights must
remain independently reviewable during a financial owner migration.

The source-only observer
scripts/settlement_c03_auth_definer_reachability_hold.py (SHA256
193572f6fed5b21417cc53d3904cdbb44b858f276e32e94b32e7911b09e3d712)
is byte-identical to the original reviewed C03 source on PR #195,
but is separately reviewed here against the clean held financial
baseline after source-only PR #200. Fourteen focused local tests
pass. Exact-head GitHub CI is independently required.

This observer performs PostgreSQL catalog SELECT in a
REPEATABLE READ READ ONLY transaction and returns HOLD when its
exact defined scope matches. It stops on an unexpected function
body, owner, search path, function inventory, writable relation,
writable public.users column, trigger, role membership or grant.

No permission migration, new application login, firewall
change, existing session termination, or financial payment is
performed or authorized. The existing three authenticating
definers do not attest all other financial writers or any Wolo
REST/RPC, signer, custody or legacy-owner paths.

## Explicit outstanding C03 blockers

The original 3030 rollback runs under a legacy HD owner-writable
identity. Both legacy HD/DE roles remain finance-writable on their
respective public schemas; existing PostgreSQL backends cannot be
made safe by a NOLOGIN toggle. The global C03 writer quarantine
must preserve website/Steam availability while proving actual
negative financial DML against every existing connection, restart
and reconnect path, including signer/CLI/REST/RPC and unscoped
unit/cron/container writers. C06 coherent offhost backup and C07
same-capture isolated restore remain separate subsequent gates.

The original mixed C03 source+October 24 documentation PR #195
has five externally unresolved GitGuardian findings and is NOT
automatically waived or approved by this source-only restack.
No scanner rule or integrity digest is weakened here.
Formal C03, C01–C09 and funded WOLO remain HARD HOLD.
