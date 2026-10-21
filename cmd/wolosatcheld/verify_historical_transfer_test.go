package main

import (
 "bytes"
 "context"
 "encoding/json"
 "os"
 "path/filepath"
 "strings"
 "testing"

 "github.com/emaren/wolochain/internal/satchel"
)

func TestHistoricalAcceptedTransferIntentIsExactAndNonSubstitutable(t *testing.T) {
 baseline:=ExpectedHistoricalTransfer{
  Version:1,Scope:"legacy-settlement-accepted-escrow-100",
  ChainID:"wolo-1",TxHash:acceptedEscrow100Hash,
  Height:acceptedEscrow100Height,Sender:"original_sender",
  Recipient:"original_recipient",AmountUWolo:"100000000",
  Memo:"immutable-original-journal-memo",JournalIdentitySHA256:strings.Repeat("a",64),
 }
 if !verifiedHistoricalIntent(baseline) {t.Fatal("expected structural baseline rejected")}
 variations:=[]func(*ExpectedHistoricalTransfer){
  func(x *ExpectedHistoricalTransfer){x.Version=2},
  func(x *ExpectedHistoricalTransfer){x.Scope="founder-claim-889"},
  func(x *ExpectedHistoricalTransfer){x.ChainID="fake-1"},
  func(x *ExpectedHistoricalTransfer){x.TxHash=strings.Repeat("B",64)},
  func(x *ExpectedHistoricalTransfer){x.TxHash=strings.ToLower(x.TxHash)},
  func(x *ExpectedHistoricalTransfer){x.Height=acceptedEscrow100Height+1},
  func(x *ExpectedHistoricalTransfer){x.AmountUWolo="300000000"},
  func(x *ExpectedHistoricalTransfer){x.AmountUWolo="1000000000"},
  func(x *ExpectedHistoricalTransfer){x.AmountUWolo="0100000000"},
  func(x *ExpectedHistoricalTransfer){x.Sender=""},
  func(x *ExpectedHistoricalTransfer){x.Recipient=x.Sender},
  func(x *ExpectedHistoricalTransfer){x.Memo=""},
  func(x *ExpectedHistoricalTransfer){x.JournalIdentitySHA256=strings.Repeat("0",64)},
  func(x *ExpectedHistoricalTransfer){x.JournalIdentitySHA256="NOT_A_DIGEST"},
 }
 for i,change:=range variations {v:=baseline;change(&v);if verifiedHistoricalIntent(v){t.Errorf("substitution %d accepted",i)}}
}

func TestHistoricalAcceptedTransferStrictJSONRejectsAmbiguity(t *testing.T){
 var x ExpectedHistoricalTransfer
 for _,raw:=range []string{
  `{}`,
  `{"version":1,"version":1}`,
  `{"version":1,"Version":2}`,
  `{"version":1,"vErSiOn":2}`,
  `{"version":1,"ſersion":2}`,
  `{"version":1,"unexpected":true}`,
  `{"version":1} {}`,
  `{"version":1,"scope":NaN}`,
  `null`,
 }{
  if err:=strictHistoricalJSON([]byte(raw),&x);err==nil && raw!="{}"{
   t.Fatalf("accepted ambiguous or invalid JSON %q",raw)
  }
 }
}

func TestHistoricalAcceptedTransferCommandCannotStartServiceOrLeakSensitivePaths(t *testing.T){
 dir,err:=filepath.EvalSymlinks(t.TempDir());if err!=nil{t.Fatal(err)}
 file:=func(name,stringBody string) string {
  p:=filepath.Join(dir,name)
  if err:=os.WriteFile(p,[]byte(stringBody),0600);err!=nil{t.Fatal(err)}
  return p
 }
 anchor,_:=json.Marshal(satchel.TrustAnchor{Height:99,Hash:strings.Repeat("A",64),PeriodSeconds:3600,EvidenceReference:"fixture-only"})
 goodExpected,_:=json.Marshal(ExpectedHistoricalTransfer{
  Version:1,Scope:"legacy-settlement-accepted-escrow-100",ChainID:"wolo-1",
  TxHash:acceptedEscrow100Hash,Height:acceptedEscrow100Height,
  Sender:"original_sender",Recipient:"original_recipient",AmountUWolo:"100000000",
  Memo:"durable-request",JournalIdentitySHA256:strings.Repeat("1",64),
 })
 anchorPath:=file("operator-anchor.json",string(anchor))
 expectedPath:=file("journal-context.json",string(goodExpected))
 proofPath:=file("untrusted-portable.json",`{"version":1,"chain_id":"wolo-1","kind":"transfer","tx_hash":"`+acceptedEscrow100Hash+`","responses":[]}`)
 weakExpected:=file("wrong-identity.json",strings.Replace(string(goodExpected),"100000000","300000000",1))
 malicious:=file("fabricated.json",`{"consensus_authenticated":true,"credit_authorized":false,"height":1078913,"tx_hash":"`+acceptedEscrow100Hash+`"}`)
 symlink:=filepath.Join(dir,"symlink.json")
 if os.Symlink(proofPath,symlink)!=nil{t.Fatal("cannot create symlink")}
 cases:=[][]string{
  {"verify-historical-transfer"},
  {"verify-historical-transfer","--config","/secret/wolo/keyring"},
  {"verify-historical-transfer","--anchor",anchorPath,"--expected",expectedPath,"--proof",proofPath},
  {"verify-historical-transfer","--anchor",anchorPath,"--expected",weakExpected,"--proof",proofPath},
  {"verify-historical-transfer","--anchor",anchorPath,"--expected",expectedPath,"--proof",malicious},
  {"verify-historical-transfer","--anchor",anchorPath,"--expected",expectedPath,"--proof",symlink},
  {"verify-historical-transfer","--anchor",anchorPath,"--expected",expectedPath,"--proof","/secret/wolo/keyring"},
  {"verify-historical-transfer","--anchor",proofPath,"--expected",expectedPath,"--proof",proofPath},
 }
 for i,args:=range cases {
  var out,errout bytes.Buffer
  if rc:=run(context.Background(),args,&out,&errout);rc!=2 || out.Len()!=0 ||
   !strings.Contains(errout.String(),"UNVERIFIABLE") ||
   strings.Contains(errout.String(),dir) || strings.Contains(errout.String(),"secret") {
   t.Errorf("case %d leaked or accepted untrusted proof: rc=%d stdout=%q stderr=%q",i,rc,out.String(),errout.String())
  }
 }
}

func TestHistoricalProofNoSourceActivationOrTransferAuthority(t *testing.T){
 if acceptedEscrow100Height<=0 || len(acceptedEscrow100Hash)!=64 {t.Fatal("historical pin invalid")}
 // The static command never installs or starts a listener; all file-path
 // inputs are force-read by the guarded offline readProofFile helper and all
 // application success paths return 3 (never 0), regardless of chain proof.
 // These are distinct from actual authoritative journal reconciliation.
}
