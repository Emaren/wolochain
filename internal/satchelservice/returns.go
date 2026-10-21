package satchelservice

import (
	"context"
	"encoding/json"
	"errors"
	"regexp"
	"strings"

	"github.com/emaren/wolochain/internal/satchel"
	bolt "go.etcd.io/bbolt"
)

// ReturnApproval is an independently reviewed app allocation, not a claim that
// money has moved. The signature binds the original funded operation to exactly
// one owner's claim/ledger allocation. No escrow key enters this service.
type ReturnApproval struct {
	Version          int               `json:"version"`
	TicketID         string            `json:"ticket_id"`
	MarketID         string            `json:"market_id"`
	LegID            string            `json:"leg_id"`
	EntitlementID    string            `json:"entitlement_id"`
	Allocation       *ReturnAllocation `json:"allocation"`
	OperationID      string            `json:"operation_id"`
	ClaimID          string            `json:"claim_id"`
	OwnerID          string            `json:"owner_id"`
	ClaimKind        string            `json:"claim_kind"`
	AmountUWolo      string            `json:"amount_uwolo"`
	AllocationDigest string            `json:"allocation_digest"`
	IssuedAt         int64             `json:"issued_at"`
	ExpiresAt        int64             `json:"expires_at"`
	Signature        string            `json:"signature"`
}
type ReturnReceipt struct {
	Version          int    `json:"version"`
	TicketID         string `json:"ticket_id"`
	MarketID         string `json:"market_id"`
	LegID            string `json:"leg_id"`
	EntitlementID    string `json:"entitlement_id"`
	AllocationID     string `json:"allocation_id"`
	OperationID      string `json:"operation_id"`
	ClaimID          string `json:"claim_id"`
	OwnerID          string `json:"owner_id"`
	ClaimKind        string `json:"claim_kind"`
	AmountUWolo      string `json:"amount_uwolo"`
	TxHash           string `json:"tx_hash"`
	ReceiptID        string `json:"receipt_id"`
	Height           int64  `json:"height"`
	BlockHash        string `json:"block_hash"`
	CreditAuthorized bool   `json:"credit_authorized"` // always false; HD must atomically consume its own global receipt
}
type ReturnPayout struct {
	RequestID   string `json:"request_id"`
	ToAddress   string `json:"to_address"`
	AmountUWolo string `json:"amount_uwolo"`
	Memo        string `json:"memo"`
}

// ReturnRun is the existing /settlement/v1/runs wire contract. Only the
// separately authorized 8092 escrow lane may execute it, after its current-source
// protected release. This service never possesses those credentials or keys.
type ReturnRun struct {
	SettlementRunID string         `json:"settlement_run_id"`
	SourceApp       string         `json:"source_app"`
	SourceEventID   string         `json:"source_event_id"`
	SignerRole      string         `json:"signer_role"`
	Payouts         []ReturnPayout `json:"payouts"`
}
type returnRecord struct {
	Approval    ReturnApproval
	Fingerprint string
	Receipt     *ReturnReceipt
}

var returns = []byte("owner-returns-v1")
var claimIDs = regexp.MustCompile(`^[1-9][0-9]{0,11}$`)

