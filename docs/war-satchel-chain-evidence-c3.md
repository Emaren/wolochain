---
id: "aoe2war.wolochain.war-satchel-chain-evidence-c3"
title: "War Satchel C3 Chain Evidence"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "git"
authority: "source-only-war-satchel-chain-evidence"
reviewed_at: "2026-10-15"
review_interval_days: 14
sensitivity: "restricted"
---

# War Satchel C3 Chain Evidence

**Every adapter result is NONCREDITING. C2 custody remains UNAVAILABLE.**
This source milestone starts from merged [C2 PR #17](https://github.com/Emaren/wolochain/pull/17),
`7e68f43ac6eba7fdb8036edf1f68ead3838d124f`. It adds bounded network evidence
collection and consistency verification; it establishes no independent Satchel
vault, signer control, consensus trust root, reserve coverage, or credit authority.

## Scope and existing authority

[App #559](https://github.com/Emaren/app-prodn/issues/559) requires exact finalized
funding plus unique durable credit; [#514](https://github.com/Emaren/app-prodn/issues/514)
also requires complete accounting, consent, funded ticket acceptance, refunds,
withdrawals, and independent release evidence. This adapter implements only the
read-only chain-evidence prerequisite. [#600](https://github.com/Emaren/app-prodn/issues/600)
requires owner-bound unique payout proof and preservation of unpaid/ambiguous
claims. An app status row, missing hash, or lookup failure cannot prove payment or
nonpayment. Its [source-policy comment](https://github.com/Emaren/app-prodn/issues/600#issuecomment-6205717106)
also requires the authorized source signer and sender/recipient/denom/amount/
ordinal plus request context; recipient-and-amount allocation is insufficient.
No claim or payout behavior changes here or retrofits claim #889.

The [C2 custody contract](war-satchel-custody-c2.md),
[wallet registry](mainnet-wallets.md), and
[settlement contract](mainnet-settlement-runbook.md) retain authority for signer
roles, exclusions, liabilities, and dated runtime observations. All 23 registered
role addresses are rejected; C2's configured-alias exclusions remain required.
8092/8093 share existing betting escrow despite distinct payout signers. Claim
#889 / Founder bonus #15 remains held with an uncertain attempt. C3 neither
repeats the exhausted founder investigation nor clears any financial hold.
Existing settlement services and the separate consensus executable are unchanged.

Canonical [mainnet metadata](mainnet-keplr-explorer.md) identifies `wolo-1`,
`uwolo`, RPC `https://rpc-mainnet.aoe2war.com`, and REST
`https://rest-mainnet.aoe2war.com`. The documented
[nginx routing](mainnet-dns-nginx-tls.md) maps those hosts and the
`aoe2war.com/rpc-mainnet/` / `rest-mainnet/` aliases to the same node's loopback
RPC `27657` and REST `1318`. Different URLs or RPC versus REST are not independent
consensus authorities. These are source-bound infrastructure observations, not a
new production health or signer-control certification.

## Read-only evidence contract

[`internal/satchel`](../internal/satchel/chain_reader.go) owns `ChainReader`.
`NewChainReader(SourceConfig)` accepts only server-owned RPC, REST, and optional
witness RPC base URLs. `ReadDeposit(ctx, intent, hash)` accepts an immutable C2
intent and transaction hash, never a source URL, transport, asserted head, or
certification flag.
HTTPS is required except literal loopback HTTP; URL credentials, queries,
fragments and redirects are refused. The adapter exposes GET requests only and
no broadcast, signer, keyring, generic RPC, ledger, or persistence operation.

The reader fetches transaction bytes/result, inclusion/following/head commit
headers, block results, and fresh node status. It reuses pinned CometBFT types
and Cosmos protobuf message decoding rather than a parallel transaction protocol.
It verifies the bytes' SHA-256 hash, transaction index and height, block hash,
chain ID, time ordering, and official `TxProof.Validate` inclusion against the
block data hash. The following header must link to the inclusion block and commit
the official `NewResults(...).Hash()` through `LastResultsHash`.

CometBFT commits result **Code, Data, GasWanted, and GasUsed** in that hash.
**Events and Log are excluded**, so a matching result hash does not authenticate
bank event content. Zero execution code must agree between transaction,
block-results and REST observations; omitted Cosmos REST `code` is legitimate
zero serialization, while malformed/nonzero values fail closed. Actual `TxRaw`
bytes decode to exactly one `MsgSend`, one positive `uwolo` coin, and the exact
intent sender, vault, amount and memo. Failed execution or additional effects
cannot produce a usable receipt candidate.

[`internal/chainevents`](../internal/chainevents/transfers.go) extracts the existing
settlement parser without changing its ordering: logs first, comma-split coins in
their original order, top-level events only when logs contain no transfers.
Strict Satchel validation rejects malformed, duplicate-attribute or ambiguous
transfer events before using that shared ordering. Every transfer, including
fees, stays in the ordinal list; no filtering or renumbering is permitted. V1
requires the complete list to contain only the exact deposit at ordinal `0`.
A legitimate transaction with an additional fee transfer is therefore refused
by this conservative contract. Compatibility must be measured on real indexed
transactions before widening it; never invent a second receipt namespace.

The optional witness is queried at fixed inclusion/following/head heights and its own latest height,
must agree on the checked block identities. Different latest heights are not
compared as if they were the same block. Matching witness observations are
corroboration only: configuration cannot assert independent operation or
authenticate a validator commit. Receipt identity remains exact `wolo-1` +
uppercase transaction hash + canonical bank ordinal, globally shared with
existing betting/challenge consumers. Its actual status is retained separately
from the matched historical head; status/commit identity and freshness are checked.

Transport bounds are at most 12 logical GET calls, 8 seconds per read, 3 seconds per request, 1 MiB per
response, 6 MiB aggregate bytes per read, and four concurrent reader calls.
Cancellation propagates; responses are closed; compressed bodies and redirects
are rejected. Strict JSON parsing rejects duplicate keys and malformed payloads.
There is no adapter retry loop: another read fetches fresh bounded observations
and does not consume, credit, or mutate a receipt. Public `EvidenceError` values
carry stable typed failure codes and fixed source/operation labels, never raw
remote payloads, URLs, credentials, or server error text.

## Explicit trust boundary and required next evidence

Successful checks yield `Status() == "NONCREDITING"`,
`ConsensusAuthenticated() == false`, and `CreditAuthorized() == false`, with
`TrustStatus() == "UNTRUSTED_CONSENSUS_ANCHOR"`, with typed
`untrusted_consensus_anchor` and `independent_trust_unavailable` blockers. No pinned
Satchel light-client/verified-commit trust root is established by available
infrastructure. `SignedHeader.ValidateBasic` checks shape/hash binding only.
Self-consistent forged headers and matching aliases can pass
consistency checks. Two endpoints, two equal heads, an environment flag, or source
CI cannot remove these blockers; uncommitted bank events remain an additional
evidence limit. `CurrentCapability()` stays immutable and unavailable.

Before durable real credits, a separately reviewed implementation still needs:

1. A pinned `wolo-1` trust anchor, verified validator-set/commit transitions,
   trusted freshness/expiry policy, and genuinely independently operated,
   authenticated corroboration. Bind inclusion, H+1 execution commitment and
   finalized head to that trust; establish authoritative bank-effect evidence
   despite uncommitted Events/Log, with real transaction/ordinal parity receipts.
2. Independently verified dedicated vault/signer control, public-key/address
   binding, isolation from 8092/8093 and HD/DE authorities, recovery/revocation,
   and the full C2 collision inventory. No destination is made available here.
3. Complete dated reserve provenance and liability reconciliation, preserving
   betting, staking, refunds, treasury and claim #889 obligations; no reused
   betting collateral or inferred solvency from balances.
4. Owner-bound single-use intent proof and durable global receipt uniqueness,
   atomic balanced credits, concurrency/restart/orphan-deposit recovery, then
   separately proved idempotent withdrawals/refunds and accepted funded tickets.
   Protected app/chain releases and an approved canary remain later gates.

Tests exercise synthetic adversarial sources, disagreement, forged/malformed
responses, extra effects, freshness, cancellation, size bounds and repeat reads.
They establish source behavior, not successful mainnet funding or certification.
No deployment, restart, key operation, wallet creation, migration, ledger credit,
withdrawal broadcast, token transfer, or app/API repository edit is part of C3.

## Engineering memory: reproduced protocol failures

- A bounded public read-only smoke initially returned
  `invalid_response:primary:commit`. Its failing raw response was not retained,
  so the exact first payload/height cannot be independently reverified.
  CometBFT `rpc/core/blocks.go` returns a **seen** commit (`canonical=false`) at
  its latest height, and the next-block-backed canonical form for historical
  heights. The reader now accepts that representation only at the observed
  latest height, still requiring header/commit hash binding and all inclusion and
  result-root checks. Missing/null metadata and historical noncanonical commits
  remain failures. Permanent offline fixtures reproduce the source's former
  rejection of that legitimate representation; this is a verified compatibility
  defect, not proof of the original response's contents or a network defect.
- The same existing staking transaction passed inclusion/result consistency on
  a subsequent read, then was correctly refused for extra fee/transfer effects.
  It was never a Satchel deposit. No network defect or payment authority follows
  from either observation. Ordinary CI uses no live node or temporary smoke file.
- SDK `x/auth/tx/query.go` serializes REST block timestamps at RFC3339 second
  precision. Preserve header nanoseconds but accept the SDK's exact truncation;
  reject a different second. Omitted proto3 zero code is valid inside a complete
  result object; null, malformed or missing result objects are not success.
- Bind each witness's actual status to its own commit before comparing heights.
  Copying the primary head would hide conflicting or stale witness observations.
- These fixes do not authenticate validator signatures, establish a trust root,
  authenticate bank events, or relax any custody/credit gate.
