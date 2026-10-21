package satchelservice

// Keplr ADR-36 is the original owner's spending consent, NOT a chain transfer
// signature. This independent verifier must be fed original, read-only SQL
// records; neither a signedAt flag nor a mutable app API may substitute for
// the exact compressed secp256k1 wallet signature.
import (
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"strings"
	"time"

	"github.com/cosmos/btcutil/bech32"
	sdksecp "github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
)

// Source-bound authorization domain; this HELD epoch cannot authorize the
// financial PostgreSQL reviewer. Release requires reviewed source rotation in
// both repositories and newly signed original owner mandates.
const ReviewerAutoSpendAuthorizationProtocol = "aoe2war/satchel/mecha-auto-spend/v2"
const ReviewerAutoSpendAuthorizationEpoch = "aoe2war/satchel/mecha/v2/held-integration-1"

func reviewerMandateEpochReleased() bool {
	return regexp.MustCompile(`^aoe2war/satchel/mecha/v2/release/[A-Za-z0-9._-]{8,100}$`).MatchString(ReviewerAutoSpendAuthorizationEpoch)
}

var ErrReviewerOwnerMandate = errors.New("reviewer_owner_mandate_refused")
var reviewerConsentNonce = regexp.MustCompile(`^[a-f0-9]{32}$`)
var reviewerOwnerUID = regexp.MustCompile(`^[A-Za-z0-9_.:-]{1,100}$`)

// These are ORIGINAL consent + original signed mandate fields, not a
// request-supplied convenience object. Dates are stored as exact SQL instants.
// Signature JSON must be read from war_satchel_auto_spend_mandates.
type ReviewerStoredOwnerMandate struct {
	OwnerUID, WalletAddress                                string
	PresetID, PresetVersion                                int64
	WinnerStakeWolo, DesyncStakeWolo                       int64
	DesyncSide                                             string
	PerGameCapWolo, DailyCapWolo                           int64
	UntilOut                                               bool
	GamesRemaining                                         *int64
	Nonce                                                  string
	IssuedAt, ChallengeExpiresAt, SpendExpiresAt, SignedAt time.Time
	RevokedAt                                              *time.Time
	ChallengeText                                          string
	PublicKeyType, PublicKeyBase64, SignatureBase64        string
}

// The other side of the comparison comes from the immutable original watcher
// reservation and the *current* preset/owner rows, re-read by an independent
// SQL principal. Neither one alone authorizes spending.
type ReviewerOwnerExpectation struct {
	OwnerUID, WalletAddress          string
	PresetID, PresetVersion          int64
	WinnerStakeWolo, DesyncStakeWolo int64
	DesyncSide                       string
	UntilOut                         bool
	GamesRemaining                   *int64
	OriginalOperationID              string
}

func reviewerISO(t time.Time) (string, error) {
	if t.IsZero() || !t.Equal(t.Truncate(time.Millisecond)) ||
		t.Location() != time.UTC {
		return "", ErrReviewerOwnerMandate
	}
	s := t.Format("2006-01-02T15:04:05.000Z")
	parsed, e := time.Parse("2006-01-02T15:04:05.000Z", s)
	if e != nil || !parsed.Equal(t) {
		return "", ErrReviewerOwnerMandate
	}
	return s, nil
}
func reviewerGamesText(m ReviewerStoredOwnerMandate) string {
	if m.UntilOut {
		return "until available funds run out"
	}
	if m.GamesRemaining == nil {
		return ""
	}
	return fmt.Sprintf("%d future games", *m.GamesRemaining)
}
func reviewerOwnerChallengeText(m ReviewerStoredOwnerMandate, issue, challenge, spend string) string {
	// Exact line order and capitalization from HD
	// lib/warSatchelAutoSpendConsent.ts satchelAutoSpendChallengeText().
	lines := []string{
		"AoE2WAR War Satchel Mecha AUTO BET SPENDING AUTHORIZATION",
		"Authorization protocol: " + ReviewerAutoSpendAuthorizationProtocol,
		"Authorization epoch: " + ReviewerAutoSpendAuthorizationEpoch,
		"Origin: aoe2war.com",
		"Chain: wolo-1",
		"Denom: uwolo",
		"Owner UID: " + m.OwnerUID,
		"Linked Keplr wallet: " + m.WalletAddress,
		"Mecha preset ID: " + fmt.Sprint(m.PresetID),
		"Exact preset version: " + fmt.Sprint(m.PresetVersion),
		"Winner selection: own exact verified Steam roster side",
		"Game allowance: " + reviewerGamesText(m),
		"Winner bet WOLO: " + fmt.Sprint(m.WinnerStakeWolo),
		"Desync selection: " + m.DesyncSide,
		"Desync bet WOLO: " + fmt.Sprint(m.DesyncStakeWolo),
		"MAX per game WOLO: " + fmt.Sprint(m.PerGameCapWolo),
		"MAX daily WOLO: " + fmt.Sprint(m.DailyCapWolo),
		"Authorization expires: " + spend,
		"One-use challenge nonce: " + m.Nonce,
		"Issued: " + issue,
		"Challenge expires: " + challenge,
		"You authorize automated bets ONLY within these limits from your verified War Satchel.",
		"Only new Watcher games first opened after this authorization may spend funds.",
		"You do NOT authorize withdrawal, wallet-key access, or spending from your Keplr wallet.",
		"Pausing the plan or revoking this mandate must stop new betting immediately.",
	}
	return strings.Join(lines, "\n")
}

