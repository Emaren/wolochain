package satchelservice

import (
 "bytes"
 "context"
 "crypto/ed25519"
 "crypto/sha256"
 "database/sql"
 "encoding/base64"
 "encoding/hex"
 "errors"
 "io"
 "testing"
 "time"
)

type testSignedLiveSource struct{
 original ReviewerWatcherLiveWitness
 err error
 calls int
}
func (r *testSignedLiveSource)FetchOriginalLiveWitness(ctx context.Context,id string)(ReviewerWatcherLiveWitness,error){
 r.calls++
 if r.err!=nil||ctx.Err()!=nil||id!=r.original.OperationID{
  return ReviewerWatcherLiveWitness{},ErrReviewerHeld
 }
 return r.original,nil
}
type testLiveCheckpointBytes struct{
 data []byte
 err error
 calls int
 delay time.Duration
}
func (r *testLiveCheckpointBytes)OpenAuthenticatedLiveCheckpoint(
 ctx context.Context,c ReviewerWatcherCandidate)(io.ReadCloser,error){
 r.calls++
 if r.delay>0{time.Sleep(r.delay)}
 if r.err!=nil||ctx.Err()!=nil||c.GameIdentityKey==""{
  return nil,ErrReviewerHeld
 }
 return io.NopCloser(bytes.NewReader(r.data)),nil
}
func reviewerLiveCheckpointFixture(t *testing.T)(
 ReviewerWatcherCandidate,*testSignedLiveSource,*testLiveCheckpointBytes,
 ed25519.PublicKey,ed25519.PrivateKey,time.Time){
 t.Helper()
 c,_,pub,key,now:=reviewerWitnessFixture(t)
 checkpoint:=[]byte("frozen partial live AoE2HD game-start Watcher data - synthetic fixture")
 h:=sha256.Sum256(checkpoint)
 w:=ReviewerWatcherLiveWitness{
  Version:2,OperationID:c.OriginalOperationID,OwnerUID:c.OwnerUID,
  OwnerSteamID:c.OwnerSteamID,GameIdentityKey:c.GameIdentityKey,
  MarketID:c.MarketID,SelectedSide:c.SelectedSide,PropositionHash:c.PropositionHash,
  LinkedSession:c.LinkedSession,SourceParseIteration:c.SourceParseIteration,
  SourceRosterHash:c.SourceRosterHash,RosterLockedAtMS:c.RosterLockedAtMS,
  ExecutionCreatedAtMS:c.CreatedAt.UnixMilli(),
  LiveCheckpointSHA256:hex.EncodeToString(h[:]),
  CapturedAtMS:now.Add(-25*time.Second).UnixMilli(),
  ObservedAtMS:now.Add(-20*time.Second).UnixMilli(),
  ExpiresAtMS:now.Add(20*time.Second).UnixMilli(),
 }
 w.Signature=base64.StdEncoding.EncodeToString(
  ed25519.Sign(key,ReviewerWatcherLiveWitnessMessage(w)))
 return c,&testSignedLiveSource{original:w},
  &testLiveCheckpointBytes{data:checkpoint},pub,key,now
}
func TestReviewerPreBetLiveWatcherWitnessHashesRealCheckpointBytes(t *testing.T){
 c,w,checkpoint,pub,_,now:=reviewerLiveCheckpointFixture(t)
 if e:=VerifyIndependentReviewerLiveWatcher(t.Context(),c,w,checkpoint,pub,now);e!=nil{
  t.Fatalf("signed original LIVE snapshot rejected: %v",e)
 }
 if w.calls!=1||checkpoint.calls!=1{
  t.Fatal("pre-bet verifier did not read both independent source contracts")
 }
}
func TestReviewerLiveWatcherRejectsPostGameOrChangedSourceWithoutSpending(t *testing.T){
 cases:=[]string{
  "forged_signature","changed_checkpoint_bytes","wrong_key","other_game",
  "other_market","changed_steam","changed_roster","wrong_owner",
  "late_final_replay","capture_outside_game_start","wrong_live_digest",
  "expired","missing_witness","missing_checkpoint","unreadable_witness",
  "unreadable_checkpoint","empty_checkpoint","oversize","canceled",
  "missing_public_key","other_receipt_protocol","expired_during_checkpoint_read",
 }
 for _,which:=range cases{
  t.Run(which,func(t *testing.T){
   c,w,checkpoint,pub,key,now:=reviewerLiveCheckpointFixture(t)
   ctx:=t.Context()
   var wr ReviewerSignedLiveWatcherReader=w
   var cr ReviewerIndependentLiveCheckpointReader=checkpoint
   switch which{
   case "forged_signature":w.original.Signature=base64.StdEncoding.EncodeToString(make([]byte,64))
   case "changed_checkpoint_bytes":checkpoint.data=[]byte("not the observed game-start checkpoint")
   case "wrong_key":pub=ed25519.PublicKey(make([]byte,ed25519.PublicKeySize))
   case "other_game":w.original.GameIdentityKey="other-game"
   case "other_market":c.MarketID++
   case "changed_steam":c.OwnerSteamID="76561198000000088"
   case "changed_roster":c.SourceRosterHash="wrong-roster-hash"
   case "wrong_owner":w.original.OwnerUID="another_owner"
   case "late_final_replay":
    w.original.CapturedAtMS=w.original.ExecutionCreatedAtMS+180000
    w.original.ObservedAtMS=w.original.CapturedAtMS
    w.original.ExpiresAtMS=w.original.ObservedAtMS+30000
   case "capture_outside_game_start":
    w.original.CapturedAtMS=w.original.ExecutionCreatedAtMS-120001
   case "wrong_live_digest":w.original.LiveCheckpointSHA256=hex.EncodeToString(make([]byte,32))
   case "expired":now=now.Add(90*time.Second)
   case "missing_witness":wr=nil
   case "missing_checkpoint":cr=nil
   case "unreadable_witness":w.err=errors.New("witness offline")
   case "unreadable_checkpoint":checkpoint.err=errors.New("checkpoint offline")
   case "empty_checkpoint":checkpoint.data=nil
   case "oversize":checkpoint.data=make([]byte,reviewerMaxLiveCheckpointBytes+1)
   case "canceled":var cancel context.CancelFunc;ctx,cancel=context.WithCancel(ctx);cancel()
   case "missing_public_key":pub=nil
   case "other_receipt_protocol":w.original.Version=1
   case "expired_during_checkpoint_read":
    w.original.ExpiresAtMS=now.Add(time.Millisecond).UnixMilli()
    checkpoint.delay=25*time.Millisecond
   }
   if which!="forged_signature" && which!="changed_checkpoint_bytes" &&
    which!="wrong_key" && which!="other_market" &&
    which!="changed_steam" && which!="changed_roster" &&
    which!="expired" && which!="missing_witness" &&
    which!="missing_checkpoint" && which!="unreadable_witness" &&
    which!="unreadable_checkpoint" && which!="empty_checkpoint" &&
    which!="oversize" && which!="canceled" && which!="missing_public_key" {
    w.original.Signature=base64.StdEncoding.EncodeToString(
     ed25519.Sign(key,ReviewerWatcherLiveWitnessMessage(w.original)))
   }
   if e:=VerifyIndependentReviewerLiveWatcher(ctx,c,wr,cr,pub,now);!errors.Is(e,ErrReviewerHeld){
    t.Fatalf("%s passed without authenticated pre-bet source: %v",which,e)
   }
  })
 }
}
type testCheckpointCloseError struct{io.Reader}
func (r testCheckpointCloseError)Close()error{return errors.New("checkpoint_archive_not_fully_verified")}
type testCloseFailCheckpoint struct{data []byte}
func (r testCloseFailCheckpoint)OpenAuthenticatedLiveCheckpoint(_ context.Context,_ ReviewerWatcherCandidate)(io.ReadCloser,error){
 return testCheckpointCloseError{bytes.NewReader(r.data)},nil
}
func TestReviewerLiveCheckpointFailsWhenSourceFinalizationFails(t *testing.T){
 c,w,cr,pub,_,now:=reviewerLiveCheckpointFixture(t)
 if e:=VerifyIndependentReviewerLiveWatcher(t.Context(),c,w,testCloseFailCheckpoint{cr.data},pub,now);!errors.Is(e,ErrReviewerHeld){
  t.Fatal("partial or unverifiable early source accepted")
 }
}
func TestReviewerLiveWitnessProofCannotOverrideHardHeldSolvency(t *testing.T){
 c,w,checkpoint,pub,_,now:=reviewerLiveCheckpointFixture(t)
 if e:=VerifyIndependentReviewerLiveWatcher(t.Context(),c,w,checkpoint,pub,now);e!=nil{t.Fatal(e)}
 pg,e:=NewReviewerReadOnlyPGSource(&sql.DB{},"satchel_reviewer_v1","1",
  testHTTPAddress(t,101),testHTTPAddress(t,102))
 if e!=nil{t.Fatal(e)}
 bridge,e:=NewReviewerIndependentWatcherSource(pg,w,checkpoint,pub)
 if e!=nil{t.Fatal(e)}
 census,e:=bridge.AuthenticatedFeeCensus(t.Context(),WagerReservation{OperationID:c.OriginalOperationID})
 if !errors.Is(e,ErrReviewerHeld)||census.PendingOperationsComplete{
  t.Fatal("signed live Watcher event incorrectly created customer bank/fee authority")
 }
 if _,e=NewReviewerIndependentWatcherSource(pg,nil,checkpoint,pub);!errors.Is(e,ErrReviewerHeld){
  t.Fatal("absent independently operated Watcher signer admitted")
 }
 if _,e=NewReviewerIndependentWatcherSource(pg,w,nil,pub);!errors.Is(e,ErrReviewerHeld){
  t.Fatal("absent immutable game-start capture reader admitted")
 }
 if _,e=NewReviewerIndependentWatcherSource(nil,w,checkpoint,pub);!errors.Is(e,ErrReviewerHeld){
  t.Fatal("absent original SQL evidence source admitted")
 }
}

