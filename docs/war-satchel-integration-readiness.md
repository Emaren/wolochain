---
id: "aoe2war.wolochain.satchel-integration-readiness"
title: "War Satchel Integration Evidence and Operator Handoff"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "git"
authority: "source-integration-proof-not-production-approval"
reviewed_at: "2026-10-21"
review_interval_days: 14
sensitivity: "restricted"
---

# War Satchel Integration Evidence and Operator Handoff

## Reviewer fee and reserve composition, October 29

The current continuation supplies `NewReviewerReserveCensusSource` for the
existing independent reviewer. It joins an actual read-only HD ledger query,
current native H/H+1 vault proof, the custody journal fee checkpoint and the
issuer's private in-process issuance checkpoint. A protected signed inventory
must bind the exact operation, original reservation fingerprint, booked
principal, source journals, complete producer set and non-overlap assignment.
Distinct enrolled accounting and custody reviewers must sign that inventory;
execution, wager and withdrawal role keys must also remain distinct. These
public signatures attest the reviewed source inventory; they cannot establish
physical operator independence or discover an omitted external liability.

`POST /satchel/v1/custody/fee-checkpoint` is private and read-only. Its requested
IDs affect status lookup only: every unresolved custody fee remains included.
Expired signed issuer approvals and crash-PENDING records remain obligations.
Only matching authenticated original fingerprints can deduplicate an issuer
fee against the actual custody journal. No expiry or empty caller list releases
UNKNOWN. Reads are bounded, bank/ledger/review identities are checked again at
completion, and changed, stale, future or unavailable evidence returns HOLD.
The fixed loopback custody reader has no proxy, redirect or retry path. Coverage
is reread from an owner-only protected file for each census.

The added mandatory tests validate genuine isolated SDK bank evidence and
signed test reviews. The existing isolated PostgreSQL CI job additionally runs
`TestReviewerFinancePostgresReserveCensusSignsOnlyWithActualIndependentSources`
through the actual `ReviewOne` call and durable issuer checkpoints. Its
owner/Watcher adapters and financial reviewer keys are explicitly test-only;
its signature is a reviewer grant and performs no Cosmos signing or broadcast.
The source increment requires new exact-head CI and does not install 8095,
provision production authorities, approve any real inventory, or complete the
separate principal-discharge and claim-return execution path.

## Principal and escrow-return evidence continuation

The reviewer daemon now requires the actual owner partition in its dual-reviewed
census. The typed `principal_spend` value binds the original reservation,
consent, owner ledger and complete custody/hold partition; it is reread at
completion. Historical review bodies without that optional value retain their
old non-authorizing library contract. This does not yet relax the custody
spend guard: post-attempt principal revalidation and permanent consumption
remain required before customer principal can be spent without extra equity.


The principal partition reader now reconciles each owner’s complete wager and
withdrawal holds against all four journal buckets under a genuine read-only PG
snapshot. It compares complete custody history on both sides of the query and
refuses unresolved operations or a native-confirmed outflow not posted in HD.
The private fixed-peer checkpoint transport pins the configured vault and policy;
its JSON is service provenance, not independent chain proof. The opaque partition
result still grants no principal allowance until separately bound to the signed
inventory and revalidated at the actual execution phase.

The escrow-return inventory verifier reauthenticates native H/H+1 bank proof
against its protected anchor and requires both reserve reviewers, exact producer
pins, full unpaid entitlements, non-overlap and uncertain gas coverage. Paid
entitlements require their actual native transfer proof, rather than a shaped
journal receipt. The original allocation’s bank digest stays immutable while the
execution bank changes. A selected payout is already one booked liability; its
principal is not charged again as extra equity. Tests use real isolated SDK
7-WOLO funding, 2-WOLO separate escrow assets and 5+2 return entitlements; they do
not establish production custody or the missing legacy pre-sign executor guard.

## Controlled OS-process qualification, October 21

