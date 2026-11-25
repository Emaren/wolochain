#!/usr/bin/env bash
# Read-only settlement-only go/no-go provenance. NEVER installs or restarts.
set -euo pipefail

EXPECTED_OLD_SOURCE="78c25985420ee41a6678c42fab8ea8d6c3b1b519"
EXPECTED_NEW_SOURCE="bdbce253c524d6faac14f61cd129ac5072287c3f"
EXPECTED_OLD_SETTLEMENT_SHA="040126a2884946caf1651a50b7d8115c5a6fb2d5aa94fcbbe150694602d451a5"
EXPECTED_NODE_SHA="4b77f622191db7550cb87cafb8f1886a0aadebee3eb6565f9f90036f809e61d3"
EXPECTED_NODE_SOURCE="d3bd62414a047a492a3814b7d3baa2717d64db2e"
REPO="/var/www/WoloChain-wolo-1"
SETTLEMENT_BIN="/usr/local/bin/wolochaind-mainnet"
NODE_BIN="/usr/local/bin/wolochaind-mainnet-node-prewartrophy"

usage() {
  cat <<'HELP'
Usage: sudo bash scripts/settlement-only-provenance.sh
       sudo bash scripts/settlement-only-provenance.sh --candidate /path/to/wolochaind --sha256 EXPECTED_SHA256

Read-only: proves running settlement/node binary identity and exact candidate VCS source.
It does not install, copy, restart, reload, sign or move any WOLO.
Pass the expected candidate SHA256 from the *independent* CI artifact receipt.
HELP
}

fail() { printf 'BLOCKED: %s\n' "$*" >&2; exit 2; }
sha_file() { sha256sum "$1" | awk '{print $1}'; }
vcs_value() {
  local bin="$1" key="$2"
  "$GO_BIN" version -m "$bin" | sed -n "s/^[[:space:]]*build[[:space:]]\+$key=//p" | head -n 1
}
assert_identity() {
  local label="$1" bin="$2" expected_sha="$3" expected_vcs="$4" expected_mod="$5"
  [[ -r "$bin" ]] || fail "$label executable not readable"
  local digest revision modified
  digest="$(sha_file "$bin")"
  [[ "$digest" == "$expected_sha" ]] || fail "$label SHA mismatch: $digest"
  revision="$(vcs_value "$bin" vcs.revision)"
  modified="$(vcs_value "$bin" vcs.modified)"
  [[ "$revision" == "$expected_vcs" ]] || fail "$label source revision mismatch: ${revision:-missing}"
  [[ "$modified" == "$expected_mod" ]] || fail "$label modification flag mismatch: ${modified:-missing}"
  printf 'PASS %-24s sha256=%s vcs=%s modified=%s\n' "$label" "$digest" "$revision" "$modified"
}
check_unit() {
  local unit="$1" expected_bin="$2" expected_sha="$3"
  systemctl is-active --quiet "$unit" || fail "$unit not active"
  local pid path actual
  pid="$(systemctl show -P MainPID "$unit")"
  [[ "$pid" =~ ^[1-9][0-9]*$ ]] || fail "$unit missing MainPID"
  path="$(readlink "/proc/$pid/exe")" || fail "$unit executable inaccessible"
  [[ "$path" == "$expected_bin" ]] || fail "$unit unexpected executable: $path"
  actual="$(sha_file "/proc/$pid/exe")" || fail "$unit running SHA inaccessible"
  [[ "$actual" == "$expected_sha" ]] || fail "$unit running SHA mismatch: $actual"
  printf 'PASS %-41s pid=%s sha256=%s\n' "$unit" "$pid" "$actual"
}

