---
id: "aoe2war.wolochain.war-satchel-custody-c2"
title: "War Satchel C2 Custody Capability"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "git"
authority: "source-only-war-satchel-custody-capability"
reviewed_at: "2026-10-30"
review_interval_days: 14
sensitivity: "restricted"
---


## Source review — October 30, 2026 UTC

The dormant C2 capability described below remains unavailable. Later runtime
execution qualification is separately documented in
[mainnet execution](war-satchel-mainnet-execution.md); neither that opaque
capability nor the new reviewer fee census certifies custody from a public
address or configuration flag. The census retains every unresolved fee and
requires separately signed complete historical coverage. The October 29 21:07
UTC read-only receipt showed no 8094/8095 listener. This renewal establishes no
new vault, key possession, recovery receipt or production financial admission;
all older custody observations retain their dates. Recovery remains owned by
its separate session; this source work performs no recovery/provider setup.

# War Satchel C2 Custody Capability

## Independent source contract review — 2026-10-30 UTC

Session B checked held-source
[`custody_authority.go`](https://github.com/Emaren/wolochain/blob/9c11a617ba1362fbdee1a9ef5903a1efad0e6db1/internal/satchelservice/custody_authority.go)
(blob `ba3e0a590bfb4daeece50072bdfbd496667fd02b`) and
[`reserve_review.go`](https://github.com/Emaren/wolochain/blob/9c11a617ba1362fbdee1a9ef5903a1efad0e6db1/internal/satchelservice/reserve_review.go)
(blob `a7157090a6352d64dc4c3f49678fc589470fff92`).
Those contracts require retained native custody authority and independent
reserve-review evidence; even a `QualifiedReserveReview` exposes
`CustodyCapability() == "UNAVAILABLE"`. The separate
[2026-10-29 21:07 UTC physical receipt](https://github.com/Emaren/wolochain/pull/115#issuecomment-6508382058)
reports **no live 8094/8095 listener**. No dedicated keyring ownership, signed
permit, off-host nonce, bank reserve/fee census or restore was re-attested in
this review. C2 remains **UNAVAILABLE**. Reviewing source conditions does not
install or qualify custody or authorize real Satchel credit.

**C2 remains unavailable. No independently verified dedicated Satchel vault or
signer has been established. No real WOLO deposit can be accepted under this
source foundation.** This document specifies source behavior and outstanding
evidence; it is not a deployment, custody, solvency, or transfer certification.

## Product and source authority

[App issue #559](https://github.com/Emaren/app-prodn/issues/559) requires the
owner-bound Keplr funding intent, independently verified vault and signer, exact
finalized receipt, globally unique credit, complete liabilities, withdrawals,
accepted funded tickets, and protected canary as separate gates. Its C2 permits
an independently proved shared partition, but this bounded implementation does
not implement or certify one. Existing betting collateral is unavailable for
Satchel funding.

[App issue #514](https://github.com/Emaren/app-prodn/issues/514) requires chain
accounting, owner consent and revocation, at most 1,000 WOLO combined per canonical
game, one accepted funded ticket, complete unmatched refunds without a fee,
withdrawals, and independent app/chain release evidence. An off-chain ownership
signature is not spending authority. Preview observations are not funded wagers.

The [latest October 15 #559 source-policy comment](https://github.com/Emaren/app-prodn/issues/559#issuecomment-6204608778)
identifies [app PR #599](https://github.com/Emaren/app-prodn/pull/599),
head `8b9876ee4f1cf0b8c15bb1256d4d542fa7d53995` (now merged), as candidate vault
exclusion only: every registered mainnet role and configured custody/treasury
alias must be excluded. It does not establish signer control or solvency. This
WoloChain change does not modify either app repository or grant its environment
variables certification authority.

This branch starts from refreshed `origin/wolo-1-mainnet-prep` at
`39a538a624f664466c05d5dcef9d40208123a6f8`. The separately refreshed default
`origin/main` remains `a2fba6bfd98d7b28fb113badbadf23ec9096a4af`.
No branch reconciliation or production promotion is implied.

## Existing custody and dated evidence

These are existing roles, not Satchel deposit destinations. The authoritative
[wallet map](mainnet-wallets.md#current-mainnet-address-labels) and
[settlement runbook](mainnet-settlement-runbook.md#live-shape) retain their
separate observation dates.

| Existing role | Address / authority | Evidence boundary |
| --- | --- | --- |
| 8092 payout, `mainnet-payout` | `wolo1zfa9ssu2gpgqg7yzvhmjt4w66mza07qr2a4rwu` | September 21–22 successful payout-role execution; refreshed by filtered live health at `2026-10-16T00:16:29Z`. |
| Shared 8092/8093 escrow, `mainnet-escrow` | `wolo1zygwt232ymc4h2g52yvkntffhmd5alx2kglw7p` | Both live health responses identify this same escrow; existing betting/settlement obligations. |
| Community Treasury | `wolo1hlfvzuv4dc46ngvh3zlteuegx0xga20hj20zd2` | Both settlement configs confirmed at `2026-10-16T00:18:39Z`; HD web config also agrees. No free-reserve claim. |
| Current staking custody and operating reserve | `wolo18v9ugfdrnz2ll2ah5z2yqzm5kzlg3e7l7jy6rn` | HD web config at `2026-10-16T00:21:33Z`: key selector `staking-mainnet`; derivation/access not independently certified. |
| App Faucet Hot Wallet | `wolo1dshyzxffd0jj39k7gj9tq9hgsx96ylxamyp5g0` | June 4 approved settlement seed source; separate app keyring. |
| 8093 Founder Rewards payout, `founder-rewards-mainnet` | `wolo1tg04m57e52evgzjkn9ruwwkz626pfv9qfv27wy` | Filtered live `wolo-1` health at `2026-10-16T00:16:29Z`; separate payout, but shares the existing escrow above. |
| Retired staking | `wolo1rmr39nd5gnnv5y5f66qtq367xfwvx9jt5w7ucr` | Historical; do not fund or reuse. |
| Legacy betting escrow | `wolo1t4jq7wd4x030t9f0yfqfq74pt4pmaep5nu67y4` | Historical; no current mainnet settlement signer configured. |
| Retired payout | `wolo1cy04t5af0mr9d8n6rrzgr8e9j4vuf42nfg02q5` | Historical; excluded from new custody. |

The refreshed observation occurred October 15 in the operator's
America/Edmonton timezone (October 16 UTC). It read only allowlisted health
fields over SSH, without signer/key access or mutation. It establishes the
reported chain and configured signer roles; it does not prove key possession,
complete liabilities, reserve availability or an independent Satchel signer.
Distinct root-private environment/state for the two services, observed October
14, does not remove their shared escrow authority.

Exclusion is broader than this summary. It includes every registered mainnet
role in the wallet map: founder cold/operating, community treasury, DEX reserve,
faucet growth/hot/test, validator operations/reserve, ecosystem bounties,
IBC/module escrow, relayer, staking, betting payout/escrow, and retired roles.
Reconcile the complete current chain and app catalogs rather than inferring
available funds from an unlabelled address.

The September 9 payout reserve policy was 250,000 WOLO plus 10 WOLO fee
headroom; betting escrow was 100 WOLO plus 10 WOLO headroom. The then-observed
417,051.500000 / 1,913,217.500000 WOLO balances are historical measurements.
Neither balances above these floors nor total chain supply proves unencumbered
Satchel reserves. Staking liabilities and reserve classification remain
app-owned; standard bank memos do not create a consensus partition.

### Source is distinct from deployed executables

The newer [October 14 runtime provenance](mainnet-settlement-runbook.md#settlement-only-verifier-candidate--source-controlled-proof-lane-october-14-2026)
records both settlement services running clean source
`78c25985420ee41a6678c42fab8ea8d6c3b1b519`, executable SHA-256
`040126a2884946caf1651a50b7d8115c5a6fb2d5aa94fcbbe150694602d451a5`.
The strengthened verifier source
`3ea79363695dd93be5f0a5e8a5121cf6e31d27b8` was staged, not certified deployed.
Older supplied estate maps recording `d5dea8d6` remain historical observations.
Refresh [Git authority](BRANCH_AUTHORITY.md) independently; a new Git HEAD does
not change any running service or settle a liability.

Consensus deliberately uses the separate
`/usr/local/bin/wolochaind-mainnet-node-prewartrophy`, embedded source
`d3bd62414a047a492a3814b7d3baa2717d64db2e`, `vcs.modified=true`, SHA-256
`4b77f622191db7550cb87cafb8f1886a0aadebee3eb6565f9f90036f809e61d3`.
This work never replaces, repoints, restarts, or rebuilds that executable.
Existing 8092/8093 execution roles and request/run state remain authoritative.

### Historical financial holds

[Claim #889 / Founder bonus #15](mainnet-settlement-runbook.md#original-request-record-forensics-for-founder-bonus-15-october-15-2026)
remains pending with an attempted payout and no confirmed transaction hash.
Previously exhausted cached-transfer and request-store investigations are not
repeated here. Incomplete history, a missing record, or an HTTP query failure
does not prove nonpayment. No retry, rescind, state rewind, or hold clearance is
authorized. The independent HD/DE payment-ingress and signer-isolation holds
also remain. Separate service environments do not prove absent shared access.

## Versioned capability and bounded implementation

`internal/satchel` owns the source contract `war-satchel-custody-v1` and intended
role `satchel-vault`. `CurrentCapability()` returns an opaque unavailable value:
deposit, credit, wager, and withdrawal authority are false, and no transfer
destination is exposed. There is no environment flag, caller-supplied boolean,
or candidate evidence record that can turn it into an available capability.
Future availability requires a separate reviewed implementation bound to
independent evidence and provisioned authority.

Pure candidate checks define necessary requirements for a later trusted adapter:

- Exact `wolo-1` chain and `uwolo` base units, positive canonical integer amount,
  immutable server intent, owner/sender, recipient, memo, and bounded intent
  lifetime. The intent is server-issued and wallet-control bound; arbitrary
  client sender, destination, or nonce cannot confer custody authority.
- Raw Cosmos `TxRaw`/`TxBody` bytes whose hash matches the claimed transaction;
  exactly one bank `MsgSend`, one `uwolo` coin, the exact intended transfer, and
  zero execution code. Unsupported messages, extra messages/coins, failed
  transactions, ambiguity, malformed values, or mismatched events fail closed.
- A positive committed deposit height and block identity bound to a fresh
  `wolo-1` head, with finality depth satisfied. Two independently fetched matching
  heads are necessary; candidate checks require explicit synchronized status, heads no older than 30 seconds,
  at least two inclusive confirmations, and bounded clock skew. Stale, future,
  or inconsistent evidence is refused. Merely supplying two equal structures
  does not establish independence or prove a node is synchronized.
- One normalized bank transfer ordinal, `0` for this one-message/one-coin
  contract. The list must include **all** transfer events using the existing
  log-first, split-coin ordering, with top-level events used only if logs have no
  transfers. No fee transfer may be filtered or any ordinal renumbered. V1
  conservatively rejects a transaction whose complete list has extra effects.
  Receipt identity is exact chain ID + uppercase transaction hash +
  canonical bank ordinal. No new namespace or ordinal convention may permit the
  same transfer to be credited a second time.
- Reserve candidates must bind bank evidence to complete dated liabilities,
  approved provenance and non-overlapping collateral. A candidate shape check
  cannot attest completeness, signer control, or available reserves.
- Withdrawal recovery can only hold, reconcile an existing uncertain attempt,
  or replay an already confirmed result. Missing or ambiguous proof never
  authorizes another send.

These are structural checks, not independent custody, finality or solvency
certification. The [C3 reader](war-satchel-chain-evidence-c3.md) adds bounded
network collection and proof consistency against unauthenticated headers. It
does not implement a consensus trust root, persistent receipt consumption, ledger credit, reservation,
signer/keyring access, signature production, transaction broadcast, or live API.
Passing candidate tests leaves the current capability unavailable.

## Evidence and provisioning required before accepting any deposit

1. **Separate custody:** provision a genuinely new vault and `satchel-vault`
   signer under a separately approved operator action. Record exact public key,
   derived canonical address, role, custody owners and policy, access isolation,
   recovery and revocation procedure. Independently verify a domain-bound signed
   control challenge and recovery rehearsal without exposing signer material.
   Include current 8092/8093 and HD/DE authorities in the isolation proof.
2. **Complete collision inventory:** exclude every registered role, retired
   role, module account, and all resolved configuration aliases. At minimum
   reconcile `WOLO_SETTLEMENT_{PAYOUT,ESCROW,TREASURY}_ADDRESS`,
   `WOLO_BET_{PAYOUT,ESCROW}_ADDRESS`, `WOLO_CHALLENGE_ESCROW_ADDRESS`,
   `NEXT_PUBLIC_WOLO_{BET,CHALLENGE}_ESCROW_ADDRESS`,
   `WOLO_STAKING_WALLET_ADDRESS`, `WOLO_COMMUNITY_TREASURY_ADDRESS`, and the
   resolved community-treasury fallback. Inventory keyring selectors, mnemonic
   fallbacks and separately loaded configuration without publishing secrets.
   A candidate or `CERTIFIED` environment variable is not evidence.
3. **Independent chain proof:** implement two independently authenticated chain
   head/proof adapters, with pinned chain identity, checked trust anchors,
   bounded fresh responses, synchronized nodes and agreeing finalized block evidence. Authenticate
   inclusion/execution of the exact transaction and its bank event at the bound
   height. Two aliases of one unauthenticated response are insufficient. Prove
   receipt identity parity and collisions against the existing betting/challenge
   parsers on real indexed transactions before trusting a new adapter.
4. **Reserve provenance:** independently reconcile a complete, dated canonical
   bank snapshot and the full asset/liability ledger: existing manual/challenge
   stakes, refunds, pending claims including #889, staking, prize/treasury
   obligations, Satchel available/reserved/committed/withdrawal liabilities and
   chargeable fees. Prove approved reserve origin and exclusive collateral;
   neither betting escrow nor another user's liability may be reused.
5. **Persistent exact-once credit:** bind a short-lived server intent to the
   logged-in owner and recent single-use Keplr ownership proof. Under durable
   unique constraints and Serializable/locked transactions, consume the global
   receipt identity once and post one immutable balanced credit. Test changed
   proofs, owner retargeting, concurrent credits, expired/orphan deposits and
   restart/replay. Simulation or uncredited evidence tables do not suffice.
6. **Durable withdrawals:** persist the immutable withdrawal identity and exact
   signed transaction bytes/hash before any send. Couple reservations and
   send-intent state durably; authenticate result/recipient/amount/chain and
   reconcile ambiguous attempts before retry. Prove idempotent recovery across
   crashes before signing, after signing, after broadcast and before result
   storage, including concurrent refund/withdrawal and complete unmatched return.
   Enforce a durable unique request-to-signed-transaction association across all
   withdrawals; one bank transfer cannot discharge two separately recorded holds.
7. **Accepted wagering and protected canary:** implement consent, caps, kill
   switch, canonical self-only Watcher/game/proposition admission, one durable
   owner/game reservation, actual vault-to-betting funding and an accepted
   BetStakeTicket. Advance the plan only after acceptance. Verify deposit →
   exact-once credit → accepted wager → refund/settlement → withdrawal under
   independently governed app and chain releases, approved low-budget canary,
   current backups, code-only rollback, and 8092/8093 continuity.

No production deployment, restart, signer creation, migration, or token movement
is part of C2 source work. These outstanding items are activation blockers;
passing source CI does not complete the production C1–C6 acceptance gates or
justify a 100/100 financial-readiness score.

## Regression memory

- Generic 8092 escrow success with a missing matched ordinal is insufficient;
  retain manual compatibility and reject it in Satchel candidate checks.
- A matching transaction hash alone cannot bind a withdrawal to its intended
  payment. Decode and compare the exact bank message as well as the immutable
  request fingerprint. Reject malformed UTF-8 before JSON fingerprinting.
- Equal head fields, evidence digests and successful synthetic fixtures cannot
  prove independent custody, finalized inclusion, complete liabilities or solvency.
- Source tests, including historical payout compatibility tests, run locally and
  in CI. They do not repeat the exhausted production founder investigation or
  resolve claim #889.
