---
id: "aoe2war.wolochain.satchel-controlled-release"
title: "War Satchel Controlled Release Gates"
type: "reference"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "git"
authority: "source-integration-proof-not-production-approval"
reviewed_at: "2026-10-18"
review_interval_days: 14
sensitivity: "restricted"
---

# War Satchel Controlled Release Gates

The release candidate builds on the combined source in draft
[PR #38](https://github.com/Emaren/wolochain/pull/38), initially
`68cdc1ae2f1c877f40e7ee3f8c094729f080394f`; the
[source-bound index](DOCUMENTATION_CONTROL_PLANE.md) identifies the current
implementation. Its [versioned HTTP contract](settlement-contracts/war-satchel-http-v1.openapi.json),
[financial proof interface](war-satchel-financial-bridge.md) and
[artifact verification](war-satchel-exact-source-artifact.md) are source contracts.
The user reports the website deployed at app commit
`5aecab73cdd7aee4bae7df78e56ab31942c13643` on October 18 with financial funding
and automatic wagering disabled. This WoloChain change neither modifies nor
independently certifies that app release. A visible UI, green source CI and
HTTP `consensus_authenticated` fields do not authorize custody or ledger credits.

The production observations below are **dated receipts**, not a new live audit
or a claim that they remain current. The candidate requires a fresh bounded
identity/financial receipt immediately before protected execution; unresolved
liabilities stay held until independently proven otherwise.

## Fresh read-only production observation

The [machine-readable receipt](settlement-contracts/satchel-live-readonly-20261017.json)
records the observations below. At 2026-10-17 20:57 UTC, existing SSH access
was used only for bounded reads:
systemd MainPID/health, `/proc/PID/exe` hashes and Go metadata, and bounded
aggregate request/run JSON inspection. No environment, keyring or secret file
was read. No candidate binary was installed or executed on the VPS. Each
executable's inode/size/mtime and MainPID were checked before/after inspection.

| Service | PID | Executable | Actual embedded source |
| --- | --- | --- | --- |
| Legacy 8092 | 1012 | `/usr/local/bin/wolochaind-mainnet` | `78c25985420ee41a6678c42fab8ea8d6c3b1b519`, modified=false |
| Founder 8093 | 1010 | same settlement executable | same clean source |
| Consensus, observe only | 1009 | `/usr/local/bin/wolochaind-mainnet-node-prewartrophy` | `d3bd62414a047a492a3814b7d3baa2717d64db2e`, modified=true |

Both actual settlement executables hash to
`040126a2884946caf1651a50b7d8115c5a6fb2d5aa94fcbbe150694602d451a5`.
The separate historical consensus executable hashes to
`4b77f622191db7550cb87cafb8f1886a0aadebee3eb6565f9f90036f809e61d3`.
8092/8093 reported healthy literal-loopback `wolo-1`; 8094 had no listener.
Payout address fingerprints differ (`d22311cf4725e370` versus
`84f8e23234b72262`), while both health reports identify the existing betting
escrow fingerprint `5712f9536e3e5c94`. That escrow is excluded from Satchel
vault custody. Fingerprints are observations, not proof of independent key
control or permission to transfer funds.

Health reported balances in uwolo: 8092 payout `397509250000`, founder payout
`356787241424`, shared escrow `826173750000`. These unauthenticated service
observations are **not** complete reserve provenance or solvency. A separately
attempted local REST balance query was unavailable; no independently proven
bank/liability reconciliation was obtained.

At 20:59 UTC, 8092 had 910 request records (904 confirmed, five failed, one
accepted) and 784 run records (780 confirmed, three failed, one accepted).
The accepted request records `100000000` uwolo. Request and run records may
refer to the same obligation; they must not be added as separate liabilities.
8093 had 646 requests (609 confirmed, 37 failed), with no run directory.
Both observed lock directories were empty. This is a nonexclusive observation,
not an ingress fence, stable snapshot, proof of no in-flight writers, or a
complete liability inventory. **Never retry an accepted/uncertain record.**
Founder claim #889 was not individually investigated or replayed; its separate
financial hold remains unchanged.

## Dependency order for operator execution

1. Independently review the final source and exact CI receipts. Download the
   composed `wolosatcheld` archive plus its separately anchored GitHub receipt;
   authenticate archive and manifest digests, then run the shared offline
   verifier with `--profile composed-satcheld` and the exact CI identity. The
   legacy `526d5eb6` artifact is a separate `wolochaind` candidate.
2. HD must consume the portable proof through a pinned offline verifier using
   its own operator-provisioned anchor and stored intent, verify signed v2
   allocations and owner withdrawal mandates, and atomically consume both
   physical transaction identity and obligation under its ledger fence. Keep
   the activation hold until that implementation and adverse tests are reviewed.
3. Obtain current reserve/liability and independent vault-control evidence.
   Provision the distinct 8094 OS account, keyring, approval boundary, private
   token, journal, network sources and independently authenticated checkpoint
   and witness through the operator's separate governed process. Never derive
   a trust checkpoint from a proof response or reuse 8092/8093/consensus keys.
4. The app owner must supply exact current schema/frontier, successful protected
   shadow and real-data backfill evidence, globally unique receipt consumption,
   owner reservation and complete lifecycle integration. Earlier seven-migration
   receipts predate the subsequently extended app schema and cannot authorize its
   current financial installation. WoloChain neither executes app migrations nor
   resolves the app's previously reported schema-equivalence hold.
5. Before any legacy replacement, fence HD and DE ingress and all alternate
   financial writers. Reconcile accepted/unknown requests and complete
   liabilities without rebroadcast. Prove exclusive current state ownership,
   checksummed current snapshots and an approved state-preserving paired
   rollback/recovery procedure. Keep #889 held. Consensus PID/executable remains
   unchanged throughout; retired rescue/rollback scripts stay retired.
6. With named operator approval, execute only the separately reviewed protected
   settlement cutover and schema installation. Provision the isolated signer
   at a versioned path from the verified composed artifact. No installation,
   key creation, service restart or financial activation is authorized while
   the preceding evidence is missing. Conditional reviewed commands below are
   an operator procedure, not permission to execute them.
7. A separately approved small canary must prove exact running binaries,
   authenticated deposit, owner/cap/revocation behavior, no double reservation,
   settlement, full unmatched principal refund, partial matched allocation,
   owner withdrawal and restart/UNKNOWN recovery. Freeze producers on any
   mismatch; retain holds and current journals for read-only reconciliation.
   Recovery must preserve the latest financial history, never restore an older
   journal or manufacture success by retrying an ambiguous payment.

## Flow status at this source milestone

| Flow | Production status | Actual remaining prerequisite |
| --- | --- | --- |
| Deposit | BLOCKED | Independently reviewed current app proof/receipt integration and protected schema admission; independent vault/reserve/trust provisioning |
| Signed auto-bet authorization | BLOCKED | deployed owner/ADR-36/revocation/Watcher proof; current 1,000 WOLO per-bet and 10,000 daily source bounds retained |
| Automatic betting | BLOCKED | dedicated signer runtime plus HD reservation/concurrency/mandate integration and canary |
| Settlement | BLOCKED | exact-source legacy cutover, authoritative match allocation review and complete liabilities/drain |
| Refund | BLOCKED | HD signed v2 allocation + authenticated proof consumption; full unmatched principal remains mandatory |
| Withdrawal | BLOCKED | HD owner-mandate/independent approval worker, durable reservation proof and authenticated finalize/recovery consumer |

No end-to-end production financial canary or new production deployment is
claimed. C2 remains `UNAVAILABLE`; all portable proof receipts are
`NONCREDITING`. Source CI and reproducible artifacts cannot clear these gates.

## Protected installation procedure — commands, not execution authority

These commands have **not** been run. An operator may execute them only after
named human approval of this exact candidate, authenticated artifact receipts,
independent key-control/role exclusion evidence, reviewed app integration,
current bank/liability reconciliation (including fees), producer fencing,
quiesced recovery snapshots and independently provisioned Comet trust. No key,
token or permit generation command is included. All configuration/secret files
must already exist from the separate governed provisioning process; the bearer
credential must never be printed, put in shell history or copied into a PR.

Use the reviewed artifact profile whose pinned implementation actually contains
this candidate. The historical `composed-satcheld` profile pins `155fcf67` and
**does not** contain later source changes. Do not bypass its source mismatch or
substitute a locally self-consistent unsigned manifest. Set the variables below
from independently authenticated GitHub run/artifact receipts, not from the
untrusted candidate itself. Use a clean candidate source/tooling checkout.

```sh
set -eu
: "${APPROVED_SOURCE_SHA:?exact independently reviewed full source SHA}"
: "${APPROVED_BINARY_SHA256:?independently authenticated artifact digest}"
: "${APPROVED_PROFILE:?reviewed pinned artifact profile for this source}"
: "${CLEAN_SOURCE:?clean checkout of exact compiled implementation}"
: "${ARTIFACT_DIR:?verified downloaded and unpacked artifact directory}"
: "${AUTHENTICATED_MANIFEST_SHA256:?separately authenticated manifest digest}"
: "${VERIFIED_BUILDER_COMMIT:?reviewed artifact tooling commit}"
: "${VERIFIED_RUN_ID:?GitHub run ID}"
: "${VERIFIED_RUN_ATTEMPT:?GitHub run attempt}"
: "${VERIFIED_WORKFLOW_REF:?exact workflow ref}"
: "${VERIFIED_WORKFLOW_SHA:?exact workflow SHA}"
test "$(git -C "$CLEAN_SOURCE" rev-parse HEAD)" = "$APPROVED_SOURCE_SHA"
python3 scripts/settlement-artifact.py verify --profile "$APPROVED_PROFILE" \
  --source-dir "$CLEAN_SOURCE" --binary "$ARTIFACT_DIR/wolosatcheld" \
  --manifest "$ARTIFACT_DIR/manifest.json" \
  --expected-manifest-sha256 "$AUTHENTICATED_MANIFEST_SHA256" \
  --repository Emaren/wolochain --builder-commit "$VERIFIED_BUILDER_COMMIT" \
  --run-id "$VERIFIED_RUN_ID" --run-attempt "$VERIFIED_RUN_ATTEMPT" \
  --workflow-ref "$VERIFIED_WORKFLOW_REF" --workflow-sha "$VERIFIED_WORKFLOW_SHA"
printf '%s  %s\n' "$APPROVED_BINARY_SHA256" "$ARTIFACT_DIR/wolosatcheld" | sha256sum -c -
```

First installation uses only the new dedicated service. The OS account,
private configuration, public approval keys, existing independently provisioned
keyring, checkpoint/witness, signed activation permit and private directories
must already be reviewed and installed. Their absence is a STOP, not a reason
to reuse a legacy role. Private files must be owned by the service EUID with no
group/world access and no symlink components; the executable and service unit
are root-owned. `-check` checks permit/configuration only and explicitly reports
`TRUST_UNCHECKED`; actual startup must authenticate current chain trust.

```sh
RELEASE_DIR="/opt/wolo-satchel/releases/$APPROVED_SOURCE_SHA"
test ! -e "$RELEASE_DIR"
test ! -e /etc/systemd/system/wolo-satchel.service
id wolo-satchel >/dev/null
sudo install -d -o root -g root -m 0755 "$RELEASE_DIR"
sudo install -o root -g root -m 0755 "$ARTIFACT_DIR/wolosatcheld" "$RELEASE_DIR/wolosatcheld"
sudo -u wolo-satchel "$RELEASE_DIR/wolosatcheld" -config /etc/wolo-satchel/config.json -check
UNIT_FILE="$(mktemp --suffix=.service)"
sed "s/REVIEWED_SHA/$APPROVED_SOURCE_SHA/g" \
  mainnet-prep/systemd/wolo-satchel.service.example > "$UNIT_FILE"
systemd-analyze verify "$UNIT_FILE"
sudo install -o root -g root -m 0644 "$UNIT_FILE" /etc/systemd/system/wolo-satchel.service
rm -- "$UNIT_FILE"
sudo systemctl daemon-reload
# Requires the separate explicit service-start approval. Do not enable on boot.
sudo systemctl start wolo-satchel.service
sudo systemctl is-active --quiet wolo-satchel.service
SATCHEL_PID="$(sudo systemctl show -P MainPID wolo-satchel.service)"
sudo readlink "/proc/$SATCHEL_PID/exe"
sudo sha256sum "/proc/$SATCHEL_PID/exe"
```

The runtime executable digest must match `APPROVED_BINARY_SHA256`. The separate
operator health probe must load the bearer secret from its protected file
without printing it or placing it in process argv, authenticate 8094, verify
exact vault/build identity, and retain only a private/redacted receipt. Do not
open financial producers or publish a deposit destination after health alone.
The app activation hold remains disabled pending independently approved canary.

For first-installation rollback, keep all producers fenced and stop **only**
this new service under recovery approval. Preserve the latest journal, including
UNKNOWN attempts, even if no successful payment is known:

```sh
sudo systemctl stop wolo-satchel.service
test "$(sudo systemctl show -P ActiveState wolo-satchel.service)" = inactive
# Capture/checksum the now-quiesced state under the reviewed private snapshot
# procedure. Never replace operations.db with a pre-operation backup.
```

An upgrade/downgrade requires a separately proven journal-format compatibility
receipt and versioned old unit/binary. Stopping the new service and preserving
state is the safe fallback when compatibility is unknown. Never delete journal
buckets, switch to an old empty state path, or restore an older database to make
UNKNOWN work retryable.

Legacy 8092/8093 replacement stays a **separate exact bdbce253 procedure**. The
existing controller accepts only its pinned old/new binaries and a root-owned
short-lived external financial permit. Inspect is nonmutating; promote/rollback
are listed solely for a later independently authorized operator cutover:

```sh
sudo python3 scripts/settlement-bdbce253-code-cutover.py --mode inspect
# AFTER explicit protected legacy cutover approval and all financial gates:
sudo python3 scripts/settlement-bdbce253-code-cutover.py --mode promote \
  --permit /root/aoe2war-release/approved-two-service-permit.json
# Under approved recovery, retaining current request/run history and fences:
sudo python3 scripts/settlement-bdbce253-code-cutover.py --mode rollback \
  --permit /root/aoe2war-release/approved-two-service-permit.json
# A partial/inactive interrupted switch uses the same reviewed permit:
sudo python3 scripts/settlement-bdbce253-code-cutover.py --mode recover-interrupted \
  --permit /root/aoe2war-release/approved-two-service-permit.json
```

These commands must never target `wolochaind-mainnet.service`, its executable,
its state or its keys. Neither recovery path resumes HD/DE financial producers.
Founder #889 and accepted legacy transactions retain their individual holds;
a release permit is not payment evidence and cannot clear them.
