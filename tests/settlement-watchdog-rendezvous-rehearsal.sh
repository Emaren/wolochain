#!/usr/bin/env bash
# Synthetic GitHub Actions ONLY isolation: no live systemd/chain/wallet access.
set -euo pipefail
umask 077
[[ "$GITHUB_ACTIONS" == "true" && "$EUID" == 0 ]] || {
  echo "Only synthetic root CI supports this test" >&2
  exit 2
}
work="$(mktemp -d /tmp/wolo-handoff-gate.XXXXXXXX)"
trap 'rm -rf -- "$work"' EXIT
mkdir -m 0700 "$work/run" "$work/helpers"
printf '%s\n' "aoe2hdbets-web.service" > "$work/run/restore-units"
chmod 0600 "$work/run/restore-units"
printf 'test node image\n' > "$work/node"
printf '#!/usr/bin/env bash\nprintf "RESCUE_CALLED\\n" >> "$SIM_ROOT/actions"\n' > "$work/helpers/rescue.sh"
chmod 0500 "$work/helpers/rescue.sh"
export SIM_ROOT="$work"

python3 - "$work" <<'PY'
from pathlib import Path
import hashlib,sys
root=Path(sys.argv[1])
s=Path("scripts/settlement-two-lane-watchdog-gate.sh").read_text()
changes={
  "RUN=/run/aoe2war-wolo-two-service-cutover":f"RUN={root}/run",
  "RESCUE=/usr/local/libexec/aoe2war-wolo/settlement-two-service-code-rollback.sh":f"RESCUE={root}/helpers/rescue.sh",
  "NODE=/usr/local/bin/wolochaind-mainnet-node-prewartrophy":f"NODE={root}/node",
  "NODE_SHA=4b77f622191db7550cb87cafb8f1886a0aadebee3eb6565f9f90036f809e61d3":"NODE_SHA="+hashlib.sha256((root/"node").read_bytes()).hexdigest(),
}
for old,new in changes.items():
  if s.count(old)!=1: raise SystemExit(f"Unexpected test substitution: {old}")
  s=s.replace(old,new)
(root/"watchdog-test.sh").write_text(s)
PY

# Already fired timer waits while controller finishes release under mutex.
exec 7>"$work/run/handoff.lock"
flock -n 7
bash "$work/watchdog-test.sh" --watchdog > "$work/commit.log" 2>&1 &
child=$!
sleep 1
[[ ! -f "$work/actions" ]] || { echo "FAIL: timer ignored controller mutex"; exit 3; }
printf 'COMMITTED-3EA79363\n' > "$work/run/COMMITTED"
chmod 0600 "$work/run/COMMITTED"
flock -u 7
wait "$child" || { cat "$work/commit.log"; exit 3; }
grep -Fq "WATCHDOG_SKIP: committed release" "$work/commit.log"
[[ ! -f "$work/actions" ]] || { echo "FAIL: committed release rolled back"; exit 3; }
echo "WATCHDOG_COMMIT_RACE_PASS"

# Aborted process with no commit marker => one independent rescue.
rm -- "$work/run/COMMITTED"
bash "$work/watchdog-test.sh" --watchdog > "$work/crash.log" 2>&1 ||
  { cat "$work/crash.log"; exit 3; }
[[ "$(cat "$work/run/COMMITTED")" == "RESCUED-3EA79363" ]]
[[ "$(grep -c '^RESCUE_CALLED$' "$work/actions")" == "1" ]]
echo "WATCHDOG_CRASH_RESCUE_PASS"

# Watchdog retry after successful rescue must not restart services again.
bash "$work/watchdog-test.sh" --watchdog > "$work/retry.log" 2>&1 ||
  { cat "$work/retry.log"; exit 3; }
grep -Fq "WATCHDOG_SKIP: original binary" "$work/retry.log"
[[ "$(grep -c '^RESCUE_CALLED$' "$work/actions")" == "1" ]]
echo "WATCHDOG_RESCUE_IDEMPOTENT_PASS"

# Unknown release outcome and unsafe manifest must never run the rescuer.
printf 'UNKNOWN\n' > "$work/run/COMMITTED"
if bash "$work/watchdog-test.sh" --watchdog > "$work/bad.log" 2>&1; then
  echo "FAIL: unknown marker trusted"; exit 3
fi
grep -Fq "unknown/partial release outcome marker" "$work/bad.log"
[[ "$(grep -c '^RESCUE_CALLED$' "$work/actions")" == "1" ]]
echo "WATCHDOG_UNKNOWN_OUTCOME_BLOCK_PASS"

rm "$work/run/COMMITTED"
chmod 0644 "$work/run/restore-units"
if bash "$work/watchdog-test.sh" --watchdog > "$work/manifest.log" 2>&1; then
  echo "FAIL: insecure manifest accepted"; exit 3
fi
grep -Fq "manifest unavailable" "$work/manifest.log"
[[ "$(grep -c '^RESCUE_CALLED$' "$work/actions")" == "1" ]]
echo "WATCHDOG_MANIFEST_FAIL_CLOSED_PASS"
