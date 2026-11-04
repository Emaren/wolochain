---
id: "aoe2war.wolochain.epoch-v3-wire-v1-hold"
title: "Native epoch-v3 wire-v1 trust mismatch and held handoff"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["developers", "operators", "ai-agents"]
source_of_truth: "git"
authority: "source-only-verifier-mismatch-not-financial-authority"
reviewed_at: "2026-10-28"
review_interval_days: 7
sensitivity: "internal"
---

# Native epoch-v3 wire-v1 trust mismatch and held handoff

**HOLD. No positive wire-v1 verifier is published by this change.** The existing
command, `--check` semantics, `ProductionEnabled=false`,
`NEW_ESCROW_SIGNER_ABSENT` and disabled HD financial ingestion remain intact.
The explicitly permitted mismatch fallback is used because the current evidence
cannot establish all facts required by the requested success contract. A passing
source test is not an installed verifier, custody receipt or financial permit.

The exact HD invocation is:

```text
<independently pinned executable> --verify-epoch-v3-portable-proof --json-stdin
```

The existing command refuses this argv with exit 2 and fixed JSON
`{"code":"EPOCH_POLICY_INVALID"}`. A focused Go refusal test preserves that
boundary. The native harness additionally builds the unchanged held command
before producing fresh SDK evidence, supplies the real sanitized golden on
stdin under HD's sanitized environment and five-second bound, and requires the
same refusal. This is explicitly **not** a successful CLI proof-verification
test, nor evidence that malformed proof subconditions have been independently
tested through a published wire decoder.

## Preserved source and evidence

The existing worktree was clean at
`00892e0d82362f53227188cde4ca34d7b6b5dd9a`. Its private preservation receipt
recorded zero staged, unstaged, untracked and ignored paths; both empty binary
patches have SHA-256
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
After that receipt, the exact upstream was fetched and deliberately advanced
with `--ff-only` to the single docs-only child
`45065503ca035790cc28edf9ad361ef68fd719f4`. No worktree, branch, controller or
PR was created. No reset, clean, stash, rebase, forced update or cache deletion
was used. Private capture paths and contents are not published.

The upstream authority document is retained byte for byte, SHA-256
`f59f74d5fae649716c43f81b06b22fd099ba9d47245fbb23c9f32d69f7f22993`.
Its registry entry is retained when this new reference and implementation
baseline are intentionally registered. The protected production Go blobs remain:

| Path | Git blob |
| --- | --- |
| `cmd/woloescrowd/main.go` | `211559480e4b4cab317a4bae6cf4ccf5f8d7944b` |
| `internal/epochescrow/evidence.go` | `8e1693d5ee966a17cf446fc9482231635cc7c2e0` |
| `internal/epochescrow/ticket.go` | `b495fe74d3c19563f54b9d3311c8d727b6b01a28` |

