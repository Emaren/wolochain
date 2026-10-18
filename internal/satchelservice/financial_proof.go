package satchelservice

// Financial proofs export the existing authenticated reader's evidence. They
// do not introduce a receipt-signing key, trust root, credit or broadcast API.
import (
	"bytes"
	"context"
	"crypto/ed25519"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"github.com/emaren/wolochain/internal/satchel"
	bolt "go.etcd.io/bbolt"
)

// DepositProofRequest is supplied by the authenticated HD server from its
// immutable intent. The vault, chain, denomination and trust sources are never
// request parameters. A player/browser must not hold the service bearer token.
type DepositProofRequest struct {
	Protocol    int    `json:"protocol"`
	OwnerID     string `json:"owner_id"`
	Sender      string `json:"sender"`
	AmountUWolo string `json:"amount_uwolo"`
	Memo        string `json:"memo"`
	CreatedAt   string `json:"created_at"`
	ExpiresAt   string `json:"expires_at"`
	TxHash      string `json:"tx_hash"`
}

// FinancialProofContext must be reconstructed from the consumer's own durable
// expected request. Taking this context from the proof itself proves nothing
// about the intended owner or accounting obligation.
type FinancialProofContext struct {
	Protocol           int                     `json:"protocol"`
	Kind               string                  `json:"kind"`
	OwnerID            string                  `json:"owner_id"`
	OperationID        string                  `json:"operation_id,omitempty"`
	Sender             string                  `json:"sender"`
	Recipient          string                  `json:"recipient"`
	AmountUWolo        string                  `json:"amount_uwolo"`
	Memo               string                  `json:"memo"`
	TxHash             string                  `json:"tx_hash"`
	FundedAmountUWolo  string                  `json:"funded_amount_uwolo,omitempty"`
	CreatedAt          string                  `json:"created_at,omitempty"`
	ExpiresAt          string                  `json:"expires_at,omitempty"`
	WithdrawalApproval *WithdrawalApproval     `json:"withdrawal_approval,omitempty"`
	OwnerMandate       *OwnerWithdrawalMandate `json:"owner_mandate,omitempty"`
	ReturnApproval     *ReturnApproval         `json:"return_approval,omitempty"`
}

// FinancialProof is a transport envelope, not an attestation. A consumer must
// independently run VerifyFinancialProof with operator-provisioned trust and
// its own durable expected context before using the verified receipt identity.
type FinancialProof struct {
	Protocol               int                   `json:"protocol"`
	ChainID                string                `json:"chain_id"`
	Denom                  string                `json:"denom"`
	Context                FinancialProofContext `json:"context"`
	ContextDigest          string                `json:"context_digest"`
	TxHash                 string                `json:"tx_hash"`
	ReceiptID              string                `json:"receipt_id"`
	TransferIndex          uint32                `json:"transfer_index"`
	MessageIndex           uint32                `json:"message_index"`
	Height                 int64                 `json:"height"`
	BlockHash              string                `json:"block_hash"`
	ConsensusAuthenticated bool                  `json:"consensus_authenticated"`
	CreditAuthorized       bool                  `json:"credit_authorized"`
	Proof                  satchel.PortableProof `json:"proof"`
}

// FinancialProofVerifierConfig contains only public, independently provisioned
// authority. Never populate it from an HTTP response or proof artifact.
type FinancialProofVerifierConfig struct {
	TrustAnchor          satchel.TrustAnchor `json:"trust_anchor"`
	Vault                string              `json:"vault"`
	BettingEscrow        string              `json:"betting_escrow"`
	ApprovalPublicKeyHex string              `json:"approval_public_key_hex"`
}

type VerifiedFinancialReceipt struct {
	Protocol         int    `json:"protocol"`
	Kind             string `json:"kind"`
	ChainID          string `json:"chain_id"`
	Denom            string `json:"denom"`
	OwnerID          string `json:"owner_id"`
	OperationID      string `json:"operation_id,omitempty"`
	ContextDigest    string `json:"context_digest"`
	TxHash           string `json:"tx_hash"`
	ReceiptID        string `json:"receipt_id"`
	TransferIndex    uint32 `json:"transfer_index"`
	MessageIndex     uint32 `json:"message_index"`
	Height           int64  `json:"height"`
	BlockHash        string `json:"block_hash"`
	CreditAuthorized bool   `json:"credit_authorized"`
}

