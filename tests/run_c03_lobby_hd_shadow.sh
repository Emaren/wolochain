#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
BIN="${PG_BINDIR:-$(dirname "$(command -v initdb)")}"
for n in initdb pg_ctl psql; do test -x "$BIN/$n"; done
test "$(id -u)" -ne 0
tmp="$(mktemp -d "/tmp/we1-lb-shadow.XXXXXXXX")"
chmod 700 "$tmp"
mkdir -m 700 "$tmp/socket"
server_running=0
cleanup() {
  if [[ "$server_running" == "1" ]]; then "$BIN/pg_ctl" -D "$tmp/data" -m immediate stop >/dev/null 2>&1 || true; fi
  [[ "$tmp" == *"/we1-lb-shadow."* ]] && rm -rf -- "$tmp"
}
trap cleanup EXIT
"$BIN/initdb" -D "$tmp/data" -U "$(id -un)" --no-sync --auth-local=trust > "$tmp/init.log" 2>&1
export PGHOST="$tmp/socket" PGPORT="${PGPORT:-55981}" PGUSER="$(id -un)" PGDATABASE=postgres
"$BIN/pg_ctl" -D "$tmp/data" -l "$tmp/server.log" -o "-k $PGHOST -p $PGPORT -h ''" start >/dev/null
server_running=1
psqlcmd() { "$BIN/psql" -X -q -A -t -v ON_ERROR_STOP=1 "$@"; }
psqlcmd -f "$ROOT/tests/fixtures/c03_lobby_shadow_schema.sql" > /dev/null
psqlcmd -f "$ROOT/scripts/c03_lobby_chat_hd_v1_install_candidate.sql" > /dev/null
query() { psqlcmd -c "$1"; }
assert_status() {
 python3 -c 'import json,sys; q=json.loads(sys.argv[1]); assert q["status"]==int(sys.argv[2]),q' "$1" "$2"
}
first="$(query "SET ROLE aoe2war_social_writer; SELECT aoe2war_social_hd_v2.lobby_send('real-player-a','source shadow test','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');")"
assert_status "$first" 201
second="$(query "SET ROLE aoe2war_social_writer; SELECT aoe2war_social_hd_v2.lobby_send('real-player-a','source shadow test','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');")"
assert_status "$second" 201
python3 -c 'import json,sys; a,b=map(json.loads,sys.argv[1:]);assert a["body"]["messageId"]==b["body"]["messageId"];assert b["body"]["replayed"] is True' "$first" "$second"
assert_status "$(query "SET ROLE aoe2war_social_writer; SELECT aoe2war_social_hd_v2.lobby_send('real-player-a','changed','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');")" 409
assert_status "$(query "SET ROLE aoe2war_social_writer; SELECT aoe2war_social_hd_v2.lobby_send('real-player-a','too soon','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb');")" 429
assert_status "$(query "SET ROLE aoe2war_social_writer; SELECT aoe2war_social_hd_v2.lobby_send(NULL,'guest','cccccccccccccccccccccccccccccccc');")" 400
assert_status "$(query "SET ROLE aoe2war_social_writer; SELECT aoe2war_social_hd_v2.lobby_send('aoe2hd_ai_scribe','bot','dddddddddddddddddddddddddddddddd');")" 401
history="$(query "SET ROLE aoe2war_social_writer; SELECT aoe2war_social_hd_v2.lobby_history(20,NULL,'real-player-b');")"
python3 -c 'import json,sys; q=json.loads(sys.argv[1]); assert len(q)==2 and q[0]["id"]==100; assert q[0]["body"]=="Historical lobby record"; assert q[0]["reactions"][0]["count"]==2; assert q[0]["reactions"][0]["anonymousCount"]==1; assert "private-guest-session-id-shall-not-leak" not in sys.argv[1];assert "Private tournament message" not in sys.argv[1]' "$history"
for sql in \
  "SELECT guest_session_id FROM public.chat_message_guest_reactions" \
  "INSERT INTO public.chat_messages(room_id,user_id,body) VALUES(10,2,'forbidden')" \
  "SELECT aoe2war_social_hd_v2.leaf_lobby_append(10,2,'forbidden')"; do
 if query "SET ROLE aoe2war_social_writer; $sql;" >/dev/null 2>&1; then
   echo "FAIL: restricted writer succeeded at forbidden SQL: $sql" >&2; exit 1
 fi
done
if query "SET ROLE aoe2war_social_exec_v2; INSERT INTO public.chat_messages(room_id,user_id,body) VALUES(10,2,'forbidden');" >/dev/null 2>&1; then
 echo "FAIL: NOLOGIN executor has raw INSERT" >&2; exit 1
fi
psqlcmd -f "$ROOT/scripts/c03_lobby_chat_hd_v1_inverse_candidate.sql" >/dev/null
test "$(query "SELECT count(*) FROM public.chat_messages WHERE room_id=10;")" == 2
test "$(query "SELECT count(*) FROM aoe2war_social_hd_v2.lobby_message_request_keys;")" == 1
test "$(query "SELECT (to_regprocedure('aoe2war_social_hd_v2.lobby_send(text,text,text)') IS NULL);")" == t
psqlcmd -f "$ROOT/scripts/c03_lobby_chat_hd_v1_install_candidate.sql" >/dev/null
redo="$(query "SET ROLE aoe2war_social_writer; SELECT aoe2war_social_hd_v2.lobby_send('real-player-a','source shadow test','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');")"
assert_status "$redo" 201
python3 -c 'import json,sys;assert json.loads(sys.argv[1])["body"]["replayed"] is True' "$redo"
test "$(query "SELECT count(*) FROM public.chat_messages WHERE room_id=10;")" == 2
echo 'PASS_LOBBY_PG_SHADOW_INSERT_RETRIEVE_IDENTITY_GUEST_DENIAL_RETRY_INVERSE_REPEAT_INSTALL'
