package satchelservice

// The first connected, but financially HELD, Watcher-source verification path.
//
// Independent operation must be provided by two separately audited trust
// domains: a signed Watcher receipt with a pinned offline-governed public key
// and authenticated original replay bytes, NOT an app/SQL-provided digest.
// Constructor injection here is testable source wiring, not operator attestation.
// Bank/liability/fee authentication remains deliberately ErrReviewerHeld.
import (
 "context"
 "crypto/ed25519"
 "crypto/sha256"
 "encoding/hex"
 "errors"
 "io"
 "time"
)

const reviewerMaxRawReplayBytes int64 = 64 << 20

// Implementations must establish and audit the origin of the SIGNED receipt.
// The API caller cannot supply the receipt in the financial review request.
type ReviewerSignedWatcherReceiptReader interface {
 FetchOriginalWitness(context.Context, string) (ReviewerWatcherWitness,error)
}

// This reader must obtain the ORIGINAL raw replay from a separately
// authenticated, source-pinned replay archive. A SHA returned by the same
// signed receipt, HD database, or caller is not independent proof.
type ReviewerOriginalReplayReader interface {
 OpenAuthenticatedReplay(context.Context, ReviewerWatcherCandidate) (io.ReadCloser,error)
}

// This implementation deliberately cannot authenticate a replay's real-world
// source by itself. That requires independent deployment/source certification.
type ReviewerIndependentWatcherSource struct {
 *ReviewerReadOnlyPGSource
 witness ReviewerSignedWatcherReceiptReader
 replay ReviewerOriginalReplayReader
 trustedKey ed25519.PublicKey
 now func()time.Time
}

func NewReviewerIndependentWatcherSource(
 pg *ReviewerReadOnlyPGSource,
 witness ReviewerSignedWatcherReceiptReader,
 replay ReviewerOriginalReplayReader,
 publicKey ed25519.PublicKey,
)(*ReviewerIndependentWatcherSource,error){
 if pg==nil||pg.db==nil||witness==nil||replay==nil||
  len(publicKey)!=ed25519.PublicKeySize {
  return nil,ErrReviewerHeld
 }
 return &ReviewerIndependentWatcherSource{
  ReviewerReadOnlyPGSource:pg,
  witness:witness,replay:replay,
  trustedKey:append(ed25519.PublicKey(nil),publicKey...),
  now:time.Now,
 },nil
}

// Hash bounded ORIGINAL bytes here instead of accepting any declared digest.
// Read failures, short/empty, oversize data and close errors all hold. A
// corrupted/truncated replay must never be represented as authenticated.
func reviewerHashOriginalReplay(ctx context.Context, reader ReviewerOriginalReplayReader,
 candidate ReviewerWatcherCandidate)(string,error){
 if reader==nil||ctx==nil||ctx.Err()!=nil{return "",ErrReviewerHeld}
 raw,e:=reader.OpenAuthenticatedReplay(ctx,candidate)
 if e!=nil||raw==nil{return "",ErrReviewerHeld}
 digest:=sha256.New()
 n,readErr:=io.CopyN(digest,raw,reviewerMaxRawReplayBytes+1)
 closeErr:=raw.Close()
 if (readErr!=nil&&!errors.Is(readErr,io.EOF))||
  closeErr!=nil||n<=0||n>reviewerMaxRawReplayBytes||ctx.Err()!=nil{
  return "",ErrReviewerHeld
 }
 return hex.EncodeToString(digest.Sum(nil)),nil
}

// A unit-testable, non-spending verification primitive. The signer must
// still obtain a separately authenticated bank+global liabilities census.
func VerifyIndependentReviewerWatcher(
 ctx context.Context,candidate ReviewerWatcherCandidate,
 witness ReviewerSignedWatcherReceiptReader,
 replay ReviewerOriginalReplayReader,
 pinnedKey ed25519.PublicKey,
 now time.Time,
)error{
 if ctx==nil||ctx.Err()!=nil||witness==nil||replay==nil||
  len(pinnedKey)!=ed25519.PublicKeySize{return ErrReviewerHeld}
 ctx,cancel:=context.WithTimeout(ctx,3*time.Second)
 defer cancel()
 receipt,e:=witness.FetchOriginalWitness(ctx,candidate.OriginalOperationID)
 if e!=nil||ctx.Err()!=nil{return ErrReviewerHeld}
 replayHash,e:=reviewerHashOriginalReplay(ctx,replay,candidate)
 if e!=nil||ctx.Err()!=nil{return ErrReviewerHeld}
 if VerifyReviewerWatcherWitness(candidate,receipt,pinnedKey,replayHash,now)!=nil{
  return ErrReviewerHeld
 }
 return nil
}

// This source may pass the independent WATCHER check only if the exact
// original PostgreSQL market is unchanged throughout an independently signed
// and bytes-verified raw-replay read. It does NOT clear the finance gate.
func (s *ReviewerIndependentWatcherSource)VerifyWatcherMarket(
 ctx context.Context,wager WagerReservation)error{
 if s==nil||s.ReviewerReadOnlyPGSource==nil||s.now==nil||
  ctx==nil||ctx.Err()!=nil{return ErrReviewerHeld}
 candidate,e:=s.InspectWatcherMarket(ctx,wager)
 if e!=nil{return ErrReviewerHeld}
 if VerifyIndependentReviewerWatcher(ctx,candidate,s.witness,s.replay,s.trustedKey,s.now())!=nil{
  return ErrReviewerHeld
 }
 // Reinspect current original financial source immediately after external
 // replay proof: no change to owner, roster, game, market or cutoff allowed.
 fresh,e:=s.InspectWatcherMarket(ctx,wager)
 if e!=nil||fresh!=candidate||ctx.Err()!=nil{return ErrReviewerHeld}
 return nil
}

// Embedded AuthenticatedFeeCensus still ALWAYS returns ErrReviewerHeld.
// No production financial release capability can emerge from this adapter.
var _ ReviewerEvidenceSource = (*ReviewerIndependentWatcherSource)(nil)
