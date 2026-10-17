#!/usr/bin/env bash
# Production WoloChain two-settlement preflight ONLY.
# No systemd, file, wallet, state or chain mutation is performed.
set -euo pipefail

(( EUID == 0 )) || { echo "STOP: use sudo bash <reviewed-script> (runs in a child shell)" >&2; exit 2; }

VOL=/mnt/HC_Volume_105319120
BASE="$VOL/wolochain-mainnet"
BACKUP="$BASE/settlement-backups/20261014T091735Z-two-settlement-node-untouched"
CANDIDATE="$BASE/settlement-candidates/3ea79363/wolochaind-settlement-only-linux-amd64"
OLD=/usr/local/bin/wolochaind-mainnet
NODE=/usr/local/bin/wolochaind-mainnet-node-prewartrophy
REPO=/var/www/WoloChain-wolo-1
PRIMARY=wolochain-mainnet-settlement.service
FOUNDER=wolochain-founder-rewards-settlement.service
NODE_UNIT=wolochaind-mainnet.service
OLD_SHA=040126a2884946caf1651a50b7d8115c5a6fb2d5aa94fcbbe150694602d451a5
NODE_SHA=4b77f622191db7550cb87cafb8f1886a0aadebee3eb6565f9f90036f809e61d3
NEW_SHA=af18e18bd32ef5763d3e414a37dd7886fe4065b640bb5a89ae742ee860fb9b87
CHECKOUT_REV=78c25985420ee41a6678c42fab8ea8d6c3b1b519

fail() { echo "BLOCKED: $*" >&2; exit 2; }
hash() { sha256sum "$1" | awk '{print $1}'; }
assert_hash() {
  local label="$1" path="$2" expected="$3"
  [[ -f "$path" && ! -L "$path" ]] || fail "$label missing, not a regular file, or symlink"
  [[ "$(hash "$path")" == "$expected" ]] || fail "$label SHA-256 mismatch"
  echo "PASS $label"
}
check_proc() {
  local name="$1" path="$2" checksum="$3" pid gotpath
  systemctl is-active --quiet "$name" || fail "$name inactive"
  pid="$(systemctl show -P MainPID "$name")"
  [[ "$pid" =~ ^[1-9][0-9]*$ ]] || fail "$name missing main PID"
  gotpath="$(readlink "/proc/$pid/exe")"
  [[ "$gotpath" == "$path" ]] || fail "$name executable differs from approved baseline"
  [[ "$(hash "/proc/$pid/exe")" == "$checksum" ]] || fail "$name running hash differs"
  printf 'PASS running %s PID=%s\n' "$name" "$pid"
}
listen_addr() {
  local file="$1"
  # Never dump source env or generic systemctl show Environment.
  python3 - "$file" <<'PY'
import pathlib
import re
import sys
found = []
for line in pathlib.Path(sys.argv[1]).read_text().splitlines():
    match = re.fullmatch(r"\s*(?:export\s+)?WOLO_SETTLEMENT_LISTEN_ADDR\s*=\s*(['\"]?)([^'\"\s]+)\1\s*", line)
    if match:
        found.append(match.group(2))
if len(found) != 1 or not re.fullmatch(r"127\.0\.0\.1:[0-9]{2,5}", found[0]):
    raise SystemExit("BLOCKED: missing, repeated, or unexpected loopback listen configuration")
print(found[0])
PY
}
echo "=== WOLO TWO-SERVICE CONTROLLED PROMOTION: READ-ONLY PREFLIGHT ==="
date -u '+UTC %Y-%m-%dT%H:%M:%SZ'
mountpoint -q "$VOL" || fail "dedicated volume not mounted"
[[ "$(git -C "$REPO" rev-parse HEAD)" == "$CHECKOUT_REV" ]] || fail "source checkout changed"
[[ -z "$(git -C "$REPO" status --porcelain)" ]] || fail "VPS source checkout dirty"
assert_hash "unmodified old shared executable" "$OLD" "$OLD_SHA"
assert_hash "preserved dedicated consensus executable" "$NODE" "$NODE_SHA"
assert_hash "verified staged candidate" "$CANDIDATE" "$NEW_SHA"
check_proc "$PRIMARY" "$OLD" "$OLD_SHA"
check_proc "$FOUNDER" "$OLD" "$OLD_SHA"
check_proc "$NODE_UNIT" "$NODE" "$NODE_SHA"

