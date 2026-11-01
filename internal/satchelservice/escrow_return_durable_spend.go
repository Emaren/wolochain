package satchelservice

// This is the separately journaled ESCROW-account return execution boundary.
// It is NOT wired to the vault's 8094 HTTP service, legacy 8092, or a live
// keyring. Source qualification cannot enroll a signer or authorize funding.
// Existing signed reviewer reserve proof and native SDK backend are reused.
import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"

	bolt "go.etcd.io/bbolt"
)

var ErrEscrowReturnSpend = errors.New("escrow_return_spend_held")
var escrowReturnSpendBucket = []byte("escrow-return-spend-v1")

// EscrowReturnSpendResult always reports UNKNOWN after an attempted signing
// boundary. Broadcast acceptance is not mainnet finality or recipient credit.
type EscrowReturnSpendResult struct {
	OperationID   string `json:"operation_id"`
	Status        string `json:"status"`
	Reason        string `json:"reason"`
	TxHash        string `json:"tx_hash,omitempty"`
	DurableFenced bool   `json:"durable_fenced"`
}
type escrowReturnSpendRecord struct {
	Version      int
	ApprovalHash string
	Request      TransferRequest
	ProofHash    string
	Signed       SignedTransaction
	Result       EscrowReturnSpendResult
}

// Existing backend callbacks must re-validate protected escrow identity,
// signed accounting reserve, exclusive signer lease, and short-lived permit.
// No request data, optional flag, or owner-only self-attestation can replace
// these independent authorities.
type EscrowReturnSpendGuard struct {
	Permit       func(context.Context, TransferRequest) bool
	PreBroadcast func(context.Context, TransferRequest, SignedTransaction) bool
}

