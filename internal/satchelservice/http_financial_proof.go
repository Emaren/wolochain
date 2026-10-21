package satchelservice

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	"github.com/emaren/wolochain/internal/chainjson"
	"github.com/emaren/wolochain/internal/satchel"
)

const MaxFinancialProofBytes = satchel.MaxPortableProofBytes + (64 << 10)

func DecodeFinancialProof(data []byte) (FinancialProof, error) {
	var p FinancialProof
	if len(data) == 0 || len(data) > MaxFinancialProofBytes || !chainjson.Valid(data) || strictHTTPJSON(data, &p) != nil {
		return FinancialProof{}, errors.New("invalid_financial_proof_encoding")
	}
	fields, ok := chainjson.Object(data)
	if !ok {
		return FinancialProof{}, errors.New("invalid_financial_proof_encoding")
	}
	portable, err := satchel.DecodePortableProof(fields["proof"])
	if err != nil {
		return FinancialProof{}, err
	}
	p.Proof = portable
	return p, nil
}

func DecodeFinancialProofContext(data []byte) (FinancialProofContext, error) {
	var c FinancialProofContext
	if len(data) == 0 || len(data) > 64<<10 || !chainjson.Valid(data) || strictHTTPJSON(data, &c) != nil {
		return FinancialProofContext{}, errors.New("invalid_financial_context_encoding")
	}
	return c, nil
}

func DecodeFinancialProofVerifierConfig(data []byte) (FinancialProofVerifierConfig, error) {
	var c FinancialProofVerifierConfig
	if len(data) == 0 || len(data) > 64<<10 || !chainjson.Valid(data) || strictHTTPJSON(data, &c) != nil {
		return FinancialProofVerifierConfig{}, errors.New("invalid_financial_verifier_encoding")
	}
	if _, err := verifierPolicy(c); err != nil {
		return FinancialProofVerifierConfig{}, err
	}
	return c, nil
}

func financialProofReason(err error) string {
	var evidence *satchel.EvidenceError
	if errors.As(err, &evidence) {
		return string(evidence.Code)
	}
	if errors.Is(err, context.Canceled) {
		return "canceled"
	}
	if errors.Is(err, context.DeadlineExceeded) {
		return "timed_out"
	}
	// Do not expose remote bodies, configuration paths or arbitrary errors.
	for _, safe := range []string{"operation_not_found", "operation_proof_unavailable", "operation_owner_binding_unavailable", "return_not_prepared", "return_proof_unavailable", "state_corrupt", "return_state_corrupt", "invalid_deposit_proof_request"} {
		if err != nil && err.Error() == safe {
			return safe
		}
	}
	return "financial_proof_unavailable"
}

func (h *privateHTTPHandler) financialProof(ctx context.Context, w http.ResponseWriter, path string, data []byte) {
	if path == "/satchel/v1/proofs/bank" {
		h.bankProof(ctx, w, data)
		return
	}
	backend, ok := h.backend.(HTTPFinancialProofBackend)
	if !ok {
		httpFailure(w, http.StatusServiceUnavailable, "financial_proof_adapter_unavailable")
		return
	}
	var p FinancialProof
	var err error
	var expected *FinancialProofContext
	switch path {
	case "/satchel/v1/proofs/deposit":
		var input DepositProofRequest
		if strictHTTPJSON(data, &input) != nil {
			httpFailure(w, http.StatusBadRequest, "invalid_deposit_proof_request")
			return
		}
		c, _, decodeErr := depositContext(input, h.identity.VaultAddress)
		if decodeErr != nil {
			httpFailure(w, http.StatusBadRequest, "invalid_deposit_proof_request")
			return
		}
		expected = &c
		p, err = backend.DepositProof(ctx, input)
		if err == nil && p.TxHash != strings.ToUpper(input.TxHash) {
			err = errors.New("financial_proof_identity_mismatch")
		}
	case "/satchel/v1/proofs/operation":
		var input struct {
			OperationID string `json:"operation_id"`
		}
		if strictHTTPJSON(data, &input) != nil || !httpOperationPattern.MatchString(input.OperationID) {
			httpFailure(w, http.StatusBadRequest, "invalid_operation_proof_request")
			return
		}
		p, err = backend.OperationProof(ctx, input.OperationID)
		if err == nil && (p.Context.OperationID != input.OperationID || (p.Context.Kind != "wager" && p.Context.Kind != "withdrawal") || p.Context.Sender != h.identity.VaultAddress) {
			err = errors.New("financial_proof_identity_mismatch")
		}
	case "/satchel/v1/proofs/return":
		var input struct {
			ClaimID string `json:"claim_id"`
		}
		if strictHTTPJSON(data, &input) != nil || !claimIDs.MatchString(input.ClaimID) || input.ClaimID == "889" {
			httpFailure(w, http.StatusBadRequest, "invalid_return_proof_request")
			return
		}
		p, err = backend.ReturnProof(ctx, input.ClaimID)
		if err == nil && (p.Context.Kind != "claim_return" || p.Context.ReturnApproval == nil || p.Context.ReturnApproval.ClaimID != input.ClaimID || p.Context.Recipient != h.identity.VaultAddress) {
			err = errors.New("financial_proof_identity_mismatch")
		}
	}
	if ctx.Err() != nil {
		err = ctx.Err()
	}
	if err != nil {
		httpWrite(w, http.StatusConflict, map[string]any{"kind": "unverifiable", "status": "UNVERIFIABLE", "reason": financialProofReason(err), "credit_authorized": false})
		return
	}
	if p.Protocol != 1 || p.ChainID != satchel.ChainID || p.Denom != satchel.Denom || !p.ConsensusAuthenticated || p.CreditAuthorized ||
		!ownerUIDPattern.MatchString(p.Context.OwnerID) || p.ContextDigest != FinancialContextDigest(p.Context) || (expected != nil && p.ContextDigest != FinancialContextDigest(*expected)) ||
		!nonzeroDigest(p.TxHash) || p.Context.TxHash != p.TxHash || p.TxHash != strings.ToUpper(p.TxHash) || p.Height <= 0 || !nonzeroDigest(p.BlockHash) || p.TransferIndex > 1 || p.MessageIndex != 0 || p.ReceiptID != (satchel.ReceiptCandidate{ChainID: satchel.ChainID, TxHash: p.TxHash, TransferIndex: p.TransferIndex}).ID() {
		httpFailure(w, http.StatusServiceUnavailable, "financial_proof_identity_unverifiable")
		return
	}
	encoded, err := json.Marshal(p)
	if err != nil || len(encoded) > MaxFinancialProofBytes {
		httpFailure(w, http.StatusServiceUnavailable, "financial_proof_size_refused")
		return
	}
	// This validates framing; independent authenticity is VerifyFinancialProof.
	if _, err := DecodeFinancialProof(encoded); err != nil {
		httpFailure(w, http.StatusServiceUnavailable, "financial_proof_encoding_refused")
		return
	}
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(encoded)
}