func FinancialContextDigest(c FinancialProofContext) string {
	// The field ordering is fixed by this struct's v1 wire contract. This digest
	// is context binding; it is not a signature or a bank/liability certificate.
	return hashJSON(c)
}

func depositContext(r DepositProofRequest, vault string) (FinancialProofContext, satchel.Intent, error) {
	created, e1 := time.Parse(time.RFC3339Nano, r.CreatedAt)
	expires, e2 := time.Parse(time.RFC3339Nano, r.ExpiresAt)
	if r.Protocol != 1 || !ownerUIDPattern.MatchString(r.OwnerID) || !validAddress(r.Sender) || !validAddress(vault) ||
		!amount(r.AmountUWolo, 100000000000000) || r.Memo == "" || len(r.Memo) > 256 || !nonzeroDigest(r.TxHash) || e1 != nil || e2 != nil {
		return FinancialProofContext{}, satchel.Intent{}, errors.New("invalid_deposit_proof_request")
	}
	c := FinancialProofContext{Protocol: 1, Kind: "deposit", OwnerID: r.OwnerID, Sender: r.Sender, Recipient: vault, AmountUWolo: r.AmountUWolo, Memo: r.Memo, TxHash: strings.ToUpper(r.TxHash), CreatedAt: r.CreatedAt, ExpiresAt: r.ExpiresAt}
	return c, satchel.Intent{OwnerID: r.OwnerID, Sender: r.Sender, Vault: vault, AmountUWolo: r.AmountUWolo, Memo: r.Memo, CreatedAt: created, ExpiresAt: expires}, nil
}

func financialEnvelope(c FinancialProofContext, e satchel.AuthenticatedEvidence, p satchel.PortableProof) (FinancialProof, error) {
	if !e.ConsensusAuthenticated() || e.CreditAuthorized() {
		return FinancialProof{}, errors.New("authenticated_financial_proof_unavailable")
	}
	o := e.Observation()
	r := e.Receipt()
	if o.Code == nil || *o.Code != 0 || o.TransferIndex == nil || o.Height <= 0 || !nonzeroDigest(o.BlockHash) ||
		o.TxHash != r.TxHash || o.ChainID != satchel.ChainID || r.ChainID != satchel.ChainID {
		return FinancialProof{}, errors.New("authenticated_financial_proof_mismatch")
	}
	return FinancialProof{Protocol: 1, ChainID: satchel.ChainID, Denom: satchel.Denom, Context: c, ContextDigest: FinancialContextDigest(c), TxHash: r.TxHash,
		ReceiptID: r.ID(), TransferIndex: r.TransferIndex, Height: o.Height, BlockHash: o.BlockHash, ConsensusAuthenticated: true, Proof: p}, nil
}

func (e *Engine) DepositProof(ctx context.Context, r DepositProofRequest, reader *satchel.TrustedReader) (FinancialProof, error) {
	if reader == nil {
		return FinancialProof{}, errors.New("financial_proof_reader_unavailable")
	}
	c, i, err := depositContext(r, e.policy.Vault)
	if err != nil {
		return FinancialProof{}, err
	}
	evidence, proof, err := reader.ReadDepositProof(ctx, i, strings.ToUpper(r.TxHash))
	if err != nil {
		return FinancialProof{}, err
	}
	return financialEnvelope(c, evidence, proof)
}

func operationContext(r record) (FinancialProofContext, error) {
	i := r.Request
	if (i.Kind != "withdrawal" && i.Kind != "wager") || !ownerUIDPattern.MatchString(i.OwnerID) {
		return FinancialProofContext{}, errors.New("operation_owner_binding_unavailable")
	}
	return FinancialProofContext{Protocol: 1, Kind: i.Kind, OwnerID: i.OwnerID, OperationID: i.OperationID, Sender: i.Sender, Recipient: i.Recipient, AmountUWolo: i.AmountUWolo, Memo: i.Memo, TxHash: r.Signed.Hash, WithdrawalApproval: i.Approval, OwnerMandate: i.OwnerMandate}, nil
}