Implementation `32f0d73d4509db074b5baf095c2338cb27c35132` adds
`internal/satchelservice/native_http_execution_test.go`. It runs the production
private HTTP server, encrypted SDK file keyring and durable engine in a separate
test process. An isolated SDK application commits the actual signed 7-WOLO
wager, and the test kills only its signer child with SIGKILL before the RPC
acknowledgement. After reopening the same journal and keyring, four concurrent
retries retain UNKNOWN without signing or broadcasting. Portable proof retrieval
leaves that hold unchanged; explicit authenticated read-only reconciliation
alone confirms the original transfer.

The fixture supplies real retained SDK bank proofs and signed continuous Comet
headers. Offline verification binds the exact owner, reservation, native fee,
recipient, amount, memo and transaction bytes. Identical-byte SDK replay fails
ante sequence validation. Vault `2,997,500 uwolo`, escrow `7,000,000 uwolo` and
fee collector/distribution `2,500 uwolo` conserve the initial `10,000,000 uwolo`.
Wrong bearer, signer role, owner, recipient, amount, fee and approval role fail
before signing. A competing process cannot acquire the active keyring lease.
Revoking the fixture permit stops submissions while proof reads and recovery
remain available; the custody capability stays UNAVAILABLE.

Run `go test ./internal/satchelservice -run '^TestNativePrivateHTTPServiceSDKRecovery$' -count=1`
to reproduce. At that source, full Go tests passed 1,799 tests including subtests
with seven existing skips; the targeted keyring/native SDK/HTTP race suite passed
12 tests including subtests. Service/command vet and independent source review
passed. The test is part of the existing repository CI, including its custody
execution race job.

This is a controlled Go test process on an ephemeral loopback port, **not** an
execution receipt for the pinned Linux release artifact or mainnet. Its signed
permit is bound to the test executable and synthetic evidence only. The two
local proof endpoints share one isolated validator; they do not establish
independent production operators. No mainnet key, transfer, installation, service
restart, app ledger or financial activation is exercised. The pinned artifact,
legacy services, outstanding liabilities and protected release holds remain
separate requirements.

## Authenticated bridge continuation, October 17

The [financial bridge](war-satchel-financial-bridge.md) at implementation
`155fcf67fb2127a2227de5ea785e51bdbb0155c0` now exports real portable Comet
evidence and verifies it offline against operator-owned trust and separately
stored expected owner/economic/hash context. New withdrawals require exact HD
Keplr consent plus the independent reservation approval. Signed v2 per-leg
conservation checks are reused. The [shared artifact profile](war-satchel-exact-source-artifact.md)
builds that exact composed `wolosatcheld`; it cannot be confused with the legacy
`526d5eb6` binary.

The frozen source passes 1,320 Go tests including 271 top-level tests, with five
existing skips. Node crypto independently verifies the signed wire fixtures;
real isolated SDK execution feeds the actual offline verifier and rejects forged
owner/hash/root/REST evidence. Production is still BLOCKED for every financial
flow. HD #638 at `c4fd91e548042807fb02c000f7360e87efa4801d` retains its hold and
has not consumed this new bridge. See [fresh live identities and controlled
release gates](war-satchel-controlled-release.md) for the finite remaining
operator prerequisites. The composition-baseline observations below remain
history; no earlier source-green report is a live activation receipt.

This source combines unchanged PR #25 at `42ecb12c130b383677f913112baa07debd52a5ab`
with PR #26 at `526d5eb6123f6cc0394b5e78489c668e77e46106` in an isolated branch.
Neither original branch is modified or merged by this proof. There were no Go
source conflicts. Both runbook entries are retained and generated documentation
is resealed to the combined ancestry. One old parser-only return fixture used an
invented address: the new checksum guard correctly rejected it. The fixture now
uses deterministic, checksum-valid public test bytes; no guard was weakened.

Full normal and race Go suites each passed **1,216 tests including subtests**
(246 top-level tests), with five existing skips: four application simulations
and the private-file foreign-owner fixture that requires root. Both command
binaries build; vet, source-only invariants and protobuf checks pass. The
Satchel source-proof workflow also runs for this stacked integration target.
These source results do not attest any public deposit or live financial flow.

