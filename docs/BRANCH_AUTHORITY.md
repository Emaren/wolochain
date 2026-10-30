---
id: "aoe2war.wolochain.branch-authority"
title: "WoloChain Branch Authority"
type: "reference"
status: "active"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "git"
authority: "git-branch-authority-contract"
reviewed_at: "2026-10-29"
review_interval_days: 14
sensitivity: "internal"
---

# WoloChain Branch Authority

Reviewed: 2026-10-29 (GitHub source only)

## October 29, 2026 — current GitHub source-authority review

Scope: remote GitHub source, PR refs and verified source CI only. **No live
Mac worktree, HEL1 runtime, signer, custody, bank, financial ledger or restore
evidence was collected.** The October 14–18 observations below remain
historical, not today's runtime truth.

| Source role | Exact SHA | Disposition |
| --- | --- | --- |
| Default `main` | `a2fba6bfd98d7b28fb113badbadf23ec9096a4af` | Separate source branch, not a deployed-binary receipt. |
| Federation `wolo-1-mainnet-prep` | `98f781d61fa6b35d2cc09b48f84605a617efc2c4` | Current documentation source; not runtime authority. |
| [Held escrow #115](https://github.com/Emaren/wolochain/pull/115) | `00892e0d82362f53227188cde4ca34d7b6b5dd9a` | Qualified **pre-documentation** head, unmerged. |
| [Held parent #111](https://github.com/Emaren/wolochain/pull/111) | `e547f24446be1318060c8f48123786f396c4e841` | Unmerged recovery/maintenance source. |
| [Held sibling #116](https://github.com/Emaren/wolochain/pull/116) | `fac1e4282140843024bb4232c340154e271b4c61` | Unmerged, independent recovery source. |
| [Diagnostic #117](https://github.com/Emaren/wolochain/pull/117) | `b2c699f6df138a510e3f0a74a87c5cbb3858b388` | Unmerged; July settlement CI did not reproduce. |

Current GitHub comparison `main...wolo-1-mainnet-prep`: **2 main-only /
230 prep-only** commits; common ancestor
`b746c22341567df373be2cbcef3843e965961f72`. The earlier 2/35 and
2/40 counts below are dated history. No automatic branch reconciliation.

At the pre-documentation #115 head, genuine disposable native
[SDK+HD/PG16 #40770005487](https://github.com/Emaren/wolochain/actions/runs/40770005487)
and [standard CI #40770005517](https://github.com/Emaren/wolochain/actions/runs/40770005517)
passed: Comet/ICS23 H/H+1 two-bank proof, conserved one 100-WOLO
physical MsgSend0 with 40+60 legs, return and fee fixtures. These are
**source tests, not production custody or funded authority**. A native
non-signing Go wire-v1 verifier executable is still absent. Held HD #940
ingress is disabled and has outstanding receipts/certificates SQL INSERT
placeholder-arity faults. July main failure remains historically
unclassified despite a passing diagnostic #117 run.

**Wave-1 application release excludes ALL funded Wolo features:** no
Keplr-to-Satchel live credit, v3 escrow signing, automatic wagers,
financial migration, legacy settlement writer changes, key provisioning,
nonce issuance or transfers. Protect current legacy 8092/8093 financial
listeners, validator, prospective 8094 vault, keys and nonces, historical
claims, rollback and restore assets. Original ambiguous 100-WOLO
transfer, founder #889, #8477, complete non-overlapping HD/DE liabilities,
current per-account bank reserves, producer fencing, legal authorization,
independent custody, isolated restores and owner/witness approvals remain
HOLD/UNKNOWN.

The last certified website deployment was
`app-prodn@33e0f42b3d34d324b6cbab6c0347d4f5aff6fb8a`,
BUILD_ID `DQ2jMprNQ_Njq6QM8GHju`. This Git review does not refresh live
Wolo PID, executable, config, runtime source or financial writer evidence;
Session F must independently prove these against the *new exact W1*
candidate. Codex unpublished WIP stays protected: no reset, clean,
parallel financial-controller rewrite or broad merge.

## Historical October 14–18 source and worktree inventory


### October 18, 2026 — combined Satchel/operations candidate

The implementation worktree is `codex/satchel-production-backend`, initially
branched from integrated draft [PR #38](https://github.com/Emaren/wolochain/pull/38)
HEAD `68cdc1ae2f1c877f40e7ee3f8c094729f080394f`. That source contains both
Satchel #29 `04912e1b7e45bc3dc489070aadcb3e729178915f` and guarded operations
#36 `7c987e5ac066968fc40a3500659188a6b9527105` as ancestors, through two-parent
merge `952bacef86febf24d3d799aca64b097b9e4502e6`. PR #37 was closed as a
superseded conflict probe; it was not merged. The exact current implementation
baseline is always the [source-bound index](DOCUMENTATION_CONTROL_PLANE.md),
not this initial branch point. App source and releases belong to their separate
engineer; no app repository is changed by this candidate.

Read-only local inventory on October 18 found seven worktrees. No worktree or
branch was deleted, reset, cleaned or rewritten:

| Worktree suffix | HEAD at inventory | Disposition |
| --- | --- | --- |
| primary `WoloChain-wolo-1` | `c1210dda` | Clean mainnet-prep authority; preserve. |
| `satchel-production-backend` | `68cdc1ae` | Clean starting combined candidate; active implementation. |
| `satchel-source-integration-proof` | `04912e1b` | Clean PR #29; integrated ancestor, preserve review/artifact lineage. |
| `satchel-mainnet-execution` | `42ecb12c` | Clean PR #25; integrated ancestor, preserve. |
| `legacy-settlement-hardening` | `526d5eb6` | Clean PR #26; integrated ancestor, preserve original artifact identity. |
| `exact-settlement-artifact` | `2405e36c` | Clean PR #27 tooling; preserve pinned historical profile. |
| `current-settlement-release` | `a332ad91` | **Dirty earlier release WIP; preserve all files pending exact diff disposition.** |

The dirty worktree includes tracked runbook/rollback edits and untracked release
policy, state evidence, watchdog/controller, helper-stage, fixtures, workflow
and tests. Its apparent overlap with later operations work is not proof that all
content is duplicated. Bytecode caches are disposable generated candidates;
even these were left untouched during this inventory. No unreviewed code is
approved for deletion. PRs #25–#36 remain useful stacked review/evidence records
although their implementation ancestry is combined; closing them requires owner
review. Old PR #16 watchdog work is an obsolete-policy *candidate*, requiring a
specific diff against the current bdbce controller before cleanup. The retired
`3ea79363` mutation scripts stay retired.

Source integration does not advance live executable authority. The `bdbce253`
legacy candidate, `526d5eb6` historical artifact and `155fcf67` composed signer
artifact keep their original identities. An artifact built from any of those
commits cannot be relabeled as this candidate. Current signed release receipts
and independent financial/operator evidence remain required.


### October 17, 2026 — authenticated financial bridge integration

Branch `codex/satchel-authenticated-financial-bridge` extends composed PR #28
`9f59b6472163e226e98a0a94d6a0136b0dc02d96` without rewriting PR #25, #26,
#27 or #28. Portable Comet proofs and mandatory owner withdrawal mandates are
source contracts; the exact composed signer artifact uses the shared pinned
profile framework. See [release gates](war-satchel-controlled-release.md) for
fresh runtime identities and accepted-state observations. None of these source
commits is deployed. All historical authority and founder #889 holds remain.


### October 17, 2026 — source-only settlement candidate

This work starts from remote-exact `wolo-1-mainnet-prep` at
`c1210dda37b725a5b141ad63361048d4b37731c2` on the isolated
`codex/legacy-settlement-hardening` branch. Its source baseline is recorded in
the [documentation index](DOCUMENTATION_CONTROL_PLANE.md); that baseline is
not deployed settlement or consensus authority. The older source/build and
October 14 runtime identities below remain dated historical observations.
The [release handoff](legacy-settlement-hardening.md) records why neither the
retired `3ea79363` policy nor the pinned `bdbce253` artifact can certify this
candidate. No new production observation or branch reconciliation occurred.
Satchel PR #25 remains intact and unmerged on its separate branch.

### Historical October 14 federation observation

The documentation federation for `wolo-1` mainnet work is sourced from
the clean remote-exact `wolo-1-mainnet-prep` branch. The
settlement-candidate workflow, exact-source provenance tooling, and new
root-private two-service snapshot, read-only cutover preflight, code-only rescue and DE parallel-ingress evidence tools advance the
**repository source/documentation baseline** to
`218dfade0722bbf9c8a087f9fa08dde787d3eef9`. This is NOT a new
settlement build or consensus module revision. The reviewed settlement
verifier code itself is `3ea79363695dd93be5f0a5e8a5121cf6e31d27b8`.

**Observed live operating identities (2026-10-14T03:32:39Z):** settlement
services compiled from `78c25985420ee41a6678c42fab8ea8d6c3b1b519`,
SHA-256 `040126a2884946caf1651a50b7d8115c5a6fb2d5aa94fcbbe150694602d451a5`.
The consensus node uses the separate unchanged
`wolochaind-mainnet-node-prewartrophy` executable with source
`d3bd62414a047a492a3814b7d3baa2717d64db2e`, locally modified
at build time, SHA-256
`4b77f622191db7550cb87cafb8f1886a0aadebee3eb6565f9f90036f809e61d3`.
Deployment of `3ea79363` is a separate, protected settlement-only operation;
none of these observation dates authorizes touching the consensus node.

**Historical implementation baseline (September 22):**

```text
d5dea8d6f1a2b0b57489a5e468dd21e34246891e
```

Do not confuse that implementation baseline with later documentation-only branch
HEADs. A GitHub-authority review on September 22, 2026 observed
`wolo-1-mainnet-prep@de81f3502c9c7d8e81783afcdfa0f800af9111cd` and
`main@a2fba6bfd98d7b28fb113badbadf23ec9096a4af`. The branches remain
intentionally diverged at `2` main-only / `40` prep-only commits, with merge
base `b746c22341567df373be2cbcef3843e965961f72`. This Git-only review made no
runtime claim and did not reconcile the branches.

The prior September 9 pre-review observation recorded prep HEAD
`8b2563b50d410a52c511ef7cdc3a7821e4546747` at `2 / 39` divergence. That
dated observation remains useful history but is not current branch identity.

The repository default/main line remains separately present at:

```text
main@a2fba6bfd98d7b28fb113badbadf23ec9096a4af
```

At the September 22 historical implementation baseline
`d5dea8d6f1a2b0b57489a5e468dd21e34246891e`, the branch relationship was:

```text
origin/main...wolo-1-mainnet-prep
main-only commits: 2
prep-only commits: 35
```

That `2 / 35` count describes the implementation baseline being documented.
Documentation-only commits after that baseline may increase the prep-only Git
count without changing the implementation baseline. Use Git for the current
live divergence:

```bash
git rev-list --left-right --count origin/main...HEAD
```

This divergence is **intentional state to understand**, not a defect to erase
automatically.

## Rule

Do not merge, rebase, reset, or cherry-pick branches merely to make a
documentation dashboard report one SHA.

Before any branch reconciliation:

1. inspect the main-only commits;
2. inspect the prep-only commits;
3. identify which exact source built any deployed mainnet binary;
4. preserve chain/settlement/runtime evidence;
5. prove tests and upgrade semantics;
6. decide the promotion/reconciliation path explicitly.

Documentation federation itself is not permission to change chain code or
runtime state.

## Authority layers

Do not collapse these identities:

- Git branch/source identity;
- deployed `wolochaind-mainnet` binary identity;
- live `wolo-1` consensus/runtime state;
- settlement service runtime/config identity;
- documentation implementation baseline;
- historical mainnet-prep receipts.

Runtime and chain truth must still be verified from the owning runtime
surfaces when an operation depends on current state.

## Current branch roles

`wolo-1-mainnet-prep` contains the current mainnet-oriented source and
documentation corpus being federated, including settlement, IBC/Osmosis,
mainnet service, wallet/custody, and Warbound Trophy implementation work.

`main` remains a distinct source line. Its existence must stay visible in
central documentation until an intentional reconciliation changes that fact.

## Central documentation rule

AoE2WAR-docs should ingest the WoloChain source registry from
`wolo-1-mainnet-prep` until the branch authority is deliberately changed.
Central documentation may index this truth; it must not silently promote
`main` or invent a merge.
