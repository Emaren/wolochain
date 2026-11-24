---
id: "aoe2war.wolochain.c03-hd-direct-media-native-executor-hold"
title: "C03 HD Direct Media native executor — owner admission HOLD"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["operators","developers","ai-agents"]
source_of_truth: "git"
authority: "source-only-fixed-media-executor-no-root-or-financial-admission"
reviewed_at: "2026-11-24"
review_interval_days: 14
sensitivity: "restricted"
---

# C03 HD Direct Media native executor — owner admission HOLD

Separate stack on #259 exact 3e4c50452541805742f31bd743117b0863582f60.
No change to the qualified 56-check media SQL or #258. Implementation
commit 5f6e4138b09ff500f137c3fe30582c01e0ab9b4c.

## Fixed identities

- Executor scripts/c03_hd_direct_media_native_executor.py
  SHA256 f91685bbc1976ce679196221a5ad8d907907e03197413eaa5e4140bdfa86a39d.
- Catalog witness scripts/c03_hd_direct_media_catalog_witness.sql
  SHA256 d1a0b2158b48da9d10f140fe67dd6fe454c44956d511787e5f26f71c344b59a4.
- Exact #259 install db4c80451f9bb627598105b826c45d9ee115fd462a56d08aebf5deb79ad0723c;
  inverse 2298690e5c1c412cdd73d232c9469ee7e268c191fbaa0816e9f6340fde138baf.
- Owner preimage helper 5f13af27345083c80d7c5e877e175b024f351644177e777c4f69fcb3a08e355d,
  existing catalog audit a25b85c8f5f1cb95d6e320029d6ff5267cd7fd9fd6180b9c34e777f15f1aa8e7.
- Separate owner Keychain source cf912cf4b4419b6b15d655b5e3b8aa2d4423ff835d521fdd153a2cd15a40b558
  and permit builder 84ec242fe02d0767fb92abe74bf6e42cf0a5357ae013d62a896ee6eac0a06455.

## Native evidence

Disposable Homebrew PG16.10, private AF_UNIX, 26/26 focused executor
composition checks passed on dc78aa6b. Final WE2 review delta 13/13
PASS independently targeted: descriptor/path replacement, symlink/mode/hash
refusal, immutable validated bytes used for all four HD/DE reads, actual
expired/not-yet-valid SQL entry, expiry after DDL atomic rollback, fresh
window install and unchanged DE. The after-DDL fixture inserted a test-only
delay before the exact final guard. Fixture removed; no prior local
qualification rerun. New Linux exact head CI required. Actual generated disposable P-256 signature
verified; tampered signed preimage, scope/nonce/expiry and changed SQL
denied. Real stale financial ACL digest rejected inside transaction.
Real exact install with invariant including original roles, memberships,
ACLs, definitions, types, dependencies, triggers/FKs, indexes, policies,
default ACLs, FDW metadata and extensions unchanged; DE full catalog
unchanged. Wrong expected inverse digest aborts all inverse changes,
correct unused inverse restores exact original HD fingerprint. Consumed
nonce without receipt and unrecognized state fail closed. Fixture stopped
and removed. State journal tests use disposable private paths/reader;
not a native root installation test. Swift typecheck and Python builder
syntax passed; no real key created, accessed or signature requested.

## Actual authority boundary

The catalog query hashes only metadata (including FDW options); no player
rows or raw passwords/options printed. The full fingerprint additionally binds PostgreSQL system identifier,
postmaster start, critical connection/configuration identity and parsed HBA
rules (including included-file rules); actual fixture HBA change and exact
restoration proved digest drift and equality. Parsed HBA is not proof of
loaded authentication behavior; actual credential tests remain required.
The full fingerprint binds exact
observed HD and DE catalogs, with a second invariant excluding only the
new media objects and reviewed direct_text body change. This is not
proof of all dynamic SQL or external producer behavior. Requires actual
review of raw catalog audit, HBA, role reachability, triggers/FKs and
current protected service authority; no reliance on name matching finance.

The root executor is fixed-purpose, hard-pinned SQL bytes, machine ID
digest, HBA digest, new distinct owner P-256 public key, exact reviewed
executor SHA and SQL source commit. Root-only review.json and nonce state
must be independently admitted; no self-installer or generic root shell.
All six forbidden authority booleans are false. Ten-minute signed packet
binds actual HD full/invariant and DE full catalog digests. Preflight
read-only; install/inverse only HD. PostgreSQL connection uses OS postgres
peer and fixed local socket, port and database. One serializable
transaction checks the signed catalog before DDL and the invariant and
postimage before COMMIT. Permit validity is rechecked after durable nonce
consumption immediately before SQL, at SQL entry and before COMMIT, with
expired/uncertain state held rather than retried. The inverse additionally binds exact prior
preimage from durable install receipt and refuses populated media ledger.
Post-commit independent readbacks must agree including unchanged DE and
HBA, or durable UNKNOWN/no retry. No auto-inverse after uncertain COMMIT.
Independent maintenance window must exclude concurrent catalog DDL; a
serializable catalog check alone does not establish comprehensive exclusion.

