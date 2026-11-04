package satchelservice

import (
	"crypto/ed25519"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strconv"
	"strings"
	"testing"
	"time"

	bolt "go.etcd.io/bbolt"
)

type reviewerFeeMergeFixture struct {
	issuer     *ReviewerIssuer
	source     *fakeReviewerEvidence
	engine     *Engine
	backend    *engineTestBackend
	issuerPath string
	enginePath string
	proposed   WagerReservation
	issued     ReviewerIssuedFeeCheckpoint
	custody    ReviewerCustodyFeeCheckpoint
	authority  ReviewerFeeMergeAuthority
	completed  time.Time
}

func newReviewerFeeMergeFixture(t *testing.T, status string) *reviewerFeeMergeFixture {
	t.Helper()
	issuer, source, policy, issuerPath := setupIssuer(t)
	issued := issuer.ReviewOne(t.Context(), source.original.OperationID)
	if issued.Approval == nil {
		t.Fatal("actual reviewer did not issue fixture grant")
	}
	backend := &engineTestBackend{confirmationStatus: status}
	if status == "UNKNOWN" {
		backend.signErr = errors.New("disposable signing outcome unknown")
	} else if status == "REFUSED" {
		backend.signErr = ErrPreSignRefused
	}
	engine, path, _ := engineTestOpen(t, backend)
	engine.now = time.Now
	if status != "NOT_RECORDED" {
		request := engineTestWager(t, "7")
		request.Reservation = issued.Approval
		if _, err := engine.Submit(t.Context(), request); err != nil {
			t.Fatal(err)
		}
		if status == "CONFIRMED" || status == "FAILED" {
			if _, err := engine.Reconcile(t.Context(), request.OperationID); err != nil {
				t.Fatal(err)
			}
		}
	}
	proposed := source.original
	proposed.OperationID = "satchel:ticket:8"
	proposed.Memo = "AoE2HDBets bet ticket v1 · ticket 8"
	f := &reviewerFeeMergeFixture{issuer: issuer, source: source, engine: engine, backend: backend, proposed: proposed,
		issuerPath: issuerPath, enginePath: path, authority: ReviewerFeeMergeAuthority{Vault: policy.Vault, CustodyPolicyDigest: hashJSON(engine.policy),
			IssuerPolicyDigest: hashJSON(policy), WagerApprovalKey: append(ed25519.PublicKey(nil), policy.WagerApprovalKey...)}}
	f.refresh(t)
	return f
}

