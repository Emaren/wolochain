# WE1 Library HD projections — purpose-specific maintenance executor (candidate)

SOURCE / REVIEW CANDIDATE, **not root-installed**, not a permit and not an admission to financial activity. This package does NOT apply the database SQL on its own and contains no private signing keys. WoloChain #248's pre-accepted four SQL files are **not modified or restaged**.

## What is new

- `scripts/c03_library_hd_exact_executor_v1.py`: a root-only command supporting `install` and `inverse`, no arbitrary SQL arguments. Requires four already-reviewed source files copied by an approved WE2 root operator into an immutable root-owned and non-writable subtree `/usr/local/libexec/wolo-financial-library-v1/sql`, each file matching hard-coded source digests. Requires a root-owned public P-256 key and a separately signed, short-lived, purpose-bound packet under `/etc/wolo-financial-library-v1`. Runs only `psql` with explicit `postgres` OS uid and local Unix peer to `aoe2hd_db`, using exact bytes piped through stdin; never extends the web role, changes HBA, or touches DE.
- `scripts/c03_library_owner_keychain_v1.swift`: an **independent** macOS login-Keychain software P-256 signing key for `LIBRARY_HD_PROJECTIONS_ONLY`; does **not** reuse the C08 governance policy signer, PRODUCT signer, wallet signer, or custody authority. `enroll` publishes only its public X9.63 bytes to an owner-private file; `sign` refuses any other domain. Does not initiate SQL or funded transactions.
- `tests/test_c03_library_hd_exact_executor_v1.py`: 27 target-specific tests of signature verification, exact action, nonce replay, rejection of financial/database/ACL drift and negative rollback behavior. No production database access.

## Protected admission / ownership

1. WE1 publishes source candidate, tests and exact hashes. The acceptance reviewer verifies root path ownership, seccomp, `postgres` OS peer/HBA, and all four source digests; independent review is **not** a fake second human signature.
2. The existing sole owner enrolls this **new purpose-specific** Mac Keychain public identity and signs a one-use short-window `LIBRARY_HD_PROJECTIONS_ONLY` payload. Root operator WE2 must separately establish the initial public-key trust chain and **install** a verified exact source package through a reviewed protected HEL1 root permit. Do NOT use generic `sudo install`, systemctl, PRODUCT signer or C08 governance signer as substitute. A verified login-Keychain identity is not on its own root authorization.
3. WE2 proves the existing OS user `postgres` (uid 108 observed at 2026-11-19) can authenticate peer to `aoe2hd_db` under the installed HBA and verifies the hardened root-only executor cannot be reached by a less-trusted account. Do not add HBA to fix this; hold if already-installed local peer rule differs.
4. WE2 runs read-only preimage witness and exact candidate install through the newly admitted one-use signed executor, postimage witness and two authenticated actual Emaren/Scribe privacy reads. Capture root-owned audit receipt hash independently. If the postimage fails, the executor attempts the exact inverse, and if rollback fails refuses any replay. A separate new signed inverse permit is required for later rollback.
5. WE2 and WE3 promote the independently requalified Library website through its own source-bound Factory/T10 permission only after the SQL proof. No chain gate close, custody action or funding admission is implied.

## Known limitations of this candidate

- There is currently **no enrolled Library-only root public key, no protected HEL1 installation, no signed one-use packet**, and no authenticated `postgres` peer proof. This is a real implementation candidate, not a live PASS.
- Root-owned O_EXCL receipts are durable against ordinary replay but not cryptographically immutable against an already-compromised root account. Independent hash receipt replication/attestation must be added at protected installation.
- `psql` success + view/ACL checks are not sufficient alone for real user privacy; WE2/WE3 must execute authenticated HTTP acceptance.

Financial status remains C04/C08 CLOSED, seven other gates OPEN, funding DENIED.
