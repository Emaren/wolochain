package satchelservice

import (
 "bytes"
 "context"
 "crypto/ed25519"
 "crypto/sha256"
 "encoding/base64"
 "encoding/hex"
 "errors"
 "io"
 "testing"
 "time"
 "database/sql"
)

type testSignedReceiptSource struct{
 original ReviewerWatcherWitness
 err error
 calls int
}
func (r *testSignedReceiptSource) FetchOriginalWitness(ctx context.Context,id string)(ReviewerWatcherWitness,error){
 r.calls++
 if r.err!=nil||ctx.Err()!=nil{return ReviewerWatcherWitness{},ErrReviewerHeld}
 if id!=r.original.OperationID{return ReviewerWatcherWitness{},ErrReviewerHeld}
 return r.original,nil
}
type testReplayBytes struct{
 data []byte
 err error
 calls int
}
func (r *testReplayBytes) OpenAuthenticatedReplay(ctx context.Context,c ReviewerWatcherCandidate)(io.ReadCloser,error){
 r.calls++
 if r.err!=nil||ctx.Err()!=nil||c.GameIdentityKey==""{return nil,ErrReviewerHeld}
 return io.NopCloser(bytes.NewReader(r.data)),nil
}
func reviewerConnectedReplayFixture(t *testing.T)(ReviewerWatcherCandidate,*testSignedReceiptSource,*testReplayBytes,ed25519.PublicKey,ed25519.PrivateKey,time.Time){
 t.Helper()
 candidate,w,pub,key,now:=reviewerWitnessFixture(t)
 raw:=[]byte("independently archived original AoE2 HD replay bytes - test only")
 hash:=sha256.Sum256(raw)
 w.RawReplaySHA256=hex.EncodeToString(hash[:])
 w.Signature=base64.StdEncoding.EncodeToString(ed25519.Sign(key,ReviewerWatcherWitnessMessage(w)))
 return candidate,&testSignedReceiptSource{original:w},&testReplayBytes{data:raw},pub,key,now
}
func TestReviewerIndependentReplayActuallyHashesBytesAndChecksPinnedSigner(t *testing.T){
 candidate,witness,replay,pub,_,now:=reviewerConnectedReplayFixture(t)
 if err:=VerifyIndependentReviewerWatcher(t.Context(),candidate,witness,replay,pub,now);err!=nil{
  t.Fatalf("independent raw replay + exact signed source rejected: %v",err)
 }
 if witness.calls!=1||replay.calls!=1{t.Fatal("did not read BOTH independent sources")}
}
func TestReviewerIndependentReplayDeniesSignerReplayAndMarketSpoofing(t *testing.T){
 for _,which:=range []string{
  "forged_witness","changed_raw_bytes","wrong_key","other_operation",
  "changed_market","changed_roster","expired_signature","empty_replay",
  "missing_witness","missing_replay","unreadable_witness","unreadable_replay",
  "canceled","oversized","missing_public_key",
 }{
  t.Run(which,func(t *testing.T){
   candidate,witness,replay,pub,_,now:=reviewerConnectedReplayFixture(t)
   ctx:=t.Context()
   var witnessReader ReviewerSignedWatcherReceiptReader = witness
   var replayReader ReviewerOriginalReplayReader = replay
   switch which{
   case "forged_witness":witness.original.Signature=base64.StdEncoding.EncodeToString(make([]byte,64))
   case "changed_raw_bytes":replay.data=[]byte("forged independent replay bytes")
   case "wrong_key":pub=ed25519.PublicKey(make([]byte,ed25519.PublicKeySize))
   case "other_operation":witness.original.OperationID="satchel:ticket:999"
   case "changed_market":candidate.MarketID++
   case "changed_roster":candidate.SourceRosterHash="wrong"
   case "expired_signature":now=now.Add(90*time.Second)
   case "empty_replay":replay.data=nil
   case "missing_witness":witnessReader=nil
   case "missing_replay":replayReader=nil
   case "unreadable_witness":witness.err=errors.New("archive offline")
   case "unreadable_replay":replay.err=errors.New("archive offline")
   case "canceled":var cancel context.CancelFunc;ctx,cancel=context.WithCancel(ctx);cancel()
   case "oversized":replay.data=make([]byte,reviewerMaxRawReplayBytes+1)
   case "missing_public_key":pub=nil
   }
   if err:=VerifyIndependentReviewerWatcher(ctx,candidate,witnessReader,replayReader,pub,now);!errors.Is(err,ErrReviewerHeld){
    t.Fatalf("%s bypassed independent source refusal: %v",which,err)
   }
  })
 }
}
type testCloseErrorReader struct{io.Reader}
func (r testCloseErrorReader)Close()error{return errors.New("replay_archive_verification_failed")}
type testCloseErrorArchive struct{data []byte}
func (r testCloseErrorArchive)OpenAuthenticatedReplay(_ context.Context,_ ReviewerWatcherCandidate)(io.ReadCloser,error){
 return testCloseErrorReader{bytes.NewReader(r.data)},nil
}
func TestReviewerIndependentReplayRequiresSourceFinalization(t *testing.T){
 c,w,raw,pub,_,now:=reviewerConnectedReplayFixture(t)
 closeFailure:=testCloseErrorArchive{data:raw.data}
 if err:=VerifyIndependentReviewerWatcher(t.Context(),c,w,closeFailure,pub,now);!errors.Is(err,ErrReviewerHeld){
  t.Fatal("unfinalized replay source incorrectly accepted")
 }
}
func TestReviewerIndependentReplayBridgeCannotAuthorizeMoney(t *testing.T){
 c,w,raw,pub,_,now:=reviewerConnectedReplayFixture(t)
 if VerifyIndependentReviewerWatcher(t.Context(),c,w,raw,pub,now)!=nil{
  t.Fatal("unit proof fixture should be valid")
 }
 db:=&sql.DB{}
 pg,e:=NewReviewerReadOnlyPGSource(db,"satchel_reviewer_v1","1",
  testHTTPAddress(t,101),testHTTPAddress(t,102))
 if e!=nil{t.Fatal(e)}
 bridge,e:=NewReviewerIndependentWatcherSource(pg,w,raw,pub)
 if e!=nil{t.Fatal(e)}
 census,e:=bridge.AuthenticatedFeeCensus(t.Context(),WagerReservation{OperationID:c.OriginalOperationID})
 if !errors.Is(e,ErrReviewerHeld)||census.PendingOperationsComplete{
  t.Fatal("Watcher proof was mistaken for a verified bank or liability inventory")
 }
 if _,e=NewReviewerIndependentWatcherSource(pg,nil,raw,pub);!errors.Is(e,ErrReviewerHeld){
  t.Fatal("missing independent receipt provider admitted")
 }
 if _,e=NewReviewerIndependentWatcherSource(pg,w,nil,pub);!errors.Is(e,ErrReviewerHeld){
  t.Fatal("missing independently authenticated raw replay provider admitted")
 }
 if _,e=NewReviewerIndependentWatcherSource(nil,w,raw,pub);!errors.Is(e,ErrReviewerHeld){
  t.Fatal("missing original read-only SQL source admitted")
 }
}
