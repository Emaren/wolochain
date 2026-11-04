package satchelservice

import (
	"context"
	"encoding/json"
	"errors"
	"reflect"
	"strings"
	"testing"
	"time"

	bolt "go.etcd.io/bbolt"
)

// The embedded source supplies test-only arithmetic and owner/market fixtures.
// Its census is not an independent bank proof or production coverage authority.
type reviewerFeeContextEvidence struct {
	*fakeReviewerEvidence
	census func(context.Context, WagerReservation) (ReviewerFeeCensus, error)
}

func (s *reviewerFeeContextEvidence) AuthenticatedFeeCensus(ctx context.Context, original WagerReservation) (ReviewerFeeCensus, error) {
	return s.census(ctx, original)
}

func reviewerFeeContextPending(r *ReviewerIssuer, original WagerReservation, id string) error {
	original.OperationID = id
	raw, err := json.Marshal(reviewerEntry{Fingerprint: reviewerFingerprint(original), Status: "PENDING"})
	if err != nil {
		return err
	}
	return r.db.Update(func(tx *bolt.Tx) error { return tx.Bucket(reviewerIssues).Put([]byte(id), raw) })
}

func reviewerFeeContextReview(t *testing.T, r *ReviewerIssuer, ctx context.Context, id string) ReviewerIssuedReply {
	t.Helper()
	done := make(chan ReviewerIssuedReply, 1)
	go func() { done <- r.ReviewOne(ctx, id) }()
	select {
	case result := <-done:
		return result
	case <-time.After(3 * time.Second):
		t.Fatal("ReviewOne did not finish; fee checkpoint may have recursively acquired the issuer mutex")
		return ReviewerIssuedReply{}
	}
}

func TestReviewerFeeContextReviewOneUsesFreshSnapshotsAndIsolatedCopies(t *testing.T) {
	r, base, policy, _ := setupIssuer(t)
	if err := reviewerFeeContextPending(r, base.original, "satchel:ticket:2"); err != nil {
		t.Fatal(err)
	}
	initial, err := r.FeeCheckpoint()
	if err != nil {
		t.Fatal(err)
	}
	var snapshots []ReviewerIssuedFeeCheckpoint
	var retained context.Context
	var callbackErr error
	r.source = &reviewerFeeContextEvidence{fakeReviewerEvidence: base, census: func(ctx context.Context, original WagerReservation) (ReviewerFeeCensus, error) {
		// ReviewOne owns the mutex. Reading the private context must not call
		// the public FeeCheckpoint method or a recursive local HTTP reader.
		if r.mu.TryLock() {
			r.mu.Unlock()
			callbackErr = errors.New("issuer mutex was not held during census")
			return ReviewerFeeCensus{}, callbackErr
		}
		checkpoint, err := reviewerIssuedFeesFromContext(ctx)
		if err != nil {
			callbackErr = err
			return ReviewerFeeCensus{}, err
		}
		snapshots = append(snapshots, cloneReviewerIssuedFees(checkpoint))
		retained = ctx
		checkpoint.PendingFees[0].FeeUWolo = "0"
		checkpoint.EntryFingerprints["satchel:ticket:2"] = strings.Repeat("0", 64)
		checkpoint.JournalDigest = "caller mutation"
		again, err := reviewerIssuedFeesFromContext(ctx)
		if err != nil || !reflect.DeepEqual(again, snapshots[len(snapshots)-1]) {
			callbackErr = errors.New("getter shared mutable checkpoint storage")
			return ReviewerFeeCensus{}, callbackErr
		}
		if len(snapshots) == 1 {
			// Simulate independently durable crash uncertainty between the two
			// source passes. The second census must not reuse the first context.
			if err := reviewerFeeContextPending(r, original, "satchel:ticket:10"); err != nil {
				callbackErr = err
				return ReviewerFeeCensus{}, err
			}
		}
		return base.AuthenticatedFeeCensus(ctx, original)
	}}
	result := reviewerFeeContextReview(t, r, t.Context(), base.original.OperationID)
	if callbackErr != nil || result.Status != "SIGNED" || result.Approval == nil || len(snapshots) != 2 || base.censusReads != 2 {
		t.Fatal("actual issuer did not complete both protected census calls", result, snapshots, callbackErr)
	}
	if snapshots[0].JournalDigest != initial.JournalDigest || snapshots[1].JournalDigest == snapshots[0].JournalDigest || len(snapshots[0].PendingFees) != 1 || len(snapshots[1].PendingFees) != 2 ||
		snapshots[1].PendingFees[0].OperationID != "satchel:ticket:10" || snapshots[1].PendingFees[1].OperationID != "satchel:ticket:2" {
		t.Fatal("second census reused or lost the current durable issuance snapshot", snapshots)
	}
	first := snapshots[0]
	first.ObservedAtMS = initial.ObservedAtMS
	if !reflect.DeepEqual(first, initial) {
		t.Fatal("context did not retain the exact source-generated checkpoint and authority bindings", first, initial)
	}
	approval := result.Approval
	request := TransferRequest{OperationID: approval.OperationID, OwnerID: approval.OwnerID, ChainID: "wolo-1", Denom: "uwolo", Kind: "wager",
		Sender: approval.Vault, Recipient: approval.Recipient, AmountUWolo: approval.AmountUWolo, Memo: approval.Memo, Reservation: approval}
	if err := policy.verifyWager(request, time.Now()); err != nil {
		t.Fatal("context delivery damaged the actual Ed25519 approval", err)
	}
	beforeID, before := reviewerFeeRawState(t, r)
	saved, err := reviewerIssuedFeesFromContext(retained)
	if err != nil || !reflect.DeepEqual(saved, snapshots[1]) {
		t.Fatal("retained protected context changed after issuance", saved, err)
	}
	saved.PendingFees[0].FeeUWolo = "0"
	delete(saved.EntryFingerprints, "satchel:ticket:10")
	current, err := r.FeeCheckpoint()
	if err != nil || len(current.PendingFees) != 3 || current.PendingFees[0].FeeUWolo != "1000000" || current.EntryFingerprints["satchel:ticket:10"] == "" {
		t.Fatal("mutating returned context evidence changed a later durable read", current, err)
	}
	afterID, after := reviewerFeeRawState(t, r)
	if beforeID != afterID || !reflect.DeepEqual(before, after) {
		t.Fatal("context copies or checkpoint reads wrote issuer state")
	}
}