candidate=""
expected_candidate_sha=""
while (( $# )); do
  case "$1" in
    --candidate) (( $# >= 2 )) || fail "missing candidate path"; candidate="$2"; shift 2 ;;
    --sha256) (( $# >= 2 )) || fail "missing expected SHA"; expected_candidate_sha="$2"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) fail "unsupported argument $1" ;;
  esac
done
[[ -z "$candidate" && -z "$expected_candidate_sha" ]] || {
  [[ -n "$candidate" && "$expected_candidate_sha" =~ ^[[:xdigit:]]{64}$ ]] ||
    fail "candidate and a 64-digit expected SHA256 are required together"
}

(( EUID == 0 )) || fail "read-only /proc inspection requires root; run with sudo"
for name in git systemctl sha256sum readlink curl sed awk; do
  command -v "$name" >/dev/null 2>&1 || fail "missing $name"
done
GO_BIN="$(command -v go || true)"
[[ -n "$GO_BIN" ]] || GO_BIN="/usr/local/go/bin/go"
[[ -x "$GO_BIN" ]] || fail "Go toolchain not available for VCS attestation"

echo "=== WOLO SETTLEMENT-ONLY PROVENANCE (READ ONLY) ==="
date -u '+observed_at=%Y-%m-%dT%H:%M:%SZ'
[[ "$(git -C "$REPO" rev-parse HEAD)" == "$EXPECTED_OLD_SOURCE" ]] ||
  fail "VPS checkout changed; inspect new source before promotion"
[[ -z "$(git -C "$REPO" status --porcelain)" ]] || fail "VPS checkout dirty"
echo "PASS checkout clean and matches pinned running settlement source"

assert_identity "installed settlement" "$SETTLEMENT_BIN" "$EXPECTED_OLD_SETTLEMENT_SHA" "$EXPECTED_OLD_SOURCE" false
assert_identity "installed consensus" "$NODE_BIN" "$EXPECTED_NODE_SHA" "$EXPECTED_NODE_SOURCE" true
check_unit "wolochain-mainnet-settlement.service" "$SETTLEMENT_BIN" "$EXPECTED_OLD_SETTLEMENT_SHA"
check_unit "wolochain-founder-rewards-settlement.service" "$SETTLEMENT_BIN" "$EXPECTED_OLD_SETTLEMENT_SHA"
check_unit "wolochaind-mainnet.service" "$NODE_BIN" "$EXPECTED_NODE_SHA"
curl -fsS --max-time 8 'http://127.0.0.1:8092/settlement/v1/health' >/dev/null ||
  fail "8092 health endpoint unavailable"
echo "PASS settlement 8092 health endpoint"

if [[ -n "$candidate" ]]; then
  [[ -f "$candidate" && -r "$candidate" && ! -L "$candidate" ]] || fail "candidate missing/unreadable or symlink"
  [[ "$(sha_file "$candidate")" == "${expected_candidate_sha,,}" ]] ||
    fail "candidate SHA256 mismatch with independent CI receipt"
  [[ "$(vcs_value "$candidate" vcs.revision)" == "$EXPECTED_NEW_SOURCE" ]] ||
    fail "candidate is not compiled from reviewed source $EXPECTED_NEW_SOURCE"
  [[ "$(vcs_value "$candidate" vcs.modified)" == false ]] ||
    fail "candidate is not a clean-source build"
  [[ "$(vcs_value "$candidate" GOOS)" == linux ]] ||
    fail "candidate is not a Linux executable"
  [[ "$(vcs_value "$candidate" GOARCH)" == amd64 ]] ||
    fail "candidate is not an amd64 executable"
  [[ "$(sha_file "$candidate")" == "${expected_candidate_sha,,}" ]] ||
    fail "candidate content changed during inspection"
  printf 'PASS candidate exact revision=%s sha256=%s\n' "$EXPECTED_NEW_SOURCE" "$expected_candidate_sha"
else
  echo "NO CANDIDATE GIVEN: existing runtime verified; deployment NOT authorized"
fi
echo "NOTE: passing provenance is not a bank/solvency, rollback, integration, or deploy approval"
