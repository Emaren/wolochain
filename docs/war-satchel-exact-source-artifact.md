---
id: "aoe2war.wolochain.war-satchel-exact-source-artifact"
title: "War Satchel Exact Source Artifact Contract"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "git"
authority: "source-artifact-proof-not-runtime-or-financial-approval"
reviewed_at: "2026-10-17"
review_interval_days: 14
sensitivity: "restricted"
---

# War Satchel Exact Source Artifact Contract

The shared [builder](../scripts/build-settlement-artifact.sh) and
[offline verifier](../scripts/settlement-artifact.py) implement two named
profiles. `legacy526` retains the exact PR #26 source
`526d5eb6123f6cc0394b5e78489c668e77e46106`, `wolochaind` binary and version 1
manifest contract. `composed-satcheld` builds only `wolosatcheld` from its
separately pinned source `155fcf67fb2127a2227de5ea785e51bdbb0155c0`, with a
version 2 manifest identifying that profile. Each profile pins its own main package and workflow. A caller cannot
supply another source revision through the CLI. An unset or placeholder composed source is rejected before building; the
implementation pin above includes the authenticated bridge and owner-mandate
source. Later tooling/documentation commits have a separate builder identity.

The [composed workflow](../.github/workflows/composed-satcheld-exact-artifact.yml)
checks out the exact implementation separately from the artifact tooling. The
manifest's source commit, tree and embedded Go VCS revision describe the code
compiled into the binary. `github.builder_commit` describes the tooling
checkout; `workflow_sha`, `workflow_ref`, run ID and attempt identify the
GitHub execution. These identities have different meanings and must all match
the independently inspected run. Caller-supplied identity strings alone do
not authenticate a run.

## Building and checking the candidate

The workflow invokes the same builder used for the legacy profile:

```sh
bash scripts/build-settlement-artifact.sh --profile composed-satcheld \
  /path/to/clean-pinned-source /path/to/new-output-directory
```

The builder requires externally supplied CI identity variables and exactly
Go 1.24.6. It compiles Linux AMD64 with `CGO_ENABLED=0`, `GOAMD64=v1`,
`-trimpath -buildvcs=true -tags=go1.27 -mod=readonly -ldflags=-buildid=`.
It uses two clean checkout paths and separate fresh Go build caches, verifies
module contents, and requires identical binary bytes. Both binaries must have
the expected ELF architecture, main package, compiler, VCS revision and clean
modification flag. The verifier rejects dirty, untracked, ignored and hidden
index source changes. It inspects private binary snapshots without executing
the candidate, with finite file, subprocess output and timeout limits.

Go embeds only some recipe flags. The verifier checks the embedded settings
and absence of a Go build ID; the reviewed CI recipe supplies the evidence for
`-mod=readonly` and the empty build ID flag. Two identical builds establish
repeatability under this compiler and recipe. They do not establish identity
across different Go versions, host toolchains or independent build operators.

For independent acceptance, first inspect the successful run through
authenticated GitHub access. Verify the repository, tooling commit, workflow
revision, exact implementation checkout, run ID and attempt. Retrieve the
artifact ID and archive digest from that run, hash the downloaded archive and
compare it with GitHub's upload receipt. Obtain `manifest_sha256` from the
authenticated run receipt or step summary, separately from the candidate's
unsigned manifest. Preserve the archive, receipt and their identities.

Then use a clean checkout of the pinned implementation and trusted Go tooling:

```sh
python3 scripts/settlement-artifact.py verify --profile composed-satcheld \
  --source-dir "$CLEAN_PINNED_SOURCE" --binary "$ARTIFACT_DIR/wolosatcheld" \
  --manifest "$ARTIFACT_DIR/manifest.json" \
  --expected-manifest-sha256 "$AUTHENTICATED_MANIFEST_SHA256" \
  --repository Emaren/wolochain --builder-commit "$VERIFIED_BUILDER_COMMIT" \
  --run-id "$VERIFIED_RUN_ID" --run-attempt "$VERIFIED_RUN_ATTEMPT" \
  --workflow-ref "$VERIFIED_WORKFLOW_REF" --workflow-sha "$VERIFIED_WORKFLOW_SHA"
```

Use values independently verified against GitHub, rather than values copied
solely from the candidate manifest. CLI verification requires the external
manifest digest and checks its raw bytes before JSON parsing. This rejects an
attacker who changes the binary and rewrites a self-consistent manifest while
retaining the original embedded Go metadata and CI identity strings. The
low-level Python `verify_manifest` function checks consistency only; it does
not authenticate an unsigned manifest.

## Authority remains held

All artifact authority flags remain false. Historical `SOURCE_AUTHORITY.json`
receipts retain their limited source-proof meaning; their former metadata-only
generator now fails closed, and the existing Satchel source-proof job retains
its race and regression tests. Its earlier generic uploads are not promoted
into the new profile. The historical `bdbce253` artifact and PR #27's separate
legacy artifact remain separate evidence.

Synthetic `.invalid` endpoints used by offline tests are not chain evidence,
live service identities or operator provisioning. An artifact does not turn
such placeholders into accepting configuration. Real custody remains
`UNAVAILABLE`; financial evidence remains subject to its authentication and
freshness checks. No service is enabled, installed, restarted or contacted by
the artifact builder.

Runtime and financial release still require the independent vault and signer
authority, authenticated chain trust, both live legacy service identities,
financial ingress drain, current liability reconciliation, exclusive state
ownership, snapshots and separately reviewed recovery authority described in
the [operator gates](war-satchel-mainnet-execution.md). Existing 8092/8093
authorities, consensus executable separation and claim #889 remain intact.
