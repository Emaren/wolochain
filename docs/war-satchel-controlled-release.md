---
id: "aoe2war.wolochain.satchel-controlled-release"
title: "War Satchel Controlled Release Gates"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "git"
authority: "source-integration-proof-not-production-approval"
reviewed_at: "2026-11-02"
review_interval_days: 14
sensitivity: "restricted"
---

# War Satchel Controlled Release Gates

## November 2 source and operating-control review

**Reviewer: Codex, acting under Tony Blum's explicit source-engineering and
review directive, November 2, 2026.** This is an automated, owner-delegated
source/documentation review by the implementation lane. No independent human,
custodian, reserve reviewer, production observer or wallet signer is claimed.
The document owner remains `wolochain-ops`. This review does not issue a
financial permit or renew an operational receipt.

Reviewed source is Wolo #115 → #122 → #123 → #124. The C01 implementation
reviewed here is `8529e5dd2bf647840308c608957b3ad16bbeb827`, sealed at
`c97470d85fe13496c6777fe19bf68ad08688731b`. The review checked the actual
[8094 HTTP route](../internal/satchelservice/http.go),
[enrolled escrow role](../internal/satchelservice/escrow_return_service.go),
[current reserve qualification](../internal/satchelservice/escrow_return_runtime.go),
[durable UNKNOWN journal](../internal/satchelservice/escrow_return_durable_spend.go),
[fixed-target CLI](../cmd/woloescrowd/execute_return.go),
[8095 reviewer](../cmd/woloreviewerd/main.go),
[artifact profiles](../scripts/settlement-artifact.py), existing six-control
[financial checklist](settlement-contracts/financial-release-checklist.json)
and [App Master Register #1108](https://github.com/Emaren/app-prodn/issues/1108).
App branches, live services, protected financial state and keys were not changed.

At this review, [native evidence #41383669730](https://github.com/Emaren/wolochain/actions/runs/41383669730)
succeeded at `c97470d`; [full CI #41383669778](https://github.com/Emaren/wolochain/actions/runs/41383669778)
failed because this document's previous October 18 review expired November 1.
That stop occurred **before** certification of the repaired production-binary
test. Native success does not override it; a new exact-head full/native result
is required after this substantive document correction.

The earlier executable failure at `9f40ae3` returned before durable intent,
with zero broadcasts and read-only recovery 404. Its fixture signed a reserve
review for approximately 110 seconds, beyond genuine native bank evidence's
approximately 30-second lifetime. The repaired fixture derives its review
expiry from that evidence; production freshness, expiry, reserve and custody
checks are unchanged. Current tests distinguish actual clean-built binary
execution/refusals from in-process native SDK post-sign drift, signing loss and
restart tests. Fixed boundary/status/context diagnostics disclose no raw
permission, credential, request body or transport error. Exact CI must confirm
the executable verdict before any source qualification claim.

**Physical scoreboard: C01–C09 all OPEN (9/9).** The previous qualified Wolo
and HD source heads are dated ancestor evidence, not present installation or
funded-product receipts. The unpublished `c01-enrolled-escrow-runtime` artifact
profile is still under review; its candidate pin has not qualified. Historical
`composed-satcheld`, `custody-runtime` and `integrated-custody-runtime` profiles
retain their original source identities and cannot represent C01 by renaming.
A source-CI receipt, archive or owner-delegated review cannot establish external
custody, independent reserve completeness, recovery or transaction signing.

| Operational control | Independently verified production status | Closure evidence and owner |
| --- | --- | --- |
| Complete producer fencing | HOLD | Chain/app operators: actual HD, DE, legacy and external producer census, build-bound signed maintenance lease, independently witnessed drain and safe resume. Source #116 is not a live fence. |
| Historical reconciliation | HOLD | Accounting/custody reviewers: original 100-WOLO intent and authenticated committed effect; explicit #889/#8477 and reused-hash disposition. UNKNOWN never permits retry. |
| Global liabilities/reserves | HOLD | Independent accounting/custody: complete nonoverlapping obligations, pending fees and uncertainty at fresh authenticated vault/escrow H/H+1 roots, account-local gas and cushion. |
| Quiesced protected backup | HOLD | Recovery lane E and operators: consistent current financial DB/WAL, journals, policy/config and service-state receipt after approved fencing. No provider decision or backup action is supplied here. |
| Independently witnessed recovery | HOLD | Recovery lane E and independent witness: isolated actual restore and state-preserving paired settlement recovery; source tests and website rollback do not substitute. |
| Authenticated release authority | HOLD | Independently enrolled custody, reviewer and owner principals: exact source/binary/config/policy, protected key roles, fresh nonce and distinct signed staging/activation authority. |

The `woloreviewerd` source HTTP contract exposes
`POST /reviewer/v1/wagers` under its separate protected startup permit. It reads
restricted HD/Watcher, bank, liability and pending-fee evidence; it is not a
transaction signer. There is **no automatic escrow-return-review endpoint** in
that surface. The 8094 return executor consumes an enrolled protected
`EscrowReturnExecutionBundle` file with both independent reserve signatures,
refreshed after preparation, plus a separate exact owner operation permit.
Producing/provisioning that genuine return review remains a required boundary;
no wager review, fixture signature or daemon-local fallback substitutes for it.

The financial deployment order is:

1. Qualify the existing protected C01 execution bridge with full exact-head
   CI, the actual clean-built `woloescrowd` → `wolosatcheld` subprocess and
   native SDK/HD evidence. Keep expiry/revocation, H/H+1 current-root checks,
   account-local reserves, signed byte identity and permanent UNKNOWN fencing.
   The App engineer separately qualifies C02: restricted HD writer/receipt
   consumption, migration 14, original Watcher/mandates and complete lifecycle.
   Communicate the interface through #1108; do not edit that engineer's branches.
2. Finish the distinct `c01-enrolled-escrow-runtime` profile using the existing
   builder. Pin the genuinely qualified source separately from builder/workflow
   identity; authenticate both exact-source CI runs and their reviewed PR
   context before two sequential fresh-cache builds. Retain compiler/package,
   clean VCS, reproducibility, archive/manifest/binary digests and the separate
   external GitHub receipt. Qualify the reviewer executable and its protected
   configuration independently; a `wolosatcheld` archive does not also certify
   `woloreviewerd` or the CLI. Historical pins must remain unchanged.
3. Obtain the six authentic operational receipts above. Prepare one reviewed,
   exact artifact/config-bound operator action and code-only rollback, then
   obtain the distinct owner authorization required for that concrete action.
4. Stage isolated 8094/8095 without funding or customer-route activation.
   Verify actual protected escrow/vault key separation, revocation, restricted
   HD writer identity and current native bank/journal coverage. Preserve
   consensus and original 8092/8093 identities; never use their legacy authority
   as an escrow-return fallback.
5. After explicit activation approval, request the selected owner's genuine
   Keplr deposit and profile-mandate signatures for at most **1 WOLO** from
   `wolo1wue7vyque2pssskgdrww0fcadlq9ps6mtn605e`. Written authorization is not
   either signature. No unrelated wallet supplies the canary principal.
6. Independently verify deposit/unique HD credit, authentic original-Watcher
   game observation, solo/team mandate admission, exactly one wager, settlement
   or refund, return/withdrawal, user-visible history and full journal/bank
   conservation. Retain UNKNOWN after any ambiguity; recover by read-only
   proof inspection and never blind resubmission. Enable the reviewed funded
   product only after these receipts and production health/rollback checks.

No source-pinned C01 production installation/start action has qualified:
protected escrow enrollment, final artifacts and independent physical receipts
are not established. Source
work does not need another general owner permission. The next eventual owner
action is the concrete source-pinned staging/activation approval after those
prerequisites, followed by actual Keplr signatures. F's website release remains
independent throughout this sequence. Financial verdict remains HOLD.

Historical source lineage begins with the combined source in draft
[PR #38](https://github.com/Emaren/wolochain/pull/38), initially
`68cdc1ae2f1c877f40e7ee3f8c094729f080394f`; the
[source-bound index](DOCUMENTATION_CONTROL_PLANE.md) identifies the current
implementation. Its [versioned HTTP contract](settlement-contracts/war-satchel-http-v1.openapi.json),
[financial proof interface](war-satchel-financial-bridge.md) and
[artifact verification](war-satchel-exact-source-artifact.md) are source contracts.
The user reports the website deployed at app commit
`5aecab73cdd7aee4bae7df78e56ab31942c13643` on October 18 with financial funding
and automatic wagering disabled. This WoloChain change neither modifies nor
independently certifies that app release. A visible UI, green source CI and
HTTP `consensus_authenticated` fields do not authorize custody or ledger credits.

The production observations below are **dated receipts**, not a new live audit
or a claim that they remain current. The candidate requires a fresh bounded
identity/financial receipt immediately before protected execution; unresolved
liabilities stay held until independently proven otherwise.

## Historical website-only schema contract: separate authority

The [website HOLD evidence v1 schema](settlement-contracts/wolo-website-hold-evidence-v1.schema.json)
is the Wolo-side observational contract originally supplied for an app-owned
website-only lane. Its schema alone does not implement or authorize a release.
The former `7ee1606a` candidate and historical `bdbce253` source-authority gate
are dated context, not today's app release instruction. Current nonfinancial
website admission, F/G/Nginx and public deployment belong exclusively to the
App engineer and #1108. An unresolved Wolo financial gate must not be used here
to block that independently qualified website release. Every financial and
custody authorization in this Wolo handoff remains false.

The consumer must independently authenticate the operator channel and exact
observer source/hash, and pin an externally reviewed immutable baseline outside
candidate-supplied JSON. It must retain the complete original source-authority
receipts, compare both settlement and consensus PID/executable identities and
source/configuration/hold digests before and after release, and preserve every
unresolved hold. Ignored-content counts alone cannot establish identical content.
Schema-valid hashes or `verification_required` fields authenticate nothing.

The app owner must separately implement reviewed candidate-scope admission,
binding deployed/candidate commits, artifact, policy and unique release attempt.
That policy must reject financial behavior changes, including transitive build,
configuration or deployment effects; missing, ambiguous or unauthenticated scope
evidence refuses admission. A unique controller-generated challenge, bounded
freshness checked again after I/O, cross-field equality and a durable attempt
store are required consumer controls, not guarantees provided by JSON Schema.
No baseline replacement, removed blocker, changed runtime or copied receipt may
be accepted as a fresh release. Existing inventories cannot certify signer
isolation, complete liabilities, reserve sufficiency or claim #889 outcomes.
These remain independent operational evidence requirements. No Wolo-only change
authorizes the app deployment or certifies preservation of live financial holds.

The v1 consumer must reject documents above 64KiB, duplicate JSON keys and
non-finite numbers before schema validation, enable date-time format checks,
and reject unknown fields. Receipt hashes mean SHA-256 of exact retained bytes,
not a JSON reserialization or a replacement digest supplied by the candidate.
Private source/configuration/hold manifests must cover actual content and signer
boundaries; they must already exist and be independently reviewed. The current
source-authority observer does not collect those complete private manifests.
Do not fill missing identities with counters, constants or an empty-set hash.
The reviewed app policy must fix observation freshness and release-window
bounds, recheck age after I/O, compare every attempt/candidate/baseline identity,
and durably fence attempts before changing anything. No such admission receipt,
complete baseline or app-controller implementation is produced by this change.

Contract tests use a synthetic, explicitly nonauthorizing fixture. Run them with
`python3 -m pip install -r tests/requirements-release-evidence.txt` then
`python3 -m unittest discover -s tests -p 'test_website_hold_evidence_contract.py'`.
The tests deliberately demonstrate that schema validity alone does not enforce
cross-field equality, freshness or authentication. The future controller must
refuse those semantically invalid inputs even when their shape is valid.

## Historical October 17 read-only production receipt

The [machine-readable receipt](settlement-contracts/satchel-live-readonly-20261017.json)
records the observations below. At 2026-10-17 20:57 UTC, existing SSH access
was used only for bounded reads:
systemd MainPID/health, `/proc/PID/exe` hashes and Go metadata, and bounded
aggregate request/run JSON inspection. No environment, keyring or secret file
was read. No candidate binary was installed or executed on the VPS. Each
executable's inode/size/mtime and MainPID were checked before/after inspection.

| Service | PID | Executable | Actual embedded source |
| --- | --- | --- | --- |
| Legacy 8092 | 1012 | `/usr/local/bin/wolochaind-mainnet` | `78c25985420ee41a6678c42fab8ea8d6c3b1b519`, modified=false |
| Founder 8093 | 1010 | same settlement executable | same clean source |
| Consensus, observe only | 1009 | `/usr/local/bin/wolochaind-mainnet-node-prewartrophy` | `d3bd62414a047a492a3814b7d3baa2717d64db2e`, modified=true |

Both actual settlement executables hash to
`040126a2884946caf1651a50b7d8115c5a6fb2d5aa94fcbbe150694602d451a5`.
The separate historical consensus executable hashes to
`4b77f622191db7550cb87cafb8f1886a0aadebee3eb6565f9f90036f809e61d3`.
8092/8093 reported healthy literal-loopback `wolo-1`; 8094 had no listener.
Payout address fingerprints differ (`d22311cf4725e370` versus
`84f8e23234b72262`), while both health reports identify the existing betting
escrow fingerprint `5712f9536e3e5c94`. That escrow is excluded from Satchel
vault custody. Fingerprints are observations, not proof of independent key
control or permission to transfer funds.

Health reported balances in uwolo: 8092 payout `397509250000`, founder payout
`356787241424`, shared escrow `826173750000`. These unauthenticated service
observations are **not** complete reserve provenance or solvency. A separately
attempted local REST balance query was unavailable; no independently proven
bank/liability reconciliation was obtained.

At 20:59 UTC, 8092 had 910 request records (904 confirmed, five failed, one
accepted) and 784 run records (780 confirmed, three failed, one accepted).
The accepted request records `100000000` uwolo. Request and run records may
refer to the same obligation; they must not be added as separate liabilities.
8093 had 646 requests (609 confirmed, 37 failed), with no run directory.
Both observed lock directories were empty. This is a nonexclusive observation,
not an ingress fence, stable snapshot, proof of no in-flight writers, or a
complete liability inventory. **Never retry an accepted/uncertain record.**
Founder claim #889 was not individually investigated or replayed; its separate
financial hold remains unchanged.

## Dependency order for operator execution

1. Independently accept the final C01 source and both exact-head CI receipts,
   including the production executable test. After the distinct C02 artifact
   profile qualifies, authenticate its immutable source/builder/workflow and
   archive/manifest/binary digests using the shared offline verifier under
   `--profile c02-native-return-check-runtime` for the check-capable runtime.
   Missing exact profile, source CI or external artifact receipt keeps
   installation on HOLD. The original C01 artifact preserves its frozen pin.
   The legacy `526d5eb6` artifact remains a separate `wolochaind` candidate.
2. HD must consume the portable proof through a pinned offline verifier using
   its own operator-provisioned anchor and stored intent, verify signed v2
   allocations and owner withdrawal mandates, and atomically consume both
   physical transaction identity and obligation under its ledger fence. Keep
   the activation hold until that implementation and adverse tests are reviewed.
3. Obtain current reserve/liability and independent vault-control evidence.
   Provision the distinct 8094 OS account, keyring, approval boundary, private
   token, journal, network sources and independently authenticated checkpoint
   and witness through the operator's separate governed process. Never derive
   a trust checkpoint from a proof response or reuse 8092/8093/consensus keys.
4. The app owner must supply exact current schema/frontier, successful protected
   shadow and real-data backfill evidence, globally unique receipt consumption,
   owner reservation and complete lifecycle integration. Earlier seven-migration
   receipts predate the subsequently extended app schema and cannot authorize its
   current financial installation. WoloChain neither executes app migrations nor
   resolves the app's previously reported schema-equivalence hold.
5. Before any legacy replacement, fence HD and DE ingress and all alternate
   financial writers. Reconcile accepted/unknown requests and complete
   liabilities without rebroadcast. Prove exclusive current state ownership,
   checksummed current snapshots and an approved state-preserving paired
   rollback/recovery procedure. Keep #889 held. Consensus PID/executable remains
   unchanged throughout; retired rescue/rollback scripts stay retired.
6. With named operator approval, execute only the separately reviewed protected
   settlement cutover and schema installation. Provision the isolated signer
   at a versioned path from its exact qualified C01 artifact. Independently
   qualify the distinct 8095 reviewer artifact and protected review boundary. No installation,
   key creation, service restart or financial activation is authorized while
   the preceding evidence is missing. The concrete operator packet below is
   an admission requirement, not permission to execute it.
7. A separately approved small canary must prove exact running binaries,
   authenticated deposit, owner/cap/revocation behavior, no double reservation,
   settlement, full unmatched principal refund, partial matched allocation,
   owner withdrawal and restart/UNKNOWN recovery. Freeze producers on any
   mismatch; retain holds and current journals for read-only reconciliation.
   Recovery must preserve the latest financial history, never restore an older
   journal or manufacture success by retrying an ambiguous payment.

## Flow status at this source milestone

| Flow | Production status | Actual remaining prerequisite |
| --- | --- | --- |
| Deposit | BLOCKED | Independently reviewed current app proof/receipt integration and protected schema admission; independent vault/reserve/trust provisioning |
| Signed auto-bet authorization | BLOCKED | deployed owner/ADR-36/revocation/Watcher proof; held source permits at most 10,000 WOLO per newly authorized wager and 50,000 WOLO per owner-signed daily Auto Bet cap; independently configured signer limits and every existing smaller mandate remain binding |
| Automatic betting | BLOCKED | dedicated signer runtime plus HD reservation/concurrency/mandate integration and canary |
| Settlement | BLOCKED | qualified distinct 8094 escrow return execution, signed original allocations, independently signed escrow reserve review, restricted HD proof/credit and complete liabilities/drain; any legacy replacement remains separately governed |
| Refund | BLOCKED | HD signed v2 allocation + authenticated proof consumption; full unmatched principal remains mandatory |
| Withdrawal | BLOCKED | HD owner-mandate/independent approval worker, durable reservation proof and authenticated finalize/recovery consumer |

No end-to-end production financial canary or new production deployment is
claimed. C01–C09 remain OPEN; a portable native proof is noncrediting until
HD independently verifies the stored intent and atomically consumes its global
physical receipt identity. Source CI and reproducible artifacts cannot clear
physical custody or release gates.

## C07 historical journal-only restore — 2026-11-04 (still HOLD)

The separately staged `scripts/settlement_archived_journal_restore_drill.py`
performs a **real isolated, root-only restore of an already archived and
checksummed settlement journal**. It is intentionally not a backup of
current production. The exact source checks the archived primary, founder and
six config/unit manifest entries, rejects symlinks, unexpected journal files,
path traversal, duplicate or changed hashes, then copies ONLY journal JSON to
the dedicated mounted recovery filesystem. It verifies all restored bytes,
fsyncs and atomically publishes a restricted receipt. It never copies
protected environment/config, keyrings, custody keys, signer binaries,
PostgreSQL, or WAL; never starts a service or performs a network call.

The 2026-10-23 HEL1 archived snapshot produced an intentional exit **3 HOLD**
with **1,750 primary + 646 founder = 2,396** journal files restored. A
separate, independent root rehash of all restored files validated the archival
manifest content, restricted modes and unchanged original consensus/8092/8093
service PIDs. The archive is older than current production. This proves a
bounded **archived journal rehydration mechanic**, not a current backed-up
financial state. No current financial table, WAL, reserve, fee, pending claim,
customer obligation or historical authority is reconstructed from that output.

C06 requires a new *consistent, encrypted, independently recoverable* current
HD+DE PostgreSQL/WAL, primary+founder journals, policies, config and custody
metadata snapshot **after an actual authorized all-producer fence**. The
previous attempted live `pg_basebackup` was blocked by execution safety
control; this journal-only drill is not an alternative attempt at that blocked
backup. C07 requires a separate independently witnessed restore of that
same current consistent snapshot and paired rollback, without rebroadcasting
UNKNOWN. Thus **C06 and C07 remain OPEN** regardless of this drill's success.

## Native C01 confined service HOLD templates — 2026-11-04

The tracked `deploy/systemd/wolo-satchel-c01.service` and
`deploy/systemd/wolo-reviewer-c01.service` are **static, nonenabled** units
for the separately qualified native binaries pinned to
`f7b5a74928e041a6a90ac983d87649e0484677a4`. They run as the distinct
`wolo-satchel` and `wolo-reviewer` service accounts, have independent 0700
state directories, strictly read-only system mounts and write access limited to
their own state, no inherited Linux capabilities, no automatic restart, and
loopback-only network permission. There is no Nginx or consensus dependency.

A `ConditionPathExists` check for each protected operator-config path is
**NOT a permit, signature, custody key or authenticated chain checkpoint**.
The runtime itself must validate exact binary/config/source/reviewer identity,
trust anchor, live reserve inventory and short-lived signed permissions.
No real protected config, reviewer authority or actual operation permit is
installed by these templates. Do not `enable` or `start` them under the
currently held financial release; copy only as reviewed, hash-verified
nonexecuting artifacts until C03–C08 physical acceptance exists. Do not
broaden egress from loopback without a separately reviewed independent
checkpoint proxy boundary.

## Protected installation admission — no current activation action

The former single-daemon installation example is withdrawn from the current
C01 path: it lacked the final C01 artifact, distinct 8095 qualification and
transaction-specific escrow enrollment now required by source. It was never a
production receipt. The following existing-source boundaries define the next
concrete action packet; they do not install or start anything:

- Independently authenticated C01 source/full/native CI and reviewed artifact
  source/builder/workflow identity, immutable archive ID and digest, manifest
  digest, binary digest, compiler/package provenance and reproducibility.
- Exact service unit, versioned binary path, dedicated EUID, network policy,
  protected configuration digest, existing separately provisioned vault and
  escrow keyrings/unlock files and public identities. No legacy or consensus
  keys; no key creation/export by the runtime or CLI.
- Genuine independent checkpoint/witness and fresh account-local H/H+1 bank
  evidence. The configuration-only `--check` output `TRUST_UNCHECKED` does not
  authenticate chain trust or authorize service start.
- Distinct independently qualified `woloreviewerd` source/binary/configuration
  on 8095 with its restricted PostgreSQL principal and genuine wager-review
  inputs. Separately require complete liabilities/pending fees and the dual-signed
  escrow reserve review covering the **post-prepare** current journal; the
  wager-only HTTP route does not issue that return review.
- Tony is the sole human authority. Custody, accounting, reviewer and
  execution keys and service identities must satisfy the existing separation
  rules. Their evidence identifies the technical role and its scope.
- Owner/execution permission bound to exact source/binary/configuration,
  enrollment, original approval, raw signed review, amount/fee, fresh nonce and
  short expiry. The runtime must neither issue that permission nor accept
  broad conversational permission in its place.
- Genuine C03–C08 maintenance, uncertainty, solvency, backup, actual restore,
  custody and operator receipts; then separately scoped staging/start approval
  and a state-preserving code rollback that retains latest UNKNOWN histories.

The reviewed operator packet must use the existing protected deployment and
recovery mechanisms for its exact action. It must capture the real running
PID/executable digest/source, service/config/UID/network identity, lease,
permission/revocation, bank/journal and readiness receipts. Compare original
8092/8093 and consensus identities before and after. Authenticated 8094 health
alone never permits producer resume, deposit publication or HD credit.

The exact protected app return contract is:

1. Under the exact HD financial lease, prepare the original signed return.
   Obtain a fresh reserve review of the resulting journal and exact signed
   owner operation permission.
2. POST that approval to `/satchel/v1/returns/check-execution`. Bind the
   nonexecuting result to a separately authenticated current H/H+1 escrow
   bank proof. Keep the permit and review digests with the attempt.
3. Commit immutable UNKNOWN in HD, then use the same lease to POST the
   **same** `ReturnApproval` to `/satchel/v1/returns/execute` on 8094.
   Its response is raw UNKNOWN with `durable_fenced=true`; a transaction hash
   is neither finality nor HD credit. The separate 8095 reviewer never becomes
   a signer or legacy executor.
4. Use read-only `GET /satchel/v1/returns/execution/{claim_id}` for recovery.
   Missing state/404 is UNKNOWN and cannot authorize repeating the POST.
5. Authenticate `/returns/reconcile` and `/proofs/return` against the original
   intent and stored signed bytes. Only restricted HD atomic global physical
   receipt consumption may credit an entitlement. Preserve original ticket and
   canonical complete market partition, MsgSend index 0 and legacy event ordinal 1.

On interruption, retain the latest journal, signed bytes, original approval,
nonce, uncertain fees and owner/reserve authorities. Never restore older
financial state, switch to an empty state path, remove journal buckets or
re-sign/rebroadcast an ambiguous attempt. A downgrade requires an actual
journal-format compatibility receipt; if absent, hold the new service under
approved recovery rather than destroying history.

Legacy 8092/8093 replacement remains the **separate exact `bdbce253` procedure**
in the existing [mainnet runbook](mainnet-settlement-runbook.md). Its short-lived
root-private permit, pinned old/new binary and state-preserving paired recovery
controls remain binding. Neither it nor C01 may target the consensus service,
executable, state or keys, or resume HD/DE producers without separate authority.
Founder #889 and accepted legacy transactions retain their individual holds;
a release permit is never payment evidence.
