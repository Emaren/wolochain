package satchelservice

import (
	"encoding/base64"
	"encoding/json"
	"errors"
	"regexp"
	"strings"
	"time"

	"github.com/cosmos/btcutil/bech32"
	sdksecp "github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
)

// OwnerWithdrawalMandate is the already-existing HD Keplr challenge protocol.
// It proves owner wallet consent, separately from the independent Ed25519 hold
// reviewer. Neither a login signature nor an auto-bet mandate is acceptable.
type OwnerWithdrawalMandate struct {
	Challenge OwnerWithdrawalChallenge `json:"challenge"`
	PubKey    OwnerWithdrawalPublicKey `json:"pub_key"`
	Signature string                   `json:"signature"`
}
type OwnerWithdrawalPublicKey struct {
	Type  string `json:"type"`
	Value string `json:"value"`
}
type OwnerWithdrawalChallenge struct {
	ID            string `json:"id"`
	OwnerUID      string `json:"owner_uid"`
	WalletAddress string `json:"wallet_address"`
	AmountUWolo   string `json:"amount_uwolo"`
	IssuedAtUTC   string `json:"issued_at_utc"`
	ExpiresAtUTC  string `json:"expires_at_utc"`
}

var ownerUIDPattern = regexp.MustCompile(`^[a-zA-Z0-9_.:-]{1,100}$`)

// WithdrawalChallengeText reproduces lib/warSatchelWithdrawalAuth.ts's exact
// withdrawalChallengeText, including the original timestamp text and newlines.
func WithdrawalChallengeText(c OwnerWithdrawalChallenge) (string, error) {
	issued, e1 := time.Parse(time.RFC3339Nano, c.IssuedAtUTC)
	expires, e2 := time.Parse(time.RFC3339Nano, c.ExpiresAtUTC)
	if !uuid.MatchString(c.ID) || !ownerUIDPattern.MatchString(c.OwnerUID) || !validAddress(c.WalletAddress) || !amount(c.AmountUWolo, 50000000000) || e1 != nil || e2 != nil || !expires.After(issued) || expires.Sub(issued) > 5*time.Minute {
		return "", errors.New("withdrawal_owner_challenge_refused")
	}
	return strings.Join([]string{
		"AoE2WAR War Satchel WITHDRAWAL AUTHORIZATION",
		"Origin: aoe2war.com", "Chain: wolo-1", "Denom: uwolo",
		"Owner UID: " + c.OwnerUID,
		"Linked Keplr receiving wallet: " + c.WalletAddress,
		"Exact withdrawal amount uwolo: " + c.AmountUWolo,
		"One-use withdrawal challenge ID: " + c.ID,
		"Issued: " + c.IssuedAtUTC,
		"Expires: " + c.ExpiresAtUTC,
		"I authorize ONLY this one withdrawal from my War Satchel into my linked Keplr wallet.",
		"This does NOT authorize automated bets or permit any service to read Keplr private keys.",
	}, "\n"), nil
}

// WithdrawalOwnerSignBytes is canonical ADR-36 Amino JSON. All object keys are
// lexicographically sorted as @cosmjs/amino serializeSignDoc requires. Strings
// remain normal JSON; no floats, amounts, timestamps or pubkeys are reencoded.
func WithdrawalOwnerSignBytes(c OwnerWithdrawalChallenge) ([]byte, error) {
	text, err := WithdrawalChallengeText(c)
	if err != nil {
		return nil, err
	}
	doc := map[string]any{"account_number": "0", "chain_id": "", "fee": map[string]any{"amount": []any{}, "gas": "0"}, "memo": "", "msgs": []any{map[string]any{"type": "sign/MsgSignData", "value": map[string]any{"data": base64.StdEncoding.EncodeToString([]byte(text)), "signer": c.WalletAddress}}}, "sequence": "0"}
	return json.Marshal(doc)
}

func OwnerMandateDigest(m OwnerWithdrawalMandate) string {
	return hashJSON([]any{"aoe2war/satchel/withdraw-owner-mandate/v1", m.Challenge.ID, m.Challenge.OwnerUID, m.Challenge.WalletAddress, m.Challenge.AmountUWolo, m.Challenge.IssuedAtUTC, m.Challenge.ExpiresAtUTC, m.PubKey.Type, m.PubKey.Value, m.Signature})
}

// WithdrawalHoldDigest binds the independently reviewed durable reservation to
// exact Keplr consent in the existing Ed25519 withdrawal approval message.
// A digest alone proves neither reservation existence nor unreserved funds.
func WithdrawalHoldDigest(reservationDigest string, m OwnerWithdrawalMandate) string {
	return hashJSON([]string{"aoe2war/satchel/withdraw-hold/v1", reservationDigest, OwnerMandateDigest(m)})
}

func verifyOwnerWithdrawal(r TransferRequest, now time.Time) error {
	m, a := r.OwnerMandate, r.Approval
	if m == nil || a == nil || !nonzeroDigest(a.ReservationDigest) || a.HoldDigest != WithdrawalHoldDigest(a.ReservationDigest, *m) || m.PubKey.Type != "tendermint/PubKeySecp256k1" {
		return errors.New("withdrawal_owner_mandate_required")
	}
	c := m.Challenge
	issued, e1 := time.Parse(time.RFC3339Nano, c.IssuedAtUTC)
	expires, e2 := time.Parse(time.RFC3339Nano, c.ExpiresAtUTC)
	if e1 != nil || e2 != nil || c.ID != a.ChallengeID || c.OwnerUID != r.OwnerID || c.WalletAddress != r.Recipient || c.AmountUWolo != r.AmountUWolo || now.Before(issued) || !now.Before(expires) ||
		a.IssuedAt < issued.Unix() || a.ExpiresAt > expires.Unix() {
		return errors.New("withdrawal_owner_context_refused")
	}
	key, e1 := base64.StdEncoding.Strict().DecodeString(m.PubKey.Value)
	sig, e2 := base64.StdEncoding.Strict().DecodeString(m.Signature)
	if e1 != nil || e2 != nil || len(key) != 33 || (key[0] != 2 && key[0] != 3) || len(sig) != 64 || base64.StdEncoding.EncodeToString(key) != m.PubKey.Value || base64.StdEncoding.EncodeToString(sig) != m.Signature {
		return errors.New("withdrawal_owner_signature_refused")
	}
	public := &sdksecp.PubKey{Key: key}
	address, err := bech32.EncodeFromBase256("wolo", public.Address())
	message, msgErr := WithdrawalOwnerSignBytes(c)
	if err != nil || msgErr != nil || address != r.Recipient || !public.VerifySignature(message, sig) {
		return errors.New("withdrawal_owner_signature_refused")
	}
	return nil
}