// operationProofRecord is a read-only snapshot. It never invokes Sign,
// Broadcast, Reconcile or any journal Update, including after an unknown send.
func (e *Engine) operationProofRecord(id string) (record, FinancialProofContext, error) {
	e.mu.Lock()
	defer e.mu.Unlock()
	var r record
	err := e.db.View(func(tx *bolt.Tx) error { var err error; r, err = load(tx, id); return err })
	if err != nil {
		return record{}, FinancialProofContext{}, err
	}
	if r.Result.Status == "FAILED" || r.Result.Status == "REFUSED" || len(r.Signed.Bytes) == 0 || e.backend.ValidateSigned(r.Request, r.Signed) != nil {
		return record{}, FinancialProofContext{}, errors.New("operation_proof_unavailable")
	}
	c, err := operationContext(r)
	return r, c, err
}

func (e *Engine) OperationProof(ctx context.Context, id string, reader *satchel.TrustedReader) (FinancialProof, error) {
	if reader == nil || !ids.MatchString(id) {
		return FinancialProof{}, errors.New("financial_proof_reader_unavailable")
	}
	r, c, err := e.operationProofRecord(id)
	if err != nil {
		return FinancialProof{}, err
	}
	evidence, proof, err := reader.ReadTransferProof(ctx, satchel.TransferIntent{Sender: c.Sender, Recipient: c.Recipient, AmountUWolo: c.AmountUWolo, Memo: c.Memo}, r.Signed.Hash)
	if err != nil {
		return FinancialProof{}, err
	}
	if !bytes.Equal(evidence.Observation().TxBytes, r.Signed.Bytes) {
		return FinancialProof{}, errors.New("operation_signed_transaction_mismatch")
	}
	return financialEnvelope(c, evidence, proof)
}

func (e *Engine) returnProofRecord(claim string) (returnRecord, FinancialProofContext, error) {
	e.mu.Lock()
	defer e.mu.Unlock()
	var r returnRecord
	var funded string
	err := e.db.View(func(tx *bolt.Tx) error {
		b := tx.Bucket(returns)
		if b == nil || b.Get([]byte(claim)) == nil {
			return errors.New("return_not_prepared")
		}
		if json.Unmarshal(b.Get([]byte(claim)), &r) != nil || r.Approval.ClaimID != claim || r.Fingerprint != returnFingerprint(r.Approval) || r.Receipt == nil || !validReturnReceipt(r, *r.Receipt) {
			return errors.New("return_proof_unavailable")
		}
		if err := e.validateReturnAt(tx, r.Approval, false); err != nil {
			return err
		}
		funding, err := load(tx, r.Approval.OperationID)
		if err != nil {
			return err
		}
		funded = funding.Request.AmountUWolo
		return nil
	})
	if err != nil {
		return returnRecord{}, FinancialProofContext{}, err
	}
	a := r.Approval
	c := FinancialProofContext{Protocol: 1, Kind: "claim_return", OwnerID: a.OwnerID, OperationID: a.OperationID, Sender: e.policy.BettingEscrow, Recipient: e.policy.Vault, AmountUWolo: a.AmountUWolo, Memo: "aoe2war/satchel/claim-return/v1/" + a.ClaimID, TxHash: r.Receipt.TxHash, FundedAmountUWolo: funded, ReturnApproval: &a}
	return r, c, nil
}

// ReturnProof requires a receipt already durably reconciled by the existing
// v2 return path. Neither a new hash nor new owner/allocation can be supplied.
func (e *Engine) ReturnProof(ctx context.Context, claim string, reader *satchel.TrustedReader) (FinancialProof, error) {
	if reader == nil || !claimIDs.MatchString(claim) || claim == "889" {
		return FinancialProof{}, errors.New("financial_proof_reader_unavailable")
	}
	r, c, err := e.returnProofRecord(claim)
	if err != nil {
		return FinancialProof{}, err
	}
	evidence, proof, err := reader.ReadTransferProof(ctx, satchel.TransferIntent{Sender: c.Sender, Recipient: c.Recipient, AmountUWolo: c.AmountUWolo, Memo: c.Memo}, r.Receipt.TxHash)
	if err != nil {
		return FinancialProof{}, err
	}
	o := evidence.Observation()
	if evidence.Receipt().ID() != r.Receipt.ReceiptID || o.Height != r.Receipt.Height || o.BlockHash != r.Receipt.BlockHash {
		return FinancialProof{}, errors.New("return_committed_identity_mismatch")
	}
	return financialEnvelope(c, evidence, proof)
}

