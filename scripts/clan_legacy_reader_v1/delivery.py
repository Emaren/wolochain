"""Review-only bounded protected copy mechanics. No CLI or live admission.
Caller must hold a durable per-file prepared receipt and a separately admitted
native maintenance scope. Never removes originals or incomplete destinations.
"""
import os, re, stat, hashlib
SOURCE=re.compile(r'file:v1:clan-hall/([0-9]{4})/(0[1-9]|1[0-2])/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(?:png|jpg|jpeg|webp))\Z')
EXT={'image/png':'png','image/jpeg':'jpg','image/webp':'webp'}
MAX=10000000
DIR=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW
READ=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK

def need(ok,code):
    if not ok: raise ValueError(code)

def key(s):return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
def shape(s):return (s.st_dev,s.st_ino,s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode))
def free(fd):
    s=os.fstatvfs(fd);return s.f_bavail*s.f_frsize

def copy_qualified(source_fd,target_fd,*,row,identity,digest,protected_ref,source_uid,target_identity,reserve,prepared):
    """Copy a single already qualified file; prepared callback must durably
    journal exact source and destination before creation, or raise. No SQL.
    Caller separately reconciles protected filename collisions with DB refs.
    """
    m=SOURCE.fullmatch(row['storage_ref']);ext=EXT.get(row['mime_type']);size=row['size_bytes']
    need(m is not None and ext is not None and type(size) is int and 0<size<=MAX,'SCOPE')
    need(m[3].rsplit('.',1)[1] in ({'jpg','jpeg'} if ext=='jpg' else {ext}),'SOURCE_MIME')
    need(re.fullmatch('file:v1:clan-[0-9a-f]{32}\\.'+ext,protected_ref) is not None,'TARGET_REF')
    name=protected_ref.removeprefix('file:v1:')
    need(re.fullmatch('[0-9a-f]{64}',digest) is not None,'HASH')
    need(shape(os.fstat(target_fd))==target_identity and target_identity[-1]==0o750,'TARGET_DIRECTORY')
    need(os.fstat(source_fd).st_uid==source_uid and not os.fstat(source_fd).st_mode&0o022,'SOURCE_ROOT')
    need(shape(os.fstat(source_fd))[:2]!=target_identity[:2],'SAME_ROOT')
    need(free(target_fd)>=reserve+size+65536,'RESERVE')
    d1=os.open(m[1],DIR,dir_fd=source_fd)
    try:
        d2=os.open(m[2],DIR,dir_fd=d1)
        try:
            for fd in (d1,d2):
                s=os.fstat(fd);need(s.st_uid==source_uid and not s.st_mode&0o022,'SOURCE_DIRECTORY')
            fd=os.open(m[3],READ,dir_fd=d2)
            with os.fdopen(fd,'rb') as f:
                a=os.fstat(f.fileno());need(stat.S_ISREG(a.st_mode) and a.st_nlink==1 and a.st_uid==source_uid and not a.st_mode&0o022,'SOURCE_FILE')
                need(key(a)==(identity['device'],identity['inode'],size,identity['mtime_ns'],identity['ctime_ns']) and identity['bytes']==size,'SOURCE_IDENTITY')
                raw=f.read(MAX+1);b=os.fstat(f.fileno());c=os.stat(m[3],dir_fd=d2,follow_symlinks=False)
                need(len(raw)==size and key(a)==key(b)==key(c) and hashlib.sha256(raw).hexdigest()==digest,'SOURCE_CONTENT')
        finally:os.close(d2)
    finally:os.close(d1)
    plan={'attachment_id':row['attachment_id'],'message_id':row['message_id'],'original_ref':row['storage_ref'],'protected_ref':protected_ref,'mime':row['mime_type'],'size_bytes':size,'content_sha256':digest,'source_identity':identity}
    prepared(plan)
    need(shape(os.fstat(target_fd))==target_identity and free(target_fd)>=reserve+size+65536,'PREWRITE_DRIFT')
    fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=target_fd)
    with os.fdopen(fd,'wb') as f:
        f.write(raw);f.flush();os.fchown(f.fileno(),target_identity[2],target_identity[3]);os.fchmod(f.fileno(),0o640);os.fsync(f.fileno());a=os.fstat(f.fileno())
    os.fsync(target_fd)
    fd=os.open(name,READ,dir_fd=target_fd)
    with os.fdopen(fd,'rb') as f:
        b=os.fstat(f.fileno());out=f.read(MAX+1);c=os.fstat(f.fileno())
        need(key(a)==key(b)==key(c) and b.st_nlink==1 and stat.S_ISREG(b.st_mode) and (b.st_uid,b.st_gid,stat.S_IMODE(b.st_mode))==(*target_identity[2:4],0o640),'TARGET_IDENTITY')
        need(len(out)==size and hashlib.sha256(out).hexdigest()==digest,'TARGET_CONTENT')
    need(key(os.stat(name,dir_fd=target_fd,follow_symlinks=False))==key(a) and free(target_fd)>=reserve,'POSTWRITE_DRIFT')
    return {**plan,'target_device':a.st_dev,'target_inode':a.st_ino,'status':'PRIVATE_COPY_VERIFIED_NOT_ADMITTED'}
