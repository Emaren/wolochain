---
id: "aoe2war.wolochain.satchel-controlled-release"
title: "War Satchel Controlled Release Gates"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "git"
authority: "source-integration-proof-not-production-approval"
reviewed_at: "2026-10-17"
review_interval_days: 14
sensitivity: "restricted"
---

# War Satchel Controlled Release Gates

The authenticated bridge source builds on PR #28 at
`9f59b6472163e226e98a0a94d6a0136b0dc02d96`. Its
[financial interface](war-satchel-financial-bridge.md) and
[exact executable artifact](war-satchel-exact-source-artifact.md) are source
contracts. Neither authorizes deployment, custody, a ledger posting or a canary.
HD #638 remains held at `c4fd91e548042807fb02c000f7360e87efa4801d`, including
`SATCHEL_FINANCIAL_BRIDGE_READY=false`. Do not remove that lock on the strength
of these tests or an HTTP `consensus_authenticated` field.

## Fresh read-only production observation

The [machine-readable receipt](settlement-contracts/satchel-live-readonly-20261017.json)
records the observations below. At 2026-10-17 20:57 UTC, existing SSH access
was used only for bounded reads:
systemd MainPID/health, `/proc/PID/exe` hashes and Go metadata, and bounded
aggregate request/run JSON inspection. No environment, keyring or secret file
was read. No candidate binary was installed or executed on the VPS. Each
executable's inode/size/mtime and MainPID were checked before/after inspection.

| Service | PID | Executable | Actual embedded source |
| --- | --- | --- | --- |
| Legacy 8092 | 1012 | `/usr/local/bin/wolochaind-mainnet` | `78c25985420ee41a6678c42fab8ea8d6c3b1b519`, modified=false |
| Founder 8093 | 1010 | same settlement executable | same clean source |
| Consensus, observe only | 1009 | `/usr/local/bin/wolochaind-mainnet-node-prewartrophy` | `d3bd62414a047a492a3814b7d3baa2717d64db2e`, modified=true |

Both actual settlement executables hash to
`040126a2884946caf1651a50b7d8115c5a6fb2d5aa94fcbbe150694602d451a5`.
The separate historical consensus executable hashes to
`4b77f622191db7550cb87cafb8f1886a0aadebee3eb6565f9f90036f809e61d3`.
8092/8093 reported healthy literal-loopback `wolo-1`; 8094 had no listener.
Payout address fingerprints differ (`d22311cf4725e370` versus
`84f8e23234b72262`), while both health reports identify the existing betting
escrow fingerprint `5712f9536e3e5c94`. That escrow is excluded from Satchel
vault custody. Fingerprints are observations, not proof of independent key
control or permission to transfer funds.

Health reported balances in uwolo: 8092 payout `397509250000`, founder payout
`356787241424`, shared escrow `826173750000`. These unauthenticated service
observations are **not** complete reserve provenance or solvency. A separately
attempted local REST balance query was unavailable; no independently proven
bank/liability reconciliation was obtained.

At 20:59 UTC, 8092 had 910 request records (904 confirmed, five failed, one
accepted) and 784 run records (780 confirmed, three failed, one accepted).
The accepted request records `100000000` uwolo. Request and run records may
refer to the same obligation; they must not be added as separate liabilities.
8093 had 646 requests (609 confirmed, 37 failed), with no run directory.
Both observed lock directories were empty. This is a nonexclusive observation,
not an ingress fence, stable snapshot, proof of no in-flight writers, or a
complete liability inventory. **Never retry an accepted/uncertain record.**
Founder claim #889 was not individually investigated or replayed; its separate
financial hold remains unchanged.

## Dependency order for operator execution

1. Independently review the final source and exact CI receipts. Download the
   composed `wolosatcheld` archive plus its separately anchored GitHub receipt;
   authenticate archive and manifest digests, then run the shared offline
   verifier with `--profile composed-satcheld` and the exact CI identity. The
   legacy `526d5eb6` artifact is a separate `wolochaind` candidate.
2. HD must consume the portable proof through a pinned offline verifier using
   its own operator-provisioned anchor and stored intent, verify signed v2
   allocations and owner withdrawal mandates, and atomically consume both
   physical transaction identity and obligation under its ledger fence. Keep
   the activation hold until that implementation and adverse tests are reviewed.
3. Obtain current reserve/liability and independent vault-control evidence.
   Provision the distinct 8094 OS account, keyring, approval boundary, private
   token, journal, network sources and independently authenticated checkpoint
   and witness through the operator's separate governed process. Never derive
   a trust checkpoint from a proof response or reuse 8092/8093/consensus keys.
4. HD owner must rehearse the **exact seven** pending migrations against a
   fresh production-schema-only shadow and obtain narrow reviewed authorization
   for the immutable guard correction. The earlier `118/112/6/2` frontier
   predates the 119th source file and cannot authorize this funded ledger.
   No generic `CREATE OR REPLACE FUNCTION` bypass or ad hoc SQL is permitted.
5. Before any legacy replacement, fence HD and DE ingress and all alternate
   financial writers. Reconcile accepted/unknown requests and complete
   liabilities without rebroadcast. Prove exclusive current state ownership,
   checksummed current snapshots and an approved state-preserving paired
   rollback/recovery procedure. Keep #889 held. Consensus PID/executable remains
   unchanged throughout; retired rescue/rollback scripts stay retired.
6. With named operator approval, execute only the separately reviewed protected
   settlement cutover and schema installation. Provision the isolated signer
   at a versioned path from the verified composed artifact. No installation,
   key creation, service restart or financial activation command is authorized
   or supplied while the preceding evidence is missing.
7. A separately approved small canary must prove exact running binaries,
   authenticated deposit, owner/cap/revocation behavior, no double reservation,
   settlement, full unmatched principal refund, partial matched allocation,
   owner withdrawal and restart/UNKNOWN recovery. Freeze producers on any
   mismatch; retain holds and current journals for read-only reconciliation.
   Recovery must preserve the latest financial history, never restore an older
   journal or manufacture success by retrying an ambiguous payment.

## Flow status at this source milestone

| Flow | Production status | Actual remaining prerequisite |
| --- | --- | --- |
| Deposit | BLOCKED | HD proof consumer and atomic global receipt claim, independent vault/reserve/trust provisioning, protected ledger installation |
| Signed auto-bet authorization | BLOCKED | deployed owner/ADR-36/revocation/Watcher proof; current 1,000 WOLO per-bet and 10,000 daily source bounds retained |
| Automatic betting | BLOCKED | dedicated signer runtime plus HD reservation/concurrency/mandate integration and canary |
| Settlement | BLOCKED | exact-source legacy cutover, authoritative match allocation review and complete liabilities/drain |
| Refund | BLOCKED | HD signed v2 allocation + authenticated proof consumption; full unmatched principal remains mandatory |
| Withdrawal | BLOCKED | HD owner-mandate/independent approval worker, durable reservation proof and authenticated finalize/recovery consumer |

No end-to-end production financial canary or new production deployment is
claimed. C2 remains `UNAVAILABLE`; all portable proof receipts are
`NONCREDITING`. Source CI and reproducible artifacts cannot clear these gates.
