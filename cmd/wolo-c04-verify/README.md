---
id: "aoe2war.wolochain.c04-original-request-proof"
title: "C04 — bounded original-request / chain-proof observation"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "git"
authority: "noncrediting-original-request-chain-evidence"
reviewed_at: "2026-11-19"
review_interval_days: 14
sensitivity: "restricted"
---

# C04 — bounded original-request / chain-proof observation

The `wolo-c04-verify` CLI is a strictly **noncrediting, root-only** historical proof reader. It joins a SHA-256 fingerprint of the original settlement request ID (not the request ID itself) to one protected recorded `accepted` request, then reuses `internal/satchel.ChainReader.ReadTransfer` to cross-check the **actual immutable memo, sender, recipient, amount, MsgSend bytes, CometBFT transaction Merkle proof and H/H+1 result commitments**. It outputs only the public hash, block height/hash, source fingerprint and explicit refusal booleans. The original wallet addresses, memo and request ID never appear in reports or diagnostics.

Example from the root-only financial host, **read-only**:

```sh
wolo-c04-verify --state-root /mnt/HC_Volume_105319120/wolochain-mainnet/settlement-state \
  --request-fingerprint 2ed7062c8d9c44411401e4705fac55159dc3b2d936ad962459ef2869b126c020 \
  --tx-hash D5B4CFAA5E9063F8342EA9E2B6119FCFF28DEE20B2E1DD6803944933B237D699 \
  --rpc https://aoe2war.com/rpc-mainnet --rest https://aoe2war.com/rest-mainnet
```

All outcomes deliberately exit with code 3 / HOLD, including cryptographically consistent positive candidates. A primary public RPC operated by AoE2WAR is **not** an independently trusted consensus witness; adding another operator URL does not automatically prove independence. No missing/failed/ambiguous read may authorize retry. The separate founder #889 claim is not reconciled by this check. Source QA: `go test ./cmd/wolo-c04-verify` plus `go vet ./cmd/wolo-c04-verify`; `go test ./...` in CI already includes this command.

## November 19, 2026 — limited authority and dated evidence review

An AI source examiner acting through the sole owner's existing connected source workspace checked this document's 15 original body lines for repository-source links, gate-authorization claims, older governance conditions and current-versus-historical language; 1 referenced local source paths were resolved. This is a **scope and safety review**, not an independent human signature or a fresh validation of each historical physical claim. Original observations remain dated and unmodified.

**Topic-specific reconciliation (financial source history):** This file retains dated nonauthorizing historical evidence; no protected execution admission arises from it.

**Current controlling decision:** WoloChain issue #239 and reviewed code head `70a95e8f9cb0facbec314063e9deafe7e15aa550`. C04 and C08 CLOSED; C01/C02/C03/C05/C06/C07/C09 OPEN; funding DENIED. The original test/source facts remain evidence only and may not authorize live SQL, HBA, custody, funds, backups or a canary. Live acceptance requires exact source, legitimate protected owner authority and independent physical readback.

**References not resolved in this WoloChain checkout:** `internal/satchel.ChainReader.ReadTransfer`. They are not falsely asserted present; they may be other-repository or historical identifiers.
