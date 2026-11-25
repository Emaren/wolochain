#!/usr/bin/env bash
# C04 encrypted physical historic-claims archive. Nonfunded; no source DB writes.
set -o pipefail
umask 077
base=/mnt/HC_Volume_105319120/aoe2war-c04-legacy-unknowns-sealed-20261109
recipients=/mnt/HC_Volume_105319120/aoe2war-c06-public-age-stage-20261109
m1="$recipients/m1-recipient.pub"
intel="$recipients/intel-recipient.pub"
archive="$base/c04-original-hd-12-financial-tables.pgcustom.age"
part="$archive.part"
receipt="$base/c04-original-hd-12-financial-tables-receipt.json"
if [ "$(id -u)" != 0 ] || [ -e "$base" ] || [ -L "$base" ]; then
 echo HOLD_C04_ROOT_OR_ALREADY_STAGED; exit 3
fi
for unit in wolochain-mainnet-settlement.service wolochain-founder-rewards-settlement.service; do
 if [ "$(systemctl show "$unit" -p LoadState --value)" != masked ] ||
    [ "$(systemctl show "$unit" -p MainPID --value)" != 0 ] ||
    [ "$(readlink "/etc/systemd/system/$unit")" != /dev/null ]; then
  echo HOLD_C04_LEGACY_PAYMENT_NOT_FENCED; exit 3
 fi
done
if ss -lnt | grep -Eq ':(8092|8093|8094|8095)[[:space:]]'; then
 echo HOLD_C04_FINANCIAL_LISTENER_OPEN; exit 3
fi
if [ "$(ssh-keygen -lf "$m1" -E sha256 | awk '{print $2}')" != 'SHA256:MfpOL/mXaiHhlPqSaB8ClcVSAUONefzrj2qtPHlsRyU' ] ||
   [ "$(ssh-keygen -lf "$intel" -E sha256 | awk '{print $2}')" != 'SHA256:+YyBnbY17VinY0oAjBsILxabobSl95slW+E8R2VPN1c' ]; then
 echo HOLD_C04_PUBLIC_RECIPIENT_DRIFT; exit 3
fi
mkdir -m 0700 "$base" || exit 3
start="$(date -u +%FT%TZ)"
echo "START_C04_ENCRYPTED_HISTORICAL_12TABLE_CAPTURE=$start"
runuser -u postgres -- /usr/bin/nice -n 15 /usr/bin/ionice -c3 \
 /usr/lib/postgresql/16/bin/pg_dump -Fc -Z3 --lock-wait-timeout=5000 \
 -d aoe2hd_db \
 --table=public.pending_wolo_claims \
 --table=public.pending_wolo_claims_repair_backup_20260610 \
 --table=public.bet_market_founder_bonuses \
 --table=public.bet_wagers \
 --table=public.bet_markets \
 --table=public.bet_market_wallets \
 --table=public.bet_market_financial_adjustments \
 --table=public.bet_market_integrity_incidents \
 --table=public.wolo_indexed_transfers \
 --table=public.scheduled_match_settlements \
 --table=public.trophy_payouts \
 --table=public.bounty_claims \
 | /usr/bin/age -R "$m1" -R "$intel" -o "$part"
rc=$?
if [ "$rc" != 0 ]; then echo "HOLD_C04_PGDUMP_AGE_FAILED=$rc"; exit 3; fi
python3 - "$part" "$archive" "$receipt" "$start" "$0" <<'PY'
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,stat,sys
part,archive,receipt=map(Path,sys.argv[1:4])
start=sys.argv[4]
source=Path(sys.argv[5])
assert not archive.exists() and not receipt.exists() and not part.is_symlink()
st=part.lstat()
assert st.st_uid==0 and st.st_nlink==1 and stat.S_ISREG(st.st_mode)
assert stat.S_IMODE(st.st_mode)==0o600 and 200<st.st_size<=128*1024*1024
h=hashlib.sha256()
with part.open('rb') as f:
 assert f.read(24).startswith(b'age-encryption.org/v1\n')
 f.seek(0)
 for block in iter(lambda:f.read(1048576),b''):h.update(block)
with part.open('rb') as f:os.fsync(f.fileno())
part.rename(archive)
obj={
 'schema':'wolo.c04.legacy-12table-unknown-quarantine-physical-archive.v1',
 'captured_utc_start':start,'captured_utc_end':datetime.now(timezone.utc).isoformat(),
 'database':'aoe2hd_db','format':'PostgreSQL16 custom compressed age v1',
 'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
 'cipher_sha256':h.hexdigest(),'cipher_bytes':st.st_size,
 'source_tables':12,'no_plaintext_financial_dump_staged':True,
 'legacy_8092_8093_persistently_masked':True,
 'native_8094_8095_closed':True,
 'two_public_recipient_fingerprints_verified':True,
 'all_historical_payment_fates_proven':False,
 'independent_intel_restore_verified':False,
 'historical_claim_rows_status_changed':False,
 'c04_formal_gate_closed':False,'financial_release_authorized':False
}
content=(json.dumps(obj,sort_keys=True,indent=2)+'\n').encode()
fd=os.open(receipt,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as f:f.write(content);f.flush();os.fsync(f.fileno())
fd=os.open(part.parent,os.O_RDONLY)
try:os.fsync(fd)
finally:os.close(fd)
print('PASS_C04_ENCRYPTED_HISTORICAL_SOURCE_ARCHIVE',st.st_size,h.hexdigest())
print('PASS_C04_CAPTURE_RECEIPT_SHA256',hashlib.sha256(content).hexdigest())
print('HOLD_C04_INTEL_OFFHOST_RESTORE_PENDING')
PY
