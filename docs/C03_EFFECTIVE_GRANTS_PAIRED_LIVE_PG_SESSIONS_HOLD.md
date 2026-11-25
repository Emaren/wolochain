---
id: "aoe2war.wolochain.c03-effective-grants-paired-live-pg-sessions-hold"
title: "C03 effective grants with paired live PostgreSQL sessions HOLD"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war", "aoe2dewarwagers"]
audience: ["developers", "operators", "ai-agents"]
source_of_truth: "git"
authority: "source-only-read-only-c03-dual-evidence-bound-observer-never-a-finance-permit"
reviewed_at: "2026-11-08"
review_interval_days: 7
sensitivity: "restricted"
---

# C03 effective grants with paired live PostgreSQL sessions HOLD

## Why this exists

C03 cannot be accepted by merely denying *new logins*: PostgreSQL backends
already connected as their table-owning legacy roles retain effective access.
It also cannot be accepted by showing only a list of running services without
checking each connected role's actual table/column capabilities.

Two separate merged read-only observers already exist:

- `settlement_c03_pg_effective_grants_hold.py` SHA256
  `4adbd53c7d324798f0b5f60822b5280438506bce6a32ac86c494f659bf138f48`
  checks HD/DE table and inherited column-level DML capability for four
  reviewed runtime/auth roles.
- `settlement_c03_existing_pg_client_origin_hold.py` SHA256
  `2202bf86402b825effd6ef54fccc59794347ba59d72957eaa2844380cff1008a`
  resolves live PG client sockets through OS process start identity to their
  original protected systemd units; it fails closed if the client population
  changes while it inspects.

The **paired classifier**
`scripts/settlement_c03_effective_grants_bound_sessions_hold.py`
requires exact private SHA256 digests for both raw root-owned 0600 JSON
files, rejects symlinks/hardlinks, checks both observations were collected
no more than 120 seconds apart and are at most 300 seconds old, checks
all approved HD/DE role and service origin identities and makes sure
the restricted R25 role still has **zero public table write permissions**.

It deliberately returns **exit 3 HOLD or exit 2 STOP**, *never PASS*.
It emits only aggregate per-service client counts and per-database public
write-capable table counts. It omits all user IDs, PostgreSQL backend PIDs,
OS PIDs, wallet addresses, customer data, SQL secrets and session
credentials. The raw source evidence remains private off GitHub.

## Physical findings at initial enrollment

On Nov 8, separate earlier HEL1 read-only audits proved:

- HD legacy `aoe2hd_user` can write all 190 HD public tables; DE
  legacy `aoe2de_user` can write all 52 DE public tables.
- Restricted R25 `aoe2war_web_prod` can write **zero** public tables.
- Steam `aoe2war_auth_owner` retains its narrow separate approved
  single-table authentication write scope in HD.
- Of 25 existing PostgreSQL clients in one snapshot, 9 used the
  HD owner role from 3030 rollback, 3 from the HD API, 3 the DE
  owner role from DE API, and 10 used the restricted R25 role.

Those two previously collected observations had **different capture times**.
They **cannot** be combined to claim a fresh paired result. The new
classifier requires fresh independent full reruns of both reviewed
observers before a root-private paired physical receipt can be issued.

## Mandatory operations / negative guarantees

Only run the new classifier with explicit absolute paths and SHA256s for
source-owned private results. Do not copy raw JSON to GitHub; share only
protected receipt hashes and aggregate HOLD counts.

Even if every legacy owner's write-capable table count later becomes
zero, the paired classifier remains HOLD: it has **not** established
negative DML from preconnected sessions, independently verified RPC/REST/
CLI egress denial, background cron/container/external writer exclusion,
Steam-safe rollback, C06 coherent encrypted backup, C07 same-state restore,
C04/C05 financial finality/solvency, C08 ratified governance, or C09 fresh
owner-signed exact transaction authority.

This is source-only, non-authorizing evidence. It must never change
PostgreSQL role memberships, table ownership, services, active
connections, wallet keys or payments. C01-C09 remain HARD HOLD.

## First production read-only execution

The two original merged observers and the new paired observer were
executed consecutively on HEL1, all returning their intended exit-3
financial HOLD. The paired observation status was
`HOLD_C03_LIVE_OWNER_SESSIONS_RETAIN_EFFECTIVE_WRITE_CAPABILITY`.

One time-of-check captured **seven legacy owner-role connections**
(one 3030 rollback, three HD API and three DE API) and **five restricted
R25 connections**. There were still effective legacy write permissions
on all **190 HD** and **52 DE** public tables. Connection counts are
dynamic and must never be reused as stable evidence.

The new private root0600 paired receipt SHA256 is
`9969a7e646cfb8e3d2afdc2d4391e69b9015b9c849ec85f47e7ccbf4ff270da0`.
The underlying independent grants and session source receipt SHA256s are
`fcbfd052319e0dcdb1e0ddaa20be1755bec3197ce10328ebdccebfe3bf6713d8`
and
`14eafdb7201208434d8ee6f643939ea755d45710748d96fbfd364d3a980711a9`
respectively. These are historical HOLD observations, not a current
release permit. No financial role, service or WOLO was changed.
