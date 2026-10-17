package satchelservice

import (
	"context"
	"crypto/ed25519"
	"encoding/base64"
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
	OperationID      string `json:"operation_id"`
	ClaimID          string `json:"claim_id"`
	OwnerID          string `json:"owner_id"`
	ClaimKind        string `json:"claim_kind"`
	AmountUWolo      string `json:"amount_uwolo"`
	AllocationDigest string `json:"allocation_digest"`
	IssuedAt         int64  `json:"issued_at"`
	ExpiresAt        int64  `json:"expires_at"`
	Signature        string `json:"signature"`
}
type ReturnReceipt struct {
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
	b, _ := json.Marshal([]any{"aoe2war/satchel/claim-return-approval/v1", "wolo-1", "uwolo", p.BettingEscrow, p.Vault, a.OperationID, a.ClaimID, a.OwnerID, a.ClaimKind, a.AmountUWolo, a.AllocationDigest, a.IssuedAt, a.ExpiresAt})
	return b
}
func returnFingerprint(a ReturnApproval) string {
	return hashJSON([]string{a.OperationID, a.ClaimID, a.OwnerID, a.ClaimKind, a.AmountUWolo, a.AllocationDigest})
}
func (e *Engine) validateReturn(tx *bolt.Tx, a ReturnApproval) error {
	r, err := load(tx, a.OperationID)
	if err != nil {
		return err
	}
	if e.backend.ValidateSigned(r.Request, r.Signed) != nil || r.Request.Kind != "wager" || r.Result.Status != "CONFIRMED" || r.Request.Recipient != e.policy.BettingEscrow || !claimIDs.MatchString(a.ClaimID) || a.ClaimID == "889" || a.OwnerID == "" || len(a.OwnerID) > 128 || !nonzeroDigest(a.AllocationDigest) || !amount(a.AmountUWolo, 50000000000) ||
		(r.Request.OwnerID != "" && r.Request.OwnerID != a.OwnerID) || (a.ClaimKind != "bet_payout" && a.ClaimKind != "bet_refund") || (a.ClaimKind == "bet_refund" && a.AmountUWolo != r.Request.AmountUWolo) {
		return errors.New("owner_return_policy_refused")
	}
	now := e.now().Unix()
	if a.IssuedAt > now || a.ExpiresAt <= now || a.ExpiresAt <= a.IssuedAt || uint64(a.ExpiresAt)-uint64(a.IssuedAt) > 300 || len(e.policy.WithdrawalApprovalKey) != ed25519.PublicKeySize {
		return errors.New("owner_return_approval_refused")
	}
	sig, err := base64.StdEncoding.Strict().DecodeString(a.Signature)
	if err != nil || len(sig) != ed25519.SignatureSize || base64.StdEncoding.EncodeToString(sig) != a.Signature || !ed25519.Verify(e.policy.WithdrawalApprovalKey, ReturnApprovalMessage(a, e.policy), sig) {
		return errors.New("owner_return_approval_refused")
	}
	return nil
}
func (e *Engine) prepareReturn(a ReturnApproval) (returnRecord, error) {
	var out returnRecord
	err := e.db.Update(func(tx *bolt.Tx) error {
		b, err := tx.CreateBucketIfNotExists(returns)
		if err != nil {
			return err
		}
		old := b.Get([]byte(a.ClaimID))
		if old != nil {
			if json.Unmarshal(old, &out) != nil || out.Fingerprint != returnFingerprint(out.Approval) {
				return errors.New("return_state_corrupt")
			}
			if out.Fingerprint != returnFingerprint(a) {
				return errors.New("return_allocation_conflict")
			}
			if out.Receipt != nil {
				if !validReturnReceipt(out, *out.Receipt) {
					return errors.New("return_state_corrupt")
				}
				return nil
			}
		}
		key := []byte("return-operation:" + a.OperationID)
		if previous := tx.Bucket(meta).Get(key); previous != nil && string(previous) != a.ClaimID {
			return errors.New("operation_return_already_allocated")
		}
		if err := e.validateReturn(tx, a); err != nil {
			return err
		}
		if err := tx.Bucket(meta).Put(key, []byte(a.ClaimID)); err != nil {
			return err
		}
		out = returnRecord{Approval: a, Fingerprint: returnFingerprint(a)}
		data, _ := json.Marshal(out)
		return b.Put([]byte(a.ClaimID), data)
	})
	return out, err
}

// PrepareReturnRun durably binds owner/claim before returning an exact escrow
// execution request. A full unmatched refund is the original entire stake;
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
	r, err := e.prepareReturn(a)
	if err != nil {
		return ReturnReceipt{}, err
	}
	if r.Receipt != nil {
		if r.Receipt.TxHash != hash {
			return ReturnReceipt{}, errors.New("return_transaction_conflict")
		}
		return *r.Receipt, nil
	}
	proof, err := reader.ReadTransfer(ctx, satchel.TransferIntent{Sender: e.policy.BettingEscrow, Recipient: e.policy.Vault, AmountUWolo: a.AmountUWolo, Memo: "aoe2war/satchel/claim-return/v1/" + a.ClaimID}, hash)
	if err != nil || !proof.ConsensusAuthenticated() || proof.CreditAuthorized() {
		return ReturnReceipt{}, errors.New("return_proof_unavailable")
	}
	o := proof.Observation()
	receipt := ReturnReceipt{OperationID: a.OperationID, ClaimID: a.ClaimID, OwnerID: a.OwnerID, ClaimKind: a.ClaimKind, AmountUWolo: a.AmountUWolo, TxHash: hash, ReceiptID: proof.Receipt().ID(), Height: o.Height, BlockHash: o.BlockHash}
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
		data, _ := json.Marshal(r)
		return tx.Bucket(returns).Put([]byte(r.Approval.ClaimID), data)
	})
}

func validReturnReceipt(r returnRecord, p ReturnReceipt) bool {
	return p.OperationID == r.Approval.OperationID && p.ClaimID == r.Approval.ClaimID && p.OwnerID == r.Approval.OwnerID && p.ClaimKind == r.Approval.ClaimKind && p.AmountUWolo == r.Approval.AmountUWolo && !p.CreditAuthorized && p.Height > 0 && nonzeroDigest(p.BlockHash) && digestRE.MatchString(p.TxHash) && p.TxHash == strings.ToUpper(p.TxHash) && (p.ReceiptID == "wolo-1:"+p.TxHash+":0" || p.ReceiptID == "wolo-1:"+p.TxHash+":1")
}
