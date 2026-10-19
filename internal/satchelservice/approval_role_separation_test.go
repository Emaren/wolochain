package satchelservice

import (
 "bytes"
 "crypto/ed25519"
 "encoding/base64"
 "encoding/json"
 "errors"
 "os"
 "path/filepath"
 "testing"
 "time"
)

// A stolen unattended Mecha wager-review key must not be valid as an
// independent withdrawal approval key. Domain separation alone is not enough
// when separate OS operators and key custody are expected in production.
func TestWagerAndWithdrawalKeysAreIndependentCryptographicAuthorities(t *testing.T){
 policy:=engineTestPolicy(t)
 if bytes.Equal(policy.WagerApprovalKey,policy.WithdrawalApprovalKey){
  t.Fatal("withdrawal and unattended wager use the same root")
 }
 wager:=engineTestWager(t,"7")
 if e:=policy.verifyWager(wager,time.Unix(1800000000,0));e!=nil{t.Fatalf("true wager signer rejected: %v",e)}
 wager.Reservation.Signature=base64.StdEncoding.EncodeToString(
  ed25519.Sign(engineTestWithdrawalApprovalKey(),WagerReservationMessage(*wager.Reservation)))
 if e:=policy.verifyWager(wager,time.Unix(1800000000,0));e==nil{
  t.Fatal("withdrawal Ed25519 key also authorized an unattended wager")
 }
 withdrawal:=engineTestWithdrawal(t)
 if e:=policy.verifyWithdrawal(withdrawal,time.Unix(1800000000,0));e!=nil{
  t.Fatalf("true withdrawal signer rejected: %v",e)
 }
 withdrawal.Approval.Signature=base64.StdEncoding.EncodeToString(
  ed25519.Sign(engineTestApprovalKey(),ApprovalMessage(*withdrawal.Approval,policy.Vault)))
 if e:=policy.verifyWithdrawal(withdrawal,time.Unix(1800000000,0));e==nil{
  t.Fatal("unattended wager reviewer key also authorized a withdrawal")
 }
}
func TestWagerApprovalMissingOrCrossRoleKeyAlwaysRefuses(t *testing.T){
 p:=engineTestPolicy(t)
 wager:=engineTestWager(t,"7")
 p.WagerApprovalKey=nil
 if e:=p.verifyWager(wager,time.Unix(1800000000,0));e==nil{
  t.Fatal("missing WagerApprovalKey silently fell back to WithdrawalApprovalKey")
 }
 p.WagerApprovalKey=append([]byte(nil),p.WithdrawalApprovalKey...)
 if e:=p.verifyWager(wager,time.Unix(1800000000,0));e==nil{
  t.Fatal("cross-role warrant key could validate original independent wager signature")
 }
 if _,e:=Open("/invalid-test-path",p,&engineTestBackend{});e==nil{
  t.Fatal("signer opened with identical wagering and withdrawal authority")
 }
}
func TestConfigRequiresThreeDistinctEd25519Authorities(t *testing.T){
 for _,which:=range []string{"missing_wager","wager_equals_withdrawal","wager_equals_activation","invalid_wager"}{
  t.Run(which,func(t *testing.T){
   c,_,_,_:=configTestFixture(t)
   switch which{
   case "missing_wager":c.WagerApprovalKeyHex=""
   case "wager_equals_withdrawal":c.WagerApprovalKeyHex=c.WithdrawalApprovalKeyHex
   case "wager_equals_activation":c.WagerApprovalKeyHex=c.ActivationAuthorityKeyHex
   case "invalid_wager":c.WagerApprovalKeyHex="ff"
   }
   b,e:=json.Marshal(c);if e!=nil{t.Fatal(e)}
   path:=filepath.Join(filepath.Dir(c.PermitFile),"invalid-three-role-config.json")
   if e=os.WriteFile(path,b,0600);e!=nil{t.Fatal(e)}
   if _,_,e=LoadConfig(path);!errors.Is(e,errors.New("independent_approval_keys_required"))&&e==nil{
    t.Fatalf("%s unsafe reviewer key configuration admitted",which)
   }
  })
 }
}
