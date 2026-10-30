package satchelservice

import (
	"bytes"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"reflect"
	"strings"
	"testing"
	"time"

	bolt "go.etcd.io/bbolt"
)

func reviewerFeeRawState(t *testing.T, r *ReviewerIssuer) (int, map[string]string) {
	t.Helper()
	var id int
	values := map[string]string{}
	if err := r.db.View(func(tx *bolt.Tx) error {
		id = tx.ID()
		return tx.Bucket(reviewerIssues).ForEach(func(key, value []byte) error {
			values[string(key)] = string(value)
			return nil
		})
	}); err != nil {
		t.Fatal(err)
	}
	return id, values
}

func TestReviewerIssuedFeeCheckpointRetainsActualFeeExpiryAndRestart(t *testing.T) {
	r, source, policy, path := setupIssuer(t)
	at := time.Now().UTC()
	r.now = func() time.Time { return at }
	empty, err := r.FeeCheckpoint()
	if err != nil || len(empty.PendingFees) != 0 || empty.PendingFees == nil || empty.EntryFingerprints == nil || len(empty.EntryFingerprints) != 0 || empty.Protocol != 1 || empty.Kind != reviewerIssuedFeeCheckpointKind ||
		empty.ChainID != "wolo-1" || empty.Denom != "uwolo" || empty.Vault != policy.Vault || empty.ObservedAtMS != at.UnixMilli() {
		t.Fatalf("invalid empty source-derived checkpoint: %+v %v", empty, err)
	}
	issued := r.ReviewOne(t.Context(), source.original.OperationID)
	if issued.Status != "SIGNED" || issued.Approval == nil {
		t.Fatal("actual reviewer did not issue fixture approval")
	}
	beforeID, before := reviewerFeeRawState(t, r)
	loads, censusReads := source.loads, source.censusReads
	source.failOwner, source.failBank = true, true
	first, err := r.FeeCheckpoint()
	if err != nil || !reflect.DeepEqual(first.PendingFees, []ReviewerPendingFee{{OperationID: source.original.OperationID, Stage: "prepared", FeeUWolo: "1"}}) {
		t.Fatalf("actual signed fee lost: %+v %v", first, err)
	}
	if !reflect.DeepEqual(first.EntryFingerprints, map[string]string{source.original.OperationID: reviewerFingerprint(source.original)}) {
		t.Fatal("signed checkpoint did not retain the exact original pre-authority fingerprint")
	}
	keyHash := sha256.Sum256(policy.WagerApprovalKey)
	if first.JournalDigest == empty.JournalDigest || !validReserveDigest(first.JournalDigest) || first.PolicyDigest != hashJSON(policy) || first.ApprovalKeyFingerprint != hex.EncodeToString(keyHash[:]) {
		t.Fatal("checkpoint did not bind current journal/policy/approval root")
	}
	r.now = func() time.Time { return at.Add(time.Hour) }
	expired, err := r.FeeCheckpoint()
	if err != nil || expired.JournalDigest != first.JournalDigest || !reflect.DeepEqual(expired.PendingFees, first.PendingFees) || !reflect.DeepEqual(expired.EntryFingerprints, first.EntryFingerprints) {
		t.Fatalf("expiry released a possible fee obligation: %+v %v", expired, err)
	}
	afterID, after := reviewerFeeRawState(t, r)
	if beforeID != afterID || !reflect.DeepEqual(before, after) || source.loads != loads || source.censusReads != censusReads {
		t.Fatal("checkpoint wrote/reissued state or queried upstream financial authority")
	}
	if err := r.Close(); err != nil {
		t.Fatal(err)
	}
	reopened, err := OpenReviewerIssuer(path, source, engineTestWagerApprovalKey(), policy)
	if err != nil {
		t.Fatal(err)
	}
	defer reopened.Close()
	reopened.now = func() time.Time { return at.Add(2 * time.Hour) }
	recovered, err := reopened.FeeCheckpoint()
	if err != nil || recovered.JournalDigest != first.JournalDigest || !reflect.DeepEqual(recovered.PendingFees, first.PendingFees) || !reflect.DeepEqual(recovered.EntryFingerprints, first.EntryFingerprints) {
		t.Fatalf("restart lost expired original fee: %+v %v", recovered, err)
	}
}

