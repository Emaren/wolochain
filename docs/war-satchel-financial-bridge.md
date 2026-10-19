---
id: "aoe2war.wolochain.satchel-financial-bridge"
title: "Authenticated War Satchel Financial Bridge"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "git"
authority: "source-integration-proof-not-production-approval"
reviewed_at: "2026-10-18"
review_interval_days: 14
sensitivity: "restricted"
---

# Authenticated War Satchel Financial Bridge

This source contract composes PR #28's durable dedicated signer with the C3
CometBFT reader. It introduces portable evidence and an independent offline
verification command. Every exported and verified receipt remains
`credit_authorized: false`. The HD financial activation hold remains required;
C2 custody remains **UNAVAILABLE**. Source CI does not certify a vault, key,
balance, liability reconciliation, endpoint operator or protected release.

The exact private wire schemas and safe failure semantics are versioned in
[OpenAPI 1.0.0](settlement-contracts/war-satchel-http-v1.openapi.json).
Source ABI tests fail on route or Go JSON-field drift. The
[controlled installation and recovery procedure](war-satchel-controlled-release.md)
keeps the dedicated signer separate from legacy services and consensus.

## Authority and transport

The sole listener is literal loopback `127.0.0.1:8094`, with
`Authorization: Bearer <operator-provisioned private token>`. Only HD's server
may know this credential. Browser evidence, proxy headers and CORS do not grant
authority. The existing `/satchel/v1/health` and `/satchel/v1/one-shot` contracts
remain; no 8194/HMAC listener exists here. Health flags do not authenticate a
transaction or authorize a ledger credit.

The normal service still requires an independent activation permit, isolated
vault/keyring, exclusive durable state and an operator-provisioned Comet trust
anchor before opening the listener. The proof routes themselves remain readable
when that permit subsequently expires. They invoke no signing, broadcast,
reservation, credit or journal update. Existing reconciliation routes can record
authenticated journal outcomes and cannot initiate another transfer.

All POST routes require `application/json`, exact case-sensitive fields, no
unknown/duplicate/aliased fields, no URL query or compressed body, and the
existing 16 KiB request cap. Existing transport timeouts, cancellation and
concurrency limits apply. Proof collection additionally retains C3's bounded
responses and Comet provider budgets. The response cap is
`MaxFinancialProofBytes = MaxPortableProofBytes + 64 KiB`; the portable proof
limit is 14 MiB plus 128 KiB framing, at most 80 bounded transcript responses.

The additional `GET /satchel/v1/custody/journal` route exports a bounded,
consistent local execution-history checkpoint for reconciliation. It does not
export the app ledger or authenticate a bank balance. Its bank, credit and
solvency authorization flags are always false and custody remains UNAVAILABLE;
see the [operator contract](war-satchel-mainnet-execution.md).

## Read-only proof requests

`POST /satchel/v1/proofs/deposit` accepts exactly:

```json
{"protocol":1,"owner_id":"HD-durable-owner","sender":"<owner wolo address>","amount_uwolo":"1000000","memo":"<immutable HD deposit memo>","created_at":"<RFC3339 timestamp>","expires_at":"<RFC3339 timestamp>","tx_hash":"<64 uppercase hex>"}
```

HD must obtain these fields from its persisted immutable intent and persisted
candidate transaction hash. The vault, chain (`wolo-1`), denomination (`uwolo`),
RPC/REST sources and trust anchor derive from operator/server configuration.
The intent has the existing maximum 30-minute admission window. Fractional
timestamps are preserved. A proof lookup never creates or consumes an intent.
Late/expired, wrong-owner/sender/recipient/memo/amount/chain/denom, failed, pending,
ambiguous or untrusted observations cannot become a credit.

`POST /satchel/v1/proofs/operation` accepts only
`{"operation_id":"satchel:withdrawal:<UUID>"}` (or a funded ticket operation).
The exact owner, transfer, accepted signature, memo and transaction hash come
from the existing journal. Caller-selected hashes/destinations are forbidden.
The actual authenticated bytes must equal the exact persisted signed bytes.
Ownerless historical wager records return `operation_owner_binding_unavailable`;
new HD wager requests must supply `owner_id` in the existing snake-case one-shot
request (`ownerId` in its camel-case form). This optional owner field does not
change the existing product caps or authorize another owner to spend funds.

