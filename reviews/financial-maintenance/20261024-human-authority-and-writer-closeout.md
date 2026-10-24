# Financial-maintenance authority and writer review — 2026-10-24

**Nonauthorizing review stacked on Wolo PR #96**, exact baseline `aa932a64ffcfc35e07f46516d38d2b923802c9b3`. PR96's 18-unit correction is closed; storage preparation is already complete. This branch only introduces an *offline cryptographic evidence verifier*, unit tests and this design. It does **not** alter `settlement_financial_maintenance.py`, its v1 permits, the existing 30-minute window or any production services. Existing financial checklist: five BLOCKED and solvency UNKNOWN. No human signatures, permits, payments, DB writes, service stops or real backup/restore occurred.

## Actual positive evidence and finite authority owners

| Authority | Accountable owner to authenticate | Verified boundary | Unproven / mandatory next human classification |
| --- | --- | --- | --- |
| HD web/API, HD + shared timer/oneshot jobs including transfer-heartbeat | HD finance owner and root VPS operator | Candidate 18-unit source scope in PR96; actual 4 running apps, 7 armed timers, 7 inactive oneshots | Exact running binaries; externally launched CLI/keyring access; timer/catch-up and activation edges |
| DE web/API, DE CLI/faucet | DE finance owner | DE role DML 52/52 DE ordinary tables, 0/190 HD | External default signer/keyring holder, manual and CI invocation |
| HD application database role | HD owner/DBA | Effective DML 190/190 HD tables, 0/52 DE | Credential copies and manual scripts; SQL functions, SECURITY DEFINER, FDW/view and background-job privileges |
| Administrative PostgreSQL role | Root/DBA, independent credential trustees | Admin superuser hash `e8a48653851e` can write both DBs | Privileged password/key custodians, remote SSH/sudo, CI root secrets, emergency override |
| Root cron, at, periodic jobs | Root VPS owner; UID1000 for own crontab | 6 cron source files, 9 job lines, 13 executable run-parts candidates, 0 at jobs; no finance keyword lines | Compare fresh file hashes to source-reviewed Oct 18 entries; positively classify changed jobs, nonstandard sources. Do NOT blanket stop cron |
| UID 0 / UID1000 user systemd & agents | Root, UID1000 | Only `launchpadlib-cache-clean.timer` among observed active user timers; GPG/dbus agents are active | Agent/socket signing ability and manually launched process access; managers aren't itself proof of no signer |
| `tokenchain-hasura` | Separate TokenChain indexer owner | RUNNING (Oct 24 03:02Z creation/start), restart=no, host network; configured main DB URL matches separate `tokenchain_callisto` | Secondary connections, DB permissions, remote schemas and indexer mutation access; not proven an HD/DE signer |
| HD faucet/staking CLI, 8092/8093 bearers | HD payout owner, 8092/8093 custody operators, all bearer holders | HD web owns direct signer and settlement bearer capabilities; original two settlement services protected | Direct OS CLI/keyring invocation, off-host tunnels, bearer/token holders, any unknown in-flight settlement; **never** stop old 8092/8093 by this fence |
| Manual HD backfill `--apply`; DE manual payout scripts | HD/DE owners and CI operators | Financial execution paths source identified; one custody tool currently source-blocked | Signed prohibition on invocation and exact script/runner inventory during window; do not execute to test |
| Wolo Hermes relay | Wolo operator/relayer credential owner | Historically inactive / disabled, potential signer | Current dormant-state proof, no manual activation, wallet authority attestation |
| GitHub CI, deployment hooks, remote SSH, OS Operator Bridge | Named release administrators and credential custodians | No exhaustive independently witnessed holder roster | Human-assigned no-run approvals with exact coverage, runner/workflow SHA, no changes to 8092/8093, no future queue activation |
| WalletConnect/Keplr, outside chain RPC | Actual wallet holders; independent finance/chain reviewers for effects | Public-chain broadcasts cannot be fenced by VPS | Independent late-deposit, finality and accounting witnesses; no claim all external wallet tx can be prevented |

### Owner's exact runtime evidence (do not overpromote)

