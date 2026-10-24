package satchelservice

import (
 "bytes"
 "crypto/ed25519"
 "encoding/base64"
 "strings"
 "testing"
 "time"

 "github.com/emaren/wolochain/internal/satchel"
)

func reserveReviewFixture(t *testing.T) (time.Time,SignedReserveReview,ReserveReviewAuthority,reviewedBankObservation,ed25519.PrivateKey,ed25519.PrivateKey) {
 t.Helper()
 now:=time.Date(2026,time.October,21,17,30,0,0,time.UTC)
 accounting:=ed25519.NewKeyFromSeed(bytes.Repeat([]byte{71},32))
 custody:=ed25519.NewKeyFromSeed(bytes.Repeat([]byte{72},32))
 d:=func(x byte)string{return strings.Repeat(string(x),64)}
 a:=ReserveReviewAuthority{
  AccountingReviewerKey:accounting.Public().(ed25519.PublicKey),
  CustodyReviewerKey:custody.Public().(ed25519.PublicKey),
  ExecutionAuthorityKey:ed25519.NewKeyFromSeed(bytes.Repeat([]byte{73},32)).Public().(ed25519.PublicKey),
  WagerApprovalKey:ed25519.NewKeyFromSeed(bytes.Repeat([]byte{74},32)).Public().(ed25519.PublicKey),
  WithdrawalApprovalKey:ed25519.NewKeyFromSeed(bytes.Repeat([]byte{75},32)).Public().(ed25519.PublicKey),
  ExpectedVault:"wolo1synthetic_only_not_an_actual_mainnet_wallet",
  ExpectedBuildSHA256:d('a'),ExpectedConfigSHA256:d('b'),ExpectedPermitSHA256:d('c'),
 }
 r:=SignedReserveReview{
  Version:1,Scope:reserveReviewScope,ChainID:"wolo-1",Denom:"uwolo",
  Vault:a.ExpectedVault,StateHeight:12345,CommitBlockHash:d('d'),
  ObservedBankUWolo:"1000",
  ConfirmedLiabilitiesUWolo:"200",
  UncertainMaxLiabilitiesUWolo:"300",
  GasReserveUWolo:"50",UnencumberedMinimumUWolo:"100",
  LiabilityInventorySHA256:d('e'),JournalSnapshotSHA256:d('f'),
  NonOverlapWitnessSHA256:d('1'),
  BuildSHA256:a.ExpectedBuildSHA256,ConfigSHA256:a.ExpectedConfigSHA256,
  PermitSHA256:a.ExpectedPermitSHA256,
  AllObligationsCovered:true,UnknownClaimsReserved:true,DedicatedVaultIsolated:true,
  IssuedAt:now.Unix()-1,ExpiresAt:now.Unix()+60,
 }
 bank:=reviewedBankObservation{
  vault:r.Vault,balance:r.ObservedBankUWolo,
  commitHash:r.CommitBlockHash,stateHeight:r.StateHeight,
  current:true,expiresAt:now.Add(90*time.Second),
 }
 return now,r,a,bank,accounting,custody
}

func signReview(r *SignedReserveReview,accounting,custody ed25519.PrivateKey) {
 m:=reserveUnsignedMessage(*r)
 r.AccountingReviewerSignature=base64.StdEncoding.EncodeToString(ed25519.Sign(accounting,m))
 r.CustodyReviewerSignature=base64.StdEncoding.EncodeToString(ed25519.Sign(custody,m))
}

func TestProofBoundReserveIndependentSignaturesAndConservativeBalance(t *testing.T){
 now,proposal,authority,bank,a,c:=reserveReviewFixture(t)
 signReview(&proposal,a,c)
 result,err:=evaluateBoundReserveReview(now,proposal,authority,bank)
 if err!=nil || !result.Sufficient || result.UncommittedUWolo!="350" ||
  result.ConservativeCommittedUWolo!="650" || result.ObservedBankUWolo!="1000" ||
  result.CustodyCapability()!="UNAVAILABLE" {
  t.Fatalf("conservative source checker broken: %+v %v",result,err)
 }
 if _,err:=EvaluateProofBoundReserveReview(now,satchel.AuthenticatedBankEvidence{},proposal,authority);err==nil {
  t.Fatal("unverified zero-valued bank evidence activated reserve checker")
 }
 // Real CometBFT block hashes commonly arrive uppercase; canonical lowercase
 // digests remain required for the separate SHA256 review artifacts.
 uppercase:=proposal
 uppercase.CommitBlockHash=strings.ToUpper(proposal.CommitBlockHash)
 signReview(&uppercase,a,c)
 if x,err:=evaluateBoundReserveReview(now,uppercase,authority,bank);err!=nil || !x.Sufficient {
  t.Fatal("case-only CometBFT hash encoding mismatch",err)
 }
}

