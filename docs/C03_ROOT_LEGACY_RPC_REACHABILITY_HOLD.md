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

## 2026-11-08 additional live confinement evidence (source v2)

Separate root-local systemctl show inspections show that BOTH legacy
root settlement units at 8092 and 8093 have NoNewPrivileges=no,
ProtectSystem=no, PrivateTmp=no, no configured privilege-drop user,
and default broad Linux capability bounding sets that include
cap_sys_admin and cap_dac_override. The consensus validator also
runs as root but has NoNewPrivileges=yes, ProtectSystem=full,
PrivateTmp=yes and explicit writable paths.

The revised v2 source-bound observer captures these confinement
properties as booleans, not private unit environment variables, and
never promotes them to financial PASS. This is permission-exposure
evidence, not proof of malicious operation. Merely adding a unit
drop-in while a process is running does NOT confine that process;
changing running root financial producers requires a separate
guarded stop/restart and rollback, gated on coherent backup/recovery
and full upstream sign-off. No such live change was made.

## Source v2 exact proof and provenance

The revised HEL1 physical observer source SHA256 is
c67ef049b9d515ee273a2d3691059bf889789537a6bcd1cc0c418a802ac8762a.
The v2 source returned expected exit 3/HOLD on the actual HEL1 and
proved both named legacy services lack NoNewPrivileges, ProtectSystem
and PrivateTmp, while the consensus validator has all three enabled.
The resulting private root0600 physical source-and-evidence receipt
SHA256 is
b07f51c0d34dc00ce9dffd96ff9bd9799c0f2f65b7ede1c92bf5c53d106cff9e
at /root/aoe2war-session-a-c03-unit-confinement-v2-20261108/physical-v2-confinement-hold-20261108.json.

All 21 new unit-confinement/transport-focused adversarial tests pass
locally. These measurements are a capability inventory and admission
gap, not a complete writer isolation, not an independent chain bank
or custody proof, and not a financial permit. No unit mutation.