## Owner action — first read-only production evidence

On HEL1, the three source-pinned read-only capture files have been staged
in owner-only /home/tony/we1-hd-direct-media-preimage-v3-20261124 (0700);
SQL files 0600, helper 0700. Native SHA readback matched all three.
No protected directory, database, HBA, service, or root executor mutated.
Earlier stages are superseded for admission. V2 owner production capture
completed during review and is retained unmodified at
/home/tony/we1-hd-direct-media-preimage-v2-20261124/capture-fqljdQoo.
Manifest SHA256 28839242f5c917a4a81f2fa3ccb504023d6bf00c3f5ccb93071ff71d759d7705;
6/6 files independently verified. PG16.15, both media object counts zero,
HBA parse errors and enabled event triggers zero, HD text body MD5 exact.
Observed four HD target owners aoe2hd_user, RLS/force RLS false, no enabled
custom target triggers, eight inbound FKs to target relations enumerated
for independent review; no claim comprehensive financial exclusion. Both login roles
reported no transitive membership; DE CONNECT ACL still true, not proof
of usable authentication. Require actual HBA/SCRAM denial.
The v2 helper had a check/use race identified by WE2; its production
observation is preliminary, not an exact-byte admission witness. V3 now
loads both bounded owner-private SQL files once with no-follow descriptors,
validates ownership/mode/inode/size/timestamps/hash and executes only the
retained immutable bytes via fixed local psql. Requires corrected owner
capture and independent review of actual protected catalog before admission.

From the owner's real M1 terminal run:

    ssh -t hel1 /home/tony/we1-hd-direct-media-preimage-v3-20261124/c03_hd_direct_media_owner_preimage.py

Type READ-ONLY-HD-DIRECT-MEDIA and authenticate sudo locally if requested.
Do not send password or any signing private material to ChatGPT.
The helper runs only catalog SELECTs under read-only transactions, captures
both HD and DE digests plus private raw audit and host/HBA pins, and prints
digest-only witness. Share capture path and hashes, not raw secrets.
Prior noninteractive sudo postgres access refused; ordinary sudo allowlists
do not authorize copying/executing a new root controller.

## After independent review only

1. WE2 reviews exact source, actual owner-presence catalog audit, HBA ordering,
   no financial grants, service identity, maintenance exclusivity and
   protected delivery path. Root installs only exact source files under
   /usr/local/libexec/aoe2war-chat-media-hd-v1, root-owned private 0600,
   directories root-owned without group/world write. Root trust and journal
   directories /etc/aoe2war-chat-media-hd-v1 and /var/lib/aoe2war-chat-media-hd-v1
   private 0700. Root review.json fields are exact schema
   wolo.we1.hd-direct-media-root-review.v1, source_commit, executor_sha256,
   file_sha256 (install/inverse/witness), host_id_sha256, hba_sha256,
   owner_public_sha256. Separate approved owner M1 terminal invokes
   Swift signer enroll to a private 0600 public export; no key export
   except public bytes. No existing Social/C08/financial signer reuse.
2. Protected root preflight runs the fixed executor with preflight only;
   independently verify output; copy only that JSON privately to owner M1
   0600. Owner invokes permit builder with install, root preflight JSON,
   enrolled public file and new empty owner 0700 output directory. It
   displays exact request and requires local interactive consent.
   Generation does not deliver or execute. Use approved root delivery
   route for permit-NONCE.json at exact trust directory.
3. Protected root invokes /usr/bin/python3 -I fixed executor install NONCE
   once. No manual ad hoc SQL, no alternate sudo path, no repeat after
   uncertain outcome. Retain root receipt and actual HD SCRAM positive,
   DE/Unix denial, financial privilege witness. Inverse requires separate
   fresh signed request and exact original lineage, never erase media keys.
4. WE2 separately admits private DATA storage/guard/NGINX/sidecar,
   WE3 actual browser acceptance and integrated receipt behavior.
   Delivery acknowledgement means authenticated recipient fetched the
   message; it does not mean read. Read receipts remain unsupported.
   CHAT_DB_READY requires actual live proof, not this source PR.

Financial #258 frozen. No gate closure, funding, custody or product
release permission from this work.
