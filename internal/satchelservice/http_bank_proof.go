package satchelservice

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"

	"github.com/emaren/wolochain/internal/satchel"
)

type HTTPBankProofBackend interface {
	BankProof(context.Context) (satchel.BankProof, error)
}

// BankProof reads chain assets only. No signer, journal, reserve, approval or
// credit operation is performed, and no caller can select an account/height.
func (e *Engine) BankProof(ctx context.Context, reader *satchel.TrustedReader) (satchel.BankProof, error) {
	if e == nil || reader == nil || ctx == nil || ctx.Err() != nil {
		return satchel.BankProof{}, errors.New("bank_proof_unavailable")
	}
	_, proof, err := reader.ReadCurrentBankProof(ctx, e.policy.Vault)
	return proof, err
}

func (h *privateHTTPHandler) bankProof(ctx context.Context, w http.ResponseWriter, data []byte) {
	var request struct {
		Protocol int `json:"protocol"`
	}
	if strictHTTPJSON(data, &request) != nil || request.Protocol != 1 {
		httpFailure(w, http.StatusBadRequest, "invalid_bank_proof_request")
		return
	}
	backend, ok := h.backend.(HTTPBankProofBackend)
	if !ok {
		httpFailure(w, http.StatusServiceUnavailable, "bank_proof_adapter_unavailable")
		return
	}
	proof, err := backend.BankProof(ctx)
	if err != nil || ctx.Err() != nil || proof.Address != h.identity.VaultAddress || proof.Version != 1 || proof.ChainID != "wolo-1" || proof.Denom != "uwolo" {
		httpFailure(w, http.StatusServiceUnavailable, "bank_proof_unavailable")
		return
	}
	encoded, err := json.Marshal(proof)
	if err != nil || len(encoded) > satchel.MaxPortableProofBytes {
		httpFailure(w, http.StatusServiceUnavailable, "bank_proof_unavailable")
		return
	}
	if _, err = satchel.DecodeBankProof(encoded); err != nil {
		httpFailure(w, http.StatusServiceUnavailable, "bank_proof_unavailable")
		return
	}
	// This untrusted transcript must still pass the app's independently pinned
	// offline verifier. HTTP success is not bank authentication or solvency.
	_, _ = w.Write(encoded)
}
