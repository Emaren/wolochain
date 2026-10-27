// Package epochescrow implements the held HD #937 native v3 policy and durable
// decision boundary. No exported API opens a keyring, signs or broadcasts.
package epochescrow

import (
	"bytes"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/cosmos/btcutil/bech32"
	secp "github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
	"github.com/emaren/wolochain/internal/satchel"
)

const Protocol = "aoe2war/escrow-epoch/v3"
const ReturnCommand = "epoch.escrow.return.execute.v3"
const FeeCommand = "epoch.escrow.fee.execute.v3"
const ProductionEnabled = false

// Blocker is public, fixed diagnostic data. It never contains credentials,
// filesystem paths, RPC replies or caller-controlled error text.
type Blocker struct {
	Code              string `json:"code"`
	Cause             string `json:"cause"`
	SafeNextOperation string `json:"safe_next_operation"`
	Retryable         bool   `json:"retryable"`
}

func (b *Blocker) Error() string             { return b.Code }
func blocked(code, cause, next string) error { return &Blocker{code, cause, next, false} }
func UnavailableExecution() error {
	return blocked("NEW_ESCROW_SIGNER_ABSENT", "Independent runtime custody and off-host escrow nonce authority are not provisioned by this source candidate.", "inspect-and-provision-independent-authority")
}

var epochPattern = regexp.MustCompile(`^[a-z][a-z0-9_-]{11,63}$`)
var uidPattern = regexp.MustCompile(`^[a-zA-Z0-9_.:-]{1,100}$`)
var idPattern = regexp.MustCompile(`^[a-zA-Z0-9:_-]{1,192}$`)
var shaPattern = regexp.MustCompile(`^[a-f0-9]{64}$`)
var hashPattern = regexp.MustCompile(`^[A-F0-9]{64}$`)
var sourcePattern = regexp.MustCompile(`^[a-f0-9]{40}$`)

func digest(s string) bool { return shaPattern.MatchString(s) && strings.Trim(s, "0") != "" }
func txhash(s string) bool { return hashPattern.MatchString(s) && strings.Trim(s, "0") != "" }
func address(s string) bool {
	h, b, e := bech32.DecodeToBase256(s)
	return e == nil && h == "wolo" && len(b) == 20 && s == strings.ToLower(s)
}
func hash(v any) string {
	b, _ := json.Marshal(v)
	s := sha256.Sum256(b)
	return hex.EncodeToString(s[:])
}
func number(s string, zero bool) (uint64, error) {
	n, e := strconv.ParseUint(s, 10, 64)
	if e != nil || strconv.FormatUint(n, 10) != s || (!zero && n == 0) || n > 100000000000000 {
		return 0, errors.New("noncanonical_amount")
	}
	return n, nil
}
func pubAddress(encoded string) (string, error) {
	k, e := hex.DecodeString(encoded)
	if e != nil || len(k) != 33 || (k[0] != 2 && k[0] != 3) {
		return "", errors.New("public_key_invalid")
	}
	return bech32.EncodeFromBase256("wolo", (&secp.PubKey{Key: k}).Address())
}

// Policy is a protected source/configuration claim, never proof of real custody
// separation. The held executable cannot activate from these fields alone.
type Policy struct {
	Version                    int                 `json:"version"`
	EpochID                    string              `json:"epoch_id"`
	HStar                      int64               `json:"h_star"`
	Vault                      string              `json:"vault"`
	Escrow                     string              `json:"escrow"`
	VaultPublicKeyHex          string              `json:"vault_public_key_hex"`
	EscrowPublicKeyHex         string              `json:"escrow_public_key_hex"`
	VaultKeyringLineageSHA256  string              `json:"vault_keyring_lineage_sha256"`
	EscrowKeyringLineageSHA256 string              `json:"escrow_keyring_lineage_sha256"`
	VaultUID                   uint32              `json:"vault_uid"`
	EscrowUID                  uint32              `json:"escrow_uid"`
	LegacyUIDs                 []uint32            `json:"legacy_uids"`
	LegacyPublicKeySHA256      []string            `json:"legacy_public_key_sha256"`
	LegacyKeyringLineageSHA256 []string            `json:"legacy_keyring_lineage_sha256"`
	ReviewerPublicKeyHex       string              `json:"reviewer_public_key_hex"`
	FeeRecipient               string              `json:"fee_recipient"`
	GasFeeUWolo                string              `json:"gas_fee_uwolo"`
	SourceCommit               string              `json:"source_commit"`
	BinarySHA256               string              `json:"binary_sha256"`
	ConfigSHA256               string              `json:"config_sha256"`
	TrustAnchor                satchel.TrustAnchor `json:"trust_anchor"`
}

