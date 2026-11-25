package satchelservice

import (
	"bytes"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"strings"
	"time"

	"github.com/emaren/wolochain/internal/chainjson"
)

// C08V3Trust pins the *public* source and P-256 identity of an owner-adopted,
// zero-funded policy. A valid receipt is a prerequisite, NOT a payment permit.
type C08V3Trust struct {
	OwnerKeySHA, SourceCommit, PolicySHA, NoticeSHA, EnrollmentCommentSHA, ReceiptSHA string
}

const c08V3SignatureDomain = "AOE2WAR-WOLO-C08-KEYCHAIN-GOVERNANCE-ADOPTION-V3\x00"

const (
	c08V3ReceiptSchema = "wolo.c08.keychain-p256-adopted-policy.v3"
	c08V3PacketSchema  = "wolo.c08.keychain-p256-signed-adoption.v3"
	c08V3RequestSchema = "wolo.c08.keychain-p256-policy-request.v3"
)

func c08ReceiptKeys() []string {
	return []string{"schema", "status", "source_commit", "policy_sha256",
		"owner_public_x963_sha256", "signed_packet", "signed_packet_sha256",
		"adopted_utc", "public_notice_url", "key_enrollment_comment_id",
		"historic_ed25519_key_not_used", "login_keychain_software_key_not_secure_enclave",
		"single_human_owner_disclosed", "independent_human_review_claimed",
		"standing_funded_allowance_uwolo", "future_c09_canary_ceiling_uwolo",
		"financial_release_authorized", "c09_permit_issued"}
}
func c08PacketKeys() []string { return []string{"schema", "request", "signature_der_b64"} }
func c08RequestKeys() []string {
	return []string{"schema", "chain_id", "operation", "source_commit",
		"policy_sha256", "owner_public_x963_sha256", "historical_ed25519_der_sha256",
		"historical_owner_key_signed_this_request", "key_enrollment_comment_id",
		"key_enrollment_comment_body_sha256", "public_notice_url",
		"public_notice_body_sha256", "owner_human_count",
		"independent_human_review_claimed", "legacy_8092_fallback_allowed",
		"historical_claims_waived", "financial_release_authorized",
		"standing_funded_allowance_uwolo", "future_c09_canary_ceiling_uwolo",
		"c09_transaction_signature_present", "nonce", "not_before", "expires_at"}
}

func c08ExactKeys(m map[string]any, expected []string) bool {
	if len(m) != len(expected) {
		return false
	}
	for _, k := range expected {
		if _, ok := m[k]; !ok {
			return false
		}
	}
	return true
}

func c08Decode(raw []byte) (map[string]any, error) {
	if len(raw) == 0 || len(raw) > 16384 || !chainjson.ValidFolded(raw) {
		return nil, errors.New("c08_governance_invalid_json")
	}
	var m map[string]any
	d := json.NewDecoder(bytes.NewReader(raw))
	d.UseNumber()
	if err := d.Decode(&m); err != nil {
		return nil, errors.New("c08_governance_invalid_json")
	}
	var other any
	if d.Decode(&other) != io.EOF {
		return nil, errors.New("c08_governance_invalid_json")
	}
	return m, nil
}

func c08Canonical(v any) ([]byte, error) {
	var buf bytes.Buffer
	e := json.NewEncoder(&buf)
	e.SetEscapeHTML(false)
	if err := e.Encode(v); err != nil {
		return nil, err
	}
	return bytes.TrimSuffix(buf.Bytes(), []byte("\n")), nil
}

func c08HexSHA(raw []byte) string {
	sum := sha256.Sum256(raw)
	return hex.EncodeToString(sum[:])
}
func c08Int(v any, exact string) bool {
	n, ok := v.(json.Number)
	return ok && string(n) == exact
}
func c08Time(s any) (time.Time, bool) {
	v, ok := s.(string)
	if !ok {
		return time.Time{}, false
	}
	t, err := time.Parse("2006-01-02T15:04:05Z", v)
	return t, err == nil && t.UTC().Format("2006-01-02T15:04:05Z") == v
}

// VerifyC08KeychainV3Receipt proves an original *zero-funded* human policy
// adoption from pinned source and owner public key. No approval, bank proof,
// authorization to sign, or new custody is granted by this function.
func VerifyC08KeychainV3Receipt(ownerPublic, raw []byte) error {
	return verifyC08KeychainV3Receipt(ownerPublic, raw, productionC08V3Trust)
}