PR #27 independently builds the **legacy implementation at 526d5eb6**, not this
combined source or a deployed 8094 signer. Its two-build manifest and externally
anchored archive/manifest/binary digests are separate from runtime approval.
Historical `bdbce253` artifacts and `78c25985` runtime observations remain dated
history. No source, artifact or migration-frontier success proves live custody.

## Actual flow status

| Flow | Source evidence | Remaining production gate |
| --- | --- | --- |
| Deposit | Exact wolo-1/uwolo intent, receipt uniqueness and authenticated chain-reader negative tests exist. | Independent vault control/reserves, complete HD ledger installation and trustworthy credit bridge; C2 remains UNAVAILABLE. |
| Auto-bet | Active HD 8094 Bearer request/acknowledgement matches Go health and one-shot wager routes. Go denies uncertain/replayed execution. | Provisioned isolated signer/journal, ADR-36/Watcher/owner/cap proofs across the deployed app and signer, revocation canary. |
| Settlement/refund | Go v2 per-leg entitlements enforce shared-budget conservation, exact principal refunds, owner attribution and durable reconciliation. | HD does not yet consume this signed allocation/authenticated return bridge. Historical unmatched-fee adjustments require separate reconciliation and approval. |
| Withdrawal | Go requires a separate owner-bound mandate and independently signed WithdrawalApproval; uncertain outcomes stay held. | HD currently reserves and returns paymentConfirmed:false, without the independent approval/execution bridge. |
| Complete journey | Existing isolated Go HTTP, withdrawal, return and allocation contracts are executable tests. | No live deposit-to-withdraw canary, production DB receipt or runtime activation evidence exists. |

The exact HD review target was PR #638 at
`9a8f6b8a0717b4769f294f38ec228ab1997f4133`, still conflicted at observation.
Its active funded worker uses `warSatchelDedicatedSignerClient`, 127.0.0.1:8094,
Bearer authentication, `/satchel/v1/health` and `/satchel/v1/one-shot`.
Do not provision the unused 8194/HMAC alternative.

Two source blockers were reproduced and sent to the HD owner. At that exact
head, `lib/warSatchelCanonicalWithdrawal.ts:49` and
`lib/warSatchelCanonicalClaimReturn.ts:43` accept fabricated decoded MsgSend REST
objects with an invented hash and head, without obtaining actual transaction
bytes or authenticated committed-chain evidence. Durable callers are in
`lib/warSatchelFundedLedger.ts:921` and `:1069`. This is a future activation
blocker, not evidence of a current live credit. Go return reconciliation instead
requires opaque TrustedReader evidence and independently signed v2 allocations.
HD must consume the correct bridge and reject the forged-evidence fixture; do
not weaken Go or describe REST/status agreement as independent authentication.

The withdrawal route at `app/api/user/war-satchel/withdrawal/route.ts:145` only
reserves. Its owner consent does not substitute for Go's separate approval key.
An end-to-end owner mandate, independent approval, one-shot execution, restart
and authenticated reconciliation contract is still required. HD source remains
owned by its coordinator; this work makes no HD code or migration changes.

## One operator handoff, in dependency order

1. Finish the HD source bridges above, reconcile #638 with current main, and
   repeat its actual PostgreSQL and signed-consent/Watcher tests. The operator's
   reported `118/112/6/2` frontier is read-only evidence: six migrations remain
   pending. It is not a schema-rehearsal or installation receipt. Use the
   existing governed HD rehearsal and separately approved migration procedures.
   That six-file main-branch frontier does not cover PR #638's additional
   `20261017_012000_war_satchel_funded_ledger_foundation` migration. Obtain a
   fresh exact-candidate frontier/schema review and the appropriate protected
   receipt for that ledger too; installing six simulation foundations alone
   cannot establish the funded product.
2. Verify PR #27's final exact-head successful CI, archive digest, external
   receipt manifest digest, actual executable digest/ELF/Go metadata and source
   pin before considering that legacy candidate. Its binary is never the
   separately provisioned Satchel service merely because both are Go programs.