func TestReviewerIssuedFeeCheckpointCrashPendingRemainsUncertainAndSorted(t *testing.T) {
	r, source, policy, path := setupIssuer(t)
	if err := r.db.Update(func(tx *bolt.Tx) error {
		for _, id := range []string{"satchel:ticket:2", "satchel:ticket:10"} {
			original := source.original
			original.OperationID = id
			raw, _ := json.Marshal(reviewerEntry{Fingerprint: reviewerFingerprint(original), Status: "PENDING"})
			if err := tx.Bucket(reviewerIssues).Put([]byte(id), raw); err != nil {
				return err
			}
		}
		return nil
	}); err != nil {
		t.Fatal(err)
	}
	beforeID, before := reviewerFeeRawState(t, r)
	checkpoint, err := r.FeeCheckpoint()
	want := []ReviewerPendingFee{{OperationID: "satchel:ticket:10", Stage: "uncertain", FeeUWolo: "1000000"}, {OperationID: "satchel:ticket:2", Stage: "uncertain", FeeUWolo: "1000000"}}
	if err != nil || !reflect.DeepEqual(checkpoint.PendingFees, want) {
		t.Fatalf("crash uncertainty or ordering lost: %+v %v", checkpoint, err)
	}
	for _, fee := range want {
		original := source.original
		original.OperationID = fee.OperationID
		if checkpoint.EntryFingerprints[fee.OperationID] != reviewerFingerprint(original) {
			t.Fatal("crash checkpoint lost its stored original fingerprint")
		}
	}
	if len(checkpoint.EntryFingerprints) != len(want) {
		t.Fatal("checkpoint invented or omitted a pending identity")
	}
	// Exact stored bytes matter even when their decoded meaning is identical.
	if err := r.db.Update(func(tx *bolt.Tx) error {
		b := tx.Bucket(reviewerIssues)
		return b.Put([]byte("satchel:ticket:2"), append([]byte(" "), b.Get([]byte("satchel:ticket:2"))...))
	}); err != nil {
		t.Fatal(err)
	}
	changed, err := r.FeeCheckpoint()
	if err != nil || changed.JournalDigest == checkpoint.JournalDigest || !reflect.DeepEqual(changed.PendingFees, checkpoint.PendingFees) {
		t.Fatal("digest ignored original raw durable bytes")
	}
	afterID, after := reviewerFeeRawState(t, r)
	if beforeID+1 != afterID || len(before) != len(after) {
		t.Fatal("read-only snapshot added a write beyond the explicit fixture mutation")
	}
	if err := r.Close(); err != nil {
		t.Fatal(err)
	}
	reopened, err := OpenReviewerIssuer(path, source, engineTestWagerApprovalKey(), policy)
	if err != nil {
		t.Fatal(err)
	}
	defer reopened.Close()
	recovered, err := reopened.FeeCheckpoint()
	if err != nil || recovered.JournalDigest != changed.JournalDigest || !reflect.DeepEqual(recovered.PendingFees, want) || !reflect.DeepEqual(recovered.EntryFingerprints, checkpoint.EntryFingerprints) {
		t.Fatalf("restart released crash PENDING fees: %+v %v", recovered, err)
	}
}

