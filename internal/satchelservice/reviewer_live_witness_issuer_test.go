package satchelservice

import (
 "context"
 "crypto/ed25519"
 "crypto/sha256"
 "encoding/hex"
 "errors"
 "os"
 "path/filepath"
 "strings"
 "testing"
 "time"
)

type originalCaptureTestSource struct{
 original OriginalLiveCapture
 calls int
 fail bool
 mutateSecond bool
}
func (s *originalCaptureTestSource)ReadOriginalLiveCapture(
 ctx context.Context,id string)(OriginalLiveCapture,error){
 s.calls++
 if s.fail||ctx.Err()!=nil||id!=s.original.Candidate.OriginalOperationID{
  return OriginalLiveCapture{},errors.New("missing-original-live-capture")
 }
 x:=s.original
 if s.mutateSecond&&s.calls==2{
  x.Candidate.SourceRosterHash=strings.Repeat("b",64)
 }
 return x,nil
}
func newOriginalLiveWitnessTestIssuer(t *testing.T)(
 *OriginalLiveWitnessIssuer,*originalCaptureTestSource,*testLiveCheckpointBytes,
 ReviewerWatcherCandidate,ed25519.PublicKey,time.Time){
 t.Helper()
 c,_,checkpoint,_,_,now:=reviewerLiveCheckpointFixture(t)
 digest:=sha256.Sum256(checkpoint.data)
 source:=&originalCaptureTestSource{original:OriginalLiveCapture{
  Candidate:c,
  CapturedAt:now.Add(-25*time.Second),
  ObservedAt:now.Add(-20*time.Second),
  CheckpointSHA256:hex.EncodeToString(digest[:]),
 }}
 pub,key,e:=ed25519.GenerateKey(nil);if e!=nil{t.Fatal(e)}
 wager,_,e:=ed25519.GenerateKey(nil);if e!=nil{t.Fatal(e)}
 withdrawal,_,e:=ed25519.GenerateKey(nil);if e!=nil{t.Fatal(e)}
 policy:=Policy{WagerApprovalKey:wager,WithdrawalApprovalKey:withdrawal}
 issuer,e:=OpenOriginalLiveWitnessIssuer(
  filepath.Join(t.TempDir(),"independent-live.db"),source,checkpoint,key,policy)
 if e!=nil{t.Fatalf("independent witness issuer cannot open: %v",e)}
 t.Cleanup(func(){_ = issuer.Close()})
 issuer.now=func()time.Time{return now}
 return issuer,source,checkpoint,c,pub,now
}
func TestIndependentLiveIssuerOneShotAndNoFinancialApproval(t *testing.T){
 issuer,src,bytes,c,pub,now:=newOriginalLiveWitnessTestIssuer(t)
 answer:=issuer.IssueOne(t.Context(),c.OriginalOperationID)
 if answer.Status!="SIGNED"||answer.Witness==nil{
  t.Fatalf("original live source refused: %+v",answer)
 }
 if src.calls!=2||bytes.calls!=2{t.Fatal("issuer did not double-read independent sources")}
 original:=answer.Witness
 if e:=VerifyReviewerWatcherLiveWitness(c,*original,pub,src.original.CheckpointSHA256,now);e!=nil{
  t.Fatal(e)
 }
 if original.ExpiresAtMS>now.Add(30*time.Second).UnixMilli(){
  t.Fatal("source-bound issued TTL exceeds 30s")
 }
 if original.Signature==""{t.Fatal("missing independently signed witness")}
 again:=issuer.IssueOne(t.Context(),c.OriginalOperationID)
 if again.Status!="SIGNED"||again.Witness==nil||
  again.Witness.Signature!=original.Signature||
  again.Witness.ExpiresAtMS!=original.ExpiresAtMS{
  t.Fatal("reissue rotated an original live witness or changed expiry")
 }
 issuer.now=func()time.Time{return now.Add(40*time.Second)}
 expired:=issuer.IssueOne(t.Context(),c.OriginalOperationID)
 if expired.Status!="PENDING"||expired.Witness!=nil{
  t.Fatal("expired original witness was minted again")
 }
}
func TestIndependentLiveIssuerRejectsMutatedSourcesAndCheckpoint(t *testing.T){
 tests:=[]string{
  "wrong_digest","changed_first_capture","changed_second_capture",
  "unreadable_bytes","empty_bytes","unknown_operation","expired_source",
  "future_observation","invalid_steam","wrong_roster_lock",
 }
 for _,which:=range tests{t.Run(which,func(t *testing.T){
  issuer,src,bytes,c,_,now:=newOriginalLiveWitnessTestIssuer(t)
  switch which{
  case "wrong_digest":src.original.CheckpointSHA256=strings.Repeat("e",64)
  case "changed_first_capture":src.original.Candidate.SelectedSide="front"
  case "changed_second_capture":src.mutateSecond=true
  case "unreadable_bytes":bytes.err=errors.New("checkpoint-unavailable")
  case "empty_bytes":bytes.data=nil
  case "unknown_operation":c.OriginalOperationID="satchel:ticket:999999"
  case "expired_source":issuer.now=func()time.Time{return now.Add(65*time.Second)}
  case "future_observation":src.original.ObservedAt=now.Add(time.Second)
  case "invalid_steam":src.original.Candidate.OwnerSteamID=""
  case "wrong_roster_lock":src.original.Candidate.RosterLockedAtMS=now.Add(time.Minute).UnixMilli()
  }
  answer:=issuer.IssueOne(t.Context(),c.OriginalOperationID)
  if answer.Status!="PENDING"||answer.Witness!=nil{
   t.Fatalf("unsafe original signed (%s)",which)
  }
 })}
}
func TestIndependentLiveIssuerPendingCrashFencing(t *testing.T){
 issuer,src,_,c,_,now:=newOriginalLiveWitnessTestIssuer(t)
 w,e:=captureToWitness(src.original,now)
 if e!=nil{t.Fatal(e)}
 fp:=independentLiveFingerprint(w)
 if e=issuer.record(c.OriginalOperationID,originalLiveIssueEntry{
  Status:"PENDING",Fingerprint:fp,
 },"");e!=nil{t.Fatal(e)}
 for i:=0;i<3;i++{
  a:=issuer.IssueOne(t.Context(),c.OriginalOperationID)
  if a.Status!="PENDING"||a.Witness!=nil{
   t.Fatal("crash-fenced original was re-signed")
  }
 }
}
func TestIndependentLiveIssuerNeverReusesFinancialSigningKey(t *testing.T){
 c,_,bytes,_,_,now:=reviewerLiveCheckpointFixture(t)
 hash:=sha256.Sum256(bytes.data)
 source:=&originalCaptureTestSource{original:OriginalLiveCapture{
  Candidate:c,CapturedAt:now.Add(-25*time.Second),
  ObservedAt:now.Add(-20*time.Second),CheckpointSHA256:hex.EncodeToString(hash[:]),
 }}
 pub,key,e:=ed25519.GenerateKey(nil);if e!=nil{t.Fatal(e)}
 other,_,e:=ed25519.GenerateKey(nil);if e!=nil{t.Fatal(e)}
 cases:=[]Policy{
  {WagerApprovalKey:pub,WithdrawalApprovalKey:other},
  {WagerApprovalKey:other,WithdrawalApprovalKey:pub},
  {WagerApprovalKey:other,WithdrawalApprovalKey:other},
 }
 for _,policy:=range cases{
  issuer,e:=OpenOriginalLiveWitnessIssuer(
   filepath.Join(t.TempDir(),"unsafe.db"),source,bytes,key,policy)
  if issuer!=nil||!errors.Is(e,ErrReviewerHeld){
   t.Fatal("watcher source key reused financial approval authority")
  }
 }
}
func TestIndependentLiveIssuerRequiresPrivateDurableStateAndRejectsNilContext(t *testing.T){
 issuer,_,_,c,_,_:=newOriginalLiveWitnessTestIssuer(t)
 if answer:=issuer.IssueOne(nil,c.OriginalOperationID);answer.Status!="PENDING"{
  t.Fatal("nil context unexpectedly signed")
 }
 path:=filepath.Join(t.TempDir(),"existing.db")
 if e:=os.WriteFile(path,[]byte("not-a-ledger"),0644);e!=nil{t.Fatal(e)}
 pub,key,e:=ed25519.GenerateKey(nil);if e!=nil{t.Fatal(e)}
 other,_,e:=ed25519.GenerateKey(nil);if e!=nil{t.Fatal(e)}
 signer,e:=OpenOriginalLiveWitnessIssuer(path,&originalCaptureTestSource{},
  &testLiveCheckpointBytes{},key,Policy{WagerApprovalKey:pub,WithdrawalApprovalKey:other})
 if signer!=nil||!errors.Is(e,ErrReviewerHeld){t.Fatal("insecure on-disk issuer accepted")}
 link:=filepath.Join(t.TempDir(),"symlink.db")
 if e:=os.Symlink(path,link);e!=nil{t.Fatal(e)}
 signer,e=OpenOriginalLiveWitnessIssuer(link,&originalCaptureTestSource{},
  &testLiveCheckpointBytes{},key,Policy{WagerApprovalKey:pub,WithdrawalApprovalKey:other})
 if signer!=nil||!errors.Is(e,ErrReviewerHeld){t.Fatal("symlink issuer accepted")}
}