// ReviewerADR36SignBytes is exported for cross-language golden vector tests,
// not as a way to authorize anything. Stable ordered Amino JSON must match
// CosmJS makeSignDoc + serializeSignDoc with empty chain/memo and no fee.
func ReviewerADR36SignBytes(wallet, challenge string) ([]byte, error) {
	if !validAddress(wallet) || challenge == "" {
		return nil, ErrReviewerOwnerMandate
	}
	envelope := map[string]any{
		"account_number": "0", "chain_id": "",
		"fee":  map[string]any{"amount": []any{}, "gas": "0"},
		"memo": "",
		"msgs": []any{map[string]any{"type": "sign/MsgSignData",
			"value": map[string]any{"signer": wallet, "data": base64.StdEncoding.EncodeToString([]byte(challenge))}}},
		"sequence": "0",
	}
	raw, e := json.Marshal(envelope)
	if e != nil {
		return nil, ErrReviewerOwnerMandate
	}
	return raw, nil
}

func reviewerCompareGames(original, current *int64, untilOut bool) bool {
	if untilOut {
		return original == nil && current == nil
	}
	return original != nil && current != nil && *original > 0 && *current > 0 && *current <= *original
}

// VerifyReviewerOwnerMandate binds live owner/preset state to the exact
// original wallet and cryptographically verifies ORIGINAL ADR-36 bytes.
// It neither authenticates the source database nor authorizes a transfer.
// A signed row can still be revoked; always rerun this immediately before
// reviewer issuance.
func VerifyReviewerOwnerMandate(m ReviewerStoredOwnerMandate, x ReviewerOwnerExpectation, now time.Time) error {
	if !reviewerOwnerUID.MatchString(m.OwnerUID) || m.OwnerUID != x.OwnerUID ||
		!validAddress(m.WalletAddress) || m.WalletAddress != x.WalletAddress ||
		!wagerIDs.MatchString(x.OriginalOperationID) ||
		m.PresetID < 1 || m.PresetVersion < 1 ||
		m.PresetID != x.PresetID || m.PresetVersion != x.PresetVersion ||
		m.WinnerStakeWolo < 1 || m.DesyncStakeWolo < 0 ||
		m.WinnerStakeWolo != x.WinnerStakeWolo || m.DesyncStakeWolo != x.DesyncStakeWolo ||
		m.DesyncSide != x.DesyncSide || m.UntilOut != x.UntilOut ||
		!reviewerCompareGames(m.GamesRemaining, x.GamesRemaining, m.UntilOut) ||
		!reviewerConsentNonce.MatchString(m.Nonce) || m.RevokedAt != nil ||
		(m.DesyncSide != "none" && m.DesyncSide != "yes" && m.DesyncSide != "no") ||
		(m.DesyncSide == "none" && m.DesyncStakeWolo != 0) ||
		(m.DesyncSide != "none" && m.DesyncStakeWolo == 0) ||
		m.WinnerStakeWolo > 1000 || m.DesyncStakeWolo > 1000 ||
		m.PerGameCapWolo < m.WinnerStakeWolo+m.DesyncStakeWolo ||
		m.PerGameCapWolo > 1000 ||
		m.DailyCapWolo < m.PerGameCapWolo || m.DailyCapWolo > 10000 ||
		(!m.UntilOut && *m.GamesRemaining > (10000/(m.WinnerStakeWolo+m.DesyncStakeWolo))) {
		return ErrReviewerOwnerMandate
	}
	issue, e1 := reviewerISO(m.IssuedAt)
	challenge, e2 := reviewerISO(m.ChallengeExpiresAt)
	spend, e3 := reviewerISO(m.SpendExpiresAt)
	signed, e4 := reviewerISO(m.SignedAt)
	if e1 != nil || e2 != nil || e3 != nil || e4 != nil || now.IsZero() ||
		m.ChallengeExpiresAt.Sub(m.IssuedAt) <= 0 ||
		m.ChallengeExpiresAt.Sub(m.IssuedAt) > 5*time.Minute ||
		m.SpendExpiresAt.Sub(m.ChallengeExpiresAt) <= 0 ||
		m.SpendExpiresAt.Sub(m.IssuedAt) > 24*time.Hour ||
		m.SignedAt.Before(m.IssuedAt) || m.SignedAt.After(now) || !m.SignedAt.Before(m.ChallengeExpiresAt) ||
		!m.SpendExpiresAt.After(now) || signed == "" {
		return ErrReviewerOwnerMandate
	}
	text := reviewerOwnerChallengeText(m, issue, challenge, spend)
	if m.ChallengeText != text ||
		m.PublicKeyType != "tendermint/PubKeySecp256k1" {
		return ErrReviewerOwnerMandate
	}
	decode := func(v string, n int) ([]byte, error) {
		raw, e := base64.StdEncoding.Strict().DecodeString(v)
		if e != nil || len(raw) != n || base64.StdEncoding.EncodeToString(raw) != v {
			return nil, ErrReviewerOwnerMandate
		}
		return raw, nil
	}
	key, e := decode(m.PublicKeyBase64, 33)
	if e != nil || (key[0] != 2 && key[0] != 3) {
		return ErrReviewerOwnerMandate
	}
	sig, e := decode(m.SignatureBase64, 64)
	if e != nil {
		return ErrReviewerOwnerMandate
	}
	pub := &sdksecp.PubKey{Key: key}
	derived, e := bech32.EncodeFromBase256("wolo", pub.Address())
	if e != nil || derived != m.WalletAddress {
		return ErrReviewerOwnerMandate
	}
	bytes, e := ReviewerADR36SignBytes(m.WalletAddress, text)
	if e != nil || !pub.VerifySignature(bytes, sig) {
		return ErrReviewerOwnerMandate
	}
	return nil
}