func TestReviewerIssuedFeeCheckpointDistinguishesSameIDDifferentReservation(t *testing.T) {
	first, firstSource, _, _ := setupIssuer(t)
	second, secondSource, _, _ := setupIssuer(t)
	// Two independently valid histories can have the same textual operation ID
	// and actual fee. A custody matcher must compare original economics too.
	secondSource.original.OwnerID = "different-owner"
	secondSource.original.ConsentDigest = strings.Repeat("c", 64)
	for _, item := range []struct {
		issuer *ReviewerIssuer
		source *fakeReviewerEvidence
	}{{first, firstSource}, {second, secondSource}} {
		if issued := item.issuer.ReviewOne(t.Context(), item.source.original.OperationID); issued.Status != "SIGNED" || issued.Approval == nil {
			t.Fatal("fixture did not issue independently valid historical approval")
		}
	}
	one, err := first.FeeCheckpoint()
	if err != nil {
		t.Fatal(err)
	}
	two, err := second.FeeCheckpoint()
	if err != nil {
		t.Fatal(err)
	}
	id := firstSource.original.OperationID
	if !reflect.DeepEqual(one.PendingFees, two.PendingFees) || one.PolicyDigest != two.PolicyDigest || one.ApprovalKeyFingerprint != two.ApprovalKeyFingerprint ||
		one.EntryFingerprints[id] == two.EntryFingerprints[id] || one.JournalDigest == two.JournalDigest {
		t.Fatal("same-ID histories did not expose distinct authenticated original identities")
	}
	if one.EntryFingerprints[id] != reviewerFingerprint(firstSource.original) || two.EntryFingerprints[id] != reviewerFingerprint(secondSource.original) {
		t.Fatal("checkpoint substituted an operation-ID-only fingerprint")
	}
}

func TestReviewerIssuedFeeCheckpointDigestBindsPolicyAndApprovalRoot(t *testing.T) {
	r, _, policy, _ := setupIssuer(t)
	initial, err := r.FeeCheckpoint()
	if err != nil {
		t.Fatal(err)
	}
	r.policy.MaxAmountUWolo--
	changedPolicy, err := r.FeeCheckpoint()
	if err != nil || changedPolicy.PolicyDigest == initial.PolicyDigest || changedPolicy.JournalDigest == initial.JournalDigest {
		t.Fatal("raw journal digest was independent of its policy")
	}
	r.policy = policy
	r.key = ed25519.NewKeyFromSeed(bytes.Repeat([]byte{82}, ed25519.SeedSize))
	r.policy.WagerApprovalKey = r.key.Public().(ed25519.PublicKey)
	changedRoot, err := r.FeeCheckpoint()
	if err != nil || changedRoot.ApprovalKeyFingerprint == initial.ApprovalKeyFingerprint || changedRoot.JournalDigest == initial.JournalDigest {
		t.Fatal("raw journal digest was independent of its enrolled approval root")
	}
}

