#!/usr/bin/env bash
# Explicit TWO-settlement code rollback. Never rewinds settlement state.
# NEVER restarts/stops the consensus node; never replaces the shared binary.
set -euo pipefail
umask 077

PRIMARY=wolochain-mainnet-settlement.service
FOUNDER=wolochain-founder-rewards-settlement.service
NODE=wolochaind-mainnet.service
OLD=/usr/local/bin/wolochaind-mainnet
NODE_BIN=/usr/local/bin/wolochaind-mainnet-node-prewartrophy
BACKUP=/mnt/HC_Volume_105319120/wolochain-mainnet/settlement-backups/20261014T091735Z-two-settlement-node-untouched
OLD_SHA=040126a2884946caf1651a50b7d8115c5a6fb2d5aa94fcbbe150694602d451a5
NODE_SHA=4b77f622191db7550cb87cafb8f1886a0aadebee3eb6565f9f90036f809e61d3
FILE_NAME=50-aoe2war-settlement-3ea79363.conf
CANDIDATE=/mnt/HC_Volume_105319120/wolochain-mainnet/settlement-candidates/3ea79363/wolochaind-settlement-only-linux-amd64

fail() { printf 'BLOCKED: %s\n' "$*" >&2; exit 2; }
sha() { sha256sum "$1" | awk '{print $1}'; }
assert_hash() {
  local p="$1" expected="$2"
  [[ -f "$p" && ! -L "$p" ]] || fail "missing file or symlink: $p"
  [[ "$(sha "$p")" == "$expected" ]] || fail "binary SHA drift: $p"
}
dropin() {
  printf '/etc/systemd/system/%s.d/%s' "$1" "$FILE_NAME"
}
expected_override() {
  printf '%s\n' \
    '# aoe2war two-settlement code-only 3ea79363' \
    '[Service]' \
    'ExecStart=' \
    "ExecStart=$CANDIDATE settlement serve"
}
inspect_override() {
  local unit="$1" f
  f="$(dropin "$unit")"
  [[ ! -L "$f" ]] || fail "override is symlink: $f"
  if [[ -e "$f" ]]; then
    cmp -s "$f" <(expected_override) || fail "override differs from audited content: $f"
    printf 'PASS audited override for %s\n' "$unit"
  else
    printf 'INFO no owned override for %s\n' "$unit"
  fi
}
check_consensus() {
  local pid actual_path
  pid="$(systemctl show -P MainPID "$NODE")"
  [[ "$pid" =~ ^[1-9][0-9]*$ ]] || fail "no live consensus PID"
  actual_path="$(readlink "/proc/$pid/exe")"
  [[ "$actual_path" == "$NODE_BIN" ]] || fail "node executable path changed"
  [[ "$(sha "/proc/$pid/exe")" == "$NODE_SHA" ]] || fail "node running executable changed"
  echo "PASS consensus remains PID $pid, dedicated pinned executable (NO TOUCH)"
}
check_backup() {
  [[ -d "$BACKUP" && ! -L "$BACKUP" ]] || fail "approved backup missing"
  [[ "$(stat -c '%u:%g:%a' "$BACKUP")" == "0:0:700" ]] || fail "approved backup directory not root-only"
  [[ ! -e "$BACKUP/INCOMPLETE" && -f "$BACKUP/proof/RECEIPT.txt" ]] || fail "backup missing valid receipt"
  (
    cd "$BACKUP"
    sha256sum -c proof/config-files.sha256 >/dev/null
  ) || fail "backup unit/env hash check failed"
  # The historic backup is audit-only; never copy it to LIVE state.
}
check_old_config() {
  for name in "$PRIMARY" "$FOUNDER"; do
    [[ "$(systemctl show -P FragmentPath "$name")" == "/etc/systemd/system/$name" ]] ||
      fail "unexpected live unit: $name"
    [[ -f "/etc/systemd/system/$name" && ! -L "/etc/systemd/system/$name" ]] ||
      fail "live unit missing/symlink: $name"
  done
}
health() {
  local port="$1" label="$2"
  # HTTP codes and JSON body checked without displaying balances or secrets.
  curl --fail --silent --show-error --max-time 12 \
    "http://127.0.0.1:$port/settlement/v1/health" |
    python3 -c 'import json,sys; j=json.load(sys.stdin); assert j.get("ok") is True and j.get("chain_id") == "wolo-1"' ||
    fail "$label health is not explicitly ok=true for wolo-1"
  echo "PASS $label health"
}
check_legacy_pids() {
  for name in "$PRIMARY" "$FOUNDER"; do
    local pid program
    systemctl is-active --quiet "$name" || fail "$name not active after rollback"
    pid="$(systemctl show -P MainPID "$name")"
    [[ "$pid" =~ ^[1-9][0-9]*$ ]] || fail "$name no running PID"
    program="$(readlink "/proc/$pid/exe")"
    [[ "$program" == "$OLD" ]] || fail "$name still not running original executable"
    [[ "$(sha "/proc/$pid/exe")" == "$OLD_SHA" ]] || fail "$name running SHA not old original"
    echo "PASS $name running original SHA"
  done
}
mode="\${1:---inspect}"
case "$mode" in
  --inspect|--rollback) ;;
  *) printf 'usage: sudo bash %s [--inspect|--rollback]\n' "$0" >&2; exit 2 ;;
esac
(( EUID == 0 )) || fail "root required for process inspection and optional rollback"
echo "=== TWO-SETTLEMENT CODE-ONLY ROLLBACK ($mode) ==="
assert_hash "$OLD" "$OLD_SHA"
assert_hash "$NODE_BIN" "$NODE_SHA"
check_consensus
check_backup
check_old_config
inspect_override "$PRIMARY"
inspect_override "$FOUNDER"
if [[ "$mode" == "--inspect" ]]; then
  echo "PASS inspect only: no files modified, no services restarted"
  exit 0
fi

# Explicitly never restore previous payout state or env files.
# Operator may use this after error, or the separately armed timeout supervisor.
echo "ROLLBACK: returning both settlement units to the intact original binary."
for name in "$PRIMARY" "$FOUNDER"; do
  timeout 40s systemctl stop "$name" || fail "could not stop $name; manual operator required"
done
for name in "$PRIMARY" "$FOUNDER"; do
  file="$(dropin "$name")"
  if [[ -f "$file" ]]; then
    rm -- "$file"
    echo "Removed only our exact reviewed override for $name"
  fi
done
timeout 30s systemctl daemon-reload || fail "systemd reload failed"
for name in "$PRIMARY" "$FOUNDER"; do
  timeout 40s systemctl start "$name" || fail "could not start $name; manual operator required"
done
check_legacy_pids
health 8092 primary
health 8093 founder
check_consensus
echo "ROLLBACK_PASS: both original settlement binaries active; live state preserved"
echo "NODE_UNTOUCHED: do not call the generic shared-binary restore script"
