---
id: "aoe2war.wolochain.we1-clan-image-member-only-admission"
title: "WE1 Clan image member-only admission — source HOLD"
type: "working"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["developers", "operators", "ai-agents"]
source_of_truth: "git"
authority: "source-only-clan-image-contract-not-production-admission"
reviewed_at: "2026-11-25"
review_interval_days: 7
sensitivity: "restricted"
---

# WE1 Clan image member-only admission — source HOLD

Source implementation 6e673f13ab64ae8a8ca3d496c82dff536f606d3a, base 1d7339d73bf0828a5db644421e65ec4fb9bbb3ec; PR #264. Exact SQL install SHA256 a265cbe16a19c6517a5fb85b84b7f5aaabdc4f501e3aa6ba2b4a73f5ccaba7b7; inverse 5b203272500a010ae4e9bc8ec9c19d60d201828e30e04db32d76019d4af2f241; fixture 67cc152aeececd852b8f7e38b7e53860a1cff04162c851a39bc0e86ef2d3025d. Native disposable AF_UNIX PG16 PID32894 28/28 reported in PR #264 comment 7162825763; clan_text stub is not full Social V2 or live catalog proof.

Existing Social V2 seq3 installed Nov20 (PR #251 comment 7044124244); do not reinstall or replay consumed permits. Separate fixed clan audience, active human membership, no admin override, empty caption, one local PNG/JPEG/WebP <=10MB. Explicitly reject nonempty captions (never silently strip), remote, audio/video, multiple files and legacy fallback. Signed actor sidecar, private read and durable replay; same-key successful replay can return original IDs for a different provisional object. Delete only confirmed unreferenced provisional objects, never after uncertain commit. Read takes row locks and must not run in a read-only transaction. Opaque references stay server-private. No direct recipient authority reuse.

Mandatory live prerequisites: independent actual HD/DE catalog, original ACL/default ACL/effective role/sequence/trigger/dependency graph, exact postimage/inverse and signed native owner admission, private storage and WE3 authenticated acceptance. Direct media #259/#260/#262 remains separate and frozen. Radio #263 requires actual bounded catalog capture and distinct grant. Financial gates C04/C08 closed; C01/C02/C03/C05/C06/C07/C09 open; funding denied, custody inactive. No installation, release or new financial privileges from this document.
