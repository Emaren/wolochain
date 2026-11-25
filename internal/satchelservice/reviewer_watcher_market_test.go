package satchelservice

import (
 "database/sql"
 "encoding/json"
 "errors"
 "strings"
 "testing"
 "time"
)

func reviewerMarketFixture(t *testing.T)(ReviewerPGMarketRow,ReviewerHDOriginResult,time.Time){
 t.Helper()
 now:=time.Date(2026,10,19,22,0,0,0,time.UTC)
 orig:=ReviewerHDOriginResult{
  OperationID:"satchel:ticket:7",OwnerUID:"steam_77",
  GameIdentityKey:"watcher:game-7",PropositionHash:strings.Repeat("3",64),
  Legs:[]ReviewerHDLeg{{ID:71,MarketID:74,AmountWolo:12,Side:"left",
   PropositionHash:strings.Repeat("3",64)}},
 }
 evidence:=map[string]any{
  "mode":"shadow","exactSteamRosterMatch":true,
  "exactUploaderUidMatch":true,"marketIntegrityStatus":"verified",
  "ownerUid":orig.OwnerUID,"propositionHash":orig.PropositionHash,
  "canonicalSessionKey":orig.GameIdentityKey,
  "teamResolutionStatus":"resolved","teamConfidence":"high",
  "winnerMarketId":int64(74),"desyncMarketId":nil,
  "linkedSessionKey":"watcher-session-7",
  "ownerSteamId":"76561198000000077",
  "sourceParseIteration":int64(2),
  "sourceRosterHash":strings.Repeat("a",64),
  "teamResolutionProvenance":"watcher",
  "rosterLockedAt":now.Add(-110*time.Second).Format("2006-01-02T15:04:05.000Z"),
 }
 raw,_:=json.Marshal(evidence)
 signed:=now.Add(-3*time.Minute)
 row:=ReviewerPGMarketRow{
  SourceEvidence:sql.NullString{Valid:true,String:string(raw)},
  ExecutionStatus:"funded_reserved",ExecutionCreated:now.Add(-90*time.Second),
  ExecutionGameKey:orig.GameIdentityKey,WinnerMarketID:74,
  SelectedSide:sql.NullString{Valid:true,String:"left"},
  ExecutionProposition:orig.PropositionHash,
  MarketStatus:"live",MarketIntegrity:"verified",
  MarketType:"winner",MarketProposition:sql.NullString{Valid:true,String:orig.PropositionHash},
  LinkedSession:sql.NullString{Valid:true,String:"watcher-session-7"},
  MarketCreated:now.Add(-2*time.Minute),
  OwnerSignedAt:sql.NullTime{Valid:true,Time:signed},
  TeamResolutionStatus:sql.NullString{Valid:true,String:"resolved"},
  TeamConfidence:sql.NullString{Valid:true,String:"high"},
  TeamResolutionProvenance:sql.NullString{Valid:true,String:"watcher"},
  SourceParseIteration:sql.NullInt64{Valid:true,Int64:2},
  SourceRosterHash:sql.NullString{Valid:true,String:strings.Repeat("a",64)},
  RosterLockedAt:sql.NullTime{Valid:true,Time:now.Add(-110*time.Second)},
  FirstStakeAcceptedAt:sql.NullTime{Valid:true,Time:now.Add(-110*time.Second)},
  BettingLockedAt:sql.NullTime{Valid:true,Time:now.Add(-110*time.Second)},
  OwnerSteamID:sql.NullString{Valid:true,String:"76561198000000077"},
 }
 row.MarketCreated=now.Add(-2*time.Minute+time.Second*10)
 // A market must be created at or before the submitted outbox execution.
 row.ExecutionCreated=now.Add(-90*time.Second)
 row.MarketCreated=now.Add(-100*time.Second)
 return row,orig,now
}
func TestReviewerWatcherMarketCurrentCanonicalOwnerGameBounded(t *testing.T){
 x,o,now:=reviewerMarketFixture(t)
 result,e:=x.validate(now,o)
 if e!=nil||result.OriginalOperationID!=o.OperationID||
  result.SelectedSide!="left"||result.MarketID!=74{
  t.Fatalf("original verified in-DB market evidence rejected: %+v %v",result,e)
 }
}
func TestReviewerWatcherMarketRejectsAllInvalidSourceAndOutcomeCases(t *testing.T){
 scenarios:=[]string{"wrong_owner","rebound_game","rebound_proposition","wrong_side",
  "market_id","not_live","unverified","wrong_type","scheduled_market",
  "no_linked_session","settled","voided","refunded","winner_known",
  "late_game_stats","linked_game_stats","old_game","market_after_execution",
  "market_before_consent","future_execution","cutoff","phase_before_open",
  "source_absent","shadow_absent","wrong_uid","roster_unverified",
  "uploader_unverified","wrong_original_hash","extra_source_flag",
  "wrong_winner_market","wrong_steam_id","altered_roster_hash",
  "altered_parse_iteration","missing_roster_lock","unresolved_team",
  "mismatched_first_stake_lock","lock_later_than_execution","first_stake_lock_before_owner"}
 for _,scenario:=range scenarios{
  t.Run(scenario,func(t *testing.T){
   row,orig,now:=reviewerMarketFixture(t)
   switch scenario{
   case "wrong_owner":orig.OwnerUID="other"
   case "rebound_game":row.ExecutionGameKey="some-other-session"
   case "rebound_proposition":row.ExecutionProposition=strings.Repeat("4",64)
   case "wrong_side":row.SelectedSide=sql.NullString{Valid:true,String:"right"}
   case "market_id":row.WinnerMarketID=75
   case "not_live":row.MarketStatus="closed"
   case "unverified":row.MarketIntegrity="legacy_unverified"
   case "wrong_type":row.MarketType="desync"
   case "scheduled_market":row.ScheduledMatchID=sql.NullInt64{Valid:true,Int64:1}
   case "no_linked_session":row.LinkedSession=sql.NullString{}
   case "settled":row.SettledAt=sql.NullTime{Valid:true,Time:now}
   case "voided":row.VoidedAt=sql.NullTime{Valid:true,Time:now}
   case "refunded":row.RefundStatus=sql.NullString{Valid:true,String:"refunded"}
   case "winner_known":row.WinnerSide=sql.NullString{Valid:true,String:"left"}
   case "late_game_stats":row.LateFinalGameStats=sql.NullInt64{Valid:true,Int64:1}
   case "linked_game_stats":row.LinkedGameStats=sql.NullInt64{Valid:true,Int64:1}
   case "old_game":row.ExecutionCreated=now.Add(-5*time.Minute)
   case "market_after_execution":row.MarketCreated=now.Add(-20*time.Second)
   case "market_before_consent":row.MarketCreated=now.Add(-4*time.Minute)
   case "future_execution":row.ExecutionCreated=now.Add(time.Second)
   case "cutoff":row.CloseAt=sql.NullTime{Valid:true,Time:now}
   case "phase_before_open":row.PhaseOpensAt=sql.NullTime{Valid:true,Time:now.Add(time.Second)}
   case "source_absent":row.SourceEvidence=sql.NullString{}
   case "shadow_absent":row.SourceEvidence.String=strings.Replace(row.SourceEvidence.String,`"shadow"`,`"manual"`,1)
   case "wrong_uid":row.SourceEvidence.String=strings.Replace(row.SourceEvidence.String,`"steam_77"`,`"steam_42"`,1)
   case "roster_unverified":row.SourceEvidence.String=strings.Replace(row.SourceEvidence.String,`"exactSteamRosterMatch":true`,`"exactSteamRosterMatch":false`,1)
   case "uploader_unverified":row.SourceEvidence.String=strings.Replace(row.SourceEvidence.String,`"exactUploaderUidMatch":true`,`"exactUploaderUidMatch":false`,1)
   case "wrong_original_hash":row.SourceEvidence.String=strings.Replace(row.SourceEvidence.String,strings.Repeat("3",64),strings.Repeat("4",64),1)
   case "extra_source_flag":row.SourceEvidence.String=strings.Replace(row.SourceEvidence.String,`"mode":"shadow"`,`"mode":"shadow","financialApproved":true`,1)
   case "wrong_winner_market":row.SourceEvidence.String=strings.Replace(row.SourceEvidence.String,`"winnerMarketId":74`,`"winnerMarketId":75`,1)
   case "wrong_steam_id":row.SourceEvidence.String=strings.Replace(row.SourceEvidence.String,`"ownerSteamId":"76561198000000077"`,`"ownerSteamId":"other"`,1)
   case "altered_roster_hash":row.SourceEvidence.String=strings.Replace(row.SourceEvidence.String,strings.Repeat("a",64),strings.Repeat("b",64),1)
   case "altered_parse_iteration":row.SourceEvidence.String=strings.Replace(row.SourceEvidence.String,`"sourceParseIteration":2`,`"sourceParseIteration":3`,1)
   case "missing_roster_lock":row.RosterLockedAt=sql.NullTime{}
   case "mismatched_first_stake_lock":row.FirstStakeAcceptedAt.Time=row.FirstStakeAcceptedAt.Time.Add(time.Second)
   case "lock_later_than_execution":row.RosterLockedAt.Time=row.ExecutionCreated.Add(time.Second)
   case "first_stake_lock_before_owner":
    row.FirstStakeAcceptedAt.Time=row.OwnerSignedAt.Time.Add(-time.Second)
    row.RosterLockedAt.Time=row.FirstStakeAcceptedAt.Time
   case "unresolved_team":row.TeamResolutionStatus=sql.NullString{Valid:true,String:"unresolved"}
   }
   if _,e:=row.validate(now,orig);!errors.Is(e,ErrReviewerHeld){
    t.Fatalf("%s unsafe Watcher row passed as independently bounded: %v",scenario,e)
   }
  })
 }
}
func TestReviewerWatcherMarketDoesNotGrantApprovalWhenSourceSelfReportsVerified(t *testing.T){
 row,orig,now:=reviewerMarketFixture(t)
 proof,e:=row.validate(now,orig)
 if e!=nil{t.Fatal(e)}
 if proof.OriginalOperationID==""||proof.LinkedSession==""{t.Fatal("missing observation")}
 // The reviewer still returns ErrReviewerHeld for this DB-only observation.
 source:=&ReviewerReadOnlyPGSource{}
 if !errors.Is(source.VerifyWatcherMarket(nil,WagerReservation{OperationID:orig.OperationID}),ErrReviewerHeld){
  t.Fatal("database flags mistaken for real Watcher attestation")
 }
 if !strings.Contains(reviewerPGMarketQuery,"JOIN public.bet_markets m")||
  !strings.Contains(reviewerPGMarketQuery,"WHERE a.operation_id=$1"){
  t.Fatal("independent market query not bound to original HD operation")
 }
}

