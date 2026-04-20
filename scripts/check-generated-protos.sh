#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BUF_BIN="${BUF_BIN:-buf}"
GO_BIN="${WOLO_GO_BIN:-go}"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    fail "Missing required command: $1"
  fi
}

require_cmd "$BUF_BIN"
require_cmd "$GO_BIN"
require_cmd cmp
require_cmd diff
require_cmd mktemp

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

cat >"$tmpdir/buf.gen.gogo.yaml" <<YAML
version: v2
plugins:
  - local: ["$GO_BIN", "run", "github.com/cosmos/gogoproto/protoc-gen-gocosmos@v1.7.0"]
    out: .
    opt:
      - plugins=grpc
      - Mgoogle/protobuf/any.proto=github.com/cosmos/gogoproto/types/any
      - Mcosmos/orm/v1/orm.proto=cosmossdk.io/orm
      - Mcosmos/app/v1alpha1/module.proto=cosmossdk.io/api/cosmos/app/v1alpha1
  - local: ["$GO_BIN", "run", "github.com/grpc-ecosystem/grpc-gateway/protoc-gen-grpc-gateway@v1.16.0"]
    out: .
    opt:
      - logtostderr=true
      - allow_colon_final_segments=true
YAML

"$BUF_BIN" generate --template "$tmpdir/buf.gen.gogo.yaml" --output "$tmpdir/out"

generated_root="$tmpdir/out/github.com/emaren/wolochain/x/wolochain/types"
expected_files=(
  genesis.pb.go
  module.pb.go
  params.pb.go
  query.pb.go
  query.pb.gw.go
  tx.pb.go
)

for name in "${expected_files[@]}"; do
  generated="$generated_root/$name"
  committed="x/wolochain/types/$name"

  [[ -f "$generated" ]] || fail "Generator did not produce $name"
  [[ -f "$committed" ]] || fail "Committed generated file is missing: $committed"

  if ! cmp -s "$generated" "$committed"; then
    diff -u "$committed" "$generated" | sed -n '1,160p'
    fail "Generated proto output is stale: $committed"
  fi
done

echo "Generated proto outputs are current."
