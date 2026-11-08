---
id: "aoe2war.wolochain.c03-root-legacy-rpc-reachability-hold"
title: "C03 root legacy settlement and RPC transport admission gap"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war", "aoe2dewarwagers"]
audience: ["developers", "operators", "ai-agents"]
source_of_truth: "git"
authority: "source-only-physical-transport-audit-no-financial-fence"
reviewed_at: "2026-11-08"
review_interval_days: 7
sensitivity: "restricted"
---

# C03 root legacy settlement and RPC transport admission gap

## Actual HEL1 physical finding

On 2026-11-08 at about 01:00 UTC, the native loopback
financial listeners were mapped with exact process identity:

| Endpoint | systemd owner | PID at observation | UID |
| --- | --- | --- | --- |
| 127.0.0.1:8092 | wolochain-mainnet-settlement.service | 1012 | root (0) |
| 127.0.0.1:8093 | wolochain-founder-rewards-settlement.service | 1010 | root (0) |
| 127.0.0.1:1318 | wolochaind-mainnet.service | 1009 | root (0) |
| 127.0.0.1:27657 | wolochaind-mainnet.service | 1009 | root (0) |

Public R25 web PID 2206791 runs under restricted UID990; original
preserved 3030 rollback PID2625090 runs under UID1000.

A kernel nftables OUTPUT rule denies UID1000 TCP to localhost
8092/8093, but not UID0. Native real TCP connect-only tests,
**sending zero application bytes**, proved:

| Listener | UID0 | UID1000 |
| --- | --- | --- |
| 8092 | reachable | denied |
| 8093 | reachable | denied |
| 1318 | reachable | reachable |
| 27657 | reachable | reachable |

This is **transport reachability**, not proof that an unsigned arbitrary
transaction could debit an account, and not evidence of a breach.
However it refutes any claim that the UID1000 8092/8093 firewall
rule is a complete financial writer fence. The original root-owned
settlement producers and the local REST/RPC ingress paths are
still uncontained by that rule.

A root-only physical transport receipt SHA256 is
3feaa919f8ccd999cfb01a4484d027d729e1f4e9640f2bd50dbda663d0b2ffb1,
stored privately at
/root/aoe2war-session-a-c03-current-20261108/root-finance-transport-physical-hold-20261108.json.
No customer records, keys or network payloads are in the receipt.

## Source and engineering control

The fail-closed read-only script
scripts/settlement_c03_root_finance_transport_hold.py binds itself
to HEL1 root, the reviewed exact service-unit names, each live main
PID/UID, the loopback listener inventory and UID0/UID1000 TCP
connection matrix. Unexpected binds or active funded 8094/8095
ports STOP, not PASS. The observed legacy risk returns
HOLD_C03_ROOT_AND_DIRECT_RPC_FINANCE_WRITERS_UNCONTAINED
with exit code 3. No source path can authorize payments.

This witness does NOT inspect Postgres ownership of all tables,
classify 161 unreviewed public tables, stop services, revoke already
connected DB sessions, revoke signer credentials, establish a
quiescent backup or certify chain finality. Separate C03/C06/C07
evidence remains mandatory.

## Safe closure dependency

The owner controller must review and prove complete financial writer
and producer isolation, including root-owned legacy services,
REST1318/RPC27657/CLI and signer paths, existing HD/DE PostgreSQL
backends, database ownership and privileged function/trigger routes.
Maintain live public R25, preserved original 3030 rollback and
consensus-read functionality; any actual maintenance cutover requires
coordinated C06 protected coherent backup, independently restored
C07 and automatic rollback.

Do NOT simply block the entire RPC port without checking the public
website's legitimate read dependencies. Do NOT conclude that moving
a role to NOLOGIN disconnects authenticated PostgreSQL sessions.
Do NOT transfer WOLO, run a payout or label a software-only
transport check as independent bank or custody proof.

All financial C01-C09 acceptance gates remain HARD HOLD.
