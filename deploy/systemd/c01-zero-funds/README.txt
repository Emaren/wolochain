Canonical C01 zero-funds service profile

These drop-in templates are for a reviewed temporary transition on the two
canonical C01 units. They do not change the currently installed held units.
The ordinary financial daemon configurations and startup permissions are
separate from this profile. No TCP listener, ledger, or transfer engine is
started by this profile.

Replace @C01_ADMISSION_BINARY@ with the absolute root-owned executable path
of the exact source-qualified wolo-c01-admission build. Preserve the existing
40-c01-reviewed-executable.conf and both start conditions. Install each
rendered template only as 50-c01-zero-funds.conf for the matching canonical
unit. The canonical config path uses the strict zero-funds admission schema
from cmd/wolo-c01-admission/README.txt. Match the role, its already enrolled
public fingerprint, its copies of the exact adopted C08 policy and public key,
and the exact permit_file named by ConditionPathExists. Use role-owned mode
0600 files with nonshared directories. Preserve each existing private nonce
journal. Never overwrite a role key or restore older nonce state.

Before any canonical change, coordinate and qualify the App protection
contract for the exact pre-start, running, stopped, and rollback states. The
current V20 contract pins the previous never-started state. Stopping a
successfully started unit does not restore its start timestamp. Do not relax
App checks or assume byte-for-byte config rollback alone restores continuity.

Use the exact reviewed binary and proposed config to prepare a fresh
owner-local zero-funds permit for each role. No earlier admission is reusable.
Then verify the fixed local Unix status socket in the real systemd profile
with role-only permissions, no TCP listeners, wrong-role and unknown-route
denial, unexpired replay refusal, and shutdown when the permit is withdrawn
or expires. Never qualify a listener by substituting a financial startup
permit.

Rollback revokes both fresh permits, stops both units, verifies socket and
runtime-directory collection, removes only the two reviewed 50-series
drop-ins and their zero-funds configs, and restores the exact prior on-disk
preimage. Keep spent nonce records. Verify App continuity against the reviewed
post-stop acceptance state and require all 8092–8095 TCP listeners closed.
