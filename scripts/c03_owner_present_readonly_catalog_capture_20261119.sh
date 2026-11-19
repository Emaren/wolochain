#!/usr/bin/env bash
# WE1: owner-present, source-pinned, READ-ONLY HD/DE catalog capture.
# THIS IS NOT A FINANCIAL SQL/HBA/GRANT/ROOT INSTALL PERMIT.
set -euo pipefail
umask 077
export PATH=/usr/bin:/bin

EXPECTED_SOURCE_SHA256='a25b85c8f5f1cb95d6e320029d6ff5267cd7fd9fd6180b9c34e777f15f1aa8e7'
SOURCE='/home/tony/we1-c03-catalog-hd-de-readonly-20261119.sql'

[[ $(id -un) == 'tony' ]] || { echo 'HOLD: expected exact owner SSH user tony' >&2; exit 20; }
[[ -t 0 && -t 1 && -r /dev/tty ]] || { echo 'HOLD: requires owner-present interactive terminal' >&2; exit 21; }
[[ -f "$SOURCE" && ! -L "$SOURCE" ]] || { echo 'HOLD: missing or linked catalog source' >&2; exit 22; }
actual=$(sha256sum "$SOURCE" | awk '{print $1}')
[[ "$actual" == "$EXPECTED_SOURCE_SHA256" ]] || { echo 'HOLD: catalog SQL SHA256 mismatch' >&2; exit 23; }
[[ -x /usr/bin/psql && -x /usr/bin/sudo ]] || { echo 'HOLD: system PostgreSQL or sudo unavailable' >&2; exit 24; }

cat >&2 <<'NOTICE'
WE1 FINANCIAL CATALOG — READ-ONLY OWNER-PRESENCE CAPTURE
Source is SHA-256 pinned. The capture reads only PostgreSQL system catalogs
for database names aoe2hd_db and aoe2de_db, using an existing sudo policy.
It NEVER creates roles, grants, functions, or changes HBA/systemd.
No output is uploaded or transmitted. Output stays in a private owner directory.
This is NOT a production writer fence or SQL installer permission.
If existing sudo policy doesn't permit postgres psql, it will STOP.
NOTICE
printf '\nTo authorize these two read-only catalog SELECTs, type READ-ONLY-HD-DE: ' >/dev/tty
IFS= read -r approval </dev/tty
[[ "$approval" == 'READ-ONLY-HD-DE' ]] || { echo 'HOLD: owner did not approve capture' >&2; exit 25; }

root='/home/tony'
[[ -d "$root" && -w "$root" ]] || { echo 'HOLD: owner home inaccessible' >&2; exit 26; }
outdir=$(mktemp -d "$root/we1-c03-catalog-witness-20261119-XXXXXXXX")
chmod 700 "$outdir"

for db in aoe2hd_db aoe2de_db; do
  case "$db" in aoe2hd_db|aoe2de_db) :;; *) exit 27;; esac
  tmp="$outdir/${db}.catalog.incomplete"
  final="$outdir/${db}.catalog.txt"
  echo "Reading $db with existing sudo permissions (interactive owner authentication may be requested)..." >&2
  # Redirection performed by the unprivileged owner shell; postgres reads
  # source SQL from stdin. No credential is exported or accepted from ChatGPT.
  if sudo -u postgres /usr/bin/psql -X -q -A -t -v ON_ERROR_STOP=1 -d "$db" < "$SOURCE" > "$tmp"; then
    chmod 600 "$tmp"
    mv -n -- "$tmp" "$final"
    [[ -s "$final" ]] || { echo "HOLD: empty $db catalog output" >&2; exit 28; }
    grep -Fq 'FINAL_NONAUTHORIZATION|' "$final" || { echo "HOLD: $db capture incomplete" >&2; exit 29; }
    grep -Fq 'AUDIT_META|' "$final" || { echo "HOLD: $db identity absent" >&2; exit 30; }
    grep -Fq "\"db\": \"$db\"" "$final" || { echo "HOLD: $db identity mismatch" >&2; exit 31; }
  else
    echo "HOLD: $db read denied or query failed; partial output retained privately as .incomplete" >&2
    exit 32
  fi
done
printf '%s\n' "$EXPECTED_SOURCE_SHA256  $SOURCE" > "$outdir/source.sha256.txt"
sha256sum "$outdir"/aoe2hd_db.catalog.txt "$outdir"/aoe2de_db.catalog.txt > "$outdir/output.sha256.txt"
chmod 600 "$outdir"/*
echo 'READ-ONLY_CAPTURE_COMPLETED: local private files only; NOT PHYSICAL ACCEPTANCE' >&2
printf 'PRIVATE_EVIDENCE_DIRECTORY=%s\n' "$outdir"
printf 'SOURCE_SHA256=%s\n' "$EXPECTED_SOURCE_SHA256"
cat "$outdir/output.sha256.txt"