func verifierPolicy(c FinancialProofVerifierConfig) (Policy, error) {
	key, err := hex.DecodeString(c.ApprovalPublicKeyHex)
	if err != nil || len(key) != ed25519.PublicKeySize || !validAddress(c.Vault) || satchel.IsKnownRoleAddress(c.Vault) || !validAddress(c.BettingEscrow) || c.Vault == c.BettingEscrow {
		return Policy{}, errors.New("invalid_financial_verifier_authority")
	}
	return Policy{Vault: c.Vault, BettingEscrow: c.BettingEscrow, ProtectedAddresses: []string{c.BettingEscrow}, MaxAmountUWolo: 50000000000, WithdrawalApprovalKey: key}, nil
}

// VerifyFinancialProof performs independent, offline Comet authentication and
// exact expected economic/owner binding. Its receipt remains NONCREDITING: HD
// must atomically claim physical (chain, tx hash) uniqueness and the durable
// obligation in its own ledger transaction, with the activation hold intact.
func VerifyFinancialProof(ctx context.Context, cfg FinancialProofVerifierConfig, expected FinancialProofContext, p FinancialProof) (VerifiedFinancialReceipt, error) {
	policy, err := verifierPolicy(cfg)
	if err != nil {
		return VerifiedFinancialReceipt{}, err
	}
	if expected.Protocol != 1 || !ownerUIDPattern.MatchString(expected.OwnerID) || !validAddress(expected.Sender) || !validAddress(expected.Recipient) || expected.Sender == expected.Recipient || !amount(expected.AmountUWolo, 100000000000000) || expected.Memo == "" || len(expected.Memo) > 256 ||
		p.Protocol != 1 || p.ChainID != satchel.ChainID || p.Denom != satchel.Denom || p.CreditAuthorized || !p.ConsensusAuthenticated || p.ContextDigest != FinancialContextDigest(expected) || FinancialContextDigest(p.Context) != p.ContextDigest || !nonzeroDigest(p.TxHash) || p.TxHash != strings.ToUpper(p.TxHash) || expected.TxHash != p.TxHash || p.MessageIndex != 0 {
		return VerifiedFinancialReceipt{}, errors.New("financial_proof_context_mismatch")
	}
	v, err := satchel.NewProofVerifier(cfg.TrustAnchor)
	if err != nil {
		return VerifiedFinancialReceipt{}, err
	}
	var evidence satchel.AuthenticatedEvidence
	switch expected.Kind {
	case "deposit":
		if expected.OperationID != "" || expected.FundedAmountUWolo != "" || expected.WithdrawalApproval != nil || expected.OwnerMandate != nil || expected.ReturnApproval != nil || expected.Recipient != policy.Vault {
			return VerifiedFinancialReceipt{}, errors.New("financial_deposit_context_refused")
		}
		_, i, err := depositContext(DepositProofRequest{Protocol: 1, OwnerID: expected.OwnerID, Sender: expected.Sender, AmountUWolo: expected.AmountUWolo, Memo: expected.Memo, CreatedAt: expected.CreatedAt, ExpiresAt: expected.ExpiresAt, TxHash: p.TxHash}, policy.Vault)
		if err != nil {
			return VerifiedFinancialReceipt{}, err
		}
		evidence, err = v.VerifyDepositProof(ctx, i, p.TxHash, p.Proof)
		if err != nil {
			return VerifiedFinancialReceipt{}, err
		}
	case "withdrawal", "wager":
		if expected.CreatedAt != "" || expected.ExpiresAt != "" || expected.FundedAmountUWolo != "" || expected.ReturnApproval != nil {
			return VerifiedFinancialReceipt{}, errors.New("financial_operation_context_refused")
		}
		r := TransferRequest{OperationID: expected.OperationID, Kind: expected.Kind, ChainID: satchel.ChainID, Denom: satchel.Denom, OwnerID: expected.OwnerID, Sender: expected.Sender, Recipient: expected.Recipient, AmountUWolo: expected.AmountUWolo, Memo: expected.Memo, Approval: expected.WithdrawalApproval, OwnerMandate: expected.OwnerMandate}
		t := time.Now()
		if r.Kind == "withdrawal" && r.Approval != nil {
			// This is verification of the original, journaled approval, not a new
			// authorization to submit after its short execution window expires.
			t = time.Unix(r.Approval.IssuedAt, 0)
			if r.OwnerMandate != nil {
				issued, parseErr := time.Parse(time.RFC3339Nano, r.OwnerMandate.Challenge.IssuedAtUTC)
				if parseErr == nil && issued.After(t) {
					t = issued
				}
			}
		}
		if policy.validate(r, t) != nil {
			return VerifiedFinancialReceipt{}, errors.New("financial_operation_authority_refused")
		}
		evidence, err = v.VerifyTransferProof(ctx, satchel.TransferIntent{Sender: expected.Sender, Recipient: expected.Recipient, AmountUWolo: expected.AmountUWolo, Memo: expected.Memo}, p.TxHash, p.Proof)
		if err != nil {
			return VerifiedFinancialReceipt{}, err
		}
	case "claim_return":
		if expected.CreatedAt != "" || expected.ExpiresAt != "" || expected.WithdrawalApproval != nil || expected.OwnerMandate != nil || verifyReturnContext(expected, policy) != nil {
			return VerifiedFinancialReceipt{}, errors.New("financial_return_authority_refused")
		}
		evidence, err = v.VerifyTransferProof(ctx, satchel.TransferIntent{Sender: expected.Sender, Recipient: expected.Recipient, AmountUWolo: expected.AmountUWolo, Memo: expected.Memo}, p.TxHash, p.Proof)
		if err != nil {
			return VerifiedFinancialReceipt{}, err
		}
	default:
		return VerifiedFinancialReceipt{}, errors.New("financial_proof_kind_refused")
	}
	verified, err := financialEnvelope(expected, evidence, p.Proof)
	if err != nil || verified.TxHash != p.TxHash || verified.ReceiptID != p.ReceiptID || verified.TransferIndex != p.TransferIndex || verified.Height != p.Height || verified.BlockHash != p.BlockHash {
		return VerifiedFinancialReceipt{}, errors.New("financial_proof_receipt_mismatch")
	}
	return VerifiedFinancialReceipt{Protocol: 1, Kind: expected.Kind, ChainID: satchel.ChainID, Denom: satchel.Denom, OwnerID: expected.OwnerID, OperationID: expected.OperationID, ContextDigest: p.ContextDigest, TxHash: verified.TxHash, ReceiptID: verified.ReceiptID, TransferIndex: verified.TransferIndex, Height: verified.Height, BlockHash: verified.BlockHash}, nil
}

