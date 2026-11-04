package satchelservice

// A nonexecuting observation of the EXISTING protected return qualification.
// It issues no permission, reserves no funds/nonce, and never signs or writes.
import (
	"context"
	"encoding/json"
	"strings"
	"time"

	bolt "go.etcd.io/bbolt"
)

type EscrowReturnExecutionCheck struct {
	Protocol              int            `json:"protocol"`
	Kind                  string         `json:"kind"`
	Approval              ReturnApproval `json:"approval"`
	OperationPermitSHA256 string         `json:"operation_permit_sha256"`
	ReserveReviewSHA256   string         `json:"reserve_review_sha256"`
	StateHeight           int64          `json:"state_height"`
	CommitHeight          int64          `json:"commit_height"`
	CommitBlockHash       string         `json:"commit_block_hash"`
	ExpiresAt             int64          `json:"expires_at"`
	ExecutionAuthorized   bool           `json:"execution_authorized"`
	CreditAuthorized      bool           `json:"credit_authorized"`
}

func (s *EnrolledEscrowExecutor) CheckExecution(ctx context.Context, approval ReturnApproval) (EscrowReturnExecutionCheck, error) {
	none := EscrowReturnExecutionCheck{}
	if s == nil || s.issuer == nil || s.native == nil || ctx == nil || ctx.Err() != nil {
		return none, ErrEscrowRuntimeHeld
	}
	raw, err := json.Marshal(approval)
	var a ReturnApproval
	if err != nil || len(raw) > HTTPMaxBodyBytes || strictHTTPJSON(raw, &a) != nil || !claimIDs.MatchString(a.ClaimID) || a.Allocation == nil {
		return none, ErrEscrowRuntimeHeld
	}
	e := s.issuer.engine
	req := TransferRequest{OperationID: "satchel:claim-return:" + a.ClaimID, ChainID: "wolo-1", Denom: "uwolo", Sender: e.policy.BettingEscrow,
		Recipient: e.policy.Vault, Kind: "claim_return", AmountUWolo: a.AmountUWolo, OwnerID: a.OwnerID,
		Memo: "aoe2war/satchel/claim-return/v1/" + a.ClaimID, ReturnApproval: &a}
	g, err := s.bindEscrowOperation(ctx, a, req)
	if err != nil {
		return none, err
	}
	ctx, cancel := context.WithDeadline(context.WithValue(ctx, enrolledEscrowOperationKey{}, g), g.expires)
	defer cancel()
	escrowBoundary(ctx, "engine_lock")
	var qualified VerifiedEscrowReturnExecution
	err = func() error {
		e.mu.Lock()
		defer e.mu.Unlock()
		// A consumed claim is recovery-only; the same permanent uncertainty and
		// nonce fence is checked again by the actual atomic intent transaction.
		if err := e.db.View(func(tx *bolt.Tx) error {
			if b := tx.Bucket(escrowReturnSpendBucket); b != nil && b.Get([]byte(a.ClaimID)) != nil {
				return ErrEscrowReturnSpend
			}
			return e.escrowSpendHistoryTx(tx, g.nonce)
		}); err != nil {
			return err
		}
		var err error
		qualified, err = s.issuer.qualifyEscrowReturnLocked(ctx, a)
		return err
	}()
	if err != nil {
		return none, ErrEscrowRuntimeHeld
	}
	var bundle EscrowReturnExecutionBundle
	if strictHTTPJSON(g.reviewRaw, &bundle) != nil || qualified.bundleHash != hashJSON(bundle) {
		return none, ErrEscrowRuntimeHeld
	}
	current := qualified.CurrentFor(ctx, a)
	authorized := s.authorized(ctx, req)
	lease := escrowKeyringLeaseCurrent(s.native)
	completed := time.Now() // after final native bank, protected file and lease I/O
	if !current || !authorized || !lease || ctx.Err() != nil || !completed.Before(g.expires) || !completed.Before(qualified.expires) ||
		!qualified.bank.CurrentAt(completed) || qualified.bank.Height() != g.stateHeight || !strings.EqualFold(qualified.bank.BlockHash(), g.commitHash) {
		return none, ErrEscrowRuntimeHeld
	}
	expires := qualified.expires
	if g.expires.Before(expires) {
		expires = g.expires
	}
	return EscrowReturnExecutionCheck{Protocol: 1, Kind: "escrow_return_execution_check", Approval: a,
		OperationPermitSHA256: g.permitDigest, ReserveReviewSHA256: g.reviewDigest,
		StateHeight: qualified.bank.Height(), CommitHeight: qualified.bank.CommitHeight(), CommitBlockHash: qualified.bank.BlockHash(), ExpiresAt: expires.Unix()}, nil
}
