package satchelservice

import (
 "crypto/ed25519"
 "encoding/base64"
 "strings"
 "testing"
 "time"
)

func reviewerWitnessFixture(t *testing.T)(ReviewerWatcherCandidate,ReviewerWatcherWitness,ed25519.PublicKey,ed25519.PrivateKey,time.Time){
 t.Helper()
 market,original,now:=reviewerMarketFixture(t)
 candidate,e:=market.validate(now,original)
 if e!=nil{t.Fatalf("real 17-field watcher source fixture rejected: %v",e)}
 public,private,e:=ed25519.GenerateKey(nil)
 if e!=nil{t.Fatal(e)}
 w:=ReviewerWatcherWitness{
  Version:1,OperationID:candidate.OriginalOperationID,
  OwnerUID:candidate.OwnerUID,OwnerSteamID:candidate.OwnerSteamID,
  GameIdentityKey:candidate.GameIdentityKey,MarketID:candidate.MarketID,
  SelectedSide:candidate.SelectedSide,PropositionHash:candidate.PropositionHash,
  LinkedSession:candidate.LinkedSession,
  SourceParseIteration:candidate.SourceParseIteration,
  SourceRosterHash:candidate.SourceRosterHash,
  RosterLockedAtMS:candidate.RosterLockedAtMS,
  ExecutionCreatedAtMS:candidate.CreatedAt.UnixMilli(),
  RawReplaySHA256:strings.Repeat("d",64),
  ObservedAtMS:now.Add(-20*time.Second).UnixMilli(),
  ExpiresAtMS:now.Add(20*time.Second).UnixMilli(),
 }
 w.Signature=base64.StdEncoding.EncodeToString(ed25519.Sign(private,ReviewerWatcherWitnessMessage(w)))
 return candidate,w,public,private,now
}
func TestReviewerWatcherWitnessValidSignedExactOriginalObservation(t *testing.T){
 candidate,w,pub,_,now:=reviewerWitnessFixture(t)
 if e:=VerifyReviewerWatcherWitness(candidate,w,pub,strings.Repeat("d",64),now);e!=nil{
  t.Fatalf("valid separately signed exact operation witness rejected: %v",e)
 }
 if candidate.OwnerSteamID==""||candidate.SourceRosterHash==""||
  candidate.SourceParseIteration<=0||candidate.RosterLockedAtMS<=0 {
  t.Fatal("signed witness candidate missing real producer provenance")
 }
}
func TestReviewerWatcherWitnessCannotRebindGameOwnerRosterMarketOrMoney(t *testing.T){
 cases:=[]string{
  "operation","owner","steam","game","market","side","proposition",
  "linked_session","parse_iteration","roster_hash","roster_lock",
  "game_created","replay_digest","future_observation","expired",
  "oversized_window","roster_after_execution","zero_version",
 }
 for _,which:=range cases{
  t.Run(which,func(t *testing.T){
   c,w,pub,private,now:=reviewerWitnessFixture(t)
   switch which{
   case "operation":w.OperationID="satchel:ticket:8"
   case "owner":w.OwnerUID="another_owner"
   case "steam":w.OwnerSteamID="76561198000000089"
   case "game":w.GameIdentityKey="platform:other-game"
   case "market":w.MarketID++
   case "side":w.SelectedSide="right"
   case "proposition":w.PropositionHash=strings.Repeat("e",64)
   case "linked_session":w.LinkedSession="other-session"
   case "parse_iteration":w.SourceParseIteration++
   case "roster_hash":w.SourceRosterHash=strings.Repeat("e",64)
   case "roster_lock":w.RosterLockedAtMS++
   case "game_created":w.ExecutionCreatedAtMS++
   case "replay_digest":w.RawReplaySHA256=strings.Repeat("e",64)
   case "future_observation":w.ObservedAtMS=now.Add(time.Second).UnixMilli()
   case "expired":w.ExpiresAtMS=now.UnixMilli()
   case "oversized_window":w.ExpiresAtMS=w.ObservedAtMS+61000
   case "roster_after_execution":w.RosterLockedAtMS=w.ExecutionCreatedAtMS+1
   case "zero_version":w.Version=0
   }
   // Even a new valid Ed25519 signature from the SAME approved test key
   // cannot authorize different immutable market/owner source values.
   w.Signature=base64.StdEncoding.EncodeToString(ed25519.Sign(private,ReviewerWatcherWitnessMessage(w)))
   if e:=VerifyReviewerWatcherWitness(c,w,pub,strings.Repeat("d",64),now);e==nil{
    t.Fatalf("altered independent witness accepted: %s",which)
   }
  })
 }
}
func TestReviewerWatcherWitnessRejectsForgedKeySignatureAndUntrustedRawReplay(t *testing.T){
 c,w,pub,_,now:=reviewerWitnessFixture(t)
 other,_,e:=ed25519.GenerateKey(nil)
 if e!=nil{t.Fatal(e)}
 if VerifyReviewerWatcherWitness(c,w,other,strings.Repeat("d",64),now)==nil{
  t.Fatal("wrong independently provisioned Watcher witness public key accepted")
 }
 if VerifyReviewerWatcherWitness(c,w,nil,strings.Repeat("d",64),now)==nil{
  t.Fatal("missing independent Watcher witness trust root accepted")
 }
 if VerifyReviewerWatcherWitness(c,w,pub,"",now)==nil{
  t.Fatal("absent independently authenticated raw replay bytes accepted")
 }
 if VerifyReviewerWatcherWitness(c,w,pub,strings.Repeat("e",64),now)==nil{
  t.Fatal("caller substituted different raw replay bytes/digest")
 }
 w.Signature=base64.StdEncoding.EncodeToString(make([]byte,64))
 if VerifyReviewerWatcherWitness(c,w,pub,strings.Repeat("d",64),now)==nil{
  t.Fatal("forged Ed25519 watcher witness signature accepted")
 }
}
func TestReviewerWatcherWitnessHasNoAbilityToClearFinancialHold(t *testing.T){
 c,w,pub,_,now:=reviewerWitnessFixture(t)
 if e:=VerifyReviewerWatcherWitness(c,w,pub,strings.Repeat("d",64),now);e!=nil{t.Fatal(e)}
 source:=&ReviewerReadOnlyPGSource{}
 if source.VerifyWatcherMarket(nil,WagerReservation{OperationID:c.OriginalOperationID})!=ErrReviewerHeld{
  t.Fatal("unprovisioned watcher source was turned into spending approval")
 }
 census,e:=source.AuthenticatedFeeCensus(nil,WagerReservation{OperationID:c.OriginalOperationID})
 if e!=ErrReviewerHeld||census.PendingOperationsComplete{
  t.Fatal("watcher signing pretended to prove bank solvency or gas liabilities")
 }
}
