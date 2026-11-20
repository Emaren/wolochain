WE1 LOBBY CHAT HD V1 — SECOND SIGNED-SESSION GATEWAY (SOURCE CANDIDATE)

DO NOT EQUATE SHADOW SQL WITH PROD ADMISSION. NO FINANCIAL PERMISSIONS.

Source dependency: WoloChain Social V2 PR #251 must have genuine
INSTALLED_POSTIMAGE_PASS, HD-only HBA SCRAM and signed-session AF_UNIX
sidecar. The two existing Social roles are reused; no new LOGIN role
or raw website-table grant is introduced. Until the signed-session
adapter binds Steam session->canonical verified UID (never browser body),
a DB function argument is not authenticated and this is NOT safe to expose.

SQL install: c03_lobby_chat_hd_v1_install_candidate.sql
SQL inverse: c03_lobby_chat_hd_v1_inverse_candidate.sql

Exact API writer boundary (WE2/WE3 implementation dependency):
  AF_UNIX private sidecar:
    lobby.send({signedSessionClaims, body, idempotencyKey})
    -> EXECUTE aoe2war_social_hd_v2.lobby_send(
         verified_uid_from_authenticated_session, normalized_body,
         32-lowercase-hex-client-idempotency-key)
    -> status 201/id/replayed or 400/401/409/429/503
  No uid argument from HTTP body, arbitrary SQL, raw Prisma ChatMessage
  writes, guest message send, or AI/system impersonation.
  AI persona reply insert is separately NOT AUTHORIZED by this contract;
  degrade gracefully until a distinct service identity is reviewed.
  Lobby-only roomSlug 'main-lobby' fixed. Other room requests unsupported.
  Caller must rate-limit and preserve session/CSRF validation.

Exact public history boundary:
  EXECUTE aoe2war_social_hd_v2.lobby_history(limit 1..120,beforeId,
    verified viewer UID or null)
  RETURNS JSON rows + registered & anonymous emoji aggregates and
  display names. Never returns guest_session_id; guest viewerReacted
  cannot be reconstructed and is false in this first version.
  Existing original chat_messages, rooms and reactions untouched.
  No raw SELECT on chat_message_guest_reactions to website or
  aoe2war_social_writer. GET must route through shaped read function,
  not Prisma nested guestReactions select.

SQL security graph:
  5 security_barrier views owned aoe2hd_user, SELECT to NOLOGIN exec.
  leaf_lobby_append SECURITY DEFINER owned original table owner.
  lobby_send/history SECURITY DEFINER owned NOLOGIN social_exec_v2.
  writer only EXECUTE on two high-level functions; no raw INSERT/SELECT.
  private dedupe table persists through inverse and repeat install.
  Inverse removes only gateway views/functions/grants, no historical
  lobby rows, reactions, users or idempotency records.

Independently rerunnable isolated PostgreSQL (no HEL1):
  PG_BINDIR=/opt/homebrew/bin bash tests/run_c03_lobby_hd_shadow.sh
  On Ubuntu 24.04 use PG_BINDIR=/usr/lib/postgresql/16/bin.
  201 send, replay same message ID, 409 changed payload, 429 cooldown,
  guest/system denial, history+reactions, private-room isolation, raw
  guest-session SELECT denial, raw message INSERT denial, leaf EXECUTE
  denial, inverse preserving existing data, repeat install preserving
  dedupe. Test fixtures are fabricated and must never be represented
  as real Emaren/Scribe or a production authenticated session.

Required PRE-PROD acceptances, not satisfied by source:
  - independent WE1/WE2 review, exact signed SQL/inverse hashes;
  - fresh separate owner-authorized root SQL permit and retained rollback;
  - real HD installed postimage, exact view/definer owners and original ACL;
  - HD SCRAM positive, DE IPv4/IPv6 and Unix denial, financial isolation;
  - physical AF_UNIX signed-session sender identity binding/guest denial;
  - WE3 app change removes legacy Prisma create for lobby POST and
    raw guest-session SELECT on Lobby GET; new qualified app artifact;
  - two-account live persistent send/read/replay and rollback/T10.
  Only then emit separately verified LOBBY_CHAT_DB_READY.
