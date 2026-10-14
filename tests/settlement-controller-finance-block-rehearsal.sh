#!/usr/bin/env bash
# GITHUB ACTIONS ONLY: fake binaries and fake service commands in /tmp.
# Prove that unresolved finance does not interrupt app or mainnet.
set -euo pipefail
umask 077

[[ "$GITHUB_ACTIONS" == "true" && "$EUID" == "0" ]] || { echo "isolated root CI required"; exit 2; }
work="$(mktemp -d /tmp/wolo-cutover-test.XXXXXXXX)"
trap 'rm -rf -- "$work"' EXIT
export SIM_ROOT="$work"
mkdir -p "$work/bin" "$work/app" "$work/repo" "$work/helpers" \
 "$work/volume/wolochain-mainnet/settlement-candidates/3ea79363" \
 "$work/volume/wolochain-mainnet/settlement-backups/20261014T091735Z-two-settlement-node-untouched/proof" \
 "$work/volume/wolochain-mainnet/settlement-backups/20261014T091735Z-two-settlement-node-untouched/state/primary" \
 "$work/volume/wolochain-mainnet/settlement-backups/20261014T091735Z-two-settlement-node-untouched/state/founder"
backup="$work/volume/wolochain-mainnet/settlement-backups/20261014T091735Z-two-settlement-node-untouched"
chmod 0700 "$backup"
touch "$backup/proof/RECEIPT.txt" "$backup/proof/config-files.sha256" \
 "$backup/proof/primary-files.sha256" "$backup/proof/founder-files.sha256"
touch "$work/original" "$work/node" "$work/app.env" \
 "$work/volume/wolochain-mainnet/settlement-candidates/3ea79363/wolochaind-settlement-only-linux-amd64"
printf '#!/bin/bash\nif [[ "$1" == "--rescue" ]]; then echo RESCUE_INVOKED >> "$SIM_ROOT/actions.log"; fi\nexit 0\n' > "$work/helpers/settlement-two-service-code-rollback.sh"
printf '// test finance audit\n' > "$work/helpers/wolo-maintenance-drain-readonly.mjs"
chmod 0500 "$work/helpers/settlement-two-service-code-rollback.sh"
chmod 0444 "$work/helpers/wolo-maintenance-drain-readonly.mjs"
chmod 0600 "$work/app.env"

python3 - "$work" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1])
body = Path("scripts/settlement-two-lane-watchdog-controller.sh").read_text()
updates = {
 "VOLUME=/mnt/HC_Volume_105319120": f"VOLUME={root}/volume",
 "OLD=/usr/local/bin/wolochaind-mainnet": f"OLD={root}/original",
 "NODE_BIN=/usr/local/bin/wolochaind-mainnet-node-prewartrophy": f"NODE_BIN={root}/node",
 "REPO=/var/www/WoloChain-wolo-1": f"REPO={root}/repo",
 "APP=/var/www/AoE2HDBets/app-prodn": f"APP={root}/app",
 "ENV_FILE=/etc/aoe2hdbets/aoe2hdbets-web.env": f"ENV_FILE={root}/app.env",
 "AUDIT=/usr/local/libexec/aoe2war-wolo/wolo-maintenance-drain-readonly.mjs": f"AUDIT={root}/helpers/wolo-maintenance-drain-readonly.mjs",
 "RECOVERY=/usr/local/libexec/aoe2war-wolo/settlement-two-service-code-rollback.sh": f"RECOVERY={root}/helpers/settlement-two-service-code-rollback.sh",
 "RUN=/run/aoe2war-wolo-two-service-cutover": f"RUN={root}/run",
 "exec 9>/run/lock/aoe2war-wolo-two-settlement-promotion.lock": f"exec 9>{root}/lock",
}
for old, new in updates.items():
 if body.count(old) != 1: raise SystemExit(f"unexpected controller field: {old}")
 body = body.replace(old, new)
(root / "controller.sh").write_text(body)
PY

cat > "$work/bin/git" <<'SH'
#!/bin/bash
case "$*" in
 *"rev-parse HEAD"*) echo 78c25985420ee41a6678c42fab8ea8d6c3b1b519 ;;
 *"status --porcelain"*) : ;;
 *) exit 3 ;;
esac
SH
cat > "$work/bin/systemctl" <<'SH'
#!/bin/bash
if [[ "$1" == "is-active" ]]; then exit 0; fi
if [[ "$1" == "show" && "$2" == "-P" ]]; then
 case "$3" in
 MainPID)
   case "$4" in
   wolochain-mainnet-settlement.service) echo 1001 ;;
   wolochain-founder-rewards-settlement.service) echo 1002 ;;
   wolochaind-mainnet.service) echo 1003 ;;
   *) exit 3 ;; esac ;;
 DropInPaths) : ;;
 FragmentPath) echo "/etc/systemd/system/$4" ;;
 *) exit 3 ;; esac
 exit 0
fi
echo "UNSAFE_SERVICE_ACTION $*" >> "$SIM_ROOT/actions.log"
exit 3
SH
cat > "$work/bin/readlink" <<'SH'
#!/bin/bash
case "$1" in
 /proc/1001/exe|/proc/1002/exe) echo "$SIM_ROOT/original" ;;
 /proc/1003/exe) echo "$SIM_ROOT/node" ;;
 *) exit 3 ;;
