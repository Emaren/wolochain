package satchelservice

// Independent pre-bet Watcher receipt issuance, WITHOUT custody, bank,
// payout, Wolo RPC, REST admission, or any financial approval authority.
// All source interfaces must be implemented from independently provisioned
// original Watcher/game-start records, NOT HTTP parameters or the HD app DB.
// A Go signature alone is not proof the operator has deployed those sources.
import (
 "bytes"
 "context"
 "crypto/ed25519"
 "crypto/sha256"
 "encoding/base64"
 "encoding/hex"
 "encoding/json"
 "os"
 "sync"
 "time"

 bolt "go.etcd.io/bbolt"
)

var independentLiveIssues=[]byte("original-live-watcher-issues-v1")

// OriginalLiveCapture is sourced from the original append-only game-start
// recorder. It must NOT be assembled from HD user-supplied market fields.
type OriginalLiveCapture struct {
 Candidate ReviewerWatcherCandidate
 CapturedAt time.Time
 ObservedAt time.Time
 CheckpointSHA256 string
}
type OriginalLiveCaptureSource interface {
 ReadOriginalLiveCapture(context.Context,string)(OriginalLiveCapture,error)
}
type originalLiveIssueEntry struct {
 Fingerprint string `json:"fingerprint"`
 Status string `json:"status"`
 Witness *ReviewerWatcherLiveWitness `json:"witness,omitempty"`
}
type OriginalLiveWitnessReply struct {
 Status string `json:"status"`
 OperationID string `json:"operation_id"`
 Witness *ReviewerWatcherLiveWitness `json:"witness,omitempty"`
}
type OriginalLiveWitnessIssuer struct {
 mu sync.Mutex
 db *bolt.DB
 source OriginalLiveCaptureSource
 checkpoint ReviewerIndependentLiveCheckpointReader
 key ed25519.PrivateKey
 now func()time.Time
}

