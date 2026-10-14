#!/usr/bin/env bash
# Source-controlled, node-no-touch snapshot of two production settlement lanes.
# Inspect mode is read-only. Snapshot mode writes ONLY to a private new backup dir.
# NO live state restore is authorized: it can re-open settled payout requests.
set -euo pipefail
umask 077

MODE="${1:---inspect}"
case "$MODE" in --inspect|--snapshot) ;; *) echo "usage: sudo bash $0 [--inspect|--snapshot]" >&2; exit 2 ;; esac
(( EUID == 0 )) || { echo "STOP: run via sudo bash (in a child shell)" >&2; exit 2; }

VOL=/mnt/HC_Volume_105319120
ROOT="$VOL/wolochain-mainnet"
BACKUP_ROOT="$ROOT/settlement-backups"
PRIMARY_ENV=/etc/wolochain-mainnet-settlement.env
FOUNDER_ENV=/etc/wolochain-founder-rewards-settlement.env
PRIMARY_STATE="$ROOT/settlement-state"
FOUNDER_STATE="$ROOT/founder-rewards-settlement-state"
PRIMARY_UNIT=wolochain-mainnet-settlement.service
FOUNDER_UNIT=wolochain-founder-rewards-settlement.service
NODE_UNIT=wolochaind-mainnet.service
OLD_BIN=/usr/local/bin/wolochaind-mainnet
NODE_BIN=/usr/local/bin/wolochaind-mainnet-node-prewartrophy
CANDIDATE="$ROOT/settlement-candidates/3ea79363/wolochaind-settlement-only-linux-amd64"
REPO=/var/www/WoloChain-wolo-1
EXPECTED_VPS_REV=78c25985420ee41a6678c42fab8ea8d6c3b1b519
EXPECTED_OLD=040126a2884946caf1651a50b7d8115c5a6fb2d5aa94fcbbe150694602d451a5
EXPECTED_NODE=4b77f622191db7550cb87cafb8f1886a0aadebee3eb6565f9f90036f809e61d3
EXPECTED_NEW=af18e18bd32ef5763d3e414a37dd7886fe4065b640bb5a89ae742ee860fb9b87

stop() { echo "STOP: $*" >&2; exit 2; }
hash() { sha256sum "$1" | awk '{print $1}'; }
check_file() {
  local label="$1" path="$2" expected="$3"
  [[ -f "$path" && ! -L "$path" ]] || stop "$label is absent or a symlink"
  [[ "$(hash "$path")" == "$expected" ]] || stop "$label SHA256 changed"
  echo "PASS $label SHA256 matches pinned baseline"
}
check_env() {
  local path="$1" s
  [[ -f "$path" && ! -L "$path" ]] || stop "$path absent or symlink"
  s="$(stat -c '%u:%g:%a' "$path")"
  [[ "$s" == "0:0:600" ]] || stop "$path is not root:root mode 600"
  echo "PASS $(basename "$path") root:root mode 600 (contents not displayed)"
}
check_state() {
  local path="$1"
  [[ -d "$path" && ! -L "$path" ]] || stop "missing state directory: $path"
  # Do not silently snapshot an in-flight request/run lock.
  [[ -z "$(find "$path" -type f -name '*.lock' -print -quit)" ]] ||
    stop "lock file present under $path; refuse online snapshot"
  [[ -z "$(find "$path" ! -type f ! -type d -print -quit)" ]] ||
    stop "unsupported special file or symlink in $path"
  du -sh "$path"
}
check_unit() {
  local name="$1" expected_program="$2" expected_hash="$3" pid path checksum
  systemctl is-active --quiet "$name" || stop "$name is not active"
  pid="$(systemctl show -P MainPID "$name")"
  [[ "$pid" =~ ^[1-9][0-9]*$ ]] || stop "$name has no running PID"
  path="$(readlink "/proc/$pid/exe")"
  [[ "$path" == "$expected_program" ]] || stop "$name unexpected running program: $path"
  checksum="$(hash "/proc/$pid/exe")"
  [[ "$checksum" == "$expected_hash" ]] || stop "$name running process hash changed"
  printf 'PASS %-44s PID=%s binary=%s\n' "$name" "$pid" "$checksum"
}

# A manifest uses relative paths and stable order; no contents are printed.
state_manifest() {
  local where="$1" outfile="$2"
  ( cd "$where" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum ) > "$outfile"
}
state_manifest_tmp() {
  local where="$1"
  ( cd "$where" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum )
}
compare_state() {
  local source="$1" backed="$2" manifest="$3" label="$4"
  state_manifest "$backed" "$manifest"
  state_manifest_tmp "$source" | cmp -s "$manifest" - ||
    stop "$label state changed during copy (or copy mismatch); snapshot NOT certified"
  echo "PASS $label copied state matched live source at post-copy observation"
}

echo "=== WOLO MAINNET: TWO-SERVICE SNAPSHOT PRECHECK ($MODE) ==="
date -u '+UTC %Y-%m-%dT%H:%M:%SZ'
mountpoint -q "$VOL" || stop "settlement volume not mounted"
[[ "$(git -C "$REPO" rev-parse HEAD)" == "$EXPECTED_VPS_REV" ]] ||
  stop "VPS source checkout unexpectedly moved"