`POST /satchel/v1/proofs/return` accepts only `{"claim_id":"101"}`.
It requires an already prepared, v2-authorized and durably reconciled return.
The owner, claim, allocation, ticket/market/leg/entitlement and physical hash
derive from that journal record. It cannot substitute an allocation revision,
funding transaction or new return hash. Founder claim **#889** is forbidden.

The envelope contains `protocol:1`, `chain_id`, `denom`, `context`,
`context_digest`, `tx_hash`, `receipt_id`, `transfer_index`, `message_index:0`,
`height`, `block_hash`, `consensus_authenticated:true`,
`credit_authorized:false`, and `proof`. These flags are transport statements,
not independent authentication. A fabricated envelope with matching hashes is
rejected by independent verification.

The context contains `protocol`, `kind` (`deposit`, `wager`, `withdrawal`, or
`claim_return`), `owner_id`, `sender`, `recipient`, `amount_uwolo`, `memo`, and
the **independently expected** `tx_hash`. Operations also include `operation_id`.
Deposits include original `created_at`/`expires_at` text. Withdrawals include
`withdrawal_approval` and `owner_mandate`. Returns include the original signed
`return_approval` and `funded_amount_uwolo` from the authenticated funded ticket.
HD must reconstruct the full expected context from its own durable records,
including original signed approvals, rather than adopting `response.context`.
`context_digest` is SHA-256 of Go's fixed-field-order context JSON; the pinned
verifier computes it, so clients need not implement another canonicalizer.

## Independent verification

The portable proof is v1 JSON containing only `version`, `chain_id`, `kind`
(`deposit` or `transfer`), `tx_hash`, and `responses`. Each response contains
`source` (`primary`, `rest`, `witness`), `path`, canonical `query`, and raw JSON
`body`. It contains **no trust anchor or source URL**. Its transcript is
untrusted input. `satchel.NewProofVerifier(operatorAnchor)` replays the existing
bounded parsers and actual CometBFT light client against operator-pinned trust,
with no network access or fallback. It verifies transaction inclusion, exact
bytes/hash, committed success/result commitment, signed blocks, chain identity,
fresh heads and corroboration. Cosmos' legitimate omitted zero code is accepted
only with the rest of that committed proof intact. Event attributes are not
Comet's deterministic execution-result commitment: the economic proof is the
exact single decoded bank MsgSend and committed successful SDK execution.

HD can use the composed, exact-source-verified binary as a separate offline
verification process, with fixed argv and no shell:

```text
wolosatcheld verify-financial-proof --authority /operator/public-authority.json --expected /hd/private/durable-expected-context.json --proof /hd/private/untrusted-export.json
```

All paths must be absolute, regular files, non-symlinks and not group/world
writable. Authority/context are capped at 64 KiB, proof at the envelope limit;
all reads are bounded and stable-file checked. The command returns before
normal service startup. It opens no listener, journal, keyring, activation
config or network connection. Authority JSON has exactly `trust_anchor`
(`height`, `hash`, `period_seconds`, `evidence_reference`), `vault`,
`betting_escrow`, and `approval_public_key_hex` (independent Ed25519 reviewer).
These public values must be provisioned independently of the proof/exporter.
Freshness uses the verifier's actual clock; no caller `--now` escape exists.

Success is exit 0 and one `VerifiedFinancialReceipt` JSON object bound to the
expected owner, kind, operation, context digest, exact hash and committed block.
It remains NONCREDITING. Failure is exit 2, no receipt on stdout, and a bounded
UNVERIFIABLE diagnostic. HTTP chain failures retain typed reasons such as
`stale_head`, `untrusted_consensus_anchor`, `transaction_mismatch`,
`execution_failed`, `ambiguous_transfers`, `source_unavailable`,
`inconsistent_observations`, `timed_out`, and `canceled`. They never imply a
retry, principal release or proven failure of an uncertain broadcast.

RPC/REST agreement and two transcript source labels do not establish independent
operator control. Comet authentication rests on the independently reviewed
initial checkpoint/validator trust, bounded trusting period, actual signatures
and provisioned witness. Missing/stale trust cannot be replaced by a flag or
an anchor supplied in the response.

