C02 private helper enrollment and exact inverse

This source-only builder does not connect to PostgreSQL. Every emitted SQL file
refuses before DDL. A generated file or passing fixture supplies no production,
funding, listener, role-enrollment or writer-exclusion authority.

The historical inputs are checked by immutable Git blob ID. The matcher and V2
wrapper fixtures preserve the previously reviewed bytes. The test compiles the
two original historical migrations and the native14 operation/wrapper subset
with explicitly declared minimal foreign-key prerequisites. This is not the
complete canonical 13+14 migration proof.

The oracle is pinned by its canonical SHA256 in reviewed source. Its current
owner policy is explicitly fixture-only, derived from the test's declared
migration-owner setup. A production owner profile requires a new independently
qualified, source-reviewed digest; caller-supplied labels cannot authorize it.
Changing both oracle and capture does not bypass the pin. The preimage binds
actual OIDs, raw ACL order,
grantors, constraints/indexes, triggers/functions, dependencies and unchanged
worker state. It also fingerprints worker credential state without returning
the stored credential. Oracle/capture provenance must be independently admitted;
capturing an arbitrary current database does not make it authoritative.

Enrollment requires a genuinely absent c02_row_lock role and c02_internal
schema, plus the existing restricted c02_journal_worker. It grants only the
specified historical columns and UPDATE on the three identifier columns, as
their verified table owners. It creates the exact NOLOGIN/NOINHERIT helper owner,
private schema and pinned helper. It changes no historical owner, table ACL,
sequence privilege, worker membership or financial record.

NULL and unrelated explicit column ACLs are supported. Explicit empty ACLs,
inheritance, policies/rules, changed original guards, unsafe relations and
unexpected sequence ownership are refused. The real matcher has no session_user
guard: private schema/function ACLs and role isolation enforce its caller boundary.

Inverse qualification is two-stage because new object OIDs do not exist before
enrollment. Capture IDENTITY_SQL through a fresh independently admitted readback
after commit. Supply that private postimage to the deterministic renderer; it
pins the created role, schema and helper identities. The unbound inverse retains
an additional unconditional refusal. An installation permit must already bind
the reviewed renderer, original preimage, postimage-capture procedure and inverse
policy. No unreviewed inverse is authorized by generating a file afterward.

Before inverse, restore the authentic original V2 wrapper body/configuration.
The inverse drops only the exact helper and schema with RESTRICT, revokes only
the added column grants as the original grantors, checks original metadata and
refuses extra objects, memberships, settings or cross-database dependencies
before dropping the new role. There is no CASCADE or DROP OWNED operation.
Accepted writer/DDL exclusion must cover the complete transaction and recovery.

Reproduce the new isolated tests (PostgreSQL16 binaries, no existing server):

    python3 scripts/test_c02_helper_enrollment.py \
      --migrations /private/path/to/original/migrations \
      --matcher scripts/c02_helper_inputs/matcher.sql \
      --v2-install scripts/c02_helper_inputs/wrapper-install.sql \
      --v2-inverse scripts/c02_helper_inputs/wrapper-inverse.sql \
      --pg-bin /path/to/postgresql16/bin --out /private/new/receipt-directory

The test creates a private Unix-only cluster and synthetic records, then stops
and removes it on success. Receipts distinguish fixture scope and admission.
Keep capture/postimage/generated SQL private; publish source and receipt hashes.
No owner or technical key, production password, wallet or receiver is accessed.