func reviewerUnstakedLiveMarket(t *testing.T)(ReviewerPGMarketRow,ReviewerHDOriginResult,time.Time){
 t.Helper()
 row,orig,now:=reviewerMarketFixture(t)
 // Real first-stake admission is the FIRST writer of these three values.
 // The shadow preview materializes an explicitly null rosterLockedAt.
 row.RosterLockedAt=sql.NullTime{}
 row.FirstStakeAcceptedAt=sql.NullTime{}
 row.BettingLockedAt=sql.NullTime{}
 record:=map[string]any{}
 if e:=json.Unmarshal([]byte(row.SourceEvidence.String),&record);e!=nil{t.Fatal(e)}
 record["rosterLockedAt"]=nil
 encoded,e:=json.Marshal(record)
 if e!=nil{t.Fatal(e)}
 row.SourceEvidence=sql.NullString{Valid:true,String:string(encoded)}
 return row,orig,now
}
func TestReviewerBeforeFirstAutoBetDoesNotRequireItsOwnFutureStakeLock(t *testing.T){
 row,orig,now:=reviewerUnstakedLiveMarket(t)
 c,e:=row.validate(now,orig)
 if e!=nil||c.RosterLockedAtMS!=0||
  c.SourceRosterHash!=strings.Repeat("a",64)||c.MarketID!=74{
  t.Fatalf("first-ever auto bet circular lock deadlock: %+v %v",c,e)
 }
}
func TestReviewerPreFirstStakeMustNotAcceptPreexistingMarketOrRosterLock(t *testing.T){
 for _,scenario:=range []string{"roster_lock_only","betting_lock_only","evidence_fake_lock"}{
  t.Run(scenario,func(t *testing.T){
   row,orig,now:=reviewerUnstakedLiveMarket(t)
   switch scenario{
   case "roster_lock_only":row.RosterLockedAt=sql.NullTime{Valid:true,Time:now}
   case "betting_lock_only":row.BettingLockedAt=sql.NullTime{Valid:true,Time:now}
   case "evidence_fake_lock":
    row.SourceEvidence.String=strings.Replace(row.SourceEvidence.String,
     `"rosterLockedAt":null`,`"rosterLockedAt":"2026-10-19T22:00:00.000Z"`,1)
   }
   if _,e:=row.validate(now,orig);!errors.Is(e,ErrReviewerHeld){
    t.Fatalf("unstaked market accepted inconsistent lock %s",scenario)
   }
  })
 }
}

