package satchelservice

// Read independently issued live witnesses through the same operator-pinned
// TLS/authentication transport as original checkpoints. This adapter neither
// issues signatures nor authenticates a witness's owner or signing key: the
// independent Watcher verifier still binds those to its enrolled authority and
// separately read immutable checkpoint before any financial review.
import (
	"context"
	"encoding/json"
	"io"
	"time"
	"unicode/utf8"
)

const reviewerSignedLivePath = "/satchel-source/v1/live-witness"
const reviewerSignedLiveJSONLimit int64 = 16 << 10

type ReviewerSignedLiveReader struct {
	api *ReviewerOriginalLiveAPIClient
	now func() time.Time
}

// The client must already have operator-provisioned endpoint, bearer, CA roots
// and SPKI pins. Requests can choose only the canonical durable operation ID.
func NewReviewerSignedLiveReader(api *ReviewerOriginalLiveAPIClient) (*ReviewerSignedLiveReader, error) {
	if api == nil || api.http == nil {
		return nil, ErrReviewerHeld
	}
	return &ReviewerSignedLiveReader{api: api, now: time.Now}, nil
}

func (s *ReviewerSignedLiveReader) FetchOriginalLiveWitness(ctx context.Context, id string) (ReviewerWatcherLiveWitness, error) {
	held := func() (ReviewerWatcherLiveWitness, error) { return ReviewerWatcherLiveWitness{}, ErrReviewerHeld }
	if s == nil || s.api == nil || s.now == nil || ctx == nil || ctx.Err() != nil || !wagerIDs.MatchString(id) {
		return held()
	}
	started, initial := time.Now(), s.now()
	request, _ := json.Marshal(struct {
		OperationID string `json:"operation_id"`
	}{id})
	response, done, err := s.api.request(ctx, reviewerSignedLivePath, request, "application/json")
	if err != nil {
		return held()
	}
	defer done()
	if response.ContentLength > reviewerSignedLiveJSONLimit {
		_ = response.Body.Close()
		return held()
	}
	raw, err := io.ReadAll(io.LimitReader(response.Body, reviewerSignedLiveJSONLimit+1))
	closeErr := response.Body.Close()
	if err != nil || closeErr != nil || int64(len(raw)) > reviewerSignedLiveJSONLimit || !utf8.Valid(raw) || ctx.Err() != nil || response.Request.Context().Err() != nil {
		return held()
	}
	value, err := reviewerStrictJSON(raw)
	object, ok := value.(map[string]any)
	if err != nil || !ok || !reviewerRecord(object, []string{"status", "operation_id", "witness"}) {
		return held()
	}
	witness, ok := object["witness"].(map[string]any)
	if !ok || !reviewerRecord(witness, []string{
		"version", "operation_id", "owner_uid", "owner_steam_id", "game_identity_key", "market_id", "selected_side", "proposition_hash",
		"linked_session", "source_parse_iteration", "source_roster_hash", "roster_locked_at_ms", "execution_created_at_ms", "live_checkpoint_sha256",
		"captured_at_ms", "observed_at_ms", "expires_at_ms", "signature",
	}) {
		return held()
	}
	var reply OriginalLiveWitnessReply
	if json.Unmarshal(raw, &reply) != nil || reply.Status != "SIGNED" || reply.OperationID != id || reply.Witness == nil || reply.Witness.Version != 2 || reply.Witness.OperationID != id {
		return held()
	}
	// Expiry is checked after transport, body reads and decoding. A clock
	// rollback cannot renew the original independently issued witness window.
	completed := s.now()
	if floor := initial.Add(time.Since(started)); floor.After(completed) {
		completed = floor
	}
	w := *reply.Witness
	if ctx.Err() != nil || response.Request.Context().Err() != nil || completed.IsZero() ||
		w.ObservedAtMS <= 0 || w.ObservedAtMS > completed.UnixMilli() || w.ExpiresAtMS <= completed.UnixMilli() ||
		w.ExpiresAtMS <= w.ObservedAtMS || w.ExpiresAtMS-w.ObservedAtMS > 60000 {
		return held()
	}
	return w, nil
}

var _ ReviewerSignedLiveWatcherReader = (*ReviewerSignedLiveReader)(nil)