3. Obtain fresh runtime identities with the following **read-only** observation.
   Run it in the operator's existing privileged VPS shell; it installs nothing,
   reads no environment/keyring contents and invokes no candidate executable.
   Preserve its timestamped output privately. Failure means HOLD, not recovery.

```bash
(
set -euo pipefail
export GOTOOLCHAIN=local GOENV=off GOWORK=off
date -u '+observed_at=%Y-%m-%dT%H:%M:%SZ'
GO_INSPECT=$(command -v go || true)
[[ -n "$GO_INSPECT" ]] || GO_INSPECT=/usr/local/go/bin/go
test -x "$GO_INSPECT"
for unit in wolochain-mainnet-settlement.service wolochain-founder-rewards-settlement.service wolochaind-mainnet.service; do
  pid=$(systemctl show -p MainPID --value "$unit")
  [[ "$pid" =~ ^[1-9][0-9]*$ ]]
  before=$(stat -Lc '%d:%i:%s:%Y' "/proc/$pid/exe")
  printf 'unit=%s pid=%s active=' "$unit" "$pid"
  systemctl is-active "$unit"
  readlink "/proc/$pid/exe"
  sha256sum "/proc/$pid/exe"
  "$GO_INSPECT" version -m "/proc/$pid/exe" | sed -n '1p;/vcs.revision=/p;/vcs.modified=/p'
  test "$(systemctl show -p MainPID --value "$unit")" = "$pid"
  test "$(stat -Lc '%d:%i:%s:%Y' "/proc/$pid/exe")" = "$before"
done
for port in 8092 8093; do
  curl --fail --silent --show-error --max-time 5 --max-filesize 1048576 \
    "http://127.0.0.1:$port/settlement/v1/health" | python3 -c '
import hashlib,json,sys
d=json.load(sys.stdin)
assert d.get("ok") is True and d.get("loopback_only") is True
assert d.get("chain_id")=="wolo-1" and d.get("runtime_chain_id")=="wolo-1"
def fp(name):
 v=d.get(name)
 assert isinstance(v,str) and v
 return hashlib.sha256(v.encode()).hexdigest()[:16]
print(json.dumps({"port":int(sys.argv[1]),"chain":"wolo-1","payout_fp":fp("payout_address"),"escrow_fp":fp("escrow_address")}))' "$port"
done
)
```

4. Separately prove HD **and** DE ingress fencing, active-job drain and every
   alternative signer/writer route. A healthy endpoint, stable PID, empty table
   or absent lock is not a drain. Reconcile current reserves/liabilities and all
   pending/accepted/UNKNOWN obligations in both legacy lanes. Founder #889 stays
   held; do not retry it or repeat exhausted investigations without new evidence.
5. Establish exclusive state ownership and current private integrity-checked
   snapshots for both legacy lanes. Rehearse an independently approved paired
   controller/watchdog against the actual current/candidate identities. Preserve
   current request/run/receipt history; recovery remains QUIESCED_RECOVERY_ONLY.
   The obsolete rollback/rescue scripts remain disabled. Unchanged consensus
   identity is mandatory throughout; no shared-binary/node operation is allowed.
6. Independently provision and verify the dedicated 8094 vault/keyring, private
   auth, independent approval authority, trust checkpoint/witness and current
   durable journal. Never reuse legacy escrow, payout, founder or validator
   authority. No signer creation or installation is authorized by this document.
7. Only after those receipts and named approval may operators execute their
   reviewed protected cutover/migration stage and a separately approved small
   signed-intent canary. Verify actual observed binaries, chain receipts and
   owner ledger postings for deposit, caps/revocation, settlement/full unmatched
   refund and withdrawal before enabling player financial flags.

No deploy/rollback command is supplied while its prerequisites and authority
remain absent. On any mismatch, retain the live system; after an authorized
cutover keep producers fenced and use only the approved state-preserving
recovery procedure. Never restore historical financial state or retry uncertain
payments to manufacture a successful canary.
