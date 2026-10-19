package satchelservice

import (
 "bytes"
 "context"
 "crypto/ed25519"
 "encoding/json"
 "errors"
 "net/http"
 "net/http/httptest"
 "path/filepath"
 "strings"
 "testing"
 "time"

 bolt "go.etcd.io/bbolt"
)

type fakeReviewerEvidence struct{
 original WagerReservation
 census ReviewerFeeCensus
 failOwner bool
 failMarket bool
 failBank bool
 loads int
}
func (f *fakeReviewerEvidence)OriginalHold(_ context.Context,id string)(WagerReservation,error){
 f.loads++
 if id!=f.original.OperationID{return WagerReservation{},ErrReviewerHeld}
 return f.original,nil
}
func (f *fakeReviewerEvidence)VerifyOwnerMandate(_ context.Context,_ WagerReservation)error{
 if f.failOwner{return ErrReviewerHeld};return nil
}
func (f *fakeReviewerEvidence)VerifyWatcherMarket(_ context.Context,_ WagerReservation)error{
 if f.failMarket{return ErrReviewerHeld};return nil
}
func (f *fakeReviewerEvidence)AuthenticatedFeeCensus(_ context.Context,_ WagerReservation)(ReviewerFeeCensus,error){
 if f.failBank{return ReviewerFeeCensus{},ErrReviewerHeld}
 return f.census,nil
}
func setupIssuer(t *testing.T)(*ReviewerIssuer,*fakeReviewerEvidence,Policy,string){
 t.Helper()
 r:=engineTestWager(t,"7")
 r.Reservation.Signature=""
 r.Reservation.IssuedAt=0
 r.Reservation.ExpiresAt=0
 r.Reservation.FeeUWolo="1"
 census:=ReviewerFeeCensus{ChainID:"wolo-1",Denom:"uwolo",OperationID:r.OperationID,
  BankBalanceUWolo:"100000005",AllOwnerLiabilitiesUWolo:"100000000",
  NewOperationFeeUWolo:"1",MinimumUnencumberedGasUWolo:"2",PendingOperationsComplete:true,
  PendingOperations:[]ReviewerPendingFee{
   {OperationID:"satchel:ticket:2",Stage:"prepared",FeeUWolo:"1"},
   {OperationID:"satchel:withdrawal:3",Stage:"uncertain",FeeUWolo:"1"},
  }}
 source:=&fakeReviewerEvidence{original:*r.Reservation,census:census}
 policy:=engineTestPolicy(t)
 state:=filepath.Join(t.TempDir(),"approval.db")
 issuer,err:=OpenReviewerIssuer(state,source,engineTestWagerApprovalKey(),policy)
 if err!=nil{t.Fatalf("issuer: %v",err)}
 t.Cleanup(func(){_ = issuer.Close()})
 return issuer,source,policy,state
}
func TestReviewerIndependentEvidenceSignsOneRealProtocolTwoGrant(t *testing.T){
 i,source,policy,_:=setupIssuer(t)
 result:=i.ReviewOne(t.Context(),"satchel:ticket:7")
 if result.Status!="SIGNED"||result.Protocol!=1||result.Approval==nil||
  result.OperationID!="satchel:ticket:7"{t.Fatalf("held valid reviewer: %+v",result)}
 transfer:=TransferRequest{OperationID:result.Approval.OperationID,OwnerID:result.Approval.OwnerID,
  ChainID:"wolo-1",Denom:"uwolo",Kind:"wager",Sender:result.Approval.Vault,
  Recipient:result.Approval.Recipient,AmountUWolo:result.Approval.AmountUWolo,
  Memo:result.Approval.Memo,Reservation:result.Approval}
 if err:=policy.verifyWager(transfer,time.Now());err!=nil{t.Fatalf("signer refused exact grant: %v",err)}
 again:=i.ReviewOne(t.Context(),"satchel:ticket:7")
 if again.Status!="SIGNED"||again.Approval.Signature!=result.Approval.Signature||source.loads!=2{
  t.Fatalf("duplicate lookup changed signature or skipped source: %+v",again)
 }
}
func TestReviewerOwnerMarketOrBankRefusalNeverSigns(t *testing.T){
 for _,which:=range []string{"owner","market","bank","budget","incomplete"}{
  t.Run(which,func(t *testing.T){
   i,s,_,_:=setupIssuer(t)
   switch which{
   case "owner":s.failOwner=true
   case "market":s.failMarket=true
   case "bank":s.failBank=true
   case "budget":s.census.BankBalanceUWolo="100000004"
   case "incomplete":s.census.PendingOperationsComplete=false
   }
   got:=i.ReviewOne(t.Context(),"satchel:ticket:7")
   if got.Status!="PENDING"||got.Approval!=nil{t.Fatalf("%s yielded approval: %+v",which,got)}
  })
 }
}
func TestReviewerRestartReusesOriginalSignatureAndRejectsChangedHold(t *testing.T){
 i,s,policy,state:=setupIssuer(t)
 result:=i.ReviewOne(t.Context(),"satchel:ticket:7")
 if result.Approval==nil{t.Fatal("no first grant")}
 if e:=i.Close();e!=nil{t.Fatal(e)}
 recovered,e:=OpenReviewerIssuer(state,s,engineTestWagerApprovalKey(),policy)
 if e!=nil{t.Fatal(e)}
 defer recovered.Close()
 same:=recovered.ReviewOne(t.Context(),"satchel:ticket:7")
 if same.Approval==nil||same.Approval.Signature!=result.Approval.Signature{
  t.Fatalf("restart duplicated signing: %+v",same)
 }
 s.original.ConsentDigest=strings.Repeat("a",64)
 changed:=recovered.ReviewOne(t.Context(),"satchel:ticket:7")
 if changed.Status!="PENDING"||changed.Approval!=nil{
  t.Fatalf("old reviewer grant reissued for changed consent: %+v",changed)
 }
}
func TestReviewerDurablePendingFromCrashCannotRenew(t *testing.T){
 i,s,_,_:=setupIssuer(t)
 fp:=reviewerFingerprint(s.original)
 if err:=i.db.Update(func(tx *bolt.Tx)error{
  b,_:=json.Marshal(reviewerEntry{Fingerprint:fp,Status:"PENDING"})
  return tx.Bucket(reviewerIssues).Put([]byte(s.original.OperationID),b)
 });err!=nil{t.Fatal(err)}
 for n:=0;n<2;n++{
  got:=i.ReviewOne(t.Context(),s.original.OperationID)
  if got.Status!="PENDING"||got.Approval!=nil{t.Fatalf("reissued after crash: %+v",got)}
 }
}
func TestReviewerCannotRenewExpiredGrant(t *testing.T){
 i,_,_,_:=setupIssuer(t)
 at:=time.Now()
 i.now=func()time.Time{return at}
 a:=i.ReviewOne(t.Context(),"satchel:ticket:7")
 if a.Approval==nil{t.Fatal("no original")}
 i.now=func()time.Time{return at.Add(70*time.Second)}
 b:=i.ReviewOne(t.Context(),"satchel:ticket:7")
 if b.Status!="PENDING"||b.Approval!=nil{t.Fatal("expired grant renewed")}
}
func TestReviewerRefusesWrongRoleKeyAndMissingSource(t *testing.T){
 i,s,policy,state:=setupIssuer(t)
 _=i.Close()
 _,bad:=OpenReviewerIssuer(state,nil,engineTestWagerApprovalKey(),policy)
 if !errors.Is(bad,ErrReviewerHeld){t.Fatal("nil evidence source admitted")}
 _,wrong,e:=ed25519.GenerateKey(nil)
 if e!=nil{t.Fatal(e)}
 if wrong==nil{t.Fatal("no synthetic key")}
 _,bad=OpenReviewerIssuer(state,s,wrong,policy)
 if !errors.Is(bad,ErrReviewerHeld){t.Fatal("unrelated approval key admitted")}
}
func reviewerRequest(t *testing.T,h http.Handler,body,token string,remote string)*httptest.ResponseRecorder{
 t.Helper()
 req:=httptest.NewRequest(http.MethodPost,reviewerHTTPPath,strings.NewReader(body))
 req.RemoteAddr=remote
 req.Header.Set("Content-Type","application/json")
 req.Header.Set("Authorization","Bearer "+token)
 w:=httptest.NewRecorder();h.ServeHTTP(w,req);return w
}
func TestPrivateReviewerHTTPAcceptsOperationOnlyAndSigns(t *testing.T){
 i,_,_,_:=setupIssuer(t)
 token:=strings.Repeat("a",48)
 h,e:=NewReviewerHTTPHandler(i,token)
 if e!=nil{t.Fatal(e)}
 w:=reviewerRequest(t,h,`{"protocol":1,"operation_id":"satchel:ticket:7"}`,token,"127.0.0.1:50122")
 if w.Code!=http.StatusOK{t.Fatalf("private operation failed %d %s",w.Code,w.Body.String())}
 var out ReviewerIssuedReply
 if json.Unmarshal(w.Body.Bytes(),&out)!=nil||out.Approval==nil||out.Status!="SIGNED"{
  t.Fatalf("signed reply missing: %s",w.Body.String())
 }
 if bytes.Contains(w.Body.Bytes(),[]byte("private_key")){t.Fatal("private signer key leaked")}
}
func TestPrivateReviewerHTTPRejectsSpoofedCallerOrEconomics(t *testing.T){
 i,_,_,_:=setupIssuer(t)
 token:=strings.Repeat("a",48)
 h,e:=NewReviewerHTTPHandler(i,token);if e!=nil{t.Fatal(e)}
 for _,test:=range []struct{body,token,remote string;status int}{
  {`{"protocol":1,"operation_id":"satchel:ticket:7","amount_uwolo":"999999"}`,token,"127.0.0.1:3000",400},
  {`{"protocol":1,"protocol":1,"operation_id":"satchel:ticket:7"}`,token,"127.0.0.1:3000",400},
  {`{"protocol":1,"operation_id":"satchel:ticket:7"}`+" ",strings.Repeat("b",48),"127.0.0.1:3000",401},
  {`{"protocol":1,"operation_id":"satchel:ticket:7"}`,token,"192.0.2.1:3000",401},
  {`{"protocol":2,"operation_id":"satchel:ticket:7"}`,token,"127.0.0.1:3000",400},
  {`{"protocol":1,"operation_id":"satchel:ticket:7","bank_verified":true}`,token,"127.0.0.1:3000",400},
  {strings.Repeat("x",1100),token,"127.0.0.1:3000",413},
 }{
  w:=reviewerRequest(t,h,test.body,test.token,test.remote)
  if w.Code!=test.status{t.Fatalf("unexpected status %d want %d",w.Code,test.status)}
 }
}
func TestPrivateReviewerHTTPDoesNotAcceptNilIssuer(t *testing.T){
 _,e:=NewReviewerHTTPHandler(nil,strings.Repeat("a",48))
 if !errors.Is(e,ErrReviewerHeld){t.Fatal("nil issuer served approvals")}
 _,e=NewReviewerHTTPServer(nil)
 if !errors.Is(e,ErrReviewerHeld){t.Fatal("nil server bound port")}
}