func TestProofBoundReserveCannotWaiveClaimsOrFakeAssetEvidence(t *testing.T) {
 now,original,auth,bank,accounting,custody:=reserveReviewFixture(t)
 checks:=map[string]func(*SignedReserveReview,*reviewedBankObservation,*ReserveReviewAuthority){
  "invented_balance":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){r.ObservedBankUWolo="10000000"},
  "unproven_bank_head":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){b.current=false},
  "wrong_bank_amount":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){b.balance="1001"},
  "wrong_bank_state_height":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){b.stateHeight++},
  "wrong_bank_commitment":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){b.commitHash=strings.Repeat("9",64)},
  "missing_liabilities":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){r.AllObligationsCovered=false},
  "unknown_exposure_not_reserved":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){r.UnknownClaimsReserved=false},
  "no_escrow_isolation":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){r.DedicatedVaultIsolated=false},
  "waive_unknown_300":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){r.UncertainMaxLiabilitiesUWolo="0"},
  "invented_accounting_snapshot":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){r.LiabilityInventorySHA256=strings.Repeat("0",64)},
  "invented_journal_snapshot":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){r.JournalSnapshotSHA256=strings.Repeat("0",64)},
  "missing_overlap_witness":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){r.NonOverlapWitnessSHA256=""},
  "wrong_vault":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){r.Vault="wolo1other"},
  "wrong_chain":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){r.ChainID="fake-1"},
  "wrong_denom":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){r.Denom="wolo"},
  "rotated_build":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){a.ExpectedBuildSHA256=strings.Repeat("2",64)},
  "rotated_config":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){a.ExpectedConfigSHA256=strings.Repeat("2",64)},
  "rotated_permit":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){a.ExpectedPermitSHA256=strings.Repeat("2",64)},
  "stale_bank_proof":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){b.expiresAt=now.Add(-time.Second)},
  "stale_review":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){r.ExpiresAt=now.Unix()-1},
  "future_review":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){r.IssuedAt=now.Unix()+20;r.ExpiresAt=now.Unix()+25},
  "too_long_review":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){r.ExpiresAt=r.IssuedAt+maxReserveReviewSeconds+1},
  "expires_after_bank":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){r.ExpiresAt=now.Unix()+95},
  "zero_gas_reserve":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){r.GasReserveUWolo="0"},
  "zero_min_reserve":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){r.UnencumberedMinimumUWolo="0"},
  "negative_amount":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){r.ConfirmedLiabilitiesUWolo="-1"},
  "fractional_amount":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){r.ConfirmedLiabilitiesUWolo="0.1"},
  "scientific_notation":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){r.ConfirmedLiabilitiesUWolo="1e3"},
  "leading_zero":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){r.ConfirmedLiabilitiesUWolo="0200"},
  "out_of_range":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){r.UncertainMaxLiabilitiesUWolo=strings.Repeat("9",39)},
  "underfunded":func(r *SignedReserveReview,b *reviewedBankObservation,a *ReserveReviewAuthority){r.ConfirmedLiabilitiesUWolo="800"},
 }
 for name,change:=range checks {
  t.Run(name,func(t *testing.T){
   r,b,a:=original,bank,auth
   change(&r,&b,&a)
   signReview(&r,accounting,custody)
   if _,err:=evaluateBoundReserveReview(now,r,a,b);err==nil {
    t.Fatal("incomplete/contradictory review unexpectedly qualified")
   }
  })
 }
}

func TestProofBoundReserveRejectsCryptographicAuthorityConfusion(t *testing.T){
 now,review,authority,bank,accounting,custody:=reserveReviewFixture(t)
 signReview(&review,accounting,custody)
 check:=func(label string,r SignedReserveReview,a ReserveReviewAuthority) {
  t.Helper()
  if _,err:=evaluateBoundReserveReview(now,r,a,bank);err==nil{t.Errorf("%s qualified",label)}
 }
 swapped:=authority
 swapped.AccountingReviewerKey=authority.CustodyReviewerKey
 swapped.CustodyReviewerKey=authority.AccountingReviewerKey
 check("swap reviewer roles",review,swapped)
 same:=authority
 same.AccountingReviewerKey=authority.CustodyReviewerKey
 check("same reviewer key",review,same)
 noKey:=authority
 noKey.CustodyReviewerKey=nil
 check("missing key",review,noKey)
 noExecutionKey:=authority
 noExecutionKey.ExecutionAuthorityKey=nil
 check("missing execution role",review,noExecutionKey)
 reusedExecution:=authority
 reusedExecution.ExecutionAuthorityKey=authority.AccountingReviewerKey
 check("reviewer is execution permit authority",review,reusedExecution)
 reusedWager:=authority
 reusedWager.WagerApprovalKey=authority.CustodyReviewerKey
 check("reviewer is wager approval authority",review,reusedWager)
 reusedWithdrawal:=authority
 reusedWithdrawal.WithdrawalApprovalKey=authority.AccountingReviewerKey
 check("reviewer is withdrawal approval authority",review,reusedWithdrawal)
 reusedSigningRoles:=authority
 reusedSigningRoles.WagerApprovalKey=authority.WithdrawalApprovalKey
 check("wager and withdrawal approval alias",review,reusedSigningRoles)
 noSign:=review
 noSign.AccountingReviewerSignature=""
 check("missing signature",noSign,authority)
 tamper:=review
 tamper.ConfirmedLiabilitiesUWolo="201"
 check("post signature liability mutation",tamper,authority)
 wrongSig:=review
 wrongSig.CustodyReviewerSignature=review.AccountingReviewerSignature
 check("replay signature in other role",wrongSig,authority)
 injected:=review
 injected.CustodyReviewerSignature=review.CustodyReviewerSignature+"="
 check("noncanonical signature",injected,authority)
}

func TestProofBoundReserveWideningMustBeReviewedWithNewSignatures(t *testing.T){
 now,review,authority,bank,accounting,custody:=reserveReviewFixture(t)
 signReview(&review,accounting,custody)
 increased:=review
 increased.ObservedBankUWolo="2000"
 // A fabricated balance, even countersigned by both reviewers, cannot
 // contradict the cryptographically pinned native bank-state observation.
 signReview(&increased,accounting,custody)
 if _,err:=evaluateBoundReserveReview(now,increased,authority,bank);err==nil{
  t.Fatal("invented signed asset balance accepted")
 }
 // A larger known exposure must be covered by actual bank funds.
 liability:=review
 liability.UncertainMaxLiabilitiesUWolo="900"
 signReview(&liability,accounting,custody)
 if _,err:=evaluateBoundReserveReview(now,liability,authority,bank);err==nil{
  t.Fatal("newly attested shortfall accepted")
 }
}
