---
id: "aoe2war.wolochain.new-epoch-escrow-v3-held"
title: "Held native new-epoch escrow v3 decision boundary"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["developers", "operators", "ai-agents"]
source_of_truth: "git"
authority: "source-review-only-nonactivating-escrow-candidate"
reviewed_at: "2026-10-26"
review_interval_days: 7
sensitivity: "internal"
---

# Held native new-epoch escrow v3 decision boundary

**NO-GO for financial execution.** `internal/epochescrow` supplies actual Go
policy, economic validation, native portable-proof verification and durable
unsigned decision source. `ProductionEnabled` is a constant false value;
`Journal.Execute` returns `NEW_ESCROW_SIGNER_ABSENT`. No exported API opens a
keyring, signs, broadcasts, credits HD, or invokes 8092/8093. This source is the
bounded policy/journal work packet; independent runtime custody and a complete
financial executor are unfinished.

The October 28 source correction evaluates bank currentness after both portable
proof replays and revalidates the owner permit at that completion time. Replay
observations must not be evaluated against an earlier admission timestamp.
Fixed refusal stages distinguish funding, account authentication/currentness,
account-root agreement, funding lag and signed-request-root disagreement without
printing native replies or credentials. The native SDK test checks the earlier
clock refusal, completion-time acceptance and unchanged stale/future limits.