func TestReviewerIssuedFeeCheckpointRejectsCorruptApprovalAndRoleRecords(t *testing.T) {
	for _, name := range []string{"bad_json", "duplicate", "aliased_field", "unknown_field", "missing_fingerprint", "zero_fingerprint", "changed_fingerprint", "bad_id", "nested_bucket", "unknown_status", "missing_approval", "pending_with_approval", "wrong_key", "role_collision", "forged_signature", "retargeted_owner", "wrong_vault", "wrong_escrow", "zero_fee", "noncanonical_fee", "oversize_fee", "bad_time"} {
		t.Run(name, func(t *testing.T) {
			r, source, _, _ := setupIssuer(t)
			issued := r.ReviewOne(t.Context(), source.original.OperationID)
			if issued.Approval == nil {
				t.Fatal("fixture approval not issued")
			}
			if name == "wrong_key" {
				r.key = engineTestApprovalKey()
			} else if name == "role_collision" {
				r.policy.WithdrawalApprovalKey = append(ed25519.PublicKey(nil), r.policy.WagerApprovalKey...)
			} else if err := r.db.Update(func(tx *bolt.Tx) error {
				bucket := tx.Bucket(reviewerIssues)
				id := []byte(source.original.OperationID)
				raw := append([]byte(nil), bucket.Get(id)...)
				var entry reviewerEntry
				if err := json.Unmarshal(raw, &entry); err != nil {
					return err
				}
				switch name {
				case "bad_json":
					return bucket.Put(id, []byte("{"))
				case "duplicate":
					return bucket.Put(id, append([]byte(`{"status":"SIGNED",`), raw[1:]...))
				case "aliased_field":
					return bucket.Put(id, bytes.Replace(raw, []byte(`"fingerprint"`), []byte(`"Fingerprint"`), 1))
				case "unknown_field":
					return bucket.Put(id, append([]byte(`{"financial_authorized":true,`), raw[1:]...))
				case "missing_fingerprint":
					entry.Fingerprint = ""
				case "zero_fingerprint":
					entry.Fingerprint = strings.Repeat("0", 64)
				case "changed_fingerprint":
					entry.Fingerprint = strings.Repeat("a", 64)
				case "bad_id":
					if err := bucket.Delete(id); err != nil {
						return err
					}
					id = []byte("satchel:ticket:07")
				case "nested_bucket":
					_, err := bucket.CreateBucket([]byte("satchel:ticket:8"))
					return err
				case "unknown_status":
					entry.Status = "CONFIRMED"
				case "missing_approval":
					entry.Approval = nil
				case "pending_with_approval":
					entry.Status = "PENDING"
				case "forged_signature":
					entry.Approval.Signature = base64.StdEncoding.EncodeToString(make([]byte, ed25519.SignatureSize))
				case "retargeted_owner":
					entry.Approval.OwnerID = "other-owner"
				case "wrong_vault":
					entry.Approval.Vault = testHTTPAddress(t, 119)
				case "wrong_escrow":
					entry.Approval.Recipient = testHTTPAddress(t, 119)
				case "zero_fee":
					entry.Approval.FeeUWolo = "0"
				case "noncanonical_fee":
					entry.Approval.FeeUWolo = "01"
				case "oversize_fee":
					entry.Approval.FeeUWolo = "1000001"
				case "bad_time":
					entry.Approval.IssuedAt = 0
				}
				if name == "retargeted_owner" || name == "wrong_vault" || name == "wrong_escrow" || strings.Contains(name, "fee") || name == "bad_time" {
					entry.Approval.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(r.key, WagerReservationMessage(*entry.Approval)))
				}
				raw, _ = json.Marshal(entry)
				return bucket.Put(id, raw)
			}); err != nil {
				t.Fatal(err)
			}
			if checkpoint, err := r.FeeCheckpoint(); !errors.Is(err, ErrReviewerHeld) || checkpoint.JournalDigest != "" || len(checkpoint.PendingFees) != 0 || len(checkpoint.EntryFingerprints) != 0 {
				t.Fatalf("corrupt checkpoint exposed partial authority: %+v %v", checkpoint, err)
			}
		})
	}
}

func TestReviewerIssuedFeeCheckpointFailsClosedAtScanLimits(t *testing.T) {
	for _, name := range []string{"entries", "bytes", "entry_size"} {
		t.Run(name, func(t *testing.T) {
			r, source, _, _ := setupIssuer(t)
			count, padding := reviewerMaxPendingOperations+1, 0
			if name == "bytes" {
				count, padding = 600, 15000
			} else if name == "entry_size" {
				count, padding = 1, reviewerIssuedFeeEntryMaxBytes
			}
			if err := r.db.Update(func(tx *bolt.Tx) error {
				bucket := tx.Bucket(reviewerIssues)
				for n := 1; n <= count; n++ {
					original := source.original
					original.OperationID = fmt.Sprintf("satchel:ticket:%d", n)
					raw, _ := json.Marshal(reviewerEntry{Fingerprint: reviewerFingerprint(original), Status: "PENDING"})
					raw = append(bytes.Repeat([]byte(" "), padding), raw...)
					if err := bucket.Put([]byte(original.OperationID), raw); err != nil {
						return err
					}
				}
				return nil
			}); err != nil {
				t.Fatal(err)
			}
			if _, err := r.FeeCheckpoint(); !errors.Is(err, ErrReviewerHeld) {
				t.Fatalf("unbounded %s scan accepted: %v", name, err)
			}
		})
	}
}

func TestReviewerIssuedFeeCheckpointUnavailableAfterClose(t *testing.T) {
	var absent *ReviewerIssuer
	if _, err := absent.FeeCheckpoint(); !errors.Is(err, ErrReviewerHeld) {
		t.Fatal("nil issuer accepted")
	}
	r, _, _, _ := setupIssuer(t)
	if err := r.Close(); err != nil {
		t.Fatal(err)
	}
	if _, err := r.FeeCheckpoint(); !errors.Is(err, ErrReviewerHeld) {
		t.Fatal("closed issuer accepted")
	}
}