func (f *reviewerFeeMergeFixture) refresh(t *testing.T) {
	t.Helper()
	var err error
	f.issued, err = f.issuer.FeeCheckpoint()
	if err != nil {
		t.Fatal(err)
	}
	requested := map[string]bool{f.proposed.OperationID: true}
	for _, fee := range f.issued.PendingFees {
		requested[fee.OperationID] = true
	}
	ids := make([]string, 0, len(requested))
	for id := range requested {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	f.custody, err = f.engine.ReviewerFeeCheckpoint(ids)
	if err != nil {
		t.Fatal(err)
	}
	f.completed = time.Now()
}

func (f *reviewerFeeMergeFixture) merge() ([]ReviewerPendingFee, error) {
	return MergeReviewerPendingFees(f.proposed, f.issued, f.custody, f.authority, f.completed)
}

func TestReviewerFeeMergeFirstOperationNeedsNoInventedPriorFee(t *testing.T) {
	issuer, source, policy, _ := setupIssuer(t)
	engine, _, _ := engineTestOpen(t, &engineTestBackend{})
	engine.now = time.Now
	issued, err := issuer.FeeCheckpoint()
	if err != nil {
		t.Fatal(err)
	}
	custody, err := engine.ReviewerFeeCheckpoint([]string{source.original.OperationID})
	if err != nil {
		t.Fatal(err)
	}
	authority := ReviewerFeeMergeAuthority{Vault: policy.Vault, CustodyPolicyDigest: hashJSON(policy), IssuerPolicyDigest: hashJSON(policy), WagerApprovalKey: policy.WagerApprovalKey}
	if got, err := MergeReviewerPendingFees(source.original, issued, custody, authority, time.Now()); err != nil || got == nil || len(got) != 0 {
		t.Fatal("first original operation acquired an invented historic fee", got, err)
	}
}

func TestReviewerFeeMergeActualCheckpointsDeduplicateWithoutAuthorityOrMutation(t *testing.T) {
	f := newReviewerFeeMergeFixture(t, "UNKNOWN")
	beforeIssued, _ := json.Marshal(f.issued)
	beforeCustody, _ := json.Marshal(f.custody)
	got, err := f.merge()
	want := []ReviewerPendingFee{{OperationID: "satchel:ticket:7", Stage: "prepared", FeeUWolo: "1"}}
	if err != nil || !reflect.DeepEqual(got, want) {
		t.Fatalf("exact original fee was omitted or counted twice: %+v %v", got, err)
	}
	// Even these actual durable checkpoints do not supply global coverage or
	// authenticate bank numbers. Existing arithmetic remains non-authorizing.
	budget, err := AssessReviewerFeeBudget(ReviewerFeeCensus{ChainID: "wolo-1", Denom: "uwolo", OperationID: f.proposed.OperationID,
		BankBalanceUWolo: "1000000000", AllOwnerLiabilitiesUWolo: "0", PendingOperations: got, NewOperationFeeUWolo: f.proposed.FeeUWolo,
		MinimumUnencumberedGasUWolo: "1", PendingOperationsComplete: false}, f.proposed)
	if err != nil || budget.Status != "CENSUS_INCOMPLETE" || budget.SpendingAuthorized || budget.BankAuthenticated || budget.OwnerLedgerAuthenticated {
		t.Fatal("merge created financial coverage or authority", budget, err)
	}
	got[0].FeeUWolo = "999"
	afterIssued, _ := json.Marshal(f.issued)
	afterCustody, _ := json.Marshal(f.custody)
	if string(beforeIssued) != string(afterIssued) || string(beforeCustody) != string(afterCustody) {
		t.Fatal("pure merge mutated either source checkpoint")
	}
}

func TestReviewerFeeMergeTerminalOriginalNeedsMatchingIdentity(t *testing.T) {
	for _, status := range []string{"CONFIRMED", "FAILED", "REFUSED"} {
		t.Run(status, func(t *testing.T) {
			f := newReviewerFeeMergeFixture(t, status)
			if got, err := f.merge(); err != nil || len(got) != 0 || got == nil {
				t.Fatalf("verified terminal duplicate remained pending: %+v %v", got, err)
			}
			f.custody.AccountedFingerprints["satchel:ticket:7"] = strings.Repeat("c", 64)
			if got, err := f.merge(); !errors.Is(err, ErrReviewerHeld) || got != nil {
				t.Fatal("terminal status alone discharged different economics", got, err)
			}
		})
	}
}

func TestReviewerFeeMergeSameIDAuthenticatedOtherOwnerCannotDischargeFee(t *testing.T) {
	for _, status := range []string{"UNKNOWN", "REFUSED"} {
		t.Run(status, func(t *testing.T) {
			first := newReviewerFeeMergeFixture(t, "UNKNOWN")
			other, source, _, _ := setupIssuer(t)
			source.original.OwnerID, source.original.ConsentDigest = "another-owner", strings.Repeat("c", 64)
			grant := other.ReviewOne(t.Context(), source.original.OperationID)
			if grant.Approval == nil {
				t.Fatal("second owner's valid original was not issued")
			}
			backend := &engineTestBackend{signErr: errors.New("second original signing uncertainty")}
			if status == "REFUSED" {
				backend.signErr = ErrPreSignRefused
			}
			engine, _, _ := engineTestOpen(t, backend)
			engine.now = time.Now
			request := engineTestWager(t, "7")
			request.OwnerID, request.Reservation = source.original.OwnerID, grant.Approval
			if _, err := engine.Submit(t.Context(), request); err != nil {
				t.Fatal(err)
			}
			actual, err := engine.ReviewerFeeCheckpoint([]string{source.original.OperationID, first.proposed.OperationID})
			if err != nil {
				t.Fatal(err)
			}
			if actual.AccountedFingerprints[source.original.OperationID] == first.issued.EntryFingerprints[source.original.OperationID] {
				t.Fatal("independent original owner identities unexpectedly collided")
			}
			if got, err := MergeReviewerPendingFees(first.proposed, first.issued, actual, first.authority, time.Now()); !errors.Is(err, ErrReviewerHeld) || got != nil {
				t.Fatal("actual same-ID status from another original owner discharged fee", got, err)
			}
		})
	}
}

func TestReviewerFeeMergeLegacyPendingAndUnknownWithdrawalRemainReserved(t *testing.T) {
	f := newReviewerFeeMergeFixture(t, "UNKNOWN")
	legacy := f.source.original
	legacy.OperationID = "satchel:ticket:6"
	if err := f.issuer.db.Update(func(tx *bolt.Tx) error {
		raw, _ := json.Marshal(reviewerEntry{Fingerprint: reviewerFingerprint(legacy), Status: "PENDING"})
		return tx.Bucket(reviewerIssues).Put([]byte(legacy.OperationID), raw)
	}); err != nil {
		t.Fatal(err)
	}
	withdrawal := engineTestWithdrawal(t)
	custodyFeeStoreUnsigned(t, f.engine, withdrawal)
	f.refresh(t)
	got, err := f.merge()
	want := []ReviewerPendingFee{{OperationID: legacy.OperationID, Stage: "uncertain", FeeUWolo: "1000000"}, {OperationID: "satchel:ticket:7", Stage: "prepared", FeeUWolo: "1"},
		{OperationID: withdrawal.OperationID, Stage: "prepared", FeeUWolo: "1000000"}}
	if err != nil || !reflect.DeepEqual(got, want) {
		t.Fatalf("legacy pending/withdrawal gas released: %+v %v", got, err)
	}
	// Its stored PENDING fingerprint can be superseded by a genuinely
	// authenticated matching original already retained by custody.
	if err := f.issuer.db.Update(func(tx *bolt.Tx) error {
		raw, _ := json.Marshal(reviewerEntry{Fingerprint: reviewerFingerprint(f.source.original), Status: "PENDING"})
		return tx.Bucket(reviewerIssues).Put([]byte(f.source.original.OperationID), raw)
	}); err != nil {
		t.Fatal(err)
	}
	f.refresh(t)
	if got, err := f.merge(); err != nil || !reflect.DeepEqual(got, want) {
		t.Fatal("matching proven custody original did not bound legacy maximum", got, err)
	}
}

func TestReviewerFeeMergeCurrentOperationIsCountedOnceOnlyWithExactOriginal(t *testing.T) {
	for _, status := range []string{"NOT_RECORDED", "UNKNOWN", "CONFIRMED"} {
		t.Run(status, func(t *testing.T) {
			f := newReviewerFeeMergeFixture(t, status)
			f.proposed = f.source.original
			f.refresh(t)
			if got, err := f.merge(); err != nil || len(got) != 0 {
				t.Fatal("exact proposed fee was not reserved solely as NewOperationFee", got, err)
			}
			f.proposed.OwnerID = "another-owner"
			if got, err := f.merge(); !errors.Is(err, ErrReviewerHeld) || got != nil {
				t.Fatal("same current operation ID retargeted its original owner", got, err)
			}
		})
	}
	f := newReviewerFeeMergeFixture(t, "NOT_RECORDED")
	f.proposed = f.source.original
	if err := f.issuer.db.Update(func(tx *bolt.Tx) error {
		raw, _ := json.Marshal(reviewerEntry{Fingerprint: reviewerFingerprint(f.proposed), Status: "PENDING"})
		return tx.Bucket(reviewerIssues).Put([]byte(f.proposed.OperationID), raw)
	}); err != nil {
		t.Fatal(err)
	}
	f.refresh(t)
	if got, err := f.merge(); !errors.Is(err, ErrReviewerHeld) || got != nil {
		t.Fatal("unaccounted current crash PENDING became a fresh request", got, err)
	}
}

func TestReviewerFeeMergeRetainsIdentityAndUnknownFeesAfterRestart(t *testing.T) {
	f := newReviewerFeeMergeFixture(t, "UNKNOWN")
	before, err := f.merge()
	if err != nil {
		t.Fatal(err)
	}
	policy := f.engine.policy
	if err := f.engine.Close(); err != nil {
		t.Fatal(err)
	}
	f.engine, err = Open(f.enginePath, policy, f.backend)
	if err != nil {
		t.Fatal(err)
	}
	defer f.engine.Close()
	if err := f.issuer.Close(); err != nil {
		t.Fatal(err)
	}
	f.issuer, err = OpenReviewerIssuer(f.issuerPath, f.source, engineTestWagerApprovalKey(), policy)
	if err != nil {
		t.Fatal(err)
	}
	defer f.issuer.Close()
	f.refresh(t)
	if after, err := f.merge(); err != nil || !reflect.DeepEqual(after, before) {
		t.Fatal("restart erased actual outstanding original fee", after, err)
	}
}

func TestReviewerFeeMergeExpiredApprovalDoesNotEraseCurrentUnknownFee(t *testing.T) {
	f := newReviewerFeeMergeFixture(t, "UNKNOWN")
	future := time.Now().Add(time.Hour)
	f.issuer.now = func() time.Time { return future }
	f.engine.now = func() time.Time { return future }
	f.refresh(t)
	f.completed = future.Add(time.Millisecond)
	if got, err := f.merge(); err != nil || !reflect.DeepEqual(got, []ReviewerPendingFee{{OperationID: "satchel:ticket:7", Stage: "prepared", FeeUWolo: "1"}}) {
		t.Fatal("expired approval erased its durable unknown fee", got, err)
	}
}

func TestReviewerFeeMergeBoundsCombinedInventory(t *testing.T) {
	f := newReviewerFeeMergeFixture(t, "NOT_RECORDED")
	f.proposed.OperationID = "satchel:ticket:999999999999"
	f.issued.PendingFees = []ReviewerPendingFee{}
	f.issued.EntryFingerprints = map[string]string{}
	f.custody.AccountedOperations = map[string]string{f.proposed.OperationID: "NOT_RECORDED"}
	f.custody.AccountedFingerprints = map[string]string{f.proposed.OperationID: ""}
	// Synthetic wire-size stress, not claims of authentic global coverage.
	for n := 1; n <= reviewerMaxPendingOperations; n++ {
		id := "satchel:ticket:" + strconv.Itoa(n)
		f.issued.PendingFees = append(f.issued.PendingFees, ReviewerPendingFee{OperationID: id, Stage: "uncertain", FeeUWolo: "1000000"})
		f.issued.EntryFingerprints[id] = strings.Repeat("a", 64)
		f.custody.AccountedOperations[id], f.custody.AccountedFingerprints[id] = "NOT_RECORDED", ""
	}
	sort.Slice(f.issued.PendingFees, func(i, j int) bool { return f.issued.PendingFees[i].OperationID < f.issued.PendingFees[j].OperationID })
	if got, err := f.merge(); err != nil || len(got) != reviewerMaxPendingOperations {
		t.Fatal("bounded maximum inventory rejected", len(got), err)
	}
	f.custody.UnresolvedFees = []ReviewerPendingFee{{OperationID: "satchel:ticket:999999999998", Stage: "uncertain", FeeUWolo: "1"}}
	if got, err := f.merge(); !errors.Is(err, ErrReviewerHeld) || got != nil {
		t.Fatal("combined over-cap inventory silently truncated", got, err)
	}
}

func TestReviewerFeeMergeRejectsUntrustedIdentityStaleOrContradictoryInputs(t *testing.T) {
	for _, name := range []string{"issuer_protocol", "issuer_kind", "issuer_chain", "issuer_denom", "issuer_vault", "issuer_policy", "issuer_key", "issuer_digest", "custody_protocol", "custody_kind", "custody_chain", "custody_vault", "custody_policy", "custody_digest", "missing_custody_key", "wrong_custody_key", "future_issuer", "future_custody", "stale_issuer", "stale_custody", "missing_issuer_fingerprint", "extra_issuer_fingerprint", "conflicting_fingerprint", "unverified_collision", "missing_status", "extra_status", "missing_custody_fingerprint", "extra_custody_fingerprint", "unknown_status", "unresolved_missing", "terminal_unresolved", "not_recorded_unresolved", "actual_fee_mismatch", "zero_fee", "noncanonical_fee", "above_cap_fee", "invalid_stage", "duplicate_issuer", "duplicate_custody", "unsorted_issuer", "malformed_withdrawal", "invalid_expected_key", "invalid_expected_policy", "current_fee_changed", "missing_list", "zero_clock"} {
		t.Run(name, func(t *testing.T) {
			f := newReviewerFeeMergeFixture(t, "UNKNOWN")
			const id = "satchel:ticket:7"
			switch name {
			case "issuer_protocol":
				f.issued.Protocol = 2
			case "issuer_kind":
				f.issued.Kind = "custody_fee_checkpoint"
			case "issuer_chain":
				f.issued.ChainID = "other"
			case "issuer_denom":
				f.issued.Denom = "wolo"
			case "issuer_vault":
				f.issued.Vault = f.proposed.Recipient
			case "issuer_policy":
				f.issued.PolicyDigest = strings.Repeat("c", 64)
			case "issuer_key":
				f.issued.ApprovalKeyFingerprint = strings.Repeat("c", 64)
			case "issuer_digest":
				f.issued.JournalDigest = strings.Repeat("0", 64)
			case "custody_protocol":
				f.custody.Protocol = 2
			case "custody_kind":
				f.custody.Kind = reviewerIssuedFeeCheckpointKind
			case "custody_chain":
				f.custody.ChainID = "other"
			case "custody_vault":
				f.custody.Vault = f.proposed.Recipient
			case "custody_policy":
				f.custody.PolicyDigest = strings.Repeat("c", 64)
			case "custody_digest":
				f.custody.JournalDigest = ""
			case "missing_custody_key":
				f.custody.WagerApprovalKeyFingerprint = ""
			case "wrong_custody_key":
				f.custody.WagerApprovalKeyFingerprint = strings.Repeat("c", 64)
			case "future_issuer":
				f.issued.ObservedAtMS = f.completed.Add(time.Millisecond).UnixMilli()
			case "future_custody":
				f.custody.ObservedAtMS = f.completed.Add(time.Millisecond).UnixMilli()
			case "stale_issuer":
				f.issued.ObservedAtMS = f.completed.Add(-reviewerFeeCheckpointMaxAge - time.Millisecond).UnixMilli()
			case "stale_custody":
				f.custody.ObservedAtMS = f.completed.Add(-reviewerFeeCheckpointMaxAge - time.Millisecond).UnixMilli()
			case "missing_issuer_fingerprint":
				delete(f.issued.EntryFingerprints, id)
			case "extra_issuer_fingerprint":
				f.issued.EntryFingerprints["satchel:ticket:99"] = strings.Repeat("c", 64)
			case "conflicting_fingerprint":
				f.custody.AccountedFingerprints[id] = strings.Repeat("c", 64)
			case "unverified_collision":
				f.custody.AccountedFingerprints[id] = ""
			case "missing_status":
				delete(f.custody.AccountedOperations, f.proposed.OperationID)
			case "extra_status":
				f.custody.AccountedOperations["satchel:ticket:99"] = "NOT_RECORDED"
			case "missing_custody_fingerprint":
				delete(f.custody.AccountedFingerprints, f.proposed.OperationID)
			case "extra_custody_fingerprint":
				f.custody.AccountedFingerprints["satchel:ticket:99"] = ""
			case "unknown_status":
				f.custody.AccountedOperations[id] = "SAFE"
			case "unresolved_missing":
				f.custody.UnresolvedFees = []ReviewerPendingFee{}
			case "terminal_unresolved":
				f.custody.AccountedOperations[id] = "CONFIRMED"
			case "not_recorded_unresolved":
				f.custody.AccountedOperations[id] = "NOT_RECORDED"
			case "actual_fee_mismatch":
				f.custody.UnresolvedFees[0].FeeUWolo = "2"
			case "zero_fee":
				f.custody.UnresolvedFees[0].FeeUWolo = "0"
			case "noncanonical_fee":
				f.issued.PendingFees[0].FeeUWolo = "01"
			case "above_cap_fee":
				f.custody.UnresolvedFees[0].FeeUWolo = "1000001"
			case "invalid_stage":
				f.custody.UnresolvedFees[0].Stage = "confirmed"
			case "duplicate_issuer":
				f.issued.PendingFees = append(f.issued.PendingFees, f.issued.PendingFees[0])
			case "duplicate_custody":
				f.custody.UnresolvedFees = append(f.custody.UnresolvedFees, f.custody.UnresolvedFees[0])
			case "unsorted_issuer":
				f.issued.PendingFees = append(f.issued.PendingFees, ReviewerPendingFee{OperationID: "satchel:ticket:6", Stage: "uncertain", FeeUWolo: "1000000"})
			case "malformed_withdrawal":
				f.custody.UnresolvedFees = append(f.custody.UnresolvedFees, ReviewerPendingFee{OperationID: "satchel:withdrawal:not-uuid", Stage: "uncertain", FeeUWolo: "1"})
			case "invalid_expected_key":
				f.authority.WagerApprovalKey = make(ed25519.PublicKey, ed25519.PublicKeySize)
			case "invalid_expected_policy":
				f.authority.CustodyPolicyDigest = strings.Repeat("0", 64)
			case "current_fee_changed":
				f.proposed = f.source.original
				f.proposed.FeeUWolo = "2"
				f.refresh(t)
			case "missing_list":
				f.custody.UnresolvedFees = nil
			case "zero_clock":
				f.completed = time.Time{}
			}
			if got, err := f.merge(); !errors.Is(err, ErrReviewerHeld) || got != nil {
				t.Fatalf("untrusted or contradictory checkpoint admitted: %+v %v", got, err)
			}
		})
	}
}

// Real native transaction bytes and the actual backend's signature verifier
// exercise explicit fee equality, independently from the journal-state fixtures.
func TestReviewerFeeMergeActualNativeSignedFee(t *testing.T) {
	native := newBackendFixture(t)
	policy := Policy{Vault: native.request.Sender, BettingEscrow: native.request.Recipient, ProtectedAddresses: []string{native.request.Recipient}, MaxAmountUWolo: 1000000000,
		WithdrawalApprovalKey: engineTestApprovalKey().Public().(ed25519.PublicKey), WagerApprovalKey: engineTestWagerApprovalKey().Public().(ed25519.PublicKey)}
	original := *native.request.Reservation
	original.Signature, original.IssuedAt, original.ExpiresAt = "", 0, 0
	source := &fakeReviewerEvidence{original: original, census: ReviewerFeeCensus{ChainID: "wolo-1", Denom: "uwolo", OperationID: original.OperationID,
		BankBalanceUWolo: "1000000000", AllOwnerLiabilitiesUWolo: "0", NewOperationFeeUWolo: "2500", MinimumUnencumberedGasUWolo: "1", PendingOperationsComplete: true}}
	issuer, err := OpenReviewerIssuer(filepath.Join(t.TempDir(), "issuer.db"), source, engineTestWagerApprovalKey(), policy)
	if err != nil {
		t.Fatal(err)
	}
	defer issuer.Close()
	grant := issuer.ReviewOne(t.Context(), original.OperationID)
	if grant.Approval == nil {
		t.Fatal("fixture grant not issued")
	}
	native.request.Reservation = grant.Approval
	signed, err := native.b.Sign(t.Context(), native.request)
	if err != nil {
		t.Fatal(err)
	}
	stateDir, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(stateDir, 0700); err != nil {
		t.Fatal(err)
	}
	engine, err := Open(filepath.Join(stateDir, "custody.db"), policy, native.b)
	if err != nil {
		t.Fatal(err)
	}
	defer engine.Close()
	if err := engine.db.Update(func(tx *bolt.Tx) error {
		return save(tx, record{Request: native.request, Fingerprint: fingerprint(native.request), Signed: signed,
			Result: Result{OperationID: original.OperationID, Status: "UNKNOWN", TxHash: signed.Hash, DurableFenced: true}})
	}); err != nil {
		t.Fatal(err)
	}
	issued, err := issuer.FeeCheckpoint()
	if err != nil {
		t.Fatal(err)
	}
	proposed := original
	proposed.OperationID, proposed.Memo = "satchel:ticket:8", "AoE2HDBets bet ticket v1 · ticket 8"
	authority := ReviewerFeeMergeAuthority{Vault: policy.Vault, CustodyPolicyDigest: hashJSON(policy), IssuerPolicyDigest: hashJSON(policy), WagerApprovalKey: policy.WagerApprovalKey}
	for _, status := range []string{"UNKNOWN", "ACCEPTED", "OBSERVED_NONCREDITING"} {
		if err := engine.db.Update(func(tx *bolt.Tx) error {
			record, err := load(tx, original.OperationID)
			if err != nil {
				return err
			}
			record.Result.Status = status
			return save(tx, record)
		}); err != nil {
			t.Fatal(err)
		}
		custody, err := engine.ReviewerFeeCheckpoint([]string{original.OperationID, proposed.OperationID})
		if err != nil {
			t.Fatal(err)
		}
		got, err := MergeReviewerPendingFees(proposed, issued, custody, authority, time.Now())
		if err != nil || !reflect.DeepEqual(got, []ReviewerPendingFee{{OperationID: original.OperationID, Stage: "uncertain", FeeUWolo: "2500"}}) {
			t.Fatal("native signed unresolved fee was omitted or counted twice", status, got, err)
		}
	}
}
