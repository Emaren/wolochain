WE1 CHAT SOCIAL V2 — PURPOSE-LOCKED ROOT / DATABASE EXECUTOR (SOURCE CANDIDATE)

NOT A ROOT INSTALL PERMIT. NOT A WRITER ACTIVATION. NO FUNDING AUTHORITY.

Review scope
------------
Corrected SQL source PR250 HEAD:
  5cf4f223a7b187f6596b6a9caac26aec7afd6e94
Corrected Social install SHA256:
  9793ff39ca80d646a89041f0174f42bb717ae3e649e49f8d68d6f102792f5c51
Exact inverse SHA256:
  84114bac7b3e15f4cadaf3a566f705440eeb9cf8ba63f3be97249652d5f25449
WE2 installed HBA SHA256:
  3fecbffb683bf2bc21e8bd880b9be982d14cbe3bbf67aae08f801159d6b76789

Source files (separate new Chat-only authority)
------------------------------------------------
c03_chat_social_hd_v2_exact_executor.py — only install/inverse phases,
 fixed five-file SHA, fixed HD database, fixed owner public key domain,
 nonce persisted before SQL, exact local OS postgres peer (no arbitrary SQL),
 readonly pre/post and identical 12-object + column ACL fingerprint,
 actual HBA source hash/ordering, bounded SQL, inverse attempt on post failure,
 separate root receipt and crash/unknown handling.

c03_chat_social_root_enroll_v1.py — fixed-source, signed, one-time WE2 root
 trust enrollment AND separately signed DB permit-delivery operation.
 Neither action runs SQL. Requires real root operator and independent review.

c03_chat_social_owner_keychain_v1.swift — new macOS Keychain tag and purpose
 domain, never Library/PRODUCT/C08/custody/financial keys.
 Owner private signing material stays in Mac Keychain.

c03_chat_social_owner_permit_builder_v1.py — owner Mac only, creates new
 ten-minute signed enrollment or SQL packet AFTER protected admission.
 Creation alone does not authorize root/SQL activity. No credential material.

c03_chat_social_v2_preimage_readonly.sql — exact HD original-owner,
 8 legacy tables, 4 sequences, nil/explicit ACLs and trigger restrictions.

c03_chat_social_v2_postimage_readonly.sql — exact 7 security-barrier views,
 5 SECURITY DEFINER function names/owners, fixed 2 high-level callable
 functions, restricted role/leaf, raw tables and finance-name negatives.

c03_chat_social_v2_acl_witness_readonly.sql — deterministic original
 12 table/sequence raw ACL entries and all original column ACLs;
 byte-identical output required pre and post.

tests/test_c03_chat_social_hd_v2_exact_executor.py — 29 separate offline
 adverse tests; no claims of live SQL, authorized root or signed credential.

TRUST AND INSTALL ORDER — WE2 MUST ACCEPT FIRST
------------------------------------------------
1. Independent WE2 review of this complete new source and exact Git SHA,
 owner key public fingerprint, source-specific SQL/inverse/witness SHA,
 actual HEL1 HBA, root-only target ownership and protected operator path.
 Protected owner root approval for exactly CHAT_SOCIAL_HD_V2_ROOT_ENROLL_ONLY.
 No Library executor, signer, phase, path, nonce, permit, key or role reuse.
2. Owner invokes Mac-only Keychain builder 'enroll' with a NEW private 0700
 output dir; verify resulting signature with independent OpenSSL.
 A fresh <=900-sec signed enrollment request binds bootstrap and all
 source blobs. Only WE2 may approve/invoke the fixed root installer 'enroll'
 through the legitimate protected channel. Root receipt status is
 PASS_CHAT_SOCIAL_ROOT_TRUST_ENROLLED_NO_SQL — NOT database readiness.
3. After root postimage accepted, owner invokes builder 'install' using
 NEW nonce and ten-minute window. Specific protected root operation
 'install-permit' checks signed source+HBA packet, root-own O_EXCL writes
 and emits PASS_SIGNED_CHAT_SOCIAL_PERMIT_ROOT_DELIVERED_NO_SQL.
 This is a separate admitted channel, not a generic root copy/SCP bypass.
4. Run only the root-owned Social executor 'install' ONCE (not the root
 installer), which consumes its nonce BEFORE any PostgreSQL phase.
 Current production HBA must have first-match local reject, HD IPv4
 SCRAM allow, all-db IPv4 reject, and IPv6 reject for Chat role.
 PostgreSQL server pid must remain unchanged; exact 8/4 raw ACL and
 column ACL fingerprint before and after; two roles and 7 views/5
 functions; finance/DE no-grant and original-fence review. Preserve
 durable root SQL receipt; refuse an expired or consumed permit.
5. WE2, separately, must configure the writer-only SCRAM secret in
 protected sidecar environment and prove real credentialed HD-positive,
 DE IPv4+IPv6-negative and local peer negative BEFORE web exposure.
 Never put writer DB password in the Next.js web process or repository.
 Then real signed-session UID -> fixed SQL sender binding, existing
 Emaren/Scribe Clan/Direct recipient/member privacy and persistence.
 Factory T6–T10 and site activation are separate WE2 protected actions.

ROOT CONTROL PATHS — MUST BE WE2 INDEPENDENTLY ADMITTED
-------------------------------------------------------
Owner-private candidate stage:
 /home/tony/we1-chat-social-v2-executor-stage-20261120
WE2 root trust:
 /etc/wolo-financial-chat-social-v2
Root-owned executable and five exact SQL:
 /usr/local/libexec/wolo-financial-chat-social-v2
Root nonce, delivery and SQL execution receipts:
 /var/lib/wolo-financial-role-state/v1/chat-social-hd-v2-exact

Source patch and scoped CI are not a permit. Foundation CI on source
PR250 remains RED solely on expired financial-document reviews; do NOT
silently extend reviews or claim full CI green. C04/C08 CLOSED, seven
other financial gates OPEN, funding DENIED. Library live/T10 untouched.

Independent review must verify credential compromise, sign-window,
unknown/crash, on-host shadow paths and no root-invocation substitution
before operator execution. The executors cannot prove a whole-financial
writer fence merely from targeted negative privilege checks.
