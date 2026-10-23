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
reviewed_at: "2026-10-22"
review_interval_days: 14
sensitivity: "restricted"
---

# War Satchel Exact Source Artifact Contract

The shared [builder](../scripts/build-settlement-artifact.sh) and
[offline verifier](../scripts/settlement-artifact.py) implement four named
profiles. Historical pins retain their original meanings:

| Profile | Exact implementation | Binary / manifest |
| --- | --- | --- |
| `legacy526` | `526d5eb6123f6cc0394b5e78489c668e77e46106` | `wolochaind`, version 1 |
| `composed-satcheld` | `155fcf67fb2127a2227de5ea785e51bdbb0155c0` | `wolosatcheld`, version 2 |
| `custody-backend` | `8c509e8f62ca3ec60711dc2654a03b12f22b0773` | `wolosatcheld`, version 2 |
| `custody-runtime` | `72a3bca5f66aff51e1c6577b914d64403785d635` | `wolosatcheld`, version 2 |

The new runtime source contains the opaque, operation-bounded custody issuer
and the 10,000 WOLO wager / 50,000 WOLO daily product ceilings. Existing smaller
signed and configured limits remain binding. The frozen `custody-backend`
binary does not implement those changes; its receipts and checksum cannot be
relabeled as the runtime candidate. Named-profile and purpose equality is
required even when package, workflow path or binary bytes happen to match.

Each profile pins its main package and workflow. A caller cannot supply another
source revision through the CLI. An unset or placeholder implementation pin is
rejected before building. Tooling and documentation commits have a separate
builder identity.

The [composed workflow](../.github/workflows/composed-satcheld-exact-artifact.yml)
checks out the exact implementation separately from the artifact tooling. The
manifest's source commit, tree and embedded Go VCS revision describe the code
compiled into the binary. `github.builder_commit` describes the tooling
checkout; `workflow_sha`, `workflow_ref`, run ID and attempt identify the
GitHub execution. These identities have different meanings and must all match
the independently inspected run. Caller-supplied identity strings alone do
not authenticate a run.

The existing [custody artifact workflow](../.github/workflows/custody-backend-satcheld-exact-artifact.yml)
now invokes `custody-runtime` against the exact `72a3bca5` source, using the same
recipe and Go 1.24.6 toolchain. Its historical filename is retained; authenticated
receipts bind the actual workflow revision and builder commit. Earlier
`custody-backend` builds remain verifiable using their original source pin and
independently retained GitHub receipts. New uploads use `custody-runtime` names,
profile and purpose. A workflow run or local test result alone is not an artifact
acceptance receipt: independently download and validate the new archive before
changing a consumer pin.

## Building and checking the candidate

The workflow invokes the same builder used for the legacy profile:

```sh
bash scripts/build-settlement-artifact.sh --profile composed-satcheld \
  /path/to/clean-pinned-source /path/to/new-output-directory
```

Use `--profile custody-runtime` with the clean `72a3bca5` checkout to build the
new runtime candidate. The same profile must be supplied to verification below;
it does not change the frozen `custody-backend` policy.

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

The runtime source still requires actual independently provisioned trust-root,
vault-control, key-isolation, dual reserve-review, runtime-permit and journal
evidence. Admissions require a fresh exact bank and journal review after each
journal mutation and sufficient extra uncommitted assets beyond recorded
liabilities, gas and floors. No authenticated atomic liability discharge is
assumed. No independent mainnet root has been supplied for this candidate;
source qualification and reproducibility cannot authorize funding or execution.
