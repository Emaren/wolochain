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
reviewed_at: "2026-10-14"
review_interval_days: 14
sensitivity: "internal"
---

# WoloChain Branch Authority

Reviewed: 2026-10-14

## Current federation source

The documentation federation for `wolo-1` mainnet work is sourced from
the clean remote-exact `wolo-1-mainnet-prep` branch. The
settlement-candidate workflow, exact-source provenance tooling, and new
root-private two-service snapshot, preflight, rollback and draft watchdog rendezvous tools advance the
**repository source/documentation baseline** to
`2933194fffdf3fb3fc370af9bc244b955e6dc310`. This is NOT a new
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
