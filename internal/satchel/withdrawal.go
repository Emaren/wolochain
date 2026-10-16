package satchel

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"unicode/utf8"
)

// WithdrawalIntent binds the eventual durable hold and transaction to one
// owner-proven destination. Consent must be fresh and scoped to this payload;
// an ADR-36 login/control signature is not withdrawal consent.
type WithdrawalIntent struct {
	RequestID, OwnerID, OwnerWallet, Vault, AmountUWolo, Memo string
}

func (i WithdrawalIntent) Fingerprint() (string, error) {
	if strings.TrimSpace(i.RequestID) == "" || len(i.RequestID) > 128 || strings.TrimSpace(i.OwnerID) == "" || len(i.OwnerID) > 128 ||
		!utf8.ValidString(i.RequestID) || !utf8.ValidString(i.OwnerID) || !utf8.ValidString(i.Memo) ||
		!address(i.OwnerWallet) || !address(i.Vault) || IsKnownRoleAddress(i.Vault) ||
		i.OwnerWallet == i.Vault || !amount(i.AmountUWolo) || len(i.Memo) == 0 || len(i.Memo) > 256 {
		return "", errors.New("invalid_withdrawal_intent")
	}
	// An ordered JSON array prevents delimiter collisions and binds policy as
	// well as every economic field. Changing any field under an ID conflicts.
	encoded, _ := json.Marshal([]string{CurrentCapability().Version(), ChainID, Denom,
		CurrentCapability().SignerRole(), i.RequestID, i.OwnerID, i.OwnerWallet, i.Vault, i.AmountUWolo, i.Memo})
	sum := sha256.Sum256(encoded)
	return hex.EncodeToString(sum[:]), nil
}

// WithdrawalRecord is an offline description of required durable state, NOT a
// persistence implementation. Signed bytes/hash must be committed atomically
// with the hold BEFORE any eventual broadcast. Never reuse 8092/8093 state.
type WithdrawalRecord struct {
	RequestID, Fingerprint, HoldEvidenceDigest, ScopedConsentDigest string
	State                                                           string // held, signed, submitted, uncertain, confirmed
	SignedTx                                                        []byte
	TxHash                                                          string
	ConfirmationDigest                                              string
}

type Recovery struct{ Action, TxHash string }

// InspectWithdrawalRecovery never returns a send, re-sign, release-hold or
// cancellation action. Unknown outcomes require reconciliation of the SAME tx.
// It cannot establish hold durability, consent validity, or chain confirmation.
func InspectWithdrawalRecovery(i WithdrawalIntent, r *WithdrawalRecord) (Recovery, error) {
	fingerprint, err := i.Fingerprint()
	if err != nil {
		return Recovery{}, err
	}
	if r == nil {
		return Recovery{Action: "blocked_missing_durable_hold"}, nil
	}
	if r.RequestID != i.RequestID || r.Fingerprint != fingerprint {
		return Recovery{}, errors.New("withdrawal_idempotency_conflict")
	}
	if !digest(r.HoldEvidenceDigest) || !digest(r.ScopedConsentDigest) {
		return Recovery{}, errors.New("withdrawal_authority_evidence_missing")
	}
	if r.State == "held" && r.TxHash == "" && len(r.SignedTx) == 0 && r.ConfirmationDigest == "" {
		return Recovery{Action: "blocked_execution_unimplemented"}, nil
	}
	if len(r.SignedTx) == 0 || len(r.SignedTx) > 65536 || !digest(r.TxHash) {
		return Recovery{}, errors.New("withdrawal_transaction_identity_missing")
	}
	hash := sha256.Sum256(r.SignedTx)
	if !strings.EqualFold(hex.EncodeToString(hash[:]), r.TxHash) {
		return Recovery{}, errors.New("withdrawal_transaction_identity_mismatch")
	}
	if !exactSend(r.SignedTx, i.Vault, i.OwnerWallet, i.AmountUWolo, i.Memo) {
		return Recovery{}, errors.New("withdrawal_signed_payload_mismatch")
	}
	switch r.State {
	case "signed", "submitted", "uncertain":
		if r.ConfirmationDigest != "" {
			return Recovery{}, errors.New("withdrawal_state_conflict")
		}
		return Recovery{Action: "reconcile_only", TxHash: strings.ToUpper(r.TxHash)}, nil
	case "confirmed":
		if !digest(r.ConfirmationDigest) {
			return Recovery{}, errors.New("withdrawal_confirmation_missing")
		}
		return Recovery{Action: "replay_recorded_confirmation", TxHash: strings.ToUpper(r.TxHash)}, nil
	default:
		return Recovery{}, errors.New("withdrawal_state_unavailable")
	}
}