func (p Policy) Validate() error {
	refuse := func() error {
		return blocked("EPOCH_POLICY_INVALID", "Missing or conflicting protected v3 policy identity.", "review-policy")
	}
	va, ve := pubAddress(p.VaultPublicKeyHex)
	ea, ee := pubAddress(p.EscrowPublicKeyHex)
	reviewer, re := hex.DecodeString(p.ReviewerPublicKeyHex)
	if p.Version != 3 || !epochPattern.MatchString(p.EpochID) || p.HStar <= 0 || ve != nil || ee != nil || va != p.Vault || ea != p.Escrow || p.Vault == p.Escrow || satchel.IsKnownRoleAddress(p.Vault) || satchel.IsKnownRoleAddress(p.Escrow) || !address(p.FeeRecipient) || p.FeeRecipient == p.Vault || p.FeeRecipient == p.Escrow || re != nil || len(reviewer) != ed25519.PublicKeySize || (!sourcePattern.MatchString(p.SourceCommit) || strings.Trim(p.SourceCommit, "0") == "") || !digest(p.BinarySHA256) || !digest(p.ConfigSHA256) {
		return refuse()
	}
	if _, e := number(p.GasFeeUWolo, false); e != nil {
		return refuse()
	}
	if !digest(p.VaultKeyringLineageSHA256) || !digest(p.EscrowKeyringLineageSHA256) || p.VaultKeyringLineageSHA256 == p.EscrowKeyringLineageSHA256 || p.VaultUID == 0 || p.EscrowUID == 0 || p.VaultUID == p.EscrowUID || len(p.LegacyUIDs) == 0 || len(p.LegacyPublicKeySHA256) == 0 || len(p.LegacyKeyringLineageSHA256) == 0 {
		return blocked("KEYRING_AUTHORITY_COLLISION", "Independent account, runtime principal and keyring inventories are required.", "witness-runtime-authorities")
	}
	vaultKey, _ := hex.DecodeString(p.VaultPublicKeyHex)
	escrowKey, _ := hex.DecodeString(p.EscrowPublicKeyHex)
	vd, ed := sha256.Sum256(vaultKey), sha256.Sum256(escrowKey)
	for _, u := range p.LegacyUIDs {
		if u == p.VaultUID || u == p.EscrowUID {
			return refuse()
		}
	}
	for _, s := range p.LegacyPublicKeySHA256 {
		if !digest(s) || s == hex.EncodeToString(vd[:]) || s == hex.EncodeToString(ed[:]) {
			return refuse()
		}
	}
	for _, s := range p.LegacyKeyringLineageSHA256 {
		if !digest(s) || s == p.VaultKeyringLineageSHA256 || s == p.EscrowKeyringLineageSHA256 {
			return refuse()
		}
	}
	if _, e := satchel.NewProofVerifier(p.TrustAnchor); e != nil {
		return refuse()
	}
	return nil
}
func PolicyDigest(p Policy) string { return hash(p) }