func ReturnApprovalMessage(a ReturnApproval, p Policy) []byte {
	if a.Version != 2 {
		b, _ := json.Marshal([]any{"aoe2war/satchel/claim-return-approval/v1", "wolo-1", "uwolo", p.BettingEscrow, p.Vault, a.OperationID, a.ClaimID, a.OwnerID, a.ClaimKind, a.AmountUWolo, a.AllocationDigest, a.IssuedAt, a.ExpiresAt})
		return b
	}
	b, _ := json.Marshal([]any{"aoe2war/satchel/claim-return-approval/v2", "wolo-1", "uwolo", p.BettingEscrow, p.Vault, a.Version, a.OperationID, a.ClaimID, a.OwnerID, a.TicketID, a.MarketID, a.LegID, a.EntitlementID, a.ClaimKind, a.AmountUWolo, a.AllocationDigest, a.IssuedAt, a.ExpiresAt})
	return b
}
func returnFingerprint(a ReturnApproval) string {
	if a.Version != 2 || a.Allocation == nil {
		return hashJSON([]string{a.OperationID, a.ClaimID, a.OwnerID, a.ClaimKind, a.AmountUWolo, a.AllocationDigest})
	}
	p := a.Allocation
	principal := ""
	for _, leg := range p.Legs {
		for _, entry := range leg.Entitlements {
			if entry.ClaimID == a.ClaimID {
				principal = entry.PrincipalUWolo
			}
		}
	}
	return hashJSON([]any{"return-claim-v2", a.Version, a.OperationID, a.ClaimID, a.OwnerID, a.TicketID, a.MarketID, a.LegID, a.EntitlementID, a.ClaimKind, a.AmountUWolo, p.AllocationID, p.FundingTxHash, p.ReturnCapUWolo, p.FundsBudgetID, p.FundsAvailableUWolo, p.BankEvidenceDigest, p.BankHeight, p.BankBlockHash, principal})
}
func (e *Engine) validateReturn(tx *bolt.Tx, a ReturnApproval) error {
	return e.validateReturnAt(tx, a, true)
}
func (e *Engine) validateReturnAt(tx *bolt.Tx, a ReturnApproval, fresh bool) error {
	if a.Version != 2 || !ownerUIDPattern.MatchString(a.OwnerID) || !claimIDs.MatchString(a.ClaimID) || a.ClaimID == "889" || !validReviewTime(a.IssuedAt, a.ExpiresAt, e.now().Unix(), fresh) || !verifyReview(e.policy.WithdrawalApprovalKey, ReturnApprovalMessage(a, e.policy), a.Signature) {
		return errors.New("owner_return_approval_refused")
	}
	_, err := e.validateAllocation(tx, a, fresh)
	return err
}
func (e *Engine) prepareReturn(a ReturnApproval) (returnRecord, error) {
	var out returnRecord
	err := e.db.Update(func(tx *bolt.Tx) error {
		if err := e.validateReturn(tx, a); err != nil {
			return err
		}
		b, err := tx.CreateBucketIfNotExists(returns)
		if err != nil {
			return err
		}
		old := b.Get([]byte(a.ClaimID))
		exists := old != nil
		if exists {
			if json.Unmarshal(old, &out) != nil || out.Approval.Version != 2 || out.Fingerprint != returnFingerprint(out.Approval) {
				return errors.New("legacy_or_corrupt_return_requires_review")
			}
			if out.Fingerprint != returnFingerprint(a) {
				return errors.New("return_allocation_conflict")
			}
			if out.Receipt != nil && !validReturnReceipt(out, *out.Receipt) {
				return errors.New("return_state_corrupt")
			}
		}
		if err := e.reserveAllocation(tx, a, !exists); err != nil {
			return err
		}
		if exists {
			return nil
		}
		out = returnRecord{Approval: a, Fingerprint: returnFingerprint(a)}
		data, _ := json.Marshal(out)
		return b.Put([]byte(a.ClaimID), data)
	})
	return out, err
}

// PrepareReturnRun durably binds owner/claim before returning an exact escrow
// execution request. An unmatched refund is its exact allocated stake portion;
// there is no 2% deduction or fee transfer in this run. Chain gas is separate.
func (e *Engine) PrepareReturnRun(ctx context.Context, a ReturnApproval) (ReturnRun, error) {
	e.mu.Lock()
	defer e.mu.Unlock()
	if ctx.Err() != nil {
		return ReturnRun{}, ctx.Err()
	}
	if _, err := e.prepareReturn(a); err != nil {
		return ReturnRun{}, err
	}
	id := "satchel:claim-return:" + a.ClaimID
	return ReturnRun{SettlementRunID: id, SourceApp: "aoe2hdbets", SourceEventID: a.OperationID, SignerRole: "escrow", Payouts: []ReturnPayout{{RequestID: id, ToAddress: e.policy.Vault, AmountUWolo: a.AmountUWolo, Memo: "aoe2war/satchel/claim-return/v1/" + a.ClaimID}}}, nil
}

