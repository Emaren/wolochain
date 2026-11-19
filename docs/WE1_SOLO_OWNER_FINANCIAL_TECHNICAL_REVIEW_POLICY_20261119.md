# WE1 solo-owner financial engineering — source review vs physical authority

**Effective 2026-11-18 owner directive; written 2026-11-19 UTC. SOURCE POLICY ONLY.**
**Canonical coordination:** [WoloChain #239](https://github.com/Emaren/wolochain/issues/239).
**Scope:** WE1 FINANCIAL/WoloChain, quarantined from WE2's website, WE3 PRODUCT and WE4 Traffic.

## One human; independent technical examinations

Tony/Emaren is the **sole human owner and decision-maker**. Separate AI engineering sessions, local restricted UID workspaces, isolated machines and GitHub Actions provide *independently reproducible technical evidence*. They are **not** additional people, source-owner GitHub accounts, cryptographic human signatures, or automatic permission to alter live finance.

A recorded `Emaren` GitHub source-review comment is a **delegated engineering decision** if it identifies scope, exact head/blob/sha256, evidence, known failures, and limitations. It must never claim to be a second human or a distinct independently authenticated FINANCIAL Codex identity. Review instruments may use GitHub CI, offline signed samples, or authenticated physical host readbacks; declare which type was actually used.

## Three distinct permissions; never collapse them

1. **SOURCE-ONLY TECHNICAL ACCEPT**: evidence-backed review of immutable proposed code or SQL. It may update explicitly reviewed SHA identity pins with a documented decision and independent byte-matching test. Existing adverse tests and DocsV2 remain mandatory. A source ACCEPT cannot create any service, database role, user, wallet, remote access, or funding authority.
2. **PRODUCTION PHYSICAL ACCEPTANCE**: exact cluster/role/HBA/service/systemd/PG executable + actual authenticated readbacks from the intended host, provenance of complete raw preimages, source/signer identity, runtime negative tests, and independently reproduced inverse recovery. Disposable PostgreSQL, PgBouncer and systemd prove *mechanics only*. Synthetic positive status must never be promoted into a live witness.
3. **OWNER-AUTHORIZED MAINTENANCE PERMIT**: one use, source- and preimage-pinned, time/site/operation scoped, human owner-presence approved under a separately accepted signing mechanism with no reusable password ceremonies. Requires preflight recovery/rollback, off-host failure checkpoint, protection of live users, C06/C07 readiness when relevant, and explicit root executor admission. Before and after physical changes, capture independently verifiable signed receipts and fail closed on mismatch. Owner's broad engineering direction is not this permit.

Funding, custody startup, chain consensus modifications, live SQL/HBA/ACL, real financial backup capture and the funded canary each require the proper distinct authority and evidence. C09 remains last.

## Source reviews and DocsV2

Record the authoring workspace and a **different technical execution path** (e.g., Ubuntu CI vs M1 PG16, isolated adversarial test runner vs source author). If one GitHub owner account writes both the source and the review comment, disclose that identity openly. A passing CI job does not create a different human reviewer.

DocsV2's source ancestry, expiry, reviewer content, and implementation baseline must undergo **substantive line-by-line re-review**. Never reset review timestamps, suppress failing checks, edit observed logs, bypass source pinning, or treat a draft PR as production accepted solely because source-only CI turns green. Add a timestamp only after actual contemporary review by the real owner/delegated independent engineering process, with evidence of what was checked.

A source failure remains visible; diagnose and fix only the actual defect. Preserve counterexample receipts and record earlier failed tests rather than hiding them.

## Journal/physical witness separation

C03 journal `INTENT`, `FENCED`, `RESTORE_INTENT` and `RESTORED` are only claims unless exact physical PostgreSQL/systemd/pooler root observations are bound to valid signed evidence and independent durable checkpoints. Tamper, path replacement, incomplete write, stale source, failed rollback, ambiguous process identity, signer revocation or unreadable original bytes => **UNKNOWN/HOLD**, not FENCED or RESTORED.

A journal string such as `C03_UNKNOWN_REQUIRES_EXTERNAL_HUMAN_RECOVERY` denotes an independently authorized **recovery procedure with Emaren as the only human**, not a requirement to invent another person. This policy clarifies the source label; it does not remove the fail-closed barrier. Changing an error label itself still requires source review/hash updates.

`NOLOGIN` or rejected HBA alone does not evict existing backend writers. Capture actual effective table/column ACLs, identity/default sequences, transitive group memberships including `SET ROLE`, PUBLIC function execution, SECURITY DEFINER owners/search_path, triggers/FKs, pooled clients and restart recovery across both financial databases. Exact inverse means raw ACL/NULL/ordering and role metadata match—not merely equivalent privileges.

## Nonfinancial website expedited boundary

WE1 can **ACCEPT bounded nonfinancial application source design** without C01–C09 financial closure. Specific website SQL privileges must still be bounded, independently evidenced and reversible. The origin of delegated application authority is WE2's independently admitted protected service contract, not a generic FINANCIAL writer role.

For `app-prodn` PR #1418, accept its reviewed exact socket/session/parameterized text architecture as **source design only**; hold the concrete `aoe2war_social_writer` role and GRANT installation until the actual HD+DE catalog graph, raw preimage/inverse and approved host identity are verified. If a true financial trigger/definer/grant path is found, cite its exact OID and dependency and HOLD that path only. No generalized hold on Library, Zodiac, public chain telemetry, unrelated website pages or WE4 Traffic.

Traffic PR #74's previously issued exact-scope technical ACCEPT remains unchanged; separate WE2/B/Steam V27/root admission controls its installation.

## Receipt and scoreboard

Always record: full source hash, CI IDs and conclusions, who authored and who *technically* reproduced the work, positive tests, negative counterexamples, unknowns, exact physical observations and time, reversible preimages, permitted next step and explicit owner-permit requirements.

**C04 and C08 CLOSED (2/9). C01, C02, C03, C05, C06, C07, C09 OPEN (7/9). FUNDING DENIED.** Maintain these until a specific physical gate actually passes, with a separate owner authorization where needed.
