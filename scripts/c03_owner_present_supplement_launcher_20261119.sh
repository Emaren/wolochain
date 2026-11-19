#!/usr/bin/env bash
# WE1 C03 November 19 owner-present SUPPLEMENT only, not full recapture.
# Source exact SHA256 verified. NO database writes, role/HBA/service changes.
set -euo pipefail
umask 077
export PATH=/usr/bin:/bin
SOURCE=/home/tony/we1-c03-owner-reachability-supplement-20261119.sql
EXPECTED_SHA256=4c08e7984db7438c399600808687420c3bda84f2440f529126ad662b8245bfc9
[[ "$(id -un)" == tony ]] || { echo 'HOLD_WRONG_OS_IDENTITY' >&2; exit 20; }
[[ -t 0 && -t 1 && -r /dev/tty ]] || { echo 'HOLD_OWNER_PRESENT_TTY_REQUIRED' >&2; exit 21; }
[[ -f "$SOURCE" && ! -L "$SOURCE" ]] || { echo 'HOLD_MISSING_OR_LINKED_SOURCE' >&2; exit 22; }
[[ "$(sha256sum "$SOURCE" | cut -d' ' -f1)" == "$EXPECTED_SHA256" ]] ||
 { echo 'HOLD_PINNED_SOURCE_SHA256_MISMATCH' >&2; exit 23; }
[[ -x /usr/bin/sudo && -x /usr/bin/psql ]] ||
 { echo 'HOLD_NO_AUTHORIZED_EXISTING_POSTGRES_CLIENT' >&2; exit 24; }
cat >&2 <<'NOTICE'
WE1 C03 — TARGETED SUPPLEMENTAL READ-ONLY HD+DE CATALOG WITNESS.
The previous original full catalog SHA256 files will NOT be changed, copied
or re-run. This examines only missing owner/role/financial-object privilege
and function reachability, plus Library event table ownership/columns/ACL.
One authorized interactive PostgreSQL READ ONLY transaction per DB.
Output stays solely in a new private /home/tony directory (0700/0600).
NO roles, table permissions, passwords, HBA, services, financial rows,
production grants, or root installers will be changed.
This is NOT production finance admission or an installation permit.
NOTICE
printf '\nType READ-ONLY-OWNER-SUPPLEMENT to authorize: ' >/dev/tty
IFS= read -r consent </dev/tty
[[ "$consent" == 'READ-ONLY-OWNER-SUPPLEMENT' ]] ||
 { echo 'HOLD_OWNER_DID_NOT_AUTHORIZE_SUPPLEMENT' >&2; exit 25; }
dir="$(mktemp -d /home/tony/we1-c03-owner-supplement-20261119-XXXXXXXX)"
chmod 700 "$dir"
for db in aoe2hd_db aoe2de_db; do
  tmp="$dir/$db.incomplete"
  target="$dir/$db.owner-reachability.txt"
  echo "Owner-authorized restricted catalog SELECT: $db" >&2
  if ! sudo -u postgres /usr/bin/psql -X -q -A -t -v ON_ERROR_STOP=1 -d "$db" \
       < "$SOURCE" > "$tmp"; then
    echo "HOLD_PRIVILEGED_READ_FAILED: $db; incomplete local output preserved" >&2
    exit 26
  fi
  chmod 600 "$tmp"
  grep -Fq 'SUPPLEMENT_META|' "$tmp" ||
    { echo "HOLD_NO_SUPPLEMENT_META: $db" >&2; exit 27; }
  grep -Fq 'SUPPLEMENT_FINAL|' "$tmp" ||
    { echo "HOLD_NO_FINAL_WITNESS: $db" >&2; exit 28; }
  grep -Fq "\"db\": \"$db\"" "$tmp" ||
    { echo "HOLD_DATABASE_IDENTITY_MISMATCH: $db" >&2; exit 29; }
  grep -Fq '"read_only": "on"' "$tmp" ||
    { echo "HOLD_TRANSACTION_NOT_READ_ONLY: $db" >&2; exit 30; }
  mv -n -- "$tmp" "$target"
done
sha256sum "$dir"/aoe2hd_db.owner-reachability.txt \
          "$dir"/aoe2de_db.owner-reachability.txt > "$dir/sha256.txt"
printf '%s  %s\n' "$EXPECTED_SHA256" "$SOURCE" > "$dir/source.sha256.txt"
chmod 600 "$dir"/*
echo 'OWNER_SUPPLEMENT_READ_ONLY_COMPLETE_NOT_PRODUCTION_ACCEPT' >&2
printf 'PRIVATE_SUPPLEMENT_DIR=%s\n' "$dir"
printf 'SOURCE_SHA256=%s\n' "$EXPECTED_SHA256"
cat "$dir/sha256.txt"
