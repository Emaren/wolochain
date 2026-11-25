package satchelservice

// Strict cross-language verifier for the persisted HD wager authorization.
// It recomputes the *exact* three hashes from the existing TypeScript
// buildSatchelWagerAuthorization contract. Hash agreement is an integrity
// prerequisite, NOT a database authentication or spend approval.
import (
 "bytes"
 "crypto/sha256"
 "encoding/hex"
 "encoding/json"
 "errors"
 "io"
 "regexp"
 "strconv"
 "strings"
)

var ErrReviewerHDOrigin = errors.New("reviewer_hd_original_authorization_refused")
var reviewerHexDigest = regexp.MustCompile(`^[a-f0-9]{64}$`)
var reviewerDecimal = regexp.MustCompile(`^(0|[1-9][0-9]{0,18})$`)

type ReviewerHDOriginColumns struct {
 OperationID string
 ReservationID string
 OwnerUserID int64
 ReservationDigest string
 LedgerRevision string
 ConsentDigest string
}
type ReviewerHDOriginResult struct {
 OperationID string
 ReservationID string
 OwnerUserID int64
 OwnerUID string
 OwnerWallet string
 Vault string
 Recipient string
 AmountUWolo string
 Memo string
 PresetID int64
 PresetVersion int64
 TicketID int64
 ConsentID string
 ChallengeText string
 OwnerSignatureJSON any
 GameIdentityKey string
 PropositionHash string
 AvailableUWolo string
 ReservedUWolo string
 LedgerVersion string
 JournalID string
 Legs []ReviewerHDLeg
 ReservationDigest string
 LedgerRevision string
 ConsentDigest string
}
type ReviewerHDLeg struct {
 ID, MarketID, AmountWolo int64
 Side, PropositionHash string
}
var reviewerTopKeys = []string{
 "executionId","ownerUserId","ownerUid","ownerWallet","reservationId",
 "operationId","ticketId","vault","recipient","amountUwolo","memo",
 "gameIdentityKey","propositionHash","presetId","presetVersion",
 "consentId","challengeText","ownerSignatureJson","ledgerVersion",
 "availableUwolo","reservedUwolo","journalId","legs",
}
func reviewerValue(dec *json.Decoder,depth int)(any,error){
 if depth>12{return nil,ErrReviewerHDOrigin}
 token,err:=dec.Token()
 if err!=nil{return nil,ErrReviewerHDOrigin}
 switch x:=token.(type){
 case json.Delim:
  switch x {
  case '{':
   fields:=map[string]any{}
   for dec.More(){
    token,err:=dec.Token();if err!=nil{return nil,ErrReviewerHDOrigin}
    key,ok:=token.(string);if !ok||len(key)>128||strings.ContainsAny(key,"\u2028\u2029"){
     return nil,ErrReviewerHDOrigin
    }
    if _,exists:=fields[key];exists{return nil,ErrReviewerHDOrigin}
    val,e:=reviewerValue(dec,depth+1);if e!=nil{return nil,e}
    fields[key]=val
    if len(fields)>96{return nil,ErrReviewerHDOrigin}
   }
   ending,e:=dec.Token()
   if e!=nil||ending!=json.Delim('}'){return nil,ErrReviewerHDOrigin}
   return fields,nil
  case '[':
   entries:=[]any{}
   for dec.More(){
    v,e:=reviewerValue(dec,depth+1);if e!=nil{return nil,e}
    entries=append(entries,v);if len(entries)>32{return nil,ErrReviewerHDOrigin}
   }
   ending,e:=dec.Token()
   if e!=nil||ending!=json.Delim(']'){return nil,ErrReviewerHDOrigin}
   return entries,nil
  default:return nil,ErrReviewerHDOrigin
  }
 case string:
  if len(x)>8192||strings.ContainsAny(x,"\u2028\u2029"){return nil,ErrReviewerHDOrigin}
  return x,nil
 case json.Number:
  if !reviewerDecimal.MatchString(string(x)){return nil,ErrReviewerHDOrigin}
  n,e:=strconv.ParseInt(string(x),10,64)
  if e!=nil||n>9007199254740991{return nil,ErrReviewerHDOrigin}
  return n,nil
 case bool: return x,nil
 case nil:return nil,nil
 default:return nil,ErrReviewerHDOrigin
 }
}
func reviewerStrictJSON(raw []byte)(any,error){
 if len(raw)==0||len(raw)>16384{return nil,ErrReviewerHDOrigin}
 dec:=json.NewDecoder(bytes.NewReader(raw));dec.UseNumber()
 val,err:=reviewerValue(dec,0)
 if err!=nil{return nil,err}
 if _,err:=dec.Token();err!=io.EOF{return nil,ErrReviewerHDOrigin}
 return val,nil
}
func reviewerCanonicalHash(values any)(string,error){
 var b bytes.Buffer
 encoder:=json.NewEncoder(&b);encoder.SetEscapeHTML(false)
 if err:=encoder.Encode(values);err!=nil{return "",ErrReviewerHDOrigin}
 sum:=sha256.Sum256(bytes.TrimSuffix(b.Bytes(),[]byte("\n")))
 return hex.EncodeToString(sum[:]),nil
}
func reviewerRecord(m map[string]any,keys []string)bool{
 if len(m)!=len(keys){return false}
 for _,key:=range keys{if _,ok:=m[key];!ok{return false}}
 return true
}
func reviewerStr(m map[string]any,key string)string{
 s,_:=m[key].(string);return s
}
func reviewerInt(m map[string]any,key string)int64{
 n,_:=m[key].(int64);return n
}
func reviewerUnsignedDecimal(s string,allowZero bool,max uint64)bool{
 if !reviewerDecimal.MatchString(s){return false}
 n,e:=strconv.ParseUint(s,10,64)
 return e==nil&&n<=max&&(allowZero||n>0)
}

