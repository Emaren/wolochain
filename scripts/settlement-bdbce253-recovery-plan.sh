#!/usr/bin/env bash
# Current bdbce253 two-service rollback-state planner. READ ONLY.
# Evaluates exact original/target systemd ownership without installing overrides.
# Does not stop/restart/reload ANY service or alter the chain, files, or request state.
# A safe mutating rollback/watchdog requires a separate reviewed, rehearsed controller
# plus independent financial ingress fence, drain, reconciliation and authorization.
set -euo pipefail

OLD=/usr/local/bin/wolochaind-mainnet
NODE_BIN=/usr/local/bin/wolochaind-mainnet-node-prewartrophy
CANDIDATE=/mnt/HC_Volume_105319120/wolochain-mainnet/settlement-candidates/bdbce253-UNDEPLOYED/wolochaind-settlement-only-linux-amd64
OLD_SHA=040126a2884946caf1651a50b7d8115c5a6fb2d5aa94fcbbe150694602d451a5
NODE_SHA=4b77f622191db7550cb87cafb8f1886a0aadebee3eb6565f9f90036f809e61d3
NEW_SHA=44d8aed5550d1b33635c734c1a359d0cb69e854093ef8c9a8a3da4f99d416ede
NODE_UNIT=wolochaind-mainnet.service
PRIMARY_UNIT=wolochain-mainnet-settlement.service
FOUNDER_UNIT=wolochain-founder-rewards-settlement.service
DROPIN_FILENAME=50-aoe2war-bdbce253-settlement-only.conf

fail() { printf 'BLOCKED: %s\n' "$*" >&2; exit 2; }
sha() { sha256sum "$1" | awk '{print $1}'; }
assert_binary() {
  local label="$1" p="$2" expected="$3"
  [[ -f "$p" && -r "$p" && ! -L "$p" ]] || fail "$label not regular, unreadable, or symlinked"
  [[ "$(sha "$p")" == "$expected" ]] || fail "$label executable differs from pinned SHA"
}
unit_pid() {
  local n="$1" p
  systemctl is-active --quiet "$n" || fail "$n is inactive"
  p="$(systemctl show -P MainPID "$n")"
  [[ "$p" =~ ^[1-9][0-9]*$ ]] || fail "$n has no stable main PID"
  printf '%s' "$p"
}
assert_running() {
  local label="$1" unit="$2" expected_path="$3" expected_sha="$4" p path
  p="$(unit_pid "$unit")"
  path="$(readlink "/proc/$p/exe")" || fail "$label executable cannot be read"
  [[ "$path" == "$expected_path" ]] || fail "$label unexpected running executable"
  [[ "$(sha "/proc/$p/exe")" == "$expected_sha" ]] || fail "$label running bytes SHA mismatch"
  echo "PASS $label pid=$p pinned_binary_sha=$expected_sha"
}
override_path() {
  printf '/etc/systemd/system/%s.d/%s' "$1" "$DROPIN_FILENAME"
}
expected_override() {
  printf '%s\n' \
    '# AOE2WAR bdbce253 two-settlement code-only; leave request/run state untouched' \
    '[Service]' \
    'ExecStart=' \
    "ExecStart=$CANDIDATE settlement serve"
}
unit_mode() {
  local unit="$1" f paths
  f="$(override_path "$unit")"
  [[ "$(systemctl show -P FragmentPath "$unit")" == "/etc/systemd/system/$unit" ]] ||
    fail "$unit original fragment not exact"
  [[ -f "/etc/systemd/system/$unit" && ! -L "/etc/systemd/system/$unit" ]] ||
    fail "$unit original fragment absent/symlinked"
  paths="$(systemctl show -P DropInPaths "$unit")"
  if [[ -e "$f" || -L "$f" ]]; then
    [[ -f "$f" && ! -L "$f" ]] || fail "$unit owned override unsafe"
    cmp -s "$f" <(expected_override) || fail "$unit owned override differs from exact reviewed content"
    [[ "$paths" == "$f" ]] || fail "$unit has unexpected additional overrides"
    echo NEW
  else
    [[ -z "$paths" ]] || fail "$unit unexpected foreign override"
    echo OLD
  fi
}

mode="${1:---inspect}"
[[ "$mode" == "--inspect" && "$#" -le 1 ]] ||
  fail "only --inspect is supported; --rollback, --apply and --rescue are NOT implemented"
(( EUID == 0 )) || fail "root required for exact protected process checks"
for bin in sha256sum systemctl readlink cmp; do
  command -v "$bin" >/dev/null || fail "missing $bin"
done

echo "=== WOLO bdbce253 TWO-SERVICE RECOVERY READ-ONLY PLAN ==="
date -u '+observed_at=%Y-%m-%dT%H:%M:%SZ'
assert_binary "original settlement" "$OLD" "$OLD_SHA"
assert_binary "candidate" "$CANDIDATE" "$NEW_SHA"
assert_binary "preserved consensus" "$NODE_BIN" "$NODE_SHA"
node_pid_before="$(unit_pid "$NODE_UNIT")"
assert_running "preserved consensus" "$NODE_UNIT" "$NODE_BIN" "$NODE_SHA"

primary_mode="$(unit_mode "$PRIMARY_UNIT")"
founder_mode="$(unit_mode "$FOUNDER_UNIT")"
[[ "$primary_mode" == "$founder_mode" ]] ||
  fail "mixed settlement code versions/overrides: manual recovery required"

if [[ "$primary_mode" == OLD ]]; then
  assert_running "primary original settlement" "$PRIMARY_UNIT" "$OLD" "$OLD_SHA"
  assert_running "founder original settlement" "$FOUNDER_UNIT" "$OLD" "$OLD_SHA"
  echo "STATE=BEFORE_CUTOVER"
else
  assert_running "primary reviewed settlement" "$PRIMARY_UNIT" "$CANDIDATE" "$NEW_SHA"
  assert_running "founder reviewed settlement" "$FOUNDER_UNIT" "$CANDIDATE" "$NEW_SHA"
  echo "STATE=AFTER_CUTOVER"
fi
[[ "$(unit_pid "$NODE_UNIT")" == "$node_pid_before" ]] ||
  fail "consensus PID changed during inspection"
assert_running "preserved consensus post-check" "$NODE_UNIT" "$NODE_BIN" "$NODE_SHA"

echo "PREFLIGHT_ONLY_NO_SYSTEMD_MUTATION=true"
echo "NO_REQUEST_OR_RUN_STATE_RESTORED=true"
echo "FINANCIAL_PRODUCERS_FENCED=false"
echo "INDEPENDENT_FINANCIAL_DRAIN_CERTIFIED=false"
echo "REHEARSED_ROLLBACK_WATCHDOG_CERTIFIED=false"
echo "ROLLBACK_OR_CUTOVER_AUTHORIZED=false"
echo "An approved rollback controller must own only these exact two overrides,"
echo "keep all payout producers fenced, retain live state and consensus PID,"
echo "and make financial resume a separate operator-controlled action."
