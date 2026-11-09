"""Extract only pg_dump SQL statements within pg_dump's Type: ACL sections."""
import sys
in_acl = False
count = 0
print("BEGIN;")
for line in sys.stdin:
    if line.startswith("-- Name: "):
        in_acl = "; Type: ACL;" in line
        continue
    if not in_acl:
        continue
    if line.startswith(("GRANT ", "REVOKE ")):
        stmt = line.strip()
        if not stmt.endswith(";") or "\x00" in stmt:
            raise SystemExit("HOLD_PGDUMP_MULTILINE_ACL_UNSUPPORTED")
        print(stmt)
        count += 1
if count < 10 or count > 2000:
    raise SystemExit(f"HOLD_UNEXPECTED_ACL_STATEMENT_COUNT:{count}")
print("COMMIT;")
print(f"C07_ACL_EXACT_SOURCE_STATEMENTS={count}", file=sys.stderr)