type Wager struct {
	WagerID             uint64 `json:"wager_id"`
	MarketID            uint64 `json:"market_id"`
	TicketID            uint64 `json:"ticket_id"`
	LegID               uint64 `json:"leg_id"`
	OwnerUID            string `json:"owner_uid"`
	Side                string `json:"side"`
	PrincipalUWolo      string `json:"principal_uwolo"`
	FundingTxHash       string `json:"funding_tx_hash"`
	FundingMessageIndex uint32 `json:"funding_message_index"`
}
type Plan struct {
	EpochID    string  `json:"epoch_id"`
	MarketID   uint64  `json:"market_id"`
	Resolution string  `json:"resolution"`
	Wagers     []Wager `json:"wagers"`
}
type Reserve struct {
	Account                    string `json:"account"`
	LiabilitiesUWolo           string `json:"liabilities_uwolo"`
	MaximumUnknownOutflowUWolo string `json:"maximum_unknown_outflow_uwolo"`
	GasReserveUWolo            string `json:"gas_reserve_uwolo"`
	OperatingFloorUWolo        string `json:"operating_floor_uwolo"`
	InventorySHA256            string `json:"inventory_sha256"`
	NonOverlapSHA256           string `json:"nonoverlap_sha256"`
}
type Request struct {
	BankStateHeight          int64   `json:"bank_state_height"`
	BankCommitHeight         int64   `json:"bank_commit_height"`
	BankCommitHash           string  `json:"bank_commit_hash"`
	BankAppHash              string  `json:"bank_app_hash"`
	Protocol                 string  `json:"protocol"`
	Command                  string  `json:"command"`
	ChainID                  string  `json:"chain_id"`
	Denom                    string  `json:"denom"`
	EpochID                  string  `json:"epoch_id"`
	OperationID              string  `json:"operation_id"`
	OriginalOperationID      string  `json:"original_operation_id"`
	EntitlementID            string  `json:"entitlement_id"`
	OwnerUID                 string  `json:"owner_uid"`
	OwnerWallet              string  `json:"owner_wallet"`
	OwnerPublicKeyHex        string  `json:"owner_public_key_hex"`
	OriginalMandateSHA256    string  `json:"original_mandate_sha256"`
	WagerID                  uint64  `json:"wager_id"`
	TicketID                 uint64  `json:"ticket_id"`
	MarketID                 uint64  `json:"market_id"`
	LegID                    uint64  `json:"leg_id"`
	FundingTxHash            string  `json:"funding_tx_hash"`
	FundingMessageIndex      uint32  `json:"funding_message_index"`
	Sender                   string  `json:"sender"`
	Recipient                string  `json:"recipient"`
	AmountUWolo              string  `json:"amount_uwolo"`
	Memo                     string  `json:"memo"`
	PolicySHA256             string  `json:"policy_sha256"`
	SourceCommit             string  `json:"source_commit"`
	BinarySHA256             string  `json:"binary_sha256"`
	ConfigSHA256             string  `json:"config_sha256"`
	Plan                     Plan    `json:"plan"`
	ResolutionEvidenceSHA256 string  `json:"resolution_evidence_sha256"`
	VaultReserve             Reserve `json:"vault_reserve"`
	EscrowReserve            Reserve `json:"escrow_reserve"`
	Nonce                    string  `json:"nonce"`
	ReviewerPermitID         string  `json:"reviewer_permit_id"`
	IssuedAt                 int64   `json:"issued_at"`
	ExpiresAt                int64   `json:"expires_at"`
	OwnerSignature           string  `json:"owner_signature"`
	ReviewerSignature        string  `json:"reviewer_signature"`
}