func TestReviewerLiveFirstStakeRequiresSourceRosterButNotFutureStakeLock(t *testing.T){
 market,orig,now:=reviewerUnstakedLiveMarket(t)
 candidate,e:=market.validate(now,orig)
 if e!=nil||candidate.RosterLockedAtMS!=0{t.Fatalf("early original source rejected: %+v %v",candidate,e)}
 _,w,checkpoint,pub,key,_:=reviewerLiveCheckpointFixture(t)
 w.original.RosterLockedAtMS=0
 w.original.CapturedAtMS=now.Add(-100*time.Second).UnixMilli()
 w.original.ObservedAtMS=now.Add(-20*time.Second).UnixMilli()
 w.original.ExpiresAtMS=now.Add(20*time.Second).UnixMilli()
 w.original.Signature=base64.StdEncoding.EncodeToString(
  ed25519.Sign(key,ReviewerWatcherLiveWitnessMessage(w.original)))
 if e:=VerifyIndependentReviewerLiveWatcher(t.Context(),candidate,w,checkpoint,pub,now);e!=nil{
  t.Fatalf("live first-ever bet required its own later roster lock: %v",e)
 }
 // Requiring a nonexistent lock is wrong; accepting an invented lock is
 // equally wrong. The read-only original first-stake status must agree.
 w.original.RosterLockedAtMS=now.Add(-110*time.Second).UnixMilli()
 w.original.Signature=base64.StdEncoding.EncodeToString(
  ed25519.Sign(key,ReviewerWatcherLiveWitnessMessage(w.original)))
 if e:=VerifyIndependentReviewerLiveWatcher(t.Context(),candidate,w,checkpoint,pub,now);!errors.Is(e,ErrReviewerHeld){
  t.Fatal("forged preexisting roster lock bypassed first-stake source")
 }
}
