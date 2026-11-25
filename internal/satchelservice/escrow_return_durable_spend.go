package satchelservice

// This is the existing separately journaled ESCROW-account return boundary.
// Protected 8094 composition reuses it with the distinct SDK keyring role.
// It has no legacy 8092/8093 transport; source qualification grants no funding.
import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"

	"github.com/emaren/wolochain/internal/chainjson"

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
	Version               int
	ApprovalHash          string
	Request               TransferRequest
	ProofHash             string
	OperationPermitSHA256 string `json:",omitempty"`
	OperationNonce        string `json:",omitempty"`
	OperationPermitRaw    []byte `json:",omitempty"`
	ReserveReviewRaw      []byte `json:",omitempty"`
	Signed                SignedTransaction
	Result                EscrowReturnSpendResult
}

// Existing backend callbacks must re-validate protected escrow identity,
// signed accounting reserve, exclusive signer lease, and short-lived permit.
// No request data, optional flag, or owner-only self-attestation can replace
// these independent authorities.
type EscrowReturnSpendGuard struct {
	Permit       func(context.Context, TransferRequest) bool
	PreBroadcast func(context.Context, TransferRequest, SignedTransaction) bool
}

// ExecuteQualifiedEscrowReturn is the lower-level primitive for the
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
			if json.Unmarshal(prior, &state) != nil || !e.validEscrowSpendRecord(state, string(key)) ||
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
		// An unresolved escrow sequence also fences every later claim. New
		// permission is not proof that ambiguous signed bytes cannot execute.
		nonce := ""
		if operation, _ := ctx.Value(enrolledEscrowOperationKey{}).(*enrolledEscrowOperation); operation != nil {
			nonce = operation.nonce
		}
		if err := e.escrowSpendHistoryTx(tx, nonce); err != nil {
			return err
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
		if operation, _ := ctx.Value(enrolledEscrowOperationKey{}).(*enrolledEscrowOperation); operation != nil {
			state.OperationPermitSHA256, state.OperationNonce = operation.permitDigest, operation.nonce
			state.OperationPermitRaw = append([]byte(nil), operation.permitRaw...)
			state.ReserveReviewRaw = append([]byte(nil), operation.reviewRaw...)
		}
		if err := writeEscrowSpend(b, key, state); err != nil {
			return err
		}
		// Refuse before signing if the raw signed authorities cannot fit the
		// existing bounded journal. Preserve every old record on rollback.
		complete, err := e.custodyJournalTx(tx)
		if err != nil || complete.BytesRead > custodyJournalMaxBytes-(128<<10) {
			return ErrEscrowReturnSpend
		}
		return nil // reserve worst-case signed-byte/status growth before signing
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
	if err != nil || len(data) > 4<<20 {
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
		if json.Unmarshal(b.Get([]byte(id)), &state) != nil || !e.validEscrowSpendRecord(state, id) {
			return ErrEscrowReturnSpend
		}
		return nil
	})
	if err != nil {
		return none, ErrEscrowReturnSpend
	}
	return state.Result, nil
}

