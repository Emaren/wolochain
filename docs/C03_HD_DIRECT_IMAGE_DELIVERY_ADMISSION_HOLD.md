---
id: "aoe2war.wolochain.c03-hd-direct-image-delivery-admission-hold"
title: "C03 HD direct image, text replay and delivery acknowledgement — admission HOLD"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "git"
authority: "source-only-nonfinancial-media-and-delivery-no-production-permit"
reviewed_at: "2026-11-24"
review_interval_days: 14
sensitivity: "restricted"
---

# C03 HD direct image, text replay and delivery acknowledgement — admission HOLD

Scope: WoloChain #259, PRODUCT #1509, Central #258. Preserve the financial
checkpoint head e0a844e and prior 10/10 qualification. This is HD-only,
nonfinancial source engineering, not live SQL admission.

## Exact candidate

- Install scripts/c03_hd_direct_image_install_candidate.sql SHA256
  db4c80451f9bb627598105b826c45d9ee115fd462a56d08aebf5deb79ad0723c.
- Inverse scripts/c03_hd_direct_image_inverse_candidate.sql SHA256
  2298690e5c1c412cdd73d232c9469ee7e268c191fbaa0816e9f6340fde138baf.
- Test tests/test_c03_hd_direct_image_pg16_isolated.py; dedicated
  c03-direct-image-isolated.yml uses actual PostgreSQL 16.

The fixed direct_image function and restricted leaf persist attachment
metadata, the message and private per-actor replay ledger atomically.
Same key plus exact canonical payload returns original ID; changed fields
conflict. File durability and uncertain-commit orphan retention are WE3
responsibilities. The actor UID is supplied by the existing authenticated
signed-session writer, not by an untrusted HTTP actor parameter.

The original direct_text body is pinned by its original prosrc MD5,
29748632792ceb09d6260bbb51900dba, as a drift check, not a signature.
The new executor-only security-barrier view exposes only IDs of
plain-text messages (no attachment kind/reference or shared lobby
message). Latest-message one-second cooldown remains. A media caption
never returns its image ID as a text replay; after cooldown, a matching
text produces a distinct message. Unused inverse restores the exact
original text definition. Never remove a populated image ledger.

Proposed direct_delivered(actor_uid text,target_uid text,message_ids
integer[]) returns status 200, body {ok:true,updatedCount:n}. Verified
recipient may acknowledge 1–50 distinct positive IDs from the exact
other participant in their two-person conversation. Validate entire
batch, lock authorized rows, update only NULL delivered_at with server
time, preserve first timestamp on retry. Any foreign ID denies entire
batch. No read acknowledgement, global sweep or SSE/GET mutation.
The separate high-level function is callable only by the existing
restricted writer, with a fixed executor-only leaf. No raw table or
sequence grants. Committed delivery evidence survives inverse; no
retroactive clearing. The existing broad legacy owner remains an
independent dependency risk and is not made newly callable directly.

## Evidence and limits

Native disposable Homebrew PG16.10, 2026-11-24: 56/56 PASS including
original 40 checks, exact text inverse, mixed-media replay/cooldown,
foreign receipt denial, atomic rollback, timestamp idempotency, bounded
batches and unchanged public relation/column ACL, role/membership and
schema fingerprints. Actual isolated writer connections; earlier
overlapping SERIALIZABLE transactions gave 40001 and safe same-key retry.
First expanded fixture failed because only the latest image timestamp
was aged; older recent sender messages correctly retained cooldown.
Adjusted all synthetic sender timestamps for the after-cooldown case;
full suite then passed, stopped and removed private cluster.

Prior Linux dedicated PG16 CI passed on f1162a9, and WE3 integrated
17/17 real PG + Sharp + filesystem tests on the earlier install bytes.
Those results do not qualify changed bytes or new HTTP receipt transport.
No synthetic fixture establishes live effective authority or browser
privacy.

## Required admission and inverse

Read actual HEL1 HD original function body, owners, roles/memberships,
HBA, complete raw table/column/sequence ACL, triggers, rewrite rules,
FKs/dependencies, security definer paths and exact postimage. Verify
restricted HD credential, DE denial and no financial privilege delta.
Existing root-controlled Social V2 executor pins different source bytes;
do not reuse its old install permit or general SQL shell. Independently
review and admit exact media/receipt install and inverse with fresh
purpose-specific owner-native signed authorization, source and preimage
binding, nonce, protected root execution and durable postimage/inverse
receipt. If changed preimage or native authority unavailable, HOLD.
Coordinate WE2 R25 guard, private DATA media root, writer/web permissions,
runtime, and legacy reference compatibility. WE3 must explicitly integrate
receipt request after authenticated recipient acceptance, emit receipt
events only for committed evidence, and preserve read status as unsupported
until separately admitted. Prove actual two-account browser acceptance,
privacy and retry. No CHAT_DB_READY before physical evidence.

Funding DENIED. Custody inactive. No financial gate closed here.

The nine expired inherited documentation reviews were reconciled against
the independently qualified #258 November 24 applicability amendments
(exact e0a844e), including the dated 14:09Z quarantine receipt. Historical
financial source and evidence remain historical; the separate #258 witness
implementation is not imported or represented as part of this media stack.