Owner's read-only Pg role census confirmed HD login hash `4389a21f98fb`: INSERT/UPDATE/DELETE/TRUNCATE on 190/190 HD, zero DE; DE hash `396ce11412d9`: same on 52/52 DE, zero HD; three other nonadmin login role hashes had zero these DML permissions in both. The PostgreSQL superuser retains all tables. Later **9/9 observed** current TCP loopback database sessions mapped via PID/cgroup to known services: **5 HD web, 2 HD API, 2 DE API**; DE web simply had no snapshot session. Previously observed prepared xacts **0** in each DB. This is **not** a continuous admission block, future-reconnect proof, full SQL privilege audit or a financial payout-drain certificate.

## Genuine five-human approval protocol

The PR96 maintenance controller presently accepts syntactically shaped `approval_refs` with an identity string and 64-character hash. This is NOT authentication, and changing the v1 caller's hashes or fabricating sample humans would be unsafe.

The additive script `scripts/settlement_human_authority_verify.py` performs **real detached Ed25519 signature verification** using OpenSSL on exactly five role/person/key registry entries:

- `owner`, `operator`, `chain_reviewer`, `finance_reviewer`, `recovery_witness`.
- Registry binds each role to one distinct `person_id`, `key_id`, public Ed25519 key. Duplicate people/keys/pubs/roles fail. A **separately controlled trust-registry SHA-256** must be pinned out of band from request, not provided by the subject claiming approval. An independent enrollment custodian must confirm five real, independently controlling humans, role conflicts, rotation, revocation, and hardware key custody. A digest comparison or signer possession cannot alone prove real people.
- A closed-schema signed request binds **phase + operation + source commit SHA + tool SHA-256 + exact 18-unit scope SHA-256 + host identity SHA-256 + evidence packet SHA-256 + procedure SHA-256 + UTC start/end + 128-bit unique nonce + bounded archive bytes + live authority flag + capture/fence parent hash**.
- Signed bytes are domain-separated as `b"AOE2WAR-WOLO-FIVE-HUMAN-APPROVAL-V1\\x00" + ascii_json_sorted({role, person_id, key_id, request})`, with deterministic ASCII JSON and no floating-point. Every approval is cryptographically verified against an enrolled key. Missing/duplicate role, changed request, bad signature, signature encoding, untrusted registry, expired authority or inconsistent parent fails closed.
- **Anti-replay admission remains a controller engineering gate**: the verifier checks an externally provided consumed-nonce ledger snapshot, but does *not* atomically consume it; parallel invocations could both pass. A production controller must durably and atomically consume a nonce under a trusted root-only lock, fsync receipt, issue-time scope authorization and independent signed evidence before its first mutation. Ledger rollback, lost lock, missing durable receipt or concurrent claim => HOLD. Current tool deliberately reports `nonce_atomically_consumed:false`.
- **Always exits 3 when all cryptographic tests pass** (an observation), 2 on HOLD. It has no production credentials and no permission to stop services, read private wallets, run SQL or issue permits. It reports `production_permit_issued:false`, `producer_fence_authorized:false`, `financial_release_authorized:false`. Human independence remains `real_human_identity_enrollment_verified:false` until separately independently witnessed.

## Resolve 30-minute live window without bypassing existing source control

**Not yet integrated into PR96.** Existing `fence-backup-isolated-restore` requires a **single unexpired <=1800-second permit** for both backup and actual isolated restore. No benchmark proves the ~9.95GiB HD full-data dump and restore/census/cleanup can finish within that limit; do not simply extend expiry or bypass the final receipt check.

### Phase A: separately approved LIVE_CAPTURE (max 1800 seconds)

Five enrolled humans independently sign the **exact**, source/host/18-unit/evidence-scoped `live_capture` request `fence-drain-capture-hd-de`. A reviewed authority-integration PR must verify all signatures under a privileged trusted registry and atomically consume nonce **before** mutating state. Establish owners for independent manual/CI/admin/CLI wallets and attest their scoped no-run/ingress controls first. Record precise original activation states. Keep original consensus and both 8092/8093 services running. Under explicit owner permit:

