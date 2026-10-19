package satchelservice

// The PRE-BET Watcher signature contract. A completed final replay is too
// late to authorize live Auto Betting. This v2 domain binds immutable bytes
// frozen DURING the live Watcher admission window. The existing v1 final
// replay witness remains usable only for post-game audit, never in this path.
import (
 "crypto/ed25519"
 "encoding/base64"
 "encoding/json"
 "errors"
 "time"
)

const reviewerWatcherLiveDomain = "aoe2war/satchel/live-watcher-checkpoint/v2"
var ErrReviewerLiveWitness = errors.New("reviewer_live_watcher_checkpoint_refused")

type ReviewerWatcherLiveWitness struct {
 Version int `json:"version"`
 OperationID string `json:"operation_id"`
 OwnerUID string `json:"owner_uid"`
 OwnerSteamID string `json:"owner_steam_id"`
 GameIdentityKey string `json:"game_identity_key"`
 MarketID int64 `json:"market_id"`
 SelectedSide string `json:"selected_side"`
 PropositionHash string `json:"proposition_hash"`
 LinkedSession string `json:"linked_session"`
 SourceParseIteration int64 `json:"source_parse_iteration"`
 SourceRosterHash string `json:"source_roster_hash"`
 RosterLockedAtMS int64 `json:"roster_locked_at_ms"`
 ExecutionCreatedAtMS int64 `json:"execution_created_at_ms"`
 // SHA256 of exact IMMUTABLE game-start bytes, never a final replay.
 LiveCheckpointSHA256 string `json:"live_checkpoint_sha256"`
 CapturedAtMS int64 `json:"captured_at_ms"`
 ObservedAtMS int64 `json:"observed_at_ms"`
 ExpiresAtMS int64 `json:"expires_at_ms"`
 Signature string `json:"signature"`
}

func ReviewerWatcherLiveWitnessMessage(w ReviewerWatcherLiveWitness)[]byte{
 b,_:=json.Marshal([]any{
  reviewerWatcherLiveDomain,"wolo-1",w.Version,w.OperationID,w.OwnerUID,
  w.OwnerSteamID,w.GameIdentityKey,w.MarketID,w.SelectedSide,
  w.PropositionHash,w.LinkedSession,w.SourceParseIteration,
  w.SourceRosterHash,w.RosterLockedAtMS,w.ExecutionCreatedAtMS,
  w.LiveCheckpointSHA256,w.CapturedAtMS,w.ObservedAtMS,w.ExpiresAtMS,
 })
 return b
}

// Exact recorded pre-bet evidence, not a caller-declared market/receipt/sha.
// Independent checkpoint capture and event signer provisioning remain
// separate operator-controlled release requirements.
func VerifyReviewerWatcherLiveWitness(
 c ReviewerWatcherCandidate,w ReviewerWatcherLiveWitness,
 root ed25519.PublicKey,independentCheckpointSHA string,now time.Time,
)error{
 hold:=ErrReviewerLiveWitness
 if len(root)!=ed25519.PublicKeySize||
  !reviewerHexDigest.MatchString(independentCheckpointSHA)||
  !reviewerHexDigest.MatchString(w.LiveCheckpointSHA256)||
  independentCheckpointSHA!=w.LiveCheckpointSHA256||
  w.Version!=2||w.OperationID!=c.OriginalOperationID||
  !wagerIDs.MatchString(w.OperationID)||
  w.OwnerUID!=c.OwnerUID||w.OwnerSteamID!=c.OwnerSteamID||
  w.GameIdentityKey!=c.GameIdentityKey||w.MarketID!=c.MarketID||
  w.SelectedSide!=c.SelectedSide||
  (w.SelectedSide!="left"&&w.SelectedSide!="right")||
  w.PropositionHash!=c.PropositionHash||
  !reviewerHexDigest.MatchString(w.PropositionHash)||
  w.LinkedSession!=c.LinkedSession||w.LinkedSession==""||
  w.SourceParseIteration!=c.SourceParseIteration||
  w.SourceParseIteration<1||w.SourceRosterHash!=c.SourceRosterHash||
  !reviewerHexDigest.MatchString(w.SourceRosterHash)||
  w.RosterLockedAtMS!=c.RosterLockedAtMS||
  w.ExecutionCreatedAtMS!=c.CreatedAt.UnixMilli()||
  w.RosterLockedAtMS<0||
  w.RosterLockedAtMS>w.ExecutionCreatedAtMS||
  w.CapturedAtMS<w.ExecutionCreatedAtMS-120000||
  w.CapturedAtMS>w.ExecutionCreatedAtMS+120000||
  w.ObservedAtMS<w.CapturedAtMS||
  w.ObservedAtMS>w.ExecutionCreatedAtMS+120000||
  w.ObservedAtMS>now.UnixMilli()||
  w.ExpiresAtMS<=now.UnixMilli()||
  w.ExpiresAtMS<=w.ObservedAtMS||
  w.ExpiresAtMS-w.ObservedAtMS>60000||now.IsZero(){
  return hold
 }
 raw,e:=base64.StdEncoding.Strict().DecodeString(w.Signature)
 if e!=nil||len(raw)!=ed25519.SignatureSize||
  base64.StdEncoding.EncodeToString(raw)!=w.Signature||
  !ed25519.Verify(root,ReviewerWatcherLiveWitnessMessage(w),raw){
  return hold
 }
 return nil
}