// ReconcileReturn only reads chain evidence; it never triggers the escrow lane.
// The actual opaque proof must come from a server-configured TrustedReader.
func (e *Engine) ReconcileReturn(ctx context.Context, a ReturnApproval, hash string, reader *satchel.TrustedReader) (ReturnReceipt, error) {
	e.mu.Lock()
	defer e.mu.Unlock()
	if !digestRE.MatchString(hash) || reader == nil {
		return ReturnReceipt{}, errors.New("return_proof_unavailable")
	}
	hash = strings.ToUpper(hash)
	if ctx.Err() != nil {
		return ReturnReceipt{}, ctx.Err()
	}
	var r returnRecord
	err := e.db.View(func(tx *bolt.Tx) error {
		b := tx.Bucket(returns)
		if b == nil {
			return errors.New("return_not_prepared")
		}
		data := b.Get([]byte(a.ClaimID))
		if data == nil {
			return errors.New("return_not_prepared")
		}
		if json.Unmarshal(data, &r) != nil || r.Approval.Version != 2 || r.Fingerprint != returnFingerprint(r.Approval) {
			return errors.New("legacy_or_corrupt_return_requires_review")
		}
		if r.Fingerprint != returnFingerprint(a) {
			return errors.New("return_allocation_conflict")
		}
		if err := e.validateReturnAt(tx, a, false); err != nil {
			return err
		}
		// Reconciliation uses the already durable authority; it cannot adopt a new
		// allocation revision, reserve another entitlement or transmit a payment.
		if a.AllocationDigest != r.Approval.AllocationDigest {
			return errors.New("reconciliation_allocation_conflict")
		}
		return nil
	})
	if err != nil {
		return ReturnReceipt{}, err
	}
	if r.Receipt != nil {
		if !validReturnReceipt(r, *r.Receipt) || r.Receipt.TxHash != hash {
			return ReturnReceipt{}, errors.New("return_transaction_conflict")
		}
		return *r.Receipt, nil
	}
	proof, err := reader.ReadTransfer(ctx, satchel.TransferIntent{Sender: e.policy.BettingEscrow, Recipient: e.policy.Vault, AmountUWolo: a.AmountUWolo, Memo: "aoe2war/satchel/claim-return/v1/" + a.ClaimID}, hash)
	if err != nil || !proof.ConsensusAuthenticated() || proof.CreditAuthorized() {
		return ReturnReceipt{}, errors.New("return_proof_unavailable")
	}
	o := proof.Observation()
	receipt := ReturnReceipt{Version: 2, TicketID: a.TicketID, MarketID: a.MarketID, LegID: a.LegID, EntitlementID: a.EntitlementID, AllocationID: a.Allocation.AllocationID, OperationID: a.OperationID, ClaimID: a.ClaimID, OwnerID: a.OwnerID, ClaimKind: a.ClaimKind, AmountUWolo: a.AmountUWolo, TxHash: hash, ReceiptID: proof.Receipt().ID(), Height: o.Height, BlockHash: o.BlockHash}
	if err = e.recordReturn(r, receipt); err != nil {
		return ReturnReceipt{}, err
	}
	return receipt, nil
}
func (e *Engine) recordReturn(r returnRecord, receipt ReturnReceipt) error {
	if !validReturnReceipt(r, receipt) {
		return errors.New("return_receipt_invalid")
	}
	return e.db.Update(func(tx *bolt.Tx) error {
		b := tx.Bucket(returns)
		if b == nil {
			return errors.New("return_not_prepared")
		}
		var stored returnRecord
		data := b.Get([]byte(r.Approval.ClaimID))
		if data == nil || json.Unmarshal(data, &stored) != nil || stored.Fingerprint != returnFingerprint(stored.Approval) || stored.Fingerprint != r.Fingerprint {
			return errors.New("return_state_corrupt")
		}
		if stored.Receipt != nil {
			if *stored.Receipt != receipt {
				return errors.New("return_transaction_conflict")
			}
			return nil
		}
		r = stored
		// Consume the physical single-MsgSend transaction, not a caller-selected
		// bank event representation. Never mint a second receipt namespace.
		key := []byte("wolo-1:" + receipt.TxHash)
		owner := "return:" + r.Approval.ClaimID
		if old := tx.Bucket(effects).Get(key); old != nil && string(old) != owner {
			return errors.New("chain_effect_already_consumed")
		}
		if err := tx.Bucket(effects).Put(key, []byte(owner)); err != nil {
			return err
		}
		r.Receipt = &receipt
		data, _ = json.Marshal(r)
		return tx.Bucket(returns).Put([]byte(r.Approval.ClaimID), data)
	})
}

func validReturnReceipt(r returnRecord, p ReturnReceipt) bool {
	return p.Version == 2 && r.Approval.Version == 2 && r.Approval.Allocation != nil && p.TicketID == r.Approval.TicketID && p.MarketID == r.Approval.MarketID && p.LegID == r.Approval.LegID && p.EntitlementID == r.Approval.EntitlementID && p.AllocationID == r.Approval.Allocation.AllocationID && p.OperationID == r.Approval.OperationID && p.ClaimID == r.Approval.ClaimID && p.OwnerID == r.Approval.OwnerID && p.ClaimKind == r.Approval.ClaimKind && p.AmountUWolo == r.Approval.AmountUWolo && !p.CreditAuthorized && p.Height > 0 && nonzeroDigest(p.BlockHash) && nonzeroDigest(p.TxHash) && p.TxHash == strings.ToUpper(p.TxHash) && (p.ReceiptID == "wolo-1:"+p.TxHash+":0" || p.ReceiptID == "wolo-1:"+p.TxHash+":1")
}