func TestReviewerFeeContextRejectsCallerJSONAndStringKeys(t *testing.T) {
	r, base, _, _ := setupIssuer(t)
	forged := ReviewerIssuedFeeCheckpoint{Protocol: 1, Kind: reviewerIssuedFeeCheckpointKind, JournalDigest: strings.Repeat("a", 64)}
	raw, err := json.Marshal(forged)
	if err != nil {
		t.Fatal(err)
	}
	var decoded ReviewerIssuedFeeCheckpoint
	if err := json.Unmarshal(raw, &decoded); err != nil {
		t.Fatal(err)
	}
	ctx := context.WithValue(t.Context(), "reviewerIssuedFeeContextKey", decoded)
	ctx = context.WithValue(ctx, "reviewer_issued_fees", raw)
	ctx = context.WithValue(ctx, "checkpoint", forged)
	for _, candidate := range []context.Context{nil, t.Context(), ctx, context.WithValue(ctx, reviewerIssuedFeeContextKey{}, decoded)} {
		if got, err := reviewerIssuedFeesFromContext(candidate); !errors.Is(err, ErrReviewerHeld) || !reflect.DeepEqual(got, ReviewerIssuedFeeCheckpoint{}) {
			t.Fatal("caller evidence constructed a private typed checkpoint", got, err)
		}
	}
	var calls int
	r.source = &reviewerFeeContextEvidence{fakeReviewerEvidence: base, census: func(protected context.Context, original WagerReservation) (ReviewerFeeCensus, error) {
		calls++
		got, err := reviewerIssuedFeesFromContext(protected)
		if err != nil || got.JournalDigest == forged.JournalDigest || got.PolicyDigest != hashJSON(r.policy) || len(got.PendingFees) != 0 {
			return ReviewerFeeCensus{}, ErrReviewerHeld
		}
		// A genuine local checkpoint still cannot supply missing independent
		// financial coverage: the fake source deliberately withholds it.
		census := base.census
		census.PendingOperationsComplete = false
		return census, nil
	}}
	result := reviewerFeeContextReview(t, r, ctx, base.original.OperationID)
	if calls != 1 || result.Status != "PENDING" || result.Approval != nil {
		t.Fatal("caller checkpoint supplied independent census authority", result, calls)
	}
	_, state := reviewerFeeRawState(t, r)
	if len(state) != 0 {
		t.Fatal("incomplete independent coverage created a signing intent")
	}
}

