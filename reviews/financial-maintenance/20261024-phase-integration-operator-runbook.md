---
id: "aoe2war.wolochain.financial-maintenance-phase-integration-20261024"
title: "Financial maintenance phase integration operator runbook — 2026-10-24"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war","aoe2dewarwagers"]
audience: ["operators","developers","ai-agents"]
source_of_truth: "git"
authority: "non-authorizing-financial-human-signature-review"
reviewed_at: "2026-10-24"
review_interval_days: 14
sensitivity: "internal"
---

# Financial maintenance phase integration operator runbook — 2026-10-24
**Status: FINANCIAL HARD HOLD / review-only code. Source branch:** `review/20261024-maintenance-phase-integration-held` stacked on held Wolo PR #97. **Never a live playbook until independently authorized.**

## Boundary and source
- [PR #95](https://github.com/Emaren/wolochain/pull/95): finite OS-root disk-backed ext4 isolated restore, no mounts or formats performed by controller, Docker data root preserved.
- [PR #96](https://github.com/Emaren/wolochain/pull/96): 18-unit application and timer/oneshot writer fence, common 30-minute LIVE permit, independent backup/restore incomplete receipts, existing service/DB test contracts. Source SHA `aa932a64ffcfc35e07f46516d38d2b923802c9b3`.
- [PR #97](https://github.com/Emaren/wolochain/pull/97): five-person Ed25519 **review** verifier. It verifies keys but does not prove humans, enroll them, consume nonce atomically, or grant financial permits. Source SHA `4a13ea021780e39cbf6db2828052bd227989724f`.
- **This review extension:** exactly three strict cryptographic evidence reviews, a durable primitive to reserve a nonce atomically in a private directory, and an unconditional CLI hard refusal of `fence`, `backup`, `restore-isolated`. The original finance controller v1 is not usable for production mutation on this branch. The code cannot issue a permit, resume units or release funds. An independent controller v2 adapter is NOT implemented.

## Exact 18-unit systemd candidate fence scope
The only candidate units eligible for financial app fence are:
- Apps: `aoe2hdbets-web.service`, `aoe2hdbets-api.service`, `aoe2dewarwagers-web.service`, `aoe2dewarwagers-api.service`.
- Timer and one-shot pairs (14): `aoe2hdbets-bet-stake-reconcile`, `aoe2hdbets-challenge-reconcile`, `aoe2hdbets-replay-auto-recovery`, `aoe2hdbets-staking-rewards`, `aoe2hdbets-trophy-tributes`, `aoe2war-prewarm`, `aoe2-wolo-transfer-heartbeat`, each `.timer` and `.service`.

This is **18 units, not 16**. Do not include the legacy 8092 or 8093 settlement services, Wolo consensus, unrelated OS cron, or Hasura in a broad stop. The actual 18-unit fence has never been executed; observed web/API/timers and the nine observed database sessions are snapshots, not continuous exclusion.

## Residual human and system owners (explicitly unclosed)
| Surface | Confirmed limited fact | Independent owner / blocker |
|---|---|---|
| HD database service login | DML 190/190 HD and zero DE tables | HD owner: enumerate copied credentials, SECURITY DEFINER/functions, manual CLI and active accesses |
| DE database service login | DML 52/52 DE and zero HD tables | DE owner: same for DE |
| DBA/root superuser | Can write both databases regardless of app grants | DBA credential and sudo/SSH custodians; require named no-run/lockout under authority |
| Live DB connections | 9/9 observed belonged to app-service cgroups; prior prepared transactions zero | Operator must re-prove under sealed ingress and repeat after drain |
| Root/UID1000 cron and user systemd | Six cron files, nine job lines, 13 run-parts candidates, no finance keyword match; user timers/agents observed | Separate owner inventory and immutable source hashes; keyword absence is not exclusion |
| CI, deployment, SSH, OS bridge, manual scripts | Potential finance capabilities, not fully enumerated | Operators and credential owners must independently attest or fence all paths |
| Signers/Wallets, Wolo 8092/8093 | Direct CLI, keyring, bearer, RPC, off-host signers possible | Independent chain/custody reviewer proves no-run and reconciles in-flight tx, finality, late deposits |
| Hasura | Running, main configured `tokenchain_callisto`, host networking | Indexer owner proves secondary connections/role privileges; no blanket exclusion |
| Hermes relay | Historically inactive/disabled | Relayer identity and manual-activation witness |

The original Wolo runtime source-drift **P1 remains**: VPS source `78c25985420ee41a6678c42fab8ea8d6c3b1b519` is 171 commits behind DocsV2 baseline `4ce11c4965da64e3d4dee6a8681b6198e1aba1eb`. This state cannot be repaired by treating the drift as a document-only diff. No automatic fast-forward.

## Trust enrollment required before a real operation
Five independent humans: **Owner**, **Operator**, **Chain Reviewer**, **Finance Reviewer**, **Recovery Witness**. Each privately generates/custodies a distinct Ed25519 key under independent control, and an enrollment/revocation custodian verifies the real person's role and key possession **out of band**. A root-protected registry SHA is pinned independently of the packet and of this repo. Rotation/revocation requires new independent ceremony, auditable immutable revision and externally witnessed hash; no self-asserted identity.

Each person signs the *identical* domain-separated closed-schema request binding exact phase/operation, expected source/tool Git SHA, host fingerprint, 18-unit scope digest, evidence/procedure SHA256, byte budget, UTC not-before/expiration, fresh nonce, and—after capture—immutable fence/capture hashes. Production phase admission must verify registry independently, policy/revocation, exact request, evidence, timestamp and source; reserve nonce durably under an exclusive root-private lock **before** operation; externally witness the ledger checkpoint to prevent root-rollback replay. A unit test that uses temporary generated keys is not a real approval.

## Phase-by-phase finite state machine and explicit authority
| State / phase | Preconditions | Artifact / action | Continuation |
|---|---|---|---|
| `HOLD` | Default | Protected source P1 and financial controls still BLOCKED | NO-GO |
| `CAPTURE_PROPOSED` (live_capture) | Five enrolled signatures, source/host/scope/policy/external ingress independently checked; fresh nonce, <=30 min | Read-only gate review only in PR98; no live permit. Future v2 executor must atomically consume nonce and fence exactly 18 with retained HOLD, bounded HD+DE dump and immutable hashes within window | Review PASS is NOT GO |
| `CAPTURE_SEALED` | Independently authenticated, completed HD/DE archive and true reader-valid fence/capture receipts before live expiry | Immutable capture SHA, full census/constraints/sequences, off-host witness. Failed/late capture => `INCOMPLETE` with HOLD | No automatic resume |
| `CAPTURE_SEALED_RESTORE_PROPOSED` (offline_verify) | **Fresh** five signatures, fresh nonce, matching prior review/capture/fence bytes, `live_actions_allowed:false`; no live access | Future offline v2 uses preprovisioned bounded filesystem, isolated disposable PostgreSQL PGDATA on OS root, network:none, pinned Docker image; complete restore+schema/row/census with zero production sockets, independent cleanup and artifact digest | Failed/missing mount or cleanup => `INCOMPLETE`, no receipt |
| `OFFLINE_RESTORE_VERIFIED` | Actual whole HD+DE schema, row, constraint, sequence comparison, intact seal, off-host witness; not simulated | Independently signed restore/witness receipt and external immutable retention | Only recovery evidence, not finance release |
| `RESTORE_EVIDENCE_REVIEWED_RESUME_PROPOSED` (resume) | **Third, fresh** five-person phase signatures and nonce; authenticated restore receipt and original capture/fence; independent late chain, staking, refunds, external signer and bank review; source drift resolved or explicitly admitted by separate policy | PR98 only returns `REVIEWED_NONAUTHORIZING`; future v2 resume controller requires distinct exact signed authority and trusted prestate | NO-GO until implemented and independently approved |
| `RESUMED` | New phase-separated v2 implementation, signed resumption control, witnessed no in-flight unresolved effects, exact original unit prestate and catchup handling | No implicit replay or settlement service restart, remove own HOLD only under independently reviewed resumption authority | Currently NOT IMPLEMENTED; never assume resume |

A successful archive alone **never** allows restoration, restart, resumption, fresh financial execution, migration, wallet usage, token transfer or release.

## Stop/failure matrix
| Failure | Required disposition |
|---|---|
| Missing fifth real person, revoked key, uncontrolled enrollment, unpinned source | HARD HOLD, no operation |
| Unexpected session/cgroup/DBA/CI/manual signer, unknown queued payout | HOLD; extend producer inventory, not fake clearance |
| Permit expires during fence/dump/hash | `INCOMPLETE`; preserve fences, do not publish verified capture |
| 18-unit activation condition tampered or timer reactivates | Preserve HOLD; refuse success |
| Restore image, loop backing, mount identity, bounded bytes drift | No isolated restore; preserve sealed source data |
| Corrupt dump, schema/row discrepancy, cleanup/container failure | No verified restore receipt, retain `INCOMPLETE`; no auto cleanup of foreign state |
| Tampered parent digest, forged/duplicated Ed25519 approvals, replayed nonce | Review gate refusal; no permit |
| Root rollbacks local nonce ledger | Locally indetectable absent independent monotonic witness; **NO-GO** |
| Resumption after verified backup but without third new signature set | Absolute NO-GO |

## Safe engineering smoke tests (disposable only)
```sh
python3 -m unittest discover -s tests -p 'test_settlement_human_authority_verify.py' -v
python3 -m unittest discover -s tests -p 'test_settlement_maintenance_phase_review.py' -v
python3 -m unittest discover -s tests -p 'test_settlement_maintenance_nonce_store.py' -v
python3 -m unittest discover -s tests -p 'test_settlement_financial_maintenance.py' -v
python3 scripts/settlement_financial_maintenance.py --mode scope
```
The inherited finance tests use mocks/disposable PostgreSQL; the actual container-specific integration remains opt-in. A nonzero review exit status 3 means evidence review only; exit 2 is HOLD. The old controller modes `fence`, `backup`, `restore-isolated` **must** exit 2 before lock/mutation on this candidate branch, even with a syntactically valid old v1 permit.

## GO/NO-GO
**Engineering source:** review-only phase gate and v1-cli lockdown qualify only after exact-head CI, negative tests, DocsV2 and independent code review. **Real finance operations:** NO-GO pending externally authenticated real human enrollment, root-protected source-specific key registry, out-of-band revocation, monotonic nonce witness, integrated operational controller v2, 18-unit residual signers/no-run exclusion, full-size HD+DE offline restore, independently verified financial inventory and bank solvency, actual witnesses and approved maintenance window.

No production backup, restore, unit stop, mount, restart, wallet operation or mainnet deployment has been performed by this review branch.
