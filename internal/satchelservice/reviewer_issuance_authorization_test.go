package satchelservice

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	bolt "go.etcd.io/bbolt"
)

func storedReviewerIssue(t *testing.T, issuer *ReviewerIssuer, id string) ([]byte, reviewerEntry) {
	t.Helper()
	var raw []byte
	err := issuer.db.View(func(tx *bolt.Tx) error {
		raw = append([]byte(nil), tx.Bucket(reviewerIssues).Get([]byte(id))...)
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	var entry reviewerEntry
	if len(raw) != 0 && json.Unmarshal(raw, &entry) != nil {
		t.Fatal("invalid stored reviewer entry")
	}
	return raw, entry
}

func TestReviewerRuntimeAuthorizationBindsOnceBeforeUseIncludingRestart(t *testing.T) {
	issuer, source, policy, state := setupIssuer(t)
	if !errors.Is(issuer.RequireIssuanceAuthorization(nil), ErrReviewerHeld) {
		t.Fatal("nil authorization accepted")
	}
	if err := issuer.RequireIssuanceAuthorization(func(context.Context) bool { return true }); err != nil {
		t.Fatal("startup authorization refused")
	}
	if !errors.Is(issuer.RequireIssuanceAuthorization(func(context.Context) bool { return true }), ErrReviewerHeld) {
		t.Fatal("authorization could be replaced")
	}
	original := issuer.ReviewOne(t.Context(), source.original.OperationID)
	if original.Status != "SIGNED" || original.Approval == nil {
		t.Fatal("authorized original grant missing")
	}
	if err := issuer.Close(); err != nil {
		t.Fatal(err)
	}
	reopened, err := OpenReviewerIssuer(state, source, engineTestWagerApprovalKey(), policy)
	if err != nil {
		t.Fatal(err)
	}
	defer reopened.Close()
	before, _ := storedReviewerIssue(t, reopened, source.original.OperationID)
	allowed := false
	if err := reopened.RequireIssuanceAuthorization(func(context.Context) bool { return allowed }); err != nil {
		t.Fatal("historical records incorrectly prevented startup binding")
	}
	held := reopened.ReviewOne(t.Context(), source.original.OperationID)
	if held.Status != "PENDING" || held.Approval != nil {
		t.Fatal("restart disclosed old grant without current authorization")
	}
	allowed = true
	resumed := reopened.ReviewOne(t.Context(), source.original.OperationID)
	if resumed.Status != "SIGNED" || resumed.Approval == nil || resumed.Approval.Signature != original.Approval.Signature {
		t.Fatal("restart did not preserve exactly the original grant")
	}
	after, _ := storedReviewerIssue(t, reopened, source.original.OperationID)
	if string(before) != string(after) {
		t.Fatal("runtime binding/replay changed historical record bytes")
	}
}

func TestReviewerRuntimeAuthorizationCannotBeAddedAfterFirstUse(t *testing.T) {
	issuer, source, _, _ := setupIssuer(t)
	source.failOwner = true
	if reply := issuer.ReviewOne(t.Context(), source.original.OperationID); reply.Approval != nil {
		t.Fatal("invalid source signed")
	}
	if !errors.Is(issuer.RequireIssuanceAuthorization(func(context.Context) bool { return true }), ErrReviewerHeld) {
		t.Fatal("issuer authorization was rebound after evidence use")
	}
}

func TestReviewerRuntimeRevocationBeforePendingNeverCreatesIssue(t *testing.T) {
	issuer, source, _, _ := setupIssuer(t)
	calls := 0
	if err := issuer.RequireIssuanceAuthorization(func(context.Context) bool {
		calls++
		return calls == 1 // entry only; revocation at the durable-intent boundary
	}); err != nil {
		t.Fatal(err)
	}
	reply := issuer.ReviewOne(t.Context(), source.original.OperationID)
	raw, _ := storedReviewerIssue(t, issuer, source.original.OperationID)
	if reply.Status != "PENDING" || reply.Approval != nil || len(raw) != 0 || calls != 2 {
		t.Fatal("revocation before intent created a signing record or grant")
	}
}

func TestReviewerRuntimeRevocationAfterPendingNeverSignsOrRenews(t *testing.T) {
	issuer, source, _, _ := setupIssuer(t)
	allowed := true
	sawPreSignPending := false
	if err := issuer.RequireIssuanceAuthorization(func(context.Context) bool {
		_, entry := storedReviewerIssue(t, issuer, source.original.OperationID)
		if entry.Status == "PENDING" && !sawPreSignPending {
			sawPreSignPending = true
			allowed = false
		}
		return allowed
	}); err != nil {
		t.Fatal(err)
	}
	reply := issuer.ReviewOne(t.Context(), source.original.OperationID)
	before, entry := storedReviewerIssue(t, issuer, source.original.OperationID)
	if !sawPreSignPending || reply.Status != "PENDING" || reply.Approval != nil || entry.Status != "PENDING" || entry.Approval != nil {
		t.Fatal("pre-sign revocation escaped the permanent intent fence")
	}
	allowed = true
	for n := 0; n < 2; n++ {
		got := issuer.ReviewOne(t.Context(), source.original.OperationID)
		if got.Status != "PENDING" || got.Approval != nil {
			t.Fatal("fresh authorization renewed a permanently pending issue")
		}
	}
	after, _ := storedReviewerIssue(t, issuer, source.original.OperationID)
	if string(before) != string(after) {
		t.Fatal("pending uncertainty was released or rewritten")
	}
}

func TestReviewerRuntimeRevocationAfterSigningBeforePersistenceKeepsPending(t *testing.T) {
	issuer, source, _, _ := setupIssuer(t)
	calls := 0
	if err := issuer.RequireIssuanceAuthorization(func(context.Context) bool {
		calls++
		return calls < 4 // entry, pre-PENDING, pre-sign; revoke pre-SIGNED write
	}); err != nil {
		t.Fatal(err)
	}
	reply := issuer.ReviewOne(t.Context(), source.original.OperationID)
	_, entry := storedReviewerIssue(t, issuer, source.original.OperationID)
	if calls != 4 || reply.Status != "PENDING" || reply.Approval != nil || entry.Status != "PENDING" || entry.Approval != nil {
		t.Fatal("post-sign revocation persisted or disclosed the grant")
	}
}

func TestReviewerRuntimeRevocationAfterSignedPreservesRecordAndGatesReplay(t *testing.T) {
	issuer, source, _, _ := setupIssuer(t)
	at := time.Now()
	issuer.now = func() time.Time { return at }
	allowed := true
	revoked := false
	if err := issuer.RequireIssuanceAuthorization(func(context.Context) bool {
		_, entry := storedReviewerIssue(t, issuer, source.original.OperationID)
		if entry.Status == "SIGNED" && !revoked {
			revoked = true
			allowed = false
		}
		return allowed
	}); err != nil {
		t.Fatal(err)
	}
	reply := issuer.ReviewOne(t.Context(), source.original.OperationID)
	before, entry := storedReviewerIssue(t, issuer, source.original.OperationID)
	if !revoked || reply.Status != "PENDING" || reply.Approval != nil || entry.Status != "SIGNED" || entry.Approval == nil {
		t.Fatal("post-persistence revocation disclosed or destroyed the signed issue")
	}
	if got := issuer.ReviewOne(t.Context(), source.original.OperationID); got.Status != "PENDING" || got.Approval != nil {
		t.Fatal("old grant disclosed without fresh runtime authorization")
	}
	allowed = true
	at = at.Add(5 * time.Second)
	got := issuer.ReviewOne(t.Context(), source.original.OperationID)
	if got.Status != "SIGNED" || got.Approval == nil || got.Approval.Signature != entry.Approval.Signature || got.Approval.IssuedAt != entry.Approval.IssuedAt || got.Approval.ExpiresAt != entry.Approval.ExpiresAt {
		t.Fatal("fresh authorization did not reuse exact still-valid historical grant")
	}
	after, _ := storedReviewerIssue(t, issuer, source.original.OperationID)
	if string(before) != string(after) {
		t.Fatal("revocation/replay deleted or renewed a durable signature")
	}
}

func TestReviewerRuntimeRevocationDuringExistingGrantReadSuppressesDisclosure(t *testing.T) {
	issuer, source, _, _ := setupIssuer(t)
	allowed := true
	if err := issuer.RequireIssuanceAuthorization(func(context.Context) bool { return allowed }); err != nil {
		t.Fatal(err)
	}
	first := issuer.ReviewOne(t.Context(), source.original.OperationID)
	if first.Approval == nil {
		t.Fatal("original grant missing")
	}
	before, _ := storedReviewerIssue(t, issuer, source.original.OperationID)
	source.censusReads = 0
	source.afterFirstCensus = func(*fakeReviewerEvidence) { allowed = false }
	got := issuer.ReviewOne(t.Context(), source.original.OperationID)
	if got.Status != "PENDING" || got.Approval != nil {
		t.Fatal("mid-read runtime revocation disclosed a historical grant")
	}
	after, _ := storedReviewerIssue(t, issuer, source.original.OperationID)
	if string(before) != string(after) {
		t.Fatal("withholding historical disclosure changed its journal record")
	}
}

func TestReviewerRuntimeAuthorizationPreservesContextDeadlineAndCancellation(t *testing.T) {
	for _, boundary := range []string{"entry", "after_pending"} {
		t.Run(boundary, func(t *testing.T) {
			issuer, source, _, _ := setupIssuer(t)
			type marker struct{}
			deadline := time.Now().Add(time.Minute)
			ctx, cancel := context.WithDeadline(context.WithValue(t.Context(), marker{}, "trusted-context"), deadline)
			defer cancel()
			calls := 0
			if err := issuer.RequireIssuanceAuthorization(func(received context.Context) bool {
				calls++
				actualDeadline, ok := received.Deadline()
				if received != ctx || received.Value(marker{}) != "trusted-context" || !ok || !actualDeadline.Equal(deadline) {
					t.Fatal("runtime authorization lost the actual request context/deadline")
				}
				if boundary == "entry" || calls == 3 {
					cancel()
				}
				return true // cancellation during the callback must still deny
			}); err != nil {
				t.Fatal(err)
			}
			got := issuer.ReviewOne(ctx, source.original.OperationID)
			raw, entry := storedReviewerIssue(t, issuer, source.original.OperationID)
			if got.Status != "PENDING" || got.Approval != nil || ctx.Err() == nil {
				t.Fatal("callback-time cancellation reached a disclosed signature")
			}
			if boundary == "entry" && (len(raw) != 0 || source.loads != 0) {
				t.Fatal("entry cancellation performed evidence I/O or created intent")
			}
			if boundary == "after_pending" && (entry.Status != "PENDING" || entry.Approval != nil) {
				t.Fatal("post-intent cancellation released pending uncertainty")
			}
		})
	}
}