// This signer key MUST be different from wager/withdrawal authority keys;
// it can only sign the domain-separated game-start receipt. It must have its
// own operator-managed, 0600, symlink-free durable issuance state.
func OpenOriginalLiveWitnessIssuer(path string,
 source OriginalLiveCaptureSource,
 checkpoint ReviewerIndependentLiveCheckpointReader,
 key ed25519.PrivateKey, policy Policy,
)(*OriginalLiveWitnessIssuer,error){
 if path==""||source==nil||checkpoint==nil||
  len(key)!=ed25519.PrivateKeySize||
  len(policy.WagerApprovalKey)!=ed25519.PublicKeySize||
  len(policy.WithdrawalApprovalKey)!=ed25519.PublicKeySize||
  bytes.Equal(key.Public().(ed25519.PublicKey),policy.WagerApprovalKey)||
  bytes.Equal(key.Public().(ed25519.PublicKey),policy.WithdrawalApprovalKey)||
  bytes.Equal(policy.WagerApprovalKey,policy.WithdrawalApprovalKey){
  return nil,ErrReviewerHeld
 }
 if s,e:=os.Lstat(path);e==nil{
  if !s.Mode().IsRegular()||s.Mode().Perm()&0077!=0{return nil,ErrReviewerHeld}
 }else if !os.IsNotExist(e){return nil,ErrReviewerHeld}
 db,e:=bolt.Open(path,0600,&bolt.Options{Timeout:100*time.Millisecond})
 if e!=nil{return nil,ErrReviewerHeld}
 if e=db.Update(func(tx *bolt.Tx)error{
  _,err:=tx.CreateBucketIfNotExists(independentLiveIssues);return err
 });e!=nil{_ = db.Close();return nil,ErrReviewerHeld}
 return &OriginalLiveWitnessIssuer{
  db:db,source:source,checkpoint:checkpoint,
  key:append(ed25519.PrivateKey(nil),key...),now:time.Now,
 },nil
}
func (r *OriginalLiveWitnessIssuer)Close()error{
 if r==nil{return nil}
 r.mu.Lock();defer r.mu.Unlock()
 if r.db==nil{return nil}
 e:=r.db.Close();r.db=nil
 for i:=range r.key{r.key[i]=0}
 return e
}
func (r *OriginalLiveWitnessIssuer)entry(id string)(originalLiveIssueEntry,error){
 var v originalLiveIssueEntry
 e:=r.db.View(func(tx *bolt.Tx)error{
  data:=tx.Bucket(independentLiveIssues).Get([]byte(id))
  if data==nil{return nil}
  if json.Unmarshal(data,&v)!=nil||v.Fingerprint==""||
   (v.Status!="PENDING"&&v.Status!="SIGNED")||
   (v.Status=="SIGNED"&&v.Witness==nil)|| 
   (v.Status=="PENDING"&&v.Witness!=nil){return ErrReviewerHeld}
  return nil
 })
 return v,e
}
func (r *OriginalLiveWitnessIssuer)record(id string,
 value originalLiveIssueEntry,expected string)error{
 return r.db.Update(func(tx *bolt.Tx)error{
  b:=tx.Bucket(independentLiveIssues);previous:=b.Get([]byte(id))
  if expected=="" {
   if previous!=nil{return ErrReviewerHeld}
  }else{
   var old originalLiveIssueEntry
   if previous==nil||json.Unmarshal(previous,&old)!=nil||
    old.Fingerprint!=value.Fingerprint||old.Status!=expected{return ErrReviewerHeld}
  }
  raw,e:=json.Marshal(value);if e!=nil{return ErrReviewerHeld}
  return b.Put([]byte(id),raw)
 })
}
func originalLiveWitnessPending(id string)OriginalLiveWitnessReply{
 return OriginalLiveWitnessReply{Status:"PENDING",OperationID:id}
}
func captureToWitness(original OriginalLiveCapture,now time.Time)(ReviewerWatcherLiveWitness,error){
 c:=original.Candidate
 if now.IsZero()||c.CreatedAt.IsZero()||
  !wagerIDs.MatchString(c.OriginalOperationID)||
  !ownerUIDPattern.MatchString(c.OwnerUID)||
  c.OwnerSteamID==""||c.GameIdentityKey==""||len(c.GameIdentityKey)>255||
  c.MarketID<1||(c.SelectedSide!="left"&&c.SelectedSide!="right")||
  !reviewerHexDigest.MatchString(c.PropositionHash)||
  c.LinkedSession==""||len(c.LinkedSession)>255||
  c.SourceParseIteration<1||
  !reviewerHexDigest.MatchString(c.SourceRosterHash)||
  !reviewerHexDigest.MatchString(original.CheckpointSHA256)||
  original.CapturedAt.IsZero()||original.ObservedAt.IsZero()||
  original.CapturedAt.After(original.ObservedAt)||
  original.ObservedAt.After(now)||
  c.RosterLockedAtMS<0||
  c.RosterLockedAtMS>original.ObservedAt.UnixMilli()||
  c.CreatedAt.After(now)||
  original.CapturedAt.Before(c.CreatedAt.Add(-120*time.Second))||
  original.CapturedAt.After(c.CreatedAt.Add(120*time.Second))||
  original.ObservedAt.After(c.CreatedAt.Add(120*time.Second))||
  now.Sub(original.ObservedAt)>=60*time.Second {
  return ReviewerWatcherLiveWitness{},ErrReviewerHeld
 }
 // A stored source timestamp, NOT the HTTP caller's clock, bounds the TTL.
 expires:=original.ObservedAt.Add(60*time.Second)
 if before:=now.Add(30*time.Second);before.Before(expires){expires=before}
 w:=ReviewerWatcherLiveWitness{
  Version:2,OperationID:c.OriginalOperationID,OwnerUID:c.OwnerUID,
  OwnerSteamID:c.OwnerSteamID,GameIdentityKey:c.GameIdentityKey,
  MarketID:c.MarketID,SelectedSide:c.SelectedSide,
  PropositionHash:c.PropositionHash,LinkedSession:c.LinkedSession,
  SourceParseIteration:c.SourceParseIteration,
  SourceRosterHash:c.SourceRosterHash,
  RosterLockedAtMS:c.RosterLockedAtMS,
  ExecutionCreatedAtMS:c.CreatedAt.UnixMilli(),
  LiveCheckpointSHA256:original.CheckpointSHA256,
  CapturedAtMS:original.CapturedAt.UnixMilli(),
  ObservedAtMS:original.ObservedAt.UnixMilli(),
  ExpiresAtMS:expires.UnixMilli(),
 }
 if w.ExpiresAtMS<=now.UnixMilli(){return ReviewerWatcherLiveWitness{},ErrReviewerHeld}
 return w,nil
}
func independentLiveFingerprint(w ReviewerWatcherLiveWitness)string{
 w.ExpiresAtMS=0;w.Signature=""
 digest:=sha256.Sum256(ReviewerWatcherLiveWitnessMessage(w))
 return hex.EncodeToString(digest[:])
}
// IssueOne always fetches *original* evidence twice, re-hashes bytes twice,
// then records a durable PENDING intent BEFORE ever signing. A crash PENDING
// cannot be recovered by signing again. No HTTP API is exposed here.
func (r *OriginalLiveWitnessIssuer)IssueOne(ctx context.Context,id string)OriginalLiveWitnessReply{
 pending:=originalLiveWitnessPending(id)
 if r==nil||ctx==nil||ctx.Err()!=nil||!wagerIDs.MatchString(id){return pending}
 r.mu.Lock();defer r.mu.Unlock()
 if r.db==nil{return pending}
 ctx,cancel:=context.WithTimeout(ctx,3*time.Second);defer cancel()
 original,e:=r.source.ReadOriginalLiveCapture(ctx,id)
 if e!=nil||ctx.Err()!=nil||original.Candidate.OriginalOperationID!=id{return pending}
 w,e:=captureToWitness(original,r.now())
 if e!=nil{return pending}
 digest,e:=reviewerHashLiveCheckpoint(ctx,r.checkpoint,original.Candidate)
 if e!=nil||digest!=original.CheckpointSHA256||ctx.Err()!=nil{return pending}
 // Source re-read at the final pre-sign boundary; reject changes in the
 // operation, linked market, roster, capture timestamps, or immutable bytes.
 fresh,e:=r.source.ReadOriginalLiveCapture(ctx,id)
 if e!=nil||ctx.Err()!=nil||fresh!=original{return pending}
 check,e:=reviewerHashLiveCheckpoint(ctx,r.checkpoint,fresh.Candidate)
 if e!=nil||check!=digest||ctx.Err()!=nil{return pending}
 w,e=captureToWitness(fresh,r.now())
 if e!=nil{return pending}
 fingerprint:=independentLiveFingerprint(w)
 prior,e:=r.entry(id)
 if e!=nil{return pending}
 if prior.Fingerprint!=""{
  if prior.Status!="SIGNED"||prior.Witness==nil||
   prior.Fingerprint!=fingerprint||prior.Witness.ExpiresAtMS<=r.now().UnixMilli(){
   return pending
  }
  if VerifyReviewerWatcherLiveWitness(fresh.Candidate,*prior.Witness,
   r.key.Public().(ed25519.PublicKey),check,r.now())!=nil{return pending}
  return OriginalLiveWitnessReply{Status:"SIGNED",OperationID:id,Witness:prior.Witness}
 }
 if r.record(id,originalLiveIssueEntry{Fingerprint:fingerprint,Status:"PENDING"},"")!=nil||
  ctx.Err()!=nil{return pending}
 w.Signature=base64.StdEncoding.EncodeToString(
  ed25519.Sign(r.key,ReviewerWatcherLiveWitnessMessage(w)))
 if VerifyReviewerWatcherLiveWitness(fresh.Candidate,w,
  r.key.Public().(ed25519.PublicKey),check,r.now())!=nil||ctx.Err()!=nil{return pending}
 if r.record(id,originalLiveIssueEntry{
  Fingerprint:fingerprint,Status:"SIGNED",Witness:&w,
 },"PENDING")!=nil{return pending}
 return OriginalLiveWitnessReply{Status:"SIGNED",OperationID:id,Witness:&w}
}
