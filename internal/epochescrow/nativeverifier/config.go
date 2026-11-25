package nativeverifier

import (
	"bytes"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"regexp"
	"strconv"
	"strings"
	"unicode/utf8"

	"github.com/cosmos/btcutil/bech32"
	secp "github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
	"github.com/emaren/wolochain/internal/chainjson"
	"github.com/emaren/wolochain/internal/epochescrow"
	"github.com/emaren/wolochain/internal/satchel"
	"github.com/emaren/wolochain/internal/satchelservice"
)

const domain = "aoe2war/epoch-v3-native-verifier/v1"
const chainCap uint64 = 100000000000000

var hexDigest = regexp.MustCompile(`^[a-f0-9]{64}$`)
var sourceDigest = regexp.MustCompile(`^[a-f0-9]{40}$`)
var identifier = regexp.MustCompile(`^[a-zA-Z0-9_.:-]{1,192}$`)

type refusal string

func (e refusal) Error() string { return string(e) }

// ErrorCode deliberately erases nested cryptographic, transport and input data.
func ErrorCode(err error) string {
	var r refusal
	if errors.As(err, &r) {
		return string(r)
	}
	return "NATIVE_VERIFIER_REFUSED"
}
func reject(code string) error  { return refusal(code) }
func validDigest(s string) bool { return hexDigest.MatchString(s) && strings.Trim(s, "0") != "" }
func canonicalAmount(s string, positive bool) (uint64, error) {
	n, e := strconv.ParseUint(s, 10, 64)
	if e != nil || strconv.FormatUint(n, 10) != s || n > chainCap || (positive && n == 0) {
		return 0, reject("NATIVE_VERIFIER_AMOUNT_INVALID")
	}
	return n, nil
}
func hashBytes(b []byte) string { h := sha256.Sum256(b); return hex.EncodeToString(h[:]) }
func digestValue(label string, v any) string {
	b, _ := json.Marshal([]any{domain, label, v})
	return hashBytes(b)
}
func keyHex(s string, size int) ([]byte, bool) {
	b, e := hex.DecodeString(s)
	return b, e == nil && len(b) == size && s == strings.ToLower(s) && strings.Trim(s, "0") != ""
}
func ownerAddress(s string) (string, bool) {
	b, ok := keyHex(s, 33)
	if !ok || (b[0] != 2 && b[0] != 3) {
		return "", false
	}
	a, e := bech32.EncodeFromBase256("wolo", (&secp.PubKey{Key: b}).Address())
	return a, e == nil
}
func strictJSON(raw []byte, max int, out any) error {
	if len(raw) == 0 || len(raw) > max || !utf8.Valid(raw) || !chainjson.ValidFolded(raw) {
		return reject("NATIVE_VERIFIER_INPUT_INVALID")
	}
	d := json.NewDecoder(bytes.NewReader(raw))
	d.DisallowUnknownFields()
	if d.Decode(out) != nil {
		return reject("NATIVE_VERIFIER_INPUT_INVALID")
	}
	if d.Decode(new(any)) != io.EOF {
		return reject("NATIVE_VERIFIER_INPUT_INVALID")
	}
	return nil
}
func DecodePins(raw []byte) (Pins, error) {
	var p Pins
	if e := strictJSON(raw, MaxPinsBytes, &p); e != nil {
		return Pins{}, reject("PRODUCTION_TRUST_ENROLLMENT_REQUIRED")
	}
	if e := ValidatePins(p); e != nil {
		return Pins{}, e
	}
	return p, nil
}

