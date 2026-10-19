package satchelservice

// The independent 8095 reviewer issuer is separated from the 8094 Cosmos
// custody signer. The ONLY signed bytes are WagerReservationMessage for an
// original owner-bound HD reservation. No chain keys, wallet RPC or broadcast.
// This library alone is NOT a production evidence loader or release authority.
import (
 "bytes"
 "context"
 "crypto/ed25519"
 "crypto/sha256"
 "encoding/base64"
 "encoding/hex"
 "encoding/json"
 "errors"
 "os"
 "sync"
 "time"

 bolt "go.etcd.io/bbolt"
)

var reviewerIssues = []byte("independent-wager-issues-v1")
var ErrReviewerHeld = errors.New("independent_reviewer_held")

// A production implementation must READ, not accept request-supplied facts.
// The adapters MUST independently verify each Keplr proof, game and market
// authority, Comet trust and the complete global financial producer census.
type ReviewerEvidenceSource interface {
 OriginalHold(context.Context, string) (WagerReservation, error)
 VerifyOwnerMandate(context.Context, WagerReservation) error
 VerifyWatcherMarket(context.Context, WagerReservation) error
 AuthenticatedFeeCensus(context.Context, WagerReservation) (ReviewerFeeCensus, error)
}
type ReviewerIssuedReply struct {
 Protocol int `json:"protocol"`
 Status string `json:"status"`
 OperationID string `json:"operation_id"`
 Approval *WagerReservation `json:"approval,omitempty"`
}
type reviewerEntry struct {
 Fingerprint string `json:"fingerprint"`
 Status string `json:"status"` // PENDING or SIGNED; PENDING never auto-reissued after crash
 Approval *WagerReservation `json:"approval,omitempty"`
}
type ReviewerIssuer struct {
 mu sync.Mutex
 db *bolt.DB
 source ReviewerEvidenceSource
 key ed25519.PrivateKey
 policy Policy
 now func()time.Time
}