## Withdrawal authorization, execution and recovery

Retain `POST /v1/satchel/withdrawals` on the same 8094 listener. Its protocol-1
request is the published `withdrawal_request` fixture, including `operation_id`,
`chain_id`, `from_address`, `to_address`, `amount:{denom,amount}`, `memo`,
`owner_id`, `approval`, and now mandatory `owner_mandate`.

`owner_mandate` contains `challenge:{id,owner_uid,wallet_address,amount_uwolo,
issued_at_utc,expires_at_utc}`, `pub_key:{type,value}`, and `signature`. The
exact HD withdrawal challenge text is reproduced by `WithdrawalChallengeText`;
original ISO timestamps are signed without truncating fractional seconds.
ADR-36 uses canonical sorted Amino JSON, empty chain/account/sequence/memo,
fee `{amount:[],gas:"0"}`, and one `sign/MsgSignData` with owner wallet and
base64 UTF-8 text. The Go backend checks canonical base64, a compressed
secp256k1 key, derived canonical `wolo` wallet and the 64-byte signature. Login
and auto-bet signatures do not authorize withdrawal. Challenge owner, receiving
wallet, amount and ID must agree with the independently reviewed approval and
durable operation. The maximum challenge lifetime remains five minutes.

The independent approval retains the existing `ApprovalMessage` ordered JSON
array and Ed25519 key, domain `aoe2war/satchel/withdraw-approval/v1`. Its new
`reservation_digest` identifies HD's independently reviewed durable unreserved
balance hold. `OwnerMandateDigest` is SHA-256 of the ordered array shown in the
fixture; `hold_digest` must equal SHA-256 of
`["aoe2war/satchel/withdraw-hold/v1",reservation_digest,owner_mandate_digest]`.
Thus the existing independent signature binds the actual owner mandate and
reviewed hold. A digest still does not prove the ledger reservation exists: HD
and the independent reviewer must establish that fact before signing.

Owner consent and independent approval are checked before durable admission,
again after account/head I/O immediately before native signing, and immediately
before first broadcast after signed-byte persistence. Expiry after signing
retains an UNKNOWN fenced operation and cannot authorize re-signing, automatic
rebroadcast, a new sequence, cancellation or hold release. The activation permit
is also rechecked after trust I/O and before signing/broadcast. Safe retries of
the same durable request return its existing state after expiry; read-only
reconciliation validates its original signed bytes. Old journal records remain
recoverable without being silently granted new owner authority.

## Signed v2 settlement and refunds

The existing `/satchel/v1/returns/prepare` accepts the complete signed v2
`ReturnApproval`; it atomically reserves its entitlement and shared reviewed
funds budget before returning the existing escrow `/settlement/v1/runs` request.
Only separately protected 8092 escrow authority may execute that run. 8094 has
no escrow key or execution credential. `/satchel/v1/returns/reconcile` accepts
`{approval,tx_hash}` and durably consumes its authenticated physical transaction.
Its scalar receipt alone is insufficient for HD credit; obtain and independently
verify `/proofs/return` against HD's original expected allocation/context.

`AllocationMessage` is the existing ordered-array domain
`aoe2war/satchel/return-allocation/v2`; its digest excludes review times and
signature. The signed plan binds chain/denom, escrow/vault, allocation ID and
revision, original operation/owner/ticket/funding hash, total return cap,
shared funds-budget identity/availability, bank-review digest/height/block and
sorted legs/entitlements. `ReturnApprovalMessage` binds the exact claim,
owner/ticket/market/leg/entitlement, kind, amount and allocation digest under
`aoe2war/satchel/claim-return-approval/v2`. Both use the already configured
independent Ed25519 review authority. Allocation renewal/revision cannot
rewrite existing economics or consume another owner's reserve.

The journal and offline verifier reuse the same allocation arithmetic: exact
ticket stake partition; unique sorted legs/markets/entitlements/claims; bounded
principal; aggregate returns within reviewed cap and shared available budget;
each `bet_refund` equals its full unmatched principal. Partial unmatched
principal returns in full and incurs no 2% deduction. A signed plan does not
create solvency or prove the bank/liability review's completeness. HD must use
the already verified funded ticket amount and original reviewed plan.

