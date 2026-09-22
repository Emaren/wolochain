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
reviewed_at: "2026-09-22"
review_interval_days: 14
sensitivity: "internal"
---

# WoloChain Branch Authority

Reviewed: 2026-09-22

## Current federation source

The documentation federation for live `wolo-1` mainnet work is sourced from
the clean remote-exact `wolo-1-mainnet-prep` branch. The implementation baseline
described by this documentation remains:

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

At the implementation baseline
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
