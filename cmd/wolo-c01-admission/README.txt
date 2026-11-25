C01 zero-funds key admission

This command checks possession of the existing Satchel custody or technical
reviewer key. It has no listener, chain client, transaction entry point, or
reviewer approval route. The canonical service unit and its normal production
configuration are separate. Coordinate any change in their topology with App.

Build a clean Linux binary with Git VCS metadata. Run only as the selected
wolo-satchel or wolo-reviewer Linux user and group. The role's existing private
state directory must contain an owner-only 0700 c01-admission subdirectory for
durable nonce tombstones. Never restore older tombstones over an active
journal. Before admitting any restored state, expire all prior permits.

The protected admission config is a single compact canonical JSON object, with
fields in order: schema, role, key_fingerprint_sha256, c08_receipt_file,
c08_owner_public_file, permit_file, and for Satchel only custody. Schema is
wolo.c01.zero-funded-startup-config.v1. The fingerprint hashes the raw enrolled
public key. The last custody object has vault, public_key_hex, and key_name in
that order. The signer must be the original C01 dedicated vault. Reviewer key,
Satchel keyring and Satchel unlock paths are fixed to the role's existing state.
No placeholder configuration or credentials ship with this command.

Prepare writes only the canonical unsigned request to standard output:

    wolo-c01-admission prepare /absolute/protected/admission.json

The owner verifies the request in the approved local macOS Terminal, then
signs the exact zero-funds scope using the separately versioned
scripts/c01_owner_startup_signature_v1.swift. The request expires in five
minutes. Transfer only the signed permit to the protected permit_file path.
It must be readable by its role and absent or replaced with exact operator
approval. The original adopted C08 policy is required independently.

    wolo-c01-admission admit /absolute/protected/admission.json

Admit consumes and fsyncs a unique nonce before opening the key, then validates
a fixed-domain possession proof. The proof's hash is exposed, not its
signature or any key bytes. Revoked, replayed, wrong-role, altered-config,
missing-key and expired attempts fail closed. Refusal after nonce consumption
requires a new owner request. The receipt has no funding authority.
