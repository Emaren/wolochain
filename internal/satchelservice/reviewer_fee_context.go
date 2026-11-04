package satchelservice

import "context"

// Only this process can attach its own authenticated, durable issuance snapshot.
// A request body/header or caller-declared JSON checkpoint cannot construct this
// private context key. Consumers must still verify current custody, native bank
// and independent reserve coverage; this snapshot never grants spending power.
type reviewerIssuedFeeContextKey struct{}
type reviewerIssuedFeeContextValue struct {
	checkpoint ReviewerIssuedFeeCheckpoint
}

func cloneReviewerIssuedFees(in ReviewerIssuedFeeCheckpoint) ReviewerIssuedFeeCheckpoint {
	out := in
	out.PendingFees = append([]ReviewerPendingFee{}, in.PendingFees...)
	out.EntryFingerprints = make(map[string]string, len(in.EntryFingerprints))
	for id, fingerprint := range in.EntryFingerprints {
		out.EntryFingerprints[id] = fingerprint
	}
	return out
}

// Caller holds r.mu. Do not recursively call the public locking checkpoint or
// this process's HTTP endpoint while ReviewOne owns that same mutex.
func (r *ReviewerIssuer) authenticatedFeeCensusLocked(ctx context.Context, original WagerReservation) (ReviewerFeeCensus, error) {
	if r == nil || r.source == nil || ctx == nil || ctx.Err() != nil {
		return ReviewerFeeCensus{}, ErrReviewerHeld
	}
	checkpoint, err := r.feeCheckpointLocked()
	if err != nil || ctx.Err() != nil {
		return ReviewerFeeCensus{}, ErrReviewerHeld
	}
	protected := context.WithValue(ctx, reviewerIssuedFeeContextKey{}, reviewerIssuedFeeContextValue{
		checkpoint: cloneReviewerIssuedFees(checkpoint),
	})
	return r.source.AuthenticatedFeeCensus(protected, original)
}

// Returns an isolated copy, so a census reader cannot mutate a later read of
// the issuance evidence. There is no fallback to request-supplied checkpoints.
func reviewerIssuedFeesFromContext(ctx context.Context) (ReviewerIssuedFeeCheckpoint, error) {
	if ctx == nil || ctx.Err() != nil {
		return ReviewerIssuedFeeCheckpoint{}, ErrReviewerHeld
	}
	protected, ok := ctx.Value(reviewerIssuedFeeContextKey{}).(reviewerIssuedFeeContextValue)
	if !ok {
		return ReviewerIssuedFeeCheckpoint{}, ErrReviewerHeld
	}
	return cloneReviewerIssuedFees(protected.checkpoint), nil
}
