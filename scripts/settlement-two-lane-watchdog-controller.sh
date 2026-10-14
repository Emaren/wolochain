#!/usr/bin/env bash
# Reviewed production release skeleton: NO DEFAULT MUTATIONS.
# Promote ONLY two Wolo settlement services, NEVER the consensus node.
# All monetary state persists across version switch and rollback.
set -euo pipefail
umask 077

PRIMARY=wolochain-mainnet-settlement.service
FOUNDER=wolochain-founder-rewards-settlement.service
NODE=wolochaind-mainnet.service
VOLUME=/mnt/HC_Volume_105319120
CANDIDATE="$VOLUME/wolochain-mainnet/settlement-candidates/3ea79363/wolochaind-settlement-only-linux-amd64"
OLD=/usr/local/bin/wolochaind-mainnet
NODE_BIN=/usr/local/bin/wolochaind-mainnet-node-prewartrophy
OLD_SHA=040126a2884946caf1651a50b7d8115c5a6fb2d5aa94fcbbe150694602d451a5
NEW_SHA=af18e18bd32ef5763d3e414a37dd7886fe4065b640bb5a89ae742ee860fb9b87
NODE_SHA=4b77f622191db7550cb87cafb8f1886a0aadebee3eb6565f9f90036f809e61d3
LEGACY_HEAD=78c25985420ee41a6678c42fab8ea8d6c3b1b519
REPO=/var/www/WoloChain-wolo-1
BACKUP="$VOLUME/wolochain-mainnet/settlement-backups/20261014T091735Z-two-settlement-node-untouched"
APP=/var/www/AoE2HDBets/app-prodn
ENV_FILE=/etc/aoe2hdbets/aoe2hdbets-web.env
AUDIT=/usr/local/libexec/aoe2war-wolo/wolo-maintenance-drain-readonly.mjs
RECOVERY=/usr/local/libexec/aoe2war-wolo/settlement-two-service-code-rollback.sh
RUN=/run/aoe2war-wolo-two-service-cutover
WATCHDOG=aoe2war-wolo-two-settlement-rescue-3ea79363
OVERLAY=50-aoe2war-settlement-3ea79363.conf
PRODUCERS="aoe2hdbets-challenge-reconcile.timer aoe2hdbets-bet-stake-reconcile.timer aoe2hdbets-replay-auto-recovery.timer aoe2hdbets-trophy-tributes.timer aoe2hdbets-staking-rewards.timer aoe2-wolo-transfer-heartbeat.timer aoe2hdbets-web.service aoe2hdbets-api.service"
armed=0
done_promotion=0

