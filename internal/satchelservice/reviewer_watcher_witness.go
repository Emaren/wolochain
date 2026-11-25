package satchelservice

// A standalone, cryptographically checkable Watcher-origin receipt. A valid
// signature proves only that a particular *independently governed* witness
// key signed these fields. It does NOT, by itself, authenticate raw replay
// data, the source/operator of that key, the chain bank, or spending authority.
//
// This primitive never mutates a game, ledger, wallet or signer. The
// ReviewerReadOnlyPGSource.VerifyWatcherMarket method stays HARD HELD until
// an independently provisioned raw-replay reader supplies its digest and a
// separately audited witness key is pinned outside the app's trust domain.
import (
 "crypto/ed25519"
 "encoding/base64"
 "encoding/json"
 "errors"
 "time"
)

var ErrReviewerWatcherWitness = errors.New("reviewer_watcher_witness_refused")

const watcherWitnessDomain = "aoe2war/satchel/independent-watcher-witness/v1"

// No HTTP requester, app database row or user profile may set these fields.
// This is a transport model for a future independent Watcher observation,
// not a source of true data by itself.
type ReviewerWatcherWitness struct {
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
 RawReplaySHA256 string `json:"raw_replay_sha256"`
 ObservedAtMS int64 `json:"observed_at_ms"`
 ExpiresAtMS int64 `json:"expires_at_ms"`
 Signature string `json:"signature"`
}

// Domain-separated, fixed-order JSON; no dynamic map, floats, whitespace
// normalization, or app-derived "already verified" boolean is signed.
func ReviewerWatcherWitnessMessage(w ReviewerWatcherWitness)[]byte {
 b,_:=json.Marshal([]any{
  watcherWitnessDomain,"wolo-1",w.Version,w.OperationID,w.OwnerUID,
  w.OwnerSteamID,w.GameIdentityKey,w.MarketID,w.SelectedSide,
  w.PropositionHash,w.LinkedSession,w.SourceParseIteration,
  w.SourceRosterHash,w.RosterLockedAtMS,w.ExecutionCreatedAtMS,
  w.RawReplaySHA256,w.ObservedAtMS,w.ExpiresAtMS,
 })
 return b
}

// externalReplayDigest MUST be computed by the independent, source-pinned
// Watcher/replay reader. Supplying this from the app, SQL market flags,
// the witness response itself or a public unauthenticated API is forbidden.
// Requiring it here does not establish that such a reader exists.
func VerifyReviewerWatcherWitness(candidate ReviewerWatcherCandidate,
 witness ReviewerWatcherWitness, trustedPublicKey ed25519.PublicKey,
 externalReplayDigest string, now time.Time) error {
 if len(trustedPublicKey)!=ed25519.PublicKeySize ||
  !reviewerHexDigest.MatchString(externalReplayDigest)||
  !reviewerHexDigest.MatchString(witness.RawReplaySHA256)||
  witness.RawReplaySHA256!=externalReplayDigest ||
  witness.Version!=1||!wagerIDs.MatchString(witness.OperationID)||
  witness.OperationID!=candidate.OriginalOperationID||
  witness.OwnerUID!=candidate.OwnerUID||
  witness.OwnerSteamID!=candidate.OwnerSteamID||
  witness.GameIdentityKey!=candidate.GameIdentityKey||
  witness.MarketID<1||witness.MarketID!=candidate.MarketID||
  witness.SelectedSide!=candidate.SelectedSide||
  (witness.SelectedSide!="left"&&witness.SelectedSide!="right")||
  witness.PropositionHash!=candidate.PropositionHash||
  !reviewerHexDigest.MatchString(witness.PropositionHash)||
  witness.LinkedSession!=candidate.LinkedSession||
  witness.LinkedSession==""||
  witness.SourceParseIteration<1||
  witness.SourceParseIteration!=candidate.SourceParseIteration||
  witness.SourceRosterHash!=candidate.SourceRosterHash||
  !reviewerHexDigest.MatchString(witness.SourceRosterHash)||
  witness.RosterLockedAtMS!=candidate.RosterLockedAtMS||
  witness.ExecutionCreatedAtMS!=candidate.CreatedAt.UnixMilli()||
  witness.RosterLockedAtMS<=0||
  witness.RosterLockedAtMS>witness.ExecutionCreatedAtMS||
  witness.ObservedAtMS<witness.ExecutionCreatedAtMS||
  witness.ObservedAtMS>now.UnixMilli()||
  witness.ExpiresAtMS<=now.UnixMilli()||
  witness.ExpiresAtMS<=witness.ObservedAtMS||
  witness.ExpiresAtMS-witness.ObservedAtMS>60000 ||
  now.IsZero(){
  return ErrReviewerWatcherWitness
 }
 raw,e:=base64.StdEncoding.Strict().DecodeString(witness.Signature)
 if e!=nil||len(raw)!=ed25519.SignatureSize||
  base64.StdEncoding.EncodeToString(raw)!=witness.Signature||
  !ed25519.Verify(trustedPublicKey,ReviewerWatcherWitnessMessage(witness),raw) {
  return ErrReviewerWatcherWitness
 }
 return nil
}
