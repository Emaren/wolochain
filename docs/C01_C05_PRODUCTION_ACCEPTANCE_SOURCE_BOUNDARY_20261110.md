---
id: "aoe2war.wolochain.c01-c05-integrated-source-acceptance-20261110"
title: "C01/C05 integrated source and physical acceptance boundary"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["operators","developers","ai-agents"]
source_of_truth: "git"
authority: "nonfunded-integration-handoff-only"
reviewed_at: "2026-11-10"
review_interval_days: 7
sensitivity: "restricted"
---

# C01/C05 integrated source and physical acceptance boundary

## Why these changes share one source branch

Held Chain source fix/c01-producer-review-20261104 contains the merged single-validator bank-height witness from PR #242 at 8382dcf750688fdb241783bf09cbbc7b95ea4fb5. The separate reviewed, CI-green but conflicting source PRs #240 and #241 are now ancestry-preserving merges on draft PR #243:

- C05 reserve-review verification and registered-legacy-escrow rejection: original PR #240 head 4bec4e9d546376283dd7382d7622bbae2913cb4d.
- C01 owner-approved one-use, zero-funds key admission: original PR #241 head 621205366f36c2105f31b0bb1f8baa3ee4cea326.

Independent git merge-tree reported conflicts only in docs/DOCUMENTATION_CONTROL_PLANE.md and docs/document-registry.json, both generated documents. The combined Go source from both PRs had no overlap conflict. The generated index was rebuilt after merging both immutable PR histories. A new exact combined-head CI success is mandatory; original PR test success does not by itself qualify merged financial source.

## Strict C01 custody admission still OPEN

The code is not a production credential or signer. Physical acceptance requires checking actual installed binary, entrypoint, systemd/drop-in and owner-governance SHA; verifying the existing real reviewer key and recoverability without regenerating it; exact live Satchel/reviewer configs; restrictive service credentials; signature, nonce, expiry and replay denials; actual no-start/misconfiguration tests; and properly enrolled distinct technical signing/review identities under the C08 ONE-HUMAN governance policy. Two distinct technical keys are not a claim that two people exist. Neither a signed source review nor zero-funds admission is permission to execute a payment, create credit or enable native 8094/8095.

## Strict C05 reserve admission still OPEN

A bank-height witness against one operator validator proves internal height consistency; it is not an independent consensus quorum or a pledge of unencumbered assets. Earlier native observations showed the dedicated prospective reserve vault had ZERO eligible pledged collateral. Complete liability review includes 2,453 historical claim rows, the 97 pre-current-mainnet unindexed hash groups, multiple claim references to indexed single native transfers, economic-key overlap, the separately paid/reversed claim #822, bounty/staking unpriced exposures, and all producer obligations. None may be erased or silently classified paid. Gross wallet balances are not eligible reserves.

Before C05 closure, produce a complete disjoint bounded claims/liabilities ledger across producers, unique economic-key proof and vault-versus-escrow nonoverlap, authenticated current H/H+1 native bank proof against an operator-pinned trust anchor, exact exclusive unencumbered collateral pledge/ownership and gas cushion, then a fresh canonical review binding both distinct technical signatures, reserves and liabilities within its short validity window. The portable off-host verifier must replay bank height, signatures, source/journal pins, reserve arithmetic and expiry. A source merge, single-node signature or old bank census does NOT close C05 or permit customer credit. No new pledge amount/source account is presently established by this document.

## Other hard dependencies; no funded authority

As of the read-only November 10 HEL1 review, native validator PID1009 was active and stable; dedicated C01 Satchel/reviewer units were INACTIVE PID0; financial ports 8092–8095 were ALL CLOSED; live R25 at 3032 PID465815 correctly returned protected betting HTTP503; Steam V18 was held pending a separately reviewed V19 source-pinned 3031 retirement repair. The formally accepted Chain scoreboard is C04/C08 CLOSED, C01/C02/C03/C05/C06/C07/C09 OPEN.

C02 requires the actually restricted finance-owned durable operation journal and a genuine one-POST/GET-only native transport; C03 still requires physical HD/DE financial writer fence and authenticated App rollback; C06/C07 require one complete, identical off-host financial/chain checkpoint and real restore; C09 requires separate exact one-use owner signature on a transaction-bound canary only AFTER earlier gates close. The Intel Mac Storage OS PILOT restore is not a C06/C07 database/Chain disaster recovery test.

## Release policy

Keep PR #243 draft until its combined exact HEAD is green for Foundation, native Go, reviewer, C03/C07 negative controls and docs, with an independently reviewed nonfinancial runtime separation. Then an authorized merge is only SOURCE acceptance. For formal C01 or C05 closure, require exact installed hashes, real timestamped physical and adversarial receipts, reversible installation evidence, individually signed owner approvals where called for, and a gate-specific acceptance post to WoloChain issue #239. Never reset the chain, reactivate legacy 8092/8093, grant App raw finance tables, waive claims or broadcast funds to make a CI test green.
