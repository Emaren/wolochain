#!/usr/bin/env bash
# EPHEMERAL GITHUB-RUNNER-ONLY systemd integration rehearsal.
# Runs patched exact watchdog gate against fake root-only files and fake
# rescuer, never against real WoloChain units or private production state.
set -euo pipefail
umask 077
[[ "${GITHUB_ACTIONS:-}" == "true" && "$EUID" -eq 0 ]] || {
  echo "BLOCKED: this test is ONLY for root inside ephemeral GitHub Actions" >&2
  exit 2
}
systemctl list-units --type=service --no-pager >/dev/null ||
  { echo "BLOCKED: systemd service manager unavailable"; exit 2; }
work="$(mktemp -d /tmp/aoe2war-watchdog-systemd.XXXXXXXX)"
prefix="aoe2war-sandbox-wolo-$$"
units=()
cleanup() {
  local unit
  for unit in "${units[@]}"; do
    systemctl stop "$unit.timer" >/dev/null 2>&1 || true
    systemctl stop "$unit.service" >/dev/null 2>&1 || true
    systemctl reset-failed "$unit.service" >/dev/null 2>&1 || true
  done
  rm -rf -- "$work"
}
trap cleanup EXIT
mkdir -m 0700 "$work/run" "$work/bin"
printf '%s\n' aoe2hdbets-web.service > "$work/run/restore-units"
chmod 0600 "$work/run/restore-units"
printf 'synthetic node, never a WoloChain binary\n' > "$work/node"
printf '#!/usr/bin/env bash\nset -euo pipefail\nprintf "RESCUE_CALLED\\n" >> "%s/actions"\n' "$work" > "$work/bin/settlement-two-service-code-rollback.sh"
chmod 0500 "$work/bin/settlement-two-service-code-rollback.sh"

python3 - "$work" <<'PY'
from pathlib import Path
import hashlib,sys
root=Path(sys.argv[1])
source=Path("scripts/settlement-two-lane-watchdog-gate.sh").read_text()
changes={
  "RUN=/run/aoe2war-wolo-two-service-cutover":f"RUN={root}/run",
  "RESCUE=/usr/local/libexec/aoe2war-wolo/settlement-two-service-code-rollback.sh":f"RESCUE={root}/bin/settlement-two-service-code-rollback.sh",
  "NODE=/usr/local/bin/wolochaind-mainnet-node-prewartrophy":f"NODE={root}/node",
  "NODE_SHA=4b77f622191db7550cb87cafb8f1886a0aadebee3eb6565f9f90036f809e61d3":
    "NODE_SHA="+hashlib.sha256((root/"node").read_bytes()).hexdigest(),
  # TEST ONLY: reduce real 150-second lock wait for bounded CI rehearsal.
  "flock -w 150 8":"flock -w 2 8",
}
for old,new in changes.items():
  if source.count(old)!=1: raise SystemExit("BLOCKED unexpected gate substitution: "+old)
  source=source.replace(old,new)
(root/"watchdog.sh").write_text(source)
PY
chmod 0500 "$work/watchdog.sh"
# GitHub runner journal storage is not a reliable observer of transient unit
# stdout. Wrap only the synthetic watchdog in a sandbox-local transcript.
printf '#!/usr/bin/env bash\nexec /usr/bin/bash "%s/watchdog.sh" --watchdog >> "%s/timer.log" 2>&1\n' "$work" "$work" > "$work/launch.sh"
chmod 0500 "$work/launch.sh"

wait_for() {
  local file="$1" pattern="$2" max="${3:-25}" i
  for ((i=0;i<max;i++)); do
    if [[ -f "$file" ]] && grep -Fq -- "$pattern" "$file"; then return 0; fi
    sleep 1
  done
  return 1
}
start_timer() {
  local name="$1"
  units+=("$name")
  systemd-run --quiet --unit="$name" --on-active=2s --on-unit-inactive=3s \
    /usr/bin/bash "$work/launch.sh"
  systemctl is-active --quiet "$name.timer" || {
    echo "BLOCKED: disposable systemd timer not armed"; exit 3;
  }
}
# Lock held during first firing; it MUST time out and later retry.
exec 7>"$work/run/handoff.lock"
flock -n 7
start_timer "$prefix-retry"
sleep 6
[[ ! -e "$work/run/COMMITTED" && ! -e "$work/actions" ]] || {
  echo "FAIL watchdog bypassed handoff lock"; exit 3;
}
flock -u 7
wait_for "$work/run/COMMITTED" RESCUED-3EA79363 24 || {
  journalctl -u "$prefix-retry.service" --no-pager -n 40 >&2 || true
  echo "FAIL retry did not perform independent rescue"; exit 3;
}
[[ "$(grep -c '^RESCUE_CALLED$' "$work/actions")" == 1 ]] ||
  { echo "FAIL expected one rescue"; exit 3; }
systemctl stop "$prefix-retry.timer" >/dev/null
echo "SYSTEMD_WATCHDOG_TIMED_RETRY_PASS"

# Already committed controller may NEVER be rolled back by a late timer.
printf '%s\n' COMMITTED-3EA79363 > "$work/run/COMMITTED"
chmod 0600 "$work/run/COMMITTED"
start_timer "$prefix-commit"
sleep 5
[[ "$(grep -c '^RESCUE_CALLED$' "$work/actions")" == 1 ]] ||
  { echo "FAIL late watchdog reverted committed release"; exit 3; }
wait_for "$work/timer.log" "WATCHDOG_SKIP: committed release" 10 || {
  echo "FAIL committed release timer did not execute, transcript follows" >&2
  cat "$work/timer.log" >&2 || true
  exit 3
}
systemctl stop "$prefix-commit.timer" >/dev/null
echo "SYSTEMD_WATCHDOG_COMMITTED_HANDOFF_PASS"

# Already rescued state remains idempotent on later timer firing.
printf '%s\n' RESCUED-3EA79363 > "$work/run/COMMITTED"
start_timer "$prefix-rescued"
sleep 5
[[ "$(grep -c '^RESCUE_CALLED$' "$work/actions")" == 1 ]] ||
  { echo "FAIL rescued state replayed"; exit 3; }
echo "SYSTEMD_WATCHDOG_ALREADY_RESCUED_PASS"
echo "ONLY_EPHEMERAL_SYSTEMD_USED: no chain, live wallet or production service touched"