// verifyReturnContext verifies the SAME signed v2 messages as the journal. It
// authenticates reviewer attribution, not the completeness of bank reserves.
// Full allocation conservation remains validateAllocation's journal contract.
func verifyReturnContext(c FinancialProofContext, p Policy) error {
	a := c.ReturnApproval
	if a == nil || a.Allocation == nil || !httpReturnV2(*a) || a.ClaimID == "889" || a.OwnerID != c.OwnerID || a.OperationID != c.OperationID || a.AmountUWolo != c.AmountUWolo || c.Sender != p.BettingEscrow || c.Recipient != p.Vault || c.Memo != "aoe2war/satchel/claim-return/v1/"+a.ClaimID ||
		!validReviewTime(a.IssuedAt, a.ExpiresAt, a.IssuedAt, false) || !verifyReview(p.WithdrawalApprovalKey, ReturnApprovalMessage(*a, p), a.Signature) {
		return errors.New("financial_return_approval_refused")
	}
	plan := a.Allocation
	if !boundedAllocation(plan) || plan.Version != 2 || !ids.MatchString(plan.AllocationID) || plan.Revision == 0 || plan.Revision > 100000 || plan.OwnerID != a.OwnerID || plan.OperationID != a.OperationID || plan.TicketID != a.TicketID || !claimIDs.MatchString(plan.TicketID) || !nonzeroDigest(plan.FundingTxHash) || plan.FundingTxHash != strings.ToUpper(plan.FundingTxHash) || !ids.MatchString(plan.FundsBudgetID) || !nonzeroDigest(plan.BankEvidenceDigest) || plan.BankHeight <= 0 || !nonzeroDigest(plan.BankBlockHash) || a.AllocationDigest != AllocationDigest(*plan, p) || !validReviewTime(plan.IssuedAt, plan.ExpiresAt, plan.IssuedAt, false) || !verifyReview(p.WithdrawalApprovalKey, AllocationMessage(*plan, p), plan.Signature) {
		return errors.New("financial_return_allocation_refused")
	}
	funded, ok := positive(c.FundedAmountUWolo, 1000000000)
	if !ok {
		return errors.New("financial_return_funding_context_refused")
	}
	if _, err := validateAllocationEconomics(*a, funded); err != nil {
		return err
	}
	return nil
}
