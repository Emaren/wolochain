# WE1 C03 — disposable PG16 + signed-evidence source integration

Status: **SOURCE-ONLY / DRAFT / FUNDING DENIED / C03 OPEN**.

This branch proposes the reviewed existing Ed25519 journal model and a strict disposable PostgreSQL 16 receipt bridge. The companion WoloChain PR #248 `scripts/c03_disposable_pg16_fence_rehearsal.py` now additionally exercises live all-reject HBA **reload** with an already-connected writer, and its test output has expanded from 13 to 15 checks. Source SHA-256 for that 15-check M1 version: `874e470e25bab8203055898df4ed1fbdd2bdd967805818afed5cff45f5f5edda`. Draft source commit `d6801a16c6a37ec39c61e99f3e53826ead9e3d02`.

The M1 local PostgreSQL 16 disposable rehearsal produced the 15-check receipt whose observed fields are preserved in this checked-in JSON test fixture; the fixture must still be compared to authentic runner stdout before acceptance. It tested one existing connected writer surviving both a live HBA reload and NOLOGIN, a SECURITY DEFINER bypass, denial of that existing connection's DML/sequence/definer operations after revocation, continuity of a reader, PostgreSQL HBA all-client rejection across two restarts and exact synthetic inverse ACL/HBA restoration. It did **not** test a real PgBouncer proxy or HEL1 PostgreSQL. Test source SHA-256 must match the value in the evidence bridge.

The new bridge archives the original PG16 *test* receipt bytes under a SHA-256 name, fsyncs a mode-0600 file and directory, and will admit a `FENCED` source-only claim only when a distinct Ed25519 evidence signature binds the receipt hash to the exact journal preimage, prior head, event and transition sequence. Every inspection by an existing process now ALSO replays the signed journal on disk and matches the cached journal head/sequence/preimage; deletion, rehashing or rewriting a signed record downgrades to UNKNOWN. Evidence reads use a directory-anchored descriptor and `O_NOFOLLOW`, strict UID/mode and single-link checks, so symlink replacement fails closed. Journal replay requires both valid signed journal state and unchanged, present evidence bytes. Missing/changed/unsafe-mode evidence returns **UNKNOWN**; a signed `RESTORED` label remains **UNKNOWN**, because physical inverse attestation is not yet implemented. Cryptographic keys in tests are synthetic and permanently ineligible for production.

This is **not a production witness**: the receipt is test-runner stdout and can be fabricated by a caller. No trusted systemd/PgBouncer/postmaster process attestor, independently enrolled keys, off-host durable checkpoint, authorized Codex acceptance or financial maintenance permit is present. The source does not control PostgreSQL or systemd, cannot reopen funds and does not prove a whole-cluster writer fence.

Focused isolated tests: **116/116 PASS** (80 existing signed model + 36 bridge/security checks) on Python 3.13. Evidence is test-only: missing production trust anchors, source-pinned independent process attestation and off-host checkpoint remain hard blockers. Run: `PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider tests/test_c03_durable_admission.py tests/test_c03_pg16_evidence_bridge.py`. The PG16 runner requires explicit `WE1_C03_DISPOSABLE_ONLY=1`, uses synthetic roles, a fresh temporary PGDATA and a private socket, and is not to be run against live systems.

Admission prerequisites: independent Codex Session A source review, source-pinned actual PostgreSQL 16 and systemd/parent child startup-mask readbacks, actual pooler/preconnected and SECURITY DEFINER/trigger/sequence graph coverage for HD+DE, signed *independent* physical witness, crash UNKNOWN/recovery adversarial tests on disposable hosts, durable attested off-host recovery checkpoint, signed owner-scoped exact inverse permit, legitimate DocsV2 review of expired financial documentation, synchronized C06 backup and C07 restoration, and later a separately approved HEL1 outage. C01 and financial ports remain isolated; C09 last. Never use this model to produce or sign owner/root permits; all financial gate status remains C03 OPEN and FUNDING DENIED.


## November 18 independent source-review addendum (source-only)

The bridge now pins the historical 15-check PostgreSQL test receipt SHA256
`300d19f126eaa42e48c75666ed52b3ea169f05903ef14840bf622486f9fa809c`.
A new JSON object containing the same `PASS` fields cannot be substituted for
that preserved prior test receipt. This prevents fixture drift, **not** forged
physical evidence: the original stdout could itself be reproduced by a caller.

The evidence writer now uses an open directory descriptor, `O_NOFOLLOW`,
owner/mode checks and directory-relative `O_EXCL` creation; this reduces
filesystem path-substitution risk on archival writes. The `require_production_fence`
interface intentionally fails with `C03_NO_INDEPENDENT_PRODUCTION_PHYSICAL_WITNESS`
even if `state` returns `FENCED` for this test-only model. No production executor,
independent PostgreSQL/systemd attestor, source owner acceptance, trust enrollment,
financial backup permit, or maintenance authorization has been installed.

The standalone source candidate was independently tested in a local Python 3.13
container with `cryptography 46.0.4` and `pytest 9.0.2`: **116/116 PASS**.
A freshly generated disposable owner-M1 PostgreSQL 16 instance independently
replayed the separately committed PR #248 test harness: **15/15 PASS** (no
production SQL). These are two SEPARATE suites, **not** end-to-end signing of
live PostgreSQL physical observations.

### Source-owner integration rule

This Git-style patch is a reviewable external candidate only. The **authorized
FINANCIAL Codex source owner** must check SHA256s, source-diff each file,
reproduce tests on its approved machine, qualify actual process-attested
readbacks, and separately commit/admit through its own FINANCIAL source
procedure. Applying this patch is not automatically an independent approval.
The existing DocsV2 review backlog remains outstanding; no historical
`reviewed_at` field is changed by this patch.