func reviewerPostShadowFirstStake(t *testing.T)(ReviewerPGMarketRow,ReviewerHDOriginResult,time.Time){
 t.Helper()
 row,orig,now:=reviewerUnstakedLiveMarket(t)
 // A different player's first wager is recorded AFTER this owner's
 // original shadow auto-bet execution. The original JSON MUST stay NULL.
 first:=now.Add(-60*time.Second)
 row.FirstStakeAcceptedAt=sql.NullTime{Valid:true,Time:first}
 row.RosterLockedAt=sql.NullTime{Valid:true,Time:first}
 row.BettingLockedAt=sql.NullTime{Valid:true,Time:first}
 return row,orig,now
}
func TestReviewerSecondAutoBettorMayFollowRealOtherPlayersFirstStake(t *testing.T){
 row,orig,now:=reviewerPostShadowFirstStake(t)
 result,e:=row.validate(now,orig)
 if e!=nil||result.RosterLockedAtMS!=row.FirstStakeAcceptedAt.Time.UnixMilli()||
  !strings.Contains(row.SourceEvidence.String,`"rosterLockedAt":null`){
  t.Fatalf("legitimate first-stake transition rejected or rewrote frozen source: %+v %v",result,e)
 }
}
func TestReviewerRejectsUnbackedPostShadowRosterLockMutations(t *testing.T){
 for _,which:=range []string{
  "first_stake_missing","first_stake_timestamp_changed","future_lock",
  "faked_original_locked_before_transition","changed_market_roster",
  "missing_betting_lock_transition",
 }{
  t.Run(which,func(t *testing.T){
   row,orig,now:=reviewerPostShadowFirstStake(t)
   switch which{
   case "first_stake_missing":row.FirstStakeAcceptedAt=sql.NullTime{}
   case "first_stake_timestamp_changed":row.FirstStakeAcceptedAt.Time=row.FirstStakeAcceptedAt.Time.Add(time.Second)
   case "future_lock":
    future:=now.Add(time.Second)
    row.RosterLockedAt.Time=future
    row.FirstStakeAcceptedAt.Time=future
   case "faked_original_locked_before_transition":
    source:=map[string]any{}
    if e:=json.Unmarshal([]byte(row.SourceEvidence.String),&source);e!=nil{t.Fatal(e)}
    source["rosterLockedAt"]=row.RosterLockedAt.Time.UTC().Format("2006-01-02T15:04:05.000Z")
    data,e:=json.Marshal(source);if e!=nil{t.Fatal(e)}
    row.SourceEvidence.String=string(data)
   case "changed_market_roster":row.SourceRosterHash=sql.NullString{Valid:true,String:strings.Repeat("f",64)}
   case "missing_betting_lock_transition":row.BettingLockedAt=sql.NullTime{}
   }
   if _,e:=row.validate(now,orig);!errors.Is(e,ErrReviewerHeld){
    t.Fatalf("%s bypassed immutable shadow-to-first-stake transition check: %v",which,e)
   }
  })
 }
}
