#!/usr/bin/env bash
# NONFUNDED C06 UNQUIESCED precapture. Never a C06/C07 gate.
set -o pipefail
umask 077
base="/mnt/HC_Volume_105319120/aoe2war-c06-public-age-stage-20261109"
file="$base/aoe2hd_db-UNQUIESCED-20261109.pgcustom.age"
partial="$file.part"
receipt="$base/aoe2hd_db-UNQUIESCED-20261109.receipt.json"
if [ "$(id -u)" != 0 ] || [ "$(stat -c '%a:%U' "$base")" != "700:root" ]; then echo HOLD_OWNER_FS; exit 3; fi
if [ -e "$file" ] || [ -e "$partial" ] || [ -e "$receipt" ]; then echo HOLD_EXISTING_OUTPUT; exit 3; fi
m1="$base/m1-recipient.pub"
intel="$base/intel-recipient.pub"
if [ "$(ssh-keygen -lf "$m1" -E sha256 | awk '{print $2}')" != "SHA256:MfpOL/mXaiHhlPqSaB8ClcVSAUONefzrj2qtPHlsRyU" ] || [ "$(ssh-keygen -lf "$intel" -E sha256 | awk '{print $2}')" != "SHA256:+YyBnbY17VinY0oAjBsILxabobSl95slW+E8R2VPN1c" ]; then
 echo HOLD_C06_PUBLIC_RECIPIENT_DRIFT; exit 3
fi
exec 9>"$base/capture-hd.lock"
if ! flock -n 9; then echo HOLD_CAPTURE_ALREADY_RUNNING; exit 3; fi
start=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
echo "START_HEL1_C06_NONFUNDED_UNQUIESCED_HD_LOCAL_ENCRYPTED $start"
runuser -u postgres -- /usr/bin/nice -n 15 /usr/bin/ionice -c3 /usr/lib/postgresql/16/bin/pg_dump \
 -Fc -Z3 --lock-wait-timeout=5000 -d aoe2hd_db | /usr/bin/age -R "$m1" -R "$intel" -o "$partial"
pipeline_rc=$?
if [ "$pipeline_rc" != 0 ]; then echo "HOLD_PGDUMP_OR_AGE_FAILED code=$pipeline_rc"; exit 3; fi
python3 - "$partial" "$file" "$receipt" "$start" <<'PY'
import os,sys,json,hashlib,stat
from pathlib import Path
from datetime import datetime,timezone
part,final,receipt=map(Path,sys.argv[1:4])
start=sys.argv[4]
if final.exists() or receipt.exists() or part.is_symlink():raise SystemExit('HOLD_FINAL_EXISTS_OR_SYMLINK')
s=part.lstat()
if not stat.S_ISREG(s.st_mode) or stat.S_IMODE(s.st_mode)!=0o600 or s.st_nlink!=1 or s.st_size<128 or s.st_size>12*2**30:
 raise SystemExit('HOLD_ENCRYPTED_FILE_UNSAFE')
h=hashlib.sha256()
with part.open('rb') as f:
 if not f.read(64).startswith(b'age-encryption.org/v1\n'):raise SystemExit('HOLD_NO_AGE_HEADER')
 f.seek(0)
 for b in iter(lambda:f.read(2**20),b''):h.update(b)
with part.open('rb') as f:os.fsync(f.fileno())
os.rename(part,final)
obj={'schema':'wolo.c06.hel1-local-age-hd-unquiesced.v1',
 'start_utc':start,'end_utc':datetime.now(timezone.utc).isoformat(),
 'database':'aoe2hd_db','postgres_dump':'pg_dump16_Fc_Z3_nice15_ionice3',
 'ciphertext_sha256':h.hexdigest(),'ciphertext_bytes':s.st_size,
 'm1_public_fingerprint':'SHA256:MfpOL/mXaiHhlPqSaB8ClcVSAUONefzrj2qtPHlsRyU',
 'intel_public_fingerprint':'SHA256:+YyBnbY17VinY0oAjBsILxabobSl95slW+E8R2VPN1c',
 'source_database_mutated':False,'writer_quiesced':False,
 'cross_database_atomic':False,'offhost_readback_verified':False,
 'c06_closed':False,'c07_closed':False,'financial_release_authorized':False}
content=(json.dumps(obj,indent=2,sort_keys=True)+'\n').encode()
fd=os.open(receipt,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as f:f.write(content);f.flush();os.fsync(f.fileno())
fd=os.open(final.parent,os.O_RDONLY)
try:os.fsync(fd)
finally:os.close(fd)
print('PASS_C06_LOCAL_UNQUIESCED_HD_ENCRYPTED',s.st_size,h.hexdigest())
print('ROOT_PRIVATE_RECEIPT_SHA256',hashlib.sha256(content).hexdigest())
print('HOLD_C06_C07_FORMAL_ACCEPTANCE_NOT_YET')
PY
