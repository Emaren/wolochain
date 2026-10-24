package satchelservice

// A service bearer token transports a request; it is not authority to spend
// another owner's custody balance. The independent ledger reviewer signs one
// exact, already-durable HD reservation and consent snapshot. This is neither a
// second customer ledger nor a claim that a digest proves reserve solvency.
import (
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"errors"
	"strings"
	"time"
)

type WagerReservation struct {
	Version           int    `json:"version"`
	OperationID       string `json:"operation_id"`
	OwnerID           string `json:"owner_id"`
	Vault             string `json:"vault"`
	Recipient         string `json:"recipient"`
	AmountUWolo       string `json:"amount_uwolo"`
	Memo              string `json:"memo"`
	ReservationDigest string `json:"reservation_digest"`
	LedgerRevision    string `json:"ledger_revision"`
	ConsentDigest     string `json:"consent_digest"`
	FeeUWolo          string `json:"fee_uwolo"`
	IssuedAt          int64  `json:"issued_at"`
	ExpiresAt         int64  `json:"expires_at"`
	Signature         string `json:"signature"`
}

// WagerReservationMessage is the versioned signing contract. An approver must
// independently establish the HD hold, owner consent, open market and fee
// headroom before signing it. No approval generator or private key ships here.
func WagerReservationMessage(a WagerReservation) []byte {
	b, _ := json.Marshal([]any{"aoe2war/satchel/wager-reservation/v1", a.Version,
		"wolo-1", "uwolo", a.OperationID, a.OwnerID, a.Vault, a.Recipient,
		a.AmountUWolo, a.Memo, a.ReservationDigest, a.LedgerRevision,
		a.ConsentDigest, a.FeeUWolo, a.IssuedAt, a.ExpiresAt})
	return b
}

func (p Policy) VerifyWager(r TransferRequest) error { return p.verifyWager(r, time.Now()) }

func (p Policy) verifyWager(r TransferRequest, now time.Time) error {
	a := r.Reservation
	if a == nil || a.Version != 1 || r.Kind != "wager" ||
		!ownerUIDPattern.MatchString(r.OwnerID) || a.OwnerID != r.OwnerID ||
		a.OperationID != r.OperationID || a.Vault != p.Vault || r.Sender != p.Vault ||
		a.Recipient != p.BettingEscrow || r.Recipient != p.BettingEscrow ||
		a.AmountUWolo != r.AmountUWolo || !amount(a.AmountUWolo, p.MaxAmountUWolo) ||
		a.Memo != r.Memo || !wagerIDs.MatchString(r.OperationID) || !ticketMemo.MatchString(r.Memo) ||
		r.ChainID != "wolo-1" || r.Denom != "uwolo" ||
		!nonzeroDigest(a.ReservationDigest) || a.ReservationDigest != strings.ToLower(a.ReservationDigest) ||
		!nonzeroDigest(a.LedgerRevision) || a.LedgerRevision != strings.ToLower(a.LedgerRevision) ||
		!nonzeroDigest(a.ConsentDigest) || a.ConsentDigest != strings.ToLower(a.ConsentDigest) ||
		!amount(a.FeeUWolo, 1000000) || a.IssuedAt > now.Unix() || a.ExpiresAt <= now.Unix() ||
		a.ExpiresAt <= a.IssuedAt || uint64(a.ExpiresAt)-uint64(a.IssuedAt) > 300 ||
		len(p.WagerApprovalKey) != ed25519.PublicKeySize {
		return errors.New("owner_bound_wager_reservation_required")
	}
	sig, err := base64.StdEncoding.Strict().DecodeString(a.Signature)
	if err != nil || len(sig) != ed25519.SignatureSize || base64.StdEncoding.EncodeToString(sig) != a.Signature ||
		!ed25519.Verify(p.WagerApprovalKey, WagerReservationMessage(*a), sig) {
		return errors.New("wager_reservation_signature_refused")
	}
	return nil
}