At source `4506550`, [standard CI](https://github.com/Emaren/wolochain/actions/runs/40793906538)
and [native SDK/HD/PG16/race CI](https://github.com/Emaren/wolochain/actions/runs/40793906520)
passed. The [sanitized native artifact](https://github.com/Emaren/wolochain/actions/runs/40793906520/artifacts/12863431709)
has **JSON SHA-256**
`150a461205f7fb8d5e41d591a8bfdb8b9d73db3d034e914aa2328e4398dead68`;
its distinct **ZIP SHA-256** is
`1a754fa57482d9afba24d9aba34b82e442413977eb783115fac97c24a1ad12c1`.
Compiler: Go 1.24.0. Disposable test executable SHA-256:
`62350d92693098f09154d592f1dc3e622845c502ab9e33025eec9137b8d3f716`.
The downloaded JSON checksum was independently rechecked. None is an installed
production-verifier pin. Archived timestamps remain historical.

The genuine fixture retains bank state H19 / commit and heads H20, equal
authenticated account roots, a single original 100-WOLO MsgSend0 partitioned
40+60 across markets, and separate 78 return / 2 matched fee / 60 void return
effects. The clock-ordering regression is solved; no expiry, roots or ordinal
are relaxed. The historical July main settlement fixture is untouched.

## Why a green wire verdict would overclaim

The complete [field-by-field matrix](epoch-v3-wire-v1-mismatch.json) records
each expected field, its source authenticator, absent evidence and blocked test.

1. **Observer provenance is absent from portable transcripts.**
   `internal/satchel/portable_proof.go:29-44` explicitly distinguishes role
   labels from independently operated endpoints. Replay at lines 179-186 uses
   fixed role hosts and supplied responses. Comet signatures authenticate chain
   validators, not the RPC operator that delivered bytes. Copying one server's
   valid signed evidence under two role labels cannot be distinguished by these
   fields. A same-server-masquerade rejection needs independently enrolled,
   authenticated acquisition/witness provenance bound to proof, head and time.
2. **Bank membership does not authenticate liabilities.**
   `BankProof` proves assets. `reserveCovers` checks canonical amounts and
   digest shape, not inventory contents, omitted outflows or nonoverlap truth.
   Reuse `satchelservice.EvaluateProofBoundReserveReview` for protected,
   separately signed bank-bound reviews; actual enrolled roots and current
   reviews are missing. Its signatures still do not establish real-world
   completeness or reviewer independence. A zero unknown-outflow assertion
   cannot be upgraded into an independently proved census.
3. **Install provenance and input authority are not provisioned.** A fixed
   root-owned public pin manifest can support HD's no-`--config` argv; that
   omission is not inherently irreducible. The current private-file reader
   requires the running UID and private permissions, so it must not be reused
   by running HD as root. A future separate public-pin reader must check its
   descriptor, protected ancestors, ownership, modes and symlinks. No manifest
   is installed here. An executing binary's own checksum or linker label cannot
   independently certify source/build/anchor authority.
4. **Stateless verification is not global consumption.** It may reauthenticate
   the same proof. Existing local journal fences and HD's atomic global receipt
   ledger remain the authorities for replay/consumption; the CLI must not add a
   second controller, claim a global unused receipt or credit a deposit.
5. **Purpose and digest semantics need an agreed adapter.** Preparation verifies
   original funding under pre-effect bank roots. A return/fee verdict needs its
   own authenticated effect and later same-root bank proofs, not reused H19
   preparation roots. Deposit is wallet-to-vault; funding is vault-to-escrow.
   HD specifies no canonical `economic_key` mapping or complete digest grammar.
   The requested transfer itself uses Comet transaction inclusion and committed
   execution results; ICS23 authenticates bank state, not a nonexistent transfer
   state key. Wire semantics must name that distinction honestly.

## Minimum pin contract requiring independent review

Before implementation, agree one non-signing, externally enrolled trust-input
contract: accepted source-to-binary/compiler/build mapping; exact executable
digest; separately provisioned Comet anchor and digest bytes; role/policy and
owner/reviewer enrollment; authenticated capture/witness provenance; and current
bank-root-bound reserve reviews with inventory/nonoverlap evidence. These are
external pins and reviews, never an authority supplied solely by stdin.
Specify byte domains for `proof_sha256`, both bank proof digests,
`verification_record_sha256` and `trust_anchor_sha256`; raw bundle SHA-256 must
always hash the exact bounded stdin bytes. Do not enroll the current docs-only
source SHA as a functioning verifier binary. No example operative manifest,
source credential or provisioning action is supplied here.

## Exact HD-owner repair handoff

At HD #940 `b7e07645e057340de051c5ffa78001ebc939191e`, native-ingest blob
`f50789bc65eb54aa9cf6c2e72a6d603107bbd3b8`:

- Keep `EPOCH_V3_NATIVE_PG_FINANCIAL_ENABLED=false` and `PERSISTED_UNCREDITED`.
- Receipts INSERT: add `$12` for `chain_time`: 14 columns / 14 values /
  12 parameters. Validate the authenticated timestamp's shape as well.
- Certificate INSERT: add `$25` for `issuer_provenance`: 28 columns /
  28 values / 25 parameters.
- Replace the stale `ae9f027...` source pin only after accepting an actual
  verifier and independently checked source/binary/anchor/install contract.
- Test the repaired real INSERT statements with an independently enrolled
  `LOGIN NOINHERIT`, explicit `SET LOCAL ROLE epoch_v3_proof_writer`, and
  SERIALIZABLE PG16 transactions: positive insert without position credit,
  rollback at each write, immutable same-root agreement/conflict, concurrent
  duplicate receipt and ordinary app/consumer role denial. Do not grant UPDATE
  to the proof writer. Reject bad/partial stdout, timeout, nonzero exit and
  source/binary/anchor/raw-input mismatch before any database write.

The existing direct SQL parity adapter is not this held ingest path. Known
same-market planner rejection stays documented and outside this narrow task.

## Remaining external holds and next action

Custody, cross-writer exclusion, off-host monotonic nonce/checkpoint, complete
HD/DE/external liability and unknown-outflow census, actual present bank proof,
the disputed original 100 WOLO, founder #889, #8477, legal authority, checksum
verified quiesced backups and independently witnessed paired isolated restores
remain unresolved. Owner/witness transaction-specific permits, installation,
role/migration changes and funded canaries are separate permissions. No HEL1,
keyring, wallet, production database, legacy settlement or W1 release is touched.

**One next integration action:** Wolo and HD owners must accept and independently
enroll the non-signing trust-input contract above. Then the exact CLI can be
implemented against actual supplied provenance rather than invented PASS flags.