// VerifyReviewerHDOrigin recomputes the exact SHA256 hashes authored by
// app/lib/warSatchelWagerAuthorization.ts from original JSONB. It refuses
// duplicate keys, extra fields, malformed/inflated integers, changed ticket
// legs, owner/custody mismatch and stored digest substitution.
func VerifyReviewerHDOrigin(raw []byte,stored ReviewerHDOriginColumns)(ReviewerHDOriginResult,error){
 bad:=func()(ReviewerHDOriginResult,error){return ReviewerHDOriginResult{},ErrReviewerHDOrigin}
 v,e:=reviewerStrictJSON(raw);if e!=nil{return bad()}
 m,ok:=v.(map[string]any);if !ok||!reviewerRecord(m,reviewerTopKeys){return bad()}
 execution:=reviewerInt(m,"executionId")
 owner:=reviewerInt(m,"ownerUserId")
 ticket:=reviewerInt(m,"ticketId")
 preset:=reviewerInt(m,"presetId")
 version:=reviewerInt(m,"presetVersion")
 operation:=reviewerStr(m,"operationId")
 reserve:=reviewerStr(m,"reservationId")
 uid:=reviewerStr(m,"ownerUid")
 vault:=reviewerStr(m,"vault")
 escrow:=reviewerStr(m,"recipient")
 wallet:=reviewerStr(m,"ownerWallet")
 amount:=reviewerStr(m,"amountUwolo")
 memo:=reviewerStr(m,"memo")
 prop:=reviewerStr(m,"propositionHash")
 if execution<1||owner<1||ticket<1||preset<1||version<1||
  !wagerIDs.MatchString(operation)||operation!="satchel:ticket:"+strconv.FormatInt(execution,10)||
  reserve!="satchel:reserve:"+strconv.FormatInt(execution,10)||
  memo!="AoE2HDBets bet ticket v1 · ticket "+strconv.FormatInt(ticket,10)||
  operation!=stored.OperationID||reserve!=stored.ReservationID||owner!=stored.OwnerUserID||
  !ownerUIDPattern.MatchString(uid)||!validAddress(wallet)||!validAddress(vault)||
  !validAddress(escrow)||vault==escrow||
  !reviewerUnsignedDecimal(amount,false,ProductMaxWagerUWolo)||
  !reviewerHexDigest.MatchString(prop)||reviewerStr(m,"gameIdentityKey")==""||
  len(reviewerStr(m,"gameIdentityKey"))>255||
  reviewerStr(m,"challengeText")==""||
  reviewerStr(m,"consentId")==""||
  !reviewerUnsignedDecimal(reviewerStr(m,"ledgerVersion"),true,9223372036854775807)||
  !reviewerUnsignedDecimal(reviewerStr(m,"availableUwolo"),true,9223372036854775807)||
  !reviewerUnsignedDecimal(reviewerStr(m,"reservedUwolo"),true,9223372036854775807)||
  !reviewerUnsignedDecimal(reviewerStr(m,"journalId"),false,9223372036854775807) {
  return bad()
 }
 legsRaw,ok:=m["legs"].([]any);if !ok||len(legsRaw)<1||len(legsRaw)>2{return bad()}
 legs:=make([]ReviewerHDLeg,0,len(legsRaw));seen:=map[int64]bool{}
 total:=int64(0)
 for _,entry:=range legsRaw{
  v,ok:=entry.(map[string]any)
  if !ok||!reviewerRecord(v,[]string{"id","marketId","side","amountWolo","propositionHash"}){return bad()}
  id,market,stake:=reviewerInt(v,"id"),reviewerInt(v,"marketId"),reviewerInt(v,"amountWolo")
  side,hash:=reviewerStr(v,"side"),reviewerStr(v,"propositionHash")
  if id<1||market<1||stake<1||stake>ProductMaxWagerWOLO||seen[id]||hash!=prop||
   (side!="left"&&side!="right"){return bad()}
  seen[id]=true;total+=stake
  legs=append(legs,ReviewerHDLeg{ID:id,MarketID:market,AmountWolo:stake,Side:side,PropositionHash:hash})
 }
 stated,e:=strconv.ParseInt(amount,10,64)
 if e!=nil||total*1000000!=stated{return bad()}
 signature,ok:=m["ownerSignatureJson"].(map[string]any)
 if !ok||!reviewerRecord(signature,[]string{"pub_key","signature"}){return bad()}
 pub,ok:=signature["pub_key"].(map[string]any)
 if !ok||!reviewerRecord(pub,[]string{"type","value"})||
  reviewerStr(pub,"type")!="tendermint/PubKeySecp256k1"||
  reviewerStr(pub,"value")==""||reviewerStr(signature,"signature")==""{return bad()}
 // Go encoding/json emits map keys in sorted lexical order, matching HD's
 // recursive canonical() for source ASCII field names.
 consent,e:=reviewerCanonicalHash([]any{
  "aoe2war/satchel/hd-wager-consent/v1",reviewerStr(m,"consentId"),
  reviewerStr(m,"challengeText"),m["ownerSignatureJson"]})
 if e!=nil{return bad()}
 ledger,e:=reviewerCanonicalHash([]any{"aoe2war/satchel/hd-wager-ledger/v1",
  owner,reviewerStr(m,"ledgerVersion"),reviewerStr(m,"availableUwolo"),
  reviewerStr(m,"reservedUwolo"),reviewerStr(m,"journalId")})
 if e!=nil{return bad()}
 reservation,e:=reviewerCanonicalHash([]any{"aoe2war/satchel/hd-wager-reservation/v1",m,consent,ledger})
 if e!=nil||consent!=stored.ConsentDigest||ledger!=stored.LedgerRevision||
  reservation!=stored.ReservationDigest||!reviewerHexDigest.MatchString(consent)||
  !reviewerHexDigest.MatchString(ledger)||!reviewerHexDigest.MatchString(reservation){return bad()}
 return ReviewerHDOriginResult{
  OperationID:operation,ReservationID:reserve,OwnerUserID:owner,OwnerUID:uid,
  OwnerWallet:wallet,Vault:vault,Recipient:escrow,AmountUWolo:amount,Memo:memo,
  PresetID:preset,PresetVersion:version,TicketID:ticket,
  ConsentID:reviewerStr(m,"consentId"),ChallengeText:reviewerStr(m,"challengeText"),
  OwnerSignatureJSON:signature,GameIdentityKey:reviewerStr(m,"gameIdentityKey"),
  PropositionHash:prop,AvailableUWolo:reviewerStr(m,"availableUwolo"),
  ReservedUWolo:reviewerStr(m,"reservedUwolo"),LedgerVersion:reviewerStr(m,"ledgerVersion"),
  JournalID:reviewerStr(m,"journalId"),Legs:legs,
  ConsentDigest:consent,LedgerRevision:ledger,ReservationDigest:reservation,
 },nil
}