// Consistency-only recovery validation. It grants no current permission,
// native finality or credit, and does not require historical permits unexpired.
func (e *Engine) validEscrowSpendRecord(state escrowReturnSpendRecord, id string) bool {
	r, a := state.Request, state.Request.ReturnApproval
	if state.Version != 1 || !claimIDs.MatchString(id) || id == "889" || a == nil || a.Version != 2 || a.Allocation == nil || a.ClaimID != id ||
		r.OperationID != "satchel:claim-return:"+id || state.Result.OperationID != r.OperationID || state.ApprovalHash != hashJSON(r) ||
		r.Kind != "claim_return" || r.ChainID != "wolo-1" || r.Denom != "uwolo" || r.Sender != e.policy.BettingEscrow || r.Recipient != e.policy.Vault ||
		r.OwnerID != a.OwnerID || r.AmountUWolo != a.AmountUWolo || r.Memo != "aoe2war/satchel/claim-return/v1/"+id || r.Approval != nil || r.OwnerMandate != nil || r.Reservation != nil ||
		state.Result.Status != "UNKNOWN" || !state.Result.DurableFenced || !validReserveDigest(state.ProofHash) {
		return false
	}
	if state.Result.TxHash == "" {
		if len(state.Signed.Bytes) != 0 || state.Signed.Hash != "" {
			return false
		}
	} else if len(state.Signed.Bytes) == 0 || len(state.Signed.Bytes) > 65536 || state.Result.TxHash != state.Signed.Hash ||
		state.Signed.Hash != strings.ToUpper(state.Signed.Hash) || !nonzeroDigest(state.Signed.Hash) || !strings.EqualFold(custodySHA(state.Signed.Bytes), state.Signed.Hash) {
		return false
	}
	if state.OperationPermitSHA256 == "" && state.OperationNonce == "" && len(state.OperationPermitRaw) == 0 && len(state.ReserveReviewRaw) == 0 {
		return true
	} // original#122 records
	if !validReserveDigest(state.OperationNonce) || !validReserveDigest(state.OperationPermitSHA256) || len(state.OperationPermitRaw) > 64<<10 || len(state.ReserveReviewRaw) > escrowReturnExecutionMaxBytes ||
		!chainjson.ValidFolded(state.OperationPermitRaw) || !chainjson.ValidFolded(state.ReserveReviewRaw) || custodySHA(state.OperationPermitRaw) != state.OperationPermitSHA256 {
		return false
	}
	var permit EscrowReturnOperationPermit
	var review EscrowReturnExecutionBundle
	return strictHTTPJSON(state.OperationPermitRaw, &permit) == nil && strictHTTPJSON(state.ReserveReviewRaw, &review) == nil &&
		permit.Version == 1 && permit.Scope == escrowOperationPermitScope && permit.ChainID == "wolo-1" && permit.Denom == "uwolo" &&
		permit.Vault == e.policy.Vault && permit.Escrow == e.policy.BettingEscrow && review.Version == 1 && review.Body.Scope == EscrowReturnExecutionScope &&
		permit.Nonce == state.OperationNonce && permit.ApprovalSHA256 == hashJSON(*a) && permit.ClaimID == id && permit.AmountUWolo == a.AmountUWolo &&
		permit.ReserveReviewSHA256 == custodySHA(state.ReserveReviewRaw) && hashJSON(review) == state.ProofHash
}

// The same permanent uncertainty/nonce fence is used by read-only checks and
// the final atomic intent write. A check cannot clear or reserve any history.
func (e *Engine) escrowSpendHistoryTx(tx *bolt.Tx, nonce string) error {
	b := tx.Bucket(escrowReturnSpendBucket)
	if b == nil {
		return nil
	}
	prepared := tx.Bucket(returns)
	if prepared == nil {
		return ErrEscrowReturnSpend
	}
	return b.ForEach(func(id, data []byte) error {
		var old escrowReturnSpendRecord
		var paid returnRecord
		if data == nil || json.Unmarshal(data, &old) != nil || !e.validEscrowSpendRecord(old, string(id)) || old.Request.ReturnApproval == nil ||
			old.Request.OperationID != "satchel:claim-return:"+string(id) || old.ApprovalHash != hashJSON(old.Request) ||
			old.Result.Status != "UNKNOWN" || !old.Result.DurableFenced || old.Signed.Hash == "" ||
			json.Unmarshal(prepared.Get(id), &paid) != nil || paid.Receipt == nil || paid.Receipt.TxHash != old.Signed.Hash || !validReturnReceipt(paid, *paid.Receipt) ||
			(nonce != "" && old.OperationNonce == nonce) {
			return ErrEscrowReturnSpend
		}
		return nil
	})
}
