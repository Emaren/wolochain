---
id: "aoe2war.wolochain.c01-authenticated-historical-merged-pr-source-ci"
title: "C01 Immutable Source CI: Recovering Authenticated Merged Pull Request Provenance"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain"]
audience: ["operators", "developers", "financial-reviewers", "ai-agents"]
source_of_truth: "git"
authority: "c01-source-provenance-nonfunded-candidate-review-not-custody-approval"
reviewed_at: "2026-11-08"
review_interval_days: 7
sensitivity: "restricted"
---

# C01 Immutable Source CI: Recovering Authenticated Merged Pull Request Provenance

## Real production blocker, not a compiler defect

The existing `c01-enrolled-escrow-runtime` artifact profile pins the genuine fixed source SHA `93e51f24acdc2a88af80b1b0d3b1db808701de8e`. It is a distinct source from the C02 native return checker and reviewer `f7b5a749...`; changing the artifact label or using the current builder branch binary as C01 would be unreviewed.

An explicitly owner-authorized GitHub Actions `workflow_dispatch` at HELD Chain source `fix/c01-producer-review-20261104` on November 8, 2026 produced [run #42496258634](https://github.com/Emaren/wolochain/actions/runs/42496258634). It correctly **failed before any build** at `SOURCE_CI_HOLD reviewed source PR missing or ambiguous`, because GitHub's old *successful* exact-source CI runs now contain `pull_requests: []` once the original pull request was merged. Existing verifier demanded exactly one live attached PR association and consequently treated authenticated historical source CI as absent.

Authenticated GitHub CLI independent observation confirmed:

- Fixed reviewed source `93e51f24...` is in the **actual 28-commit list of merged PR #124**.
- PR #124: repository ID `990989676`, PR ID `5112667912`, old source head branch `codex/c01-executable-deadline-repair-20261101`, original base SHA `75743d4ef6574226d5b6244ad45150ccd92d4171`, original head `464907a723080dea015297d9bba5380ea73b04cc`, merge commit `c1e14d7e82abe939675b161d34407fce3f7292c6`.
- Exact-source `ci.yml` run `41479070158` and `epoch-escrow-v3.yml` run `41479070152` both **completed success** on original SHA, but both report `pull_requests: []`.
- The present HELD Chain builder branch contains both the original source SHA and merged PR #124's merge commit as real Git ancestors; the source-to-builder history now exceeds **300 commits**. The old fixed `<=250 commits` comparison rule also would reject the legitimate current builder.

## Audited repair: independently authenticated fixed PR, no green-run fallback

`scripts/settlement-artifact.py` now supports exactly ONE additional fail-closed GitHub evidence path when and only when a reviewed successful exact-source run explicitly has `pull_requests: []`:

1. Authenticated `GET /repos/Emaren/wolochain/pulls/124` must return the exact existing hardcoded PR number, ID, repository ID, original source/base branches, pinned base SHA, real closed/merged state and canonical merge SHA.
2. Authenticated `GET /pulls/124/commits?per_page=100` must return a **complete** list of the PR's at most 100 commits, count matching the PR itself, with no duplicate SHA, source SHA occurring exactly once, and last SHA matching the PR head. The user cannot select a new PR, external URL, source SHA, merge SHA, or signer identity.
3. Two independent authenticated GitHub Compare API ancestry proofs bind `original source ... current exact builder` and `original merged PR SHA ... current exact builder`. The API provides `merge_base_commit`, `behind_by=0`, and `status=ahead`; the verifier requests **page 1 and exact page `total_commits` with `per_page=1`**. The final page must contain the *exact builder SHA*, preventing truncated 250-commit responses from being mistaken for a complete head proof.
4. Both CI workflows must still be completed/successful, be the exact fixed workflow identities, exact original source SHA, genuine pinned repository, matching historical PR identity, unchanged head branch and current GitHub build event IDs. A single missing/pending/failed/newer source run or branch identity mismatch **still fails**.
5. The historical path is NOT used when `pull_requests` is missing entirely, when nonempty attachments are ambiguous/foreign, or when the two source CI workflows disagree on context. Existing normal live-PR receipt checks and all previous historical source pins remain unchanged.

All GitHub responses are retrieved through the existing authenticated, no-redirect, no-proxy, 2-MiB-per-response, finite-time source verifier. No extra credential is put into the artifact or logged.

## Physical owner M1 proof

Live authenticated GitHub verification, using the owner's existing authenticated GitHub CLI token **only as an ephemeral local environment secret**, returned:

`PASS_C01_AUTHENTICATED_HISTORICAL_GITHUB_PR_CI_PROVENANCE 93e51f24acdc2a88af80b1b0d3b1db808701de8e`

Two exact-source CI runs authenticated (IDs above), `merged_pr_ancestry_authenticated=true`, source-to-builder depth **305** at observation, `production_authorized=false`. This is a *real external GitHub evidence check*, not a hermetic fixture or an owner-made-up source receipt.

The source change adds separate adversarial tests for broken merge identity, spoofed repository/PR IDs, missing/duplicate/out-of-order source commits, wrong branch, nonmerged PR, substituted comparison builder SHA, inconsistent first/last GitHub ancestry pages, zero/overlong commit ancestry and failure to infer any funded permit. It preserves 32 original immutable artifact-profile tests.

## Next exact C01 candidate step

After source-head GitHub CI passes and the held branch is merged, re-dispatch the existing **nonfunded** `custody-backend-satcheld-exact-artifact.yml` with reviewed `profile=c01-enrolled-escrow-runtime`. The workflow has a pre-build gate that must authenticate the two source CI runs, then runs the pinned Go 1.24.6 full/race tests and two independent fresh-cache builds. Only the successful GitHub artifact ID/digest, manifest, authentic source+CI receipt and exact executable can qualify a staged **UNDEPLOYED** C01 binary. No workflow identity may be fabricated.

Live HEL1 still has root-owned but **empty** `/etc/wolo-financial-c01` and inactive `wolo-satchel-c01.service`/`wolo-reviewer-c01.service`; neither missing `custody.json` nor `reviewer.json` can be substituted by the owner-printed historical CI. Exact independent custody/reviewer keys and reserve approval, C03 live writer containment, C04 chain finality, C05 same-height solvency, C06+C07 backup/recovery, current C08 ratification, and separate C09 amount/recipient/nonce permit remain mandatory.

**No private keys, customer WOLO, bank, database permissions, systemd services or production financial funds changed**. This fixes only the real historical source CI provenance-bound candidate blocker.