// OpenReviewerIssuer does not create, import or export a reviewer signing key.
// It requires separate key custody and a private dedicated state file. It does
// not open a listener or any chain connection.
func OpenReviewerIssuer(statePath string, source ReviewerEvidenceSource, key ed25519.PrivateKey, policy Policy) (*ReviewerIssuer,error) {
 if statePath=="" || source==nil || len(key)!=ed25519.PrivateKeySize ||
  len(policy.WagerApprovalKey)!=ed25519.PublicKeySize ||
  len(policy.WithdrawalApprovalKey)!=ed25519.PublicKeySize ||
  bytes.Equal(policy.WagerApprovalKey,policy.WithdrawalApprovalKey) ||
  !bytes.Equal(key.Public().(ed25519.PublicKey),policy.WagerApprovalKey) ||
  !validAddress(policy.Vault) || !validAddress(policy.BettingEscrow) ||
  policy.Vault==policy.BettingEscrow || policy.MaxAmountUWolo==0 {
  return nil,ErrReviewerHeld
 }
 // Refuse symlinks, preexisting world/group-readable material and directories.
 if st,e:=os.Lstat(statePath);e==nil {
  if !st.Mode().IsRegular() || st.Mode().Perm()&0077!=0 {return nil,ErrReviewerHeld}
 } else if !os.IsNotExist(e) {return nil,ErrReviewerHeld}
 db,e:=bolt.Open(statePath,0600,&bolt.Options{Timeout:100*time.Millisecond,NoFreelistSync:false})
 if e!=nil {return nil,ErrReviewerHeld}
 e=db.Update(func(tx *bolt.Tx)error{_,err:=tx.CreateBucketIfNotExists(reviewerIssues);return err})
 if e!=nil {_=db.Close();return nil,ErrReviewerHeld}
 return &ReviewerIssuer{db:db,source:source,key:append(ed25519.PrivateKey(nil),key...),policy:policy,now:time.Now},nil
}
func (r *ReviewerIssuer)Close()error{
 if r==nil {return nil}
 r.mu.Lock();defer r.mu.Unlock()
 if r.db==nil {return nil}
 e:=r.db.Close();r.db=nil
 for i:=range r.key{r.key[i]=0}
 return e
}
func reviewerFingerprint(a WagerReservation)string{
 // Signature is excluded; only original immutable financial identity persists.
 a.Signature=""
 sum:=sha256.Sum256(WagerReservationMessage(a))
 return hex.EncodeToString(sum[:])
}
func (r *ReviewerIssuer) loadEntry(id string)(reviewerEntry,error){
 var entry reviewerEntry
 e:=r.db.View(func(tx *bolt.Tx)error{
  raw:=tx.Bucket(reviewerIssues).Get([]byte(id))
  if raw==nil{return nil}
  if json.Unmarshal(raw,&entry)!=nil || entry.Fingerprint=="" ||
   (entry.Status!="PENDING" && entry.Status!="SIGNED") ||
   (entry.Status=="SIGNED" && entry.Approval==nil){return ErrReviewerHeld}
  return nil
 })
 return entry,e
}
func (r *ReviewerIssuer)writeEntry(id string,e reviewerEntry,expected string)error{
 return r.db.Update(func(tx *bolt.Tx)error{
  bucket:=tx.Bucket(reviewerIssues)
  old:=bucket.Get([]byte(id))
  if expected=="" {if old!=nil{return ErrReviewerHeld}
  }else{
   var present reviewerEntry
   if old==nil || json.Unmarshal(old,&present)!=nil ||
    present.Fingerprint!=e.Fingerprint || present.Status!=expected{return ErrReviewerHeld}
  }
  data,err:=json.Marshal(e);if err!=nil{return ErrReviewerHeld}
  return bucket.Put([]byte(id),data)
 })
}
func reviewerPending(id string)ReviewerIssuedReply{
 return ReviewerIssuedReply{Protocol:1,Status:"PENDING",OperationID:id}
}
// ReviewOne always rechecks independent sources before revealing any existing
// signed review. A prior PENDING, including a crash between durable fence and
// signature, stays PENDING forever until separately witnessed recovery.
// This is an *approval*, NOT a transfer; no retry of chain sends is possible.
func (r *ReviewerIssuer)ReviewOne(ctx context.Context,id string)ReviewerIssuedReply {
 pending:=reviewerPending(id)
 if r==nil || !wagerIDs.MatchString(id)||ctx.Err()!=nil{return pending}
 r.mu.Lock();defer r.mu.Unlock()
 if r.db==nil{return pending}
 original,err:=r.source.OriginalHold(ctx,id)
 if err!=nil||ctx.Err()!=nil||original.OperationID!=id||
  original.Version!=1||original.Signature!=""||
  original.Vault!=r.policy.Vault||original.Recipient!=r.policy.BettingEscrow||
  original.Memo!="AoE2HDBets bet ticket v1 · ticket "+id[len("satchel:ticket:"):] ||
  !nonzeroDigest(original.ReservationDigest)||!nonzeroDigest(original.LedgerRevision)||
  !nonzeroDigest(original.ConsentDigest)||!ownerUIDPattern.MatchString(original.OwnerID) {
  return pending
 }
 // Time and fee are derived from trusted evidence, never request body.
 if r.source.VerifyOwnerMandate(ctx,original)!=nil ||
  r.source.VerifyWatcherMarket(ctx,original)!=nil ||ctx.Err()!=nil{return pending}
 census,err:=r.source.AuthenticatedFeeCensus(ctx,original)
 if err!=nil||ctx.Err()!=nil{return pending}
 budget,err:=AssessReviewerFeeBudget(census,original)
 if err!=nil||budget.Status!="BUDGET_SUFFICIENT_NONAUTHORIZING" ||
  budget.SpendingAuthorized||budget.BankAuthenticated||budget.OwnerLedgerAuthenticated{return pending}
 // Re-read AFTER the first independent bank/fee census. A revocation,
 // closed market, changed immutable hold or drained gas reserve that appears
 // while the earlier source calls run must not become a signed approval.
 // This is an additional *final pre-sign source fence*, not an atomic
 // financial checkpoint or authenticated bank proof. Production remains
 // HOLD until the externally governed evidence authority establishes those.
 fresh,err:=r.source.OriginalHold(ctx,id)
 if err!=nil||ctx.Err()!=nil||fresh.OperationID!=id||
  fresh.Version!=1||fresh.Signature!=""||
  fresh.IssuedAt!=0||fresh.ExpiresAt!=0||
  reviewerFingerprint(fresh)!=reviewerFingerprint(original)||
  fresh.Vault!=r.policy.Vault||fresh.Recipient!=r.policy.BettingEscrow||
  r.source.VerifyOwnerMandate(ctx,fresh)!=nil||
  r.source.VerifyWatcherMarket(ctx,fresh)!=nil||ctx.Err()!=nil {
  return pending
 }
 freshCensus,err:=r.source.AuthenticatedFeeCensus(ctx,fresh)
 if err!=nil||ctx.Err()!=nil{return pending}
 finalBudget,err:=AssessReviewerFeeBudget(freshCensus,fresh)
 if err!=nil||finalBudget.Status!="BUDGET_SUFFICIENT_NONAUTHORIZING"||
  finalBudget.SpendingAuthorized||finalBudget.BankAuthenticated||
  finalBudget.OwnerLedgerAuthenticated{return pending}
 // Preserve the final-read values: never sign a superseded initial snapshot.
 original=fresh
 now:=r.now().Unix()
 // The source fingerprint EXCLUDES authority timestamps. It must remain
 // invariant over repeated lookups: an old approval cannot be renewed.
 if original.IssuedAt!=0||original.ExpiresAt!=0{return pending}
 fingerprint:=reviewerFingerprint(original)
 original.IssuedAt=now;original.ExpiresAt=now+60
 current,err:=r.loadEntry(id)
 if err!=nil{return pending}
 if current.Fingerprint!=""{
  if current.Fingerprint!=fingerprint||current.Status!="SIGNED"||
   current.Approval==nil||current.Approval.ExpiresAt<=now{return pending}
  check:=TransferRequest{OperationID:id,OwnerID:current.Approval.OwnerID,ChainID:"wolo-1",
   Denom:"uwolo",Sender:current.Approval.Vault,Recipient:current.Approval.Recipient,
   AmountUWolo:current.Approval.AmountUWolo,Memo:current.Approval.Memo,Kind:"wager",Reservation:current.Approval}
  if r.policy.verifyWager(check,r.now())!=nil{return pending}
  return ReviewerIssuedReply{Protocol:1,Status:"SIGNED",OperationID:id,Approval:current.Approval}
 }
 // The durable PENDING intent is synced BEFORE Ed25519 signing.
 if r.writeEntry(id,reviewerEntry{Fingerprint:fingerprint,Status:"PENDING"},"")!=nil{return pending}
 if ctx.Err()!=nil{return pending}
 original.Signature=base64.StdEncoding.EncodeToString(ed25519.Sign(r.key,WagerReservationMessage(original)))
 request:=TransferRequest{OperationID:id,OwnerID:original.OwnerID,ChainID:"wolo-1",
  Denom:"uwolo",Sender:original.Vault,Recipient:original.Recipient,
  AmountUWolo:original.AmountUWolo,Memo:original.Memo,Kind:"wager",Reservation:&original}
 if r.policy.verifyWager(request,r.now())!=nil||ctx.Err()!=nil{return pending}
 if r.writeEntry(id,reviewerEntry{Fingerprint:fingerprint,Status:"SIGNED",Approval:&original},"PENDING")!=nil{return pending}
 return ReviewerIssuedReply{Protocol:1,Status:"SIGNED",OperationID:id,Approval:&original}
}