// RequestMessage signs ordered canonical Go JSON of the complete immutable
// request. A service token, old owner challenge or legacy approval cannot sign
// this domain. No signing helper or embedded approval key is supplied.
func RequestMessage(r Request) []byte {
	r.OwnerSignature = ""
	r.ReviewerSignature = ""
	b, _ := json.Marshal([]any{Protocol, r})
	return b
}
func Fingerprint(r Request) string { return hash([]any{Protocol, string(RequestMessage(r))}) }
func EntitlementID(epoch string, market, ticket, leg uint64) string {
	return fmt.Sprintf("satchel:e3:%s:entitlement:%d:%d:%d", epoch, market, ticket, leg)
}
func OriginalOperationID(epoch string, ticket uint64) string {
	return fmt.Sprintf("satchel:e3:%s:%d", epoch, ticket)
}
func FundingMemo(epoch string, ticket uint64) string {
	return fmt.Sprintf("aoe2war/satchel/epoch-v3/%s/ticket/%d", epoch, ticket)
}
func ReturnMemo(epoch, entitlement string) string {
	return "aoe2war/satchel/epoch-v3/" + epoch + "/return/" + entitlement
}
func (p Policy) ValidateRequest(r Request, now time.Time) error {
	refuse := func() error {
		return blocked("EPOCH_REPLAY_REJECTED", "The request does not match its exact new-epoch economic and authorization identity.", "lookup-original-operation")
	}
	if e := p.Validate(); e != nil {
		return e
	}
	if r.BankStateHeight <= p.HStar || r.BankCommitHeight <= 0 || r.BankCommitHeight != r.BankStateHeight+1 || !txhash(r.BankCommitHash) || !txhash(r.BankAppHash) || r.Protocol != Protocol || r.ChainID != "wolo-1" || r.Denom != "uwolo" || r.EpochID != p.EpochID || r.Plan.EpochID != p.EpochID || r.Plan.MarketID != r.MarketID || !uidPattern.MatchString(r.OwnerUID) || !address(r.OwnerWallet) || r.OwnerWallet == p.Vault || r.OwnerWallet == p.Escrow || r.OwnerWallet == p.FeeRecipient || !digest(r.OriginalMandateSHA256) || !digest(r.ResolutionEvidenceSHA256) || !digest(r.Nonce) || !idPattern.MatchString(r.ReviewerPermitID) || r.IssuedAt <= 0 || r.ExpiresAt <= r.IssuedAt || r.ExpiresAt-r.IssuedAt > 120 || now.Unix() < r.IssuedAt || now.Unix() >= r.ExpiresAt || r.PolicySHA256 != PolicyDigest(p) || r.SourceCommit != p.SourceCommit || r.BinarySHA256 != p.BinarySHA256 || r.ConfigSHA256 != p.ConfigSHA256 || r.Sender != p.Escrow || !idPattern.MatchString(r.OperationID) || len(r.Memo) == 0 || len(r.Memo) > 256 || r.FundingMessageIndex != 0 || !txhash(r.FundingTxHash) || r.EntitlementID != EntitlementID(p.EpochID, r.MarketID, r.TicketID, r.LegID) || r.OriginalOperationID != OriginalOperationID(p.EpochID, r.TicketID) {
		return refuse()
	}
	outcomes, e := PlanSettlement(r.Plan)
	if e != nil {
		return e
	}
	var selected *Outcome
	for i := range outcomes {
		if outcomes[i].Wager.WagerID == r.WagerID {
			selected = &outcomes[i]
		}
	}
	if selected == nil {
		return refuse()
	}
	w := selected.Wager
	if w.OwnerUID != r.OwnerUID || w.TicketID != r.TicketID || w.LegID != r.LegID || w.MarketID != r.MarketID || w.FundingTxHash != r.FundingTxHash || w.FundingMessageIndex != r.FundingMessageIndex {
		return refuse()
	}
	switch r.Command {
	case ReturnCommand:
		if r.OperationID != r.EntitlementID+":return" || r.Recipient != p.Vault || r.Memo != ReturnMemo(p.EpochID, r.EntitlementID) || r.AmountUWolo != selected.PayoutUWolo {
			return refuse()
		}
	case FeeCommand:
		if r.OperationID != r.EntitlementID+":fee" || r.Recipient != p.FeeRecipient || r.Memo != "aoe2war/satchel/epoch-v3/"+p.EpochID+"/fee/"+r.EntitlementID || r.AmountUWolo != selected.FeeUWolo {
			return refuse()
		}
	default:
		return refuse()
	}
	if _, e := number(r.AmountUWolo, false); e != nil {
		return blocked("ZERO_ECONOMIC_TRANSFER", "This entitlement has no positive native transfer.", "retain-economic-plan-without-transfer")
	}
	pub, e := pubAddress(r.OwnerPublicKeyHex)
	key, _ := hex.DecodeString(r.OwnerPublicKeyHex)
	sig, se := base64.StdEncoding.Strict().DecodeString(r.OwnerSignature)
	if e != nil || pub != r.OwnerWallet || se != nil || len(sig) != 64 || base64.StdEncoding.EncodeToString(sig) != r.OwnerSignature || !(&secp.PubKey{Key: key}).VerifySignature(RequestMessage(r), sig) {
		return refuse()
	}
	reviewer, _ := hex.DecodeString(p.ReviewerPublicKeyHex)
	reviewSig, e := base64.StdEncoding.Strict().DecodeString(r.ReviewerSignature)
	if e != nil || len(reviewSig) != ed25519.SignatureSize || base64.StdEncoding.EncodeToString(reviewSig) != r.ReviewerSignature || bytes.Equal(key, reviewer) || !ed25519.Verify(reviewer, RequestMessage(r), reviewSig) {
		return refuse()
	}
	return nil
}
