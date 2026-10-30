package satchelservice

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"

	"github.com/emaren/wolochain/internal/satchel"
)

type HTTPEscrowBankProofBackend interface {
	EscrowBankProof(context.Context) (satchel.BankProof, error)
}

// EscrowBankProof selects only the protected betting escrow, independently of
// the custody vault. It reads genuine current H/H+1 evidence; no caller can
// substitute an account, proof root, height, balance or spendability assertion.
func (e *Engine) EscrowBankProof(ctx context.Context, reader *satchel.TrustedReader) (satchel.BankProof, error) {
	if e == nil || reader == nil || ctx == nil || ctx.Err() != nil || !validAddress(e.policy.BettingEscrow) || e.policy.Vault == e.policy.BettingEscrow {
		return satchel.BankProof{}, errors.New("escrow_bank_proof_unavailable")
	}
	_, proof, err := reader.ReadCurrentBankProof(ctx, e.policy.BettingEscrow)
	return proof, err
}

func (h *privateHTTPHandler) escrowBankProof(ctx context.Context, w http.ResponseWriter, data []byte) {
	var request struct {
		Protocol int `json:"protocol"`
	}
	if strictHTTPJSON(data, &request) != nil || request.Protocol != 1 {
		httpFailure(w, http.StatusBadRequest, "invalid_escrow_bank_proof_request")
		return
	}
	backend, ok := h.backend.(HTTPEscrowBankProofBackend)
	if !ok || !validAddress(h.identity.EscrowAddress) || h.identity.EscrowAddress == h.identity.VaultAddress {
		httpFailure(w, http.StatusServiceUnavailable, "escrow_bank_proof_adapter_unavailable")
		return
	}
	proof, err := backend.EscrowBankProof(ctx)
	if err != nil || ctx.Err() != nil || proof.Address != h.identity.EscrowAddress || proof.Version != 1 || proof.ChainID != "wolo-1" || proof.Denom != "uwolo" {
		httpFailure(w, http.StatusServiceUnavailable, "escrow_bank_proof_unavailable")
		return
	}
	wire, err := json.Marshal(proof)
	if err != nil || len(wire) > satchel.MaxPortableProofBytes {
		httpFailure(w, http.StatusServiceUnavailable, "escrow_bank_proof_unavailable")
		return
	}
	if _, err = satchel.DecodeBankProof(wire); err != nil {
		httpFailure(w, http.StatusServiceUnavailable, "escrow_bank_proof_unavailable")
		return
	}
	// Compact Go JSON is transport evidence only. Consumers must authenticate
	// it through the independently pinned CLI with protected --account-role escrow.
	_, _ = w.Write(wire)
}
