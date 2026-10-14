#!/usr/bin/env bash
# Release watchdog rendezvous. Can run under an independent transient timer.
# NO change to the consensus node, no old financial-state restore.
set -euo pipefail
umask 077

RUN=/run/aoe2war-wolo-two-service-cutover
GATE_LOCK="$RUN/handoff.lock"
COMMITTED="$RUN/COMMITTED"
MANIFEST="$RUN/restore-units"
RESCUE=/usr/local/libexec/aoe2war-wolo/settlement-two-service-code-rollback.sh
OLD_SHA=040126a2884946caf1651a50b7d8115c5a6fb2d5aa94fcbbe150694602d451a5
NODE=/usr/local/bin/wolochaind-mainnet-node-prewartrophy
NODE_SHA=4b77f622191db7550cb87cafb8f1886a0aadebee3eb6565f9f90036f809e61d3

fail() { printf 'WATCHDOG_BLOCKED: %s\n' "$*" >&2; exit 2; }
[[ "${1:---inspect}" == "--inspect" || "${1:---inspect}" == "--watchdog" ]] ||
  fail "unknown watchdog mode"
(( EUID == 0 )) || fail "root required"
[[ -d "$RUN" && ! -L "$RUN" && "$(stat -c '%u:%g:%a' "$RUN")" == "0:0:700" ]] ||
  fail "private operator run directory missing/unsafe"
[[ ! -L "$GATE_LOCK" && ! -L "$COMMITTED" && ! -L "$MANIFEST" ]] ||
  fail "operator state contains a symlink"
[[ -f "$MANIFEST" && "$(stat -c '%u:%g:%a' "$MANIFEST")" == "0:0:600" ]] ||
  fail "complete owner-only service restore manifest unavailable"
[[ -f "$RESCUE" && ! -L "$RESCUE" &&
   "$(stat -c '%u:%g:%a' "$RESCUE")" == "0:0:500" ]] ||
  fail "root-only reviewed rescue unavailable"
[[ -f "$NODE" && ! -L "$NODE" &&
   "$(sha256sum "$NODE" | awk '{print $1}')" == "$NODE_SHA" ]] ||
  fail "dedicated consensus image changed"

# The exact same lock is owned by the controller BEFORE the first service stop
# through producer resumption, commit-marker fsync/rename and timer disarm.
# A timed rescue cannot revert the new binary after a committed handoff.
if [[ "${1:---inspect}" == "--inspect" ]]; then
  printf 'WATCHDOG_INSPECT_PASS: private manifest present; no actions performed\n'
  exit 0
fi

exec 8>"$GATE_LOCK"
flock -w 150 8 || fail "operator controller failed to release bounded handoff lock"
if [[ -f "$COMMITTED" && ! -L "$COMMITTED" ]] &&
   [[ "$(cat "$COMMITTED")" == "COMMITTED-3EA79363" ]]; then
  echo "WATCHDOG_SKIP: committed release and producer recovery already complete"
  exit 0
fi
[[ ! -e "$COMMITTED" ]] || fail "unknown/partial commit marker"
echo "WATCHDOG_RECOVER: no committed release; verify and rescue BOTH settlement lanes"
bash "$RESCUE" --rescue
echo "WATCHDOG_RECOVERY_PASS: legacy binaries/health and producer resume verified"
