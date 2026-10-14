#!/usr/bin/env bash
# Version-pinned offline-able helpers for a future dual-settlement release.
# --inspect is READ ONLY; --stage writes only to /usr/local/libexec.
# Neither mode modifies systemd, source checkouts, wallet keys, or chain state.
set -euo pipefail
umask 077

DIR=/usr/local/libexec/aoe2war-wolo
RESCUE=settlement-two-service-code-rollback.sh
AUDIT=wolo-maintenance-drain-readonly.mjs
RESCUE_REF=f547b5d6e25d0bf843fb6b83c8b88b4a3d1d5cbb
AUDIT_REF=3ecc28bd983bd517f4e82b982ef5726f3f33eaf7
RESCUE_BLOB=8bf03c7f90d7566b06575927cf5f92b5aa69a499
AUDIT_BLOB=f8372e27fb0cad13fecbdcb42ca2457dbf4caabb
RESCUE_URL="https://raw.githubusercontent.com/Emaren/wolochain/$RESCUE_REF/scripts/$RESCUE"
AUDIT_URL="https://raw.githubusercontent.com/Emaren/app-prodn/$AUDIT_REF/scripts/$AUDIT"
fail() { echo "BLOCKED: $*" >&2; exit 2; }
verify_existing() {
  local name="$1" blob="$2" mode="$3" p="$DIR/$1"
  [[ -f "$p" && ! -L "$p" ]] || fail "missing helper or symlink: $name"
  [[ "$(git hash-object "$p")" == "$blob" ]] || fail "source blob drift for $name"
  [[ "$(stat -c '%u:%g:%a' "$p")" == "0:0:$mode" ]] ||
    fail "unexpected helper ownership/mode: $name"
  echo "PASS $name exact pinned source and private permissions"
  sha256sum "$p"
}
mode=--inspect
if (( $# > 0 )); then mode="$1"; fi
(( EUID == 0 )) || fail "root required even for private file inspection"
case "$mode" in
  --inspect)
    verify_existing "$RESCUE" "$RESCUE_BLOB" 500
    verify_existing "$AUDIT" "$AUDIT_BLOB" 444
    echo "INSPECT_PASS: no file or service changes"
    ;;
  --stage)
    [[ -d "$DIR" && ! -L "$DIR" ]] || {
      [[ ! -e "$DIR" && ! -L "$DIR" ]] || fail "unsafe helper directory"
      install -d -o root -g root -m 0755 "$DIR" || fail "helper directory creation failed"
    }
    [[ "$(stat -c '%u:%g:%a' "$DIR")" == 0:0:755 ]] ||
      fail "helper directory ownership/mode drift"
    for file in "$DIR/$RESCUE" "$DIR/$AUDIT"; do
      [[ ! -L "$file" ]] || fail "refusing symlink target $file"
    done
    work="$(mktemp -d /tmp/wolo-pinned-helpers.XXXXXXXX)" || fail "temporary workspace"
    trap 'rm -rf -- "$work"' EXIT
    curl -fsSL --connect-timeout 10 --max-time 40 "$RESCUE_URL" -o "$work/$RESCUE" ||
      fail "could not retrieve exact rescue source"
    curl -fsSL --connect-timeout 10 --max-time 40 "$AUDIT_URL" -o "$work/$AUDIT" ||
      fail "could not retrieve exact financial audit source"
    [[ "$(git hash-object "$work/$RESCUE")" == "$RESCUE_BLOB" ]] ||
      fail "downloaded rescue source mismatches pinned Git blob"
    [[ "$(git hash-object "$work/$AUDIT")" == "$AUDIT_BLOB" ]] ||
      fail "downloaded finance source mismatches pinned Git blob"
    for spec in "$RESCUE:$RESCUE_BLOB:500" "$AUDIT:$AUDIT_BLOB:444"; do
      name="$(printf '%s' "$spec" | cut -d: -f1)"
      blob="$(printf '%s' "$spec" | cut -d: -f2)"
      if [[ -e "$DIR/$name" ]]; then
        [[ "$(git hash-object "$DIR/$name")" == "$blob" ]] ||
          fail "refusing to overwrite changed helper $name"
      fi
    done
    install -o root -g root -m 0500 "$work/$RESCUE" "$DIR/$RESCUE"
    install -o root -g root -m 0444 "$work/$AUDIT" "$DIR/$AUDIT"
    verify_existing "$RESCUE" "$RESCUE_BLOB" 500
    verify_existing "$AUDIT" "$AUDIT_BLOB" 444
    echo "STAGE_PASS: helper files only; no website/settlement/node changes"
    echo "Operator: retain the printed SHA-256 fingerprints for separately gated controller."
    ;;
  *)
    echo "usage: sudo bash source-verified-helper [--inspect|--stage]" >&2
    exit 2
    ;;
esac
