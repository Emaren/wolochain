woloreviewerd: protected independent reviewer startup composition

This source command composes existing production evidence adapters. It is not
an installation, operator enrollment, solvency certificate, release seal, or
financial activation. No live inputs ship with the source. The current owner
authorization source epoch remains held; this command has no override for it.

Entrypoint
  woloreviewerd --config /absolute/protected/reviewer.json
  woloreviewerd --config /absolute/protected/reviewer.json --check

The only listener is the existing private 127.0.0.1:8095 reviewer HTTP server.
Its existing request schema is POST /reviewer/v1/wagers with an authenticated
application/json body containing only protocol=1 and operation_id. A caller
cannot choose a signer, vault, amount, fee, proof, database, URL, or policy.
There is no health response asserting custody readiness or financial approval.

--check validates the exact config schema, policy digest, clean embedded Git
revision, executable SHA256, and independent startup permit. It performs no
source I/O, reads no private reviewer key/DB credential/token, opens no journal
or listener, and explicitly reports SOURCES_UNCHECKED. It does not prove that
the selected PostgreSQL role, original Watcher, chain, or financial census is
available or authoritative.

Selected protected inputs (no defaults or operative placeholder example)

config.go defines the complete required JSON schema. Every field is mandatory;
null, unknown, duplicate, case-aliased, and trailing JSON values are refused.
All paths must be absolute, clean, and distinct. Config, immutable input pins,
and startup permit are read with the existing same-descriptor private-file
reader: current-EUID owner, regular file, single link, no symlink components,
no group/world permissions, bounded size and stable descriptor metadata.

version is 1. source_revision must match the clean Git vcs.revision embedded
by the Go build. vcs.modified must be false. binary_sha256 must match the
running executable. No -ldflags, environment, or command-line attestation
override exists. issuer_policy_sha256 is SHA256(json.Marshal(existing Policy))
with the exact protected address order and decoded public-key bytes. An
uncommitted candidate executable therefore cannot qualify as a clean build.

vault and betting_escrow are distinct valid wolo addresses; the vault cannot
be a registered treasury/founder/legacy role. protected_addresses includes the
escrow and excludes the vault. max_amount_uwolo is explicit and currently
bounded to the selected one-WOLO canary (1,000,000 uwolo). No principal release
or treasury float is supplied by this cap. This is the canary startup-config
gate; it does not change the existing product Policy amount limits.
fee_uwolo, minimum_gas_reserve_uwolo,
and minimum_unencumbered_uwolo must all be explicit positive bounded integers.

roles selects five distinct nonzero 32-byte Ed25519 public keys: accounting,
custody review, execution authority, wager approval, and withdrawal approval.
The Watcher witness key must be a sixth distinct key. reviewer_private_key
selects only the already provisioned 64-byte canonical Ed25519 wager-reviewer
key, matching the enrolled wager public key. Seeds, key generation, Cosmos
keyrings, chain signers, key import/export, and signer selection are absent.
Only this separately held reviewer key is selected; its protected bytes are
checked with the other pinned startup inputs. The issuer is constructed only
after chain/source startup checks, copies the key and zeroes its copy on close.

Every filePin is {path,sha256}, binding exact separately reviewed bytes:
PostgreSQL password, explicit CA and mTLS client certificate/key; original
Watcher CA and bearer; reviewer key; separate HTTP and custody read-only
bearers. These selected pins are reread before and after each source operation.
Certificates/tokens are never taken from a request or a remote response. The
HTTP, Watcher and custody bearers must remain three distinct principals.
Errors print fixed public labels, never paths, URLs, DSNs, secrets or source
response bodies.

postgres selects an explicit hostname/IP, port, database and independent role
matching satchel_reviewer_[a-z0-9_]{1,48}. PG* environment variables cause
refusal. There is no DSN/URL override. lib/pq uses verify-full with the selected
CA and inline selected mTLS material, so it does not discover ~/.postgresql
client credentials. A nonempty selected password prevents .pgpass fallback.
The session is READ ONLY by default, with 2-second statement/connect bounds,
500ms lock timeout, limited connection count and short connection lifetime.
Startup verifies the exact role and rejects privileged roles. Each existing
evidence adapter independently checks role membership, table/column write
privileges and actual immutable owner/ledger data inside its read-only
transaction; the startup login check is not a substitute for those checks.

watcher selects an HTTPS origin (no path/query/credentials), explicit CA,
leaf SPKI SHA256, bearer, and independent live-witness public key. The existing
transport enforces TLS 1.3, the selected trust roots and SPKI, finite budgets,
no proxy, no redirects and no environment fallback. The adapters read/hash
the original captured pre-bet live checkpoint, verify the separately signed
live witness and re-read the immutable PG identity after source I/O. A completed
replay or the application's own market JSON cannot replace these sources.

