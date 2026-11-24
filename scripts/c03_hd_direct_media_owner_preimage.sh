#!/usr/bin/env bash
# Owner-present catalog-only native capture. Never a SQL install permit.
set -euo pipefail
umask 077
export PATH=/usr/bin:/bin
root='/home/tony/we1-hd-direct-media-preimage-20261124'
witness="$root/c03_hd_direct_media_catalog_witness.sql"
audit="$root/c03_social_writer_catalog_readonly.sql"
[[ $(id -un) == tony && -t 0 && -t 1 && -r /dev/tty ]] || { echo 'HOLD_OWNER_TERMINAL_REQUIRED' >&2; exit 3; }
[[ -d "$root" && ! -L "$root" && -O "$root" && -f "$witness" && ! -L "$witness" && -f "$audit" && ! -L "$audit" ]] || exit 3
[[ $(sha256sum "$witness" | awk '{print $1}') == 29d57312178c9ea3aeaaa215fce53ad1438316465c8508ff3d2f507c34826582 ]] || exit 3
[[ $(sha256sum "$audit" | awk '{print $1}') == a25b85c8f5f1cb95d6e320029d6ff5267cd7fd9fd6180b9c34e777f15f1aa8e7 ]] || exit 3
echo 'Read-only HD/DE PostgreSQL catalogs only; no player rows, DDL, grants, service changes, or financial authority.'
printf 'Type READ-ONLY-HD-DIRECT-MEDIA to authorize catalog capture: ' >/dev/tty
IFS= read -r approval </dev/tty
[[ "$approval" == READ-ONLY-HD-DIRECT-MEDIA ]] || exit 3
# Genuine owner authentication in the existing local terminal if required.
sudo -v
out=$(mktemp -d "$root/capture-XXXXXXXX")
chmod 700 "$out"
for db in aoe2hd_db aoe2de_db; do
 { printf '%s\n' "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;" "SET LOCAL search_path=pg_catalog,pg_temp;" "SET LOCAL statement_timeout='5s';" "SET LOCAL lock_timeout='350ms';"; cat "$witness"; printf '\n;\nROLLBACK;\n'; } |
   sudo -u postgres /usr/bin/psql -X -w -qAt -v ON_ERROR_STOP=1 -h /var/run/postgresql -p 5432 -d "$db" > "$out/$db.witness.incomplete"
 /usr/bin/python3 - "$out/$db.witness.incomplete" "$db" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x['database']==sys.argv[2] and x['pg_version'].startswith('16') and x['enabled_event_triggers']==0 and x['hba_parse_errors']==0
PY
 mv "$out/$db.witness.incomplete" "$out/$db.witness.json"
 sudo -u postgres /usr/bin/psql -X -w -qAt -v ON_ERROR_STOP=1 -h /var/run/postgresql -p 5432 -d "$db" < "$audit" > "$out/$db.private-audit.incomplete"
 grep -q '^FINAL_NONAUTHORIZATION|' "$out/$db.private-audit.incomplete"
 mv "$out/$db.private-audit.incomplete" "$out/$db.private-audit.txt"
done
tr -d '\n' </etc/machine-id | sha256sum | awk '{print $1}' > "$out/host-id.sha256"
sudo -u postgres /usr/bin/sha256sum /etc/postgresql/16/main/pg_hba.conf | awk '{print $1}' > "$out/hba.sha256"
(cd "$out" && sha256sum -- *.json *.txt *.sha256 > capture-manifest.sha256)
printf 'READ_ONLY_CAPTURE_COMPLETE_NOT_ADMISSION=%s\n' "$out"
cat "$out/aoe2hd_db.witness.json" "$out/aoe2de_db.witness.json"