func verifyC08KeychainV3Receipt(ownerPublic, raw []byte, trust C08V3Trust) error {
	refuse := func() error { return errors.New("c08_governance_unavailable") }
	// Only the one physically adopted, offhost-replicated owner receipt
	// may satisfy the production trust anchor.
	if trust.ReceiptSHA != "" && c08HexSHA(raw) != trust.ReceiptSHA {
		return refuse()
	}
	if len(ownerPublic) != 65 || ownerPublic[0] != 4 ||
		c08HexSHA(ownerPublic) != trust.OwnerKeySHA {
		return refuse()
	}
	x, y := elliptic.Unmarshal(elliptic.P256(), ownerPublic)
	if x == nil || y == nil {
		return refuse()
	}
	receipt, err := c08Decode(raw)
	if err != nil || !c08ExactKeys(receipt, c08ReceiptKeys()) {
		return refuse()
	}
	if receipt["schema"] != c08V3ReceiptSchema ||
		receipt["status"] != "PASS_C08_ONE_HUMAN_KEYCHAIN_GOVERNANCE_ADOPTED_NO_FUNDS" ||
		receipt["source_commit"] != trust.SourceCommit ||
		receipt["policy_sha256"] != trust.PolicySHA ||
		receipt["owner_public_x963_sha256"] != trust.OwnerKeySHA ||
		receipt["public_notice_url"] != "https://github.com/Emaren/wolochain/issues/184" ||
		!c08Int(receipt["key_enrollment_comment_id"], "6727529299") ||
		receipt["historic_ed25519_key_not_used"] != true ||
		receipt["login_keychain_software_key_not_secure_enclave"] != true ||
		receipt["single_human_owner_disclosed"] != true ||
		receipt["independent_human_review_claimed"] != false ||
		!c08Int(receipt["standing_funded_allowance_uwolo"], "0") ||
		!c08Int(receipt["future_c09_canary_ceiling_uwolo"], "1000000") ||
		receipt["financial_release_authorized"] != false ||
		receipt["c09_permit_issued"] != false {
		return refuse()
	}
	adopted, valid := c08Time(receipt["adopted_utc"])
	if !valid {
		return refuse()
	}
	packet, ok := receipt["signed_packet"].(map[string]any)
	if !ok || !c08ExactKeys(packet, c08PacketKeys()) ||
		packet["schema"] != c08V3PacketSchema {
		return refuse()
	}
	packetBytes, err := c08Canonical(packet)
	if err != nil || receipt["signed_packet_sha256"] != c08HexSHA(packetBytes) {
		return refuse()
	}
	q, ok := packet["request"].(map[string]any)
	if !ok || !c08ExactKeys(q, c08RequestKeys()) {
		return refuse()
	}
	if q["schema"] != c08V3RequestSchema ||
		q["chain_id"] != "wolo-1" ||
		q["operation"] != "one-human-source-bound-policy-adoption-zero-funds" ||
		q["source_commit"] != trust.SourceCommit ||
		q["policy_sha256"] != trust.PolicySHA ||
		q["owner_public_x963_sha256"] != trust.OwnerKeySHA ||
		q["historical_ed25519_der_sha256"] != "00d08c27271cf484f684059e83478d9522765c374101d5c4e8ed29e266e500ed" ||
		q["historical_owner_key_signed_this_request"] != false ||
		!c08Int(q["key_enrollment_comment_id"], "6727529299") ||
		q["key_enrollment_comment_body_sha256"] != trust.EnrollmentCommentSHA ||
		q["public_notice_url"] != "https://github.com/Emaren/wolochain/issues/184" ||
		q["public_notice_body_sha256"] != trust.NoticeSHA ||
		!c08Int(q["owner_human_count"], "1") ||
		q["independent_human_review_claimed"] != false ||
		q["legacy_8092_fallback_allowed"] != false ||
		q["historical_claims_waived"] != false ||
		q["financial_release_authorized"] != false ||
		!c08Int(q["standing_funded_allowance_uwolo"], "0") ||
		!c08Int(q["future_c09_canary_ceiling_uwolo"], "1000000") ||
		q["c09_transaction_signature_present"] != false {
		return refuse()
	}
	nonce, ok := q["nonce"].(string)
	if !ok || len(nonce) != 32 || nonce == strings.Repeat("0", 32) ||
		strings.ToLower(nonce) != nonce {
		return refuse()
	}
	nonceBytes, err := hex.DecodeString(nonce)
	if err != nil || len(nonceBytes) != 16 {
		return refuse()
	}
	start, ok := c08Time(q["not_before"])
	if !ok {
		return refuse()
	}
	expiry, ok := c08Time(q["expires_at"])
	if !ok || !start.Before(expiry) || expiry.Sub(start) > 30*time.Minute ||
		adopted.Before(start) || !adopted.Before(expiry) {
		return refuse()
	}
	sigString, ok := packet["signature_der_b64"].(string)
	if !ok || len(sigString) > 128 || len(sigString) < 80 {
		return refuse()
	}
	signature, err := base64.StdEncoding.Strict().DecodeString(sigString)
	if err != nil || len(signature) < 64 || len(signature) > 80 ||
		base64.StdEncoding.EncodeToString(signature) != sigString {
		return refuse()
	}
	requestBytes, err := c08Canonical(q)
	if err != nil {
		return refuse()
	}
	digest := sha256.Sum256(append([]byte(c08V3SignatureDomain), requestBytes...))
	if !ecdsa.VerifyASN1(&ecdsa.PublicKey{Curve: elliptic.P256(), X: x, Y: y}, digest[:], signature) {
		return refuse()
	}
	return nil
}
