package satchelservice

import (
	"bytes"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"strconv"
	"time"

	"github.com/emaren/wolochain/internal/chainjson"
	bolt "go.etcd.io/bbolt"
)

const reviewerIssuedFeeCheckpointKind = "reviewer_issued_fee_checkpoint"
const reviewerIssuedFeeCheckpointDomain = "aoe2war/satchel/reviewer-issued-fee-checkpoint/v1\x00"
const reviewerIssuedFeeEntryMaxBytes = 16 << 10

// FeeCheckpoint reads one consistent, bounded issuance snapshot. An expired
// approval remains a possible fee obligation until independently accounted for
// by custody; expiry alone cannot prove that signing or submission never took
// place. Nothing here consumes a receipt, releases a hold, signs or writes state.
func (r *ReviewerIssuer) FeeCheckpoint() (ReviewerIssuedFeeCheckpoint, error) {
	if r == nil {
		return ReviewerIssuedFeeCheckpoint{}, ErrReviewerHeld
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.feeCheckpointLocked()
}

// Caller owns r.mu, including when ReviewOne snapshots its own outstanding
// approvals before supplying evidence to the independent census adapter.
func (r *ReviewerIssuer) feeCheckpointLocked() (ReviewerIssuedFeeCheckpoint, error) {
	if r == nil || r.db == nil || r.now == nil || len(r.key) != ed25519.PrivateKeySize ||
		len(r.policy.WagerApprovalKey) != ed25519.PublicKeySize || len(r.policy.WithdrawalApprovalKey) != ed25519.PublicKeySize ||
		bytes.Equal(r.policy.WagerApprovalKey, r.policy.WithdrawalApprovalKey) || !bytes.Equal(r.key.Public().(ed25519.PublicKey), r.policy.WagerApprovalKey) ||
		!validAddress(r.policy.Vault) || !validAddress(r.policy.BettingEscrow) || r.policy.Vault == r.policy.BettingEscrow || r.policy.MaxAmountUWolo == 0 {
		return ReviewerIssuedFeeCheckpoint{}, ErrReviewerHeld
	}
	publicDigest := sha256.Sum256(r.policy.WagerApprovalKey)
	policyBytes, err := json.Marshal(r.policy)
	if err != nil {
		return ReviewerIssuedFeeCheckpoint{}, ErrReviewerHeld
	}
	out := ReviewerIssuedFeeCheckpoint{Protocol: 1, Kind: reviewerIssuedFeeCheckpointKind,
		ChainID: "wolo-1", Denom: "uwolo", Vault: r.policy.Vault, PolicyDigest: hashJSON(r.policy),
		ApprovalKeyFingerprint: hex.EncodeToString(publicDigest[:]), PendingFees: []ReviewerPendingFee{}, EntryFingerprints: map[string]string{}}
	scan := custodyJournalScan{hash: sha256.New()}
	scan.hash.Write([]byte(reviewerIssuedFeeCheckpointDomain))
	if scan.frame('P', nil, policyBytes) != nil || scan.frame('K', nil, publicDigest[:]) != nil {
		return ReviewerIssuedFeeCheckpoint{}, ErrReviewerHeld
	}
	err = r.db.View(func(tx *bolt.Tx) error {
		bucket := tx.Bucket(reviewerIssues)
		if bucket == nil {
			return ErrReviewerHeld
		}
		var sequence [8]byte
		binary.BigEndian.PutUint64(sequence[:], bucket.Sequence())
		if scan.frame('B', reviewerIssues, sequence[:]) != nil {
			return ErrReviewerHeld
		}
		// Bolt iteration is lexicographic, giving stable operation ordering. Hash
		// original framed keys/values rather than re-marshaled decoded entries.
		if err := bucket.ForEach(func(id, raw []byte) error {
			if len(out.PendingFees) >= reviewerMaxPendingOperations || !wagerIDs.Match(id) || raw == nil ||
				len(raw) > reviewerIssuedFeeEntryMaxBytes || scan.frame('V', id, raw) != nil || !chainjson.ValidFolded(raw) {
				return ErrReviewerHeld
			}
			var entry reviewerEntry
			if strictHTTPJSON(raw, &entry) != nil || !validReserveDigest(entry.Fingerprint) {
				return ErrReviewerHeld
			}
			fields, ok := chainjson.Object(raw)
			if !ok {
				return ErrReviewerHeld
			}
			fee := ReviewerPendingFee{OperationID: string(id), Stage: "uncertain", FeeUWolo: strconv.Itoa(reviewerMaxOperationFeeUWolo)}
			switch entry.Status {
			case "PENDING":
				// The old pre-sign record retains only the original fingerprint,
				// not the fee. A crash can never turn that uncertainty into zero.
				if entry.Approval != nil || len(fields) != 2 {
					return ErrReviewerHeld
				}
			case "SIGNED":
				if entry.Approval == nil || len(fields) != 3 || !r.validIssuedFeeApproval(string(id), entry) {
					return ErrReviewerHeld
				}
				fee.Stage, fee.FeeUWolo = "prepared", entry.Approval.FeeUWolo
			default:
				return ErrReviewerHeld
			}
			out.PendingFees = append(out.PendingFees, fee)
			// Preserve the exact stored original identity. A matching operation
			// ID or custody terminal status alone cannot discharge this fee.
			out.EntryFingerprints[string(id)] = entry.Fingerprint
			return nil
		}); err != nil {
			return err
		}
		return scan.frame('E', nil, nil)
	})
	if err != nil {
		return ReviewerIssuedFeeCheckpoint{}, ErrReviewerHeld
	}
	out.ObservedAtMS = r.now().UnixMilli()
	if out.ObservedAtMS <= 0 {
		return ReviewerIssuedFeeCheckpoint{}, ErrReviewerHeld
	}
	out.JournalDigest = hex.EncodeToString(scan.hash.Sum(nil))
	return out, nil
}

func (r *ReviewerIssuer) validIssuedFeeApproval(id string, entry reviewerEntry) bool {
	a := *entry.Approval
	if a.OperationID != id || a.IssuedAt <= 0 || a.ExpiresAt <= a.IssuedAt {
		return false
	}
	request := TransferRequest{OperationID: id, Kind: "wager", ChainID: "wolo-1", Denom: "uwolo",
		OwnerID: a.OwnerID, Sender: a.Vault, Recipient: a.Recipient, AmountUWolo: a.AmountUWolo, Memo: a.Memo, Reservation: &a}
	// Authenticate the full original signature and policy at issuance, without
	// renewing it or confusing historical expiry with proof of no transmission.
	if r.policy.validate(request, time.Unix(a.IssuedAt, 0)) != nil {
		return false
	}
	// The issuer's durable fingerprint predates its authority timestamps.
	a.IssuedAt, a.ExpiresAt, a.Signature = 0, 0, ""
	return reviewerFingerprint(a) == entry.Fingerprint
}