for name in "$PRIMARY" "$FOUNDER"; do
  [[ "$(systemctl show -P DropInPaths "$name")" == "" ]] ||
    fail "$name has unreviewed drop-in overrides"
  [[ "$(systemctl show -P FragmentPath "$name")" == "/etc/systemd/system/$name" ]] ||
    fail "$name unexpected unit fragment"
  [[ "$(grep -Ec '^ExecStart=/usr/local/bin/wolochaind-mainnet[[:space:]]+settlement[[:space:]]+serve[[:space:]]*$' "/etc/systemd/system/$name")" == 1 ]] ||
    fail "$name ExecStart not exact audited settlement serve"
  echo "PASS $name original unit and effective override-free configuration"
done

[[ -d "$BACKUP" && ! -L "$BACKUP" ]] || fail "private backup missing or symlink"
[[ "$(stat -c '%u:%g:%a' "$BACKUP")" == "0:0:700" ]] ||
  fail "backup directory not root-only 0700"
[[ ! -e "$BACKUP/INCOMPLETE" ]] || fail "backup marked incomplete"
[[ -f "$BACKUP/proof/RECEIPT.txt" ]] || fail "missing snapshot verification receipt"
( cd "$BACKUP" && sha256sum -c proof/config-files.sha256 >/dev/null ) ||
  fail "backup executable/units/config checksum failure"
( cd "$BACKUP/state/primary" && sha256sum -c ../../proof/primary-files.sha256 >/dev/null ) ||
  fail "primary backup state checksum failure"
( cd "$BACKUP/state/founder" && sha256sum -c ../../proof/founder-files.sha256 >/dev/null ) ||
  fail "founder backup state checksum failure"
echo "PASS root-private snapshot checksum integrity for both services"

primary_env=/etc/wolochain-mainnet-settlement.env
founder_env=/etc/wolochain-founder-rewards-settlement.env
for file in "$primary_env" "$founder_env"; do
  [[ "$(stat -c '%u:%g:%a' "$file")" == "0:0:600" ]] ||
    fail "secret config file permission drift: $file"
done

primary_addr="$(listen_addr "$primary_env")" || fail "primary bind config unknown"
founder_addr="$(listen_addr "$founder_env")" || fail "founder bind config unknown"
[[ "$primary_addr" == "127.0.0.1:8092" ]] || fail "primary bind changed"
[[ "$founder_addr" == "127.0.0.1:8093" ]] || fail "founder bind changed"

echo "PASS primary listen $primary_addr and founder listen $founder_addr"
curl --fail --silent --show-error --max-time 8 "http://$primary_addr/settlement/v1/health" >/dev/null ||
  fail "primary settlement health failed"
curl --fail --silent --show-error --max-time 8 "http://$founder_addr/settlement/v1/health" >/dev/null ||
  fail "founder settlement health failed"
echo "PASS HTTP health both settlement lanes"

for dir in "$BASE/settlement-state" "$BASE/founder-rewards-settlement-state"; do
  [[ -d "$dir" && ! -L "$dir" ]] || fail "current live state dir not accessible"
  [[ -z "$(find "$dir" -type f -name '*.lock' -print -quit)" ]] ||
    fail "in-flight lock under $dir; cannot treat as quiesced"
done
echo "PASS no current request/run lock files observed"
df -h "$VOL"
echo "PREFLIGHT_PASS: repository, backup, binaries, units, binds and current health align"
echo "NOT A DEPLOY AUTHORIZATION: app-side financial drain and protected rollback still required"
