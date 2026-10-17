---
id: "aoe2war.wolochain.settlement-exact-source-artifact"
title: "Exact-source Settlement Artifact"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "git"
authority: "non-deploying-settlement-artifact-contract"
reviewed_at: "2026-10-17"
review_interval_days: 14
sensitivity: "restricted"
---

# Exact-source Settlement Artifact

This lane builds the hardened legacy settlement implementation at exactly
`526d5eb6123f6cc0394b5e78489c668e77e46106`, the reviewed head of
[PR #26](https://github.com/Emaren/wolochain/pull/26). The separate stacked
`codex/exact-settlement-artifact` branch contains the builder, verifier and
tests. Its commit and GitHub workflow identity describe the build machinery;
they must not replace the binary's source revision in a receipt. The target
base remains `codex/legacy-settlement-hardening`. Neither branch is deployed. The stronger recovered builder is consolidated into
[PR #27](https://github.com/Emaren/wolochain/pull/27), replacing its earlier
single-build workflow rather than creating another artifact standard.

The existing `settlement-current-implementation-candidate.yml` continues to
refer to historical source `bdbce253c524d6faac14f61cd129ac5072287c3f`.
That artifact is not renamed, repinned or accepted as this implementation.
Historical provenance, preflight and recovery locks remain intact.

## Build and verification contract

The new [workflow](../.github/workflows/legacy-settlement-exact-526d5-artifact.yml)
checks out the artifact machinery and the exact reviewed implementation
separately. [The builder](../scripts/build-settlement-artifact.sh) rejects
source revision drift and a dirty source checkout. A pinned Go 1.24.6 toolchain
builds `./cmd/wolochaind` for `GOOS=linux`, `GOARCH=amd64`, `GOAMD64=v1`,
`CGO_ENABLED=0` with `-trimpath -buildvcs=true -tags=go1.27 -mod=readonly
-ldflags=-buildid=`. The tag does not select a Go 1.27 compiler. Two separate
checkout paths and fresh Go build caches must produce the same binary SHA-256;
the shared module cache is checked with `go mod verify`. This is a same-toolchain
reproducibility check; it does not claim independent compiler or consensus
authentication.

A versioned `manifest.json` binds the exact implementation commit/tree/VCS time,
Go's embedded VCS revision and `vcs.modified=false`, compiler and toolchain
identity, Linux AMD64 target, build recipe, both build SHA-256 values, builder
commit, and GitHub repository/run ID/attempt/workflow reference/workflow SHA.
The artifact also contains `wolochaind`, `SHA256SUMS` and
`go-build-metadata.txt`. [The offline verifier](../scripts/settlement-artifact.py)
checks claims against actual binary metadata and ELF architecture. It rejects
an unexpected source, dirty VCS metadata, different embedded revision, changed
binary checksum or wrong architecture. Go does not embed every command-line
flag: `-mod=readonly` is a reviewed recipe claim; the verifier checks an empty
build ID rather than pretending Go embeds `-ldflags=-buildid=`.

An unsigned manifest alone is not an independent attestation. Verification also
requires `--expected-manifest-sha256` from the independently authenticated upload
receipt; rehashing an untrusted local manifest is insufficient. Its GitHub fields
must match externally trusted run identity and the successful GitHub run/API
receipt. Retain the immutable upload receipt, including artifact ID/digest,
alongside it. The upload receipt is external because its archive digest does
not exist until after upload; embedding it would create a circular claim.

For independent offline inspection, obtain the expected manifest SHA-256, builder
SHA, run ID, attempt, workflow reference and workflow SHA from the reviewed PR and
authenticated GitHub run context. Verify the downloaded archive against the
GitHub artifact API/upload digest before extraction. Supply those externally
obtained values, never values copied from the candidate manifest:

```bash
python3 /path/to/reviewed-artifact-tools/scripts/settlement-artifact.py verify \
  --source-dir /path/to/clean-526d5eb6-checkout \
  --binary /path/to/extracted-candidate/wolochaind \
  --manifest /path/to/extracted-candidate/manifest.json \
  --expected-manifest-sha256 "$TRUSTED_MANIFEST_SHA256" \
  --builder-commit "$REVIEWED_BUILDER_SHA" \
  --repository Emaren/wolochain \
  --run-id "$TRUSTED_RUN_ID" --run-attempt "$TRUSTED_RUN_ATTEMPT" \
  --workflow-ref "$TRUSTED_WORKFLOW_REF" \
  --workflow-sha "$TRUSTED_WORKFLOW_SHA" \
  --go /path/to/trusted/go
```

The source directory must be a clean Git checkout of the full pinned commit,
including no ignored files or hidden index flags; keep artifacts outside it.
The command inspects a private snapshot of the candidate and never executes
it. It verifies the binary, manifest and supplied identity consistently; it
does not authenticate GitHub, validate an archive digest or rerun the second
compilation. The two-build claim is bound to the reviewed workflow and external
run receipt. `SHA256SUMS` and the metadata text support inspection but cannot
replace that external receipt or the verifier's binary inspection.

Offline adversarial tests exercise malformed, inconsistent and forged
provenance without running a candidate or accessing a service. The workflow
also runs source tests at the pinned implementation. The original 26 offline adversarial cases remain intact; seven additional
receipt cases reject retargeting a binary and manifest while retaining valid Go
metadata. All 33 pass. Full Go and race runs each passed 797 tests including
subtests, with four existing simulation skips. The final PR receipt
records the exact builder commit, run URL, artifact identity and verification
results; those are distinct from the fixed implementation commit above.

This is an **UNDEPLOYED, NON-PROMOTING** artifact. A `wolochaind` binary can
contain other commands; its presence never authorizes invoking a node,
signer, keyring or financial command. The lane installs nothing and neither
opens a production connection nor grants release credentials.

## Remaining protected-release evidence

The artifact satisfies only a source/build prerequisite. Separately authorized
operators must still obtain all of the following before any release:

1. Fresh identities for **both** live settlement services: effective units and
   drop-ins, MainPIDs, executable paths and SHA-256 values, embedded revision and
   modification state, exact loopback 8092/8093 binds, health, independent signer
   roles, and state/config paths. Historical `78c25985` observations are not a
   current runtime receipt. Record the separate consensus executable and prove
   its PID/path/digest remain unchanged throughout the protected operation.
2. HD **and** DE financial-ingress fencing, including timers, active job
   services and alternate producers/signing routes, followed by proof that no
   authorized or inflight operation can write. Health, idle timers, absent lock
   files and empty caches cannot establish this drain.
3. Canonical chain/request-state reconciliation in both lanes for all accepted,
   pending, failed, unverifiable and authorized obligations; complete liabilities
   and reserve provenance; and independent owner/receipt attribution. Preserve
   founder claim #889's unresolved hold without retries or repeating exhausted
   investigations. Existing betting collateral is not Satchel collateral.
4. Exclusive ownership of both state trees with no parallel legacy or
   downgraded writer; current, private, integrity-checked state/config/unit
   snapshots taken under the agreed fence; and a reconciled recovery point.
   A historical snapshot cannot safely erase payment or idempotency history.
5. A separately reviewed two-service controller/watchdog and named rollback
   authority for the actual current-runtime/candidate pair. Recovery remains
   `QUIESCED_RECOVERY_ONLY`: preserve current financial state and keep producers
   and signers fenced until independent reconciliation and explicit approval.
   Retired `--rollback`/`--rescue` modes and automatic financial resume stay
   unavailable. Changing historical pins alone cannot create this authority.
6. A protected release window, independently checked artifact/run/upload
   receipts, named activation authority and exact observed post-release
   identities for both settlement lanes. No generic shared-binary replacement
   or restore may alter the consensus executable.

No source or artifact success certifies runtime solvency, payment finality,
custody readiness or release approval. Satchel [PR #25](https://github.com/Emaren/wolochain/pull/25)
remains separate and unchanged at
`42ecb12c130b383677f913112baa07debd52a5ab`; C2 custody remains `UNAVAILABLE`.
There are no SSH, service operations, keys, broadcasts, transactions, database
changes, retries or Satchel activation in this milestone.