esac
SH
cat > "$work/bin/sha256sum" <<'SH'
#!/bin/bash
if [[ "$1" == "-c" ]]; then exit 0; fi
case "$1" in
 "$SIM_ROOT/original"|/proc/1001/exe|/proc/1002/exe)
  echo "040126a2884946caf1651a50b7d8115c5a6fb2d5aa94fcbbe150694602d451a5  $1" ;;
 "$SIM_ROOT/node"|/proc/1003/exe)
  echo "4b77f622191db7550cb87cafb8f1886a0aadebee3eb6565f9f90036f809e61d3  $1" ;;
 "$SIM_ROOT/volume/wolochain-mainnet/settlement-candidates/3ea79363/wolochaind-settlement-only-linux-amd64")
  echo "af18e18bd32ef5763d3e414a37dd7886fe4065b640bb5a89ae742ee860fb9b87  $1" ;;
 *) /usr/bin/sha256sum "$@" ;;
esac
SH
cat > "$work/bin/curl" <<'SH'
#!/bin/bash
echo '{"ok":true,"chain_id":"wolo-1"}'
SH
cat > "$work/bin/mountpoint" <<'SH'
#!/bin/bash
exit 0
SH
cat > "$work/bin/systemd-run" <<'SH'
#!/bin/bash
if [[ "$*" == *"--wait"* ]]; then
 if [[ "$SIM_FINANCE_CODE" == 0 ]]; then
  echo FINANCE_AUDIT_CLEAR >> "$SIM_ROOT/actions.log"
  exit 0
 fi
 echo FINANCE_AUDIT_BLOCKED >> "$SIM_ROOT/actions.log"
 exit 3
fi
echo ARMED_RESCUE_TIMER >> "$SIM_ROOT/actions.log"
exit 0
SH
chmod 0755 "$work/bin/"*

rescue_sha="$(/usr/bin/sha256sum "$work/helpers/settlement-two-service-code-rollback.sh" | cut -d' ' -f1)"
audit_sha="$(/usr/bin/sha256sum "$work/helpers/wolo-maintenance-drain-readonly.mjs" | cut -d' ' -f1)"
rc=0
PATH="$work/bin:$PATH" \
 EXPECTED_RESCUE_SHA256="$rescue_sha" EXPECTED_AUDIT_SHA256="$audit_sha" \
 PROMOTION_ACK="REVIEWED-DUAL-SERVICE-3EA79363" \
 bash "$work/controller.sh" --promote > "$work/output.log" 2>&1 || rc=$?

if [[ "$rc" == 0 ]] || ! grep -Fq "unresolved financial evidence" "$work/output.log"; then
 echo "FAIL: expected financial cutoff was not reached" >&2
 cat "$work/output.log" >&2
 exit 3
fi
grep -Fxq FINANCE_AUDIT_BLOCKED "$work/actions.log"
if grep -Eq "UNSAFE_SERVICE_ACTION|ARMED_RESCUE_TIMER" "$work/actions.log"; then
 echo "FAIL: production-like mutation before financial proof!" >&2
 cat "$work/actions.log" >&2
 exit 3
fi
echo "CUTOVER_FINANCE_BLOCK_PASS: no service action or rescue timer before zero-drain proof"


# SECOND scenario: a clear initial audit arms the timer but the first
# fake timer/service stop fails. The rescue trap must run immediately.
: > "$work/actions.log"
rc=0
SIM_FINANCE_CODE=0 PATH="$work/bin:$PATH" \
 EXPECTED_RESCUE_SHA256="$rescue_sha" EXPECTED_AUDIT_SHA256="$audit_sha" \
 PROMOTION_ACK="REVIEWED-DUAL-SERVICE-3EA79363" \
 bash "$work/controller.sh" --promote > "$work/output-rescue.log" 2>&1 || rc=$?
if [[ "$rc" == 0 ]]; then
 echo "FAIL: simulated service-stop failure unexpectedly passed" >&2
 exit 3
fi
for event in FINANCE_AUDIT_CLEAR ARMED_RESCUE_TIMER RESCUE_INVOKED; do
 grep -Fxq "$event" "$work/actions.log" || {
  echo "FAIL: missing watchdog/rollback event $event" >&2
  cat "$work/output-rescue.log" "$work/actions.log" >&2
  exit 3
 }
done
awk '
 $0=="FINANCE_AUDIT_CLEAR" {a=NR}
 $0=="ARMED_RESCUE_TIMER" {b=NR}
 /^UNSAFE_SERVICE_ACTION / && c==0 {c=NR}
 $0=="RESCUE_INVOKED" {d=NR}
 END {if (!(a>0 && b>a && c>b && d>c)) exit 3}
' "$work/actions.log" || {
 echo "FAIL: financial proof, watchdog, failure and rescue ordering incorrect" >&2
 cat "$work/actions.log" >&2
 exit 3
}
echo "CUTOVER_STOP_FAILURE_PASS: watchdog precedes stop, immediate rescue invoked"
