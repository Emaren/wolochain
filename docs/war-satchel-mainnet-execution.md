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
reviewed_at: "2026-10-17"
review_interval_days: 7
sensitivity: "restricted"
---

# War Satchel Mainnet Execution and Operator Gates

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

## HD interface and custody boundary

[HD PR #638](https://github.com/Emaren/app-prodn/pull/638), inspected at
`30d4b23152ef20f293f1cb6459ac674cb89d1036`, defines
`IsolatedSatchelSigner.submitOneShot({requestId, chainId, senderAddress,
recipientAddress, denom, amountUwolo, memo})`. It never automatically retries.
The dedicated service binds `wolo-1`, `uwolo`, the independently provisioned
vault and approved escrow destination before any signing. A service bearer token
is not player spending consent, withdrawal approval, custody certification or
permission to change the destination.

The app contains two compatible client ports with distinct encodings. The
service must validate either complete format and refuse mixed/unknown fields:

| Private endpoint | Contract |
| --- | --- |
| `GET /satchel/v1/health` | Authenticated loopback health, including the exact configured vault, custody role and service identity expected by the selected HD adapter. Health is a process assertion, not independent custody proof. |
| `POST /satchel/v1/one-shot` | Snake-case `request_id`, `chain_id`, `signer_role`, `from_address`, `to_address`, `amount:{denom,amount}`, `memo`; or protocol-1 camel-case `requestId`, `chainId`, `senderAddress`, `recipientAddress`, `denom`, `amountUwolo`, `memo`. |
| `GET /satchel/v1/operations/<operation-id>` | Read an existing durable operation; never signs or resubmits. |
| `POST /satchel/v1/reconcile` | Strict `operation_id`; observes the original signed transaction without transmitting it. |
| `POST /v1/satchel/withdrawals` | Owner-bound withdrawal plus independent approval; a service token alone is insufficient. |

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
independently. A full unmatched refund must equal the original stake; fee
headroom is accounted separately. Finish only with exact owner balances,
liabilities, fee debits and immutable receipts reconciled. A canary failure grants
no claim #889 retry, state rewind or consensus restart.

No canary, wallet creation, funding, installation, key operation or real transfer
was performed in this source work. CI and negative tests are reported against
the exact PR head; they do not certify any unperformed operator step above.
