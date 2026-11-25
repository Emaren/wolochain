package satchelservice

import (
 "context"
 "database/sql"
 "errors"
 "strings"
 "testing"
 "time"
)

func samplePGOriginalRow(t *testing.T)ReviewerPGOriginalRow{
 t.Helper()
 raw,col:=sampleHDOrigin(t)
 return ReviewerPGOriginalRow{
  SnapshotJSON:string(raw),OperationID:col.OperationID,
  ReservationID:col.ReservationID,OwnerUserID:col.OwnerUserID,
  ReservationDigest:col.ReservationDigest,
  LedgerRevision:col.LedgerRevision,ConsentDigest:col.ConsentDigest,
  ReservationStatus:"reserved",TicketRequestID:col.OperationID,
  ReservationAmount:"12000000",
  ReservationTicketID:sql.NullInt64{Int64:7,Valid:true},
  ExecutionStatus:"funded_reserved",AttemptCount:1,
  ExecutionReservationID:col.ReservationID,
  GameIdentityKey:"watcher:game-7",
  PropositionHash:strings.Repeat("3",64),
  ExecutionPresetID:9,ExecutionPresetVersion:2,
  ExecutionCreatedAt:time.Now().Add(-time.Minute),
  PlanEnabled:true,PlanSelfOnly:true,PlanVersion:2,
  UserUID:"steam_77",
  UserWallet:sql.NullString{String:testHTTPAddress(t,100),Valid:true},
  TicketID:7,TicketStatus:"awaiting_signature",TicketSource:"auto",
  TicketProvider:sql.NullString{String:"satchel-vault",Valid:true},
  TicketWallet:testHTTPAddress(t,101),TicketTotalWolo:12,
  BalanceReserved:"12000000",
 }
}
func TestReadonlyPGOriginRequiresExactRealHDReservation(t *testing.T){
 row:=samplePGOriginalRow(t)
 approved,err:=row.validate(time.Now(),"2500",testHTTPAddress(t,101),testHTTPAddress(t,102))
 if err!=nil||approved.OperationID!="satchel:ticket:7"||
  approved.ReservationDigest!=row.ReservationDigest||
  approved.FeeUWolo!="2500"||approved.Signature!=""||
  approved.IssuedAt!=0||approved.ExpiresAt!=0{
  t.Fatalf("authentic read-only snapshot failed or self-signed: %+v %v",approved,err)
 }
}
func TestReadonlyPGOriginRefusesChangedDBRowsAndUncertainBroadcasts(t *testing.T){
 for _,name:=range []string{
  "wrong_owner","wrong_uid","wrong_wallet","bad_preset","changed_plan_version",
  "disabled_preset","not_self_only","rebound_game","rebound_proposition",
  "changed_ticket","untrusted_ticket_source","wrong_wallet_provider","wrong_vault",
  "different_stake","low_reserved","missing_ticket","already_attempted",
  "old_game","future_game","has_broadcast","signed_ticket","unknown_hold",
 }{
  t.Run(name,func(t *testing.T){
   row:=samplePGOriginalRow(t)
   switch name {
   case "wrong_owner":row.OwnerUserID=42
   case "wrong_uid":row.UserUID="other-user"
   case "wrong_wallet":row.UserWallet=sql.NullString{String:testHTTPAddress(t,103),Valid:true}
   case "bad_preset":row.ExecutionPresetID=11
   case "changed_plan_version":row.PlanVersion=4
   case "disabled_preset":row.PlanEnabled=false
   case "not_self_only":row.PlanSelfOnly=false
   case "rebound_game":row.GameIdentityKey="other-watcher-game"
   case "rebound_proposition":row.PropositionHash=strings.Repeat("4",64)
   case "changed_ticket":row.TicketID=8
   case "untrusted_ticket_source":row.TicketSource="manual"
   case "wrong_wallet_provider":row.TicketProvider=sql.NullString{String:"keplr",Valid:true}
   case "wrong_vault":row.TicketWallet=testHTTPAddress(t,104)
   case "different_stake":row.ReservationAmount="13000000"
   case "low_reserved":row.BalanceReserved="1000000"
   case "missing_ticket":row.TicketID=0
   case "already_attempted":row.AttemptCount=2
   case "old_game":row.ExecutionCreatedAt=time.Now().Add(-5*time.Minute)
   case "future_game":row.ExecutionCreatedAt=time.Now().Add(time.Minute)
   case "has_broadcast":row.AlreadyBroadcast=true
   case "signed_ticket":row.TicketHash=sql.NullString{String:strings.Repeat("A",64),Valid:true}
   case "unknown_hold":row.ReservationStatus="unknown_hold"
   }
   _,err:=row.validate(time.Now(),"2500",testHTTPAddress(t,101),testHTTPAddress(t,102))
   if !errors.Is(err,ErrReviewerHeld){t.Fatalf("%s approved mutable HD evidence: %v",name,err)}
  })
 }
}
func TestReadonlyPGSourceIsAlwaysHeldUntilAllOtherIndependentEvidenceArrives(t *testing.T){
 row:=samplePGOriginalRow(t)
 source:=ReviewerReadOnlyPGSource{}
 original,err:=row.validate(time.Now(),"2500",testHTTPAddress(t,101),testHTTPAddress(t,102))
 if err!=nil{t.Fatal(err)}
 if !errors.Is(source.VerifyOwnerMandate(context.Background(),original),ErrReviewerHeld)||
  !errors.Is(source.VerifyWatcherMarket(context.Background(),original),ErrReviewerHeld){
  t.Fatal("source pretended to verify an unfunded owner or Watcher game")
 }
 census,err:=source.AuthenticatedFeeCensus(context.Background(),original)
 if !errors.Is(err,ErrReviewerHeld)||census.PendingOperationsComplete{
  t.Fatal("source fabricated a bank/fee census")
 }
 if _,err=source.OriginalHold(context.Background(),"satchel:ticket:7");!errors.Is(err,ErrReviewerHeld){
  t.Fatal("empty read-only source performed financial approval")
 }
}
func TestReadonlyPGRoleCannotBeAppOrPrivilegedOperator(t *testing.T){
 for _,role:=range []string{"", "app", "postgres", "satchel_reviewer_",
  "satchel_reviewer_app;DELETE FROM users", "satchel_reviewer_SUPER"}{
  if reviewerPGRole.MatchString(role){t.Fatalf("unsafe PG role accepted: %s",role)}
 }
 if _,err:=NewReviewerReadOnlyPGSource(nil,"satchel_reviewer_v1","2500",testHTTPAddress(t,101),testHTTPAddress(t,102));!errors.Is(err,ErrReviewerHeld){
  t.Fatal("DB-less reviewer was accepted as ready")
 }
 if reviewerPGOriginalQuery==""||reviewerPGIdentityQuery==""||
  !strings.Contains(reviewerPGIdentityQuery,"has_table_privilege")||
  !strings.Contains(reviewerPGIdentityQuery,"transaction_read_only")||
  !strings.Contains(reviewerPGIdentityQuery,"SELECT session_user, current_user")||
  !strings.Contains(reviewerPGMarketQuery,"WHERE a.operation_id=$1")||
  !strings.Contains(reviewerPGOriginalQuery,"WHERE a.operation_id=$1")||
  !strings.Contains(reviewerPGOriginalQuery,"FROM public.war_satchel_wager_authorizations")||
  !strings.Contains(reviewerPGOriginalQuery,"JOIN public.bet_auto_executions")||
  !strings.Contains(reviewerPGIdentityQuery,"'public.war_satchel_wager_authorizations'")||
  !strings.Contains(reviewerPGIdentityQuery,"'public.war_satchel_auto_spend_mandates'"){
  t.Fatal("independent SQL principal or parameterization gate missing")
 }
}

func TestReviewerPGTrustIdentityRejectsPrivilegedRoleImpersonation(t *testing.T) {
 const expected="satchel_reviewer_v1"
 for _,tc:=range []struct{
  name,login,effective,readonly string
  privileged,canWrite,accept bool
 }{
  {"real dedicated login",expected,expected,"on",false,false,true},
  {"privileged operator SET ROLE","postgres",expected,"on",false,false,false},
  {"other service SET ROLE","aoe2war_app",expected,"on",false,false,false},
  {"wrong active role",expected,"postgres","on",false,false,false},
  {"writable dedicated login",expected,expected,"on",false,true,false},
  {"superuser dedicated login",expected,expected,"on",true,false,false},
  {"writable transaction",expected,expected,"off",false,false,false},
  {"missing login","",expected,"on",false,false,false},
 }{
  t.Run(tc.name,func(t *testing.T){
   if reviewerPGTrustIdentity(tc.login,tc.effective,tc.readonly,tc.privileged,tc.canWrite,expected)!=tc.accept{
    t.Fatal("PostgreSQL reviewer identity allowed unauthorized login or rejected dedicated read-only role")
   }
  })
 }
}
