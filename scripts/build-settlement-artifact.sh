#!/usr/bin/env bash
# Build and inspect only. Never executes the candidate or operates a service.
set -euo pipefail

EXPECTED_SOURCE=526d5eb6123f6cc0394b5e78489c668e77e46106
EXPECTED_GO=go1.24.6
fail() { printf 'INVALID SETTLEMENT BUILD: %s\n' "$*" >&2; exit 2; }
[[ $# == 2 ]] || fail 'usage: build-settlement-artifact.sh CLEAN_SOURCE_DIR NEW_OUTPUT_DIR'
tools_dir="$(cd "$(dirname "$0")" && pwd)"
source_dir="$(cd "$1" && pwd)"
output_dir="$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve())' "$2")"
[[ ! -e "$output_dir" ]] || fail 'output directory must not already exist'
[[ "$output_dir/" != "$source_dir/"* ]] || fail 'output must be outside the source checkout'

# Reject ambient toolchain selection, workspace overlays, build flags and CPU or
# FIPS variants. These are build inputs, not operator financial configuration.
export GOTOOLCHAIN=local GOENV=off GOWORK=off GOFLAGS= GOEXPERIMENT= GOFIPS140=off
export GOOS=linux GOARCH=amd64 GOAMD64=v1 CGO_ENABLED=0 GIT_NO_REPLACE_OBJECTS=1
export GOPRIVATE= GONOPROXY= GONOSUMDB= GOSUMDB=sum.golang.org
export GOPROXY=https://proxy.golang.org,direct
export PYTHONDONTWRITEBYTECODE=1
unset GODEBUG
go_bin="$(command -v go)"
[[ "$("$go_bin" env GOVERSION)" == "$EXPECTED_GO" ]] || fail 'requires exactly Go 1.24.6'
for name in BUILDER_COMMIT GITHUB_REPOSITORY GITHUB_RUN_ID GITHUB_RUN_ATTEMPT GITHUB_WORKFLOW_REF GITHUB_WORKFLOW_SHA; do
  [[ -n "${!name:-}" ]] || fail "missing externally supplied CI identity: $name"
done

check_source() {
  # Run the same source policy used by the manifest verifier before and after
  # compilation, including hidden index flags and ignored source inputs.
  python3 - "$tools_dir/settlement-artifact.py" "$1" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("artifact", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.source_identity(sys.argv[2])
PY
}
check_source "$source_dir"
[[ "$(git --no-replace-objects -C "$source_dir" rev-parse HEAD)" == "$EXPECTED_SOURCE" ]] || fail 'source drift'
scratch_dir="$(mktemp -d "${TMPDIR:-/tmp}/wolo-artifact.XXXXXXXX")"
trap 'rm -rf -- "$scratch_dir"' EXIT
git clone --quiet --no-local --no-checkout "$source_dir" "$scratch_dir/rebuild-source"
git -C "$scratch_dir/rebuild-source" checkout --quiet --detach "$EXPECTED_SOURCE"
check_source "$scratch_dir/rebuild-source"
mkdir -p "$output_dir" "$scratch_dir/rebuild"

build_one() {
  local checkout="$1" cache="$2" destination="$3"
  (
    cd "$checkout"
    "$go_bin" mod verify
    GOCACHE="$cache" "$go_bin" build -trimpath -buildvcs=true -tags=go1.27 \
      -mod=readonly -ldflags=-buildid= -o "$destination" ./cmd/wolochaind
  )
  check_source "$checkout"
}
build_one "$source_dir" "$scratch_dir/cache-first" "$output_dir/wolochaind"
build_one "$scratch_dir/rebuild-source" "$scratch_dir/cache-second" "$scratch_dir/rebuild/wolochaind"
cmp -s "$output_dir/wolochaind" "$scratch_dir/rebuild/wolochaind" || fail 'independent builds differ'

identity_args=(
  --source-dir "$source_dir" --binary "$output_dir/wolochaind" --manifest "$output_dir/manifest.json"
  --builder-commit "$BUILDER_COMMIT" --repository "$GITHUB_REPOSITORY"
  --run-id "$GITHUB_RUN_ID" --run-attempt "$GITHUB_RUN_ATTEMPT"
  --workflow-ref "$GITHUB_WORKFLOW_REF" --workflow-sha "$GITHUB_WORKFLOW_SHA" --go "$go_bin"
)
python3 "$tools_dir/settlement-artifact.py" create "${identity_args[@]}" --rebuild "$scratch_dir/rebuild/wolochaind"
manifest_sha="$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$output_dir/manifest.json")"
python3 "$tools_dir/settlement-artifact.py" verify "${identity_args[@]}" --expected-manifest-sha256 "$manifest_sha"
"$go_bin" version -m "$output_dir/wolochaind" > "$output_dir/go-build-metadata.txt"
python3 - "$output_dir" <<'PY'
import hashlib, pathlib, sys
root = pathlib.Path(sys.argv[1])
with (root / "SHA256SUMS").open("x") as output:
    for name in ("wolochaind", "manifest.json", "go-build-metadata.txt"):
        with (root / name).open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        output.write(f"{digest}  {name}\n")
PY
printf 'UNDEPLOYED exact-source settlement artifact: %s\n' "$output_dir"
