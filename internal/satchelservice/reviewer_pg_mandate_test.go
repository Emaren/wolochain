package satchelservice

import (
 "database/sql"
 "encoding/json"
 "errors"
 "strings"
 "testing"
 "time"
)
func samplePGMandateRow(t *testing.T)(ReviewerPGMandateRow,ReviewerHDOriginResult){
 t.Helper()
 signed,expected:=sampleReviewerMandate(t)
 raw,_:=json.Marshal(map[string]any{
  "pub_key":map[string]any{"type":signed.PublicKeyType,"value":signed.PublicKeyBase64},
  "signature":signed.SignatureBase64,
 })
 origin:=ReviewerHDOriginResult{
  OperationID:expected.OriginalOperationID,OwnerUID:signed.OwnerUID,
  OwnerWallet:signed.WalletAddress,
  PresetID:signed.PresetID,PresetVersion:signed.PresetVersion,
  ConsentID:"12345678-1234-4123-8123-123456789abc",
  ChallengeText:signed.ChallengeText,
  OwnerSignatureJSON:map[string]any{
   "pub_key":map[string]any{"type":signed.PublicKeyType,"value":signed.PublicKeyBase64},
   "signature":signed.SignatureBase64,
  },
 }
 m:=ReviewerPGMandateRow{
  ConsentID:origin.ConsentID,OwnerUID:signed.OwnerUID,Wallet:signed.WalletAddress,
  PresetID:signed.PresetID,PresetVersion:signed.PresetVersion,
  WinnerStakeWolo:signed.WinnerStakeWolo,
  DesyncStakeWolo:signed.DesyncStakeWolo,DesyncSide:signed.DesyncSide,
  PerGameCapWolo:signed.PerGameCapWolo,DailyCapWolo:signed.DailyCapWolo,
  Nonce:signed.Nonce,IssuedAt:signed.IssuedAt,ChallengeExpiresAt:signed.ChallengeExpiresAt,
  SpendExpiresAt:signed.SpendExpiresAt,
  SignedAt:sql.NullTime{Valid:true,Time:signed.SignedAt},
  UntilOut:signed.UntilOut,GamesRemaining:sql.NullInt64{Valid:true,Int64:*signed.GamesRemaining},
  ChallengeText:signed.ChallengeText,SignatureJSON:string(raw),
  MandateSignedAt:sql.NullTime{Valid:true,Time:signed.SignedAt},
  PlanEnabled:true,PlanSelfOnly:true,CurrentPresetVersion:signed.PresetVersion,
  CurrentUntilOut:signed.UntilOut,
  CurrentGamesRemaining:sql.NullInt64{Valid:true,Int64:*signed.GamesRemaining},
  CurrentWinnerStakeWolo:signed.WinnerStakeWolo,
  CurrentDesyncStakeWolo:signed.DesyncStakeWolo,
  CurrentDesyncSide:signed.DesyncSide,
  CurrentUID:signed.OwnerUID,CurrentWallet:sql.NullString{Valid:true,String:signed.WalletAddress},
 }
 return m,origin
}
func TestReviewerPGMandateAuthenticatesActualOriginalKeplrSignature(t *testing.T){
 row,original:=samplePGMandateRow(t)
 if err:=row.verify(original,row.SignedAt.Time.Add(time.Minute));err!=nil{
  t.Fatalf("independent SQL row's actual original Keplr signature rejected: %v",err)
 }
}
func TestReviewerPGMandateFailsClosedForSignatureRevocationOrChangedPlan(t *testing.T){
 for _,scenario:=range []string{"wrong_signature","changed_consent","changed_wallet","changed_plan",
  "wrong_wallet_owner","changed_spending_limit","revoked","unsigned",
  "not_self_only","disabled","incorrect_signed_at","future_spend",
  "increased_finite_allowance","changed_challenge","wrong_pubkey"}{
  t.Run(scenario,func(t *testing.T){
   row,origin:=samplePGMandateRow(t)
   now:=row.SignedAt.Time.Add(time.Minute)
   switch scenario {
   case "wrong_signature":row.SignatureJSON=strings.Replace(row.SignatureJSON,"signature","bad_signature",1)
   case "changed_consent":row.ConsentID="00000000-0000-4000-8000-000000000000"
   case "changed_wallet":row.Wallet=testHTTPAddress(t,108)
   case "changed_plan":row.CurrentPresetVersion++
   case "wrong_wallet_owner":row.CurrentUID="other_owner"
   case "changed_spending_limit":row.CurrentWinnerStakeWolo=20
   case "revoked":row.RevokedAt=sql.NullTime{Valid:true,Time:now}
   case "unsigned":row.SignedAt=sql.NullTime{}
   case "not_self_only":row.PlanSelfOnly=false
   case "disabled":row.PlanEnabled=false
   case "incorrect_signed_at":row.MandateSignedAt=sql.NullTime{Valid:true,Time:row.SignedAt.Time.Add(time.Second)}
   case "future_spend":now=row.SpendExpiresAt
   case "increased_finite_allowance":row.CurrentGamesRemaining.Int64++
   case "changed_challenge":row.ChallengeText+=" more stakes"
   case "wrong_pubkey":row.SignatureJSON=strings.Replace(row.SignatureJSON,"tendermint/PubKeySecp256k1","ed25519",1)
   }
   if err:=row.verify(origin,now);!errors.Is(err,ErrReviewerHeld){
    t.Fatalf("%s mistakenly authorized original wallet: %v",scenario,err)
   }
  })
 }
}
func TestReviewerPGMandateFiniteAllowancesMayOnlyDecrease(t *testing.T){
 row,original:=samplePGMandateRow(t)
 row.CurrentGamesRemaining.Int64=2
 if e:=row.verify(original,row.SignedAt.Time.Add(time.Minute));e!=nil{
  t.Fatalf("legitimate smaller future game count refused: %v",e)
 }
 row.CurrentGamesRemaining.Int64=6
 if e:=row.verify(original,row.SignedAt.Time.Add(time.Minute));!errors.Is(e,ErrReviewerHeld){
  t.Fatal("increased original future game count accepted")
 }
}
func TestReviewerSQLMandateBoundToPublicTablesAndNotTransferCredentials(t *testing.T){
 for _,q:=range []string{
  "FROM public.war_satchel_wager_authorizations",
  "JOIN public.war_satchel_auto_spend_consents",
  "JOIN public.war_satchel_auto_spend_mandates",
  "JOIN public.bet_auto_presets",
  "JOIN public.users",
  "WHERE a.operation_id=$1",
 }{
  if !strings.Contains(reviewerPGMandateQuery,q){t.Fatalf("missing independent read-only join: %s",q)}
 }
 if strings.Contains(reviewerPGMandateQuery,"INSERT ")||
  strings.Contains(reviewerPGMandateQuery,"UPDATE ")||
  strings.Contains(reviewerPGMandateQuery,"DELETE "){
  t.Fatal("database verifier can mutate original wallet consent")
 }
}