## Durable HD admission and remaining gates

Before any ledger credit/debit, HD must atomically consume **physical
`(wolo-1, uppercase tx_hash)` globally across every financial lane**, plus its
own immutable intent/claim/withdrawal idempotency key. `message_index:0` denotes
the single decoded bank message. `transfer_index`/old `receipt_id` preserve
journal compatibility; fee/event ordinals are auxiliary and must never create
another credit namespace. A deposit, return, withdrawal and manual betting
consumer cannot each claim the same transaction. Verification stores no global
receipt and cannot replace that ledger transaction.

HD retains ownership of player linkage, ADR-36 auto-bet scope/expiry/revocation,
game participation, available/reserved balances, concurrency, product caps,
seven-migration admission and the permanent financial hold. The Wolo service
does not increase spending caps. Independently provisioned vault/signer role,
unencumbered reserves, complete legacy/Satchel liabilities, current trust anchor
and witness control, exclusive journal ownership, protected release and recovery
authority remain operator gates. Preserve 8092/8093 separation and founder #889.
No deposit, withdrawal, credit, broadcast or production activation is authorized
by this source contract or its fixtures.

## Reviewable fixtures and tests

`internal/satchelservice/testdata/financial-bridge-v1.json` publishes test-only
public keys, canonical challenge/signing bytes, owner consent, existing
withdrawal approval/hold, v2 allocation and return signatures, and exact request
schemas. It has no mainnet authority. Go pins source-to-fixture equality;
`node scripts/check-satchel-financial-bridge-fixture.mjs` independently verifies
the HD text, secp256k1/Ed25519 signatures, ordered arrays and tamper rejection.
Core isolated SDK execution tests execute a real signed bank transfer with ante
fee, then authenticate its bytes/results with validator-signed Comet headers
and verify the portable transcript. These isolated fixture validators are
explicit test trust, not evidence of mainnet validator or custody readiness.

`PYTHONDONTWRITEBYTECODE=1 python3 scripts/check-satchel-financial-proof-roundtrip.py`
builds the verifier before exporting a fresh real SDK execution fixture, verifies
its financial proof through the actual offline CLI with actual-clock freshness,
checks identical read-only receipt identity on repeat verification, and rejects
wrong expected hash/owner, wrong checkpoint and fabricated REST-only evidence.
It creates only temporary isolated test files and never contacts production.

## Automatic reviewer economics source contract (October 19, 2026)

The first automatic-reviewer source milestone is `internal/satchelservice/reviewer_fee_budget.go`, with adversarial tests in `reviewer_fee_budget_test.go`. This is a deliberately **pure, NONAUTHORIZING prerequisite**, corresponding to the app-side held `warSatchelFeeHeadroom.ts`. It binds a proposed ticket operation and its exact signed-protocol fee to bounded integer arithmetic: all owner liability principal + the possible gas of every prepared/uncertain operation + the prospective wager gas + an unencumbered operating-gas cushion must fit inside the observed bank amount.

The arithmetic refuses wrong chain/denomination/operation, mismatched fee, duplicate or invalid pending operation IDs, bad/capped/overflowing integers and oversized pending lists. UNKNOWN stays gas-reserved. A declared incomplete census returns `CENSUS_INCOMPLETE`; apparently sufficient sums return only `BUDGET_SUFFICIENT_NONAUTHORIZING`, with `SpendingAuthorized=false`, `BankAuthenticated=false` and `OwnerLedgerAuthenticated=false` **always**. A caller saying `PendingOperationsComplete=true` does not authenticate its inventory or guarantee completeness. Neither the result nor the supplied bank number can authorize a reviewer signature.

**Remaining functional work:** independently authenticated owner mandate, immutable HD reservation, canonical Watcher market/identity, custody bank and all HD/DE/external financial liabilities; completeness proof for competing signer operations; independently controlled Ed25519 approval service with durable idempotent issuance and atomic ingestion; and isolated end-to-end reviewer→8094→escrow→return/withdraw tests. The pure arithmetic has no signer key, RPC, database, transport, side effects or live activation. All mainnet financial and protected release controls remain held. See WoloChain issue #46 for the complete reviewer integration gate and issue #5 for legacy financial-release HOLD.