The exact upstream contract is HD
[`docs/FINANCIAL_EPOCH_V3_WOLO_EXECUTOR_INTERFACE.md` at bde1a40808b661b4fbd257353d71b4700d52ed81](https://github.com/Emaren/app-prodn/blob/bde1a40808b661b4fbd257353d71b4700d52ed81/docs/FINANCIAL_EPOCH_V3_WOLO_EXECUTOR_INTERFACE.md),
blob `463dba3119acd03b67d40c83136cd51b58ba6aae`. Its pure economic source is
[`lib/warSatchelNewEpochFinancialContracts.ts`](https://github.com/Emaren/app-prodn/blob/bde1a40808b661b4fbd257353d71b4700d52ed81/lib/warSatchelNewEpochFinancialContracts.ts),
which reuses the canonical HD `betWagerSettlement.ts` planner. Neither those HD
candidates nor this Wolo candidate is connected to production financial paths.
The [documentation index](DOCUMENTATION_CONTROL_PLANE.md) records the exact
implementation baseline for this branch.

## Implemented source contracts

- `policy.go`: distinct address/public-key binding, protected runtime/keyring
  inventories, canonical v3 operation/entitlement/memo identities, original
  owner UID and wallet, original mandate and resolution evidence digests,
  explicit epoch/h-star and exact H/H+1 bank root, source/binary/config/policy identity, expiry, reviewer
  permit and nonce. Original owner secp256k1 and separate reviewer Ed25519
  signatures bind the complete immutable request under
  `aoe2war/escrow-epoch/v3`. These keys represent actual roles; their existence
  does not imply multiple human operators or independent custody.
- `economics.go`: canonical sorted wager IDs, exact native whole-WOLO units,
  real opposite-side matching, largest remainder allocation by remainder,
  stake and wager ID (including the existing JavaScript IEEE-754 remainder ordering), whole-WOLO positive rounding of the 2% matched-volume
  fee, exact void refunds and unmatched principal. A fee requires its separate
  execute command, economic identity, amount, memo and allowlisted destination.
  Zero-return/zero-fee outcomes cannot initiate native transfers.
- `evidence.go`: the existing `satchel.ProofVerifier` authenticates every
  unique original funding MsgSend against the protected Comet trust root, the exact
  vault-to-escrow epoch memo and message ordinal zero. Both account-local bank
  proofs must be current and committed at the same H/H+1 root. Each account
  independently covers liabilities, finite unknown outflows, positive gas and
  operating reserves; escrow additionally covers the exact debit and native
  gas fee. An opaque verified preparation is required before journal admission.
- `journal.go`: private bbolt file and exclusive lock, synchronous transactions,
  parent directory fsync, immutable decisions, append-only hash-chained events,
  market/funding/entitlement/local nonce indexes, fingerprint-bound lookup and
  durable `UNKNOWN_NO_REPLAY` quarantine. Original events and financial holds
  remain after expiry/restart. Capacity refusal rolls back the complete mutation so older decisions remain readable, while reserved event/byte headroom always retains one future uncertainty transition per prepared decision. Missing events, indexes, altered signatures and
  policy drift refuse recovery. This is local corruption detection; a restored
  complete older database still requires an independent checkpoint witness.

`woloescrowd -config /absolute/private/policy.json -check` only checks protected
JSON structure and policy identity. Success prints `STRUCTURAL_REVIEW_ONLY`
and false signing/broadcast flags. Without `-check`, the command exits held;
there is no enable flag, private listener, signer credential or keyring path.
The example config intentionally fails validation until operator provisioning.
The example service is an uninstalled held source boundary and exits without
opening a signer. A different UID or configured lineage digest is an assertion,
not a custody certificate.

## Wire and accounting limits

`RequestMessage` is the exported canonical signing-byte function: an ordered
JSON array containing the protocol domain and the complete typed request with
both signature fields empty. Amounts are canonical decimal strings; no maps
occur in the signed request. HD must use these exact bytes and a separately
reviewed original owner mandate. This is a held future wire candidate, not a
change to the existing 8094 bearer client; no 8194/HMAC adapter is introduced.

The original operation is `satchel:e3:<epoch>:<ticket>`. Entitlements are
`satchel:e3:<epoch>:entitlement:<market>:<ticket>:<leg>`. This candidate suffixes
`:return` or `:fee` for their distinct immutable execution decisions. Native
physical identity is exactly `(wolo-1, uppercase tx hash, message index 0)`.
No legacy claim ID or old return memo can enter this namespace.

The HD #940 ticket contract at `b7e07645e057340de051c5ffa78001ebc939191e`
uses one original receipt with a complete conserved allocation. `OriginalTicket`
now binds its epoch, owner UID/wallet/key, ticket, MsgSend0 receipt, full physical
principal and 1–16 canonical market legs. The original owner signs
`OriginalTicketMessage`: protocol, original-ticket domain, chain, denom, actual
vault/escrow, exact funding memo and the unsigned typed ticket. Its SHA-256 is
the selected request's original mandate digest. The current owner/reviewer
request signatures additionally bind all included certificates and market truth.
All allocations sum exactly to the authenticated original principal; every
known current-market leg must occur in the plan. Each unique receipt is verified
once against its full amount, regardless of the number of economic legs.

Journal admission atomically pins the receipt, original ticket, owner mapping
and every allocation (including future markets) to the immutable partition.
History verification checks those same pins after restart. Conflicting
partitions remain `RETURN_ENTITLEMENT_COLLISION`; identical receipt use by a
different legal market preserves the original uncertainty fence. HD's existing
atomic ledger remains the global receipt-consumption authority. No local journal
claim certifies cross-system consumption, completeness of liabilities or real HD
owner enrollment. Old held records without an original-ticket certificate are
not migrated or repaired by this source.

`ObserveReturn` verifies a native exact return effect and remains noncrediting.
It does not consume HD's global physical receipt or authenticate a later bank
snapshot for an HD credit. The separate native `VerifyMessageTransferProof` API retains the complete
SDK bank event list and legacy event ordinal (the ante fee precedes the send),
while its authenticated exact single MsgSend has canonical message index zero.
The existing `ReadTransfer` API and event-ordinal identities are unchanged.
Current full native bank proof admission is in
`VerifyPreparation`; a future observe response needs the independently
consumed latest H/H+1 bank commitment and economic ownership tuple. Native
proof authentication cannot prove the truth or completeness of a signed
liability inventory, original owner mapping or market resolution.

## Remaining P0 implementation and provisioning

1. Implement an independently reviewed `SOLO_CUSTODY_ESCROW v1` runtime actor
   architecture with actual escrow public-key/account binding, separate OS
   principal, protected SDK keyring lineage, mount/ACL and credential exclusion,
   separate installed policy and binary/config witness. Explicitly exclude
   old 8092/8093, vault, DE, HD legacy and external generic writers. Provisioning
   is an operator action; source cannot create or counterfeit the evidence.
2. Enroll the escrow-specific off-host durable nonce authority and append-only
   checkpoint witness. The present local nonce index prevents source replay;
   it is never treated as off-host signing authority. No old maintenance nonce
   or settlement journal can substitute for this domain.
3. Compose the existing `satchelservice.KeyringBackend` SDK signing machinery
   behind a strict new escrow role, dedicated private interface and operation
   grant. Preserve existing vault/legacy role behavior. Persist and fsync
   `ATTEMPT_FENCED` before the signer call and signed bytes before broadcast;
   implement native confirmation and source-bound revocation. Every post-sign
   ambiguity must stay `UNKNOWN_NO_REPLAY`. No such path is exported yet.
4. Authenticate original market truth, owner mandate and source-complete
   account-local liabilities; integrate the conserved ticket
   partitions with HD global physical receipt consumption and read-only lookup/
   observe integration. Preserve historic 889, 8477, original 100-WOLO ambiguity,
   reused hashes, legacy HD/DE claims and all uncertain outgoing payments in
   their existing protected domain.
5. Complete actual escrow signer execution and crash/timeout tests, immutable
   source/binary reproduction, runtime witness,
   full writer exclusion, quiesced backup/restore and exact transaction-specific
   owner permit before requesting a separately approved small real-WOLO canary.

The original policy and journal pin the trust anchor. A future recovery protocol
must separately enroll a current read-only observation root after the original
anchor expires, retaining the immutable original authorization and never
reopening spending authority. Root rotation is not implemented here.

The source does not claim a deployed independent signer, complete lifecycle,
production H/H+1 evidence, complete legacy exclusion, solvency or funded GO.

## Validation

Focused tests cover HD matched/unmatched/void economics and rounding; wrong
chain/epoch/source/owner/leg/ordinal; legacy route, memo and signature domains;
shared runtime/key lineage; account-local deficits; missing native proofs;
concurrent duplicate delivery; immutable fingerprint/nonce decisions;
quarantine and expired lookup after restart; append-only event/index/signature
corruption; expired-original read-only observation, atomic admission expiry/capacity checks, and the unprovisioned execution gate. Disposable private fixture
seals test journal semantics only and are explicitly not native bank proofs.
The existing native SDK/Comet/ICS23 suites remain the underlying evidence
boundary. CI is source verification, never custody certification.

The dedicated `Held epoch v3 native evidence` CI job runs
`scripts/check-epoch-escrow-native-v3.py`: it builds the v3 test binary before
exporting fresh proofs from the existing continuous SDK lifecycle fixture, then
immediately consumes them. Actual fee-paying funding, escrow return and
matched-only fee sends exercise canonical message zero alongside legacy event
one. Both native bank accounts use the same H/H+1 root. Wrong owner, denom,
message ordinal, signed/trusted root, expiry, account-root disagreement and
escrow reserve deficit are rejected. No freshness window or permit TTL is
extended for compilation. The accepted native preparation still cannot execute
because independent runtime custody/off-host nonce authority remains absent.

The native recipe uses a genuine 100-WOLO original transfer allocated 40+60
across markets 77/78, plus a separately owned 40-WOLO counterparty ticket.
It verifies a 78-WOLO matched return, separate 2-WOLO economic fee and 60-WOLO
void return, including the existing whole-WOLO fee rounding. Public golden
evidence contains original transaction/proof bytes, bank commitments, signing
bytes and fingerprints; it excludes fixture private keys. Archived timestamps
are historical evidence, never a renewed current bank proof.

`scripts/check-epoch-escrow-hd940.mts` runs minimal, hash-pinned actual HD #940
TypeScript and SQL sources against that freshly generated evidence and an
isolated PG16 database. Its direct SQL adapter is fixture-only; it does not
activate the held native ingress. HD has no Go signing-byte implementation or
published pinned verifier executable. Its old Wolo source pin, two native-ingest
INSERT arity defects and the zero-payout loser label difference remain explicit
cross-repository mismatches requiring separate HD review. No HD branch, role,
migration, credential or financial enable flag is changed by this candidate.