func TestReviewerFeeContextPreservesDeadlineAndCancellation(t *testing.T) {
	r, base, _, _ := setupIssuer(t)
	ctx, cancel := context.WithDeadline(t.Context(), time.Now().Add(5*time.Second))
	defer cancel()
	wantDeadline, _ := ctx.Deadline()
	var calls int
	var callbackErr error
	r.source = &reviewerFeeContextEvidence{fakeReviewerEvidence: base, census: func(protected context.Context, original WagerReservation) (ReviewerFeeCensus, error) {
		calls++
		deadline, ok := protected.Deadline()
		if !ok || !deadline.Equal(wantDeadline) || protected.Err() != nil {
			callbackErr = errors.New("private context lost caller deadline")
		}
		cancel()
		if !errors.Is(protected.Err(), context.Canceled) {
			callbackErr = errors.New("private context lost caller cancellation")
		}
		if _, err := reviewerIssuedFeesFromContext(protected); !errors.Is(err, ErrReviewerHeld) {
			callbackErr = errors.New("canceled context still exposed a checkpoint")
		}
		return base.census, nil
	}}
	result := reviewerFeeContextReview(t, r, ctx, base.original.OperationID)
	if callbackErr != nil || calls != 1 || result.Status != "PENDING" || result.Approval != nil {
		t.Fatal("cancellation allowed a grant or another census", result, calls, callbackErr)
	}
	if result = reviewerFeeContextReview(t, r, ctx, base.original.OperationID); calls != 1 || result.Approval != nil {
		t.Fatal("already canceled request reached census", result, calls)
	}
	_, state := reviewerFeeRawState(t, r)
	if len(state) != 0 {
		t.Fatal("canceled source pass created a durable signing intent")
	}
}

func TestReviewerFeeContextCorruptionStopsCensusBeforeSigning(t *testing.T) {
	for _, stage := range []string{"before-first", "before-second"} {
		t.Run(stage, func(t *testing.T) {
			r, base, _, _ := setupIssuer(t)
			corrupt := func() error {
				return r.db.Update(func(tx *bolt.Tx) error { return tx.Bucket(reviewerIssues).Put([]byte("satchel:ticket:2"), []byte("{")) })
			}
			if stage == "before-first" {
				if err := corrupt(); err != nil {
					t.Fatal(err)
				}
			}
			var calls int
			r.source = &reviewerFeeContextEvidence{fakeReviewerEvidence: base, census: func(ctx context.Context, original WagerReservation) (ReviewerFeeCensus, error) {
				calls++
				if _, err := reviewerIssuedFeesFromContext(ctx); err != nil {
					return ReviewerFeeCensus{}, err
				}
				if err := corrupt(); err != nil {
					return ReviewerFeeCensus{}, err
				}
				return base.AuthenticatedFeeCensus(ctx, original)
			}}
			result := reviewerFeeContextReview(t, r, t.Context(), base.original.OperationID)
			wantCalls := 0
			if stage == "before-second" {
				wantCalls = 1
			}
			if calls != wantCalls || result.Status != "PENDING" || result.Approval != nil {
				t.Fatal("corrupt issuance snapshot reached census or signing", result, calls)
			}
			_, state := reviewerFeeRawState(t, r)
			if len(state) != 1 || state["satchel:ticket:2"] != "{" || state[base.original.OperationID] != "" {
				t.Fatal("corrupt checkpoint created a new intent or rewrote existing state", state)
			}
		})
	}
}

func TestReviewerFeeContextRestartPendingRemainsUncertainAndUnsigned(t *testing.T) {
	r, base, policy, path := setupIssuer(t)
	if err := reviewerFeeContextPending(r, base.original, base.original.OperationID); err != nil {
		t.Fatal(err)
	}
	if err := r.Close(); err != nil {
		t.Fatal(err)
	}
	var calls int
	source := &reviewerFeeContextEvidence{fakeReviewerEvidence: base, census: func(ctx context.Context, original WagerReservation) (ReviewerFeeCensus, error) {
		calls++
		checkpoint, err := reviewerIssuedFeesFromContext(ctx)
		if err != nil || len(checkpoint.PendingFees) != 1 || checkpoint.PendingFees[0].OperationID != original.OperationID ||
			checkpoint.PendingFees[0].Stage != "uncertain" || checkpoint.PendingFees[0].FeeUWolo != "1000000" || checkpoint.EntryFingerprints[original.OperationID] != reviewerFingerprint(original) {
			return ReviewerFeeCensus{}, ErrReviewerHeld
		}
		return base.AuthenticatedFeeCensus(ctx, original)
	}}
	reopened, err := OpenReviewerIssuer(path, source, engineTestWagerApprovalKey(), policy)
	if err != nil {
		t.Fatal(err)
	}
	defer reopened.Close()
	beforeID, before := reviewerFeeRawState(t, reopened)
	result := reviewerFeeContextReview(t, reopened, t.Context(), base.original.OperationID)
	afterID, after := reviewerFeeRawState(t, reopened)
	if result.Status != "PENDING" || result.Approval != nil || calls != 2 || beforeID != afterID || !reflect.DeepEqual(before, after) {
		t.Fatal("restart renewed a crash-fenced approval or lost its fee uncertainty", result, calls)
	}
}