## Independent 8095 reviewer issuer core — source milestone, NOT production authority

`internal/satchelservice/reviewer_issuer.go` and `reviewer_http.go`
implement the separately controlled reviewer's **internal approval engine**
and fixed-loopback HTTP contract. It accepts only an authenticated
`POST /reviewer/v1/wagers` containing `{"protocol":1,"operation_id":"satchel:ticket:…"}`,
never a client-provided hold, bank balance, key, destination, fee, approval
or proposed stake. The original exact owner-bound financial reservation
must come from the independent `ReviewerEvidenceSource.OriginalHold` adapter.
Separate `VerifyOwnerMandate`, `VerifyWatcherMarket` and
`AuthenticatedFeeCensus` adapters must establish all upstream evidence
independently. The gas assessment binds the original wager's exact fee and
operation to all owner liabilities and pending/uncertain operations. The
reviewer signs only `WagerReservationMessage` with a distinct Ed25519
review key, never the Satchel Cosmos custody key. On the wire, this exactly
matches the app's PR #708 signed-approval pickup: PENDING or SIGNED with
an owner-bound, 60-second signed reservation.

A separate private bbolt journal durably fences the original
operation-and-economics fingerprint **before signing**. It never signs again
after a crash on PENDING, never renews expired approvals, and never reveals
a cached grant if the independent source ceases to verify or its economics
change. Crash/uncertainty needs separate witnessed reconciliation, not a
retry. The bounded loopback transport authenticates a private bearer and
refuses duplicate JSON keys, unexpected fields, nonloopback callers,
oversize bodies and arbitrary destinations. The app and the reviewer
must run under distinct private OS identities with separately protected keys.

**NOT YET IMPLEMENTED / RELEASED:** There is deliberately **no**
production-wired `ReviewerEvidenceSource` adapter, independent read-only HD
database principal, authentic Comet bank/liabilities trust reader,
complete external-producer census, operator-managed Ed25519 key deployment,
independently attested daemon configuration/startup, activation permit
or production systemd service for 8095. Tests inject synthetic adapters;
they are not proof of operational source independence. The library is
not wired into `cmd/wolosatcheld` or any chain/consensus service, and cannot
start an authorization listener by itself. Only separately reviewed
authentic evidence adapters and release authority may make it live.

