---
id: "aoe2war.wolochain.war-satchel-mainnet-execution"
title: "War Satchel Mainnet Execution and Operator Gates"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "git"
authority: "restricted-satchel-execution-and-provisioning-contract"
reviewed_at: "2026-10-30"
review_interval_days: 7
sensitivity: "restricted"
---

# War Satchel Mainnet Execution and Operator Gates

## Independent source and gate review — 2026-10-30 UTC

Session B re-read the operator/owner gates against the immutable held-source
[`http.go`](https://github.com/Emaren/wolochain/blob/9c11a617ba1362fbdee1a9ef5903a1efad0e6db1/internal/satchelservice/http.go)
(blob `2bb311876fd84ebb94eca760de6304df993b0d0c`) and
[`reviewer_finance_observation.go`](https://github.com/Emaren/wolochain/blob/9c11a617ba1362fbdee1a9ef5903a1efad0e6db1/internal/satchelservice/reviewer_finance_observation.go)
(blob `d08a835500bc8da406b19bd60eea1a0ea9574cfb`).
The private HTTP handler does not equate health/accepted broadcast with
credit. `AuthenticatedFeeCensus` still returns
`ReviewerFinanceCoverageUnknown`: owner ledger and authenticated bank reads
are NOT complete cross-source signer/withdrawal/uncertain-fee coverage.
[Codex's separate October 29 HEL1 receipt](https://github.com/Emaren/wolochain/pull/115#issuecomment-6508382058)
reports **8094/8095 absent**, and notes HD Satchel migrations not qualified.
The [B #121 exact-head source CI](https://github.com/Emaren/wolochain/actions/runs/40979957375)
passes 19 synthetic arithmetic cases but FAILS DocsV2 review expiry; it is
not a funded execution, bank witness or signer approval. This source review
does not validate pending prepared fees, unmaterialized broadcasts, signed
dual-review identity, native keyring, replay/return executor, real recovery or
owner Keplr authorization. The financial path remains **HOLD**.

**Source implementation is not production authorization. C2 custody remains
`UNAVAILABLE`; C3 evidence remains `NONCREDITING`.** No dedicated wallet, signer
control, independent consensus trust root or reconciled financial reserve has
been certified by this change. No deposit destination is published here.

The source starts at `wolo-1-mainnet-prep` merge
`c1210dda37b725a5b141ad63361048d4b37731c2` ([PR #24](https://github.com/Emaren/wolochain/pull/24)).
The [documentation index](DOCUMENTATION_CONTROL_PLANE.md) identifies the
implementation baseline. Existing consensus code, 8092/8093 financial roles and
historical liabilities remain separate from the dedicated Satchel execution
process. App/API source is owned by its separate release; this PR changes neither.

The exact private wire schemas and safe failure semantics are versioned in
[OpenAPI 1.0.0](settlement-contracts/war-satchel-http-v1.openapi.json).
Source ABI tests fail on route or Go JSON-field drift. The
[controlled installation and recovery procedure](war-satchel-controlled-release.md)
keeps the dedicated signer separate from legacy services and consensus.

## HD interface and custody boundary

### October 22 — qualified runtime capability, no live activation

The production command now installs `CustodyAuthority` before opening 8094.
Its opaque `RuntimeCustodyCapability` can report `AVAILABLE` only after all of
these current facts agree: the actual encrypted-keyring backend still owns its
native directory lease; the recovered, bounded journal passes every existing
payload/effect check and has no unresolved operation; bank state at `head-1`
authenticates against the exact configured Comet root; and two distinct reserve
reviewer signatures bind that bank commitment, journal digest, liability and
nonoverlap evidence, actual running binary, exact configuration and execution
permit. All five reviewer/approval/activation keys must be distinct.

Three optional private configuration fields provision this boundary:
`accounting_reviewer_key_hex`, `custody_reviewer_key_hex` and
`reserve_review_file`. They must be supplied together. Missing provisioning
keeps the service `UNAVAILABLE` and refuses new execution. No reviewer key,
permit, vault or production trust root is supplied by source. Reviewers sign
the exact bytes from `satchelservice.ReserveReviewMessage`; this function does
not sign or certify a proposal. A signature does not discover missing financial
obligations or establish the signer's independence: the named operators still
must genuinely prove those external facts.

Health now includes `custody_capability` and, only for a positive runtime value,
`custody_capability_version:"war-satchel-runtime-custody-v1"` and
`custody_capability_expires_at`. The deadline is bounded by the authenticated
bank/anchor freshness, both-reviewer statement and current runtime permit.
Health requalifies from actual current handles; an environment boolean or a
marshalable `QualifiedReserveReview` cannot supply the opaque capability.
The dormant C2 `CurrentCapability()` and the read-only custody-journal response
remain `UNAVAILABLE`, with credit and solvency authority false.

For each new operation, qualification occurs under the existing execution
mutex **before its first durable intent write**. A private grant binds only that
exact request fingerprint and its exact eventual signed bytes, so the admitted
operation may advance its own journal phases without trying to reuse the
pre-intent snapshot. Another operation cannot share the review: any journal
mutation invalidates health/admission until a fresh dual review binds the new
bank and journal state. Native signing rechecks the grant after account/head
I/O immediately before SDK signing; broadcasting rechecks it again. Current
private configuration, permit, bearer/unlock-file identity and permissions,
journal-file identity, native lease and grant expiry are enforced. A revoked
or expired pre-sign grant never enters SDK signing. A signature that already
exists remains `UNKNOWN` if authority is then lost; it is never rebroadcast on
retry. Read-only proof retrieval, operation lookup and reconciliation continue
after revocation. Return preparation remains conservatively gated; it cannot
be used to relax reserve admission.

**Conservative execution margin:** amount plus the exact configured fee must
fit funds remaining **after** known liabilities, uncertain upper bounds, gas
reserve and unencumbered minimum. This requires extra equity beyond covered
customer principal. There is currently no independently authenticated atomic
liability-discharge proof, so a customer withdrawal/wager cannot assume its own
liability has been released. Zero extra margin remains unavailable even with
two valid signatures. Tests use actual SDK assets of 110 WOLO and test inventory
countersigned by two distinct fixture keys covering 100 WOLO of owner liability plus 1 WOLO uncertain
exposure and 0.02 WOLO gas/floor: one 7 WOLO transfer fits the extra margin; the
next does not. These are controlled test authorities and funds, not production
accounting or custody certification.

The latest product ceilings are 10,000 WOLO per wager and 50,000 WOLO daily
Auto Bets. The native signer, independent HD snapshot/origin/owner reviewer and
funded return verification share these ceilings. Existing smaller configured
limits, signed owner budgets and reservations are unchanged and remain binding;
old mandates are never rewritten. The frozen `8c509e8` verifier retains its old
semantics. Source with the expanded cap/proof contract needs a separately
reviewed reproducible artifact and actual receipt; do not relabel that binary.

No runtime is activated by this source change. Production remains blocked on
independent chain trust, dedicated vault control, genuine complete liability
and nonoverlap reconciliation, separately provisioned reviewers, exact-build
permits, reviewed recovery/installation and bounded transaction approvals.
Authenticated bank observations remain bounded observations, not a promise
that no newer network block can exist during the chain/database interval.
Historical 8092/8093 liabilities and claim #889 remain protected by issue #5.

[HD PR #638](https://github.com/Emaren/app-prodn/pull/638), inspected at
`6afc11399c6e84c7cfcb308f4d4523ce1b8c3866`, defines
`IsolatedSatchelSigner.submitOneShot({requestId, chainId, senderAddress,
recipientAddress, denom, amountUwolo, memo})`. It never automatically retries.
The dedicated service binds `wolo-1`, `uwolo`, the independently provisioned
vault and approved escrow destination before any signing. A service bearer token
is not player spending consent, withdrawal approval, custody certification or
permission to change the destination.

The authoritative Go transport is **`127.0.0.1:8094` with Bearer
authentication**. `warSatchelDedicatedSignerClient.ts` targets this protocol.
The Go service requires the protocol-2 signed owner reservation for a new wager.
Its existing snake-case and protocol-1 camel-case forms support exact historical
replay; they cannot initiate a new bearer-only wager. Mixed/unknown fields fail.
HD's competing `warSatchelIsolatedSignerClient.ts` targets `127.0.0.1:8194`,
`/v1/*` and HMAC envelopes; that client is not this Go protocol and cannot be
enabled against it. HD must select the 8094 adapter in its separate release.

| Private endpoint | Contract |
| --- | --- |
| `GET /satchel/v1/health` | Authenticated loopback health, including the exact configured vault, custody role and service identity expected by the selected HD adapter. Health is a process assertion, not independent custody proof. |
| `POST /satchel/v2/one-shot` | Protocol 2 snake-case wager with required independently signed owner ledger reservation; exact schema is in the versioned OpenAPI contract. |
| `POST /satchel/v1/one-shot` | Legacy replay compatibility; a new bearer-only wager is refused. Snake-case `request_id`, `chain_id`, `signer_role`, `from_address`, `to_address`, `amount:{denom,amount}`, `memo`; or protocol-1 camel-case `requestId`, `chainId`, `senderAddress`, `recipientAddress`, `denom`, `amountUwolo`, `memo`. |
| `GET /satchel/v1/custody/journal` | Bounded consistent execution-history checkpoint, exact journal/policy digests and unresolved/confirmed totals; bank, credit and solvency authority always false. |
| `GET /satchel/v1/operations/<operation-id>` | Read an existing durable operation; never signs or resubmits. |
| `POST /satchel/v1/reconcile` | Strict `operation_id`; observes the original signed transaction without transmitting it. |
| `POST /v1/satchel/withdrawals` | Owner-bound withdrawal plus independent approval; a service token alone is insufficient. |
| `POST /satchel/v1/returns/prepare` | Strict version-2 signed claim/allocation below; durably reserves the entitlement and returns a prepared 8092 run with `execution_authorized:false`, `credit_authorized:false`. It never calls 8092. |
| `POST /satchel/v1/returns/reconcile` | Strict `{approval:<original-version-2-approval>,tx_hash:<hash>}`; authenticates the original escrow return and persists its unique receipt without signing, transmitting or crediting. |

The endpoint is private `127.0.0.1:8094` with service-to-service Bearer
authentication; it must never be exposed by public nginx or an unauthenticated
signing route. Wager request identity is `satchel:ticket:<execution-id>` and its
memo must match the canonical HD ticket contract. Do not derive a different
ticket number from the execution ID: the durable request and ticket memo are
distinct identities supplied by the app's prepared ticket.

The historical HD result label `broadcast_confirmed` means an accepted broadcast
hash at this adapter boundary. It is not committed chain execution. The existing
ticket commit independently verifies the exact funding transaction before a
wager can become accepted. Timeout, malformed acknowledgment, process failure or
uncertain broadcast returns UNKNOWN/HOLD; no caller may interpret HTTP 200 alone
as payment or nonpayment.

## App contract for new owner-reserved wagers

`POST /satchel/v2/one-shot` requires `protocol:2`, `request_id`,
`chain_id:"wolo-1"`, `signer_role:"exclusive-war-satchel-v1"`, `from_address`,
`to_address`, `amount:{denom:"uwolo",amount:<canonical positive units>}`,
`memo`, `owner_id` and `reservation`. See the exact machine-readable
[request schema](settlement-contracts/war-satchel-http-v1.openapi.json).
The app must atomically create and retain its real owner reservation before
requesting independent review; a service token does not prove an owner balance.

The reservation is version 1 and binds operation, owner, vault, escrow, amount,
memo, `reservation_digest`, `ledger_revision`, `consent_digest`, `fee_uwolo`,
issue and expiry times. All three digests are lowercase SHA-256 and the time
window is at most 300 seconds. The independent approver signs the exact bytes
returned by `satchelservice.WagerReservationMessage` with its configured
Ed25519 review key. It must independently validate the app's durable hold,
owner mandate/caps/revocation, still-open market and operating-fee headroom;
there is no approval/key generator or generic signing endpoint here. This
boundary does not invent a second customer ledger or certify a bank balance.
The separate activation authority cannot substitute for this ledger reviewer.

A new v1 request without this authority is refused. Historical exact v1 replay
can still read its existing durable result without broadcasting. Protocol 2
returns actual `ACCEPTED`/`UNKNOWN`/`CONFIRMED` state instead of the historical
`broadcast_confirmed` acknowledgment label. Only authenticated reconciliation
of the original signed bytes proves committed successful execution. Changed
owner, ledger hold, consent, amount, destination or fee under the same durable
identity must never produce another transfer.

## Persistent one-shot execution and recovery

One isolated process exclusively owns the persistent bbolt journal. The whole
database file is a financial authority, not a disposable cache. Each operation
ID permanently binds sender, destination, denom, amount and memo; a changed
payload under the same ID fails. Before signing, the operation intent and a
signing HOLD are durable. Exact signed transaction bytes/hash are persisted
before a broadcasting HOLD and the single transmission attempt.

Every replay phase refuses another transmission, including a restart before an
acknowledgment. Unresolved signing/broadcast outcomes fence subsequent operations
until independently reconciled; this prevents a fresh operation ID from silently
reusing an uncertain signer sequence or available balance. Never delete a
journal, operation, lock or unknown attempt to make a request retryable. A missing
hash is not proof that signing or broadcasting did not occur.

Reconciliation must compare the existing immutable signed bytes/hash and exact
operation to canonical chain execution; it cannot sign or submit replacement
bytes. Accepted, confirmed, failed and UNKNOWN remain distinct. An administrative
decision or a token-authenticated caller cannot invent a successful transfer.
Backups and rollback preserve the latest journal generation, including all
pending liabilities, request fences and signed bytes.

## Custody reconciliation checkpoint

`GET /satchel/v1/custody/journal` returns one consistent local bbolt snapshot
without signing, broadcasting, network I/O, journal writes or release of holds.
The versioned schema defines every field: exact framed `journal_digest`,
`policy_digest`, bounded scan counts/bytes, six operation status counts,
unresolved operation count, held outbound amount, confirmed outbound amount,
and durably reconciled return receipt count/amount. UNKNOWN, ACCEPTED and
OBSERVED_NONCREDITING principal remain held; zero unresolved operations do not
prove zero external liabilities or permission to spend the vault balance.

The digest binds actual bucket/key/value boundaries and bytes, including
historical authority/reservation indexes; the scan refuses more than 8 MiB,
100,000 framed records or depth 64, arithmetic overflow and inconsistent
receipt/effect history. It is a checkpoint of execution history, not a public
balance API or customer ledger. Always expect
`bank_balance_authenticated:false`, `credit_authorized:false`,
`solvency_authorized:false`, `custody_capability:"UNAVAILABLE"`. No netting of
reported totals proves fees, complete deposits, app liabilities or bank reserves.
A real reserve attestation still needs independently authenticated exact-height
bank evidence and the app's quiesced complete liability/reservation snapshot.
Neither a digest nor a reviewer's signature can invent those financial facts.

## Consensus authentication requires an independent checkpoint

The opt-in `satchel.TrustedReader` uses the pinned CometBFT light client to
verify validator signatures/transitions from a provisioned height/hash, then
binds transaction inclusion, the H+1 execution-result commitment and a fresh
head to those verified headers. It does not adopt a checkpoint automatically
from an RPC. Its `AuthenticatedEvidence` is opaque and still grants no ledger
credit or C2 custody capability.

The operator must independently verify and retain `height`, uppercase block
`hash`, `period_seconds` and `evidence_reference`, and provision a genuinely
separately governed witness. Two aliases of the documented mainnet node are not
independent. Source validation cannot certify how an operator obtained those
values or the honesty of the validator quorum. Preserve the checkpoint and
configuration evidence with release receipts.

Missing, expired, future or inconsistent trust evidence fails closed. Ordinary
C3 observations remain `NONCREDITING` and cannot release an unresolved signer
fence. The light-client path is bounded rather than an unbounded history sync;
resource refusal also retains the hold. No production checkpoint or independent
witness has been provisioned or certified by this PR.

## Withdrawals and owner-attributed returns

Withdrawals require an independently approved owner-bound request in addition to
the service credential. The approval binds the withdrawal/challenge identity,
owner and wallet, exact `uwolo` amount and memo, hold digest, issue time and expiry
under the service's canonical domain-separated Ed25519 contract. Request
retargeting, changed amounts, expired approval and reuse of an approval for a
different hold must fail before signing. The service must not create an approval
key or claim that a bearer token alone authorizes withdrawal.

The exact approval message is the UTF-8 JSON array returned by the exported
`satchelservice.ApprovalMessage` function, in this fixed order:

```text
["aoe2war/satchel/withdraw-approval/v1", "wolo-1", "uwolo", vault,
 withdrawal_id, challenge_id, owner_id, recipient, amount_uwolo, memo,
 hold_digest, issued_at, expires_at]
```

The actual signature covers canonical Go JSON bytes without display whitespace,
not this formatted example. Use `ApprovalMessage` to avoid encoder/escaping
differences. The signature is strict standard-base64 Ed25519. Both IDs are
canonical lowercase UUIDs; the operation ID is
`satchel:withdrawal:<withdrawal_id>` and the memo is
`aoe2war/satchel/withdraw/v1/<withdrawal_id>`. The hold digest is 64 hex digits,
times are Unix seconds, issuance cannot be in the future, and expiry must be
after server time and no more than 300 seconds after issuance. The independent
approver must verify the real owner's ledger hold and wallet consent before
signing; this cryptographic approval does not itself create that ledger evidence.

The strict withdrawal HTTP object is `protocol:1`, `operation_id`,
`chain_id:"wolo-1"`, `from_address`, `to_address`,
`amount:{denom:"uwolo",amount:<canonical-positive-units>}`, `memo`, `owner_id`
and `approval`. The approval object contains `withdrawal_id`, `challenge_id`,
`owner_id`, `recipient`, `amount_uwolo`, `memo`, `hold_digest`, `issued_at`,
`expires_at` and `signature`. Economic fields must agree between the request,
approval and persisted hold.

An escrow return is separate from a player deposit. Reconcile the actual
escrow-to-vault transfer against the durable HD claim/ticket/owner mapping,
authorized amount and exact claim-return memo. Credit a globally unique receipt
only through the app's funded ledger after the exact chain proof is verified.
Neither a vault balance increase nor recipient-and-amount coincidence identifies
the owner. Distinct bank effects must retain their identities; one transfer
cannot discharge two owners' claims or withdrawal holds.

An unmatched refund returns the complete original stake with **zero betting
fee**. Signer transaction fees require separately reconciled operating headroom;
they must not silently reduce the refund or spend another owner's reserve.
This signing service does not mutate the app ledger or manufacture a return
from the existing betting escrow.

## Version-2 multi-leg return contract

One funding operation may pay a winner leg and refund a desync leg independently,
in either order. The durable deduplication key is the globally unique `claim_id`,
with an immutable fingerprint binding owner, funding operation/hash, ticket,
market, leg, entitlement, claim kind, exact amount, allocated principal and
allocation/funds roots. It is no longer a single return per funding operation.
Each entitlement names exactly one claim; changing a claim's economics or owner
under the same ID is a conflict. Transaction-hash consumption spans all return
and signing receipts in this journal, regardless of an observed fee-event index.

`internal/satchelservice/returns.go` and `return_allocation.go` define the exact
snake-case JSON objects. `POST /satchel/v1/returns/prepare` takes this outer
`ReturnApproval` object directly, without a wrapper:

| Object | Required fields |
| --- | --- |
| `ReturnApproval` | `version:2`, `operation_id`, `claim_id`, `owner_id`, `ticket_id`, `market_id`, `leg_id`, `entitlement_id`, `claim_kind`, `amount_uwolo`, `allocation_digest`, `issued_at`, `expires_at`, `signature`, `allocation`. |
| `allocation` (`ReturnAllocation`) | `version:2`, `allocation_id`, `revision`, `operation_id`, `owner_id`, `ticket_id`, `funding_tx_hash`, `return_cap_uwolo`, `funds_budget_id`, `funds_available_uwolo`, `bank_evidence_digest`, `bank_height`, `bank_block_hash`, `legs`, `issued_at`, `expires_at`, `signature`. |
| Each `legs[]` element | `leg_id`, `market_id`, `stake_uwolo`, `entitlements`. |
| Each `entitlements[]` element | `entitlement_id`, `claim_id`, `claim_kind`, `principal_uwolo`, `amount_uwolo`. |

Amounts are canonical positive decimal `uwolo` strings. `ticket_id`, `market_id`
and `claim_id` are positive decimal strings of at most 12 digits. Claim `889`
remains excluded. Other identities use the existing bounded identifier contract.
`claim_kind` is `bet_payout` or `bet_refund`. Funding hashes are uppercase hex;
bank evidence and block hashes are nonzero 64-digit hex. Times are Unix seconds;
both reviews must be current for preparation, issued no later than server time
and valid for at most 300 seconds. JSON bodies remain bounded to 16 KiB, with
duplicate, aliased, unknown and trailing fields rejected.

The original wager must already be `CONFIRMED`, have the exact funding hash,
escrow destination and `AoE2HDBets bet ticket v1 · ticket <ticket_id>` memo.
The full immutable leg partition sums exactly to that funding principal. There
are at most 16 legs, 64 entitlements per leg and 128 total entitlements. Legs are
strictly lexicographically sorted by `leg_id`; each entitlement list is sorted
by `entitlement_id`. Market, claim and entitlement identities are unique within
the allocation. A leg's entitled principal portions cannot exceed its stake.
Every refund's amount equals its exact allocated principal: a partial unmatched
leg returns 100% of that portion, with no 2% betting fee. Payouts may include
reviewed winnings, within the immutable return cap.

Use the exported Go helpers for the actual canonical JSON bytes. The two
Ed25519 signatures use the configured independent approval public key and
strict padded standard base64. Their distinct domains cannot authorize a
withdrawal or substitute for the player's betting consent. The array contracts
are:

```text
legs := [[leg_id, market_id, stake_uwolo,
          [[entitlement_id, claim_id, claim_kind, principal_uwolo, amount_uwolo], ...]], ...]

allocation_fields := ["aoe2war/satchel/return-allocation/v2", "wolo-1", "uwolo",
 escrow, vault, version, allocation_id, revision, operation_id, owner_id,
 ticket_id, funding_tx_hash, return_cap_uwolo, funds_budget_id,
 funds_available_uwolo, bank_evidence_digest, bank_height, bank_block_hash, legs]

AllocationMessage := allocation_fields followed by issued_at, expires_at
AllocationDigest := SHA-256 of canonical JSON(allocation_fields)

ReturnApprovalMessage := ["aoe2war/satchel/claim-return-approval/v2", "wolo-1",
 "uwolo", escrow, vault, version, operation_id, claim_id, owner_id, ticket_id,
 market_id, leg_id, entitlement_id, claim_kind, amount_uwolo,
 allocation_digest, issued_at, expires_at]
```

`AllocationMessage`, `AllocationDigest` and `ReturnApprovalMessage` are the
authoritative encoders; the display whitespace above is not signed. Digesting
excludes review times/signature so the same plan can be freshly approved. The
outer approval's `allocation_digest` must exactly identify the nested plan.

The first independently signed revision may arrive out of order. A newer
revision must preserve the full leg partition, root, cap and funds evidence,
and be an append-only superset of all previous entitlements. Older signed
revisions may prepare an earlier unprepared claim only when their entire plan
is an unchanged subset of the stored latest revision. Stored revisions and
reservations never regress. Existing claims retain their original durable
approval for reconciliation; a fresh signature cannot retarget an old claim.

In the same bbolt transaction as the new claim record, the engine reserves its
full amount against both the funding allocation's cap and **one shared funds
budget for this journal**. Pending, unknown and paid claims all retain their
reservations. Every funding allocation must use the same pinned budget ID,
ceiling and bank-review identity; changing the budget cannot mint fresh capacity.
No timeout, missing proof or cancellation frees a reservation. Reservations are
durable before any prepared run is returned.

The bank/liability review is authenticated by the independent reviewer's
signature and referenced digest, height and block identity. **It is not a native
bank-state Merkle proof, current solvency certification or a lock on competing
escrow writers.** Real activation still requires complete fresh physical-bank,
liability and fee-headroom evidence, exclusive allocation coordination, and the
existing 8092 signer's funds/sequence preflight. This bounded service prepares
and reconciles returns; it holds no betting escrow key or execution credential.

Preparation returns HTTP 200 with `kind:"escrow_run_prepared"`,
`execution_authorized:false`, `credit_authorized:false` and `run`. The run uses
the existing `/settlement/v1/runs` schema: `settlement_run_id` and the sole
payout's `request_id` are `satchel:claim-return:<claim_id>`, `source_app` is
`aoe2hdbets`, `source_event_id` is the original `operation_id`, `signer_role` is
`escrow`, destination is the configured Satchel vault, amount is the exact
approved amount, and memo remains
`aoe2war/satchel/claim-return/v1/<claim_id>`. No new return execution route is
introduced. Only a separately authorized operator may submit this exact run to
the protected existing 8092 lane after its release gates close. Replaying the
prepared run must use its original durable IDs, never a new claim or retry ID.

Reconciliation requires the original durable approval and authenticated exact
escrow-to-vault chain evidence. Its version-2 receipt includes the complete
owner/ticket/market/leg/entitlement/allocation identity, original operation and
claim, exact amount, transaction hash, receipt ID, committed height/block hash,
and `credit_authorized:false`. Expired reviews may reconcile an already prepared
claim; they cannot prepare a new liability. Missing/forged/ambiguous evidence
leaves the claim reserved and triggers no transmission.

**Migration and HD credit remain HELD.** Existing version-1 claim records,
receipts and one-return markers are preserved byte-for-byte; their presence
blocks new version-2 allocation until a separately reviewed migration/liability
decision. There is no automatic replay, reinterpretation or migration command.
The retained bucket name `owner-returns-v1` is storage compatibility, not v1
approval acceptance.

HD must independently map `owner_id` to the actual Steam user's immutable
`users.id`/`uid`, `ticket_id` to `BetStakeTicket.id`, `leg_id` to `BetStakeLeg.id`,
and `market_id` to that leg's market; `entitlement_id` must identify the reviewed
settled `BetWager` entitlement. `claim_id` is `PendingWoloClaim.id`, whose
`claimedByUserId`, source market, kind and amount must agree. The Go signer does
not read these application tables. HD's current return-credit function can
aggregate one owner's wagers across multiple tickets in a market; such a mixed
claim cannot be silently recast as this contract's single funding operation.
That explicit bridge remains required in the separately owned HD integration.
Only its atomically locked funded-ledger path may consume the globally unique
chain receipt, recheck owner/entitlement and all vault liabilities against fresh
bank evidence, and post the rightful owner's credit. A Go receipt grants no
ledger posting authority.

## Secure operator provisioning — separate approval required

No step below was performed by this PR. Wallet/key creation, funding,
installation and any real transmission require explicit operator approval.

1. Allocate a genuinely separate `exclusive-war-satchel-v1` vault and service
   identity. Independently reconcile the complete
   [protected wallet inventory](mainnet-wallets.md), all 23 C2 registered roles,
   retired roles and resolved runtime aliases. Exclude betting escrow/payout,
   founder, treasury, staking, faucet, relayer and validator custody. Distinct
   addresses alone do not prove independent seed custody or administrative control.
2. Record the public key/address binding, custody owners, dedicated keyring and
   OS access policy. Use an already provisioned native Cosmos SDK file keyring
   provisioning; this service supplies no key-creation endpoint and invokes no
   chain CLI. Require an independent domain-bound control challenge and an
   isolated recovery rehearsal. Do not copy an existing role's mnemonic or key.
3. Give the process a dedicated least-privilege OS account and exclusive journal
   directory. Existing web/API, 8092/8093 and validator accounts must not be able
   to read or replace its keyring, passphrase, bearer credential or journal.
   Store secret files outside Git with owner-only permissions and load secrets
   through the protected service manager. Never pass secrets as command-line
   arguments, print credential files, log request approval material or place
   mnemonic/passphrase values in an environment example.
4. Provision the withdrawal approval public key from the independent authority;
   keep its private approval key outside the signing service. Bind both approval
   and service custody policies to reviewed, dated evidence. A health field
   claiming no shared mnemonic cannot independently establish this fact.
5. Seal encrypted off-host backups and an isolated restore proof for the
   keyring and current journal, with separate recovery custody. Reuse existing
   Recovery OS proof verification where applicable; do not treat a dated backup
   as the latest operation journal or restore an older journal over real sends.
6. Reconcile bank assets, all owner available/reserved/committed/withdrawal
   liabilities, operation uncertainty and fee headroom. Prove approved reserve
   provenance and exclusive collateral. Existing betting collateral and historical
   balances are unavailable as inferred Satchel funding.

## Installation and health — staged, not activated

Build a versioned dedicated Satchel executable from the exact reviewed source,
record embedded VCS/unmodified metadata and executable SHA-256, and verify them
again at staged installation. Never replace
`/usr/local/bin/wolochaind-mainnet-node-prewartrophy` or the shared legacy
`/usr/local/bin/wolochaind-mainnet` to install Satchel.

Provision configuration and secrets privately, preserve the dedicated journal
and keep public deposit, funded credit, live Mecha and withdrawal activation OFF.
An authenticated health response must match the intended vault, role, key/build
identity, exact chain/denom and durable one-shot contract. Independently verify
the running executable/PID, bind address, filesystem ownership and keyring public
identity; compare expected values rather than trusting the service's report.
Health inspection must not sign, broadcast, repair or mutate a ledger.

A configuration flag is an execution switch after evidence review, never
certification. Source CI cannot establish key possession, exclusive custody,
current solvency or independent consensus trust. The optional light-client path
requires the independently provisioned checkpoint/witness above; ordinary C3
observations, matching endpoints and self-reported certification remain
insufficient.

## Existing two-settlement release remains protected

Fresh [issue #5](https://github.com/Emaren/wolochain/issues/5) still distinguishes
operator-observed legacy settlement VCS
`78c25985420ee41a6678c42fab8ea8d6c3b1b519` from financial source
`bdbce253c524d6faac14f61cd129ac5072287c3f`. A new checkout, candidate build or
Satchel health response does not remove that runtime hold. Founder #889 remains
UNKNOWN and must not be retried or inferred paid/unpaid from incomplete history.
No new founder investigation or live state read was performed here.

PR #24 deliberately retired the old `3ea79363` helper's mutating rollback/rescue
modes before side effects. Its historical `--inspect` is not a current release
controller. Do not reuse draft PR #11/#16, repin that old helper or import an
unrelated prior release branch to authorize this release.

A separately authorized settlement-only window must first bind the exact
candidate artifact/source and both current service units; prove fresh ingress
isolation and zero inflight/unknown ownership; preserve both current request,
run, receipt and prebroadcast-hold stores; and establish independently executable
code-only recovery. Keep producers quiesced through adverse rollback rehearsal.
Never restore historic monetary state or automatically resume financial producers
on the old binary: legacy grouped/receipt semantics are not certified compatible.
The consensus executable, PID/hash and advancing chain remain unchanged.

Only after named approval may an operator execute the paired settlement
procedure, capture actual `/proc` executable hashes/VCS and health for both
8092/8093, and reconcile VPS source plus federation to the observed runtime.
Missing approval, one failed service, unexpected state, unavailable recovery or
changed consensus identity is a STOP. This document authorizes no service stop,
restart or activation; the current source-readiness evidence is read-only.

## One bounded mainnet canary — explicit money approval required

After custody, accounting, chain trust, app migration/release and settlement
gates are genuinely closed, approve one named owner, exact principal and fee
budget, wallet/vault/escrow identities, request IDs, evidence collectors and stop
conditions. Use operator-approved funds, never another user's liability.

Run the real Keplr deposit → exact-once funded credit → signed self-only Watcher
authorization → one exact vault-to-escrow ticket → accepted wager → full unmatched
refund/settlement return → owner withdrawal journey. Use an actual eligible game
and canonical ticket; do not fabricate Watcher proof or turn a simulation row
into funds. Verify raw transaction identity, execution, sender, recipient,
amount, memo and unique receipts at each movement. Re-submit identical requests
only as non-sending replay checks, and verify a changed payload under an original
operation ID is refused.

An UNKNOWN response freezes the operation and corresponding app reserve; stop
the canary without another send. Preserve original bytes/hash and reconcile
independently. A full unmatched refund must equal its entire unmatched stake portion; fee
headroom is accounted separately. Finish only with exact owner balances,
liabilities, fee debits and immutable receipts reconciled. A canary failure grants
no claim #889 retry, state rewind or consensus restart.

No canary, wallet creation, funding, installation, key operation or real transfer
was performed in this source work. CI and negative tests are reported against
the exact PR head; they do not certify any unperformed operator step above.

## Recovery validation — October 17, 2026

The recovered starting PR head was
`d3b7586dc13c9ab38d634acbc0572e350463a325`. The immutable-baseline fixture in
`tests/fixtures/satchel-multileg-before_test.go.txt`, replayed offline by
`scripts/check-satchel-multileg-regression.py`, reproduces both original defects:
a second independently approved leg is refused by the one-operation marker,
and a full refund of one leg is refused because it is smaller than total ticket
funding. Ordinary source CI now reproduces those historical failures as well as
running the corrected contracts.

The recovered full Go suite and full repository race run each pass **1,043 tests
and subtests (225 top-level), zero failures**. Four opt-in application simulations
and the foreign-owner filesystem check requiring elevated test privileges are
skipped locally. Native signer/keyring tests use synthetic temporary fixtures.
Vet, both executable builds, protobuf drift checks, source invariants and the
nine Python settlement safety tests pass. These results do not establish live
key control, balances, reserves, a production checkpoint or a successful canary.

Coverage includes winner/desync claims in either order, partial/full unmatched
principal, immutable claims, concurrent delivery/shared-budget races, append-only
revisions arriving out of order, restart/uncertain reservations, physical receipt
reuse, independent withdrawal authority and nested HTTP schema/receipt binding.
The C3 SDK timestamp/status-commit checks were already present; the recovered
patch adds the missing witness freshness check after light-client I/O.

## Exact HD #656 compatibility handoff (source inspected through GitHub)

At HD #656 head `1a79e5f615bff0ebf2f5c6903042ac26f42c5424`,
`warSatchelDedicatedSignerClient.ts` still sends an unsigned
`POST /satchel/v1/one-shot` and expects the historical
`broadcast_status:"accepted_once"` field. Its
`warSatchelAutoBetExecutor.ts` signer input has no reservation approval.
That contract intentionally cannot initiate a new wager against this backend;
new source requires `/satchel/v2/one-shot` and independent owner-ledger review.
The concurrent app engineer owns the following minimal compatible patch:

1. Add the exact `WagerReservation` object from the OpenAPI contract to the
   existing signer input. After canonical ticket preparation, independently
   review the durable owner reservation, current consent/market/caps/revocation
   and separately reconciled fee headroom. Bind operation, owner, vault, escrow,
   amount, exact prepared ticket memo, hold/ledger/consent digests and short
   expiry. Persist the original approval and exact request before its one-shot
   attempt; never manufacture a signature from a service credential.
2. Preserve the existing serializable reservation and
   `markSatchelSubmissionAttempt` no-retry fence. Extend the client to send
   `protocol:2`, exact snake-case fields and the stored signed reservation to
   `/satchel/v2/one-shot`. Retain the private 8094 bearer protocol; no 8194/HMAC
   client or new parallel ledger is needed.
3. Consume actual `status:ACCEPTED` (or authenticated `CONFIRMED`), exact
   request/operation identity, valid hash and `durable_request_fenced:true`.
   Protocol 2 does not emit the misleading historical `broadcast_confirmed`
   alias. An accepted broadcast still requires authenticated exact funding proof
   before committing a ticket, consuming a game slot or posting ledger effects.
4. On timeout, malformed response, UNKNOWN or uncertain attempt acknowledgment,
   keep the original app hold and recover via original operation lookup and
   reconcile/proof routes. Never resubmit, change IDs or auto-refund uncertainty.
   Add real cross-contract tests for signed v2 acceptance, invalid/expired or
   reused approval, changed memo/owner/fee and restart recovery, preserving the
   false financial activation gate.

The exact Go approval bytes are supplied by exported
`WagerReservationMessage`, not an app-invented canonicalizer. HD's existing
1,000 WOLO combined game and 10,000 daily policy remain app authority; this
handoff changes neither cap. No app files were read locally or modified.
