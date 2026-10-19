package satchelservice

// Private loopback 8095 request/receipt transport for the independent reviewer.
// The bearer authenticates the caller only. Neither caller nor token may
// choose an approval, amount, fee, evidence source, chain or signing key.
import (
 "context"
 "crypto/sha256"
 "crypto/subtle"
 "encoding/json"
 "io"
 "net"
 "net/http"
 "time"
)

const reviewerHTTPPath="/reviewer/v1/wagers"
type reviewerHTTPHandler struct {
 issuer *ReviewerIssuer
 tokenHash [32]byte
 slots chan struct{}
}
func NewReviewerHTTPHandler(issuer *ReviewerIssuer,token string)(http.Handler,error){
 if issuer==nil||issuer.db==nil||!httpTokenPattern.MatchString(token){
  return nil,ErrReviewerHeld
 }
 return &reviewerHTTPHandler{issuer:issuer,tokenHash:sha256.Sum256([]byte(token)),slots:make(chan struct{},4)},nil
}
func NewReviewerHTTPServer(handler http.Handler)(*http.Server,error){
 if handler==nil{return nil,ErrReviewerHeld}
 return NewPrivateHTTPServer("127.0.0.1:8095",handler)
}
func reviewerDecodeRequest(body io.Reader)(string,error){
 d:=json.NewDecoder(io.LimitReader(body,1025))
 first,err:=d.Token()
 if err!=nil||first!=json.Delim('{'){return "",ErrReviewerHeld}
 seen:=map[string]bool{}
 var id string
 var protocol int
 for d.More(){
  keyToken,err:=d.Token()
  key,ok:=keyToken.(string)
  if err!=nil||!ok||seen[key]||(key!="protocol"&&key!="operation_id"){return "",ErrReviewerHeld}
  seen[key]=true
  if key=="protocol"{if d.Decode(&protocol)!=nil{return "",ErrReviewerHeld}
  }else{if d.Decode(&id)!=nil{return "",ErrReviewerHeld}}
 }
 closeToken,err:=d.Token()
 if err!=nil||closeToken!=json.Delim('}')||!seen["protocol"]||!seen["operation_id"]||
  protocol!=1||!wagerIDs.MatchString(id){return "",ErrReviewerHeld}
 var rest any
 if d.Decode(&rest)!=io.EOF{return "",ErrReviewerHeld}
 return id,nil
}
func (h *reviewerHTTPHandler)ServeHTTP(w http.ResponseWriter,r *http.Request){
 w.Header().Set("Cache-Control","no-store")
 w.Header().Set("Content-Type","application/json")
 w.Header().Set("X-Content-Type-Options","nosniff")
 if r.URL.Path!=reviewerHTTPPath||r.URL.RawQuery!=""||r.URL.RawPath!=""{
  http.Error(w,"reviewer_route_unavailable",http.StatusNotFound);return
 }
 if r.Method!=http.MethodPost{http.Error(w,"method_not_allowed",http.StatusMethodNotAllowed);return}
 host,_,err:=net.SplitHostPort(r.RemoteAddr)
 ip:=net.ParseIP(host)
 secret:=r.Header.Get("Authorization")
 if err!=nil||ip==nil||!ip.IsLoopback()||
  len(secret)<len("Bearer ")||secret[:len("Bearer ")]!="Bearer "||
  !httpTokenPattern.MatchString(secret[len("Bearer "):])||
  subtle.ConstantTimeCompare(h.tokenHash[:],hashReviewerToken(secret[len("Bearer "):]))!=1{
  http.Error(w,"private_authentication_required",http.StatusUnauthorized);return
 }
 if r.Header.Get("Content-Type")!="application/json"{
  http.Error(w,"invalid_content_type",http.StatusBadRequest);return
 }
 if r.ContentLength>1024{http.Error(w,"invalid_request_size",http.StatusRequestEntityTooLarge);return}
 select{case h.slots<-struct{}{}:defer func(){<-h.slots}()
 default:http.Error(w,"reviewer_busy",http.StatusServiceUnavailable);return}
 ctx,cancel:=context.WithTimeout(r.Context(),4*time.Second)
 defer cancel()
 id,e:=reviewerDecodeRequest(http.MaxBytesReader(w,r.Body,1024))
 if e!=nil{http.Error(w,"invalid_private_request",http.StatusBadRequest);return}
 reply:=h.issuer.ReviewOne(ctx,id)
 if json.NewEncoder(w).Encode(reply)!=nil{return}
}
func hashReviewerToken(s string)[]byte{
 h:=sha256.Sum256([]byte(s));return h[:]
}