This source does not change the protected Wolo financial HOLD (#5), founder
claim #889, 8092/8093 settlement, Satchel 8094 custody,
`SATCHEL_FINANCIAL_BRIDGE_READY=false`, operator approvals or real funds.

## Independently verified Keplr ADR-36 consent (October 19, 2026)

The held 8095 reviewer now has a **real Go secp256k1 owner-mandate
verification primitive** in `internal/satchelservice/reviewer_owner_mandate.go`
with source tests. It rebuilds the exact HD/CosmJS challenge text from
the original persisted owner UID, wallet, preset/version, per-game stake,
daily and per-game ceilings, finite-games/until-out allowance, nonce,
and issue/expiry dates. It reconstructs CosmJS's canonical
`makeSignDoc`/`serializeSignDoc` for `sign/MsgSignData`, verifies the
original 64-byte Keplr ADR-36 signature against the compressed
secp256k1 public key and its derived `wolo` address, and binds the
record to *current* owner and preset state. Revocation, expiry, late
signing, a changed wallet/stake/nonce, increasing finite allowance, an
unbounded cap or forged challenge all refuse verification.

A `signedAt` field, a correct hash, or a service bearer is NOT a
signature. The method always returns only an error/non-error predicate
and cannot itself authorize an approval or WOLO transfer. It must be fed
original read-only SQL records by the separately governed 8095 evidence
adapter, and the app's immutable reservation/ledger/consent digests
still need exact cross-language recomputation and comparison. Live
database credentials, independent read-only PostgreSQL role, cryptographic
Comet bank/liability/fee census, multi-producer source closure and
protected 8095 service activation do **not** yet exist. The six issue #5
financial controls, unknown chain transactions and founder claim #889
remain held. No production custody keys or transactions are touched.

## HD financial-origin digest agreement — independently implemented (October 19)

The reviewer source now contains
`internal/satchelservice/reviewer_hd_snapshot.go`. It independently
reconstructs the exact TypeScript
`buildSatchelWagerAuthorization` triplet:
`consentDigest`, `ledgerRevision`, and `reservationDigest`, using
bounded, recursive sorted-key JSON and SHA256. The Go tests contain an
independently generated **CosmJS/TypeScript golden vector** for an original
HD wager, rather than comparing two implementations with the same
unknown defect. A source record is rejected for a mismatched DB column
identity/digest, changed owner, vault, escrow, amount, memo, game,
proposition, ticket leg, original owner signature field, extra/duplicate
JSON keys, noninteger economics or unsafe excessive amounts.

This adds *original-source integrity verification*, not evidence that
the HD database writer was independently controlled, that a valid
wallet owner signed it, or that any chain transfer was finalized.
The independent Keplr ADR-36 verifier is a distinct component from
reviewer source PR #49, and the signer's Ed25519 reservation key
remains separate from the player's Cosmos wallet. **Next:** a
read-only, independently governed PostgreSQL adapter must fetch the
original DB columns and verify these hashes AND run the Keplr
signature checker; a separate authenticated Watcher/market adapter,
Comet light-client bank proof, and complete global financial
producer/liability/fee census must approve within a coordinated
atomic reviewer issue step. These verified-source capabilities have
not been activated or deployed. 8092/8093, 8094, 8095 and all
financial HOLDs remain unchanged.

## Independent SELECT-only HD PostgreSQL original-wager reader (source, HELD)

`internal/satchelservice/reviewer_pg_origin.go` is the first
**real SQL source adapter** for the separate 8095 reviewer. It opens
a repeatable-read READ ONLY PostgreSQL transaction as a required
`satchel_reviewer_*` account, pins all source tables to the literal `public` schema, checks `current_user`,
`transaction_read_only=on`, nonprivileged role flags, and **absence
of financial table INSERT/UPDATE/DELETE privileges**. It executes
only a fixed parameterized original operation query; the remote
caller supplies no SQL, amount, bank claim, key or wallet identity.

The original wager row is joined, at the same SQL snapshot, against
the existing funded reservation, Watcher execution, player preset,
original owner/wallet, provisional stake ticket and owner reserved
balance. The result must agree with the independently recomputed
three hashes of the immutable HD authorization, and with canonical
ticket, amount, memo, game identity, proposition, profile/version,
and vault/escrow. Any altered owner, market, state, already-broadcast
ticket, insufficient original reserved amount, expired four-minute
game or unattempted-holder mismatch refuses. Every source read is
bounded and never writes application or chain state.

**Still financially incomplete:** the adapter now implements
`OriginalHold` **and** `VerifyOwnerMandate` with a separate
repeatable-read, SELECT-only PostgreSQL query. It re-reads the
original consent row, original mandate signature bytes and current
enabled owner preset; matches the persisted challenge and signature
JSON against the original cryptographically hashed source; and
independently reconstructs and verifies the real Keplr ADR-36
secp256k1 signature. A changed wallet, disabled or revoked mandate,
increased future game allowance, altered stake/preset, missing or
wrong public key, expired signature, or changed original digest
returns `ErrReviewerHeld`.

**HARD HOLD remains:** `VerifyWatcherMarket` and
`AuthenticatedFeeCensus` still always refuse. Signed Watcher/Steam
source attribution, Comet-authenticated bank, complete global
liability/pending-gas producer census, provenance, reviewer
private-key provisioning, live credentials and protected
transaction-wide financial coordination are not established. No
8095 service, PostgreSQL role, database changes, wallet signer,
consensus operation or WOLO movement was activated. The reviewer
**cannot issue any approval** until those remaining checks are
independently implemented, wired and certified.

## Watcher market source boundary — actual shadow producer, still NOT independent approval

`internal/satchelservice/reviewer_watcher_market.go` implements a
bounded READ-ONLY diagnostic query for the original live Watcher market.
The source is the **actual** 17-field shadow producer from app
`lib/betAutomationShadowWorker.ts`, not a fabricated 7-field test
fixture. It cross-checks winner market ID, original HD game and
proposition identities, exact user Steam ID, verified roster-match flags,
team resolution/high confidence, parse iteration, original source
roster hash, canonical and linked session identities, and roster-lock
timestamp against the current market row and original immutable stake
leg. It refuses scheduled, settled, refunded, voided, late/final-stat,
cutoff-passed, future, reordered, and older-than-four-minutes games.
A strict 17-key JSON evidence record also rejects data injected
outside the canonical shadow-source schema.

**Authority distinction:** a web application's `integrity_status`
database column, even if `verified`, is NOT an independently
authenticated Watcher or Steam event. The source exports only
`InspectWatcherMarket` as an observation method; its actual
`VerifyWatcherMarket` spending-approval method continues to
return `ErrReviewerHeld` without exception. The separate Watcher
provenance signature, independent raw replay/archive reader,
attested game/roster/source origin and trustworthy issuer-key boundary
remain to be wired before approving customer WOLO. The
`AuthenticatedFeeCensus` bank/liability/gas evidence method is
also still hard held. No 8095 listener, DB credential, treasury,
signer, wallet, consensus, balances or production setting changed.

## Independently signed Watcher replay witness — crypto contract only, HARD HOLD

`internal/satchelservice/reviewer_watcher_witness.go` defines the
first **Ed25519-authenticated Watcher observation receipt**. It signs
a fixed, domain-separated ordered message bound to `wolo-1` and the
original operation ID, exact owner UID/Steam ID, game identity,
winner market and selected side, proposition, linked session,
parse iteration, exact source roster hash and roster-lock time,
execution created time, an independently computed SHA256 of the
**raw replay**, and a maximum 60-second issuer interval.

The strict verifier takes a separately provisioned witness public
key, the unchanged `ReviewerWatcherCandidate` read from the
restricted PostgreSQL role, and a digest provided by a genuinely
**independent, source-pinned raw replay reader**. A signed response
cannot substitute the owner, market, game, roster, source parsing,
original source digest or timestamp without rejection. Synthetic
test signing keys and forged receipts prove validation semantics
but are not production Watcher trust roots.

**This is NOT yet real event authentication.** No independently
governed Watcher witness signing daemon, root-trusted raw replay
reader, user/Steam roster verification, approved signing key,
raw replay provenance ledger or external digest source has been
installed or attested. A caller who copies a digest from the
app database or a self-reported HTTP body cannot satisfy the
required trust boundary, regardless of whether the hash matches.
Therefore `ReviewerReadOnlyPGSource.VerifyWatcherMarket` remains
unconditionally `ErrReviewerHeld`; this uncalled primitive
**does not issue approvals or activate the watcher**. Global
`AuthenticatedFeeCensus` and authenticated CometBFT bank/gas
liability checks also remain hard-held. No 8095 / 8094 service,
systemd unit, app release, Wolo node, private production key,
balance, consensus or transaction was touched.

## Separate Wager and Withdrawal approval roots — source-only preproduction correction

The 8094 signer previously used `WithdrawalApprovalKey` to verify both
owner-withdrawal approvals and autonomous wager reviews. The two messages
were domain-separated, but relying on the same Ed25519 key unnecessarily
joined two financially distinct responsibilities.

**The held signer now requires three different keys, not one:**
`activation_authority_key_hex` (operator release permit),
`withdrawal_approval_key_hex` (one-use owner-withdrawal approval), and
**`wager_approval_key_hex`** (automatic wager reviewer grant).
Config loading rejects absent, malformed, or equal keys across all
three roles. Wager signatures are verified **only** with the wager
public key; withdrawal approval signatures **only** with the
withdrawal public key. The 8095 reviewer refuses to open unless
the private approval key it holds derives the pinned wager key and
that key differs from the withdrawal approval key. The 8094
runtime policy copies both keys and refuses a role collision.
Synthetic regression tests prove each role cannot substitute
for the other; a missing wager key cannot fall back to withdrawals.
The historical **withdrawal, claim-return and allocation** signing fixture
remains bit-identical, while the isolated wager-only Ed25519 golden fixture
was independently regenerated from its unchanged exact sign bytes.

**Operational consequence:** this changes the protected signer
configuration contract and requires independently provisioned,
distinct production roles and a new source/config-bound permit.
There is no existing 8094 production signer to hot-swap, and
none is installed here. Do **not** copy or repurpose an existing
withdrawal key as the automatic wager key. A source-green PR
does not authorize Wolo deposits, game wagering, withdrawals,
recovery or treasury actions. 8095 bank/Watcher trust and the
six financial-release controls remain HOLD. No keys were generated
on a production machine or placed into GitHub.

## Final reviewer evidence-revalidation fence (October 19)

The held 8095 `ReviewerIssuer.ReviewOne` now **revalidates the original
financial hold, signed owner mandate, live Watcher market, and complete
fee/bank census after the initial evidence sequence**, immediately before
writing its durable PENDING intent and performing any Ed25519 approval
signature. It demands the same original immutable operation fingerprint,
zero provisional issuer timestamps, exact signer vault and escrow, and
a second independently verified `BUDGET_SUFFICIENT_NONAUTHORIZING`
arithmetic result. A changed source during the first fee-census read
refuses rather than signing a stale earlier observation. An already
SIGNED grant is still returned only under fresh source verification
and the existing immutable same-signature + expiration fence.

Adversarial tests force owner revocation, market closure, a changed
reservation digest, rebinding of owner UID, bank-gas headroom loss,
and incomplete producer inventory **between** the initial and final
evidence reads. Each case refuses without even writing a new durable
signing intent. On a stable source, the tests require two independent
source reads and fee-census passes and prohibit reissuance after a
revocation.

**This is necessary but not sufficient for real spending safety.**
Repeated reads are not a single cross-system atomic snapshot and
cannot prove solvency or authenticity. Live reviewer operation
requires an independently governed, bounded bank/liability/fee
checkpoint and real Watcher replay trust root, plus source freshness
through signing/broadcast. The current PG evidence source still
unconditionally refuses `VerifyWatcherMarket` and
`AuthenticatedFeeCensus`. These controls do NOT activate customer
WOLO, deploy 8095/8094, provision keys or clear Wolo issue #5.

## Live-game Watcher v2 receipt + frozen pre-bet source bytes (held)

**IMPORTANT product timing:** Auto Betting must fire DURING the next
Watcher-detected Age of Empires II match. The existing content-addressed
`aoe2-replay-archive` stores the final replay and is **post-game**
evidence. Requiring that final replay before a wager would prevent the
minimum viable product from working. The earlier
`ReviewerWatcherWitness` v1 `raw_replay_sha256` signature stays
available for post-game audits only; it must not grant pre-bet authority.

`internal/satchelservice/reviewer_watcher_live_witness.go` introduces
a new **separately domain-separated v2** Ed25519 signed receipt for a
frozen **live game-start checkpoint**. It binds exact original operation,
Steam user, game/market/side/proposition, source roster hash, parse
iteration and roster-lock time, signed checkpoint SHA256, capture and
observation timestamps, and a maximum 60-second receipt TTL.
Capture and observation must occur within the first 120 seconds after
the original admitted live execution and not precede roster-lock time.
A final replay captured only after the match ends is NOT eligible.

`reviewer_watcher_replay_bridge.go` implements
`ReviewerSignedLiveWatcherReader` and
`ReviewerIndependentLiveCheckpointReader`. The reviewer does **not**
accept a caller-provided hash. It computes SHA256 itself over the
frozen game-start bytes, strictly bounded to 64 MiB, and verifies
the separate pinned v2 signature against the read-only original
market/Steam source. Empty, corrupt, oversized, unreadable or
unfinalized checkpoints, forged receipts, cross-version v1 signatures
and late-final evidence refuse. The original market is re-read
after verification and must remain unchanged.

**Not live, not independently attested:** the interface providers
are synthetic in source tests. There is no separately administered
frozen live-checkpoint producer, independent signing key or OS role,
Steam/game-start trust audit, or signed receipt serving operation
yet. A screenshot, HD database flag, final replay, old legacy
Watcher receipt or self-reported API hash cannot substitute.
The inherited independent `AuthenticatedFeeCensus` method STILL
unconditionally returns `ErrReviewerHeld`. Bank, all liabilities,
pending gas, global producers and the Wolo issue #5 controls
remain HOLD. Nothing has been installed on the app, replay API,
8094/8095, settlement processes or consensus.
