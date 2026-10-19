package satchelservice

import (
 "encoding/base64"
 "errors"
 "fmt"
 "strings"
 "testing"
 "time"

 "github.com/cosmos/btcutil/bech32"
 sdksecp "github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
)

func sampleReviewerMandate(t *testing.T)(ReviewerStoredOwnerMandate,ReviewerOwnerExpectation){
 t.Helper()
 priv:=sdksecp.GenPrivKeyFromSecret([]byte("test ADR36 user wallet held isolated 20261019"))
 addr,err:=bech32.EncodeFromBase256("wolo",priv.PubKey().Address())
 if err!=nil{t.Fatal(err)}
 issued:=time.Date(2026,10,19,16,0,0,0,time.UTC)
 games:=int64(5)
 m:=ReviewerStoredOwnerMandate{
  OwnerUID:"steam_77",WalletAddress:addr,PresetID:9,PresetVersion:3,
  WinnerStakeWolo:10,DesyncSide:"none",DesyncStakeWolo:0,
  PerGameCapWolo:10,DailyCapWolo:50,UntilOut:false,GamesRemaining:&games,
  Nonce:strings.Repeat("a",32),IssuedAt:issued,ChallengeExpiresAt:issued.Add(5*time.Minute),
  SpendExpiresAt:issued.Add(23*time.Hour),SignedAt:issued.Add(time.Minute),
  PublicKeyType:"tendermint/PubKeySecp256k1",
  PublicKeyBase64:base64.StdEncoding.EncodeToString(priv.PubKey().Bytes()),
 }
 issue,_:=reviewerISO(m.IssuedAt)
 expires,_:=reviewerISO(m.ChallengeExpiresAt)
 spend,_:=reviewerISO(m.SpendExpiresAt)
 m.ChallengeText=reviewerOwnerChallengeText(m,issue,expires,spend)
 bytes,err:=ReviewerADR36SignBytes(addr,m.ChallengeText)
 if err!=nil{t.Fatal(err)}
 signature,err:=priv.Sign(bytes)
 if err!=nil{t.Fatal(err)}
 m.SignatureBase64=base64.StdEncoding.EncodeToString(signature)
 x:=ReviewerOwnerExpectation{OwnerUID:m.OwnerUID,WalletAddress:m.WalletAddress,
  PresetID:m.PresetID,PresetVersion:m.PresetVersion,
  WinnerStakeWolo:m.WinnerStakeWolo,DesyncSide:m.DesyncSide,
  DesyncStakeWolo:m.DesyncStakeWolo,UntilOut:m.UntilOut,
  GamesRemaining:&games,OriginalOperationID:"satchel:ticket:7"}
 return m,x
}
func TestReviewerOriginalKeplrADR36SignatureIsReallyVerified(t *testing.T){
 m,x:=sampleReviewerMandate(t)
 if err:=VerifyReviewerOwnerMandate(m,x,m.SignedAt.Add(time.Minute));err!=nil{
  t.Fatalf("correct independent owner signature rejected: %v",err)
 }
}
func TestReviewerADR36ExactSortedCosmJSAminoEnvelope(t *testing.T){
 m,_:=sampleReviewerMandate(t)
 bytes,err:=ReviewerADR36SignBytes(m.WalletAddress,"Hello")
 if err!=nil{t.Fatal(err)}
 want:=fmt.Sprintf(`{"account_number":"0","chain_id":"","fee":{"amount":[],"gas":"0"},"memo":"","msgs":[{"type":"sign/MsgSignData","value":{"data":"SGVsbG8=","signer":%q}}],"sequence":"0"}`,m.WalletAddress)
 if string(bytes)!=want{t.Fatalf("CosmJS ADR-36 bytes mismatch\ngot=%s\nwant=%s",bytes,want)}
}
func TestReviewerKeplrSignatureOrWalletForgeryRefused(t *testing.T){
 for _,which:=range []string{"wrong_wallet","forged_signature","wrong_key","wrong_issuer","unsigned","extra_signature_byte"}{
  t.Run(which,func(t *testing.T){
   m,x:=sampleReviewerMandate(t)
   switch which{
   case "wrong_wallet":x.WalletAddress="wolo1"+"z"+m.WalletAddress[6:]
   case "forged_signature":m.SignatureBase64=base64.StdEncoding.EncodeToString(make([]byte,64))
   case "wrong_key":m.PublicKeyBase64=base64.StdEncoding.EncodeToString(append([]byte{2},make([]byte,32)...))
   case "wrong_issuer":x.OwnerUID="some_other_steam_uid"
   case "unsigned":m.SignatureBase64=""
   case "extra_signature_byte":m.SignatureBase64=base64.StdEncoding.EncodeToString(make([]byte,65))
   }
   if err:=VerifyReviewerOwnerMandate(m,x,m.SignedAt.Add(time.Minute));!errors.Is(err,ErrReviewerOwnerMandate){
    t.Fatalf("%s verification incorrectly passed: %v",which,err)
   }
  })
 }
}
func TestReviewerKeplrSpendingAndPlanMutationRefused(t *testing.T){
 for _,which:=range []string{"stake","preset","version","side","limit","daily","games_increase","unknown_game"}{
  t.Run(which,func(t *testing.T){
   m,x:=sampleReviewerMandate(t)
   switch which{
   case "stake":x.WinnerStakeWolo++
   case "preset":x.PresetID++
   case "version":x.PresetVersion++
   case "side":x.DesyncSide="yes"
   case "limit":m.PerGameCapWolo=1000
   case "daily":m.DailyCapWolo=200
   case "games_increase":n:=int64(6);x.GamesRemaining=&n
   case "unknown_game":x.OriginalOperationID="satchel:ticket:0"
   }
   if err:=VerifyReviewerOwnerMandate(m,x,m.SignedAt.Add(time.Minute));!errors.Is(err,ErrReviewerOwnerMandate){
    t.Fatalf("changed %s spending approved: %v",which,err)
   }
  })
 }
}
func TestReviewerKeplrRevokedExpiredStaleAndForgedConsentRefused(t *testing.T){
 for _,which:=range []string{"revoked","expired","future_signature","late_signature","forged_challenge","unbounded_challenge","unbounded_spend","noncanonical_time","zero_nonce"}{
  t.Run(which,func(t *testing.T){
   m,x:=sampleReviewerMandate(t)
   now:=m.SignedAt.Add(time.Minute)
   switch which{
   case "revoked":rev:=m.SignedAt;m.RevokedAt=&rev
   case "expired":now=m.SpendExpiresAt
   case "future_signature":m.SignedAt=m.IssuedAt.Add(-time.Second)
   case "late_signature":m.SignedAt=m.ChallengeExpiresAt
   case "forged_challenge":m.ChallengeText+="\nSpend more WOLO"
   case "unbounded_challenge":m.ChallengeExpiresAt=m.IssuedAt.Add(6*time.Minute)
   case "unbounded_spend":m.SpendExpiresAt=m.IssuedAt.Add(25*time.Hour)
   case "noncanonical_time":m.IssuedAt=m.IssuedAt.Add(time.Microsecond)
   case "zero_nonce":m.Nonce=strings.Repeat("0",31)
   }
   if err:=VerifyReviewerOwnerMandate(m,x,now);!errors.Is(err,ErrReviewerOwnerMandate){
    t.Fatalf("%s consent incorrectly accepted: %v",which,err)
   }
  })
 }
}
func TestReviewerKeplrAllowsFinitePlanToDecreaseButNotIncrease(t *testing.T){
 m,x:=sampleReviewerMandate(t)
 smaller:=int64(2);x.GamesRemaining=&smaller
 if err:=VerifyReviewerOwnerMandate(m,x,m.SignedAt.Add(time.Minute));err!=nil{
  t.Fatalf("legitimate finite remaining allowance decrease refused: %v",err)
 }
 bigger:=int64(7);x.GamesRemaining=&bigger
 if err:=VerifyReviewerOwnerMandate(m,x,m.SignedAt.Add(time.Minute));!errors.Is(err,ErrReviewerOwnerMandate){
  t.Fatal("increased original game allowance accepted")
 }
}
func TestReviewerKeplrUntilOutConsentIsStillBoundedByDailyAndExpiry(t *testing.T){
 m,x:=sampleReviewerMandate(t)
 m.UntilOut=true;m.GamesRemaining=nil
 x.UntilOut=true;x.GamesRemaining=nil
 issue,_:=reviewerISO(m.IssuedAt);challenge,_:=reviewerISO(m.ChallengeExpiresAt);spend,_:=reviewerISO(m.SpendExpiresAt)
 m.ChallengeText=reviewerOwnerChallengeText(m,issue,challenge,spend)
 priv:=sdksecp.GenPrivKeyFromSecret([]byte("test ADR36 user wallet held isolated 20261019"))
 data,_:=ReviewerADR36SignBytes(m.WalletAddress,m.ChallengeText)
 sig,_:=priv.Sign(data)
 m.SignatureBase64=base64.StdEncoding.EncodeToString(sig)
 if err:=VerifyReviewerOwnerMandate(m,x,m.SignedAt.Add(time.Minute));err!=nil{
  t.Fatalf("valid until-out challenge rejected: %v",err)
 }
 m.DailyCapWolo=10001
 if err:=VerifyReviewerOwnerMandate(m,x,m.SignedAt.Add(time.Minute));!errors.Is(err,ErrReviewerOwnerMandate){
  t.Fatal("unbounded daily cap accepted")
 }
}
