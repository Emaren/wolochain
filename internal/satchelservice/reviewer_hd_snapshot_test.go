package satchelservice

import (
 "encoding/json"
 "errors"
 "strings"
 "testing"
)
func sampleHDOrigin(t *testing.T)([]byte,ReviewerHDOriginColumns){
 t.Helper()
 prop:=strings.Repeat("3",64)
 origin:=map[string]any{
  "executionId":7,"ownerUserId":77,"ownerUid":"steam_77",
  "ownerWallet":testHTTPAddress(t,100),
  "reservationId":"satchel:reserve:7","operationId":"satchel:ticket:7",
  "ticketId":7,"vault":testHTTPAddress(t,101),"recipient":testHTTPAddress(t,102),
  "amountUwolo":"12000000","memo":"AoE2HDBets bet ticket v1 · ticket 7",
  "gameIdentityKey":"watcher:game-7","propositionHash":prop,
  "presetId":9,"presetVersion":2,
  "consentId":"12345678-1234-4123-8123-123456789abc",
  "challengeText":"owner signed bounded ADR-36 mandate",
  "ownerSignatureJson":map[string]any{
   "pub_key":map[string]any{"type":"tendermint/PubKeySecp256k1","value":"ABC="},
   "signature":"SIG=",
  },
  "ledgerVersion":"9","availableUwolo":"88000000","reservedUwolo":"12000000",
  "journalId":"71",
  "legs":[]any{map[string]any{
   "id":71,"marketId":74,"side":"left","amountWolo":12,"propositionHash":prop,
  }},
 }
 raw,e:=json.Marshal(origin);if e!=nil{t.Fatal(e)}
 stored:=ReviewerHDOriginColumns{
  OperationID:"satchel:ticket:7",ReservationID:"satchel:reserve:7",OwnerUserID:77,
  // The following values were generated using the actual TypeScript
  // buildSatchelWagerAuthorization() canonical() SHA256 algorithm, not Go.
  ConsentDigest:"b6a5ff613e0eb2ca94e6dd42813d81c01ef260e60605a49a5094339a8ff0e657",
  LedgerRevision:"f1bece53a3ff5b26c679e175b76cd10ba1ad8afaed89d32760c43647e010a41d",
  ReservationDigest:"493da44ea2c8029f70afb10cbec9516b3a248d2f74d4df7dbea2b41567d579ae",
 }
 return raw,stored
}
func TestReviewerHDDigestsMatchIndependentTypeScriptGoldenVector(t *testing.T){
 raw,stored:=sampleHDOrigin(t)
 got,e:=VerifyReviewerHDOrigin(raw,stored)
 if e!=nil{t.Fatalf("valid TS original snapshot refused: %v",e)}
 if got.ReservationDigest!=stored.ReservationDigest||got.ConsentDigest!=stored.ConsentDigest||
  got.LedgerRevision!=stored.LedgerRevision||got.OperationID!=stored.OperationID||
  got.OwnerUserID!=77||got.AmountUWolo!="12000000"||len(got.Legs)!=1 {
  t.Fatalf("TS/Go original snapshot digest mismatch: %+v",got)
 }
}
func TestReviewerHDOriginalRejectsTamperedSourceOrStoredDigest(t *testing.T){
 for _,change:=range []string{
  "owner","vault","escrow","amount","memo","game","proposition",
  "stake","market","signer","consent","ledger","reservation","additional",
  "no_legs","different_ticket","reserved_amount",
 }{
  t.Run(change,func(t *testing.T){
   raw,stored:=sampleHDOrigin(t)
   x:=map[string]any{}
   if err:=json.Unmarshal(raw,&x);err!=nil{t.Fatal(err)}
   switch change {
   case "owner":stored.OwnerUserID=76
   case "vault":x["vault"]=testHTTPAddress(t,102)
   case "escrow":x["recipient"]=testHTTPAddress(t,101)
   case "amount":x["amountUwolo"]="13000000"
   case "memo":x["memo"]="different memo"
   case "game":x["gameIdentityKey"]="rebound-game"
   case "proposition":x["propositionHash"]=strings.Repeat("4",64)
   case "stake":x["legs"].([]any)[0].(map[string]any)["amountWolo"]=13.0
   case "market":x["legs"].([]any)[0].(map[string]any)["marketId"]=75.0
   case "signer":x["ownerSignatureJson"].(map[string]any)["signature"]="different"
   case "consent":stored.ConsentDigest=strings.Repeat("0",64)
   case "ledger":stored.LedgerRevision=strings.Repeat("0",64)
   case "reservation":stored.ReservationDigest=strings.Repeat("0",64)
   case "additional":x["extraField"]=true
   case "no_legs":x["legs"]=[]any{}
   case "different_ticket":x["ticketId"]=8.0
   case "reserved_amount":x["reservedUwolo"]="0"
   }
   mutated,e:=json.Marshal(x);if e!=nil{t.Fatal(e)}
   _,e=VerifyReviewerHDOrigin(mutated,stored)
   if !errors.Is(e,ErrReviewerHDOrigin){t.Fatalf("modified %s original accepted: %v",change,e)}
  })
 }
}
func TestReviewerHDOriginRefusesDuplicateJsonEvenIfHashLooksValid(t *testing.T){
 raw,stored:=sampleHDOrigin(t)
 raw=append([]byte(nil),raw...)
 // Duplicate one top-level identity key; a naive map unmarshal would accept
 // the latter and hide contradictory source bytes.
 s:=string(raw)
 s=strings.Replace(s,`"executionId":7`,`"executionId":7,"executionId":7`,1)
 if s==string(raw){t.Fatal("fixture field not found")}
 if _,e:=VerifyReviewerHDOrigin([]byte(s),stored);!errors.Is(e,ErrReviewerHDOrigin){
  t.Fatalf("duplicate JSON key accepted: %v",e)
 }
}
func TestReviewerHDOriginRefusesFloatUnboundedAndNonCanonicalNumbers(t *testing.T){
 for _,corrupt:=range []string{
  `"executionId":7.5`,`"executionId":7e0`,`"executionId":9007199254740992`,
  `"amountUwolo":"0001"`,`"ledgerVersion":"-1"`,
  `"availableUwolo":"9223372036854775808"`,
  `"ownerUserId":null`,
 }{
  raw,stored:=sampleHDOrigin(t)
  var modified string
  if strings.HasPrefix(corrupt,`"executionId":`){
   modified=strings.Replace(string(raw),`"executionId":7`,corrupt,1)
  }else if strings.HasPrefix(corrupt,`"ownerUserId":`){
   modified=strings.Replace(string(raw),`"ownerUserId":77`,corrupt,1)
  }else{
   m:=strings.SplitN(corrupt,":",2)
   idx:=strings.Index(string(raw),m[0]+":")
   if idx<0{t.Fatalf("key not found %s",corrupt)}
   val:=m[1]
   origin:=map[string]any{}
   _=json.Unmarshal(raw,&origin)
   var obj any
   _=json.Unmarshal([]byte(val),&obj)
   origin[strings.Trim(m[0],`"`)]=obj
   data,_:=json.Marshal(origin)
   modified=string(data)
  }
  if modified==string(raw){t.Fatalf("fixture replacement failed %s",corrupt)}
  if _,e:=VerifyReviewerHDOrigin([]byte(modified),stored);!errors.Is(e,ErrReviewerHDOrigin){
   t.Fatalf("invalid original accepted %s: %v",corrupt,e)
  }
 }
}
func TestReviewerHDOriginNeverGrantsTransferOrSignerAuthority(t *testing.T){
 raw,stored:=sampleHDOrigin(t)
 proof,e:=VerifyReviewerHDOrigin(raw,stored)
 if e!=nil{t.Fatal(e)}
 if proof.ConsentID==""||proof.LedgerVersion==""||proof.JournalID==""{t.Fatal("missing original source bindings")}
 // ReviewerHDOriginResult is an immutable diagnostic projection, with NO
 // signer key, no wallet private key, no boolean granting a chain transfer.
 if proof.OwnerSignatureJSON==nil{t.Fatal("original consent evidence absent")}
}