1. Close externally controlled HTTP/CI/manual financial admission first, then install the source-pinned persistent HOLD and activation-condition drop-ins across **only the reviewed 18 HD/DE units**. Verify effective systemd conditions prior to exact authorized service/timer stops. Reject unexpected dependencies or active jobs.
2. Prove cgroups empty and **all other** HD and DE PostgreSQL sessions (idle included), prepared transactions and pending systemd jobs zero under privileged full visibility **twice**, while new ingress is positively held. Analyze in-memory settlement requests, queued work, eventual chain credit and unknown payouts; do not retry or suppress them.
3. With independent witnessed continuity take complete HD+DE dumps, exact old two-service settlement state/config snapshots and pinned financial row/constraint/sequence censuses. Verify source and output checksums, archive byte bounds and post-capture census before permit expiry. Only then seal `CAPTURE_COMPLETE_NONRESTORED`. Failed/late/partial capture retains `INCOMPLETE` and HOLD. Full-size performance rehearsal must prove a realistic worst case **before scheduling** this phase.

### Phase B: independent OFFLINE_VERIFY approval

Five *fresh* approvals on `isolated-restore-verify-sealed-archives`, a new nonce and an **immutable Phase A archive manifest plus actual fence receipt SHA-256**. `live_actions_allowed:false` is mandatory. A new source-qualified offline controller must not read the evolving production DB, change on-host systemd, withdraw funds, clear HOLD or treat old expired live authority as renewal. It runs a complete **actual** isolated PostgreSQL restore from sealed archives on the already-qualified disk-backed private bounded filesystem, pinned image, network:none, read-only container root, no production socket/secrets, fully checked schema/constraints/sequence and financial census. Delete only known-owned disposable resources after identity checks. An offline-specific, separately reviewed time budget can reflect real restore benchmarks; the verifier's prototype caps this window to four hours, **not permission to extend Phase A or the existing controller's 30-minute permit**. No verified receipt after expiry or failed cleanup. Off-host copy/restore remains an independent witness requirement.

### Phase C: new signed RESUME authority

New five-person signature set on `reviewed-resume-existing-hd-de-units` and exact capture/fence lineage; restore only original prestate after independent late-chain effects, failed/unknown payments, timer catch-up and postcapture drift reviews. Never automatically run queued payouts. Do not restart original 8092/8093 services or Wolo consensus as part of this procedure. Never restore old request/journal trees over live state. If a fence or recovery step fails/loses its permitted window, **retain HOLD, no automatic unfence**, escalate to named owner and recovery witness.

### Fail-closed interruption outcomes

| State | Only authorized continuation |
| --- | --- |
| Missing owner, off-host signer, trust registry or genuine independent identity | No live operation; finance HOLD |
| Partial 18-unit activation gate or expiry | Retain HOLD; inspect source and cgroups; separate human recovery authorization |
| Sessions/unknown chain payments not drained | Retain HOLD; no archive promotion |
| Dump/hash/census incomplete or past Phase A expiry | Retain INCOMPLETE and HOLD; never synthesize a backup receipt |
| Sealed Phase A capture with expired live permit | New five-person Phase B authority, only offline |
| Offline restore or bounded cleanup failed | No verified restore receipt; retain immutable capture; new offline authority for retry |
| Offline verification succeeded | Recovery evidence ONLY, not solvency, live availability or cutover authorization |
| Resume uncertain | Keep HOLD; independent current-state review and witness required |

## Implementation gap requiring a distinct reviewed controller PR

This new verifier is a **crypto proof component**, not an authorizing controller. Future controller v2 must make the signature bundle SHA, trusted registry hash, persistent revocation/nonce database, root-private file identity, exact phase/action, source SHA and evidence *mandatory*, independently verify them before the first side effect, atomically consume the nonce, and prevent a stale V1 hash-only permit being silently upgraded. It must enforce Phase B's **absence** of all live-system mutation capabilities, and require fully witnessed Phase A proof without treating retained HOLD as permit renewal. Review and negative-test this integration under independent security/finance signoff; only then may humans authorize an actual maintenance window. No production finance authority exists today.

### Local source-only contract tests

```sh
python3 -m unittest discover -s tests -p test_settlement_human_authority_verify.py -v
```

Tests use 5 **throwaway** Ed25519 keys generated by OpenSSL in a local temporary directory. Positive result never produces operational authorization. Negative tests: changed source/host/scope/evidence, invalid signatures and base64, wrong persons/duplicate keys/roles, missing approvals, stale/overlong UTC, prior nonce ledger, duplicate JSON keys, Boolean byte-bound loopholes, bad capture/fence lineage, and phase/live escalation. These are **synthetic tests**, not five real human approvals or mainnet readiness. Original finance six controls remain BLOCKED/UNKNOWN; refunds #8477, founder #889, full balance/solvency and external chain bank finality are separate independent reviews.