rpc, rest, witness_rpc and trust_anchor are explicit reviewed chain inputs.
URLs are origins, HTTPS or literal loopback HTTP. Primary and witness must
differ. The actual existing TrustedReader authenticates the independently
provisioned Comet anchor and live heads before the issuer journal/listener open;
bank observations retain native H/H+1 proof verification. Endpoint TLS by
itself is not the chain trust authority. No checkpoint is learned/enrolled
automatically from a provider response.

custody pins the actual separate custody runtime's build, config, permit and
policy digests. Its fee checkpoint reader is fixed by existing source to
127.0.0.1:8094/satchel/v1/custody/fee-checkpoint, authenticated with the selected
read-only bearer; no alternate URL or execution fallback exists. The issuer
provides its own actual durable fee checkpoint through the existing private
context seam. No issuer HTTP self-call or second journal reader is invented.

reserve_coverage_path selects the existing protected, separately refreshed
dual-signed complete coverage bundle. The existing census requires all six
built-in producer identities, plus every explicit required_producer_ids entry,
exact owner/native-bank/custody/issuer journal checkpoints, policy/runtime
pins, current signed reserve review, nonoverlap and every UNKNOWN fee. Empty
current Satchel state cannot erase historical or external obligations. The
command does not manufacture a bundle, mark it complete, rewrite bank evidence,
release booked principal, or turn reserve signatures into an execution permit.

journal_path selects a dedicated existing private non-symlink directory owned
by the process. A new issuer journal may be opened there by the existing issuer;
the command never creates/repairs a directory or changes permissions. Existing
journals must be regular, private, owned, single-link files. Bolt's existing
exclusive lock and durable PENDING-before-signing semantics remain intact.
PENDING/UNKNOWN is not freed or automatically reissued on restart.

Independent startup permit

permit_path selects a protected refreshable JSON startupPermit. Its only
accepted scope is aoe2war/satchel/reviewer-startup/v1, version 1. It binds exact
config SHA256, running binary SHA256, source revision, issuer policy SHA256,
vault, wager public key, issued_at and expires_at. It must already be issued,
unexpired, at most 120 seconds long, and signed by the separately enrolled
execution-authority PUBLIC key. No execution-authority private key is opened.

The exact signing bytes are JSON encoding of the array in permitMessage:
[domain,version,scope,config_sha256,binary_sha256,source_revision,
 issuer_policy_sha256,vault,wager_public_key_hex,issued_at,expires_at].
domain and scope both equal aoe2war/satchel/reviewer-startup/v1. Signature is
canonical padded base64 Ed25519. The config contains the fixed permit path,
not its digest, avoiding a self-referential config/permit hash. This reviewer
permit cannot substitute for the 8094 custody execution permit or the separate
dual financial review bound to custody runtime pins.

Revocation boundaries and remaining authority limits

The gate checks selected immutable bytes and the fresh signed permit before
and after every evidence-source call. Before opening HTTP, this command binds
the same gate through RequireIssuanceAuthorization. This trusted-runtime API
accepts one non-nil callback before this process's first issuer use; it cannot
be replaced, removed, or selected through HTTP. Existing records on restart
do not prevent binding the current protected gate before their first use.

ReviewOne checks authorization at entry, before durable PENDING, immediately
before Ed25519 signing, before persisting SIGNED, before disclosing an existing
grant, and before its final new-grant reply. It checks the actual context both
before and after the callback. Revocation/cancellation after PENDING leaves a
permanent PENDING entry with no automatic retry or renewal. Revocation observed
after durable SIGNED suppresses the reply and preserves the exact signature,
timestamps, fingerprint and financial obligation. Later disclosure requires
fresh authorization and all normal current-source checks; it reuses only the
same unexpired grant. No revocation path deletes or frees an UNKNOWN obligation.
The final HTTP response is additionally buffered until another gate check.
These explicit checks do not assert an atomic transaction with an independently
changed filesystem; the issuer no longer omits the final-sign authorization
boundary. This remains an approval service, not the custody execution boundary.

Cryptography checks selected identities and signed statements. It cannot
prove physical operator independence or discover an omitted external source.
Actual protected inputs, released owner epoch, all producer coverage and the
separate custody guard remain essential. Missing inputs, stale trust, a changed
file, revoked/expired permit, absent bank/census, or source failure remain HELD.

Verification status

New tests cover schema/identity substitution, exact clean-build pins, scoped
short-lived independent permits, protected file changes/permissions, explicit
TLS/DSN construction, PG environment refusal, journal aliases/permissions,
source-call revocation, private context preservation and response suppression.
Issuer tests additionally inspect actual durable Bolt state at pre-intent,
pre-sign, pre-SIGNED and post-SIGNED authorization boundaries, permanent PENDING,
historical grant replay, one-time startup binding, and context cancellation.
These tests are source artifacts and have NOT been run locally. No Go/native
build, live SDK execution, production installation, production input reads,
fund transfer, service change or key provisioning was performed for this change.
