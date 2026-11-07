---
id: "aoe2war.wolochain.c08.single-owner-public-notice-hold"
title: "C08 Single-Owner Public Notice — Pinned 24-Hour Financial HOLD"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["operators", "developers", "financial-reviewers"]
source_of_truth: "git"
authority: "public-notice-source-integrity-only-no-financial-permit"
reviewed_at: "2026-11-07"
review_interval_days: 7
sensitivity: "internal"
---

# C08 Single-Owner Public Notice Source Guard — Financial HOLD

WOLO has **one human financial owner**. That person controls custody,
reserve assessment and activation approvals; this is centralized oversight,
NOT independent human review. Separate computers and technical credentials
do not establish human independence. The old five-human financial permission
contract is not silently replaced. Real financial source and backing gates
C01 through C09 remain HOLD until separately accepted.

## Public publication and immutable source identity

The reviewed public notice is
https://github.com/Emaren/wolochain/issues/184
on the **public** Emaren/wolochain repository, created by Emaren at
`2026-11-07T10:22:33Z`. The exact original notice Markdown body SHA256 is
`b17206bc8b693b1777cd4a3ceef53f81f62f18668a6ebd2c2b8d793bd3146223`.

Its earliest possible 86,400-second completion is
`2026-11-08T10:22:33Z`. That timestamp is **not a funded release time**:
a changed or withdrawn proposal may require new notice, and separate
runtime policy implementation, recovery, liabilities, reserves, custody,
witness, and transaction-specific owner authorization must pass.

The no-credential observer
`scripts/settlement_solo_owner_public_notice_hold.py --inspect` uses
read-only authenticated GitHub CLI `gh api` to re-fetch the issue and
repository visibility. It rejects private repositories, missing/closed
issues, wrong author/URL/creation UTC, altered body SHA, duplicate JSON
keys, future clocks and unsound API responses. It cannot inspect owner
custody or call WOLO chain/financial services.

Before 24 hours it emits `HOLD_PUBLIC_NOTICE_24H_STILL_RUNNING`.
At or after 24 hours it emits
`PASS_NOTICE_TIME_ONLY_ALL_FINANCIAL_GATES_HOLD`.
**Both return exit 3/HOLD for financial activation.** Any authenticity
failure returns exit 2/STOP. Nothing in either result approves funding.
The script is NOT a financial permit, public-notice ratification,
independent signer, bank root or reserve proof.

## Financial release and test policy

The mandatory Foundation CI step executes the hermetic observer regression
suite under `tests/test_settlement_solo_owner_public_notice_hold.py`.
It checks exact period boundaries, substitute issue/author/repository,
mutated body, missing/duplicate JSON, forged clocks, and permanent
`financial_release_authorized=false`.

C03 writer containment, C06 exact coordinated encrypted backups, C07
real same-source restore, C04 UNKNOWN payout adjudication, C05 authentic
full non-additive liability/reserve coverage, C01 native custody,
C08 one-use witness and C09 separately confirmed owner transaction permit
remain mandatory. Legacy 8092 cannot serve as a new Satchel 8094 fallback.

The owner-device NONFINANCIAL governance-direction receipt SHA256 is
`3951e77f153e9a7b9ca27fa17548d67521cd55cc61489b5b612d0ecde843aca4`.
It was automatically signed under owner instruction and is not a
contemporaneous human-authorized WOLO spend.