[[ -z "$(git -C "$REPO" status --porcelain)" ]] || stop "VPS repo dirty"
[[ "$(stat -c '%u:%g' "$BACKUP_ROOT")" == "0:0" ]] || stop "backup root ownership changed"
check_file "original shared settlement binary" "$OLD_BIN" "$EXPECTED_OLD"
check_file "preserved consensus binary" "$NODE_BIN" "$EXPECTED_NODE"
check_file "staged verifier candidate" "$CANDIDATE" "$EXPECTED_NEW"
check_env "$PRIMARY_ENV"
check_env "$FOUNDER_ENV"
check_unit "$PRIMARY_UNIT" "$OLD_BIN" "$EXPECTED_OLD"
check_unit "$FOUNDER_UNIT" "$OLD_BIN" "$EXPECTED_OLD"
check_unit "$NODE_UNIT" "$NODE_BIN" "$EXPECTED_NODE"
check_state "$PRIMARY_STATE"
check_state "$FOUNDER_STATE"
echo "=== VOLUME CAPACITY ==="
df -h "$VOL"
free_kb="$(df -Pk "$VOL" | awk 'NR==2 {print $4}')"
(( free_kb >= 1048576 )) || stop "less than 1GiB of volume headroom"
echo "PASS minimum volume headroom"
if [[ "$MODE" == "--inspect" ]]; then
  echo "INSPECTION ONLY: no files written, no services or secrets altered"
  exit 0
fi

snapshot="$BACKUP_ROOT/$(date -u +%Y%m%dT%H%M%SZ)-two-settlement-node-untouched"
[[ ! -e "$snapshot" && ! -L "$snapshot" ]] || stop "snapshot path exists"
install -d -o root -g root -m 0700 "$snapshot"
echo 'INCOMPLETE: NOT A VERIFIED BACKUP; DO NOT RESTORE' > "$snapshot/INCOMPLETE"
mkdir -m 0700 "$snapshot/config" "$snapshot/units" "$snapshot/state" "$snapshot/proof"
echo "Created private snapshot; root:root mode 0700"

# Protect secrets inside a directory that is NOT user-readable.
cp -p "$PRIMARY_ENV" "$snapshot/config/primary.env"
cp -p "$FOUNDER_ENV" "$snapshot/config/founder.env"
install -o root -g root -m 0600 "$OLD_BIN" "$snapshot/config/original-settlement-executable"
install -o root -g root -m 0600 "/etc/systemd/system/$PRIMARY_UNIT" "$snapshot/units/$PRIMARY_UNIT"
install -o root -g root -m 0600 "/etc/systemd/system/$FOUNDER_UNIT" "$snapshot/units/$FOUNDER_UNIT"
# This captures the effective node config as evidence. It never edits the node.
systemctl cat "$NODE_UNIT" > "$snapshot/units/node-effective-readonly.txt"
chmod 0600 "$snapshot/units/node-effective-readonly.txt"
cp -a "$PRIMARY_STATE" "$snapshot/state/primary"
cp -a "$FOUNDER_STATE" "$snapshot/state/founder"

# Capture private hashes and ensure there was no in-flight lock or file drift.
check_state "$PRIMARY_STATE"
check_state "$FOUNDER_STATE"
compare_state "$PRIMARY_STATE" "$snapshot/state/primary" "$snapshot/proof/primary-files.sha256" primary
compare_state "$FOUNDER_STATE" "$snapshot/state/founder" "$snapshot/proof/founder-files.sha256" founder
check_file "live original after copy" "$OLD_BIN" "$EXPECTED_OLD"
check_unit "$NODE_UNIT" "$NODE_BIN" "$EXPECTED_NODE"
check_unit "$PRIMARY_UNIT" "$OLD_BIN" "$EXPECTED_OLD"
check_unit "$FOUNDER_UNIT" "$OLD_BIN" "$EXPECTED_OLD"

( cd "$snapshot" &&
  find config units -type f -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum > proof/config-files.sha256 )
( cd "$snapshot" && sha256sum -c proof/config-files.sha256 >/dev/null ) ||
  stop "snapshot config verification failed"

rm "$snapshot/INCOMPLETE"
printf '%s\n'   "SNAPSHOT_OK: both environment files, original executable, unit configurations,"   "both state trees, independent digests, and unchanged live process fingerprints."   "State was copied online; never restore historical state automatically after payouts."   "Rollback contract: remove only the two settlement override drop-ins, reload systemd,"   "and return both settlement services to the intact shared executable."   "Never restart the consensus node or use generic shared-binary restore." > "$snapshot/proof/RECEIPT.txt"
chmod 0600 "$snapshot/proof/RECEIPT.txt"
echo "PASS private two-service snapshot completed at $snapshot"
echo "NOT DEPLOYED: only backup files created; no systemd or live chain operation"
echo "DO NOT RESTORE STATE BLINDLY: existing idempotency records must remain authoritative"
