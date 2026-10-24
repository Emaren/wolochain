---
id: "aoe2war.wolochain.legacy-settlement-hardening"
title: "Legacy Settlement Hardening and Protected Release Handoff"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "git"
authority: "source-only-legacy-settlement-hardening"
reviewed_at: "2026-10-17"
review_interval_days: 14
sensitivity: "restricted"
---

# Legacy Settlement Hardening and Protected Release Handoff

The implementation baseline in the
[documentation index](DOCUMENTATION_CONTROL_PLANE.md) identifies this source
candidate. The starting authority was `wolo-1-mainnet-prep` at
`c1210dda37b725a5b141ad63361048d4b37731c2`. This review used repository source
and deterministic local tests; it obtained no new VPS or mainnet runtime
observations. Satchel [PR #25](https://github.com/Emaren/wolochain/pull/25)
remains a separate, unmerged draft at
`42ecb12c130b383677f913112baa07debd52a5ab` and is not part of this candidate.

## Current contracts retained

[C4 exact payout confirmation](exact-settlement-confirmation-c4.md), durable
prebroadcast holds, receipt ownership and canonical amount normalization were
already present at the starting authority. They are not newly repaired here.
A successful HTTP response, broadcast acceptance or a configured node's chain
name cannot prove a particular payment. Omitted Cosmos proto3 execution code
zero remains valid only within an otherwise complete, exact transaction result.
Uncertain evidence never authorizes rebroadcasting or deletion of request state.

Configured RPC/REST agreement is not independent validator-commit authentication.
The two legacy services retain their separate payout signer and request-state
authorities. Their shared betting escrow is not available Satchel collateral.
C2 custody remains `UNAVAILABLE`; C3 observations remain `NONCREDITING` under
their source contracts. No Satchel financial flag is enabled by this work.

## Bounded source corrections

The generic escrow path previously relied on matching REST transfer events after
parsing a transaction body, without requiring those effects to agree with the
actual hash-bound transaction bytes. Event-only substitutions could therefore
survive checks already strict for payouts. Escrow verification now reuses the
configured-source transaction-byte/result contract and checks the decoded bank
transfer against the expected sender, escrow recipient, exact `uwolo` amount and
any canonical challenge memo. Duplicate or conflicting matches remain
unverifiable. Distinct transfers retain their identities; generic discovery responses
are not payment authority or permission to credit a ledger. Challenge funding
search treats rows only as candidate hashes, deduplicates them and obtains the
same exact transaction proof as direct verification before returning
`Funding.OK=true`, under one shared lookup deadline. Empty or partial
discovery is never proof of nonpayment.
The shared proof retains C4's restricted `TxRaw` shape: at most 64 KiB,
nonempty auth metadata and exactly one nonempty signature, with a decoded body
equal to REST. Escrow may contain distinct bank sends/coins within the existing
250-message bound, but a multisignature transaction remains unverifiable under
this adapter. This structural signature guard does not independently verify a
signature or validator commit. Payout proof still requires exactly one bank send
and one `uwolo` coin; escrow support does not widen that payout contract.

Financial addresses require checksum-valid, canonical lowercase Bech32 with
the expected WOLO HRP and a 20-byte account payload. A `wolo1` prefix alone is
insufficient. No account, signer or key is created by validating an address.

Legacy JSON reads share the bounded evidence transport and JSON structure
guards: response-size and time limits, cancellation, no redirects or compressed
responses, and refusal of duplicate members, excessive structure and trailing
JSON. Financial HTTP request bodies are bounded objects subject to the same
structural guard. Legacy financial parsing also rejects case-folded member
aliases, including `memo`/`MEMO` and Unicode aliases such as
`source_app`/`ſource_app`, before Go can substitute one field for another.
The shared guard's existing C3 mode is unchanged; unknown fields and one
alternate spelling remain compatible with legacy callers.
Each request and each upstream JSON evidence object is capped at 1 MiB with
maximum depth 32 and 100,000 nodes. The evidence client caps each HTTP operation at five seconds, connection,
TLS handshake and response headers at two seconds, response headers at 16 KiB,
and per-host connections at four (eight idle globally, four per host).

The service allows 16 concurrent handlers and refuses excess work with HTTP 503
before entering its handler; it does not queue or retry a financial operation.
HTTP header/body read deadlines are five/ten seconds, idle timeout is 30 seconds
and request headers are capped at 16 KiB. The write budget is one minute plus
250 times the configured command, confirmation and lookup budgets (three hours,
37 minutes, 40 seconds under the current 30/12/10-second defaults), preserving
sequential grouped-run capacity. A write deadline is not a financial rollback
or evidence that an in-progress transfer did not occur. Existing durable request
holds and `retryable=false` uncertainty remain authoritative if the client
disconnects or confirmation expires. These controls preserve the existing
bearer-authenticated 8092/8093 contract.

Regression coverage uses local synthetic sources and never signs or broadcasts
a real transaction. The draft PR records failing-before cases, final test totals,
exact implementation SHA and hosted CI receipts. This document does not turn
those source results into a production receipt.

## Source validation receipt

Local `go test -tags go1.27 ./... -count=1` and the same full suite with
`-race` each passed 797 tests including subtests (158 top-level tests). Four
existing application simulation tests remained skipped; they were not enabled
or replaced by mock financial execution. `go vet -tags go1.27 ./...`, the
`wolochaind` build, all operator shell syntax checks, the source-only chain
invariant guard and generated-protobuf drift check passed. Eleven Python
contracts passed: five founder state-forensics contracts and six release-policy
contracts. The tag matches existing repository CI's pinned Sonic compatibility
setting. The documentation seal and actual hosted CI apply to the final PR head.

Failing-before fixtures reproduced escrow event/body substitutions, missing or
mismatched RPC bytes/results, ambiguous effects, noncanonical expected amounts,
forged challenge memo/recipient, event-only discovery promotion, incomplete
canceled discovery, malformed addresses, unbounded/ambiguous JSON, redirects,
error-body disclosure, case-folded field substitution and incorrect founder
ports. Positive controls preserve genuine zero-code serialization, exact
multi-message/coin transfers, canonical challenge funding, distinct payout
receipts and existing uncertain-payment holds.

## Protected release inspection

The October 17 review found these existing contracts; no script was run on a
server and no new release authority was inferred:

| Source contract | What it establishes | What remains blocked |
| --- | --- | --- |
| `scripts/settlement-only-provenance.sh` | Read-only installed/running binary, embedded VCS and optional candidate checks against its exact pins. | Its settlement runtime pin is historical `78c25985`; its candidate pin is retired `3ea79363`. It cannot attest this candidate. |
| `scripts/settlement-dual-service-release-preflight.sh` | Checks both historical settlement units, separate consensus process, private snapshot checksums, exact loopback 8092/8093 binds, HTTP health and observed absence of locks. | Pins and paths are historical. Health and no observed lock do not prove zero financial work or permission to release. |
| `scripts/settlement-dual-service-snapshot.sh` | Two separately recorded private state/config trees with drift checks and immutable historical receipts. | An online copy is not an atomic chain/request-state snapshot or permission to restore financial history. |
| `.github/workflows/settlement-current-implementation-candidate.yml` | No-deploy build of exactly `bdbce253c524d6faac14f61cd129ac5072287c3f`, clean embedded VCS, binary checksum and explicit nonauthorization receipt. | It checks out that SHA rather than this PR head; its artifact does not contain these changes. |
| `scripts/settlement-two-service-code-rollback.sh` | Read-only historical inspection; `--rollback` and `--rescue` return exit 2 with `OBSOLETE_LEGACY_RECOVERY` before live/root checks. | There is no currently authorized modern activation/recovery controller in this base. Retired automatic producer resume must stay retired. |

One concrete preflight defect was reproduced: after requiring primary port
8092, its bind policy accepted any distinct founder loopback port, including
8094 and 18093. The guard now requires exactly `127.0.0.1:8093`. The new offline
regression executes the actual bind-policy fragment without privileged runtime
or network operations. It failed before this correction and now passes; the
canonical 8092/8093 pair remains accepted. The existing four recovery-retirement
tests and both new bind-contract tests pass (six total); syntax checks of the
four scripts above pass. These checks establish source behavior only. No other
release-tool change or modern controller was introduced.

## Evidence required for a later protected release

A future separately reviewed release must provide the following evidence in a
versioned operator receipt; this document does not supply that receipt:

1. Fresh, timestamped runtime observations for **both** settlement services:
   MainPID, effective unit/drop-ins, executable path and SHA-256, embedded source
   revision/modified flag, loopback 8092/8093 health, distinct signer roles and
   state/config identities. Record the consensus PID/path/SHA independently and
   prove it is unchanged throughout the operation. Historical `78c25985` and
   reviewed `bdbce253` observations are not current production truth.
2. An independently reviewed immutable Linux artifact for the exact final
   approved implementation SHA, with a clean build's embedded VCS, CI run and
   artifact identity/digest, toolchain and explicit release manifest. The
   existing pinned `bdbce253` artifact cannot represent this implementation.
   Any provenance/preflight policy for a new candidate needs its own review;
   changing old source pins alone does not establish safe recovery.
3. Operator-owned HD **and** DE financial-ingress isolation, including scheduled
   producers, active job services and alternate signing routes, plus canonical
   chain/request-state reconciliation of all authorized, pending, accepted,
   unverifiable and inflight obligations in both lanes. No-lock observations,
   disabled timers, empty cached queries or a source test suite cannot prove a
   drain. Founder claim #889 retains its independent unresolved hold; do not
   retry it or repeat exhausted investigations.
4. Governed private snapshots for both lanes, current liability/reserve evidence
   and a separately reviewed two-settlement-only controller/watchdog rehearsed
   against the approved runtime/artifact pair. Recovery must preserve current
   live request/run/receipt state and remain `QUIESCED_RECOVERY_ONLY`: keep
   financial producers and signers fenced until independent reconciliation and
   named approval. Historical state restoration or automatic producer resume
   can reopen already consumed payout obligations and is prohibited.
5. Named authorization and a protected window, followed by an independently
   observed exact runtime receipt for both lanes and unchanged consensus
   identity. The generic shared-binary restore can restart consensus; its
   settlement-only path does not coordinate the founder lane. Neither is an
   approved two-service recovery procedure.

The smallest legitimate next step is an exact-source artifact and a reviewed
protected two-lane release/recovery manifest after those financial gates are
satisfied. This source PR performs no SSH, deployments, service operations,
key access, signing, broadcasts, token transfers, database changes, state
rewrites or retries. Green source CI is not live custody certification or
production cutover approval.