// ConfigDigest uses typed Go JSON. Both self-referential config fields are empty.
func ConfigDigest(p Pins) string {
	p.ConfigSHA256 = ""
	p.Policy.ConfigSHA256 = ""
	return digestValue("protected-config", p)
}
func ValidatePins(p Pins) error {
	bad := func() error { return reject("PRODUCTION_TRUST_ENROLLMENT_REQUIRED") }
	if p.Version != 1 || (p.Mode != ModeDisposableTest && p.Mode != ModeProduction) || (p.Mode == ModeProduction && (!p.ProductionTrustEnrolled || !validDigest(p.EnrollmentSHA256))) || (p.Mode == ModeDisposableTest && p.ProductionTrustEnrolled) {
		return bad()
	}
	i := p.ExpectedIdentity
	if !sourceDigest.MatchString(i.SourceCommit) || strings.Trim(i.SourceCommit, "0") == "" || !strings.HasPrefix(i.Compiler, "go1.") || len(i.Compiler) > 64 || i.Modified || !validDigest(i.BinarySHA256) || p.Policy.SourceCommit != i.SourceCommit || p.Policy.BinarySHA256 != i.BinarySHA256 || !validDigest(p.ConfigSHA256) || p.ConfigSHA256 != ConfigDigest(p) || p.Policy.ConfigSHA256 != p.ConfigSHA256 || p.Policy.Validate() != nil {
		return bad()
	}
	keys := []string{p.FinancialKeys.AccountingReviewerKeyHex, p.FinancialKeys.CustodyReviewerKeyHex, p.FinancialKeys.ExecutionAuthorityKeyHex, p.FinancialKeys.WagerApprovalKeyHex, p.FinancialKeys.WithdrawalApprovalKeyHex}
	seen := map[string]bool{}
	for _, k := range keys {
		if _, ok := keyHex(k, ed25519.PublicKeySize); !ok || seen[k] {
			return bad()
		}
		seen[k] = true
	}
	if p.Policy.ReviewerPublicKeyHex != p.FinancialKeys.WagerApprovalKeyHex || len(p.Observers) != 2 {
		return bad()
	}
	roles, ops, endpoints, ids := map[string]bool{}, map[string]bool{}, map[string]bool{}, map[string]bool{}
	for _, o := range p.Observers {
		if (o.Role != "primary" && o.Role != "witness") || roles[o.Role] || !identifier.MatchString(o.KeyID) || !identifier.MatchString(o.OperatorID) || ids[o.KeyID] || ops[o.OperatorID] || !validDigest(o.EndpointSHA256) || endpoints[o.EndpointSHA256] {
			return bad()
		}
		if _, ok := keyHex(o.PublicKeyHex, ed25519.PublicKeySize); !ok || seen[o.PublicKeyHex] {
			return bad()
		}
		seen[o.PublicKeyHex] = true
		roles[o.Role] = true
		ops[o.OperatorID] = true
		endpoints[o.EndpointSHA256] = true
		ids[o.KeyID] = true
	}
	if len(p.Owners) == 0 || len(p.Owners) > 4096 || len(p.RequiredLiabilitySources) == 0 || len(p.RequiredLiabilitySources) > 128 {
		return bad()
	}
	uids, wallets, pubs := map[string]bool{}, map[string]bool{}, map[string]bool{}
	for _, o := range p.Owners {
		a, ok := ownerAddress(o.PublicKeyHex)
		if !ok || a != o.Wallet || !identifier.MatchString(o.UID) || uids[o.UID] || wallets[o.Wallet] || pubs[o.PublicKeyHex] || o.Wallet == p.Policy.Vault || o.Wallet == p.Policy.Escrow || o.Wallet == p.Policy.FeeRecipient || satchel.IsKnownRoleAddress(o.Wallet) {
			return bad()
		}
		uids[o.UID] = true
		wallets[o.Wallet] = true
		pubs[o.PublicKeyHex] = true
	}
	prev := ""
	for _, s := range p.RequiredLiabilitySources {
		if !identifier.MatchString(s) || s <= prev {
			return bad()
		}
		prev = s
	}
	return nil
}
func enrolled(p Pins, uid, wallet, pub string) bool {
	for _, o := range p.Owners {
		if o.UID == uid && o.Wallet == wallet && o.PublicKeyHex == pub {
			return true
		}
	}
	return false
}
func PayloadDigest(b Bundle) string { b.Captures = nil; return digestValue("capture-payload", b) }
func CaptureMessage(c Capture) []byte {
	c.Signature = ""
	b, _ := json.Marshal([]any{domain, "observer-capture", c})
	return b
}
func InventoryDigest(i Inventory) string             { return digestValue("liability-inventory", i) }
func NonOverlapDigest(i Inventory) string            { return digestValue("liability-nonoverlap", i) }
func JournalSnapshotDigest(i Inventory) string       { return digestValue("source-snapshots", i.Sources) }
func TrustAnchorDigest(a satchel.TrustAnchor) string { return digestValue("comet-trust-anchor", a) }
func ProofDigest(p satchel.PortableProof) string     { return digestValue("selected-msgsend-proof", p) }
func BankProofDigest(p satchel.BankProof) string     { return digestValue("bank-state-proof", p) }
func VerificationRecordDigest(v Verdict) string {
	v.VerificationRecordSHA256 = ""
	return digestValue("verified-record", v)
}

// PermitDigest binds the reviewed liabilities to the complete authorization.
func PermitDigest(b Bundle) string {
	return digestValue("economic-event-permit", []any{b.Purpose, b.EconomicKey, b.TxHash, b.Request, b.Deposit, b.Withdrawal})
}

// DepositMandateMessage uses the existing Keplr-compatible ADR-36 encoder.
func DepositMandateMessage(d DepositMandate) []byte {
	d.OwnerSignature = ""
	b, _ := json.Marshal([]any{epochescrow.Protocol, "deposit-only", "wolo-1", "uwolo", d})
	m, _ := satchelservice.ReviewerADR36SignBytes(d.OwnerWallet, string(b))
	return m
}