fail() { echo "BLOCKED: $*" >&2; exit 2; }
sha() { sha256sum "$1" | awk '{print $1}'; }
checked_hash() {
  [[ -f "$1" && ! -L "$1" ]] || fail "file absent or symlink: $1"
  [[ "$(sha "$1")" == "$2" ]] || fail "binary/hash drift: $1"
}
pid_hash() {
  local unit="$1" program="$2" wanted="$3" pid
  systemctl is-active --quiet "$unit" || fail "inactive: $unit"
  pid="$(systemctl show -P MainPID "$unit")"
  [[ "$pid" =~ ^[1-9][0-9]*$ ]] || fail "no PID: $unit"
  [[ "$(readlink "/proc/$pid/exe")" == "$program" ]] || fail "wrong running executable: $unit"
  [[ "$(sha "/proc/$pid/exe")" == "$wanted" ]] || fail "wrong running digest: $unit"
}
health() {
  curl -fsS --max-time 12 "http://127.0.0.1:$1/settlement/v1/health" |
    python3 -c 'import sys,json; j=json.load(sys.stdin); assert j.get("ok") is True and j.get("chain_id") == "wolo-1"' ||
    fail "settlement health failed on port $1"
}
dropin() { printf '/etc/systemd/system/%s.d/%s' "$1" "$OVERLAY"; }
expected() {
  printf '%s\n' \
    '# aoe2war two-settlement code-only 3ea79363' \
    '[Service]' \
    'ExecStart=' \
    "ExecStart=$CANDIDATE settlement serve"
}
preflight() {
  mountpoint -q "$VOLUME" || fail "mounted state volume missing"
  [[ "$(git -C "$REPO" rev-parse HEAD)" == "$LEGACY_HEAD" ]] || fail "checkout baseline unexpectedly changed"
  [[ -z "$(git -C "$REPO" status --porcelain)" ]] || fail "dirty Wolo checkout"
  checked_hash "$OLD" "$OLD_SHA"
  checked_hash "$CANDIDATE" "$NEW_SHA"
  checked_hash "$NODE_BIN" "$NODE_SHA"
  pid_hash "$PRIMARY" "$OLD" "$OLD_SHA"
  pid_hash "$FOUNDER" "$OLD" "$OLD_SHA"
  pid_hash "$NODE" "$NODE_BIN" "$NODE_SHA"
  for unit in "$PRIMARY" "$FOUNDER"; do
    [[ -z "$(systemctl show -P DropInPaths "$unit")" ]] || fail "unknown override on $unit"
    [[ "$(systemctl show -P FragmentPath "$unit")" == "/etc/systemd/system/$unit" ]] ||
      fail "unexpected systemd fragment: $unit"
  done
  [[ -d "$BACKUP" && ! -L "$BACKUP" ]] || fail "approved snapshot missing"
  [[ "$(stat -c '%u:%g:%a' "$BACKUP")" == 0:0:700 ]] || fail "backup permissions drift"
  [[ ! -e "$BACKUP/INCOMPLETE" && -f "$BACKUP/proof/RECEIPT.txt" ]] || fail "backup is incomplete"
  (cd "$BACKUP" && sha256sum -c proof/config-files.sha256 >/dev/null) || fail "backup config integrity"
  (cd "$BACKUP/state/primary" && sha256sum -c ../../proof/primary-files.sha256 >/dev/null) ||
    fail "backup primary file integrity"
  (cd "$BACKUP/state/founder" && sha256sum -c ../../proof/founder-files.sha256 >/dev/null) ||
    fail "backup founder file integrity"
  health 8092
  health 8093
  echo "PRECHECK_PASS: old settlement services + node + candidate + backup"
}
approved_tools() {
  [[ -f "$RECOVERY" && ! -L "$RECOVERY" ]] || fail "root-installed rescue unavailable"
  [[ "$(stat -c '%u:%g:%a' "$RECOVERY")" == 0:0:500 ]] || fail "rescue must be root-only mode 0500"
  [[ -n "$EXPECTED_RESCUE_SHA256" ]] || fail "independent pinned rescue fingerprint absent"
  [[ "$(sha "$RECOVERY")" == "$EXPECTED_RESCUE_SHA256" ]] || fail "rescue digest mismatch"
  bash "$RECOVERY" --inspect
  [[ -f "$AUDIT" && ! -L "$AUDIT" ]] || fail "protected database auditor unavailable"
  [[ -n "$EXPECTED_AUDIT_SHA256" ]] || fail "pinned finance source fingerprint absent"
  [[ "$(sha "$AUDIT")" == "$EXPECTED_AUDIT_SHA256" ]] || fail "finance source mismatch"
  [[ "$(stat -c '%u:%g:%a' "$AUDIT")" == 0:0:444 ]] || fail "auditor not root-owned read-only 0444"
  [[ "$(stat -c '%u:%g:%a' "$ENV_FILE")" == 0:0:600 ]] || fail "private prod env permissions changed"
}
on_exit() {
  local result="$1"
  if (( armed == 1 && done_promotion == 0 )); then
    echo "RELEASE INTERRUPTED rc=$result: invoking immediate code-only rescue ..." >&2
    bash "$RECOVERY" --rescue ||
      echo "CRITICAL: immediate rescue failed; independent rescue TIMER REMAINS ARMED" >&2
  fi
}
arm_rescue() {
  systemd-run --quiet --unit="$WATCHDOG" --on-active=900s \
    /usr/bin/bash "$RECOVERY" --rescue || fail "could not arm independent timer"
  systemctl is-active --quiet "$WATCHDOG.timer" || fail "independent rescue timer not active"
  armed=1
  echo "PASS independently scheduled rescue (survives SSH disconnect)"
}
stop_ingress() {
  install -d -o root -g root -m 0700 "$RUN"
  : > "$RUN/restore-units"
  chmod 0600 "$RUN/restore-units"
  local unit
  for unit in $PRODUCERS; do
    systemctl is-active --quiet "$unit" && printf '%s\n' "$unit" >> "$RUN/restore-units"
  done
  for unit in $PRODUCERS; do
    case "$unit" in *.timer) timeout 35s systemctl stop "$unit" || fail "cannot freeze $unit" ;; esac
  done
  for unit in aoe2hdbets-web.service aoe2hdbets-api.service; do
    timeout 60s systemctl stop "$unit" || fail "cannot freeze $unit"
  done
  for unit in $PRODUCERS; do
    if systemctl is-active --quiet "$unit"; then fail "ingress still active: $unit"; fi
  done
  for unit in aoe2hdbets-challenge-reconcile.service aoe2hdbets-bet-stake-reconcile.service aoe2hdbets-replay-auto-recovery.service aoe2hdbets-trophy-tributes.service aoe2hdbets-staking-rewards.service aoe2-wolo-transfer-heartbeat.service; do
    if systemctl is-active --quiet "$unit"; then fail "financial job in progress: $unit"; fi
  done
}
run_finance_scan() {
  local code=0
  timeout 70s systemd-run --quiet --wait --pipe --collect \
    --unit="aoe2war-wolo-drain-$RANDOM-$" \
    --property=User=tony \
    --property=WorkingDirectory="$APP" \
    --property=EnvironmentFile="$ENV_FILE" \
    --property=NoNewPrivileges=yes \
    --property=ProtectSystem=strict \
    --property=RuntimeMaxSec=50s \
    --setenv="AOE2WAR_PACKAGE_JSON=$APP/package.json" \
    /usr/bin/node "$AUDIT" || code=$?
  [[ "$code" == 0 ]] || fail "unresolved financial evidence (code=$code); leave funds untouched"
}
verify_drain() {
  run_finance_scan
  for dir in "$VOLUME/wolochain-mainnet/settlement-state" "$VOLUME/wolochain-mainnet/founder-rewards-settlement-state"; do
    [[ -z "$(find "$dir" -type f -name '*.lock' -print -quit)" ]] || fail "settlement lock still exists"
  done
  [[ "$(ss -Htn state established | awk '$4 ~ /:(8092|8093)$/ {n++} END {print n+0}')" == 0 ]] ||
    fail "settlement connection still established"
}
make_overrides() {
  local unit directory destination
  for unit in "$PRIMARY" "$FOUNDER"; do
    directory="/etc/systemd/system/$unit.d"
    destination="$(dropin "$unit")"
    install -d -o root -g root -m 0755 "$directory"
    [[ ! -e "$destination" && ! -L "$destination" ]] || fail "existing override: $unit"
    expected > "$destination"
    chmod 0644 "$destination"
    cmp -s "$destination" <(expected) || fail "override bytes mismatch"
  done
}
restore_producers() {
  local unit
  for unit in aoe2hdbets-api.service aoe2hdbets-web.service; do
    if grep -Fxq "$unit" "$RUN/restore-units"; then
      timeout 60s systemctl start "$unit" || fail "cannot resume app $unit"
      systemctl is-active --quiet "$unit" || fail "app did not resume $unit"
    fi
  done
  while IFS= read -r unit; do
    case "$unit" in
      *.timer)
        timeout 35s systemctl start "$unit" || fail "cannot resume timer $unit"
        systemctl is-active --quiet "$unit" || fail "timer not active $unit"
        ;;
    esac
  done < "$RUN/restore-units"
}
promote() {
  # Prevent two concurrent operator windows from racing watchdogs/overrides.
  exec 9>/run/lock/aoe2war-wolo-two-settlement-promotion.lock
  flock -n 9 || fail "another settlement promotion is in progress"
  [[ "$PROMOTION_ACK" == "REVIEWED-DUAL-SERVICE-3EA79363" ]] ||
    fail "explicit operator approval absent"
  approved_tools
  # Catch known historical ambiguity (e.g. founder claim #889) BEFORE any
  # maintenance outage; recheck after freezing new ingress for race safety.
  run_finance_scan
  arm_rescue
  trap 'on_exit "$?"' EXIT
  stop_ingress
  verify_drain
  timeout 40s systemctl stop "$PRIMARY" || fail "cannot stop primary"
  timeout 40s systemctl stop "$FOUNDER" || fail "cannot stop founder"
  make_overrides
  timeout 30s systemctl daemon-reload || fail "systemd reload failed"
  timeout 45s systemctl start "$PRIMARY" || fail "primary did not start"
  timeout 45s systemctl start "$FOUNDER" || fail "founder did not start"
  pid_hash "$PRIMARY" "$CANDIDATE" "$NEW_SHA"
  pid_hash "$FOUNDER" "$CANDIDATE" "$NEW_SHA"
  health 8092
  health 8093
  pid_hash "$NODE" "$NODE_BIN" "$NODE_SHA"
  restore_producers
  systemctl stop "$WATCHDOG.timer" || fail "unable to disarm rescue timer"
  armed=0
  done_promotion=1
  echo "PROMOTION_PASS: two settlement services verified, original consensus untouched"
  echo "SOURCE_CHECKOUT_UNCHANGED: release source drift must be separately reconciled"
}

(( EUID == 0 )) || fail "must run as root inside a separate child shell"
mode="--inspect"
if (( $# > 0 )); then mode="$1"; fi
case "$mode" in
  --inspect)
    preflight
    echo "INSPECTION ONLY: no files or services modified"
    ;;
  --promote)
    EXPECTED_RESCUE_SHA256="$(printenv EXPECTED_RESCUE_SHA256 || true)"
    EXPECTED_AUDIT_SHA256="$(printenv EXPECTED_AUDIT_SHA256 || true)"
    PROMOTION_ACK="$(printenv PROMOTION_ACK || true)"
    preflight
    promote
    ;;
  *)
    echo "usage: sudo bash reviewed-script [--inspect|--promote]" >&2
    exit 2
    ;;
esac