// ExecuteQualifiedEscrowReturn is an *unwired* source primitive for the
// separately enrolled escrow-account signer. All runs require a private opaque
// VerifiedEscrowReturnExecution, a prepared original owner entitlement, exact
// escrow→vault transfer, and independent permits. It never signs via e.backend.
// Every accepted claim ID is durably consumed even on ambiguous failure,
// and a replay can only READ the previous outcome.
func (e *Engine) ExecuteQualifiedEscrowReturn(
	ctx context.Context, a ReturnApproval, qualified VerifiedEscrowReturnExecution,
	escrow Backend, guards EscrowReturnSpendGuard,
) (EscrowReturnSpendResult, error) {
	none := EscrowReturnSpendResult{}
	if e == nil || e.db == nil || ctx == nil || ctx.Err() != nil ||
		escrow == nil || guards.Permit == nil || guards.PreBroadcast == nil ||
		qualified.engine != e || !qualified.CurrentFor(ctx, a) {
		return none, ErrEscrowReturnSpend
	}
	// Never let the request supply escrow address, beneficiary or fee.
	req := TransferRequest{OperationID: "satchel:claim-return:" + a.ClaimID,
		ChainID: "wolo-1", Denom: "uwolo", Sender: e.policy.BettingEscrow,
		Recipient: e.policy.Vault, Kind: "claim_return",
		AmountUWolo: a.AmountUWolo, OwnerID: a.OwnerID,
		Memo: "aoe2war/satchel/claim-return/v1/" + a.ClaimID, ReturnApproval: &a}
	if !guards.Permit(ctx, req) || req.Sender == req.Recipient ||
		!validAddress(req.Sender) || !validAddress(req.Recipient) ||
		!amount(req.AmountUWolo, e.policy.MaxAmountUWolo) {
		return none, ErrEscrowReturnSpend
	}
	e.mu.Lock()
	defer e.mu.Unlock()
	var state escrowReturnSpendRecord
	existing := false
	key := []byte(a.ClaimID)
	identity := hashJSON(req)
	err := e.db.Update(func(tx *bolt.Tx) error {
		b := tx.Bucket(escrowReturnSpendBucket)
		if b != nil && b.Get(key) != nil {
			prior := b.Get(key)
			existing = true
			if json.Unmarshal(prior, &state) != nil || state.Version != 1 ||
				state.ApprovalHash != identity ||
				state.Result.OperationID != req.OperationID ||
				!state.Result.DurableFenced {
				return ErrEscrowReturnSpend
			}
			return nil
		}
		// Under the original engine mutex and the same Bolt transaction,
		// recheck journal, allocation, receipt and signed reserve identity.
		if qualified.now == nil {
			return ErrEscrowReturnSpend
		}
		now := qualified.now()
		if now.IsZero() ||
			!now.Before(qualified.expires) || !qualified.bank.CurrentAt(now) ||
			qualified.claimFingerprint != returnFingerprint(a) ||
			qualified.allocationDigest != a.AllocationDigest ||
			!validReserveDigest(qualified.bundleHash) || ctx.Err() != nil {
			return ErrEscrowReturnSpend
		}
		journal, err := e.custodyJournalTx(tx)
		if err != nil || journal.JournalDigest != qualified.journalHash ||
			journal.PolicyDigest != qualified.policyHash ||
			e.validateReturnAt(tx, a, true) != nil {
			return ErrEscrowReturnSpend
		}
		prepared := tx.Bucket(returns)
		if prepared == nil {
			return ErrEscrowReturnSpend
		}
		raw := prepared.Get(key)
		var original returnRecord
		if raw == nil || json.Unmarshal(raw, &original) != nil ||
			original.Receipt != nil || original.Fingerprint != returnFingerprint(a) ||
			hashJSON(original.Approval) != hashJSON(a) {
			return ErrEscrowReturnSpend
		}
		// The verified reserve snapshot binds the *old* Bolt bucket tree.
		// Creating the new spend bucket before the journal comparison would
		// invalidate its own independently signed snapshot.
		b, err = tx.CreateBucketIfNotExists(escrowReturnSpendBucket)
		if err != nil {
			return err
		}
		state = escrowReturnSpendRecord{Version: 1, ApprovalHash: identity,
			Request: req, ProofHash: qualified.bundleHash,
			Result: EscrowReturnSpendResult{OperationID: req.OperationID,
				Status: "UNKNOWN", Reason: "intent_persisted", DurableFenced: true}}
		return writeEscrowSpend(b, key, state)
	})
	if err != nil {
		return none, ErrEscrowReturnSpend
	}
	if existing {
		return state.Result, nil
	}

	update := func(reason string, signed *SignedTransaction) error {
		state.Result.Reason = reason
		if signed != nil {
			state.Signed = *signed
			state.Result.TxHash = signed.Hash
		}
		return e.db.Update(func(tx *bolt.Tx) error {
			b := tx.Bucket(escrowReturnSpendBucket)
			if b == nil || b.Get(key) == nil {
				return ErrEscrowReturnSpend
			}
			return writeEscrowSpend(b, key, state)
		})
	}
	// On any uncertainty there is no second attempt. The original intent is
	// retained forever, including across process crashes and permit expiry.
	if ctx.Err() != nil || !guards.Permit(ctx, req) ||
		!qualified.now().Before(qualified.expires) {
		if update("pre_sign_permit_revoked", nil) != nil {
			return none, ErrEscrowReturnSpend
		}
		return state.Result, nil
	}
	if update("signing_started", nil) != nil {
		return none, ErrEscrowReturnSpend
	}
	signed, err := escrow.Sign(ctx, req)
	if err != nil {
		if update("signing_uncertain", nil) != nil {
			return none, ErrEscrowReturnSpend
		}
		return state.Result, nil
	}
	sum := sha256.Sum256(signed.Bytes)
	if len(signed.Bytes) == 0 || len(signed.Bytes) > 65536 ||
		!strings.EqualFold(signed.Hash, hex.EncodeToString(sum[:])) ||
		escrow.ValidateSigned(req, signed) != nil {
		if update("invalid_signed_bytes_unknown", nil) != nil {
			return none, ErrEscrowReturnSpend
		}
		return state.Result, nil
	}
	signed.Hash = strings.ToUpper(signed.Hash)
	if update("signed_bytes_persisted", &signed) != nil {
		return none, ErrEscrowReturnSpend
	}
	if ctx.Err() != nil || !guards.PreBroadcast(ctx, req, signed) ||
		!guards.Permit(ctx, req) || !qualified.now().Before(qualified.expires) {
		if update("signed_permit_revoked_unknown", nil) != nil {
			return none, ErrEscrowReturnSpend
		}
		return state.Result, nil
	}
	if update("broadcast_started", nil) != nil {
		return none, ErrEscrowReturnSpend
	}
	sent, err := escrow.Broadcast(ctx, signed)
	if err != nil || sent.Status != "ACCEPTED" || sent.Code != 0 {
		if update("broadcast_uncertain", nil) != nil {
			return none, ErrEscrowReturnSpend
		}
		return state.Result, nil
	}
	if update("broadcast_accepted_unconfirmed", nil) != nil {
		return none, ErrEscrowReturnSpend
	}
	return state.Result, nil
}

func writeEscrowSpend(b *bolt.Bucket, key []byte, state escrowReturnSpendRecord) error {
	data, err := json.Marshal(state)
	if err != nil || len(data) > 131072 {
		return ErrEscrowReturnSpend
	}
	return b.Put(key, data)
}

// Journal reading is limited to existing operation identities. This cannot
// authorize a broadcast or turn acceptance into a paid return receipt.
func (e *Engine) ReadEscrowReturnSpend(id string) (EscrowReturnSpendResult, error) {
	none := EscrowReturnSpendResult{}
	if e == nil || e.db == nil || !claimIDs.MatchString(id) {
		return none, ErrEscrowReturnSpend
	}
	e.mu.Lock()
	defer e.mu.Unlock()
	var state escrowReturnSpendRecord
	err := e.db.View(func(tx *bolt.Tx) error {
		b := tx.Bucket(escrowReturnSpendBucket)
		if b == nil || b.Get([]byte(id)) == nil {
			return ErrEscrowReturnSpend
		}
		if json.Unmarshal(b.Get([]byte(id)), &state) != nil || state.Version != 1 ||
			state.Result.Status != "UNKNOWN" || !state.Result.DurableFenced ||
			state.Result.OperationID != "satchel:claim-return:"+id ||
			state.ApprovalHash != hashJSON(state.Request) {
			return ErrEscrowReturnSpend
		}
		return nil
	})
	if err != nil {
		return none, ErrEscrowReturnSpend
	}
	return state.Result, nil
}
