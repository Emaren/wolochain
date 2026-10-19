package satchelservice

// Pre-bet live Watcher verification (finance HELD). Never require the
// completed/final replay archive to bet during a live Age of Empires 2 game.
// Only a frozen, independently witnessed pre-bet checkpoint may be signed.
// Source-interface injection does NOT authenticate a production event source.
import (
 "context"
 "crypto/ed25519"
 "crypto/sha256"
 "encoding/hex"
 "errors"
 "io"
 "time"
)

const reviewerMaxLiveCheckpointBytes int64 = 64 << 20

type ReviewerSignedLiveWatcherReader interface {
 FetchOriginalLiveWitness(context.Context,string)(ReviewerWatcherLiveWitness,error)
}
type ReviewerIndependentLiveCheckpointReader interface {
 OpenAuthenticatedLiveCheckpoint(context.Context,ReviewerWatcherCandidate)(io.ReadCloser,error)
}

type ReviewerIndependentWatcherSource struct {
 *ReviewerReadOnlyPGSource
 witness ReviewerSignedLiveWatcherReader
 checkpoint ReviewerIndependentLiveCheckpointReader
 trustedKey ed25519.PublicKey
 now func()time.Time
}

func NewReviewerIndependentWatcherSource(
 pg *ReviewerReadOnlyPGSource,
 witness ReviewerSignedLiveWatcherReader,
 checkpoint ReviewerIndependentLiveCheckpointReader,
 publicKey ed25519.PublicKey,
)(*ReviewerIndependentWatcherSource,error){
 if pg==nil||pg.db==nil||witness==nil||checkpoint==nil||
  len(publicKey)!=ed25519.PublicKeySize {return nil,ErrReviewerHeld}
 return &ReviewerIndependentWatcherSource{
  ReviewerReadOnlyPGSource:pg,witness:witness,checkpoint:checkpoint,
  trustedKey:append(ed25519.PublicKey(nil),publicKey...),now:time.Now,
 },nil
}

// Hash ORIGINAL CAPTURED GAME-START bytes here. Empty, truncated, oversize,
// failed/corrupt or unfinalized captures are denied. A completed replay isn't
// available in time for V1 auto betting and must not be used as an input.
func reviewerHashLiveCheckpoint(
 ctx context.Context,provider ReviewerIndependentLiveCheckpointReader,
 candidate ReviewerWatcherCandidate)(string,error){
 if ctx==nil||ctx.Err()!=nil||provider==nil{return "",ErrReviewerHeld}
 raw,e:=provider.OpenAuthenticatedLiveCheckpoint(ctx,candidate)
 if e!=nil||raw==nil{return "",ErrReviewerHeld}
 digest:=sha256.New()
 n,readErr:=io.CopyN(digest,raw,reviewerMaxLiveCheckpointBytes+1)
 closeErr:=raw.Close()
 if (readErr!=nil&&!errors.Is(readErr,io.EOF))||
  closeErr!=nil||n<=0||n>reviewerMaxLiveCheckpointBytes||
  ctx.Err()!=nil{return "",ErrReviewerHeld}
 return hex.EncodeToString(digest.Sum(nil)),nil
}

func VerifyIndependentReviewerLiveWatcher(
 ctx context.Context,c ReviewerWatcherCandidate,
 witness ReviewerSignedLiveWatcherReader,
 checkpoint ReviewerIndependentLiveCheckpointReader,
 pinnedKey ed25519.PublicKey,now time.Time,
)error{
 if ctx==nil||ctx.Err()!=nil||witness==nil||checkpoint==nil||
  len(pinnedKey)!=ed25519.PublicKeySize{return ErrReviewerHeld}
 started:=time.Now()
 ctx,cancel:=context.WithTimeout(ctx,3*time.Second)
 defer cancel()
 proof,e:=witness.FetchOriginalLiveWitness(ctx,c.OriginalOperationID)
 if e!=nil||ctx.Err()!=nil{return ErrReviewerHeld}
 originalDigest,e:=reviewerHashLiveCheckpoint(ctx,checkpoint,c)
 if e!=nil||ctx.Err()!=nil{return ErrReviewerHeld}
 // A signed live checkpoint can expire DURING source I/O. The caller's
 // original wall clock is advanced using monotonic elapsed time before
 // verifying the TTL; never approve a stale receipt on a slow archive read.
 verifiedAt:=now.Add(time.Since(started))
 if VerifyReviewerWatcherLiveWitness(c,proof,pinnedKey,originalDigest,verifiedAt)!=nil{
  return ErrReviewerHeld
 }
 return nil
}

func (s *ReviewerIndependentWatcherSource)VerifyWatcherMarket(
 ctx context.Context,wager WagerReservation)error{
 if s==nil||s.ReviewerReadOnlyPGSource==nil||s.now==nil||
  ctx==nil||ctx.Err()!=nil{return ErrReviewerHeld}
 candidate,e:=s.InspectWatcherMarket(ctx,wager)
 if e!=nil{return ErrReviewerHeld}
 if VerifyIndependentReviewerLiveWatcher(
  ctx,candidate,s.witness,s.checkpoint,s.trustedKey,s.now())!=nil{return ErrReviewerHeld}
 // A replay verifier is NOT allowed to approve a changed live market.
 fresh,e:=s.InspectWatcherMarket(ctx,wager)
 if e!=nil||fresh!=candidate||ctx.Err()!=nil{return ErrReviewerHeld}
 return nil
}

// AuthenticatedFeeCensus is inherited from PG and always ErrReviewerHeld.
// Distinct bank/liability/gas release authority remains unavailable.
var _ ReviewerEvidenceSource = (*ReviewerIndependentWatcherSource)(nil)
